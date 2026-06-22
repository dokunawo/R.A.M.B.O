# rambo-backend/agents/architect.py

class Architect:
    def create_plan(self, goal: str):
        goal_lower = goal.lower()

        steps = [f"Clarify goal: {goal}"]

        if "dashboard" in goal_lower or "hud" in goal_lower:
            steps += [
                "Identify required data sources and APIs",
                "Define UI sections and components",
                "Specify backend endpoints needed",
                "Outline success criteria and test cases",
            ]
        elif "integration" in goal_lower or "notion" in goal_lower or "slack" in goal_lower:
            steps += [
                "Identify external service and auth method",
                "Define data to sync and sync direction",
                "Design API contract and error handling",
                "Plan logging and monitoring for integration",
            ]
        else:
            steps += [
                "Break goal into 3–5 concrete tasks",
                "Assign each task to the most suitable brain",
                "Define what 'done' looks like for each task",
            ]

        return steps

    def execute(self, task):
        return f"[Architect] Planning: {task.description}"
