"""Read/write REST surface for the to-do list, sharing the same TodosRepo instance
the voice skill uses (todos_skill.get_repo()/set_repo()) — a voice-added task and a
panel-added task are the same data."""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import todos_skill

router = APIRouter(prefix="/todos", tags=["todos"])


class NewTodo(BaseModel):
    text: str
    priority: str = "normal"
    due: Optional[str] = None
    recurrence: Optional[str] = None


def _repo():
    repo = todos_skill.get_repo()
    if repo is None:
        raise HTTPException(status_code=503, detail="Todos repo not configured")
    return repo


@router.get("")
async def list_todos() -> list[dict]:
    return await _repo().list_open()


@router.post("")
async def create_todo(body: NewTodo) -> dict:
    return await _repo().add(body.text, priority=body.priority, due=body.due,
                             recurrence=body.recurrence, source="api")


@router.post("/{task_id}/complete")
async def complete_todo(task_id: int) -> dict:
    row = await _repo().complete(task_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return row


@router.delete("/{task_id}")
async def delete_todo(task_id: int) -> dict:
    ok = await _repo().delete(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"deleted": task_id}
