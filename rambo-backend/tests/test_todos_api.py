from fastapi import FastAPI
from fastapi.testclient import TestClient
import todos_skill
from todos_repo import TodosRepo
from api.todos import router


def _app(tmp_path):
    app = FastAPI()
    app.include_router(router)
    return app


def _client(tmp_path):
    import asyncio
    repo = TodosRepo(db_path=tmp_path / "api_todos.db")
    asyncio.run(repo.init_db())
    todos_skill.set_repo(repo)
    return TestClient(_app(tmp_path))


def test_get_todos_empty(tmp_path):
    client = _client(tmp_path)
    r = client.get("/todos")
    assert r.status_code == 200
    assert r.json() == []


def test_post_creates_todo(tmp_path):
    client = _client(tmp_path)
    r = client.post("/todos", json={"text": "call the vet", "priority": "high"})
    assert r.status_code == 200
    body = r.json()
    assert body["text"] == "call the vet"
    assert body["priority"] == "high"
    assert body["source"] == "api"
    r2 = client.get("/todos")
    assert len(r2.json()) == 1


def test_complete_endpoint(tmp_path):
    client = _client(tmp_path)
    created = client.post("/todos", json={"text": "buy milk"}).json()
    r = client.post(f"/todos/{created['id']}/complete")
    assert r.status_code == 200
    assert r.json()["status"] == "done"
    assert client.get("/todos").json() == []


def test_complete_missing_returns_404(tmp_path):
    client = _client(tmp_path)
    r = client.post("/todos/999/complete")
    assert r.status_code == 404


def test_delete_endpoint(tmp_path):
    client = _client(tmp_path)
    created = client.post("/todos", json={"text": "old idea"}).json()
    r = client.delete(f"/todos/{created['id']}")
    assert r.status_code == 200
    assert client.get("/todos").json() == []


def test_delete_missing_returns_404(tmp_path):
    client = _client(tmp_path)
    r = client.delete("/todos/999")
    assert r.status_code == 404
