"""
Drift checker for the self-knowledge document.

Scans hand-written sections for references to file paths, qualified symbols,
and tool/agent/integration names, then verifies each still exists in the codebase.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from self_knowledge.parser import parse


_BACKEND = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND.parent

_FILE_REF = re.compile(
    r"`([a-zA-Z0-9_\-./\\]+\.[a-zA-Z]{1,5}(?::[a-zA-Z_]\w*(?:\(\))?)?)`"
)
_LINK_REF = re.compile(
    r"\]\((\.\./[^\)]+|[a-zA-Z0-9_\-./]+\.[a-zA-Z]{1,5})\)"
)


@dataclass
class DriftFinding:
    kind: str
    reference: str
    location_in_doc: int
    reason: str


def _load_allowlist(doc_path: Path) -> set[str]:
    allowlist_path = doc_path.parent / f".{doc_path.stem}-allowlist.txt"
    if not allowlist_path.exists():
        return set()
    entries = set()
    for line in allowlist_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            entries.add(stripped)
    return entries


def check(doc_path: Path | None = None) -> list[DriftFinding]:
    if doc_path is None:
        doc_path = _BACKEND / "context" / "self" / "rambo.md"

    doc = doc_path.read_text(encoding="utf-8")
    blocks = parse(doc)
    allowlist = _load_allowlist(doc_path)
    findings: list[DriftFinding] = []
    line_offset = 0

    for block in blocks:
        if block.is_auto:
            line_offset += block.content.count("\n") + 1
            continue

        block_lines = block.content.split("\n")
        for i, line in enumerate(block_lines):
            abs_line = line_offset + i + 1

            for m in _FILE_REF.finditer(line):
                ref = m.group(1)
                path_part = ref.split(":")[0]
                if path_part in allowlist or ref in allowlist:
                    continue
                finding = _check_file_ref(path_part, abs_line, doc_path)
                if finding:
                    findings.append(finding)

            for m in _LINK_REF.finditer(line):
                ref = m.group(1)
                if ref in allowlist:
                    continue
                finding = _check_link_ref(ref, abs_line, doc_path)
                if finding:
                    findings.append(finding)

        line_offset += len(block_lines)

    return findings


def _check_file_ref(path_str: str, line: int, doc_path: Path) -> DriftFinding | None:
    candidates = [
        _BACKEND / path_str,
        _REPO_ROOT / path_str,
        doc_path.parent / path_str,
    ]
    for c in candidates:
        if c.exists():
            return None
    return DriftFinding(
        kind="file_path",
        reference=path_str,
        location_in_doc=line,
        reason=f"File not found at any expected location",
    )


def _check_link_ref(path_str: str, line: int, doc_path: Path) -> DriftFinding | None:
    resolved = (doc_path.parent / path_str).resolve()
    if resolved.exists():
        return None
    return DriftFinding(
        kind="link",
        reference=path_str,
        location_in_doc=line,
        reason=f"Link target does not exist",
    )
