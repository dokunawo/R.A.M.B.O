#!/usr/bin/env python3
"""Phase 1 harness — prove the Managed Agents loop on the real repo, in isolation.

This is a THROWAWAY harness that lives OUTSIDE the RAMBO app (it is not imported
by the backend). It exists only to de-risk the one scary assumption in
docs/PLAN_self-coding-agent.md: that RAMBO can edit a sandboxed clone of its own
repo and open a PR a human reviews — never touching the running process.

See docs/PLAN_self-coding-agent.md → Phase 1 (STOP/GO checkpoint).

────────────────────────────────────────────────────────────────────────────
Two stages, by increasing setup cost:

  Stage 1a (default)  — Prove the loop + sandbox WITHOUT GitHub.
                        Creates an environment + agent + session, gives the agent
                        a trivial task in its sandbox container (write a file, read
                        it back), streams events to idle, prints the result, then
                        archives the session. No secrets required beyond the
                        Anthropic key. This alone proves: agent loop runs, sandbox
                        executes tools, events stream back.

  Stage 1b (--repo)   — Add repo mount + PR. Requires a GitHub PAT and the repo to
                        exist on GitHub. The agent clones RAMBO into the sandbox,
                        makes a trivial edit on a branch, pushes, and (with the
                        GitHub MCP server) opens a PR. THIS is the full Phase 1
                        proof. Gated behind --repo / --github-token because it needs
                        your credentials.

────────────────────────────────────────────────────────────────────────────
COST / SIDE EFFECTS — read before running live:
  - A live run BILLS (model inference inside the session) and creates PERSISTENT
    objects: an `environment` and an `agent`. Those linger on your Anthropic
    account by design — Phase 2 reuses them (don't re-create per run). The session
    is archived at the end of a run; the env + agent are not.
  - --dry-run prints the planned config and makes NO API calls. Start there.

Usage:
  python scripts/phase1_agent_harness.py --dry-run
  python scripts/phase1_agent_harness.py                 # Stage 1a live

  # Stage 1b — prefer GITHUB_TOKEN env var (keeps the PAT out of shell history):
  #   PowerShell:  $env:GITHUB_TOKEN = "github_pat_xxx"
  #   bash:        export GITHUB_TOKEN=github_pat_xxx
  python scripts/phase1_agent_harness.py --repo https://github.com/<owner>/<repo>
  # (--github-token github_pat_xxx still works as a fallback if you must)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────
MODEL = "claude-opus-4-8"  # verified working 2026-06-24
AGENT_NAME = "RAMBO Phase 1 Harness Agent"
ENV_NAME = "rambo-phase1-sandbox"
AGENT_MD = Path(__file__).resolve().parent.parent / "rambo-backend" / "AGENT.md"
DOTENV = Path(__file__).resolve().parent.parent / "rambo-backend" / ".env"

STAGE_1A_TASK = (
    "Write a file at /workspace/hello_rambo.txt containing the single line "
    "'RAMBO sandbox online.', then read it back and report its contents. "
    "Keep it to those two steps."
)
STAGE_1B_TASK = (
    "On a new branch named 'rambo/phase1-proof', append a line "
    "'<!-- RAMBO Phase 1 proof -->' to the end of README.md, commit it, push the "
    "branch, and open a pull request titled 'RAMBO Phase 1 proof' against the "
    "default branch. Report the PR URL. Make no other changes."
)


def load_key() -> str:
    """Read ANTHROPIC_API_KEY from the environment, falling back to rambo-backend/.env."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    if DOTENV.exists():
        for raw in DOTENV.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.partition("=")[2].strip().strip('"').strip("'")
    sys.exit("ANTHROPIC_API_KEY not found in env or rambo-backend/.env")


def agent_system_prompt() -> str:
    """RAMBO's own voice (AGENT.md) so the harness agent talks like RAMBO."""
    base = AGENT_MD.read_text(encoding="utf-8") if AGENT_MD.exists() else ""
    rails = (
        "\n\n## Operating rails (Phase 1 harness)\n"
        "You are running in an isolated sandbox container against a CLONE of the "
        "RAMBO repository. You never touch the running RAMBO process. All changes "
        "go on a branch and land as a pull request a human reviews and merges. "
        "Do exactly what the task asks — no extra changes, no cleanup, no refactors."
    )
    return base + rails


def planned_config(stage_1b: bool, repo: str | None) -> dict:
    cfg = {
        "model": MODEL,
        "environment": {"name": ENV_NAME, "config": {"type": "cloud", "networking": {"type": "unrestricted"}}},
        "agent": {"name": AGENT_NAME, "tools": [{"type": "agent_toolset_20260401"}]},
        "task": STAGE_1B_TASK if stage_1b else STAGE_1A_TASK,
    }
    if stage_1b:
        cfg["agent"]["mcp_servers"] = [{"type": "url", "name": "github", "url": "https://api.githubcopilot.com/mcp/"}]
        cfg["agent"]["tools"].append({"type": "mcp_toolset", "mcp_server_name": "github"})
        cfg["repo"] = repo
    return cfg


def run_live(stage_1b: bool, repo: str | None, github_token: str | None) -> None:
    import anthropic  # imported here so --dry-run needs no SDK

    client = anthropic.Anthropic(api_key=load_key())

    print(f"[1/4] Creating environment '{ENV_NAME}' …")
    env = client.beta.environments.create(
        name=ENV_NAME,
        config={"type": "cloud", "networking": {"type": "unrestricted"}},
    )
    print(f"      env id: {env.id}")

    print(f"[2/4] Creating agent '{AGENT_NAME}' …")
    agent_kwargs = {
        "name": AGENT_NAME,
        "model": MODEL,
        "system": agent_system_prompt(),
        "tools": [{"type": "agent_toolset_20260401"}],
    }
    if stage_1b:
        agent_kwargs["mcp_servers"] = [
            {"type": "url", "name": "github", "url": "https://api.githubcopilot.com/mcp/"}
        ]
        agent_kwargs["tools"].append({"type": "mcp_toolset", "mcp_server_name": "github"})
    agent = client.beta.agents.create(**agent_kwargs)
    print(f"      agent id: {agent.id}  (PERSISTENT — reused in Phase 2, not auto-deleted)")

    print("[3/4] Starting session …")
    session_kwargs = {"agent": agent.id, "environment_id": env.id, "title": "RAMBO Phase 1 proof"}
    if stage_1b:
        if not (repo and github_token):
            sys.exit("Stage 1b requires --repo and --github-token")
        session_kwargs["resources"] = [
            {"type": "github_repository", "url": repo, "authorization_token": github_token}
        ]
        # NOTE: opening a PR also needs a vault credential for the GitHub MCP server.
        # See docs/PLAN_self-coding-agent.md and the managed-agents tools/vaults docs.
    session = client.beta.sessions.create(**session_kwargs)
    print(f"      session id: {session.id}")
    print(f"      watch live: https://platform.claude.com/workspaces/default/sessions/{session.id}")

    task = STAGE_1B_TASK if stage_1b else STAGE_1A_TASK
    print(f"[4/4] Streaming. Task: {task}\n" + "─" * 70)

    # Stream-first, then send (see managed-agents client patterns).
    with client.beta.sessions.events.stream(session.id) as stream:
        client.beta.sessions.events.send(
            session.id,
            events=[{"type": "user.message", "content": [{"type": "text", "text": task}]}],
        )
        for event in stream:
            etype = getattr(event, "type", "?")
            if etype == "agent.message":
                for block in getattr(event, "content", []):
                    if getattr(block, "type", None) == "text":
                        print(block.text, end="", flush=True)
            elif etype in ("agent.tool_use", "agent.custom_tool_use", "agent.mcp_tool_use"):
                print(f"\n  · {etype}: {getattr(event, 'name', '')}", flush=True)
            elif etype == "session.status_idle":
                sr = getattr(event, "stop_reason", None)
                if getattr(sr, "type", None) == "requires_action":
                    continue
                break
            elif etype == "session.status_terminated":
                break

    print("\n" + "─" * 70 + "\nDone. Archiving session (env + agent persist).")
    # Poll briefly before archive (post-idle status-write race).
    for _ in range(10):
        s = client.beta.sessions.retrieve(session.id)
        if s.status != "running":
            break
        time.sleep(0.2)
    try:
        client.beta.sessions.archive(session.id)
    except Exception as e:  # noqa: BLE001
        print(f"  (archive skipped: {e})")
    print(f"\nKeep these for Phase 2:  AGENT_ID={agent.id}  ENV_ID={env.id}")


def main() -> None:
    ap = argparse.ArgumentParser(description="RAMBO Phase 1 Managed Agents harness")
    ap.add_argument("--dry-run", action="store_true", help="Print planned config, make no API calls")
    ap.add_argument("--repo", help="GitHub repo URL → enables Stage 1b (repo mount + PR)")
    ap.add_argument("--github-token", help="GitHub PAT for repo clone/push (Stage 1b)")
    args = ap.parse_args()

    stage_1b = bool(args.repo)
    # Prefer the env var so the PAT stays out of shell history; --github-token is a fallback.
    github_token = os.environ.get("GITHUB_TOKEN") or args.github_token
    cfg = planned_config(stage_1b, args.repo)

    print(f"=== RAMBO Phase 1 Harness — Stage {'1b (repo + PR)' if stage_1b else '1a (sandbox only)'} ===")
    if args.dry_run:
        print("DRY RUN — no API calls. Planned config:\n")
        print(json.dumps(cfg, indent=2))
        print("\nRemove --dry-run to execute live (BILLS + creates persistent env/agent).")
        return
    if stage_1b and not github_token:
        sys.exit("Stage 1b needs a token: set GITHUB_TOKEN env var (preferred) or pass --github-token.")
    run_live(stage_1b, args.repo, github_token)


if __name__ == "__main__":
    main()
