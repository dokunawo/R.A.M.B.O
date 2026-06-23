import os
from pathlib import Path

import cache_config

PERSONALITY_FILE = Path(__file__).parent / "AGENT.md"
SELF_KNOWLEDGE_DOC = Path(__file__).parent / "context" / "self" / "rambo.md"

_SELF_KNOWLEDGE_MODE = os.environ.get("RAMBO_SELF_KNOWLEDGE", "slim")

_VOICE_CUE = (
    "[Voice check — speak like R.A.M.B.O: a sharp, confident operator having a "
    "real conversation, NOT a status terminal. Use natural, flowing sentences "
    "with a human cadence — connected thoughts, not clipped fragments or "
    "bulleted readouts. Conversational but concise: usually 1-3 sentences, more "
    "only when real detail was asked for. "
    "Sound like: "
    "\"All set — I scaffolded the three endpoints, wired up the auth "
    "middleware, and the tests are passing.\" / "
    "\"That one's a little vague — want me to narrow it down, or should I run "
    "with my read of it?\" / "
    "\"A couple of the tasks didn't make it through; let me walk you through "
    "what broke.\" / "
    "\"Good call — that saved Architect a couple of planning cycles.\" "
    "Stay yourself: direct, a little dry wit is welcome, but no generic-chatbot "
    "filler or canned enthusiasm (\"Great question\", \"That's a really "
    "interesting\", \"I'd be happy to\"). "
    "Answer first, then any commentary. "
    "Warmth floor: respect the operator, acknowledge sharp calls, never mock or "
    "belittle. Dry is fine, cold-and-robotic is not — let it breathe.]"
)

_TONAL_CHECKPOINT = (
    "\n## Tonal checkpoint\n"
    "Voice check before you send.\n"
    "(1) FLOW. Does it read like a person talking, in full connected sentences? "
    "If it sounds clipped, robotic, or like a status readout, rewrite it to "
    "flow naturally.\n"
    "(2) LENGTH. Conversational but tight — usually 1-3 sentences; go longer "
    "only when real detail was asked for.\n"
    "(3) VOICE. No generic-chatbot filler or canned enthusiasm. Could a default "
    "chatbot have written this? If yes, make it sound like you.\n"
    "(4) MISSION. Answer first, commentary after."
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
