"""Auto-load user-defined tools from a folder of plain Python files.

Point ``custom_tools_dir`` (or the AETHER_CUSTOM_TOOLS environment variable)
at a directory; every ``*.py`` file in it is imported and any ``Tool``
subclass found at module level is instantiated and registered. This lets you
drop a new capability into the folder without touching Aether's source.

Example ``my_tools.py``:

    from aether.tools.base import Tool

    class Shout(Tool):
        name = "shout"
        description = "Repeat a message in capital letters."
        parameters = {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        }

        def run(self, args: dict) -> str:
            return args["text"].upper() + "!"

Notes:
- Files whose name starts with ``_`` are skipped.
- A tool whose ``name`` collides with an existing one replaces it
  (handy for overriding built-ins deliberately).
- A class failing to instantiate is reported and skipped; the rest still load.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import List

from .base import Tool, ToolRegistry


def load_tools_from_dir(directory: str | Path, registry: ToolRegistry) -> List[str]:
    """Import every plugin file in ``directory`` and register the tools found.

    Returns the names of tools that were actually registered.
    """
    folder = Path(directory).expanduser()
    if not folder.is_dir():
        print(f"[aether] custom tools dir not found: {folder}", file=sys.stderr)
        return []

    registered: List[str] = []
    for path in sorted(folder.glob("*.py")):
        if path.name.startswith("_"):
            continue
        module_name = f"aether_plugins_{path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                raise ImportError(f"cannot load {path.name}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module  # allow plugin-internal imports
            spec.loader.exec_module(module)
        except Exception as exc:  # noqa: BLE001 - one bad file must not kill startup
            print(f"[aether] skipped plugin {path.name}: {exc}", file=sys.stderr)
            continue

        for attr in dir(module):
            obj = getattr(module, attr)
            if (
                isinstance(obj, type)
                and issubclass(obj, Tool)
                and obj.__module__ == module_name  # only classes defined here
            ):
                try:
                    instance = obj()
                    if not instance.name or instance.name == "tool":
                        raise ValueError("tool has no usable 'name'")
                    registry.register(instance)
                    registered.append(instance.name)
                except Exception as exc:  # noqa: BLE001
                    print(
                        f"[aether] plugin class {obj.__name__} in {path.name} skipped: {exc}",
                        file=sys.stderr,
                    )
    return registered
