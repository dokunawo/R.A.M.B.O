"""Tier 5 — Registry watcher.

Polls spawned_agents every 30s and (un)registers dispatch tools
for new/archived agents. Also called immediately on approval.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable

from factory.config_agent import ConfigDrivenAgent
from factory.repo import FactoryRepo
from factory.tool_registry import ToolDef, ToolRegistry

logger = logging.getLogger(__name__)

POLL_INTERVAL = 30


def build_dispatch_tool(slug: str, row: dict, registry: ToolRegistry, llm_client) -> ToolDef:
    async def execute(message: str, **kwargs) -> str:
        agent = ConfigDrivenAgent(row=row, tool_registry=registry, llm_client=llm_client)
        return await agent.run(message)

    return ToolDef(
        name=f"dispatch_to_{slug}",
        description=f"Dispatch a message to the '{row['name']}' agent. Specialty: {row['specialty']}",
        input_schema={
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "The message to send to this agent"},
            },
            "required": ["message"],
        },
        execute=execute,
        factory_allowed=False,
    )


class RegistryWatcher:
    def __init__(
        self,
        *,
        repo: FactoryRepo,
        tool_registry: ToolRegistry,
        llm_client,
    ):
        self._repo = repo
        self._tools = tool_registry
        self._llm = llm_client
        self._known_slugs: set[str] = set()
        self._task: asyncio.Task | None = None

    async def refresh(self) -> None:
        rows = await self._repo.list_active_agents()
        new_slugs = {r["slug"] for r in rows}
        rows_by_slug = {r["slug"]: r for r in rows}

        for slug in new_slugs - self._known_slugs:
            tool = build_dispatch_tool(
                slug, rows_by_slug[slug], self._tools, self._llm,
            )
            self._tools.register(tool)
            logger.info("Registered dispatch_to_%s", slug)

        for slug in self._known_slugs - new_slugs:
            self._tools.unregister(f"dispatch_to_{slug}")
            logger.info("Unregistered dispatch_to_%s", slug)

        self._known_slugs = new_slugs

    async def _poll_loop(self) -> None:
        while True:
            try:
                await self.refresh()
            except Exception:
                logger.exception("Registry watcher poll failed")
            await asyncio.sleep(POLL_INTERVAL)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._poll_loop())
            logger.info("Registry watcher started (poll every %ds)", POLL_INTERVAL)

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("Registry watcher stopped")
