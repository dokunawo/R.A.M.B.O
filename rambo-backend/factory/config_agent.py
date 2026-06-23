"""Tier 5 — ConfigDrivenAgent.

A single generic runtime that reads a spawned_agents row and runs a
vanilla tool-use loop. No specialist logic — behavior comes entirely
from the row's system_prompt and tool_allowlist.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from factory.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 8


class ConfigDrivenAgent:
    def __init__(self, row: dict, tool_registry: ToolRegistry, llm_client,
                 cache_prompt: bool = True):
        self._row = row
        self._tools = tool_registry
        self._llm = llm_client
        # Caching is on by default. An agent that combines this loop with
        # context-management/compaction can pass cache_prompt=False to be left
        # byte-for-byte unchanged.
        self._cache_prompt = cache_prompt

    def _filtered_tools(self) -> list[dict]:
        return self._tools.to_anthropic_tools(names=self._row["tool_allowlist"])

    def _system(self):
        """Return the system prompt. When caching is on, return it as a single
        cached text block so tools+system (tools render first) are cached
        together as one stable prefix every spawned agent re-sends."""
        text = self._row["system_prompt"]
        if not self._cache_prompt:
            return text
        import cache_config
        return [{
            "type": "text",
            "text": text,
            "cache_control": cache_config.cache_control(),
        }]

    async def run(self, user_message: str) -> str:
        tools = self._filtered_tools()
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_message},
        ]

        for _ in range(MAX_ITERATIONS):
            response = await self._llm.messages.create(
                model=self._row.get("model", "claude-sonnet-4-20250514"),
                max_tokens=4096,
                system=self._system(),
                messages=messages,
                tools=tools if tools else [],
            )

            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                return self._extract_text(response.content)

            tool_results = []
            pending_confirmations = []
            for block in response.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                tool_def = self._tools.get(block.name)
                if tool_def is None or block.name not in self._row["tool_allowlist"]:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps({"error": f"Tool '{block.name}' not available"}),
                        "is_error": True,
                    })
                    continue

                # Tier 4: gated tools are NOT executed — stage a confirmation.
                if getattr(tool_def, "requires_confirmation", False):
                    from factory import confirmations
                    rec = confirmations.request_confirmation(
                        block.name, dict(block.input), agent_slug=self._row.get("slug"),
                    )
                    pending_confirmations.append(rec)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps({
                            "status": "confirmation_required",
                            "confirmation_id": rec["id"],
                            "tool": block.name,
                            "note": "This action needs human approval and was not executed.",
                        }),
                    })
                    continue

                try:
                    result = await tool_def.execute(**block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
                except Exception as exc:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps({"error": str(exc)}),
                        "is_error": True,
                    })

            # If anything needs confirmation, stop here — the action waits for a
            # human. The agent can resume once approved (out-of-band execution).
            if pending_confirmations:
                messages.append({"role": "user", "content": tool_results})
                names = ", ".join(f"{c['tool_name']} (id={c['id']})" for c in pending_confirmations)
                return f"⏸ Awaiting your confirmation before running: {names}"

            if tool_results:
                messages.append({"role": "user", "content": tool_results})
            else:
                return self._extract_text(response.content)

        return self._extract_text(messages[-1].get("content", []))

    @staticmethod
    def _extract_text(content) -> str:
        if isinstance(content, str):
            return content
        parts = []
        for block in content:
            if getattr(block, "type", None) == "text":
                parts.append(block.text)
        return "\n".join(parts) if parts else "(no text response)"
