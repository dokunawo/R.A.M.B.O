class Keeper:
    """Memory specialist. Persistence is handled by the orchestrator's async
    Keeper handler (KeeperRepo); this sync stub is only a fallback if that
    handler isn't wired."""

    def __init__(self, store=None):
        self.store = store

    def execute(self, task):
        return f"[Keeper] Memory task noted (no store wired): {task.description}"
