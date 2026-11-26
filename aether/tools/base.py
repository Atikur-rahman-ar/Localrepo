"""Tool base class and registry."""

from __future__ import annotations

import json
import traceback


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [output truncated, {len(text) - limit} chars dropped]"


class Tool:
    """A callable capability exposed to the model.

    Subclasses define ``name``, ``description``, ``parameters`` (a JSON Schema
    object) and implement ``run(args: dict) -> str``. The returned string is
    what the model sees.
    """

    name: str = "tool"
    description: str = ""
    parameters: dict = {"type": "object", "properties": {}, "required": []}

    def run(self, args: dict) -> str:  # pragma: no cover - overridden
        raise NotImplementedError

    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


class ToolRegistry:
    def __init__(self, max_output: int = 8000):
        self.tools: dict[str, Tool] = {}
        self.max_output = max_output

    def register(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def schemas(self) -> list[dict]:
        return [t.schema() for t in self.tools.values()]

    def call(self, name: str, arguments: str | dict) -> str:
        tool = self.tools.get(name)
        if tool is None:
            return f"ERROR: unknown tool '{name}'. Available: {', '.join(self.tools)}"

        if isinstance(arguments, str):
            try:
                args = json.loads(arguments) if arguments.strip() else {}
            except json.JSONDecodeError as exc:
                return f"ERROR: arguments for '{name}' are not valid JSON: {exc}"
        else:
            args = arguments

        try:
            result = tool.run(args)
        except Exception as exc:  # noqa: BLE001 - errors go back to the model
            result = f"ERROR: {exc.__class__.__name__}: {exc}\n{traceback.format_exc(limit=2)}"
        return truncate(str(result), self.max_output)
