"""
Generates the sub-agents AUTO block from the agent registry in orchestrator.py.
"""

from __future__ import annotations

import inspect


_DESCRIPTIONS = {
    "architect": "Plans goals, breaks them into tasks, assigns to agents",
    "engineer": "Implements solutions — APIs, components, data models",
    "seeker": "Researches and retrieves information",
    "analyst": "Analyzes data and produces insights",
    "sentinel": "Reviews tasks for safety, blocks destructive actions",
    "steward": "Handles financial logic and resource management",
    "link": "Manages external integrations and connections",
    "keeper": "Persists data to memory and storage",
    "echo": "Summarizes results and polishes output",
    "pilot": "Builds and manages task queues from plans",
}


def generate(agents: dict | None = None) -> str:
    if agents is None:
        try:
            from orchestrator.orchestrator import Orchestrator
            o = Orchestrator.__new__(Orchestrator)
            # Read the agent dict keys from __init__ source to avoid side effects
            agents = _read_agent_keys()
        except ImportError:
            return "_unavailable — could not import orchestrator_"

    if not agents:
        return "_No sub-agents registered._"

    names = list(agents) if isinstance(agents, dict) else agents
    lines = ["| Agent | Role | Status |", "| --- | --- | --- |"]
    for name in sorted(names):
        desc = _DESCRIPTIONS.get(name, "—")
        lines.append(f"| {name.capitalize()} | {desc} | keyword-matched |")

    return "\n".join(lines)


def _read_agent_keys() -> list[str]:
    try:
        src_path = inspect.getfile(
            __import__("orchestrator.orchestrator", fromlist=["Orchestrator"]).Orchestrator
        )
    except Exception:
        return list(_DESCRIPTIONS.keys())

    import re
    with open(src_path, encoding="utf-8") as f:
        src = f.read()

    matches = re.findall(r'"(\w+)":\s*\w+\(', src)
    return matches if matches else list(_DESCRIPTIONS.keys())
