"""ToolRegistry: unknown tools, bad JSON, truncation, error capture."""

from __future__ import annotations

from aether.tools.base import Tool, ToolRegistry


class Boom(Tool):
    name = "boom"
    description = "always raises"
    parameters = {"type": "object", "properties": {}, "required": []}

    def run(self, args):
        raise ValueError("kaboom")


class Echo(Tool):
    name = "echo"
    description = "echoes text"
    parameters = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}

    def run(self, args):
        return args["text"]


def test_unknown_tool_lists_available():
    reg = ToolRegistry()
    reg.register(Echo())
    out = reg.call("nope", {})
    assert out.startswith("ERROR: unknown tool 'nope'")
    assert "echo" in out


def test_bad_json_arguments():
    reg = ToolRegistry()
    reg.register(Echo())
    out = reg.call("echo", "{not json")
    assert out.startswith("ERROR: arguments for 'echo' are not valid JSON")


def test_tool_exception_is_captured_not_raised():
    reg = ToolRegistry()
    reg.register(Boom())
    out = reg.call("boom", {})
    assert out.startswith("ERROR: ValueError: kaboom")
    assert "kaboom" in out


def test_output_truncation():
    reg = ToolRegistry(max_output=50)
    reg.register(Echo())
    out = reg.call("echo", {"text": "x" * 500})
    assert len(out) < 200
    assert "truncated" in out


def test_str_and_dict_arguments_equivalent():
    reg = ToolRegistry()
    reg.register(Echo())
    import json

    assert reg.call("echo", json.dumps({"text": "hi"})) == reg.call("echo", {"text": "hi"}) == "hi"


def test_schemas_shape():
    reg = ToolRegistry()
    reg.register(Echo())
    (schema,) = reg.schemas()
    assert schema["name"] == "echo"
    assert "description" in schema and "parameters" in schema
