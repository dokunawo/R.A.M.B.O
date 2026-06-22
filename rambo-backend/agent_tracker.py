from datetime import datetime

_stats = {}
_activity = {}
_learnings = []

BUDGET_DATA = {
    "total_budget": 5000.00,
    "total_spent": 3247.50,
    "categories": [
        {"name": "Cloud Hosting", "budgeted": 1500.00, "spent": 1320.00},
        {"name": "API Services", "budgeted": 800.00, "spent": 645.50},
        {"name": "Data Storage", "budgeted": 600.00, "spent": 482.00},
        {"name": "Monitoring", "budgeted": 400.00, "spent": 350.00},
        {"name": "External Data", "budgeted": 700.00, "spent": 250.00},
        {"name": "Miscellaneous", "budgeted": 1000.00, "spent": 200.00},
    ],
}


def _ensure(agent_key):
    if agent_key not in _stats:
        _stats[agent_key] = {"tasks_completed": 0, "tasks_pending": 0, "success_rate": "100%"}
    if agent_key not in _activity:
        _activity[agent_key] = []


def record_task_start(agent_key, description):
    _ensure(agent_key)
    _stats[agent_key]["tasks_pending"] += 1
    _activity[agent_key].insert(0, {
        "time": datetime.utcnow().strftime("%H:%M:%S"),
        "text": description,
        "status": "pending",
    })
    if len(_activity[agent_key]) > 20:
        _activity[agent_key] = _activity[agent_key][:20]


def record_task_end(agent_key, description, success=True):
    _ensure(agent_key)
    s = _stats[agent_key]
    s["tasks_pending"] = max(0, s["tasks_pending"] - 1)
    s["tasks_completed"] += 1
    total = s["tasks_completed"]
    failed = sum(1 for a in _activity[agent_key] if a["status"] == "failed")
    s["success_rate"] = f"{round((total - failed) / total * 100)}%" if total else "100%"
    for a in _activity[agent_key]:
        if a["text"] == description and a["status"] == "pending":
            a["status"] = "completed" if success else "failed"
            a["time"] = datetime.utcnow().strftime("%H:%M:%S")
            break


def get_detail(agent_key):
    _ensure(agent_key)
    result = dict(_stats[agent_key])
    result["recent_activity"] = _activity.get(agent_key, [])[:10]
    if agent_key == "steward":
        result["budget"] = BUDGET_DATA
    return result


def add_learning(text, source="System", category="General"):
    _learnings.insert(0, {
        "text": text,
        "source": source,
        "category": category,
        "time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
    })
    if len(_learnings) > 50:
        _learnings[:] = _learnings[:50]


def get_learnings():
    return list(_learnings)
