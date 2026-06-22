from models.task import Task

def choose_brain(task: Task) -> str:
    description = task.description.lower()

    if "analyze" in description:
        return "analyst"
    if "search" in description or "find" in description:
        return "seeker"
    if "build" in description or "create" in description:
        return "engineer"
    if "store" in description or "save" in description:
        return "keeper"
    if "summarize" in description:
        return "echo"

    return "architect"
