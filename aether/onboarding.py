"""One-time onboarding: ask once for an API key, save it forever.

Aether deliberately does NOT bundle an API key: anything published to PyPI
is public, and keys embedded in public packages get scraped and abused
within hours. Instead the first interactive run walks the user through a
10-second wizard, stores their choice in the per-user config file
(``~/.aether/config.yaml``) and never asks again. Ollama and the mock
provider remain fully keyless.
"""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

from . import config as _config
from .config import Config

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML is a hard dependency
    yaml = None

MENU = """\
=== Aether one-time setup =================================================
Aether needs one API key from your LLM provider - this happens ONCE.
It will be saved to: {path}
and never asked again. (Change later: edit that file or run `aether --setup`.)

  [1] Z.ai - free glm-4.7-flash tier                  (recommended)
  [2] OpenRouter / Groq / Google AI Studio / any OpenAI-compatible API
  [3] Ollama - local model, no key, no internet needed
  [4] Offline mock demo - no key, this session only
==========================================================================="""

NOT_INTERACTIVE = """\
Aether needs an API key before it can call a real LLM provider.

Three ways to provide it (pick any one):
  1. One-time setup (recommended): run `aether --setup` in a terminal -
     the key is saved to ~/.aether/config.yaml and never asked again.
  2. Environment variable: set AETHER_API_KEY.
  3. Config file: put `api_key: "..."` in a config.yaml and pass it with
     --config. Or pick a keyless provider: `--provider ollama` (local, no
     key) or `--provider mock` (offline demo)."""


class SetupRequired(RuntimeError):
    """Raised when a non-interactive session cannot obtain an API key."""


def needs_key(cfg: Config) -> bool:
    """True when the config targets a real API but carries no key."""
    return cfg.provider == "openai_compatible" and not (cfg.api_key or "").strip()


def save_user_config(values: dict, path: Path | None = None) -> Path:
    """Persist wizard results to the per-user config file (creates dirs)."""
    target = path or _config.user_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# Aether per-user configuration - created by `aether --setup`.\n"
        "# Environment variables and CLI flags override these values.\n"
    )
    if yaml is not None:
        body = yaml.safe_dump(values, sort_keys=True, default_flow_style=False)
    else:  # pragma: no cover - PyYAML ships with every install
        body = "\n".join(f"{key}: {values[key]}" for key in sorted(values)) + "\n"
    target.write_text(header + body, encoding="utf-8")
    return target


def ensure_api_key(cfg: Config, *, force: bool = False) -> Config:
    """Return a Config ready for real runs, prompting at most once.

    Keyless providers and already-configured configs pass through untouched.
    With ``force`` (``aether --setup``) the wizard runs even when a key is
    already configured. Non-interactive sessions are never blocked - they
    get :class:`SetupRequired` with clear instructions instead.
    """
    if not force and not needs_key(cfg):
        return cfg

    if not sys.stdin.isatty():
        raise SetupRequired(NOT_INTERACTIVE)

    target = _config.user_config_path()
    print(MENU.format(path=target))

    choice = input("Choose [1]: ").strip() or "1"
    while choice not in ("1", "2", "3", "4"):
        choice = input("Choose 1, 2, 3 or 4: ").strip() or "1"

    if choice == "3":  # Ollama - local, keyless
        model = input("Ollama model [llama3.1]: ").strip() or "llama3.1"
        save_user_config({"provider": "ollama", "model": model}, target)
        cfg.provider = "ollama"
        cfg.base_url = "http://localhost:11434"
        cfg.api_key = ""
        cfg.model = model
        print(f"Saved to {target} - Ollama mode, no key needed. Happy hacking!")
        return cfg

    if choice == "4":  # offline mock demo, session only, nothing saved
        cfg.provider = "mock"
        cfg.base_url = "mock://local"
        cfg.api_key = ""
        cfg.model = "aether-demo"
        print("Offline mock demo for this session (nothing was saved).")
        return cfg

    if choice == "1":  # Z.ai
        label = "Z.ai"
        base_url = "https://api.z.ai/api/paas/v4"
        model = "glm-4.7-flash"
        print("Get a free key at https://z.ai (Open Platform -> API Keys).")
    else:  # choice == "2" - any other OpenAI-compatible provider
        label = "your provider"
        base_url = input("Base URL (e.g. https://openrouter.ai/api/v1): ").strip()
        model = input("Model name (e.g. deepseek/deepseek-chat-v3.1:free): ").strip()
        if not base_url or not model:
            raise SetupRequired(
                "Base URL and model are required for a custom provider - "
                "nothing was saved. Run `aether --setup` to retry."
            )

    key = (getpass.getpass(f"Paste your {label} API key (input hidden): ") or "").strip()
    if not key:
        raise SetupRequired(
            "No key entered - nothing was saved. Run `aether --setup` to retry."
        )

    save_user_config(
        {
            "provider": "openai_compatible",
            "base_url": base_url,
            "api_key": key,
            "model": model,
        },
        target,
    )
    cfg.provider = "openai_compatible"
    cfg.base_url = base_url
    cfg.api_key = key
    cfg.model = model
    print(f"Saved to {target} - you will never be asked again.")
    return cfg
