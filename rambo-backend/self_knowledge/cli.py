"""
CLI entry point for self-knowledge management.

Usage:
    python -m self_knowledge --render    Show what would be written
    python -m self_knowledge --refresh   Write rendered doc to disk
    python -m self_knowledge --check     Soft drift check (exit 0 with warnings)
    python -m self_knowledge --check --strict  Exit non-zero on any finding
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from self_knowledge.renderer import render_doc, refresh_doc
from self_knowledge.drift import check


_DOC_PATH = Path(__file__).resolve().parent.parent / "context" / "self" / "rambo.md"


def main():
    parser = argparse.ArgumentParser(description="R.A.M.B.O self-knowledge manager")
    parser.add_argument("--render", action="store_true", help="Show rendered doc")
    parser.add_argument("--refresh", action="store_true", help="Write rendered doc to disk")
    parser.add_argument("--check", action="store_true", help="Run drift check")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on drift findings")
    args = parser.parse_args()

    if not any([args.render, args.refresh, args.check]):
        parser.print_help()
        return

    if args.render:
        print(render_doc(_DOC_PATH))

    if args.refresh:
        changed = refresh_doc(_DOC_PATH)
        if changed:
            print("self-knowledge doc refreshed.")
        else:
            print("self-knowledge doc already up to date.")

    if args.check:
        findings = check(_DOC_PATH)
        if not findings:
            print("No drift detected.")
            return

        for f in findings:
            print(f"  [{f.kind}] line {f.location_in_doc}: `{f.reference}` — {f.reason}")

        print(f"\n{len(findings)} drift finding(s).")

        if args.strict:
            sys.exit(1)


if __name__ == "__main__":
    main()
