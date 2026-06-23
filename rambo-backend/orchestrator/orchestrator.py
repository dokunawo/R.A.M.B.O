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
from memory.sqlite_store import SQLiteStore
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
import sentinel_queue


class Orchestrator:
    def __init__(self):
        self.store = SQLiteStore()
        self.ws = ConnectionManager()
        self.conversation = ConversationManager()
        self.personality_text = load_personality()
        self.llm = (
            anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
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
            "keeper":    Keeper(self.store),
            "echo":      Echo(),
            "pilot":     Pilot(),
        }

        self.agent_status = {name: "idle" for name in self.agents}

    async def broadcast(self, message: str):
        try:
            await self.ws.broadcast(message)
        except:
            pass

    def get_status(self):
        return {
            "overseer": {"name": "R.A.M.B.O", "role": "Overseer", "status": "online"},
            "agents": [
                {"name": name.capitalize(), "status": self.agent_status[name]}
                for name in self.agents
            ],
        }

    async def _set_status(self, name: str, status: str):
        self.agent_status[name] = status
        await self.broadcast(f"STATUS:{name}:{status}")

    async def _contact(self, name: str):
        # structured (for the UI) + a human-readable log line
        await self.broadcast(json.dumps({"t": "contact", "agent": name}))
        await self.broadcast(f"[Pilot] Contacting {name.capitalize()} agent to finish the job.")

    async def _response(self, name: str, text: str):
        await self.broadcast(json.dumps({"t": "response", "agent": name, "text": text}))

    async def handle(self, goal: str, ctx: dict = None):
        ctx = ctx or {}

        # Real-world skills run first (weather, etc.). The matched agent flips
        # WORKING → runs the live skill → IDLE, and its result is returned.
        skill = match_skill(goal)
        if skill:
            agent_name = skill["agent"]
            await self._set_status(agent_name, "working")
            agent_tracker.record_task_start(agent_name, goal)
            await self.broadcast(f"[{agent_name.capitalize()}] Working on: {goal}")
            try:
                result = await skill["run"](goal, ctx)
                agent_tracker.record_task_end(agent_name, goal, success=True)
                agent_tracker.add_learning(
                    f"Completed skill '{skill['name']}' for: {goal}",
                    source=agent_name.capitalize(), category=skill["name"],
                )
            except Exception as e:
                result = f"[{skill['name']}] error: {e}"
                agent_tracker.record_task_end(agent_name, goal, success=False)
            await self.broadcast(f"[{agent_name.capitalize()}] Finished: {goal}")
            await self._set_status(agent_name, "idle")

            voiced = await self._speak(goal, [f"Skill: {skill['name']}"], [result])
            return {"response": voiced, "agent": "rambo"}

        architect = self.agents["architect"]
        pilot     = self.agents["pilot"]
        echo      = self.agents["echo"]

        await self._set_status("architect", "working")
        await self.broadcast(f"[Architect] Creating plan for goal: {goal}")
        plan = architect.create_plan(goal)
        await self.broadcast(f"[Architect] Plan created with {len(plan)} steps.")
        await self._set_status("architect", "idle")

        await self._set_status("pilot", "working")
        await self.broadcast("[Pilot] Building task queue...")
        tasks = pilot.build_task_queue(goal, plan)
        await self.broadcast(f"[Pilot] {len(tasks)} tasks queued.")
        await self._set_status("pilot", "idle")

        results = []

        for task in tasks:
            agent_name = choose_brain(task)
            agent      = self.agents[agent_name]

            await self._contact(agent_name)
            await self._set_status(agent_name, "working")
            agent_tracker.record_task_start(agent_name, task.description)
            await self.broadcast(f"[{agent_name.capitalize()}] Starting: {task.description}")

            if agent_name in ("engineer", "steward", "link"):
                sentinel = self.agents["sentinel"]
                await self._set_status("sentinel", "working")
                decision = sentinel.review_task(task)

                if decision["status"] == "DENY":
                    msg = f"[Sentinel] BLOCKED: {decision['reason']}"
                    await self.broadcast(msg)
                    await self._set_status("sentinel", "idle")
                    await self._set_status(agent_name, "idle")
                    results.append(msg)
                    continue

                if decision["status"] == "REVIEW":
                    approval = sentinel_queue.add_approval(task, agent_name)
                    msg = f"[Sentinel] HOLD: {approval['description']} (awaiting approval)"
                    await self.broadcast(msg)
                    await self._set_status("sentinel", "idle")
                    await self._set_status(agent_name, "idle")
                    results.append(msg)
                    continue

                await self._set_status("sentinel", "idle")

            output = agent.execute(task)
            results.append(output)
            agent_tracker.record_task_end(agent_name, task.description, success=True)

            await self._response(agent_name, output)
            await self.broadcast(f"[{agent_name.capitalize()}] Finished: {task.description}")
            await self._set_status(agent_name, "idle")
            await asyncio.sleep(0.15)

        agent_tracker.add_learning(
            f"Orchestrated {len(tasks)} tasks for: {goal}",
            source="Pilot", category="orchestration",
        )

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

    async def _emit_segment(self, text: str, base_turn_id: str, seq: int, is_final: bool, t0: float):
        segment_id = f"{base_turn_id}::{seq}"
        await self.ws.broadcast_json({
            "t": "speak_segment",
            "turn_id": segment_id,
            "base_turn_id": base_turn_id,
            "seq": seq,
            "text": text,
            "is_final": is_final,
        })
        elapsed = time.monotonic() - t0
        print(f"[stream] speak_segment base={base_turn_id} seq={seq} "
              f"chars={len(text)} t_since_start={elapsed:.2f}s final={is_final}")

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

        self.conversation.add_user_message(execution_report)
        messages = self.conversation.get_messages_for_api()
        append_voice_cue(messages)
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
                model="claude-sonnet-4-20250514",
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

            final_msg = stream.get_final_message()
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
