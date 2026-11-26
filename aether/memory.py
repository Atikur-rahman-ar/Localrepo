"""Session transcript + long-term notes, stored under the memory directory."""

from __future__ import annotations

import json
import time
from pathlib import Path


class Memory:
    def __init__(self, memory_dir: Path):
        self.dir = Path(memory_dir)
        (self.dir / "sessions").mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.session_path = self.dir / "sessions" / f"{stamp}.jsonl"
        self.notes_path = self.dir / "notes.md"

    # ------------------------------------------------------------- transcript
    def log(self, role: str, content: str) -> None:
        entry = {"ts": time.time(), "role": role, "content": content}
        with self.session_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------ notes
    def remember(self, fact: str) -> str:
        fact = fact.strip()
        if not fact:
            return "ERROR: empty fact."
        with self.notes_path.open("a", encoding="utf-8") as fh:
            fh.write(f"- [{time.strftime('%Y-%m-%d %H:%M')}] {fact}\n")
        return f"Remembered: {fact}"

    def recall(self, query: str = "") -> str:
        if not self.notes_path.exists():
            return "No notes stored yet."
        lines = self.notes_path.read_text(encoding="utf-8").splitlines()
        if query:
            needle = query.lower()
            lines = [ln for ln in lines if needle in ln.lower()]
        return "\n".join(lines) if lines else f"No notes matching '{query}'."

    def load_notes_into_context(self, max_chars: int = 1500) -> str:
        if not self.notes_path.exists():
            return ""
        return self.notes_path.read_text(encoding="utf-8")[-max_chars:]
