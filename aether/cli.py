"""Command line interface: one-shot tasks and an interactive REPL."""

from __future__ import annotations

import argparse
import sys

from .agent import Agent
from .config import load_config
from .llm import LLMClient, LLMError
from .memory import Memory
from .tools import build_default_tools

HELP = """Commands:
  <any text>           run it as the next instruction for the agent
  /reset               start a fresh conversation
  /notes               show long-term notes
  /forget              wipe long-term notes
  /tools               list available tools
  /help                this help
  /exit  (or Ctrl-D)   quit
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="aether", description="Aether - autonomous agent framework"
    )
    p.add_argument("task", nargs="*", help="task to run; omit to enter interactive mode")
    p.add_argument("--config", help="path to config.yaml")
    p.add_argument("--provider", choices=["openai_compatible", "ollama", "mock"])
    p.add_argument("--base-url", help="API root, e.g. https://api.z.ai/api/paas/v4")
    p.add_argument("--api-key")
    p.add_argument("--model")
    p.add_argument("--workspace", help="directory the agent operates in")
    p.add_argument("--max-iterations", type=int)
    p.add_argument("--auto", action="store_true", help="skip confirmation prompts (blocklist still applies)")
    p.add_argument("--no-plan", action="store_true", help="skip the planning step")
    p.add_argument("--no-color", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    config = load_config(
        args.config,
        provider=args.provider,
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model,
        workspace=args.workspace,
        max_iterations=args.max_iterations,
        auto_approve=True if args.auto else None,
    )

    try:
        llm = LLMClient(config)
        memory = Memory(config.resolved_memory_dir())
        registry = build_default_tools(config, memory)
        agent = Agent(config, llm, registry, memory, color=not args.no_color)
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to initialise Aether: {exc}", file=sys.stderr)
        return 1

    task = " ".join(args.task).strip()
    if task:
        try:
            agent.run(task, use_plan=not args.no_plan)
        except LLMError as exc:
            print(f"LLM error: {exc}", file=sys.stderr)
            return 2
        return 0

    # ------------------------------------------------------------------ REPL
    print("Aether interactive mode. Type /help for commands.")
    while True:
        try:
            line = input("\naether> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        if line in ("/exit", "/quit"):
            return 0
        if line == "/reset":
            agent.reset()
            print("Conversation cleared.")
            continue
        if line == "/notes":
            print(memory.recall())
            continue
        if line == "/forget":
            memory.notes_path.write_text("", encoding="utf-8")
            print("Notes wiped.")
            continue
        if line == "/tools":
            for schema in registry.schemas():
                print(f"- {schema['name']}: {schema['description'][:100]}")
            continue
        if line in ("/help", "/?"):
            print(HELP)
            continue
        try:
            agent.follow_up(line)
        except LLMError as exc:
            print(f"LLM error: {exc}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
