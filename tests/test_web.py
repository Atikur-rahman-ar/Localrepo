"""Web UI: Flask test client against the real app factory + mock backend."""

from __future__ import annotations

import json
import time

import pytest

flask = pytest.importorskip("flask")

from aether.config import Config  # noqa: E402
from aether.web.server import create_app  # noqa: E402


@pytest.fixture()
def app(tmp_path):
    cfg = Config(
        provider="mock",
        workspace=str(tmp_path / "ws"),
        max_iterations=10,
        max_delegate_depth=1,
    )
    return create_app(None, **{
        "provider": "mock",
        "workspace": str(tmp_path / "ws"),
        "max_iterations": 10,
        "max_delegate_depth": 1,
    })


@pytest.fixture()
def client(app):
    return app.test_client()


def _wait_run(client, run_id, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"/api/runs/{run_id}").get_json()
        if data["status"] != "running":
            return data
        time.sleep(0.1)
    raise AssertionError("run did not finish in time")


def test_index_serves_dashboard(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"html" in r.data.lower()


def test_health(client):
    data = client.get("/api/health").get_json()
    assert data["ok"] is True
    assert data["provider"] == "mock"
    assert data["version"]


def test_tools_endpoint_lists_builtins(client):
    schemas = client.get("/api/tools").get_json()
    names = {s["name"] for s in schemas}
    assert "write_file" in names and "delegate_task" in names


def test_run_lifecycle_end_to_end(client, tmp_path):
    r = client.post("/api/runs", json={"task": "run the demo"})
    assert r.status_code in (200, 201)
    run_id = r.get_json()["run_id"]
    data = _wait_run(client, run_id)
    assert data["status"] == "done"
    assert "aether-demo.txt" in data["result"]
    kinds = [e["type"] for e in data["events"]]
    assert kinds[0] == "run_start" and kinds[-1] == "run_end"


def test_run_history_listing(client):
    run_id = client.post("/api/runs", json={"task": "history demo"}).get_json()["run_id"]
    _wait_run(client, run_id)
    runs = client.get("/api/runs").get_json()["runs"]
    assert any(r["run_id"] == run_id for r in runs)
    assert any(r["task"] == "history demo" for r in runs)


def test_token_guard(monkeypatch, tmp_path):
    monkeypatch.setenv("AETHER_WEB_TOKEN", "sekrit")
    cfg = Config(provider="mock", workspace=str(tmp_path / "ws"))
    app = create_app(None, workspace=str(tmp_path / "ws"), provider="mock")
    c = app.test_client()
    assert c.get("/api/health").status_code == 401
    assert c.get("/api/health?token=wrong").status_code == 401
    assert c.get("/api/health?token=sekrit").status_code == 200
    assert c.get("/api/health", headers={"X-Aether-Token": "sekrit"}).status_code == 200


def test_unknown_run_returns_404(client):
    assert client.get("/api/runs/nonexistent").status_code == 404


def test_delegate_task_available_in_web_registry(client):
    schemas = client.get("/api/tools").get_json()
    delegate = [s for s in schemas if s["name"] == "delegate_task"]
    assert delegate and "task" in delegate[0]["parameters"]["required"]
