"""How R.A.M.B.O addresses the operator.

Default: "sir" — RAMBO always addresses the operator as sir. A future "Ultron
mode" (RAMBO_MODE=ultron) flips to the operator's real name for a more aggressive
persona; until then, sir it is.

Env:
  RAMBO_OPERATOR_NAME  honorific/name RAMBO uses (default "sir")
  RAMBO_REAL_NAME      the operator's real name, used only in Ultron mode
  RAMBO_MODE           "standard" (default) or "ultron"
"""
import os


def is_ultron() -> bool:
    return os.environ.get("RAMBO_MODE", "standard").strip().lower() == "ultron"


def address() -> str:
    """What RAMBO calls the operator right now."""
    if is_ultron():
        return os.environ.get("RAMBO_REAL_NAME", "").strip() or os.environ.get("RAMBO_OPERATOR_NAME", "sir")
    return os.environ.get("RAMBO_OPERATOR_NAME", "sir")
