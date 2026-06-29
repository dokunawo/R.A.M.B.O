"""Chief of Staff skill — doctrine-anchored daily prioritization."""

import re
from pathlib import Path
from datetime import datetime, date

NORTH_STAR_PATHS = [
    Path(__file__).parent / "north-star.md",
    Path.home() / ".claude" / "north-star.md",
]


def _find_doctrine() -> Path | None:
    for p in NORTH_STAR_PATHS:
        if p.exists() and p.stat().st_size > 0:
            return p
    return None


def _parse_frontmatter(text: str) -> dict | None:
    m = re.match(r'^---\s*\n(.*?)\n---', text, re.DOTALL)
    if not m:
        return None
    fm = {}
    for line in m.group(1).splitlines():
        if ':' in line:
            key, val = line.split(':', 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if val.startswith('[') and val.endswith(']'):
                val = [x.strip() for x in val[1:-1].split(',')]
            fm[key] = val
    if fm.get('type') != 'north-star':
        return None
    return fm


def _extract_section(text: str, heading: str) -> str:
    pattern = rf'^##\s+.*{re.escape(heading)}.*$'
    m = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
    if not m:
        return ""
    start = m.end()
    next_heading = re.search(r'^##\s+', text[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(text)
    return text[start:end].strip()


def _extract_rules(text: str) -> list[str]:
    section = _extract_section(text, "Operating Rules")
    return [line.lstrip('- ').strip() for line in section.splitlines() if line.strip().startswith('-')]


def north_star_context() -> str | None:
    """Compact north-star doctrine (revenue target + operating rules) as plain text
    for injection into RAMBO's reasoning context, so it weighs the operator's goal
    when advising/prioritizing. None when no doctrine doc exists."""
    p = _find_doctrine()
    if not p:
        return None
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return None
    fm = _parse_frontmatter(text)
    if not fm or not fm.get("target"):
        return None
    parts = [f"Revenue goal: {fm['target']}."]
    rules = _extract_rules(text)
    if rules:
        parts.append("Operating rules: " + "; ".join(rules) + ".")
    return " ".join(parts)


def _staleness_check(fm: dict) -> str | None:
    reviewed = fm.get('last_reviewed', '')
    cadence = int(fm.get('review_cadence_days', 30))
    try:
        reviewed_date = date.fromisoformat(reviewed)
        days_ago = (date.today() - reviewed_date).days
        if days_ago > cadence:
            return f"⚠️ Doctrine last reviewed {days_ago} days ago — consider a review."
    except (ValueError, TypeError):
        pass
    return None


async def chief_of_staff_skill(goal: str, ctx: dict) -> str:
    doc_path = _find_doctrine()
    if not doc_path:
        return (
            "Can't run the daily brief — no valid north-star doc found.\n\n"
            "This skill needs a doctrine doc with your revenue target, 90-day filter, "
            "and operating rules. Create north-star.md in the backend directory or ~/.claude/.\n\n"
            "Run the Chief of Staff setup in Claude Code first: it will walk you through writing one."
        )

    text = doc_path.read_text(encoding='utf-8')
    fm = _parse_frontmatter(text)
    if not fm:
        return "north-star.md exists but has invalid or missing frontmatter. Needs type: north-star."

    target = fm.get('target', '(no target set)')
    filters = fm.get('filter', ['sales', 'delivery_speed', 'margin', 'retention'])
    if isinstance(filters, str):
        filters = [f.strip() for f in filters.split(',')]

    objective = _extract_section(text, "Objective")
    rules = _extract_rules(text)
    errata = _extract_section(text, "Errata")

    staleness = _staleness_check(fm)
    today = datetime.now().strftime("%Y-%m-%d")

    brief_parts = [
        f"# Daily Revenue Brief — {fm.get('product', 'Operations')} — {today}",
    ]
    if staleness:
        brief_parts.append(staleness)

    if errata and not errata.startswith("("):
        brief_parts.append(f"\n**Errata override:** {errata}")

    brief_parts.append(f"\n**Active objective:** {target}")
    brief_parts.append(f"**Filter dimensions:** {' · '.join(filters)}")

    if objective:
        brief_parts.append(f"\n**90-day focus:** {objective}")

    if rules:
        brief_parts.append("\n**Operating rules in effect:**")
        for r in rules:
            brief_parts.append(f"  - {r}")

    brief_parts.append(f"\n---\nDoctrine: {doc_path}  ·  Last reviewed: {fm.get('last_reviewed', 'unknown')}")

    return "\n".join(brief_parts)
