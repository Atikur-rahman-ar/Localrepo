"""Shared fixtures and helpers for the Aether test suite."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# Make the repo root importable when running from a source checkout.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from aether.config import Config  # noqa: E402
from aether.memory import Memory  # noqa: E402
from aether.tools import build_default_tools  # noqa: E402


@pytest.fixture()
def workspace(tmp_path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


@pytest.fixture()
def config(workspace) -> Config:
    """Offline-friendly config: mock provider, tight workspace, no delegation."""
    return Config(
        provider="mock",
        workspace=str(workspace),
        max_delegate_depth=0,  # tests opt back in explicitly
        auto_approve=True,
        allow_outside_workspace=False,
    )


@pytest.fixture()
def memory(config) -> Memory:
    return Memory(config.resolved_memory_dir())


@pytest.fixture()
def registry(config, memory):
    return build_default_tools(config, memory)


class ScriptedLLM:
    """Duck-typed stand-in for LLMClient: replays scripted replies.

    ``script`` is a list of reply dicts ({"content": ..., "tool_calls": ...});
    each chat() call pops the next one, repeating the last entry forever.
    Records every (messages, tools) pair it saw.
    """

    def __init__(self, script):
        self.script = list(script)
        self.calls: list[dict] = []

    def chat(self, messages, tools=None):
        self.calls.append({"messages": messages, "tools": tools})
        if not self.script:
            return {"content": "(no scripted reply)", "tool_calls": None}
        reply = self.script.pop(0)
        if self.script == []:
            self.script.append(reply)  # repeat last reply
        return json.loads(json.dumps(reply))  # deep copy


@pytest.fixture()
def scripted_llm():
    def factory(script):
        return ScriptedLLM(script)

    return factory
