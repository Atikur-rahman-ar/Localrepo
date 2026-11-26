"""The autonomous loop: plan, act (tool calls), observe, repeat, report."""

from __future__ import annotations

import json

from .config import Config
from .llm import LLMClient
from .memory import Memory
from .planner import make_plan
from .tools import ToolRegistry

SYSTEM_PROMPT = """You are Aether, a fully autonomous agent running on the user's machine.

Mission: complete the user's task end-to-end using the tools available to you.
You decide your own approach. Do not ask the user questions unless the task is
literally impossible without missing information.

Operating rules:
1. Think before acting: state what you are about to do and why (one short line).
2. Prefer tools over guessing. Verify outcomes (run tests, re-read files, check URLs).
3. Work inside the workspace directory. Keep files tidy and idiomatic.
4. Tool outputs are truncated; if you need more, re-read with line ranges.
5. If an approach fails twice, change strategy instead of repeating it.
6. Durable facts worth keeping (user preferences, project layout) go to `remember`.
7. When the task is fully done, reply with a concise final summary (no tool calls):
   what was done, key decisions, and anything the user should check."""

ANSI = {
    "reset": "\033[0m",
    "dim": "\033[2m",
    "cyan": "\033[36m",
    "green": "\033[32m",
    "yellow": "\033[33m",
}


def _canonical(arguments) -> str:
    try:
        if isinstance(arguments, str):
            return json.dumps(json.loads(arguments), sort_keys=True)
        return json.dumps(arguments, sort_keys=True)
    except Exception:  # noqa: BLE001
        return str(arguments)


class Agent:
    def __init__(
        self,
        config: Config,
        llm: LLMClient,
        registry: ToolRegistry,
        memory: Memory,
        color: bool = True,
    ):
        self.config = config
        self.llm = llm
        self.registry = registry
        self.memory = memory
        self.color = color
        self.conversation: list[dict] = []

    # ----------------------------------------------------------------- events
    def _say(self, text: str, color: str = "reset") -> None:
        if self.color:
            print(f"{ANSI.get(color, '')}{text}{ANSI['reset']}")
        else:
            print(text)

    def reset(self) -> None:
        self.conversation.clear()

    # --------------------------------------------------------------- seeding
    def _seed(self, task: str, plan: list[str]) -> None:
        self.reset()
        self.conversation.append({"role": "system", "content": SYSTEM_PROMPT})

        notes = self.memory.load_notes_into_context()
        if notes:
            self.conversation.append(
                {
                    "role": "system",
                    "content": "Long-term notes from previous sessions (may be relevant):\n" + notes,
                }
            )

        content = task
        if plan:
            checklist = "\n".join(f"{i}. {s}" for i, s in enumerate(plan, 1))
            content += f"\n\nSuggested plan (adapt freely if reality disagrees):\n{checklist}"
        self.conversation.append({"role": "user", "content": content})

    # ------------------------------------------------------------- single run
    def run(self, task: str, use_plan: bool = True) -> str:
        self.memory.log("user", task)
        self._say(f"\n[TASK] {task}", "cyan")

        plan = make_plan(self.llm, task) if use_plan else []
        if plan:
            self._say("[PLAN]", "dim")
            for i, step in enumerate(plan, 1):
                self._say(f"  {i}. {step}", "dim")

        self._seed(task, plan)
        return self._loop()

    # ------------------------------------------------------------- multi-turn
    def follow_up(self, message: str) -> str:
        """Continue the current conversation (REPL mode)."""
        self.memory.log("user", message)
        if not self.conversation:
            self._seed(message, plan=[])
        else:
            self.conversation.append({"role": "user", "content": message})
        return self._loop()

    # ------------------------------------------------------------ the loop
    def _loop(self) -> str:
        recent_actions: list[str] = []
        final_answer = ""

        for step in range(1, self.config.max_iterations + 1):
            reply = self.llm.chat(self.conversation, tools=self.registry.schemas())
            content = reply.get("content")
            tool_calls = reply.get("tool_calls")

            if content:
                self._say(f"[{step}] {content}", "dim")
                self.memory.log("assistant", content)

            if not tool_calls:
                final_answer = content or "(no response)"
                break

            self.conversation.append(
                {"role": "assistant", "content": content, "tool_calls": tool_calls}
            )

            for call in tool_calls:
                preview = str(call["arguments"])[:120]
                self._say(f"[{step}] {call['name']}({preview})", "yellow")

                result = self.registry.call(call["name"], call["arguments"])
                first_line = result.splitlines()[0][:160] if result else "(empty)"
                self._say(f"      -> {first_line}", "dim")
                self.memory.log("tool", f"{call['name']}: {result[:500]}")

                recent_actions.append(call["name"] + ":" + _canonical(call["arguments"]))

                self.conversation.append(
                    {"role": "tool", "tool_call_id": call["id"], "content": result}
                )

            if len(recent_actions) >= 3 and len(set(recent_actions[-3:])) == 1:
                self.conversation.append(
                    {
                        "role": "system",
                        "content": (
                            "You have repeated the identical action 3 times with no "
                            "progress. Change approach, gather the missing information "
                            "differently, or finish with your best result."
                        ),
                    }
                )
                recent_actions.clear()
        else:
            final_answer = (
                f"Stopped after {self.config.max_iterations} iterations. "
                "Raise --max-iterations or split the task into smaller pieces."
            )

        self.memory.log("final", final_answer)
        self._say(f"\n[RESULT]\n{final_answer}", "green")
        return final_answer
