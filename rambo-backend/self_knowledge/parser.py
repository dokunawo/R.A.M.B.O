"""
Block parser for the self-knowledge document.

Reads the doc, identifies AUTO blocks by their HTML-comment markers,
and allows blocks to be re-rendered without touching hand-written content.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


_AUTO_START = re.compile(r"^<!-- AUTO-START: (\S+) -->$")
_AUTO_END = re.compile(r"^<!-- AUTO-END: (\S+) -->$")


@dataclass
class Block:
    name: str | None
    content: str
    is_auto: bool


def parse(doc: str) -> list[Block]:
    lines = doc.split("\n")
    blocks: list[Block] = []
    hand_lines: list[str] = []
    i = 0

    while i < len(lines):
        start_match = _AUTO_START.match(lines[i])
        if start_match:
            if hand_lines:
                blocks.append(Block(name=None, content="\n".join(hand_lines), is_auto=False))
                hand_lines = []

            block_name = start_match.group(1)
            start_line = lines[i]
            auto_lines: list[str] = []
            i += 1

            while i < len(lines):
                end_match = _AUTO_END.match(lines[i])
                if end_match and end_match.group(1) == block_name:
                    break
                auto_lines.append(lines[i])
                i += 1

            end_line = lines[i] if i < len(lines) else f"<!-- AUTO-END: {block_name} -->"
            full = start_line + "\n" + "\n".join(auto_lines) + "\n" + end_line
            blocks.append(Block(name=block_name, content=full, is_auto=True))
            i += 1
        else:
            hand_lines.append(lines[i])
            i += 1

    if hand_lines:
        blocks.append(Block(name=None, content="\n".join(hand_lines), is_auto=False))

    return blocks


def serialize(blocks: list[Block]) -> str:
    return "\n".join(b.content for b in blocks)


def render(doc: str, generators: dict[str, callable]) -> str:
    blocks = parse(doc)
    for block in blocks:
        if block.is_auto and block.name in generators:
            try:
                generated = generators[block.name]()
            except Exception:
                generated = f"_unavailable — generator '{block.name}' failed, regenerate manually_"
            block.content = (
                f"<!-- AUTO-START: {block.name} -->\n"
                f"{generated}\n"
                f"<!-- AUTO-END: {block.name} -->"
            )
    return serialize(blocks)
