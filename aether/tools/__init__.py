"""Default toolbelt assembly."""

from __future__ import annotations

import os

from ..config import Config
from ..memory import Memory
from .base import Tool, ToolRegistry
from .data import RenderChart, RunSqlite
from .files import EditFile, ListDir, ReadFile, WriteFile
from .knowledge import SearchArxiv, SearchGitHub, SearchWikipedia
from .loader import load_tools_from_dir
from .net import DownloadFile, HttpRequest
from .productivity import CreateCalendarEvent, SendEmail
from .python_exec import ExecutePython
from .shell import RunCommand
from .web import FetchURL, WebSearch

__all__ = ["Tool", "ToolRegistry", "build_default_tools", "load_tools_from_dir"]


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


def build_default_tools(config: Config, memory: Memory, delegate_depth: int = 0) -> ToolRegistry:
    """Instantiate every built-in tool, then any custom tools from
    config.custom_tools_dir (or AETHER_CUSTOM_TOOLS).

    ``delegate_depth`` is the nesting level of the agent this registry is
    built for (0 = top-level). ``delegate_task`` is registered only while
    ``delegate_depth < config.max_delegate_depth``, so sub-agents cannot
    delegate beyond the configured limit.
    """
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
    registry.register(SendEmail())
    registry.register(CreateCalendarEvent(workspace))

    if config.max_delegate_depth > delegate_depth:
        from .delegate import DelegateTool

        registry.register(
            DelegateTool(
                config,
                memory,
                depth=delegate_depth + 1,
            )
        )

    custom_dir = config.custom_tools_dir or os.environ.get("AETHER_CUSTOM_TOOLS", "")
    if custom_dir:
        load_tools_from_dir(custom_dir, registry)
    return registry
