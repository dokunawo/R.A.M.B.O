# rambo-backend/agents/engineer.py

class Engineer:
    def execute(self, task):
        desc = task.description.lower()
        if "endpoint" in desc or "api" in desc:
            return f"[Engineer] Designing and scaffolding API for: {task.description}"
        if "component" in desc or "ui" in desc:
            return f"[Engineer] Implementing frontend component for: {task.description}"
        if "database" in desc or "schema" in desc:
            return f"[Engineer] Designing data model for: {task.description}"
        return f"[Engineer] Implementing solution for: {task.description}"
