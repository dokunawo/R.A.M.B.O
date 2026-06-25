"""dev_agent — RAMBO's git-isolated self-coding lane.

The high-risk capability (RAMBO editing its own source) lives here, kept apart
from the factory (which spawns helper agents). Every self-change happens on a
throwaway git branch inside an isolated worktree — never the live working tree,
never `main` — and only reaches `main` when the operator merges it.
"""
