"""Shell execution with a hard blocklist for catastrophic commands."""

from __future__ import annotations

import re
import subprocess

from .base import Tool

SYSTEM_PREFIXES = (
    "/usr", "/etc", "/var", "/bin", "/sbin", "/boot",
    "/dev", "/proc", "/sys", "/lib", "/opt", "/root",
)

CONFIRM_PATTERNS = [
    r"\bgit\s+push\b",
    r"\b(curl|wget)\b[^|]*\|\s*(sudo\s+)?(ba|z|da)?sh\b",
    r"\bsudo\b",
    r"\bapt(-get)?\s+(install|remove|purge|upgrade)\b",
    r"\bpip\s+install\b",
    r"\bnpm\s+(install|i)\b",
    r"\bdocker\b",
]


def _has_recursive_rm(command: str) -> bool:
    if not re.search(r"\brm\s", command):
        return False
    if not re.search(r"(?:^|\s)-{1,2}[a-z]*r|\s--recursive\b", command, re.I):
        return False
    for tok in command.split()[1:]:
        tok = tok.strip("'\"")
        if tok.startswith("-"):
            continue
        if tok in ("/", "~", "$HOME", "/*", "~/*", "$HOME/*", "${HOME}", "${HOME}/*"):
            return True
        if tok.startswith(SYSTEM_PREFIXES) or tok.startswith("~/"):
            return True
    return False


def _catastrophic_reason(command: str) -> str | None:
    """Return a reason string if this command must never run, else None."""
    if re.search(r":\(\)\s*\{\s*:\|:\s*&\s*\}\s*;\s*:", command):
        return "fork bomb"
    if re.search(r"\b(mkfs|shutdown|reboot|halt|poweroff|init\s+[06])\b", command):
        return "filesystem or power operation"
    if re.search(r"\bdd\b[^;|&]*of=/dev/(sd|hd|nvme|vd|mmcblk)", command):
        return "raw disk write (dd)"
    if re.search(r">\s*/dev/(sd[a-z]|nvme|vd[a-z])", command):
        return "direct disk overwrite"
    if re.search(
        r"\b(chmod|chown)\s+-R\s+\S+\s+/(usr|etc|var|bin|sbin|boot|lib|opt)(/|\s|$)",
        command,
    ):
        return "recursive permission change on a system directory"
    if _has_recursive_rm(command):
        return "recursive delete of a system or home root"
    return None


class RunCommand(Tool):
    name = "run_command"
    description = (
        "Run a shell command inside the workspace and get stdout, stderr and the "
        "exit code. Use for builds, git, package managers, tests, ffmpeg, etc."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The shell command to execute."},
            "timeout": {"type": "integer", "description": "Seconds to wait (default 120, max 600)."},
        },
        "required": ["command"],
    }

    def __init__(self, workspace, auto_approve: bool = False):
        self.workspace = workspace
        self.auto_approve = auto_approve

    def run(self, args: dict) -> str:
        command = str(args.get("command", "")).strip()
        if not command:
            return "ERROR: 'command' is required."
        timeout = min(int(args.get("timeout") or 120), 600)

        reason = _catastrophic_reason(command)
        if reason:
            return (
                f"BLOCKED ({reason}): Aether never executes destructive system "
                "commands - this protects your machine even in full-auto mode. "
                "Rephrase the task safely."
            )

        needs_confirm = any(re.search(p, command) for p in CONFIRM_PATTERNS)
        if needs_confirm and not self.auto_approve:
            answer = input(
                f"\n[Aether] potentially impactful command:\n  $ {command}\nApprove? [y/N] "
            ).strip().lower()
            if answer not in ("y", "yes"):
                return "DENIED by user. Choose a different approach or finish."

        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=str(self.workspace),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return f"ERROR: command timed out after {timeout}s."

        parts = []
        if proc.stdout:
            parts.append(f"stdout:\n{proc.stdout.strip()}")
        if proc.stderr:
            parts.append(f"stderr:\n{proc.stderr.strip()}")
        parts.append(f"exit_code: {proc.returncode}")
        return "\n---\n".join(parts)
