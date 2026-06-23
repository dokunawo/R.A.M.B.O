"""Tier 1 — Research subagent.

Given a role description, produces a structured Skills Report by
searching the web and synthesizing findings. Uses Anthropic's native
web_search tool and a forced emit_skills_report tool call on the
final iteration.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

from factory.schemas import SkillsReport

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 8

_EMIT_TOOL = {
    "name": "emit_skills_report",
    "description": (
        "Emit the final structured Skills Report. You MUST call this "
        "tool exactly once to complete your research."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "domain": {"type": "string"},
            "competencies": {
                "type": "array", "items": {"type": "string"},
                "minItems": 4, "maxItems": 8,
            },
            "tools_available": {
                "type": "array", "items": {"type": "string"},
            },
            "tools_wishlist": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "purpose": {"type": "string"},
                        "external_dependency": {"type": "string"},
                    },
                    "required": ["name", "purpose"],
                },
            },
            "design_patterns": {
                "type": "array", "items": {"type": "string"},
                "minItems": 2, "maxItems": 5,
            },
            "sources": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "title": {"type": "string"},
                        "excerpt": {"type": "string"},
                    },
                    "required": ["url", "title"],
                },
                "minItems": 3, "maxItems": 15,
            },
        },
        "required": [
            "domain", "competencies", "tools_available",
            "tools_wishlist", "design_patterns", "sources",
        ],
    },
}

_WEB_SEARCH_TOOL = {
    "name": "web_search",
    "type": "web_search_20250305",
}


def _build_system_prompt(factory_tool_names: list[str]) -> str:
    tool_list = ", ".join(factory_tool_names) if factory_tool_names else "(none)"
    return (
        "You are a research specialist. Your job: research what an agent "
        "that does the described role should be capable of, and produce a "
        "structured Skills Report.\n\n"
        "You have access to web_search. Use it 3-6 times to gather real "
        "evidence from real sources (vendor docs, open-source projects, "
        "technical blogs).\n\n"
        "You MUST end by calling emit_skills_report with these fields:\n"
        "- domain: the domain you researched\n"
        "- competencies: 4-8 concrete capabilities the agent should have\n"
        "- tools_available: tool names from this catalog the agent can use "
        f"today: {tool_list}\n"
        "- tools_wishlist: tools we DON'T have yet that this agent would need\n"
        "- design_patterns: 2-5 real patterns you observed\n"
        "- sources: 3-15 sources with url + title + short excerpt (<400 chars)\n\n"
        "Quote excerpts must be SHORT and clearly attributable."
    )


def _normalize_query(role_description: str) -> str:
    return re.sub(r"\s+", " ", role_description.strip().lower())


async def run_research(
    *,
    llm_client,
    role_description: str,
    factory_tool_names: list[str],
    repo=None,
) -> SkillsReport:
    """Run the research loop and return a validated SkillsReport.

    If repo is provided, checks for a cached report first and persists
    the result.
    """
    query_key = _normalize_query(role_description)

    if repo:
        cached = await repo.get_cached_report(query_key)
        if cached:
            logger.info("Cache hit for research query: %s", query_key)
            return SkillsReport(**cached["report_json"])

    # Single cached block: caches tools + system together as a stable prefix
    # re-sent on every iteration of this research loop.
    import cache_config
    system_prompt = [{
        "type": "text",
        "text": _build_system_prompt(factory_tool_names),
        "cache_control": cache_config.cache_control(),
    }]
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": f"Research this agent role: {role_description}"},
    ]
    tools = [_WEB_SEARCH_TOOL, _EMIT_TOOL]

    for iteration in range(MAX_ITERATIONS):
        is_last = iteration == MAX_ITERATIONS - 1

        kwargs: dict[str, Any] = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 4096,
            "system": system_prompt,
            "messages": messages,
            "tools": tools,
        }
        if is_last:
            kwargs["tool_choice"] = {"type": "tool", "name": "emit_skills_report"}

        response = await llm_client.messages.create(**kwargs)

        # Collect assistant content
        messages.append({"role": "assistant", "content": response.content})

        # Check for emit_skills_report call
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == "emit_skills_report":
                report = SkillsReport(**block.input)
                if repo:
                    report_id = uuid.uuid4().hex
                    await repo.save_report(
                        report_id=report_id,
                        query_key=query_key,
                        report=report.model_dump(),
                    )
                return report

        # Build tool results for any tool_use blocks
        tool_results = []
        for block in response.content:
            if getattr(block, "type", None) == "tool_use":
                if block.name == "web_search":
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": "Search results provided by Anthropic web search.",
                    })
                else:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps({"error": f"Unknown tool: {block.name}"}),
                    })

        if tool_results:
            messages.append({"role": "user", "content": tool_results})
        elif response.stop_reason == "end_turn":
            messages.append({
                "role": "user",
                "content": "You must call emit_skills_report to complete your research.",
            })

    raise RuntimeError("Research loop exhausted without emitting a Skills Report")
