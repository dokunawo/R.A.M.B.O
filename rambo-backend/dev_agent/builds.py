"""Standalone app builds — RAMBO builds a NEW project into `<repo>/builds/<slug>/`.

Unlike the self-edit dev lane (worktree → review → merge), a build is fresh,
isolated code that isn't part of RAMBO, so there's no merge gate. The operator
sees it in the UI and opens it on the desktop.

Also holds the container↔host path helpers (the container writes to /repo/builds,
but the operator's desktop sees a Windows path) used by the /desktop/open bridge.
"""
from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path, PureWindowsPath

from dev_agent import git_workspace as gw
from dev_agent.coding_agent import CodingAgent

logger = logging.getLogger(__name__)

import os

_RUN_TIMEOUT = 30          # seconds to run a built app before killing it
_TEST_TIMEOUT = 180        # seconds for a build's test run
_MAX_OUT = 8_000           # chars of captured output returned to the UI

# Where builds land (container path). Default: <repo>/builds. The container sets
# RAMBO_BUILDS_DIR=/repo/builds; on the host it resolves to the real repo's builds/.
def builds_dir() -> Path:
    env = os.environ.get("RAMBO_BUILDS_DIR")
    return Path(env) if env else gw.resolve_repo_root() / "builds"


# The repo root as the OPERATOR's Windows sees it (the container sees /repo).
def host_repo_root() -> str:
    return os.environ.get("RAMBO_HOST_REPO_ROOT", r"C:\Users\dokun\PycharmProjects\R.A.M.B.O")


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return slug or "build"


# ── build naming (short, human folder names) ────────────────────────────────
def _heuristic_name(goal: str) -> str:
    """Best-effort short name when no LLM is available. Strips the imperative
    'build me a …' lead and trailing filler, keeps the core noun phrase."""
    g = (goal or "").strip()
    g = re.sub(r"^(please\s+)?(build|make|create|write|generate|code|develop|design)\s+"
               r"(me\s+)?(a|an|the|some)?\s*", "", g, flags=re.I)
    g = re.sub(r"^(small|simple|basic|quick|little|cool|new)\s+", "", g, flags=re.I)
    g = re.split(r"\b(from scratch|and place|and put|in this director|into the|that |which |so that|for me)\b",
                 g, flags=re.I)[0]
    g = re.sub(r"\b(app|application|program|tool|script|project)\b\s*$", "", g.strip(), flags=re.I)
    g = re.sub(r"\s+", " ", g).strip(" .,-")
    return " ".join(g.split()[:4]).title() or "Build"


async def _llm_name(llm, goal: str) -> str:
    try:
        import model_config
        from usage_capture import record_usage
        resp = await llm.messages.create(
            model=model_config.fast_model(), max_tokens=20,
            messages=[{"role": "user", "content": (
                "Give a SHORT project name (1-3 words, Title Case, no punctuation, no "
                "generic words like 'app'/'project'/'tool') for this build request. "
                "Examples: 'build me a calculator app' -> Calculator; "
                "'build a snake game simulator' -> Snake Game. "
                "Reply with ONLY the name.\n\nRequest: " + (goal or ""))}],
        )
        try:
            await record_usage(model_config.fast_model(), resp.usage, source="build_name")
        except Exception:
            pass
        txt = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        txt = re.sub(r"[^A-Za-z0-9 ]", "", txt).strip()
        return " ".join(txt.split()[:3]).title()
    except Exception:
        return ""


async def summarize_build_name(llm, goal: str) -> str:
    """A short, human folder name for a build request ('Calculator', 'Snake Game').
    LLM-summarized with a heuristic fallback."""
    name = (await _llm_name(llm, goal)) if llm else ""
    return name or _heuristic_name(goal)


# ── delete a build (folder + dock record) ───────────────────────────────────
_REPO = None  # set at startup by main.py so the delete skill can reach the dock DB


def set_repo(repo) -> None:
    global _REPO
    _REPO = repo


def _on_rm_error(func, path, exc):
    """rmtree onerror: clear read-only (Windows .git objects) and retry once."""
    import stat
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


async def delete_build(slug: str) -> dict:
    """Remove a build: delete its folder under builds/<slug>/ AND its dock record.
    Path-guarded so it can never escape the builds root."""
    import shutil
    root = builds_dir().resolve()
    p = (root / slug).resolve()
    removed_dir = False
    if (p == root or root in p.parents) and p.is_dir():
        shutil.rmtree(p, onerror=_on_rm_error)
        removed_dir = True
    if _REPO is not None:
        try:
            await _REPO.delete(slug)
        except Exception:
            logger.exception("builds_repo.delete failed for %s", slug)
    return {"slug": slug, "deleted": True, "removed_dir": removed_dir}


async def delete_build_by_name(query: str) -> dict:
    """Find the build whose slug/name best matches the spoken `query` and delete it.
    Returns an error (with the current build list) when nothing matches."""
    if _REPO is None:
        return {"error": "the builds system isn't available right now"}
    q = re.sub(r"[^a-z0-9 ]", " ", (query or "").lower())
    q = re.sub(r"\b(delete|remove|get|rid|of|the|my|that|this|a|an|build|builds|app|"
               r"project|folder|please)\b", " ", q)
    q = re.sub(r"\s+", " ", q).strip()
    builds = await _REPO.list_all()
    if not builds:
        return {"error": "there are no builds to delete"}

    def score(b: dict) -> int:
        hay = (b["slug"].replace("-", " ") + " " + (b.get("name") or "")).lower()
        return sum(1 for w in q.split() if w and w in hay)

    best = max(builds, key=score)
    if not q or score(best) == 0:
        return {"error": f"no build matches \"{query}\"",
                "builds": [b["slug"] for b in builds]}
    res = await delete_build(best["slug"])
    res["name"] = best.get("name") or best["slug"]
    return res


def to_host_path(container_path: str | Path) -> str:
    """Translate a path under the repo into the Windows path the operator sees.

    Anything not under the repo root is returned unchanged (best effort)."""
    p = Path(container_path).resolve()
    root = gw.resolve_repo_root()
    try:
        rel = p.relative_to(root)
    except ValueError:
        return str(container_path)
    return str(PureWindowsPath(host_repo_root()) / PureWindowsPath(*rel.parts))


def is_safe_host_path(host_path: str) -> bool:
    """True only if host_path is inside the operator's repo root — so the
    desktop-open bridge can never be asked to open arbitrary locations."""
    try:
        root = PureWindowsPath(host_repo_root())
        target = PureWindowsPath(host_path)
        return target == root or root in target.parents
    except Exception:
        return False


async def build_app(*, llm, repo, slug: str, name: str, goal: str,
                    personality_text: str = "", on_event=None) -> dict:
    """Build a standalone project into builds/<slug>/. Returns a result dict."""
    on_event = on_event or (lambda *a, **k: None)
    build_dir = builds_dir() / slug
    # Rough ETA so the UI can show a countdown + progress bar. Heuristic only —
    # the bar snaps to 100% on the real completion event, not when this elapses.
    eta_s = max(30, min(180, 25 + len(goal) // 6))
    try:
        on_event(stage="workspace", msg=f"Creating builds/{slug}", eta_s=eta_s)
        build_dir.mkdir(parents=True, exist_ok=True)

        on_event(stage="coding", msg="Building the project")
        agent = CodingAgent(
            llm, build_dir, personality_text=personality_text,
            on_event=lambda **k: on_event(stage="tool", **k),
            test_cwd="",  # run tests from the build root, not rambo-backend
        )
        summary = await agent.run(
            f"Build a new standalone project in this directory: {goal}\n"
            "Create all needed files DIRECTLY in the current working directory. "
            "Do NOT create a wrapper subfolder for the project (no nested "
            "'builds/', project-name, or 'src/'-only folder that just holds "
            "everything) — the entry point (e.g. main.py) must be at the top "
            "level. Include a brief README and, where it makes sense, a test."
        )

        files = sorted(agent.touched)
        if not files:  # fallback: list whatever source landed on disk (ignore git/cache)
            files = sorted(
                str(f.relative_to(build_dir)) for f in build_dir.rglob("*")
                if f.is_file() and ".git" not in f.parts and ".pytest_cache" not in f.parts
            )[:200]

        # No source files means the build genuinely failed (the agent errored or
        # wrote nothing). Mark it FAILED instead of READY so the UI doesn't show a
        # runnable card that has nothing to run ("no runnable .py entry point").
        if not files:
            msg = ("the build produced no files — the coding agent didn't write "
                   "anything (likely an API/agent error). Try rebuilding.")
            await repo.set_error(slug, msg)
            on_event(stage="error", msg=msg)
            return {"slug": slug, "error": msg}

        # Give the finished project its own git repo + an initial commit, so the
        # build is version-controlled the moment it's created. This is a nested
        # repo inside builds/<slug>/ (the outer RAMBO repo gitignores builds/).
        on_event(stage="commit", msg="Committing the build")
        await _git_init_commit(build_dir, f"Initial build by RAMBO: {name}")

        rel_path = str(build_dir.relative_to(gw.resolve_repo_root())) \
            if _under_repo(build_dir) else str(build_dir)
        host_path = to_host_path(build_dir)
        await repo.set_ready(slug, rel_path=rel_path, host_path=host_path,
                             files=files, summary=summary[:400])
        on_event(stage="ready", msg="Build ready", host_path=host_path)
        return {"slug": slug, "host_path": host_path, "files": files, "summary": summary}
    except Exception as e:  # noqa: BLE001
        logger.exception("build_app failed for %s", slug)
        try:
            await repo.set_error(slug, str(e))
        except Exception:
            pass
        return {"slug": slug, "error": str(e)}


def _under_repo(p: Path) -> bool:
    try:
        p.resolve().relative_to(gw.resolve_repo_root())
        return True
    except ValueError:
        return False


def _safe_build_dir(slug: str) -> Path | None:
    """Resolve builds/<slug>, refusing anything that escapes the builds root."""
    root = builds_dir().resolve()
    p = (root / slug).resolve()
    if p != root and root not in p.parents:
        return None
    return p if p.is_dir() else None


async def _run_in_build(slug: str, cmd: list[str], timeout: int) -> dict:
    bd = _safe_build_dir(slug)
    if bd is None:
        return {"error": "build not found"}
    return await _run_in_dir(bd, cmd, timeout)


async def _run_in_dir(cwd: Path, cmd: list[str], timeout: int) -> dict:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return {"ok": False, "timed_out": True,
                    "output": f"(stopped after {timeout}s — still running)"}
    except FileNotFoundError:
        return {"error": f"command not found: {cmd[0]}"}
    text = out.decode("utf-8", errors="replace")
    return {"ok": proc.returncode == 0, "returncode": proc.returncode,
            "output": text[-_MAX_OUT:]}


async def run_tests(slug: str) -> dict:
    """Run pytest in a built project's folder."""
    return await _run_in_build(slug, ["python", "-m", "pytest", "-q"], _TEST_TIMEOUT)


_ENTRY_NAMES = ("main.py", "app.py", "__main__.py", "run.py")


def _entry_point(build_dir: Path) -> Path | None:
    """Find a runnable entry point. Searches the build root first, then any
    subfolder (the agent sometimes nests the project one level deep), preferring
    well-known entry names and shallower paths. Returns an absolute path."""
    # Top-level well-known names win.
    for name in _ENTRY_NAMES:
        if (build_dir / name).exists():
            return build_dir / name
    # Recurse: rank by (depth, preference, name) so a nested main.py beats a
    # random top-level helper, and shallow beats deep.
    candidates = []
    for p in build_dir.rglob("*.py"):
        if p.name.startswith("test_") or not p.is_file():
            continue
        depth = len(p.relative_to(build_dir).parts)
        pref = _ENTRY_NAMES.index(p.name) if p.name in _ENTRY_NAMES else len(_ENTRY_NAMES)
        candidates.append((pref, depth, str(p), p))
    candidates.sort(key=lambda c: (c[0], c[1], c[2]))
    return candidates[0][3] if candidates else None


async def run_app(slug: str) -> dict:
    """Run a built project's entry point (best-guess .py) and capture its output."""
    bd = _safe_build_dir(slug)
    if bd is None:
        return {"error": "build not found"}
    entry = _entry_point(bd)
    if not entry:
        return {"error": "no runnable .py entry point found"}
    # Run from the entry point's own folder so nested projects resolve their
    # imports/relative paths correctly.
    rel_entry = entry.relative_to(bd)
    res = await _run_in_dir(entry.parent, ["python", entry.name], _RUN_TIMEOUT)
    res["entry"] = str(rel_entry)
    return res


async def _git_init_commit(build_dir: Path, message: str) -> None:
    """git init + add + initial commit inside the build dir (best-effort)."""
    try:
        rc, _ = await gw._git(build_dir, "init")
        if rc != 0:
            return
        await gw._git(build_dir, "add", "-A")
        await gw._git(build_dir, *gw._IDENT, "commit", "--no-verify", "-m", message)
    except Exception:  # noqa: BLE001
        logger.exception("git init/commit failed for %s", build_dir)
