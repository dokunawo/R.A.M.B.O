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
    def __init__(self, row: dict, tool_registry: ToolRegistry, llm_client):
        self._row = row
        self._tools = tool_registry
        self._llm = llm_client

    def _filtered_tools(self) -> list[dict]:
        return self._tools.to_anthropic_tools(names=self._row["tool_allowlist"])

    async def run(self, user_message: str) -> str:
        tools = self._filtered_tools()
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_message},
        ]

        for _ in range(MAX_ITERATIONS):
            response = await self._llm.messages.create(
                model=self._row.get("model", "claude-sonnet-4-20250514"),
                max_tokens=4096,
                system=self._row["system_prompt"],
                messages=messages,
                tools=tools if tools else [],
            )

            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                return self._extract_text(response.content)

            tool_results = []
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
