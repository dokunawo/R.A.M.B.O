from models.task import Task, BrainName

def choose_brain(task: Task) -> BrainName:
    text = task.description.lower()

    if "plan" in text or "steps" in text:
        return "architect"
    if "build" in text or "code" in text or "api" in text:
        return "engineer"
    if "search" in text or "look up" in text or "compare" in text:
        return "seeker"
    if "analyze" in text or "trend" in text:
        return "analyst"
    if "budget" in text or "money" in text:
        return "steward"
    if "integration" in text or "oauth" in text:
        return "link"
    if "memory" in text or "history" in text:
        return "keeper"
    if "summary" in text or "tone" in text:
        return "echo"
    if "queue" in text or "task" in text:
        return "pilot"

    return "echo"
