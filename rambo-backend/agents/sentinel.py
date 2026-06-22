# rambo-backend/agents/sentinel.py
class Sentinel:
    def review_task(self, task):
        text = task.description.lower()
        if "delete" in text or "wipe" in text:
            return {"status": "DENY", "reason": "Sentinel blocked destructive action."}
        if "payment" in text or "transfer" in text:
            return {"status": "REVIEW", "reason": "Sentinel requires approval for financial action."}
        return {"status": "ALLOW"}

    def execute(self, task):
        return f"[Sentinel] Monitoring: {task.description}"
