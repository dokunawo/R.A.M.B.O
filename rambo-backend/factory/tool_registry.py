"""Global tool registry for Factory-spawned agents.

Each tool has a name, description, JSON input schema, an async execute
function, and a factory_allowed flag controlling whether the Factory can
grant it to spawned agents.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


@dataclass
class ToolDef:
    name: str
    description: str
    input_schema: dict
    execute: Callable[..., Awaitable[str]]
    factory_allowed: bool = True
    # Tier 4 — human-in-the-loop. When True, the tool router stops and asks for
    # explicit confirmation before this tool runs, instead of executing it.
    requires_confirmation: bool = False


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolDef] = {}

    def register(self, tool: ToolDef) -> None:
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get(self, name: str) -> ToolDef | None:
        return self._tools.get(name)

    def list_all(self) -> list[ToolDef]:
        return list(self._tools.values())

    def list_factory_allowed(self) -> list[ToolDef]:
        return [t for t in self._tools.values() if t.factory_allowed]

    def names_factory_allowed(self) -> list[str]:
        return [t.name for t in self._tools.values() if t.factory_allowed]

    def to_anthropic_tools(self, names: list[str] | None = None) -> list[dict]:
        """Convert tools to Anthropic API tool format."""
        tools = self._tools.values() if names is None else [
            self._tools[n] for n in names if n in self._tools
        ]
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in tools
        ]


# ── Built-in tools ───────────────────────────────────────────────

async def _web_search(query: str, **kwargs) -> str:
    return json.dumps({"note": "web_search is handled natively by Anthropic"})


async def _read_file(path: str, **kwargs) -> str:
    from pathlib import Path
    p = Path(path)
    if not p.exists():
        return json.dumps({"error": f"File not found: {path}"})
    return p.read_text(encoding="utf-8", errors="replace")[:10_000]


async def _write_file(path: str, content: str, **kwargs) -> str:
    from pathlib import Path
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return json.dumps({"written": str(p), "bytes": len(content)})


async def _http_get(url: str, **kwargs) -> str:
    try:
        import httpx
    except ImportError:
        return json.dumps({"error": "httpx not installed"})
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url)
        return r.text[:10_000]


async def _list_files(directory: str = ".", pattern: str = "*", **kwargs) -> str:
    from pathlib import Path
    p = Path(directory)
    if not p.is_dir():
        return json.dumps({"error": f"Not a directory: {directory}"})
    files = sorted(str(f.relative_to(p)) for f in p.rglob(pattern))[:100]
    return json.dumps(files)


async def _summarize_text(text: str, **kwargs) -> str:
    return json.dumps({
        "note": "summarize_text is handled by the agent's LLM — "
                "include the text in the conversation and ask for a summary"
    })


async def _propose_handoff(target_agent: str, reason: str, task: str,
                           artifacts: dict | None = None,
                           preconditions: list | None = None,
                           confidence: float = 0.5, **kwargs) -> str:
    """Record a handoff recommendation for human approval. Does NOT dispatch."""
    from factory.handoff import HandoffRecommendation, propose
    rec = HandoffRecommendation(
        target_agent=target_agent, reason=reason, task=task,
        artifacts=artifacts or {}, preconditions=preconditions or [],
        confidence=confidence,
    )
    entry = propose(rec, from_agent=kwargs.get("_from_agent"))
    return json.dumps({
        "status": "handoff_proposed",
        "handoff_id": entry["id"],
        "note": "Recommendation recorded. A human must approve before the "
                "target agent runs. You did not dispatch it.",
    })


def build_default_registry() -> ToolRegistry:
    """Populate a registry with the initial set of tools."""
    reg = ToolRegistry()

    reg.register(ToolDef(
        name="read_file",
        description="Read the contents of a file at a given path. Returns up to 10,000 characters.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or relative file path"},
            },
            "required": ["path"],
        },
        execute=_read_file,
        factory_allowed=True,
    ))

    reg.register(ToolDef(
        name="write_file",
        description="Write content to a file, creating directories as needed.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write to"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["path", "content"],
        },
        execute=_write_file,
        factory_allowed=True,
        requires_confirmation=True,  # writing/overwriting files is irreversible
    ))

    reg.register(ToolDef(
        name="list_files",
        description="List files in a directory, optionally matching a glob pattern.",
        input_schema={
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Directory to list", "default": "."},
                "pattern": {"type": "string", "description": "Glob pattern", "default": "*"},
            },
        },
        execute=_list_files,
        factory_allowed=True,
    ))

    reg.register(ToolDef(
        name="http_get",
        description="Fetch a URL via HTTP GET and return the response body (up to 10,000 chars).",
        input_schema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to fetch"},
            },
            "required": ["url"],
        },
        execute=_http_get,
        factory_allowed=True,
    ))

    reg.register(ToolDef(
        name="summarize_text",
        description="Summarize a block of text into key points.",
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to summarize"},
            },
            "required": ["text"],
        },
        execute=_summarize_text,
        factory_allowed=True,
    ))

    reg.register(ToolDef(
        name="propose_handoff",
        description=(
            "Recommend the NEXT step and which agent should take it. This does "
            "NOT run the next agent — it records a proposal for a human to "
            "approve. Pass artifacts as references (paths/IDs/URLs), not inline "
            "content."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "target_agent": {"type": "string", "description": "Slug/name of the agent to take the next step"},
                "reason": {"type": "string", "description": "One sentence on why this handoff helps"},
                "task": {"type": "string", "description": "The task to pass the next agent verbatim"},
                "artifacts": {"type": "object", "description": "Map of name → path/ID/URL the next agent should read"},
                "preconditions": {"type": "array", "items": {"type": "string"}, "description": "Things the human should verify first"},
                "confidence": {"type": "number", "description": "0–1 confidence in this handoff"},
            },
            "required": ["target_agent", "reason", "task"],
        },
        execute=_propose_handoff,
        factory_allowed=True,
    ))

    return reg
