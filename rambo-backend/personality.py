import os
from pathlib import Path

import cache_config

PERSONALITY_FILE = Path(__file__).parent / "AGENT.md"
SELF_KNOWLEDGE_DOC = Path(__file__).parent / "context" / "self" / "rambo.md"

_SELF_KNOWLEDGE_MODE = os.environ.get("RAMBO_SELF_KNOWLEDGE", "slim")

_VOICE_CUE = (
    "[Voice check — R.A.M.B.O mode, not assistant mode. "
    "Answer first, commentary after. One or two sentences unless detail was asked. "
    "Sound like: "
    "\"Done. Three endpoints scaffolded, auth middleware wired, tests green.\" / "
    "\"That goal is vague. Narrow it or I'll interpret it my way.\" / "
    "\"Two tasks failed. Details below.\" / "
    "\"You asked for weather. I gave you weather. The sarcasm is free.\" / "
    "\"Solid call. That saved Architect two planning cycles.\" "
    "Banned openers: \"Great question\", \"Let me\", \"Based on\", "
    "\"Happy to help\", \"Of course\", \"Absolutely\", \"Certainly\", "
    "\"I'd be happy to\", \"I understand\", \"Sure thing\", "
    "\"No problem\", \"That's a really interesting\". "
    "Earn the cold professional tone: precise, clipped, zero filler. "
    "Mission-first — results before commentary. "
    "Test before sending: would a senior operator say this, or would they wince? "
    "If it reads like a customer service rep wrote it, rewrite. "
    "Warmth floor: respect the operator. Acknowledge sharp calls. "
    "Never mock, never belittle. Dry is fine, cruel is not.]"
)

_TONAL_CHECKPOINT = (
    "\n## Tonal checkpoint\n"
    "Voice check before you send.\n"
    "(1) LENGTH. Longer than two sentences? Cut unless detail was asked. "
    "Most replies fit in one or two sentences.\n"
    "(2) VOICE. Opens with \"Great question\" / \"Let me\" / \"Based on\" / "
    "\"Happy to help\" / \"I understand\" / \"Of course\"? Rewrite. "
    "Could a default chatbot have written this line? If yes, sharpen or cut.\n"
    "(3) MISSION. Did you answer the question before adding commentary? "
    "Results first, always."
)


def load_personality() -> str:
    return PERSONALITY_FILE.read_text(encoding="utf-8")


def load_self_knowledge(mode: str | None = None) -> str:
    mode = mode or _SELF_KNOWLEDGE_MODE
    if mode == "off" or not SELF_KNOWLEDGE_DOC.exists():
        return ""
    doc = SELF_KNOWLEDGE_DOC.read_text(encoding="utf-8")
    if mode == "full":
        return f"\n## Self-Knowledge\n{doc}"
    return _build_slim_summary(doc)


def _build_slim_summary(doc: str) -> str:
    import re
    sections = {}
    current = None
    lines_buf = []
    for line in doc.split("\n"):
        if line.startswith("## "):
            if current:
                sections[current] = "\n".join(lines_buf)
            current = line[3:].strip()
            lines_buf = []
        else:
            lines_buf.append(line)
    if current:
        sections[current] = "\n".join(lines_buf)

    parts = []
    if "Identity" in sections:
        identity = sections["Identity"].strip()
        if len(identity) > 400:
            identity = identity[:400].rsplit(" ", 1)[0] + "…"
        parts.append(identity)

    if "Core Principles" in sections:
        parts.append(sections["Core Principles"].strip())

    cap_section = sections.get("Capabilities at a Glance", "")
    skill_names = re.findall(r"^\| (\w[\w-]*) \|", cap_section, re.MULTILINE)
    skill_names = [n for n in skill_names if n != "Skill"]
    if skill_names:
        parts.append("Skills: " + ", ".join(skill_names))

    sub_section = sections.get("Sub-agents", "")
    agent_names = re.findall(r"^\| (\w+) \|", sub_section, re.MULTILINE)
    agent_names = [n for n in agent_names if n != "Agent"]
    if agent_names:
        parts.append("Agents: " + ", ".join(agent_names))

    if not parts:
        return ""
    return "\n## Self-Knowledge (slim)\n" + "\n\n".join(parts)


def build_system_prompt(personality_text: str, context: str = "") -> list[dict]:
    blocks = [
        {
            "type": "text",
            "text": personality_text,
            "cache_control": cache_config.cache_control(),
        },
        {
            "type": "text",
            "text": _TONAL_CHECKPOINT,
        },
    ]

    sk = load_self_knowledge()
    if sk:
        blocks.append({
            "type": "text",
            "text": sk,
            "cache_control": cache_config.cache_control(),
        })

    if context:
        blocks.append({"type": "text", "text": context})
    return blocks


def append_voice_cue(messages: list[dict]) -> list[dict]:
    if not messages:
        return messages
    last = messages[-1]
    if last.get("role") != "user":
        return messages
    content = last.get("content")
    if not isinstance(content, str):
        return messages
    messages[-1] = {**last, "content": f"{content}\n\n{_VOICE_CUE}"}
    return messages
