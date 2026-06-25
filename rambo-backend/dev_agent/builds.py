"""Standalone app builds — RAMBO builds a NEW project into `<repo>/builds/<slug>/`.

Unlike the self-edit dev lane (worktree → review → merge), a build is fresh,
isolated code that isn't part of RAMBO, so there's no merge gate. The operator
sees it in the UI and opens it on the desktop.

Also holds the container↔host path helpers (the container writes to /repo/builds,
but the operator's desktop sees a Windows path) used by the /desktop/open bridge.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path, PureWindowsPath

from dev_agent import git_workspace as gw
from dev_agent.coding_agent import CodingAgent

logger = logging.getLogger(__name__)

import os

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
            "Create all needed files here. Include a brief README and, where it "
            "makes sense, a test."
        )

        files = sorted(agent.touched)
        if not files:  # fallback: list whatever landed on disk
            files = sorted(
                str(f.relative_to(build_dir)) for f in build_dir.rglob("*") if f.is_file()
            )[:200]

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
