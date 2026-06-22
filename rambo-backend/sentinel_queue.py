import uuid
from datetime import datetime

_queue = []
_history = []


def add_approval(task, brain_name):
    entry = {
        "id": str(uuid.uuid4()),
        "agent": brain_name.capitalize(),
        "description": f"Approval needed for {brain_name}: {task.description}",
        "status": "PENDING",
        "created": datetime.utcnow().isoformat(),
    }
    _queue.append(entry)
    return entry


def list_approvals():
    return [a for a in _queue if a["status"] == "PENDING"]


def decide(approval_id, decision):
    for a in _queue:
        if a["id"] == approval_id:
            a["status"] = decision
            a["decided"] = datetime.utcnow().isoformat()
            _history.append(dict(a))
            return True
    return False


def get_history():
    return list(_history)
