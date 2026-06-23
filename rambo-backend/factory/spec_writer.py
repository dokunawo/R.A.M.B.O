"""Tier 2 — Spec markdown + system-prompt generation.

Turns a SkillsReport into:
  1. A human-readable spec markdown file at agent-specs/<slug>.md
  2. A generated system prompt for the spawned agent
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from factory.schemas import SkillsReport

logger = logging.getLogger(__name__)

_SPECS_DIR = Path(__file__).resolve().parent.parent / "agent-specs"

_META_PROMPT = """\
You write system prompts for AI sub-agents.

Given:
  - the agent's name
  - the agent's role / domain
  - a Skills Report (competencies, tools, design patterns)
  - any special requirements from the user

Produce a system prompt that:
  - addresses the agent in second person ("You are <name>...")
  - states the agent's domain and competencies clearly
  - tells the agent which tools it has and when to use them
  - encodes any special requirements
  - is 200-500 words

Return ONLY the system prompt text. No preamble, no commentary."""

_REVISION_ADDENDUM = """
The previous draft was:
---
{prior_prompt}
---
The user asked for these changes:
{revision_feedback}
Produce a revised system prompt incorporating the feedback."""


def write_spec_markdown(
    *,
    slug: str,
    name: str,
    role_description: str,
    special_requirements: str,
    report: SkillsReport,
) -> Path:
    """Write a human-readable spec file and return its path."""
    _SPECS_DIR.mkdir(parents=True, exist_ok=True)
    path = _SPECS_DIR / f"{slug}.md"

    wishlist_lines = ""
    for w in report.tools_wishlist:
        dep = f" (needs: {w.external_dependency})" if w.external_dependency else ""
        wishlist_lines += f"- **{w.name}**: {w.purpose}{dep}\n"

    source_lines = ""
    for s in report.sources:
        excerpt = f" — {s.excerpt}" if s.excerpt else ""
        source_lines += f"- [{s.title}]({s.url}){excerpt}\n"

    md = f"""# Agent Spec: {name}

**Slug:** `{slug}`
**Role:** {role_description}
**Special Requirements:** {special_requirements or 'None'}

---

## Competencies

{chr(10).join(f'- {c}' for c in report.competencies)}

## Granted Tools

{chr(10).join(f'- `{t}`' for t in report.tools_available) or '- (none)'}

## Tool Wishlist

{wishlist_lines or '- (none)'}

## Design Patterns

{chr(10).join(f'- {p}' for p in report.design_patterns)}

## Sources

{source_lines}
"""
    path.write_text(md, encoding="utf-8")
    logger.info("Wrote spec: %s", path)
    return path


async def generate_system_prompt(
    *,
    llm_client,
    name: str,
    role_description: str,
    special_requirements: str,
    report: SkillsReport,
    prior_prompt: str | None = None,
    revision_feedback: str | None = None,
) -> str:
    """Generate a system prompt for a spawned agent via one LLM call."""
    user_content = (
        f"Agent name: {name}\n"
        f"Role: {role_description}\n"
        f"Special requirements: {special_requirements or 'None'}\n\n"
        f"Skills Report:\n{report.model_dump_json(indent=2)}"
    )

    if prior_prompt and revision_feedback:
        user_content += "\n\n" + _REVISION_ADDENDUM.format(
            prior_prompt=prior_prompt,
            revision_feedback=revision_feedback,
        )

    response = await llm_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        system=_META_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    prompt_text = ""
    for block in response.content:
        if getattr(block, "type", None) == "text":
            prompt_text += block.text

    prompt_text = prompt_text.strip()
    if not prompt_text:
        raise RuntimeError("LLM returned empty system prompt")

    return prompt_text
