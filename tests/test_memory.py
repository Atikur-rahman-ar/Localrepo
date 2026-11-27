"""Memory: session transcript, long-term notes, recall."""

from __future__ import annotations

from aether.memory import Memory


def test_log_writes_session_jsonl(memory):
    memory.log("user", "hello")
    memory.log("assistant", "hi")
    text = memory.session_path.read_text(encoding="utf-8")
    assert '"role": "user"' in text
    assert '"role": "assistant"' in text
    assert "hello" in text


def test_remember_and_recall_roundtrip(memory):
    assert "Remembered" in memory.remember("The deploy key lives in vault X")
    assert "vault X" in memory.recall()
    assert "vault X" in memory.recall("deploy")
    assert memory.recall("nothing-matches-this") == "No notes matching 'nothing-matches-this'."


def test_remember_empty_fact_is_rejected(memory):
    assert memory.remember("   ").startswith("ERROR")


def test_recall_before_any_notes(memory):
    assert memory.recall() == "No notes stored yet."


def test_load_notes_into_context(memory):
    for i in range(5):
        memory.remember(f"fact number {i}")
    ctx = memory.load_notes_into_context(max_chars=40)
    assert len(ctx) <= 40
    assert "fact number 4" in ctx  # tail is kept


def test_directories_created(tmp_path):
    mem = Memory(tmp_path / "does" / "not" / "exist")
    assert (tmp_path / "does" / "not" / "exist" / "sessions").is_dir()
