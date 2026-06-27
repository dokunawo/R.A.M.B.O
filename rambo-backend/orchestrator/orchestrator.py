import asyncio
import json
import os
import re
import time
import uuid
from collections import deque

try:
    import anthropic
    _HAS_ANTHROPIC = bool(os.environ.get("ANTHROPIC_API_KEY"))
except ImportError:
    _HAS_ANTHROPIC = False

from models.task import Task
from router import choose_brain
from usage_capture import record_usage
from skills import match_skill
import agent_tracker

from agents.architect import Architect
from agents.engineer import Engineer
from agents.seeker import Seeker
from agents.analyst import Analyst
from agents.sentinel import Sentinel
from agents.steward import Steward
from agents.link import Link
from agents.keeper import Keeper
from agents.echo import Echo
from agents.pilot import Pilot

from websocket.manager import ConnectionManager
from conversation import ConversationManager
from personality import load_personality, build_system_prompt, append_voice_cue
from orchestrator.routing import SmartRouter
from orchestrator.roster_index import RosterIndex
import sentinel_queue
import cache_config
import model_config
from skills import SKILLS
from temporal import resolve_temporal, format_temporal_context


class Orchestrator:
    def __init__(self):
        self.keeper_repo = None   # set by main.py once the DB exists
        self.ws = ConnectionManager()
        self.conversation = ConversationManager()
        # When RAMBO asks a clarifying question, remember it so the NEXT turn's
        # answer is routed in context. Consumed once, on the following turn.
        self._pending_clarify = None
        # Clean recent turns ({role, content}) fed to the ROUTER so follow-ups and
        # affirmations ("yes", "do it") route against what was just discussed. This
        # is routing-facing memory — separate from the verbose conversation history
        # used for voicing.
        self._recent_turns = deque(maxlen=6)
        self.transcript_repo = None   # durable Q&A transcript, set by main.py
        self.personality_text = load_personality()
        self.llm = (
            anthropic.AsyncAnthropic(
                api_key=os.environ.get("ANTHROPIC_API_KEY"),
                default_headers=cache_config.beta_headers() or None,
            )
            if _HAS_ANTHROPIC else None
        )

        self.agents = {
            "architect": Architect(),
            "engineer":  Engineer(),
            "seeker":    Seeker(),
            "analyst":   Analyst(),
            "sentinel":  Sentinel(),
            "steward":   Steward(),
            "link":      Link(),
            "keeper":    Keeper(),
            "echo":      Echo(),
            "pilot":     Pilot(),
        }

        self.agent_status = {name: "idle" for name in self.agents}

        # Tier 1 — smart routing brain (fast model: routing is a quick decision).
        self.router = SmartRouter(self.llm, model=model_config.fast_model())
        # Embedding-based roster pre-filter — shortlists the roster before routing
        # (no-op when VOYAGE_API_KEY is unset). See orchestrator/roster_index.py.
        self.roster_index = RosterIndex()

        # Factory wiring — set later by main.py once the DB + registry exist.
        self.factory_repo = None
        self.tool_registry = None

        # Self-coding (dev) lane — set later by main.py via set_dev_agent.
        self.dev_repo = None

        # Standalone builds — set later by main.py via set_builds.
        self.builds_repo = None

        # Dispatch log — set later via set_dispatch_repo (best-effort, may be None).
        self.dispatch_repo = None

        # TTS client — set later via set_tts (best-effort, may be None).
        self.tts = None
        self.tts_usage_repo = None

        # Spotify — set later via set_spotify (best-effort, may be None). The
        # playback device lives in the browser; its id is registered at runtime.
        self.spotify = None
        self._spotify_device = None

    # One-line ownership for each routable mode. Drives the routing roster and
    # keeps dispatch knowledge centralized in the conductor (not in agents).
    # The 7 former LLM-shell agents collapse into 3 modes; only their distinct
    # services (keeper memory, sentinel gate, pilot queue) keep separate identity.
    CORE_OWNERSHIP = {
        "planner":    "planning, decomposition, specs, and summarizing results",
        "executor":   "building/implementing code, integrations, budgeting & resource actions",
        "researcher": "searching, finding, looking things up, and analyzing/evaluating data",
        "keeper":     "storing, recalling, and managing files/memory",
    }

    # Router-facing mode → underlying shell agent. The shells still live in
    # self.agents so the orchestrate pipeline (choose_brain) keeps working; only
    # the routing surface is collapsed. _speak() handles summary voicing, so the
    # "planner" mode covers both architect (plan) and echo (summarize).
    _MODE_AGENTS = {
        "planner":    "architect",
        "executor":   "engineer",   # absorbs steward + link
        "researcher": "seeker",     # absorbs analyst
    }
    # keeper is routable but runs via _run_keeper, not a mode shell.
    # sentinel + pilot are internal-only (review / queue-building) and are not
    # offered as routable targets.

    # The lineup the dashboard shows: consolidated modes + the distinct services,
    # NOT the 10 internal shells. Each entry aggregates the live status of its
    # underlying shell agents. (display_key, display_name, [shell members])
    DISPLAY_GROUPS = [
        ("planner",    "Planner",    ["architect", "echo"]),
        ("executor",   "Executor",   ["engineer", "steward", "link"]),
        ("researcher", "Researcher", ["seeker", "analyst"]),
        ("keeper",     "Keeper",     ["keeper"]),
        ("sentinel",   "Sentinel",   ["sentinel"]),
        ("pilot",      "Pilot",      ["pilot"]),
    ]

    def set_factory(self, factory_repo, tool_registry):
        """Give the orchestrator access to spawned agents + their tools."""
        self.factory_repo = factory_repo
        self.tool_registry = tool_registry

    def set_dev_agent(self, dev_repo):
        """Give the orchestrator access to the self-coding (dev) lane repo."""
        self.dev_repo = dev_repo

    def set_builds(self, builds_repo):
        """Give the orchestrator access to the standalone-builds repo."""
        self.builds_repo = builds_repo

    def set_dispatch_repo(self, dispatch_repo):
        """Give the orchestrator a durable dispatch log (best-effort)."""
        self.dispatch_repo = dispatch_repo
        # Wire the digester so long completed-history blocks get compressed with
        # the fast model before injection (no-op if the LLM is unavailable).
        try:
            dispatch_repo.set_digester(self._digest_dispatch_history)
        except Exception:
            pass

    async def _digest_dispatch_history(self, raw_block: str) -> str:
        """Compress a raw completed-dispatch block into a 1-2 line activity digest
        using the fast model. Best-effort — callers fall back to raw on failure."""
        if not self.llm:
            return ""
        prompt = (
            "Compress this list of recently completed tasks into ONE short line "
            "(<=25 words) capturing the gist of recent activity. No preamble.\n\n"
            f"{raw_block}"
        )
        resp = await self.llm.messages.create(
            model=model_config.fast_model(),
            max_tokens=80,
            messages=[{"role": "user", "content": prompt}],
        )
        await record_usage(model_config.fast_model(), resp.usage, source="digest")
        return "".join(
            b.text for b in resp.content if getattr(b, "type", None) == "text"
        ).strip()

    def set_tts(self, tts):
        """Give the orchestrator a best-effort TTS client (or None)."""
        self.tts = tts

    def set_tts_usage_repo(self, repo):
        """Give the orchestrator a best-effort ElevenLabs character-usage log."""
        self.tts_usage_repo = repo

    def set_spotify(self, client):
        """Give the orchestrator the Spotify client for voice control."""
        self.spotify = client

    def set_spotify_device(self, device_id: str):
        """Register the browser's Web Playback SDK device so voice commands can
        target the R.A.M.B.O player even when nothing is active yet."""
        self._spotify_device = device_id

    @staticmethod
    def _spotify_failed(res) -> bool:
        return isinstance(res, dict) and bool(res.get("error"))

    _NO_DEVICE = ("I can't reach the player — make sure a R.A.M.B.O tab is open "
                  "and Spotify is connected.")

    async def _run_spotify(self, text: str) -> str:
        """Voice/command control of Spotify: play a track, playlist, or Liked
        Songs, switch tracks, pause/resume, shuffle, or report what's playing.
        Resolves a live device first so playback actually lands somewhere."""
        client = getattr(self, "spotify", None)
        if not client:
            return "[Spotify] Music control isn't wired."
        if not await client.is_connected():
            return "Spotify isn't connected yet — hit Connect Spotify on the dashboard first."

        t = (text or "").strip()
        low = t.lower()
        # Target the currently-active R.A.M.B.O device (handles stale/duplicate ids).
        dev = await client.resolve_device(self._spotify_device)

        if re.search(r"\b(what'?s playing|what is playing|current (?:song|track)|what song|now playing)\b", low):
            np = await client.now_playing()
            item = np.get("item") if isinstance(np, dict) else None
            if not item:
                return "Nothing's playing right now."
            artists = ", ".join(a.get("name", "") for a in item.get("artists", []))
            return f"Now playing {item.get('name')} by {artists}."

        # shuffle on / off
        m = re.search(r"\bshuffle\b", low)
        if m and not re.search(r"\bplay\b", low):
            on = not re.search(r"\b(off|stop|no|disable)\b", low)
            res = await client.shuffle(on, dev)
            if self._spotify_failed(res):
                return self._NO_DEVICE
            return "Shuffle on." if on else "Shuffle off."

        if re.search(r"\b(pause|stop)\b", low):
            await client.pause(dev)
            return "Paused."
        if re.search(r"\b(next|skip)\b", low):
            await client.next(dev)
            return "Skipped ahead."
        if re.search(r"\b(previous|go back|last song|prev)\b", low):
            await client.previous(dev)
            return "Back a track."

        # play [my|the] <name> playlist  /  play playlist <name>
        m = re.search(r"play(?:\s+(?:my|the))?\s+(.+?)\s+playlist\b", low) or \
            re.search(r"play(?:\s+(?:my|the))?\s+playlist\s+(.+)", low)
        if m:
            name = t[m.start(1):m.end(1)].strip()
            data = await client.playlists()
            items = data.get("items", []) if isinstance(data, dict) else []
            match = next((p for p in items if name.lower() in (p.get("name") or "").lower()), None)
            if match:
                res = await client.play(device_id=dev, context_uri=match["uri"])
                return self._NO_DEVICE if self._spotify_failed(res) else f"Playing your {match['name']} playlist."
            return f'Couldn\'t find a playlist called "{name}".'

        # play my liked songs
        if re.search(r"\b(liked(?: songs?)?|my (?:liked|saved) (?:songs?|music|tracks?)|my songs?)\b", low) \
                and re.search(r"\b(play|put on|shuffle|start)\b", low):
            res = await client.play_liked(device_id=dev)
            if self._spotify_failed(res):
                if res.get("error") == "no_liked_songs":
                    return "Your Liked Songs list looks empty."
                return self._NO_DEVICE
            return "Playing your Liked Songs."

        # play <something>
        m = re.search(r"\b(?:play|put on|queue up)\b\s+(.+)", low)
        if m:
            q = t[m.start(1):].strip().rstrip(".")
            if not q or q in ("music", "something", "a song", "some music"):
                res = await client.play_liked(device_id=dev)
                if self._spotify_failed(res):
                    return self._NO_DEVICE if res.get("error") != "no_liked_songs" else "Your Liked Songs list looks empty."
                return "Playing your Liked Songs."
            # "song by artist" → drop the connective so search matches better.
            sq = re.sub(r"\s+by\s+", " ", q)
            res = await client.search(sq, "track")
            tracks = (res.get("tracks") or {}).get("items", []) if isinstance(res, dict) else []
            if not tracks:
                return f'Couldn\'t find "{q}" on Spotify.'
            top = tracks[0]
            # Play within the track's album context (offset to the track) so the
            # next/previous buttons have somewhere to go instead of pausing at the
            # end of a one-track queue. Fall back to the bare track if no album.
            album = (top.get("album") or {}).get("uri")
            if album:
                played = await client.play(device_id=dev, context_uri=album, offset={"uri": top["uri"]})
            else:
                played = await client.play(device_id=dev, uris=[top["uri"]])
            if self._spotify_failed(played):
                return self._NO_DEVICE
            artists = ", ".join(a.get("name", "") for a in top.get("artists", []))
            return f"Playing {top.get('name')} by {artists}."

        if re.search(r"\b(resume|unpause|play)\b", low):
            res = await client.play(device_id=dev)
            return self._NO_DEVICE if self._spotify_failed(res) else "Resuming."

        return "I can play songs or playlists, skip, pause, shuffle, or tell you what's on — just say the word."

    def set_keeper_repo(self, repo):
        """Give the Keeper agent a durable memory store."""
        self.keeper_repo = repo

    def set_transcript_repo(self, repo):
        """Durable clean Q&A transcript (best-effort), surfaced via /transcript."""
        self.transcript_repo = repo

    def _remember_turn(self, user_text: str, assistant_text: str) -> None:
        """Record a clean turn: into the router's follow-up deque AND the durable
        transcript (fire-and-forget) the operator can scroll back through + copy."""
        self._recent_turns.append({"role": "user", "content": (user_text or "")[:300]})
        self._recent_turns.append({"role": "assistant", "content": (assistant_text or "")[:300]})
        repo = getattr(self, "transcript_repo", None)
        if repo:
            try:
                asyncio.get_running_loop().create_task(repo.add(user_text, assistant_text))
            except RuntimeError:
                pass  # no running loop (e.g. unit test on the sync path) — skip

    async def set_conversation_repo(self, repo):
        """Back the in-memory conversation with a durable store and hydrate the
        recent history so context survives a restart."""
        self.conversation.set_repo(repo)
        await self.conversation.hydrate()

    async def _build_operator_context(self, goal: str) -> str:
        """Assemble the 'living memory' block injected into the system prompt each
        turn: the synthesized operator profile, recent reflection insights, and the
        memories most relevant to THIS request. Returns '' when there's nothing to
        add (or embeddings are off — recall degrades gracefully). This is what
        makes RAMBO actually USE what it has learned, every reply."""
        repo = getattr(self, "keeper_repo", None)
        if not repo:
            return ""
        sections: list[str] = []
        try:
            profile = await repo.read("operator_profile")
            if profile and profile.get("value"):
                sections.append("## What you know about the operator\n"
                                + profile["value"].strip())
        except Exception:
            pass
        try:
            relevant = await repo.recall(goal, limit=3)
            lines = [f"- {h['key']}: {h['value']}" for h in relevant
                     if h.get("key") and h.get("value")]
            if lines:
                sections.append("## Relevant memory (recalled for this request)\n"
                                + "\n".join(lines))
        except Exception:
            pass
        # Adaptive tone + how to address the operator. Always present, even with
        # no memory yet, so RAMBO matches depth to the request and addresses the
        # operator correctly ("sir" by default).
        from operator_identity import address
        sections.append(
            f"## Address & tone\nAddress the operator as \"{address()}\". "
            "Adapt depth: be terse and direct for quick or operational asks; "
            "expand and explain when they're exploring or ask why/how. Honor any "
            "communication preferences noted above.")
        return ("\n\n# Operator memory — use this to personalize your reply; do "
                "not recite it verbatim.\n" + "\n\n".join(sections))

    async def _run_keeper(self, text: str) -> str:
        """Persist or recall a memory via the Keeper store. Save intents
        ('remember X is Y') write; recall intents ('what is my X') read back."""
        repo = getattr(self, "keeper_repo", None)
        if not repo:
            return "[Keeper] No memory store is wired."
        t = (text or "").strip()
        low = t.lower()

        # Save intent.
        m = re.search(r"\b(?:remember|save|store|note|keep|memorize)\b\s*(?:that\s+)?(.+)", low)
        if m:
            body = t[m.start(1):].strip().rstrip(".")
            kv = re.match(r"(.+?)\s+(?:is|are|=|equals|:)\s+(.+)", body, re.IGNORECASE)
            if kv:
                key = re.sub(r"^(my|the|our)\s+", "", kv.group(1).strip(), flags=re.IGNORECASE)
                value = kv.group(2).strip()
            else:
                key, value = body[:48], body
            slug = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_") or "note"
            try:
                await repo.write(slug, value, tags="keeper")
            except Exception as e:
                return f"[Keeper] Couldn't store that: {e}"
            return f"[Keeper] Stored — {key}: {value}"

        # Recall intent.
        m = re.search(r"\b(?:what(?:'s| is| are)?|recall|remember|tell me|do you (?:know|have))\b\s*(?:my|the|our|about)?\s*(.+)", low)
        if m:
            term = re.sub(r"[?.!]+$", "", m.group(1)).strip()
            # Hybrid recall: blends keyword + semantic + recency + confidence, and
            # works with Voyage off. Falls back to substring/word matching only if
            # the blended pass surfaces nothing.
            hits = []
            try:
                recall = getattr(repo, "recall", None)
                if recall:
                    hits = await recall(term, limit=5)
            except Exception:
                hits = []
            if not hits:
                hits = await repo.query(term, limit=5)
            if not hits:
                # Fall back to matching individual significant words (handles
                # phrasing/plural drift, e.g. "dog's name" vs stored "dog_s_name").
                stop = {"the", "my", "our", "your", "is", "are", "was", "were",
                        "what", "whats", "name", "value", "about", "for", "of", "a", "an"}
                words = [w for w in re.findall(r"[a-z0-9]+", term.lower())
                         if len(w) > 2 and w not in stop]
                seen = {}
                for w in words:
                    forms = {w, w[:-1]} if w.endswith("s") and len(w) > 3 else {w}
                    for f in forms:
                        for h in await repo.query(f, limit=5):
                            seen[h["key"]] = h
                hits = list(seen.values())[:5]
            if hits:
                # Assert verified facts; hedge on low-confidence hints so the
                # voice layer never states an uncertain memory as established fact.
                verified = [h for h in hits if h.get("confidence", "verified") != "hint"]
                hinted = [h for h in hits if h.get("confidence", "verified") == "hint"]
                parts = []
                if verified:
                    parts.append("; ".join(f"{h['key']}: {h['value']}" for h in verified))
                if hinted:
                    parts.append("possibly " + "; ".join(
                        f"{h['key']}: {h['value']}" for h in hinted))
                return "[Keeper] " + " — ".join(parts)
            return f'[Keeper] Nothing stored about "{term}".'

        # Default: report what's stored.
        info = await repo.confirm()
        if info["count"] == 0:
            return "[Keeper] Memory is empty."
        items = ", ".join(h["key"] for h in info["recent"])
        return f"[Keeper] {info['count']} stored. Recent: {items}"

    async def _dispatch_spawned(self, goal: str):
        """If the goal names a Factory-spawned agent, run it and return a
        result dict; otherwise return None so normal routing proceeds."""
        if not self.factory_repo or not self.tool_registry or not self.llm:
            return None
        try:
            agents = await self.factory_repo.list_active_agents()
        except Exception:
            return None
        if not agents:
            return None

        g = goal.lower()
        matched = None
        for row in agents:
            slug = row["slug"].lower()
            name = row["name"].lower()
            slug_spaced = slug.replace("-", " ")
            if slug in g or slug_spaced in g or name in g:
                matched = row
                break
        if matched is None:
            return None

        result = await self._run_spawned(matched, goal)
        voiced = await self._speak(goal, [f"Agent: {matched['name']}"], [result])
        return {"response": voiced, "agent": "rambo"}

    async def _run_spawned(self, row: dict, goal: str) -> str:
        """Run a Factory-spawned ConfigDrivenAgent and return its text result."""
        from factory.config_agent import ConfigDrivenAgent

        await self.broadcast(f"[{row['name']}] Dispatched: {goal}")
        agent_tracker.record_task_start(row["slug"], goal)
        try:
            agent = ConfigDrivenAgent(
                row=row, tool_registry=self.tool_registry, llm_client=self.llm,
            )
            result = await agent.run(goal)
            agent_tracker.record_task_end(row["slug"], goal, success=True)
            agent_tracker.add_learning(
                f"Spawned agent '{row['name']}' handled: {goal}",
                source=row["name"], category="factory-dispatch",
            )
        except Exception as e:
            result = f"[{row['name']}] error: {e}"
            agent_tracker.record_task_end(row["slug"], goal, success=False)
        await self.broadcast(f"[{row['name']}] Finished: {goal}")
        return result

    async def broadcast(self, message: str):
        try:
            await self.ws.broadcast(message)
        except:
            pass

    def get_status(self):
        agents = []
        for key, name, members in self.DISPLAY_GROUPS:
            working = any(self.agent_status.get(m) == "working" for m in members)
            agents.append({
                "key": key,
                "name": name,
                "status": "working" if working else "idle",
            })
        return {
            "overseer": {"name": "R.A.M.B.O", "role": "Overseer", "status": "online"},
            "agents": agents,
        }

    def detail_for(self, key: str):
        """Drill-down detail for a dashboard lineup entry — merges the activity
        of its underlying shell agents so the consolidated view stays coherent."""
        members = next((m for k, _n, m in self.DISPLAY_GROUPS if k == key), [key])
        return agent_tracker.get_detail_merged(members)

    def _display_key(self, name: str) -> str:
        """Map an internal shell agent (architect, engineer, …) to the consolidated
        lineup key the UI shows (planner, executor, …). Services and unknown names
        map to themselves so live broadcasts stay consistent with /agents/status."""
        for key, _n, members in self.DISPLAY_GROUPS:
            if name in members:
                return key
        return name

    # Friendly, operator-facing names for routing targets, so RAMBO can announce
    # a handoff in plain language instead of internal target keys.
    _TARGET_LABELS = {
        "planner": "the Planner",
        "executor": "the Executor",
        "researcher": "the Researcher",
        "keeper": "the Keeper",
        "orchestrate": "the full agent team",
        "spotify": "the Spotify controller",
        "dev": "the Engineer",
        "build": "the Engineer",
    }

    def _target_label(self, target: str) -> str:
        if target in self._TARGET_LABELS:
            return self._TARGET_LABELS[target]
        # Skills and spawned agents: humanize their slug (e.g. "weather-bot" →
        # "Weather Bot").
        return target.replace("-", " ").replace("_", " ").title()

    async def _announce_handoff(self, target: str, task: str):
        """Announce a hand-off ONLY when it's going to the Engineer (a build or a
        self-code edit) — that's the only hand-off the operator wants called out.
        Every other target just gets done quietly; RAMBO voices the result via
        _speak() afterward, so no 'handing this to X' chatter."""
        if target not in ("build", "dev"):
            return
        snippet = (task or "").strip()
        if len(snippet) > 80:
            snippet = snippet[:77].rstrip() + "…"
        msg = "Building" if target == "build" else "Drafting that change"
        if snippet:
            msg += f" — {snippet}"
        await self.broadcast(f"[Engineer] {msg}.")
        spoken = "On it — building that now." if target == "build" \
            else "On it — drafting that change now."
        await self._voice_text(spoken)

    async def _set_status(self, name: str, status: str):
        # Track per-shell (get_status aggregates), but broadcast the display key
        # so the live UI matches the consolidated lineup.
        self.agent_status[name] = status
        await self.broadcast(f"STATUS:{self._display_key(name)}:{status}")

    async def _contact(self, name: str):
        # structured (for the UI) + a human-readable log line
        display = self._display_key(name)
        await self.broadcast(json.dumps({"t": "contact", "agent": display}))
        await self.broadcast(f"[Pilot] Contacting {display.capitalize()} to finish the job.")

    async def _response(self, name: str, text: str):
        await self.broadcast(json.dumps({"t": "response", "agent": self._display_key(name), "text": text}))

    # ── Dispatch log helpers (best-effort — never raise) ──────────

    async def _register_dispatch(self, goal: str, plan: list[str]) -> "int | None":
        repo = getattr(self, "dispatch_repo", None)
        if not repo:
            return None
        try:
            return await repo.register(goal, "; ".join(plan))
        except Exception:
            return None

    async def _close_dispatch(self, dispatch_id, status: str, summary: str):
        repo = getattr(self, "dispatch_repo", None)
        if not repo or dispatch_id is None:
            return
        try:
            await repo.update_status(dispatch_id, status, summary[:500])
        except Exception:
            pass

    async def _dispatch_context(self) -> str:
        repo = getattr(self, "dispatch_repo", None)
        if not repo:
            return ""
        try:
            return await repo.format_for_prompt()
        except Exception:
            return ""

    # ── Tier 1: smart-routed entry point ─────────────────────────

    async def handle(self, goal: str, ctx: dict = None):
        ctx = ctx or {}

        # On-demand screen vision: an attached frame short-circuits straight to a
        # direct multimodal Q&A (no agent routing).
        image = ctx.get("image")
        if image:
            return await self._vision_answer(goal, image)

        # Deterministic fast-path: high-confidence watchlist commands ("keep an eye
        # on X", "remind me … is due …") go straight to the watchlist handler so the
        # LLM router can't mis-route them (e.g. "keep an eye on the AI chip market"
        # drifting to news).
        if self._is_watchlist_command(goal):
            res = await self._run_watchlist(goal)
            summary = await self._speak(goal, [f"watchlist: {goal}"], [res])
            self._remember_turn(goal, summary)
            return {"response": summary, "agent": "rambo"}

        roster_lines, valid_targets = await self._build_roster()
        # Semantic pre-filter: route over the top-K relevant lines, but keep the
        # FULL valid_targets set so the router may still name a non-shortlisted
        # target without sanitize() rewriting it. No-op without embeddings.
        shortlisted = await self.roster_index.shortlist(goal, roster_lines)

        # Resolve relative date phrases ("yesterday", "this week") to explicit
        # ranges. Stash them on ctx so skills (e.g. calendar) can reuse the same
        # resolution, and surface them to the router so it dispatches against
        # real dates instead of guessing.
        temporal = resolve_temporal(goal)
        if temporal:
            ctx["temporal"] = temporal
        temporal_ctx = format_temporal_context(temporal)

        # If we just asked a clarifying question, fold it into the routing context
        # (consume-once) so this turn's answer resolves the original request.
        clarify_ctx = ""
        if self._pending_clarify:
            pc = self._pending_clarify
            self._pending_clarify = None
            clarify_ctx = (
                f"CONTEXT: You earlier asked the operator: \"{pc['question']}\" about "
                f"their request \"{pc['goal']}\". This message is their answer — route "
                "the resolved, combined request (carry the original subject into the task)."
            )

        # Dispatch history is deliberately NOT fed to the router — it lists recently
        # FINISHED tasks (e.g. an old build) and was hijacking short follow-ups like
        # "yes". Recent conversation (below) is what gives follow-ups their context.
        prefix = "\n\n".join(p for p in (clarify_ctx, temporal_ctx) if p)
        routed_goal = f"{prefix}\n\n{goal}" if prefix else goal
        history = list(self._recent_turns)
        decision = await self.router.route(routed_goal, shortlisted, valid_targets,
                                           history=history)

        # Router unavailable or punted → keyword fallback (failure isolation).
        if decision is None:
            resp = await self._legacy_handle(goal, ctx)
            self._remember_turn(goal, resp.get("response", ""))
            return resp

        if decision.mode == "clarify":
            q = decision.question.strip()
            await self.broadcast(f"[R.A.M.B.O] {q}")
            await self._voice_text(q)
            # Remember the question + the request it was about, so the operator's
            # next utterance is routed as the answer (not in isolation).
            self.conversation.add_assistant_message(q)
            self._pending_clarify = {"question": q, "goal": goal}
            self._remember_turn(goal, q)
            return {"response": q, "agent": "rambo", "clarify": True}

        # dispatch: run each ordered step through the right target.
        plan, results = [], []
        for step in decision.steps:
            plan.append(f"{step.target}: {step.task}")

        dispatch_id = await self._register_dispatch(goal, plan)
        try:
            for step in decision.steps:
                await self._announce_handoff(step.target, step.task)
                res = await self._run_target(step.target, step.task, ctx)
                results.append(res)
            summary = await self._speak(goal, plan, results)
            await self._close_dispatch(dispatch_id, "completed", summary)
            self._remember_turn(goal, summary)
            return {"response": summary, "agent": "rambo"}
        except Exception as e:
            await self._close_dispatch(dispatch_id, "failed", str(e))
            raise

    async def _build_roster(self):
        """Return (roster_lines, valid_targets) over core agents, skills, and
        live Factory-spawned manifests. This is the menu the router routes over."""
        lines, targets = [], set()

        for name, desc in self.CORE_OWNERSHIP.items():
            lines.append(f"- {name} (core agent): {desc}")
            targets.add(name)

        lines.append(
            "- converse (conversation): greetings, small talk, opinions, and "
            "direct questions you can answer yourself in conversation without "
            "agents or tools. The default home for anything chatty or answerable."
        )
        targets.add("converse")

        lines.append(
            "- orchestrate (pipeline): open-ended multi-agent build/research "
            "goals that need full planning → task queue → multi-agent execution"
        )
        targets.add("orchestrate")

        lines.append(
            "- spotify (music): play/pause/skip songs, play a named playlist, "
            "search and play tracks, and report what's currently playing"
        )
        targets.add("spotify")

        lines.append(
            "- dev (self-coding): when the operator asks RAMBO to change its OWN "
            "code — fix a bug, add a feature/endpoint, refactor, edit its own "
            "files. Drafts the change on an isolated branch for review; never "
            "edits the running code directly."
        )
        targets.add("dev")

        lines.append(
            "- build (standalone app): when the operator asks RAMBO to BUILD a "
            "NEW standalone app, script, tool, or project (separate from RAMBO "
            "itself). Lands in a builds/ folder the operator can open on their "
            "desktop. Use this for 'build me a …', not for editing RAMBO's own code."
        )
        targets.add("build")

        lines.append(
            "- watchlist (proactive watch): add/remove/list the operator's WATCH "
            "topics (things to keep an eye on) and DEADLINES. Use for 'keep an eye "
            "on X', 'watch/track/monitor X', 'stop watching X', 'what am I "
            "watching', 'remind me X is due Friday', 'add a deadline …', 'what are "
            "my deadlines'."
        )
        targets.add("watchlist")

        for skill in SKILLS:
            desc = skill.get("desc") or f"real-world '{skill['name']}' action"
            lines.append(f"- {skill['name']} (live skill): {desc}")
            targets.add(skill["name"])

        if self.factory_repo:
            try:
                for row in await self.factory_repo.list_active_agents():
                    lines.append(f"- {row['slug']} (spawned agent): {row['specialty']}")
                    targets.add(row["slug"])
            except Exception:
                pass

        return lines, targets

    # High-confidence watchlist phrases — deterministic so they never mis-route.
    _WATCHLIST_RE = re.compile(
        r"\b(keep an eye on|keep tabs on|keep watching|stop watching|stop tracking|"
        r"what am i watching|watch ?list|add (?:a )?deadline|set (?:a )?deadline|"
        r"my deadlines|upcoming deadlines|what are my deadlines)\b|\bis due\b|\bare due\b",
        re.IGNORECASE)

    def _is_watchlist_command(self, goal: str) -> bool:
        return bool(self._WATCHLIST_RE.search(goal or ""))

    async def _run_watchlist(self, task: str) -> str:
        """Add/remove/list WATCH topics + DEADLINES from natural language, so the
        operator can say 'keep an eye on X' or 'remind me Y is due Friday' instead
        of typing into the Watch tab. Reuses seeker_watch + proactive_nudges."""
        repo = getattr(self, "keeper_repo", None)
        if not repo:
            return "Memory store isn't available right now."
        import re as _re
        import seeker_watch
        import proactive_nudges as pn
        t = task.strip()
        low = t.lower()

        # ── list ──
        if _re.search(r"what am i watching|watch ?list|watch topics|what.*watching", low):
            topics = await seeker_watch.list_topics(repo)
            if not topics:
                return "You're not watching anything yet, sir."
            return "You're watching: " + ", ".join(x["topic"] for x in topics) + "."
        if _re.search(r"deadlines?\b", low) and _re.search(r"what|list|my|upcoming|show", low) \
                and not _re.search(r"\bdue\b|add|set|new", low):
            dls = await pn.list_deadlines(repo)
            if not dls:
                return "No deadlines tracked, sir."
            return "Deadlines: " + "; ".join(f"{d['text']} ({d['due']})" for d in dls) + "."

        # ── remove a watch topic ──
        m = _re.search(r"stop (?:watching|tracking|monitoring|following)\s+(.+)", t, _re.I)
        if m:
            name = m.group(1).strip(" .?!")
            ok = await seeker_watch.remove_topic(repo, seeker_watch.slugify(name))
            return f"Stopped watching \"{name}\", sir." if ok else f"I wasn't watching \"{name}\"."

        # ── add a deadline (phrasing with 'due' or 'deadline') ──
        if " due " in f" {low} " or "deadline" in low:
            text_part, when_part = None, None
            idx = low.rfind(" due ")
            if idx != -1:
                text_part, when_part = t[:idx], t[idx + 5:]
            else:
                dm = _re.search(r"deadline(?:\s+for)?\s+(.+?)\s+(?:on|by|for|at)\s+(.+)", t, _re.I)
                if dm:
                    text_part, when_part = dm.group(1), dm.group(2)
            if text_part and when_part:
                text_part = _re.sub(r"^(?:remind me(?: that)?|please|hey|can you|"
                                    r"remember(?: that)?|set|add|a|new|the)\s+", "",
                                    text_part.strip(), flags=_re.I).strip()
                text_part = _re.sub(r"\b(is|are|'s)$", "", text_part).strip(" .?!")
                res = await pn.add_deadline(repo, text_part, when_part.strip(" .?!"))
                if res.get("error"):
                    return (f"I couldn't pin a date from \"{when_part.strip()}\", sir — "
                            "try 'tomorrow', 'next Friday', or a date like 2026-07-01.")
                return f"Logged it — \"{res['text']}\" due {res['due']}, sir."

        # ── add a watch topic ──
        m = _re.search(r"(?:keep an eye on|keep tabs on|keep watching|watch|track|"
                       r"monitor|follow)\s+(.+)", t, _re.I)
        if m:
            topic = _re.sub(r"\s+for me\b", "", m.group(1), flags=_re.I).strip(" .?!")
            if topic:
                await seeker_watch.add_topic(repo, topic)
                return f"On it — I'll keep an eye on \"{topic}\" and flag anything new, sir."

        return ("Tell me what to watch or track — e.g. \"keep an eye on NVDA\" or "
                "\"remind me the report is due Friday,\" sir.")

    async def _run_target(self, target: str, task: str, ctx: dict) -> str:
        """Dispatch one routed step. Every branch is isolated so a single
        target failing never aborts the whole turn (Tier 3)."""
        try:
            if target == "converse":
                # No agent work — the goal is answerable in conversation. Returning
                # an empty marker lets _speak() voice a direct LLM reply.
                return ""

            if target == "orchestrate":
                plan, results = await self._orchestrate(task)
                return "\n".join(str(r) for r in results) if results else "(no output)"

            if target == "watchlist":
                return await self._run_watchlist(task)

            if target == "spotify":
                # Spotify is an external integration → light the Executor (link).
                await self._set_status("link", "working")
                try:
                    return await self._run_spotify(task)
                finally:
                    await self._set_status("link", "idle")

            if target == "dev":
                return await self._run_dev_session(task)

            if target == "build":
                return await self._run_build_session(task)

            skill = next((s for s in SKILLS if s["name"] == target), None)
            if skill:
                return await self._run_skill(skill, task, ctx)

            if self.factory_repo:
                row = await self.factory_repo.get_agent_by_slug(target)
                if row and row.get("status") == "active":
                    # Spawned agents aren't in the lineup → light Pilot (dispatcher).
                    await self._set_status("pilot", "working")
                    try:
                        return await self._run_spawned(row, task)
                    finally:
                        await self._set_status("pilot", "idle")

            # Router-facing modes resolve to their underlying shell agent.
            resolved = self._MODE_AGENTS.get(target, target)
            if resolved in self.agents:
                return await self._run_core_agent(resolved, task)

            # Unknown target slipped through → fall back to full pipeline.
            plan, results = await self._orchestrate(task)
            return "\n".join(str(r) for r in results) if results else "(no output)"
        except Exception as e:
            return f"[{target}] error: {e}"

    async def _run_skill(self, skill: dict, goal: str, ctx: dict) -> str:
        agent_name = skill["agent"]
        label = self._display_key(agent_name).capitalize()
        await self._set_status(agent_name, "working")
        agent_tracker.record_task_start(agent_name, goal)
        await self.broadcast(f"[{label}] Working on: {goal}")
        try:
            result = await skill["run"](goal, ctx)
            agent_tracker.record_task_end(agent_name, goal, success=True)
            agent_tracker.add_learning(
                f"Completed skill '{skill['name']}' for: {goal}",
                source=label, category=skill["name"],
            )
        except Exception as e:
            result = f"[{skill['name']}] error: {e}"
            agent_tracker.record_task_end(agent_name, goal, success=False)
        await self.broadcast(f"[{label}] Finished: {goal}")
        await self._set_status(agent_name, "idle")
        return result

    async def _run_dev_session(self, task: str) -> str:
        """Self-coding lane: draft a change to RAMBO's OWN code on an isolated
        branch, analyze its impact, and register it for operator review. Never
        merges — the operator approves in the Code Review dock."""
        if not self.dev_repo or not self.llm:
            return ("The self-coding lane isn't available right now "
                    "(needs the dev agent and an API key configured).")
        from dev_agent import session as dev_session
        import uuid

        change_id = uuid.uuid4().hex[:12]
        await self.dev_repo.create(change_id, task)
        await self._set_status("engineer", "working")
        await self.broadcast(f"[Engineer] Drafting self-change: {task}")

        async def _emit(**kw):
            await self.ws.broadcast_json({"t": "dev_progress", "id": change_id, **kw})

        def _emit_sync(**kw):
            asyncio.create_task(_emit(**kw))

        try:
            impact = await dev_session.draft_change(
                llm=self.llm, repo=self.dev_repo, change_id=change_id, goal=task,
                personality_text=self.personality_text, on_event=_emit_sync,
            )
        finally:
            await self.broadcast(f"[Engineer] Finished drafting: {task}")
            await self._set_status("engineer", "idle")

        rec = impact.get("recommendation")
        affects = ", ".join(impact.get("affects") or []) or "a few files"
        if rec == "merge":
            verdict = "My read is it's safe to merge."
        elif rec == "escalate":
            verdict = "It looks right, but I'd want Claude's eyes on it before merging."
        else:  # hold
            verdict = "I'd hold off merging — it's not ready or it's risky."
        # Returned as a result block; _speak() voices it in RAMBO's tone.
        return (
            f"Drafted the change on an isolated branch (id {change_id}) — nothing is "
            f"merged. It touches {affects}. {impact.get('summary','')} {verdict} "
            f"It's waiting in the review dock for you to look at the diff and decide."
        )

    async def _run_build_session(self, task: str) -> str:
        """Standalone build lane: build a NEW project into builds/<slug>/ that the
        operator can open on their desktop. Not a RAMBO self-edit — no merge gate."""
        if not self.builds_repo or not self.llm:
            return ("The build lane isn't available right now "
                    "(needs the builds repo and an API key configured).")
        from dev_agent import builds as builds_mod
        import uuid

        # Short, human folder name (e.g. "Calculator", "Snake Game") instead of the
        # whole sentence. LLM-summarized with a heuristic fallback.
        name = await builds_mod.summarize_build_name(self.llm, task)
        slug = base = builds_mod.slugify(name)
        i = 2
        while await self.builds_repo.slug_taken(slug):
            slug = f"{base}-{i}"
            i += 1
        await self.builds_repo.create(uuid.uuid4().hex[:12], slug, name, task)
        await self._set_status("engineer", "working")
        await self.broadcast(f"[Engineer] Building: {task}")

        async def _emit(**kw):
            await self.ws.broadcast_json({"t": "build_progress", "slug": slug, **kw})

        try:
            result = await builds_mod.build_app(
                llm=self.llm, repo=self.builds_repo, slug=slug, name=name, goal=task,
                personality_text=self.personality_text, on_event=lambda **k: asyncio.create_task(_emit(**k)),
            )
        finally:
            await self.broadcast(f"[Engineer] Finished building: {task}")
            await self._set_status("engineer", "idle")

        if result.get("error"):
            return f"I hit a problem building that: {result['error']}"
        host_path = result.get("host_path", "the builds folder")
        files = result.get("files") or []
        return (
            f"Built it — it's in `{host_path}` ({len(files)} file"
            f"{'' if len(files) == 1 else 's'}). It's in the Builds dock; "
            f"hit Open and I'll pop it up on your desktop."
        )

    async def _run_core_agent(self, agent_name: str, task_desc: str) -> str:
        from models.task import Task
        task = Task(description=task_desc)
        agent = self.agents[agent_name]
        await self._contact(agent_name)
        await self._set_status(agent_name, "working")
        agent_tracker.record_task_start(agent_name, task_desc)
        label = self._display_key(agent_name).capitalize()
        await self.broadcast(f"[{label}] Starting: {task_desc}")

        if agent_name in ("engineer", "steward", "link"):
            sentinel = self.agents["sentinel"]
            await self._set_status("sentinel", "working")
            decision = sentinel.review_task(task)
            if decision["status"] == "DENY":
                msg = f"[Sentinel] BLOCKED: {decision['reason']}"
                await self.broadcast(msg)
                await self._set_status("sentinel", "idle")
                await self._set_status(agent_name, "idle")
                return msg
            if decision["status"] == "REVIEW":
                approval = sentinel_queue.add_approval(task, agent_name)
                msg = f"[Sentinel] HOLD: {approval['description']} (awaiting approval)"
                await self.broadcast(msg)
                await self._set_status("sentinel", "idle")
                await self._set_status(agent_name, "idle")
                return msg
            await self._set_status("sentinel", "idle")

        try:
            if agent_name == "keeper":
                output = await self._run_keeper(task_desc)
            else:
                output = agent.execute(task)
        except Exception as e:                       # Tier 3: contain agent crashes
            output = f"[{agent_name}] ran into trouble: {e}"
            agent_tracker.record_task_end(agent_name, task_desc, success=False)
        else:
            agent_tracker.record_task_end(agent_name, task_desc, success=True)

        await self._response(agent_name, output)
        await self.broadcast(f"[{label}] Finished: {task_desc}")
        await self._set_status(agent_name, "idle")
        return output

    async def _orchestrate(self, goal: str):
        """The full architect → pilot → multi-agent execution pipeline.
        Returns (plan, results). agent.execute is wrapped so one core agent
        throwing can't crash the turn (Tier 3)."""
        architect = self.agents["architect"]
        pilot     = self.agents["pilot"]

        await self._set_status("architect", "working")
        await self.broadcast(f"[Planner] Creating plan for goal: {goal}")
        plan = architect.create_plan(goal)
        await self.broadcast(f"[Planner] Plan created with {len(plan)} steps.")
        await self._set_status("architect", "idle")

        await self._set_status("pilot", "working")
        await self.broadcast("[Pilot] Building task queue...")
        tasks = pilot.build_task_queue(goal, plan)
        await self.broadcast(f"[Pilot] {len(tasks)} tasks queued.")
        await self._set_status("pilot", "idle")

        results = []
        for task in tasks:
            agent_name = choose_brain(task)
            output = await self._run_core_agent(agent_name, task.description)
            results.append(output)
            await asyncio.sleep(0.15)

        agent_tracker.add_learning(
            f"Orchestrated {len(tasks)} tasks for: {goal}",
            source="Pilot", category="orchestration",
        )
        return plan, results

    async def _legacy_handle(self, goal: str, ctx: dict):
        """Keyword-routed fallback for when the LLM router is unavailable.
        Preserves the original skill → spawned → orchestrate behavior."""
        skill = match_skill(goal)
        if skill:
            result = await self._run_skill(skill, goal, ctx)
            voiced = await self._speak(goal, [f"Skill: {skill['name']}"], [result])
            return {"response": voiced, "agent": "rambo"}

        spawned = await self._dispatch_spawned(goal)
        if spawned is not None:
            return spawned

        plan, results = await self._orchestrate(goal)
        summary = await self._speak(goal, plan, results)
        return {"response": summary, "agent": "rambo"}

    _SENTENCE_END = re.compile(
        r'(?<=[.!?])\s+(?=[A-Z"])'
        r'|(?<=[.!?])$'
    )
    _ABBREVS = re.compile(r'\b(?:Mr|Mrs|Ms|Dr|Sr|Jr|e\.g|i\.e|vs|etc)\.\s*$', re.IGNORECASE)

    def _split_sentence(self, buffer: str) -> tuple[str | None, str]:
        for m in self._SENTENCE_END.finditer(buffer):
            candidate = buffer[:m.start()].rstrip()
            if not candidate:
                continue
            if self._ABBREVS.search(candidate):
                continue
            remainder = buffer[m.end():]
            return candidate, remainder
        return None, buffer

    # Spoken-form fix: the dotted acronym makes TTS spell out "R-A-M-B-O".
    # Say it as the word "Rambo" instead (voice only — on-screen text is untouched).
    _SPOKEN_RAMBO = re.compile(r"R\.A\.M\.B\.O\.?", re.IGNORECASE)

    async def _segment_audio(self, text: str) -> "str | None":
        """Synthesize a spoken segment to base64 MP3, best-effort. None on
        missing client, empty result, or any error."""
        tts = getattr(self, "tts", None)
        if not tts:
            return None
        try:
            spoken = self._SPOKEN_RAMBO.sub("Rambo", text)
            data = await tts.synthesize(spoken)
            if not data:
                return None
            await self._record_tts_usage(spoken, getattr(tts, "model", ""))
            import base64
            return base64.b64encode(data).decode("ascii")
        except Exception:
            return None

    async def _record_tts_usage(self, text: str, model: str) -> None:
        """Best-effort: log characters sent to ElevenLabs for the credit HUD."""
        repo = getattr(self, "tts_usage_repo", None)
        if not repo:
            return
        try:
            await repo.record(len(text), model)
        except Exception:
            pass

    async def _emit_segment(self, text: str, base_turn_id: str, seq: int, is_final: bool, t0: float):
        segment_id = f"{base_turn_id}::{seq}"
        payload = {
            "t": "speak_segment",
            "turn_id": segment_id,
            "base_turn_id": base_turn_id,
            "seq": seq,
            "text": text,
            "is_final": is_final,
        }
        audio = await self._segment_audio(text)
        if audio:
            payload["audio"] = audio
        await self.ws.broadcast_json(payload)
        elapsed = time.monotonic() - t0
        print(f"[stream] speak_segment base={base_turn_id} seq={seq} "
              f"chars={len(text)} t_since_start={elapsed:.2f}s final={is_final}")

    async def _voice_text(self, text: str) -> None:
        """Speak an already-decided string (e.g. a clarify question) through the
        ElevenLabs pipeline as speak_segment(s). No LLM call. Per-segment, if
        ElevenLabs yields no audio, _emit_segment omits the audio field and the
        frontend's browser-voice last resort takes over (unchanged behavior)."""
        text = (text or "").strip()
        if not text:
            return
        t0 = time.monotonic()
        base_turn_id = uuid.uuid4().hex
        # Split into sentences for natural cadence; reuse the existing splitter.
        sentences, buf = [], text
        while True:
            s, buf = self._split_sentence(buf)
            if s is None:
                break
            sentences.append(s)
        if buf.strip():
            sentences.append(buf.strip())
        if not sentences:
            sentences = [text]
        for i, s in enumerate(sentences):
            await self._emit_segment(s, base_turn_id, i, i == len(sentences) - 1, t0)

    @staticmethod
    def _cache_last_message(messages: list[dict]) -> None:
        """Place a rolling cache breakpoint on the last message so the growing
        conversation prefix is read from cache on the next turn instead of
        re-paid at full price. Converts the last message's string content into a
        single cached text block. No-op on empty history."""
        if not messages:
            return
        last = messages[-1]
        content = last.get("content")
        if isinstance(content, str):
            last["content"] = [{
                "type": "text",
                "text": content,
                "cache_control": cache_config.cache_control(),
            }]
        elif isinstance(content, list) and content:
            block = content[-1]
            if isinstance(block, dict):
                block["cache_control"] = cache_config.cache_control()

    async def _speak(self, goal: str, plan: list[str], results: list[str]) -> str:
        results_block = "\n".join(f"  - {r}" for r in results)

        if not self.llm:
            text = results_block.strip()
            await self._response("rambo", text)
            await self.broadcast("[R.A.M.B.O] Response delivered.")
            return text

        execution_report = (
            f"Operator goal: {goal}\n\n"
            f"Plan:\n" + "\n".join(f"  - {s}" for s in plan) + "\n\n"
            f"Agent results:\n" + results_block
        )
        dispatch_ctx = await self._dispatch_context()
        if dispatch_ctx:
            execution_report = f"{dispatch_ctx}\n\n{execution_report}"

        self.conversation.add_user_message(execution_report)
        messages = self.conversation.get_messages_for_api()
        append_voice_cue(messages)
        self._cache_last_message(messages)
        operator_ctx = await self._build_operator_context(goal)
        return await self._stream_voice(messages, fallback_text=results_block,
                                        system_context=operator_ctx)

    async def _stream_voice(
        self, messages: list[dict], fallback_text: str = "", *, source: str = "conversation",
        system_context: str = "",
    ) -> str:
        """Stream a voiced reply for already-prepared `messages`: split into
        sentences, emit speak_segments (+TTS) over WS, record usage, persist the
        assistant turn, and return the full text. Shared by _speak and
        _vision_answer so the voice/TTS pipeline lives in one place."""
        system = build_system_prompt(self.personality_text, context=system_context)

        t0 = time.monotonic()
        base_turn_id = uuid.uuid4().hex
        seq = 0
        held_text = None
        held_seq = None
        sentences = []
        token_buf = ""
        text = (fallback_text or "").strip()

        try:
            async with self.llm.messages.stream(
                model=model_config.default_model(),
                system=system,
                messages=messages,
                max_tokens=1024,
            ) as stream:
                async for event in stream:
                    if event.type == "content_block_delta" and event.delta.type == "text_delta":
                        token_buf += event.delta.text
                        while True:
                            sentence, token_buf = self._split_sentence(token_buf)
                            if sentence is None:
                                break
                            sentences.append(sentence)
                            await self.ws.broadcast_json({"t": "transcript_delta", "text": sentence})
                            if held_text is not None:
                                await self._emit_segment(held_text, base_turn_id, held_seq, False, t0)
                            held_text = sentence
                            held_seq = seq
                            seq += 1

            final_msg = await stream.get_final_message()
            await record_usage(final_msg.model, final_msg.usage, source=source)

            if token_buf.strip():
                sentences.append(token_buf.strip())
                await self.ws.broadcast_json({"t": "transcript_delta", "text": token_buf.strip()})
                if held_text is not None:
                    await self._emit_segment(held_text, base_turn_id, held_seq, False, t0)
                held_text = token_buf.strip()
                held_seq = seq
                seq += 1

            text = " ".join(s for s in sentences if s)

            if held_text is not None:
                await self._emit_segment(held_text, base_turn_id, held_seq, True, t0)

        except Exception:
            text = (fallback_text or "").strip()
            await self._emit_segment(text, base_turn_id, 0, True, t0)

        self.conversation.add_assistant_message(text)
        await self._response("rambo", text)
        await self.broadcast("[R.A.M.B.O] Response delivered.")
        return text

    async def _vision_answer(self, goal: str, image_b64: str) -> dict:
        """On-demand screen vision: answer/describe what's in the captured frame.
        Bypasses agent routing — it's a direct multimodal Q&A in R.A.M.B.O's voice.
        The image is sent for THIS call only; conversation history keeps a text-only
        turn so screenshots don't bloat (and re-bill) every later turn."""
        if not self.llm:
            msg = "Vision's offline — no model is wired."
            await self._response("rambo", msg)
            await self.broadcast("[R.A.M.B.O] Response delivered.")
            return {"response": msg, "agent": "rambo"}

        question = (goal or "").strip() or "What's on my screen right now? Describe what you see."
        await self.broadcast("[R.A.M.B.O] Looking at your screen…")

        # Persist a text-only user turn; swap in the image for the API call only.
        self.conversation.add_user_message(question)
        messages = self.conversation.get_messages_for_api()
        messages[-1] = {
            "role": "user",
            "content": [
                {"type": "text", "text": question},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": image_b64,
                    },
                },
            ],
        }
        append_voice_cue(messages)
        self._cache_last_message(messages)
        operator_ctx = await self._build_operator_context(question)
        text = await self._stream_voice(
            messages, fallback_text="I couldn't make out the screen.", source="vision",
            system_context=operator_ctx,
        )
        return {"response": text, "agent": "rambo"}
