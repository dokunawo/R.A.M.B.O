import asyncio
import json
import os
import re
import time
import uuid

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
import sentinel_queue
import cache_config
import model_config
from skills import SKILLS


class Orchestrator:
    def __init__(self):
        self.keeper_repo = None   # set by main.py once the DB exists
        self.ws = ConnectionManager()
        self.conversation = ConversationManager()
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

        # Factory wiring — set later by main.py once the DB + registry exist.
        self.factory_repo = None
        self.tool_registry = None

        # Dispatch log — set later via set_dispatch_repo (best-effort, may be None).
        self.dispatch_repo = None

        # TTS client — set later via set_tts (best-effort, may be None).
        self.tts = None
        self.tts_usage_repo = None

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

    def set_dispatch_repo(self, dispatch_repo):
        """Give the orchestrator a durable dispatch log (best-effort)."""
        self.dispatch_repo = dispatch_repo

    def set_tts(self, tts):
        """Give the orchestrator a best-effort TTS client (or None)."""
        self.tts = tts

    def set_tts_usage_repo(self, repo):
        """Give the orchestrator a best-effort ElevenLabs character-usage log."""
        self.tts_usage_repo = repo

    def set_keeper_repo(self, repo):
        """Give the Keeper agent a durable memory store."""
        self.keeper_repo = repo

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
                return "[Keeper] " + "; ".join(f"{h['key']}: {h['value']}" for h in hits)
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

        roster_lines, valid_targets = await self._build_roster()
        dispatch_ctx = await self._dispatch_context()
        routed_goal = f"{dispatch_ctx}\n\n{goal}" if dispatch_ctx else goal
        decision = await self.router.route(routed_goal, roster_lines, valid_targets)

        # Router unavailable or punted → keyword fallback (failure isolation).
        if decision is None:
            return await self._legacy_handle(goal, ctx)

        if decision.mode == "clarify":
            q = decision.question.strip()
            await self.broadcast(f"[R.A.M.B.O] {q}")
            return {"response": q, "agent": "rambo", "clarify": True}

        # dispatch: run each ordered step through the right target.
        plan, results = [], []
        for step in decision.steps:
            plan.append(f"{step.target}: {step.task}")

        dispatch_id = await self._register_dispatch(goal, plan)
        try:
            for step in decision.steps:
                res = await self._run_target(step.target, step.task, ctx)
                results.append(res)
            summary = await self._speak(goal, plan, results)
            await self._close_dispatch(dispatch_id, "completed", summary)
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

        for skill in SKILLS:
            lines.append(f"- {skill['name']} (live skill): real-world '{skill['name']}' action")
            targets.add(skill["name"])

        if self.factory_repo:
            try:
                for row in await self.factory_repo.list_active_agents():
                    lines.append(f"- {row['slug']} (spawned agent): {row['specialty']}")
                    targets.add(row["slug"])
            except Exception:
                pass

        return lines, targets

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

            skill = next((s for s in SKILLS if s["name"] == target), None)
            if skill:
                return await self._run_skill(skill, task, ctx)

            if self.factory_repo:
                row = await self.factory_repo.get_agent_by_slug(target)
                if row and row.get("status") == "active":
                    return await self._run_spawned(row, task)

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

    async def _segment_audio(self, text: str) -> "str | None":
        """Synthesize a spoken segment to base64 MP3, best-effort. None on
        missing client, empty result, or any error."""
        tts = getattr(self, "tts", None)
        if not tts:
            return None
        try:
            data = await tts.synthesize(text)
            if not data:
                return None
            await self._record_tts_usage(text, getattr(tts, "model", ""))
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
        system = build_system_prompt(self.personality_text)

        t0 = time.monotonic()
        base_turn_id = uuid.uuid4().hex
        seq = 0
        held_text = None
        held_seq = None
        sentences = []
        token_buf = ""

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
            await record_usage(final_msg.model, final_msg.usage)

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
            text = results_block.strip()
            await self._emit_segment(text, base_turn_id, 0, True, t0)

        self.conversation.add_assistant_message(text)
        await self._response("rambo", text)
        await self.broadcast("[R.A.M.B.O] Response delivered.")
        return text
