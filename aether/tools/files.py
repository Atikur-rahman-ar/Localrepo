"""File tools, sandboxed to the workspace directory."""

from __future__ import annotations

from pathlib import Path

from .base import Tool

IGNORE_PARTS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".aether", ".idea", ".vscode",
}


def _looks_binary(chunk: bytes) -> bool:
    return b"\0" in chunk


class _WorkspaceTool(Tool):
    def __init__(self, workspace: Path, allow_outside: bool = False):
        self.workspace = Path(workspace).resolve()
        self.allow_outside = allow_outside

    def _resolve(self, raw: str) -> Path:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = self.workspace / p
        p = p.resolve()
        if not self.allow_outside and not p.is_relative_to(self.workspace):
            raise ValueError(
                f"Path '{raw}' is outside the workspace ({self.workspace}). "
                "Use paths inside the workspace."
            )
        return p


class ReadFile(_WorkspaceTool):
    name = "read_file"
    description = "Read a text file. Optionally limit to a line range."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "start_line": {"type": "integer"},
            "end_line": {"type": "integer"},
        },
        "required": ["path"],
    }

    def run(self, args: dict) -> str:
        path = self._resolve(str(args["path"]))
        if not path.exists():
            return f"ERROR: {path} does not exist."
        data = path.read_bytes()[:1_000_000]
        if _looks_binary(data[:2048]):
            return f"ERROR: {path} looks binary ({path.stat().st_size} bytes); not reading."
        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()
        start = max(int(args.get("start_line") or 1), 1)
        end = int(args.get("end_line") or len(lines))
        window = lines[start - 1 : end]
        numbered = [f"{start + i:5d}| {ln}" for i, ln in enumerate(window)]
        return f"{path} ({len(lines)} lines)\n" + "\n".join(numbered)


class WriteFile(_WorkspaceTool):
    name = "write_file"
    description = (
        "Create or overwrite a file with the given content. "
        "Parent directories are created automatically."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
    }

    def run(self, args: dict) -> str:
        path = self._resolve(str(args["path"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(args.get("content", "")), encoding="utf-8")
        return f"Wrote {path} ({path.stat().st_size} bytes)."


class EditFile(_WorkspaceTool):
    name = "edit_file"
    description = (
        "Replace an exact snippet in a file. old_text must appear exactly once; "
        "include enough surrounding context to make it unique."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "old_text": {"type": "string"},
            "new_text": {"type": "string"},
        },
        "required": ["path", "old_text", "new_text"],
    }

    def run(self, args: dict) -> str:
        path = self._resolve(str(args["path"]))
        if not path.exists():
            return f"ERROR: {path} does not exist."
        text = path.read_text(encoding="utf-8")
        old = str(args["old_text"])
        new = str(args["new_text"])
        count = text.count(old)
        if count == 0:
            return "ERROR: old_text not found (check whitespace and indentation)."
        if count > 1:
            return f"ERROR: old_text appears {count} times; make it unique or use write_file."
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        return f"Edited {path}."


class ListDir(_WorkspaceTool):
    name = "list_dir"
    description = "List files and folders under a path (defaults to the workspace root)."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "depth": {"type": "integer", "description": "Recursion depth (default 2, max 5)."},
        },
        "required": [],
    }

    def run(self, args: dict) -> str:
        root = self._resolve(str(args.get("path") or "."))
        if not root.exists():
            return f"ERROR: {root} does not exist."
        depth = min(int(args.get("depth") or 2), 5)
        out: list[str] = []
        for path in sorted(root.rglob("*")):
            rel = path.relative_to(root)
            if any(part in IGNORE_PARTS for part in rel.parts):
                continue
            if len(rel.parts) > depth:
                continue
            kind = "dir " if path.is_dir() else "file"
            size = f" ({path.stat().st_size}B)" if path.is_file() else "/"
            out.append(f"{kind} {rel}{size}")
            if len(out) >= 500:
                out.append("... [listing truncated]")
                break
        return "\n".join(out) or "(empty)"
