"""Multi-agent handoffs: the agent can delegate subtasks to sub-agents.

``delegate_task`` spawns a child :class:`~aether.agent.Agent` with a fresh
conversation, its own iteration budget and the same toolbelt (minus further
delegation once the configured depth limit is reached). The child runs to
completion synchronously; its final answer becomes the tool output the parent
sees.

Guard rails:
- ``max_delegate_depth`` (default 1): how many nesting levels are allowed.
  0 disables the tool entirely; 1 means the top-level agent may delegate but
  sub-agents may not delegate further.
- ``delegate_max_iterations`` (default 15): smaller loop budget for children,
  so a delegation can never run longer than the parent itself.
- The parent's stop flag is shared: stopping a run also stops any in-flight
  sub-agent.
- Sub-agent events are forwarded to observers (Web UI) as ``delegate_event``
  payloads so delegation stays visible in the dashboard.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .base import Tool

_PROVIDER_LABEL = {
    "openai_compatible": "openai-compatible",
    "ollama": "ollama",
    "mock": "mock",
}


class DelegateTool(Tool):
    """Run a self-contained subtask in a fresh sub-agent and return its result."""

    name = "delegate_task"
    description = (
        "Spawn a sub-agent to complete a self-contained subtask with its own fresh "
        "context and toolbelt. Ideal for focused pieces of work you can hand off "
        "completely - e.g. 'research X and summarise it', 'draft file Y', 'fix the "
        "failing tests in module Z'. Give a crisp, complete task description plus any "
        "background the sub-agent cannot see (it does NOT share your conversation). "
        "The sub-agent's final report is returned as the tool result."
    )
    parameters = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "Complete, self-contained description of the subtask.",
            },
            "context": {
                "type": "string",
                "description": "Optional background facts, file paths or constraints "
                "the sub-agent needs but cannot discover on its own.",
            },
            "use_plan": {
                "type": "boolean",
                "description": "Let the sub-agent make an explicit plan first "
                "(default false; usually not needed for focused subtasks).",
            },
        },
        "required": ["task"],
    }

    def __init__(
        self,
        config,  # aether.config.Config
        memory,  # aether.memory.Memory (shared with the parent)
        depth: int = 1,  # this tool's children will run at this depth
        parent_stop_flag=None,  # threading.Event from the parent agent
        parent_on_event=None,  # observer callable from the parent agent
    ):
        self.config = config
        self.memory = memory
        self.depth = depth
        self._stop_flag = parent_stop_flag
        self._on_event = parent_on_event

    # ------------------------------------------------------------------ events
    def bind_agent(self, agent) -> None:
        """Called by Agent.__init__: receive the owning agent's stop flag and
        event observer so sub-agents stream into the same dashboard and stop
        together with the parent."""
        self._stop_flag = agent.stop_flag
        self._on_event = agent.on_event

    def _forward(self, event: dict) -> None:
        if self._on_event is None:
            return
        try:
            self._on_event({"type": "delegate_event", "depth": self.depth, "event": event})
        except Exception:  # noqa: BLE001 - observation must not break execution
            pass

    # ---------------------------------------------------------------- execution
    def run(self, args: dict) -> str:
        task = str(args.get("task", "")).strip()
        if not task:
            return "ERROR: 'task' is required and cannot be empty."
        context = str(args.get("context", "")).strip()
        use_plan = bool(args.get("use_plan", False))

        # Lazy imports: the tools package imports this module, so importing it
        # at module level would be circular.
        from ..agent import Agent
        from ..config import Config
        from ..llm import LLMClient, LLMError
        from . import build_default_tools

        if not isinstance(self.config, Config):  # pragma: no cover - defensive
            return "ERROR: delegate_task was constructed with an invalid config."

        sub_config = replace(
            self.config,
            max_iterations=self.config.delegate_max_iterations,
        )

        llm = LLMClient(sub_config)
        registry = build_default_tools(sub_config, self.memory, delegate_depth=self.depth)

        child = Agent(
            sub_config,
            llm,
            registry,
            self.memory,
            color=False,
            on_event=self._forward,
        )
        # Share the parent's stop flag: stopping the run stops the whole tree.
        if self._stop_flag is not None:
            child.stop_flag = self._stop_flag

        prompt = task
        if context:
            prompt += f"\n\nBackground from the parent agent:\n{context}"

        provider = _PROVIDER_LABEL.get(sub_config.provider, sub_config.provider)
        try:
            result = child.run(prompt, use_plan=use_plan)
        except LLMError as exc:
            return (
                f"ERROR: sub-agent could not reach its LLM backend "
                f"(provider={provider}): {exc}"
            )
        except Exception as exc:  # noqa: BLE001 - errors go back to the model
            return f"ERROR: sub-agent failed: {exc.__class__.__name__}: {exc}"

        if child.stop_flag.is_set():
            return (
                f"Sub-agent stopped before finishing (user requested stop). "
                f"Partial report:\n{result}"
            )

        return f"[sub-agent result, depth {self.depth}]\n{result}"


def workspace_label(config) -> str:
    """Human-readable workspace path for prompt/docs use."""
    ws: Path = config.resolved_workspace()
    return str(ws)
