"""
Web API Integration Tests - PR-Review Agent
Test all API endpoints
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Create test client with isolated task manager"""
    # Patch output dir to temp
    import src.web.routes_task as rt
    rt._manager = None
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))

    from src.web_app import app
    from src.web.routes_task import get_manager
    # Override manager
    import src.web.routes_task as mod
    from src.scheduler.task_manager import WebTaskManager
    mod._manager = WebTaskManager(output_dir=str(tmp_path))

    return TestClient(app)


class TestHealthEndpoint:
    def test_health(self, client):
        res = client.get("/api/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"


class TestTaskEndpoints:
    def test_create_task_simple(self, client):
        res = client.post("/api/tasks", json={
            "mode": "simple", "repo_path": ".", "base_commit": "HEAD", "target_commit": "HEAD",
        })
        assert res.status_code == 200
        data = res.json()
        assert "task_id" in data
        assert data["mode"] == "simple"

    def test_list_tasks(self, client):
        # Create a task first
        client.post("/api/tasks", json={"mode": "simple", "repo_path": "."})
        res = client.get("/api/tasks")
        assert res.status_code == 200
        data = res.json()
        assert "tasks" in data
        assert "stats" in data

    def test_get_task(self, client):
        create_res = client.post("/api/tasks", json={"mode": "simple", "repo_path": "."})
        task_id = create_res.json()["task_id"]
        res = client.get(f"/api/tasks/{task_id}")
        assert res.status_code == 200
        assert res.json()["task_id"] == task_id

    def test_get_nonexistent_task(self, client):
        res = client.get("/api/tasks/nonexistent")
        assert res.status_code == 404

    def test_delete_task(self, client):
        create_res = client.post("/api/tasks", json={"mode": "simple"})
        task_id = create_res.json()["task_id"]
        res = client.delete(f"/api/tasks/{task_id}")
        assert res.status_code == 200
        # Verify deleted
        res = client.get(f"/api/tasks/{task_id}")
        assert res.status_code == 404

    def test_restart_task(self, client):
        create_res = client.post("/api/tasks", json={"mode": "simple"})
        task_id = create_res.json()["task_id"]
        res = client.post(f"/api/tasks/{task_id}/restart")
        assert res.status_code == 200
        new_data = res.json()
        assert new_data["task_id"] != task_id


class TestReportEndpoints:
    def test_get_findings_not_found(self, client):
        create_res = client.post("/api/tasks", json={"mode": "simple"})
        task_id = create_res.json()["task_id"]
        res = client.get(f"/api/tasks/{task_id}/findings")
        assert res.status_code == 404

    def test_get_report_not_found(self, client):
        create_res = client.post("/api/tasks", json={"mode": "simple"})
        task_id = create_res.json()["task_id"]
        res = client.get(f"/api/tasks/{task_id}/report")
        assert res.status_code == 404

    def test_get_transcript_empty(self, client):
        create_res = client.post("/api/tasks", json={"mode": "simple"})
        task_id = create_res.json()["task_id"]
        res = client.get(f"/api/tasks/{task_id}/transcript")
        assert res.status_code == 200
        assert res.json()["total"] == 0


class TestConfigEndpoints:
    def test_read_config(self, client):
        res = client.get("/api/config")
        assert res.status_code == 200
        data = res.json()
        assert "mimo" in data
        assert "embedding" in data
        # Keys should be masked
        assert "***" in data["mimo"]["api_key"]

    def test_update_config(self, client):
        res = client.put("/api/config", json={"mimo_model_name": "test-model"})
        assert res.status_code == 200
        assert "updated" in res.json()
