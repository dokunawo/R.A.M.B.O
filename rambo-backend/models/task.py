class Task:
    def __init__(self, description, id=None, assigned_to=None,
                 status="pending", metadata=None):
        self.id = id
        self.description = description
        self.assigned_to = assigned_to
        self.status = status
        self.metadata = metadata or {}
