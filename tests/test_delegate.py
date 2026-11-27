"""Multi-agent handoffs: delegate_task end-to-end, depth limits, stop sharing."""

from __future__ import annotations

import json

from aether.agent import Agent
from aether.config import Config
from aether.memory import Memory
from aether.tools import build_default_tools


def _cfg(workspace, **kw) -> Config:
    return Config(
        provider="mock",
        workspace=str(workspace),
        auto_approve=True,
        **kw,
    )


def _delegate_script():
    """Parent script: delegate first, finalise second."""
    return [
        {
            "content": "Delegating the demo to a sub-agent.",
            "tool_calls": [
                {
                    "id": "c1",
                    "name": "delegate_task",
                    "arguments": json.dumps({
                        "task": "Run your demo: create the demo file and verify it.",
                        "context": "Workspace root is already set.",
                    }),
                }
            ],
        },
        {"content": "Parent done; sub-agent completed the demo.", "tool_calls": None},
    ]


def test_delegation_runs_sub_agent_and_returns_report(config, memory, scripted_llm, workspace):
    config.max_delegate_depth = 1
    config.delegate_max_iterations = 10
    registry = build_default_tools(config, memory)
    events = []
    parent = Agent(config, scripted_llm(_delegate_script()), registry, memory,
                   color=False, on_event=events.append)
    result = parent.run("Hand the demo off.", use_plan=False)

    # The sub-agent (mock backend) really wrote its demo file in the shared workspace
    assert (workspace / "aether-demo.txt").exists(), "sub-agent did not write the demo file"

    # The parent saw the sub-agent's report as the delegate_task tool result
    delegate_results = [
        e for e in events
        if e["type"] == "tool_result" and e["name"] == "delegate_task"
    ]
    assert delegate_results, "parent never received the sub-agent report"
    res = delegate_results[0]["result"]
    assert "sub-agent result" in res.lower()
    assert "mock backend" in res.lower()  # the mock demo's signature closing line

    assert result == "Parent done; sub-agent completed the demo."


def test_sub_agent_events_are_forwarded(config, memory, scripted_llm):
    config.max_delegate_depth = 1
    registry = build_default_tools(config, memory)
    events = []
    parent = Agent(config, scripted_llm(_delegate_script()), registry, memory,
                   color=False, on_event=events.append)
    parent.run("Hand off.", use_plan=False)
    wrapped = [e for e in events if e["type"] == "delegate_event"]
    assert wrapped, "sub-agent events were not forwarded to the observer"
    # wrapped payloads carry the nesting depth and the original event
    assert all(w["depth"] == 1 for w in wrapped)
    kinds = {w["event"]["type"] for w in wrapped}
    assert {"run_start", "run_end"} <= kinds
    tool_calls = [w for w in wrapped if w["event"]["type"] == "tool_call"]
    assert tool_calls and tool_calls[0]["event"]["name"] == "write_file"


def test_sub_agent_shares_parent_stop_flag(config, memory, scripted_llm):
    config.max_delegate_depth = 1
    registry = build_default_tools(config, memory)
    parent = Agent(config, scripted_llm(_delegate_script()), registry, memory, color=False)
    tool = registry.tools["delegate_task"]
    assert tool._stop_flag is parent.stop_flag, "stop flag was not shared with the sub-agent tool"


def test_depth_limit_one_prevents_nested_delegation(config, memory, workspace):
    """A sub-agent built at depth 1 must not offer delegate_task again."""
    config.max_delegate_depth = 1
    registry = build_default_tools(config, memory, delegate_depth=1)
    assert "delegate_task" not in registry.tools


def test_two_level_nesting_allowed(config, memory):
    config.max_delegate_depth = 2
    registry = build_default_tools(config, memory, delegate_depth=1)
    assert "delegate_task" in registry.tools


def test_empty_task_is_rejected(config, memory):
    from aether.tools.delegate import DelegateTool

    tool = DelegateTool(config, memory, depth=1)
    out = tool.run({"task": "  "})
    assert out.startswith("ERROR") and "task" in out


def test_delegate_tool_binds_agent(config, memory):
    from aether.tools.delegate import DelegateTool

    tool = DelegateTool(config, memory, depth=1)
    assert tool._stop_flag is None and tool._on_event is None
    # bind_agent hook (called by Agent.__init__ for every registry tool)
    config.max_delegate_depth = 1
    registry = build_default_tools(config, memory)
    agent = Agent(config, None, registry, memory, color=False)  # llm unused here
    bound = registry.tools["delegate_task"]
    assert bound._stop_flag is agent.stop_flag
    assert bound._on_event is agent.on_event
