"""Aether live Web UI (optional: pip install flask).

The server module imports Flask at module level, so we expose it lazily:
importing ``aether.web`` alone never requires Flask, and ``python -m
aether.web`` can print a friendly install hint instead of a traceback.
"""

from __future__ import annotations

__all__ = ["RunManager", "create_app"]


def __getattr__(name: str):
    if name in ("RunManager", "create_app"):
        from .server import RunManager, create_app

        return {"RunManager": RunManager, "create_app": create_app}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
