"""Agent loop: mock end-to-end run, planning, stop, repetition nudge."""

from __future__ import annotations

import json

from aether.agent import Agent


def test_mock_backend_full_run(config, memory, workspace, capsys):
    """The scripted mock backend must complete: write file, verify, report."""
    from aether.llm import LLMClient
    from aether.tools import build_default_tools

    registry = build_default_tools(config, memory)
    agent = Agent(config, LLMClient(config), registry, memory, color=False)
    events = []
    agent.on_event = events.append

    result = agent.run("run the demo", use_plan=False)
    assert "aether-demo.txt" in result
    assert (workspace / "aether-demo.txt").exists()
    kinds = [e["type"] for e in events]
    assert kinds[0] == "run_start" and kinds[-1] == "run_end"
    assert "tool_call" in kinds and "tool_result" in kinds


def test_plan_is_parsed_from_planner(config, memory, scripted_llm):
    from aether.tools import build_default_tools

    llm = scripted_llm([{"content": "1. do A\n2. do B\nnot a step", "tool_calls": None}])
    registry = build_default_tools(config, memory)
    agent = Agent(config, llm, registry, memory, color=False)
    agent.run("task", use_plan=True)
    # first call was the planner (no tools attached)
    assert llm.calls[0]["tools"] is None


def test_final_answer_without_tool_calls(config, memory, scripted_llm):
    from aether.tools import build_default_tools

    llm = scripted_llm([{"content": "All done.", "tool_calls": None}])
    registry = build_default_tools(config, memory)
    agent = Agent(config, llm, registry, memory, color=False)
    assert agent.run("task", use_plan=False) == "All done."


def test_stop_flag_halts_before_next_turn(config, memory, scripted_llm):
    from aether.tools import build_default_tools

    # loop forever: each reply repeats the same echo call
    forever = [{
        "content": "working...",
        "tool_calls": [{"id": "x", "name": "remember",
                        "arguments": json.dumps({"fact": "loop"})}],
    }]
    llm = scripted_llm(forever)
    registry = build_default_tools(config, memory)
    agent = Agent(config, llm, registry, memory, color=False)

    # stop after the first tool call
    original = agent.registry.call

    def stop_after_first(name, args):
        out = original(name, args)
        agent.request_stop()
        return out

    agent.registry.call = stop_after_first
    result = agent.run("loop forever", use_plan=False)
    assert agent.stop_flag.is_set()


def test_max_iterations_message(config, memory, scripted_llm):
    from aether.tools import build_default_tools

    forever = [{
        "content": "",
        "tool_calls": [{"id": "x", "name": "remember",
                        "arguments": json.dumps({"fact": "same"})}],
    }]
    config.max_iterations = 2
    llm = scripted_llm(forever)
    registry = build_default_tools(config, memory)
    agent = Agent(config, llm, registry, memory, color=False)
    result = agent.run("never finishes", use_plan=False)
    assert "Stopped after 2 iterations" in result


def test_identical_action_nudge_is_emitted(config, memory, scripted_llm):
    from aether.tools import build_default_tools

    same_call = {
        "content": "retrying",
        "tool_calls": [{"id": "x", "name": "recall", "arguments": "{}"}],
    }
    script = [same_call, same_call, same_call,
              {"content": "gave up sensibly", "tool_calls": None}]
    llm = scripted_llm(script)
    registry = build_default_tools(config, memory)
    events = []
    agent = Agent(config, llm, registry, memory, color=False, on_event=events.append)
    agent.run("repeat myself", use_plan=False)
    assert any(e["type"] == "loop_warning" for e in events), "nudge was not emitted"


def test_follow_up_continues_conversation(config, memory, scripted_llm):
    from aether.tools import build_default_tools

    llm = scripted_llm([{"content": "first", "tool_calls": None},
                        {"content": "second", "tool_calls": None}])
    registry = build_default_tools(config, memory)
    agent = Agent(config, llm, registry, memory, color=False)
    assert agent.run("task one", use_plan=False) == "first"
    assert agent.follow_up("and now?") == "second"
    roles = [m["role"] for m in agent.conversation]
    assert roles.count("user") == 2  # conversation kept growing


def test_observer_errors_never_break_the_loop(config, memory, scripted_llm):
    from aether.tools import build_default_tools

    def bad_observer(event):
        raise RuntimeError("observer is buggy")

    llm = scripted_llm([{"content": "done", "tool_calls": None}])
    registry = build_default_tools(config, memory)
    agent = Agent(config, llm, registry, memory, color=False, on_event=bad_observer)
    assert agent.run("task", use_plan=False) == "done"
