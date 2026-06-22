class Keeper:
    def __init__(self, store):
        self.store = store

    def execute(self, task):
        return f"[Keeper] Memory task: {task.description}"
