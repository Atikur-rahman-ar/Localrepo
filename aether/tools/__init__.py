"""Default toolbelt assembly."""

from __future__ import annotations

from ..config import Config
from ..memory import Memory
from .base import Tool, ToolRegistry
from .data import RenderChart, RunSqlite
from .files import EditFile, ListDir, ReadFile, WriteFile
from .knowledge import SearchArxiv, SearchGitHub, SearchWikipedia
from .net import DownloadFile, HttpRequest
from .python_exec import ExecutePython
from .shell import RunCommand
from .web import FetchURL, WebSearch

__all__ = ["Tool", "ToolRegistry", "build_default_tools"]


class RememberTool(Tool):
    name = "remember"
    description = "Store a durable fact or preference in long-term notes for future sessions."
    parameters = {
        "type": "object",
        "properties": {"fact": {"type": "string"}},
        "required": ["fact"],
    }

    def __init__(self, memory: Memory):
        self.memory = memory

    def run(self, args: dict) -> str:
        return self.memory.remember(str(args.get("fact", "")))


class RecallTool(Tool):
    name = "recall"
    description = "Search your long-term notes. Pass a query to filter, or none to list all."
    parameters = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": [],
    }

    def __init__(self, memory: Memory):
        self.memory = memory

    def run(self, args: dict) -> str:
        return self.memory.recall(str(args.get("query", "")).strip())


def build_default_tools(config: Config, memory: Memory) -> ToolRegistry:
    """Instantiate every built-in tool. Add custom tools here."""
    registry = ToolRegistry(max_output=config.max_tool_output)
    workspace = config.resolved_workspace()

    registry.register(RunCommand(workspace, auto_approve=config.auto_approve))
    registry.register(ReadFile(workspace, allow_outside=config.allow_outside_workspace))
    registry.register(WriteFile(workspace, allow_outside=config.allow_outside_workspace))
    registry.register(EditFile(workspace, allow_outside=config.allow_outside_workspace))
    registry.register(ListDir(workspace, allow_outside=config.allow_outside_workspace))
    registry.register(ExecutePython(workspace))
    registry.register(WebSearch())
    registry.register(FetchURL())
    registry.register(HttpRequest())
    registry.register(DownloadFile(workspace, allow_outside=config.allow_outside_workspace))
    registry.register(SearchWikipedia())
    registry.register(SearchArxiv())
    registry.register(SearchGitHub())
    registry.register(RunSqlite(workspace, allow_outside=config.allow_outside_workspace))
    registry.register(RenderChart(workspace, allow_outside=config.allow_outside_workspace))
    registry.register(RememberTool(memory))
    registry.register(RecallTool(memory))
    return registry
