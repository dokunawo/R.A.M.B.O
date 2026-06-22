# rambo-backend/agents/echo.py

class Echo:
    def summarize(self, goal, plan, results):
        lines = []
        lines.append(f"🎯 Goal")
        lines.append(f"  {goal}")
        lines.append("")
        lines.append("🧩 Plan")
        for step in plan:
            lines.append(f"  • {step}")
        lines.append("")
        lines.append("📡 Execution Log")
        for r in results:
            lines.append(f"  • {r}")
        return "\n".join(lines)

    def execute(self, task):
        return f"[Echo] Polishing: {task.description}"
