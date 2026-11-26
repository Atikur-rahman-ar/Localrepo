"""Run Python code in a subprocess for math, data crunching and quick scripts."""

from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path

from .base import Tool


class ExecutePython(Tool):
    name = "execute_python"
    description = (
        "Execute Python 3 code and get stdout/stderr back. Use for math, data "
        "processing, quick experiments and generating files."
    )
    parameters = {
        "type": "object",
        "properties": {
            "code": {"type": "string"},
            "timeout": {"type": "integer", "description": "Seconds (default 60, max 300)."},
        },
        "required": ["code"],
    }

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace)

    def run(self, args: dict) -> str:
        code = str(args.get("code", ""))
        if not code.strip():
            return "ERROR: 'code' is required."
        timeout = min(int(args.get("timeout") or 60), 300)

        tmp = self.workspace / f".aether_pyexec_{uuid.uuid4().hex[:8]}.py"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(code, encoding="utf-8")
        try:
            proc = subprocess.run(
                [sys.executable, str(tmp)],
                cwd=str(self.workspace),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return f"ERROR: execution timed out after {timeout}s."
        finally:
            tmp.unlink(missing_ok=True)

        parts = []
        if proc.stdout:
            parts.append(f"stdout:\n{proc.stdout.strip()}")
        if proc.stderr:
            parts.append(f"stderr:\n{proc.stderr.strip()}")
        parts.append(f"exit_code: {proc.returncode}")
        return "\n---\n".join(parts)
