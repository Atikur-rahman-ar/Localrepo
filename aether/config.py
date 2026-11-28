"""Configuration loading: YAML file + environment variable overrides.

Config sources, lowest to highest precedence:
  defaults < ~/.aether/config.yaml (per-user file, written by `aether --setup`)
           < explicit --config file < environment variables < CLI overrides
"""

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
    provider: str = "openai_compatible"  # "openai_compatible" | "ollama" | "mock"
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
    custom_tools_dir: str = ""  # folder with user-defined Tool plugins (optional)
    max_delegate_depth: int = 1  # 0 disables delegate_task; N allows N levels of sub-agents
    delegate_max_iterations: int = 15  # loop budget for sub-agents spawned via delegate_task

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
    "custom_tools_dir": "AETHER_CUSTOM_TOOLS",
    "max_delegate_depth": "AETHER_MAX_DELEGATE_DEPTH",
    "delegate_max_iterations": "AETHER_DELEGATE_MAX_ITERATIONS",
}


def user_config_path() -> Path:
    """Per-user config file holding the result of the one-time setup wizard.

    ``~/.aether/config.yaml`` (``C:\\Users\\<name>\\.aether\\config.yaml`` on
    Windows). Read automatically when no explicit --config path is given.
    """
    return Path.home() / ".aether" / "config.yaml"


def _read_yaml(path: str) -> dict:
    if yaml is None:
        raise RuntimeError("PyYAML is required for YAML configs: pip install pyyaml")
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_config(path: str | None = None, **overrides) -> Config:
    """Merge config file < environment variables < explicit overrides.

    With ``path=None`` the per-user file ``~/.aether/config.yaml`` is used
    when it exists (created by ``aether --setup``); an explicit ``path``
    always wins over it. Environment variables and *overrides* top both.
    """
    data: dict = {}
    if path:
        data = _read_yaml(path)
    else:
        home = user_config_path()
        if home.exists():
            data = _read_yaml(str(home))

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
        if cfg.provider == "ollama":
            cfg.base_url = "http://localhost:11434"
        elif cfg.provider == "mock":
            cfg.base_url = "mock://local"  # never used; the backend is offline
        else:
            cfg.base_url = "https://api.z.ai/api/paas/v4"
    if not cfg.model:
        cfg.model = (
            "llama3.1"
            if cfg.provider == "ollama"
            else "aether-demo" if cfg.provider == "mock" else "glm-4.7-flash"
        )

    return cfg
