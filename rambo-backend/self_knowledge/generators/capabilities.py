"""
Generates the capabilities AUTO block from the SKILLS registry in skills.py.
"""

from __future__ import annotations


def generate(skills: list[dict] | None = None) -> str:
    if skills is None:
        try:
            from skills import SKILLS
            skills = SKILLS
        except ImportError:
            return "_unavailable — could not import skills registry_"

    if not skills:
        return "_No skills registered._"

    lines = ["| Skill | Routed To | Match Keywords |", "| --- | --- | --- |"]
    for s in skills:
        name = s.get("name", "?")
        agent = s.get("agent", "?")
        matcher = s.get("match")
        keywords = _extract_keywords(matcher) if matcher else "—"
        lines.append(f"| {name} | {agent} | {keywords} |")

    return "\n".join(lines)


def _extract_keywords(matcher) -> str:
    try:
        source = _get_lambda_source(matcher)
        if source:
            return source
    except Exception:
        pass
    return "custom matcher"


def _get_lambda_source(fn) -> str | None:
    import inspect
    try:
        src = inspect.getsource(fn).strip()
    except (OSError, TypeError):
        return None
    # Extract keyword strings from lambda bodies like:
    # lambda g: any(w in g.lower() for w in ("weather", "temperature"))
    import re
    matches = re.findall(r'"([^"]+)"', src)
    if matches:
        return ", ".join(matches[:6]) + ("…" if len(matches) > 6 else "")
    return None
