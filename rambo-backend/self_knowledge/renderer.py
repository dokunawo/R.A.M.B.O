"""
Full renderer — wires generators to AUTO block names and renders the doc.
"""

from __future__ import annotations

from pathlib import Path

from self_knowledge.parser import render
from self_knowledge.generators.capabilities import generate as gen_capabilities
from self_knowledge.generators.subagents import generate as gen_subagents
from self_knowledge.generators.integrations import generate as gen_integrations
from self_knowledge.generators.voice import generate as gen_voice
from self_knowledge.generators.recent_activity import generate as gen_recent_activity


_DOC_PATH = Path(__file__).resolve().parent.parent / "context" / "self" / "rambo.md"

GENERATORS = {
    "capabilities": gen_capabilities,
    "subagents": gen_subagents,
    "integrations": gen_integrations,
    "voice": gen_voice,
    "recent_activity": gen_recent_activity,
}


def render_doc(doc_path: Path | None = None) -> str:
    path = doc_path or _DOC_PATH
    doc = path.read_text(encoding="utf-8")
    return render(doc, GENERATORS)


def refresh_doc(doc_path: Path | None = None) -> bool:
    path = doc_path or _DOC_PATH
    current = path.read_text(encoding="utf-8")
    rendered = render(current, GENERATORS)
    if rendered != current:
        path.write_text(rendered, encoding="utf-8")
        return True
    return False
