def add_approval(task, brain_name):
    return {
        "description": f"Approval needed for {brain_name}: {task.description}"
    }
