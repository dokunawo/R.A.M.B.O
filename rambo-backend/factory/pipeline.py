"""Tier 3 — Spawn pipeline.

Walks a spawn_tasks row through every state from PENDING to
AWAITING_APPROVAL. Wraps everything in a try/except so that a
task always lands in a terminal state.
"""

from __future__ import annotations

import logging
import re
import uuid

from factory.repo import FactoryRepo, State, RESERVED_SLUGS
from factory.research import run_research
from factory.sanitize import sanitize_role_input
from factory.schemas import SkillsReport
from factory.spec_writer import generate_system_prompt, write_spec_markdown
from factory.tool_registry import ToolRegistry
import model_config

logger = logging.getLogger(__name__)


def _slugify(name_hint: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name_hint.strip().lower()).strip("-")
    return slug or "agent"


class SpawnPipeline:
    def __init__(
        self,
        *,
        repo: FactoryRepo,
        tool_registry: ToolRegistry,
        llm_client,
        emit_event=None,
    ):
        self._repo = repo
        self._tools = tool_registry
        self._llm = llm_client
        self._emit_event = emit_event or (lambda **kw: None)

    async def run(self, task_id: str) -> None:
        """Drive a task from PENDING → AWAITING_APPROVAL (or FAILED)."""
        try:
            await self._run_inner(task_id)
        except Exception as exc:
            logger.exception("Pipeline failed for task %s", task_id)
            try:
                await self._repo.set_error(task_id, str(exc))
                await self._repo.transition(task_id, State.FAILED)
            except Exception:
                logger.exception("Failed to mark task %s as FAILED", task_id)

    async def _run_inner(self, task_id: str) -> None:
        task = await self._repo.get_task(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        role_description = sanitize_role_input(task["role_description"])
        special_requirements = sanitize_role_input(
            task.get("special_requirements") or ""
        )
        name_hint = task["name_hint"]

        slug = _slugify(name_hint)
        if slug in RESERVED_SLUGS:
            raise ValueError(f"Slug '{slug}' is reserved — choose a different name")

        existing = await self._repo.get_agent_by_slug(slug)
        if existing:
            raise ValueError(f"Slug '{slug}' already taken by an existing agent")

        # ── RESEARCHING ──────────────────────────────────────────
        await self._repo.transition(task_id, State.RESEARCHING)
        await self._broadcast(task_id, "researching", name_hint)

        factory_tool_names = self._tools.names_factory_allowed()
        report = await run_research(
            llm_client=self._llm,
            role_description=role_description,
            factory_tool_names=factory_tool_names,
            repo=self._repo,
        )

        report_id = uuid.uuid4().hex
        await self._repo.save_report(
            report_id=report_id,
            query_key=role_description.lower().strip(),
            report=report.model_dump(),
        )
        await self._repo.set_research_report(task_id, report_id)

        # ── DRAFTING_SPEC ────────────────────────────────────────
        await self._repo.transition(task_id, State.DRAFTING_SPEC)
        await self._broadcast(task_id, "drafting_spec", name_hint)

        write_spec_markdown(
            slug=slug,
            name=name_hint,
            role_description=role_description,
            special_requirements=special_requirements,
            report=report,
        )

        # ── WRITING_PROMPT ───────────────────────────────────────
        await self._repo.transition(task_id, State.WRITING_PROMPT)
        await self._broadcast(task_id, "writing_prompt", name_hint)

        system_prompt = await generate_system_prompt(
            llm_client=self._llm,
            name=name_hint,
            role_description=role_description,
            special_requirements=special_requirements,
            report=report,
        )

        manifest = {
            "slug": slug,
            "name": name_hint,
            "specialty": report.domain,
            "system_prompt": system_prompt,
            "tool_allowlist": report.tools_available,
            "model": model_config.default_model(),
        }
        await self._repo.set_proposed_manifest(task_id, manifest)

        # ── AWAITING_APPROVAL ────────────────────────────────────
        await self._repo.transition(task_id, State.AWAITING_APPROVAL)
        await self._broadcast(
            task_id, "awaiting_approval", name_hint,
            manifest=manifest,
            tools_wishlist=[w.model_dump() for w in report.tools_wishlist],
        )

    async def run_revision(self, task_id: str) -> None:
        """Re-run prompt generation after rejection with feedback.

        Only regenerates the system prompt (Tier 2) — research is cached.
        """
        try:
            await self._run_revision_inner(task_id)
        except Exception as exc:
            logger.exception("Revision failed for task %s", task_id)
            try:
                await self._repo.set_error(task_id, str(exc))
                await self._repo.transition(task_id, State.FAILED)
            except Exception:
                logger.exception("Failed to mark task %s as FAILED", task_id)

    async def _run_revision_inner(self, task_id: str) -> None:
        task = await self._repo.get_task(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        if task["status"] != State.WRITING_PROMPT.value:
            raise ValueError(f"Task not in writing_prompt state")

        manifest = task["proposed_manifest"]
        if not manifest:
            raise ValueError("No prior manifest to revise")

        report_row = None
        if task.get("research_report_id"):
            report_row = await self._repo.get_cached_report(
                task["role_description"].lower().strip()
            )
        if not report_row:
            raise ValueError("Research report not found for revision")

        report = SkillsReport(**report_row["report_json"])

        system_prompt = await generate_system_prompt(
            llm_client=self._llm,
            name=manifest["name"],
            role_description=task["role_description"],
            special_requirements=task.get("special_requirements") or "",
            report=report,
            prior_prompt=manifest["system_prompt"],
            revision_feedback=task["revision_feedback"],
        )

        manifest["system_prompt"] = system_prompt
        await self._repo.set_proposed_manifest(task_id, manifest)

        await self._repo.transition(task_id, State.AWAITING_APPROVAL)
        await self._broadcast(task_id, "awaiting_approval", manifest["name"])

    async def _broadcast(self, task_id, status, name, **extra):
        try:
            event = {"task_id": task_id, "status": status, "name": name, **extra}
            self._emit_event(kind="factory_update", event=event)
        except Exception:
            pass
