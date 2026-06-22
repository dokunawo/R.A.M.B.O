# rambo-backend/agents/pilot.py

from models.task import Task
import uuid

class Pilot:
    def build_task_queue(self, goal, plan):
        tasks = []
        for step in plan:
            tasks.append(
                Task(
                    id=str(uuid.uuid4()),
                    description=step,
                    assigned_to=None,
                    status="pending",
                    metadata={"goal": goal},
                )
            )
        return tasks

    def execute(self, task):
        return f"[Pilot] Managing task: {task.description}"
