"""Optional planning step: decompose a task into an ordered checklist."""

from __future__ import annotations

import re

SYSTEM = (
    "You are a planning module inside an autonomous agent. Given a task, output a "
    "concise ordered checklist of concrete steps (max 10). One step per line, "
    "formatted as '1. ...'. No preamble, no explanation."
)


def make_plan(llm, task: str) -> list[str]:
    """Best-effort planning; any failure simply means 'no plan'."""
    try:
        reply = llm.chat(
            [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": task},
            ]
        )
    except Exception:  # noqa: BLE001 - planning must never block execution
        return []

    steps = []
    for line in (reply.get("content") or "").splitlines():
        match = re.match(r"^\d+[.)]\s*(.+)$", line.strip())
        if match:
            steps.append(match.group(1).strip())
    return steps[:10]
