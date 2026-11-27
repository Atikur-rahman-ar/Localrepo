"""File tools: CRUD inside the workspace, sandbox enforcement, edit semantics."""

from __future__ import annotations

import pytest


def _tool(reg, name):
    return reg.tools[name]


def test_registry_has_expected_builtin_tools(registry):
    expected = {
        "run_command", "read_file", "write_file", "edit_file", "list_dir",
        "execute_python", "web_search", "fetch_url", "http_request",
        "download_file", "search_wikipedia", "search_arxiv", "search_github",
        "run_sqlite", "render_chart", "remember", "recall",
        "send_email", "create_calendar_event",
    }
    assert expected <= set(registry.tools)


def test_write_and_read_roundtrip(registry):
    assert "Wrote" in registry.call("write_file", {"path": "a.txt", "content": "hello"})
    out = registry.call("read_file", {"path": "a.txt"})
    assert "hello" in out


def test_edit_requires_unique_old_text(registry):
    registry.call("write_file", {"path": "b.txt", "content": "one two one"})
    out = registry.call("edit_file", {"path": "b.txt", "old_text": "one", "new_text": "X"})
    assert out.startswith("ERROR") and "2 times" in out
    ok = registry.call("edit_file", {"path": "b.txt", "old_text": "two", "new_text": "X"})
    assert not ok.startswith("ERROR")
    assert "one X one" in registry.call("read_file", {"path": "b.txt"})


def test_read_missing_file(registry):
    assert registry.call("read_file", {"path": "ghost.txt"}).startswith("ERROR")


def test_list_dir(registry):
    registry.call("write_file", {"path": "sub/item.txt", "content": "x"})
    out = registry.call("list_dir", {"path": "."})
    assert "sub" in out


def test_path_escape_is_blocked(registry, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    out = registry.call("read_file", {"path": str(outside)})
    assert out.startswith("ERROR") and "outside the workspace" in out


def test_traversal_escape_is_blocked(registry):
    out = registry.call("read_file", {"path": "../../../etc/passwd"})
    assert out.startswith("ERROR")


def test_write_allows_absolute_inside_workspace(registry, workspace):
    target = workspace / "abs.txt"
    out = registry.call("write_file", {"path": str(target), "content": "ok"})
    assert not out.startswith("ERROR")
    assert target.exists()


def test_run_sqlite_read_and_write(registry):
    import sqlite3

    db = "data.db"
    # the tool never creates databases - seed one first
    with sqlite3.connect(str(registry.tools["run_sqlite"].workspace / db)) as conn:
        conn.execute("CREATE TABLE t (id INTEGER, name TEXT)")
    registry.call("run_sqlite", {
        "path": db, "sql": "INSERT INTO t VALUES (1, 'ada')", "mode": "write",
    })
    out = registry.call("run_sqlite", {"path": db, "sql": "SELECT * FROM t"})
    assert "ada" in out
    # read-only default: DDL must fail
    out = registry.call("run_sqlite", {"path": db, "sql": "DROP TABLE t"})
    assert out.startswith("ERROR")


def test_run_sqlite_never_creates_db(registry):
    out = registry.call("run_sqlite", {"path": "missing.db", "sql": "SELECT 1"})
    assert out.startswith("ERROR") and "does not exist" in out


def test_execute_python_sandbox(registry):
    out = registry.call("execute_python", {"code": "print(6 * 7)"})
    assert "42" in out


def test_remember_recall_tools(registry, memory):
    assert "Remembered" in registry.call("remember", {"fact": "project uses uv"})
    assert "uv" in registry.call("recall", {})
