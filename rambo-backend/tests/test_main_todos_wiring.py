# rambo-backend/tests/test_main_todos_wiring.py
from fastapi.testclient import TestClient
import main


def test_todos_routes_mounted():
    with TestClient(main.app) as client:
        r = client.get("/todos")
        assert r.status_code == 200   # repo initialized by the startup event


def test_todos_repo_shared_with_skill():
    import todos_skill
    with TestClient(main.app):
        assert todos_skill.get_repo() is not None
