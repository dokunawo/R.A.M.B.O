"""CodingAgent — a worktree-confined tool-use loop for self-code changes.

Same shape as factory.config_agent.ConfigDrivenAgent (call tool → feed result →
repeat), but the file tools are hard-confined to a single worktree path: the
agent physically cannot read or write outside the isolated branch checkout. Its
system prompt is RAMBO's AGENT.md voice plus a self-modification contract.

The agent does NOT commit, diff, or merge — that's git_workspace's job, driven
by the orchestrator after the loop finishes.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
from pathlib import Path
from typing import Any

import model_config

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 16
_MAX_FILE_CHARS = 20_000
_TEST_TIMEOUT = 180          # seconds; a runaway test must not hang the loop
_MAX_TEST_OUTPUT = 8_000     # chars of pytest output fed back to the model

# How the dev lane runs tests. The agent can only invoke THIS command (pytest) on
# a worktree path — not arbitrary shell. Overridable for other project layouts.
#   RAMBO_TEST_CMD  default "python -m pytest -q"
#   RAMBO_TEST_CWD  default "rambo-backend" (relative to the worktree root; this
#                   repo's tests run from there so imports resolve)
_DEFAULT_TEST_CMD = "python -m pytest -q"
_DEFAULT_TEST_CWD = "rambo-backend"

_CONTRACT = """

## Self-modification contract (non-negotiable)
You are editing an isolated git worktree on a throwaway branch — a CLONE of the
codebase, never the running process and never `main`. Your file tools cannot
reach outside this worktree.
- Make ONLY the change the task asks for. No drive-by refactors, no cleanup, no
  reformatting unrelated code, no new abstractions.
- Touch ONLY the file(s) the task names. If it says create one file, create
  exactly that one file. Do NOT create, copy, duplicate, or regenerate any other
  file — especially not documentation, self-description, or context files you
  happened to read. Reading a file is not a reason to write one.
- Read before you write. Match the surrounding code's style.
- When done, stop and briefly state what you changed and why. Do not claim to
  have run, merged, or deployed anything — a human reviews your diff and merges.
"""


def _confine(worktree: Path, path: str) -> Path:
    """Resolve `path` against the worktree and refuse anything that escapes it."""
    root = worktree.resolve()
    candidate = (root / path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"path escapes the worktree: {path}")
    return candidate


def _tool_defs() -> list[dict]:
    return [
        {
            "name": "read_file",
            "description": "Read a file in the worktree (up to 20,000 chars).",
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Path relative to the worktree root"}},
                "required": ["path"],
            },
        },
        {
            "name": "list_files",
            "description": "List tracked-style files in the worktree, optionally matching a glob.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "Subdirectory, default '.'"},
                    "pattern": {"type": "string", "description": "Glob pattern, default '*'"},
                },
            },
        },
        {
            "name": "write_file",
            "description": "Create or overwrite a file in the worktree with the given content.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
        {
            "name": "edit_file",
            "description": "Replace an exact string in a file with another. old_string must appear exactly once.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_string": {"type": "string"},
                    "new_string": {"type": "string"},
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
        {
            "name": "run_tests",
            "description": (
                "Run the project's tests (pytest) on a path inside the worktree and "
                "return pass/fail plus output. Use this to watch your new test FAIL "
                "before you implement, and PASS after. Pass the path to a test file or "
                "directory; keep it narrow (the specific test you wrote) so it's fast."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Test file or dir, relative to the worktree root"},
                },
                "required": ["path"],
            },
        },
    ]


class CodingAgent:
    def __init__(self, llm_client, worktree_path: Path, personality_text: str = "",
                 model: str | None = None, on_event=None, playbooks: str | None = None,
                 test_cwd: str | None = None):
        self._llm = llm_client
        self._worktree = Path(worktree_path)
        self._model = model or model_config.default_model()
        # System prompt = RAMBO's voice + the self-modification contract + the
        # engineering playbooks (Phase 4: TDD / debugging / verification).
        from dev_agent.playbooks import load_playbooks
        pb = load_playbooks() if playbooks is None else playbooks
        self._system = (personality_text or "") + _CONTRACT + pb
        self._on_event = on_event or (lambda *a, **k: None)
        self._test_cmd = shlex.split(os.environ.get("RAMBO_TEST_CMD", _DEFAULT_TEST_CMD))
        # test_cwd: where pytest runs (relative to the agent root). Standalone
        # builds pass "" to run from the build root; default falls back to env.
        self._test_cwd = test_cwd if test_cwd is not None else os.environ.get("RAMBO_TEST_CWD", _DEFAULT_TEST_CWD)
        # Exact set of worktree-relative paths the agent wrote/edited. The diff
        # shown to the operator is built from ONLY these — never `git add -A` —
        # so nothing the agent didn't touch can leak into the review.
        self.touched: set[str] = set()

    async def _run_tests(self, path: str) -> str:
        """Run pytest on a worktree-confined path. pytest only — never arbitrary
        shell — so the agent's reach is bounded. Runs in an isolated worktree, so
        it exercises the agent's draft, never the live process."""
        try:
            target = _confine(self._worktree, path)  # rejects escapes
        except ValueError as e:
            return json.dumps({"error": str(e)})
        if not target.exists():
            return json.dumps({"error": f"Path not found: {path}"})

        cwd = (self._worktree / self._test_cwd) if self._test_cwd else self._worktree
        if not cwd.is_dir():
            cwd = self._worktree
        try:
            rel = target.relative_to(cwd.resolve())
        except ValueError:
            rel = target  # target outside cwd → pass absolute
        try:
            proc = await asyncio.create_subprocess_exec(
                *self._test_cmd, str(rel),
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                out, _ = await asyncio.wait_for(proc.communicate(), timeout=_TEST_TIMEOUT)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                return json.dumps({"error": f"tests timed out after {_TEST_TIMEOUT}s",
                                   "passed": False})
        except FileNotFoundError:
            return json.dumps({"error": f"test runner not found: {self._test_cmd[0]}"})

        text = out.decode("utf-8", errors="replace")
        return json.dumps({
            "passed": proc.returncode == 0,
            "returncode": proc.returncode,
            "output": text[-_MAX_TEST_OUTPUT:],
        })

    async def _exec_tool(self, name: str, inp: dict) -> str:
        try:
            if name == "read_file":
                p = _confine(self._worktree, inp["path"])
                if not p.exists():
                    return json.dumps({"error": f"File not found: {inp['path']}"})
                return p.read_text(encoding="utf-8", errors="replace")[:_MAX_FILE_CHARS]
            if name == "list_files":
                base = _confine(self._worktree, inp.get("directory", "."))
                if not base.is_dir():
                    return json.dumps({"error": f"Not a directory: {inp.get('directory', '.')}"})
                pattern = inp.get("pattern", "*")
                files = sorted(
                    str(f.relative_to(self._worktree))
                    for f in base.rglob(pattern)
                    if f.is_file() and ".git" not in f.parts
                )[:200]
                return json.dumps(files)
            if name == "write_file":
                p = _confine(self._worktree, inp["path"])
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(inp["content"], encoding="utf-8")
                self.touched.add(p.relative_to(self._worktree.resolve()).as_posix())
                return json.dumps({"written": inp["path"], "bytes": len(inp["content"])})
            if name == "edit_file":
                p = _confine(self._worktree, inp["path"])
                if not p.exists():
                    return json.dumps({"error": f"File not found: {inp['path']}"})
                text = p.read_text(encoding="utf-8")
                old = inp["old_string"]
                count = text.count(old)
                if count == 0:
                    return json.dumps({"error": "old_string not found"})
                if count > 1:
                    return json.dumps({"error": f"old_string matches {count} places; make it unique"})
                p.write_text(text.replace(old, inp["new_string"], 1), encoding="utf-8")
                self.touched.add(p.relative_to(self._worktree.resolve()).as_posix())
                return json.dumps({"edited": inp["path"]})
            if name == "run_tests":
                return await self._run_tests(inp["path"])
            return json.dumps({"error": f"Unknown tool: {name}"})
        except ValueError as e:  # confinement violation
            return json.dumps({"error": str(e)})
        except Exception as e:  # noqa: BLE001
            return json.dumps({"error": str(e)})

    async def run(self, task: str) -> str:
        tools = _tool_defs()
        messages: list[dict[str, Any]] = [{"role": "user", "content": task}]

        for _ in range(MAX_ITERATIONS):
            response = await self._llm.messages.create(
                model=self._model,
                max_tokens=4096,
                system=self._system,
                messages=messages,
                tools=tools,
            )
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                return _extract_text(response.content)

            tool_results = []
            for block in response.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                self._on_event(tool=block.name, input=dict(block.input))
                result = await self._exec_tool(block.name, dict(block.input))
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })
            messages.append({"role": "user", "content": tool_results})

        return _extract_text(messages[-1].get("content", []))


def _extract_text(content) -> str:
    if isinstance(content, str):
        return content
    parts = [b.text for b in content if getattr(b, "type", None) == "text"]
    return "\n".join(parts) if parts else "(no text response)"
