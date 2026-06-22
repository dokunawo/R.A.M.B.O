import asyncio

from models.task import Task
from router import choose_brain
from memory.sqlite_store import SQLiteStore

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
import sentinel_queue


class Orchestrator:
    def __init__(self):
        self.store = SQLiteStore()
        self.ws = ConnectionManager()

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

    async def handle(self, goal: str):
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

            await self._set_status(agent_name, "working")
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

            await self.broadcast(f"[{agent_name.capitalize()}] Finished: {task.description}")
            await self._set_status(agent_name, "idle")
            await asyncio.sleep(0.15)

        await self._set_status("echo", "working")
        await self.broadcast("[Echo] Finalizing response...")
        summary = echo.summarize(goal, plan, results)
        await self.broadcast("[Echo] Response ready.")
        await self._set_status("echo", "idle")

        return summary
