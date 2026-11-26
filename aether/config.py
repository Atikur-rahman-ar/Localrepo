"""Configuration loading: YAML file + environment variable overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


@dataclass
class Config:
    provider: str = "openai_compatible"  # "openai_compatible" | "ollama"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.7
    max_iterations: int = 40
    auto_approve: bool = False
    workspace: str = "."
    max_tool_output: int = 8000
    memory_dir: str = ""  # defaults to <workspace>/.aether
    allow_outside_workspace: bool = False

    def resolved_workspace(self) -> Path:
        return Path(self.workspace).expanduser().resolve()

    def resolved_memory_dir(self) -> Path:
        if self.memory_dir:
            return Path(self.memory_dir).expanduser().resolve()
        return self.resolved_workspace() / ".aether"


_ENV_OVERRIDES = {
    "provider": "AETHER_PROVIDER",
    "base_url": "AETHER_BASE_URL",
    "api_key": "AETHER_API_KEY",
    "model": "AETHER_MODEL",
    "max_iterations": "AETHER_MAX_ITERATIONS",
    "auto_approve": "AETHER_AUTO_APPROVE",
    "workspace": "AETHER_WORKSPACE",
}


def load_config(path: str | None = None, **overrides) -> Config:
    """Merge config.yaml < environment variables < explicit overrides."""
    data: dict = {}
    if path:
        if yaml is None:
            raise RuntimeError("PyYAML is required for YAML configs: pip install pyyaml")
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}

    cfg = Config()
    for key, value in data.items():
        if hasattr(cfg, key) and value is not None:
            setattr(cfg, key, value)

    for attr, env in _ENV_OVERRIDES.items():
        raw = os.environ.get(env)
        if raw:
            current = getattr(cfg, attr)
            if isinstance(current, bool):
                setattr(cfg, attr, raw.lower() in ("1", "true", "yes", "on"))
            elif isinstance(current, int):
                setattr(cfg, attr, int(raw))
            else:
                setattr(cfg, attr, raw)

    for key, value in overrides.items():
        if value is not None and hasattr(cfg, key):
            setattr(cfg, key, value)

    if not cfg.base_url:
        cfg.base_url = (
            "http://localhost:11434"
            if cfg.provider == "ollama"
            else "https://api.z.ai/api/paas/v4"
        )
    if not cfg.model:
        cfg.model = "llama3.1" if cfg.provider == "ollama" else "glm-4.7-flash"

    return cfg
