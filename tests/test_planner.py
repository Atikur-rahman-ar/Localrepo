"""Planner: checklist parsing and graceful failure."""

from __future__ import annotations

from aether.planner import make_plan


class FakeLLM:
    def __init__(self, reply=None, exc=None):
        self.reply = reply
        self.exc = exc
        self.called_with = None

    def chat(self, messages, tools=None):
        self.called_with = messages
        if self.exc:
            raise self.exc
        return self.reply


def test_numbered_lines_are_parsed():
    llm = FakeLLM({"content": "1. First step\n2. Second step\n3) Third\nrandom line\n4. Fourth"})
    plan = make_plan(llm, "do the thing")
    assert plan == ["First step", "Second step", "Third", "Fourth"]


def test_prompt_is_sent_as_system_plus_task():
    llm = FakeLLM({"content": "1. x"})
    make_plan(llm, "the task")
    roles = [m["role"] for m in llm.called_with]
    assert roles == ["system", "user"]
    assert "the task" in llm.called_with[1]["content"]


def test_llm_failure_means_no_plan():
    llm = FakeLLM(exc=RuntimeError("backend down"))
    assert make_plan(llm, "task") == []


def test_empty_reply_means_no_plan():
    assert make_plan(FakeLLM({"content": ""}), "task") == []


def test_plan_capped_at_ten_steps():
    lines = "\n".join(f"{i}. step {i}" for i in range(1, 16))
    plan = make_plan(FakeLLM({"content": lines}), "task")
    assert len(plan) == 10
