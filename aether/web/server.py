"""Live Web UI for Aether: watch the agent plan, act and report in real time.

Run with:  python -m aether.web --workspace <dir> [--provider mock]
Then open: http://127.0.0.1:5000

The server is a local dashboard (binds to 127.0.0.1 by default). It is meant
for one user on their own machine; do not expose it to the public internet.
Set AETHER_WEB_TOKEN to require a shared token on every API call.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

from ..agent import Agent
from ..config import Config, load_config
from ..llm import LLMClient
from ..memory import Memory
from ..tools import build_default_tools

STATIC_DIR = Path(__file__).parent / "static"

# Tool results longer than this are trimmed before reaching the browser.
EVENT_RESULT_LIMIT = 6000


@dataclass
class RunState:
    run_id: str
    task: str
    status: str = "running"  # running | done | stopped | error
    created_at: float = field(default_factory=time.time)
    events: list[dict] = field(default_factory=list)
    result: str = ""
    error: str = ""
    agent: Agent | None = None
    cond: threading.Condition = field(default_factory=threading.Condition)

    def emit(self, event: dict) -> None:
        with self.cond:
            self.events.append(event)
            self.cond.notify_all()

    def finish(self, status: str, *, result: str = "", error: str = "") -> None:
        with self.cond:
            self.status = status
            self.result = result or self.result
            self.error = error
            self.cond.notify_all()


class RunManager:
    """Owns every run started through the Web UI (one thread per run)."""

    def __init__(self, base_config: Config, keep_last: int = 200):
        self.base = base_config
        self.keep_last = keep_last
        self.runs: dict[str, RunState] = {}
        self.order: list[str] = []
        self.lock = threading.Lock()

    # ------------------------------------------------------------------ start
    def start(self, task: str, overrides: dict | None = None) -> str:
        overrides = {k: v for k, v in (overrides or {}).items() if v not in (None, "")}
        cfg = replace(self.base, **overrides) if overrides else self.base

        state = RunState(run_id=uuid.uuid4().hex[:12], task=task)
        # NOTE: no run_start event here - Agent.run() emits it once the
        # thread is up; emitting twice would duplicate the task card in the UI.

        with self.lock:
            self.runs[state.run_id] = state
            self.order.append(state.run_id)
            # Prune old finished runs so the process stays small.
            while len(self.order) > self.keep_last:
                old_id = self.order[0]
                old = self.runs.get(old_id)
                if old is not None and old.status == "running":
                    break
                self.order.pop(0)
                self.runs.pop(old_id, None)

        threading.Thread(
            target=self._execute,
            args=(state, cfg),
            daemon=True,
            name=f"aether-{state.run_id}",
        ).start()
        return state.run_id

    # ---------------------------------------------------------------- execute
    def _execute(self, state: RunState, cfg: Config) -> None:
        try:
            llm = LLMClient(cfg)
            memory = Memory(cfg.resolved_memory_dir())
            registry = build_default_tools(cfg, memory)
            agent = Agent(cfg, llm, registry, memory, color=False, on_event=state.emit)
            state.agent = agent

            result = agent.run(state.task)
            status = "stopped" if agent.stop_flag.is_set() else "done"
            state.finish(status, result=result)
        except Exception as exc:  # noqa: BLE001 - report the failure to the browser
            message = f"{exc.__class__.__name__}: {exc}"
            state.emit({"type": "run_error", "message": message})
            state.finish("error", error=message)

    # ------------------------------------------------------------------- stop
    def stop(self, run_id: str) -> bool:
        state = self.runs.get(run_id)
        if state is None or state.agent is None or state.status != "running":
            return False
        state.agent.request_stop()
        return True

    # ------------------------------------------------------------------ query
    def get(self, run_id: str) -> RunState | None:
        return self.runs.get(run_id)

    def summary(self) -> list[dict]:
        with self.lock:
            states = [self.runs[r] for r in reversed(self.order) if r in self.runs]
        return [
            {
                "run_id": s.run_id,
                "task": s.task,
                "status": s.status,
                "created_at": s.created_at,
                "event_count": len(s.events),
            }
            for s in states
        ]


# ---------------------------------------------------------------- trimming
def _trim(event: dict) -> dict:
    """Cap oversized tool results before they reach the browser."""
    if event.get("type") == "tool_result" and len(event.get("result", "")) > EVENT_RESULT_LIMIT:
        event = dict(event)
        dropped = len(event["result"]) - EVENT_RESULT_LIMIT
        event["result"] = (
            event["result"][:EVENT_RESULT_LIMIT] + f"\n... [{dropped} chars trimmed for display]"
        )
    return event


# --------------------------------------------------------------- SSE stream
def _sse_stream(state: RunState) -> Response:
    def generate():
        idx = 0  # late subscribers replay everything that already happened
        while True:
            with state.cond:
                while idx >= len(state.events) and state.status == "running":
                    state.cond.wait(timeout=15)
                    if idx >= len(state.events):
                        yield ": keep-alive\n\n"
                fresh = state.events[idx:]
                idx = len(state.events)
                finished = state.status != "running"

            for event in fresh:
                yield f"data: {json.dumps(_trim(event), ensure_ascii=False)}\n\n"

            if finished:
                tail = {"status": state.status}
                if state.error:
                    tail["error"] = state.error
                yield f"event: end\ndata: {json.dumps(tail)}\n\n"
                return

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ------------------------------------------------------------ Flask factory
def create_app(config_path: str | None = None, **config_overrides) -> Flask:
    base = load_config(config_path, **config_overrides)
    manager = RunManager(base)
    token = os.environ.get("AETHER_WEB_TOKEN", "")

    app = Flask("aether", static_folder=None)

    def authorized() -> bool:
        """When AETHER_WEB_TOKEN is set, every call must present it."""
        if not token:
            return True
        supplied = request.headers.get("X-Aether-Token") or request.args.get("token")
        if not supplied and request.is_json:
            supplied = (request.get_json(silent=True) or {}).get("token")
        return supplied == token

    def guard():
        if not authorized():
            return (
                jsonify(
                    {
                        "error": "unauthorized: present AETHER_WEB_TOKEN "
                        "as ?token=, X-Aether-Token header, or token field"
                    }
                ),
                401,
            )
        return None

    # ------------------------------------------------------------------ pages
    @app.get("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.get("/static/<path:filename>")
    def static_files(filename: str):
        return send_from_directory(STATIC_DIR, filename)

    # -------------------------------------------------------------------- API
    @app.get("/api/health")
    def health():
        blocked = guard()
        if blocked:
            return blocked
        from .. import __version__

        return jsonify(
            {
                "ok": True,
                "version": __version__,
                "provider": base.provider,
                "model": base.model,
                "workspace": str(base.resolved_workspace()),
                "secured": bool(token),
            }
        )

    @app.get("/api/tools")
    def tools():
        blocked = guard()
        if blocked:
            return blocked
        memory = Memory(base.resolved_memory_dir())
        registry = build_default_tools(base, memory)
        return jsonify(registry.schemas())

    @app.post("/api/runs")
    def create_run():
        blocked = guard()
        if blocked:
            return blocked
        body = request.get_json(silent=True) or {}
        task = str(body.get("task", "")).strip()
        if not task:
            return jsonify({"error": "task is required"}), 400
        if len(task) > 20_000:
            return jsonify({"error": "task is too long (max 20000 chars)"}), 400
        overrides = {
            key: body.get(key)
            for key in ("provider", "base_url", "model", "max_iterations", "temperature")
        }
        run_id = manager.start(task, overrides)
        return jsonify({"run_id": run_id, "status": "running"}), 201

    @app.get("/api/runs")
    def list_runs():
        blocked = guard()
        if blocked:
            return blocked
        return jsonify({"runs": manager.summary()})

    @app.get("/api/runs/<run_id>")
    def get_run(run_id: str):
        blocked = guard()
        if blocked:
            return blocked
        state = manager.get(run_id)
        if state is None:
            return jsonify({"error": "unknown run"}), 404
        with state.cond:
            return jsonify(
                {
                    "run_id": state.run_id,
                    "task": state.task,
                    "status": state.status,
                    "created_at": state.created_at,
                    "result": state.result,
                    "error": state.error,
                    "events": [_trim(e) for e in state.events],
                }
            )

    @app.post("/api/runs/<run_id>/stop")
    def stop_run(run_id: str):
        blocked = guard()
        if blocked:
            return blocked
        ok = manager.stop(run_id)
        return jsonify({"ok": ok}), (200 if ok else 409)

    @app.get("/api/stream/<run_id>")
    def stream(run_id: str):
        blocked = guard()
        if blocked:
            return blocked
        state = manager.get(run_id)
        if state is None:
            return jsonify({"error": "unknown run"}), 404
        return _sse_stream(state)

    return app
