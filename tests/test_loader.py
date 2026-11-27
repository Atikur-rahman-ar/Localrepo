"""Custom tool loader: plugin discovery, overrides, resilience."""

from __future__ import annotations

from aether.memory import Memory
from aether.tools import build_default_tools, load_tools_from_dir
from aether.tools.base import Tool


PLUGIN_GOOD = '''
from aether.tools.base import Tool

class Shout(Tool):
    name = "shout"
    description = "Repeat a message in capital letters."
    parameters = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }

    def run(self, args):
        return args["text"].upper() + "!"
'''

PLUGIN_OVERRIDE = '''
from aether.tools.base import Tool

class Recall(Tool):
    name = "recall"
    description = "Custom recall that always says overridden."
    parameters = {"type": "object", "properties": {}, "required": []}

    def run(self, args):
        return "overridden"
'''

PLUGIN_BROKEN = '''
class Broken:  # no Tool subclass, and instantiating garbage below
    raise RuntimeError("this file is broken at import time")
'''


def _write_plugin(tmp_path, filename, source):
    folder = tmp_path / "plugins"
    folder.mkdir(exist_ok=True)
    (folder / filename).write_text(source, encoding="utf-8")
    return folder


def test_load_and_call_custom_tool(config, memory, tmp_path):
    folder = _write_plugin(tmp_path, "shout.py", PLUGIN_GOOD)
    registry = build_default_tools(config, memory)
    loaded = load_tools_from_dir(str(folder), registry)
    assert "shout" in loaded
    assert registry.call("shout", {"text": "registry mode works"}) == "REGISTRY MODE WORKS!"


def test_custom_tools_dir_config_wiring(config, memory, tmp_path):
    folder = _write_plugin(tmp_path, "shout.py", PLUGIN_GOOD)
    config.custom_tools_dir = str(folder)
    registry = build_default_tools(config, memory)
    assert "shout" in registry.tools


def test_custom_tool_overrides_builtin(config, memory, tmp_path):
    folder = _write_plugin(tmp_path, "override.py", PLUGIN_OVERRIDE)
    registry = build_default_tools(config, memory)
    load_tools_from_dir(str(folder), registry)
    assert registry.call("recall", {}) == "overridden"


def test_broken_plugin_is_skipped(config, memory, tmp_path):
    folder = _write_plugin(tmp_path, "broken.py", PLUGIN_BROKEN)
    _write_plugin(tmp_path, "shout.py", PLUGIN_GOOD)
    registry = build_default_tools(config, memory)
    loaded = load_tools_from_dir(str(folder), registry)  # must not raise
    assert "shout" in loaded and "broken" not in loaded


def test_underscore_files_are_skipped(config, memory, tmp_path):
    folder = _write_plugin(tmp_path, "_private.py", PLUGIN_GOOD)
    registry = build_default_tools(config, memory)
    loaded = load_tools_from_dir(str(folder), registry)
    assert "shout" not in loaded


def test_missing_folder_is_reported_not_fatal(tmp_path, capsys):
    from aether.tools.base import ToolRegistry

    reg = ToolRegistry()
    loaded = load_tools_from_dir(str(tmp_path / "nope"), reg)
    assert loaded == []
    assert "not found" in capsys.readouterr().err


def test_delegate_task_registered_only_within_depth(config, memory):
    config.max_delegate_depth = 1
    reg = build_default_tools(config, memory, delegate_depth=0)
    assert "delegate_task" in reg.tools
    # at the limit the tool is absent
    reg2 = build_default_tools(config, memory, delegate_depth=1)
    assert "delegate_task" not in reg2.tools
    # disabled entirely
    config.max_delegate_depth = 0
    reg3 = build_default_tools(config, memory, delegate_depth=0)
    assert "delegate_task" not in reg3.tools


def test_schema_of_delegate_tool(registry):
    # registry fixture uses max_delegate_depth=0, so build one with it enabled
    from aether.config import Config as C

    config = C(provider="mock", workspace="/tmp", max_delegate_depth=1)
    mem = Memory(config.resolved_memory_dir())
    reg = build_default_tools(config, mem)
    schema = reg.tools["delegate_task"].schema()
    assert schema["name"] == "delegate_task"
    assert "task" in schema["parameters"]["required"]
