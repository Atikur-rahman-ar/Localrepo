"""One-time setup wizard + per-user config store (~/.aether/config.yaml)."""

from __future__ import annotations

import types
from pathlib import Path

import pytest

from aether import config as aconfig
from aether import onboarding
from aether.config import Config, load_config
from aether.onboarding import SetupRequired, ensure_api_key, needs_key, save_user_config


@pytest.fixture()
def home_config(tmp_path, monkeypatch) -> Path:
    """Redirect the per-user config store into a tmp dir for the test."""
    target = tmp_path / "aether-home" / "config.yaml"
    monkeypatch.setattr(aconfig, "user_config_path", lambda: target)
    return target


def _tty(is_tty: bool, monkeypatch) -> None:
    monkeypatch.setattr("sys.stdin", types.SimpleNamespace(isatty=lambda: is_tty))


# --------------------------------------------------------------- needs_key
def test_needs_key_by_provider():
    assert needs_key(Config(provider="openai_compatible"))
    assert not needs_key(Config(provider="openai_compatible", api_key="sk-x"))
    assert not needs_key(Config(provider="ollama"))
    assert not needs_key(Config(provider="mock"))


# ------------------------------------------------------ per-user config IO
def test_home_config_is_picked_up(home_config):
    save_user_config(
        {
            "provider": "openai_compatible",
            "api_key": "sk-home",
            "base_url": "https://api.z.ai/api/paas/v4",
            "model": "glm-4.7-flash",
        }
    )
    cfg = load_config()
    assert cfg.api_key == "sk-home"
    assert cfg.provider == "openai_compatible"
    assert cfg.model == "glm-4.7-flash"
    assert not needs_key(cfg)


def test_env_var_still_overrides_home(home_config, monkeypatch):
    save_user_config(
        {"provider": "openai_compatible", "api_key": "sk-home",
         "base_url": "https://x", "model": "m"}
    )
    monkeypatch.setenv("AETHER_API_KEY", "sk-env")
    assert load_config().api_key == "sk-env"


def test_explicit_config_file_wins_over_home(home_config, tmp_path):
    save_user_config(
        {"provider": "openai_compatible", "api_key": "sk-home",
         "base_url": "https://x", "model": "m"}
    )
    project = tmp_path / "config.yaml"
    project.write_text(
        "provider: openai_compatible\napi_key: sk-project\n"
        "base_url: https://y\nmodel: mm\n",
        encoding="utf-8",
    )
    assert load_config(str(project)).api_key == "sk-project"


def test_missing_home_file_leaves_defaults(home_config):
    cfg = load_config(provider="mock")
    assert cfg.provider == "mock"
    assert cfg.api_key == ""


# ------------------------------------------------------------------ wizard
def test_configured_config_passes_through(home_config, monkeypatch):
    # must never touch stdin, even when stdin is not a tty
    _tty(False, monkeypatch)
    cfg = Config(provider="openai_compatible", api_key="sk-x")
    assert ensure_api_key(cfg) is cfg


def test_non_interactive_gets_instructions(home_config, monkeypatch):
    _tty(False, monkeypatch)
    with pytest.raises(SetupRequired) as excinfo:
        ensure_api_key(Config())
    text = str(excinfo.value)
    assert "aether --setup" in text
    assert "AETHER_API_KEY" in text
    assert not home_config.exists()


def test_wizard_zai_choice(home_config, monkeypatch):
    _tty(True, monkeypatch)
    monkeypatch.setattr("builtins.input", lambda *a, **k: "1")
    monkeypatch.setattr(onboarding.getpass, "getpass", lambda *a, **k: "  sk-zai-123  ")
    cfg = ensure_api_key(Config())
    assert cfg.api_key == "sk-zai-123"  # input is trimmed
    assert cfg.provider == "openai_compatible"
    assert cfg.base_url == "https://api.z.ai/api/paas/v4"
    assert cfg.model == "glm-4.7-flash"
    saved = home_config.read_text(encoding="utf-8")
    assert "sk-zai-123" in saved
    assert "api_key" in saved
    assert not needs_key(load_config())  # next load finds the saved key


def test_wizard_ollama_choice(home_config, monkeypatch):
    _tty(True, monkeypatch)
    answers = iter(["3", ""])
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(answers))
    cfg = ensure_api_key(Config())
    assert cfg.provider == "ollama"
    assert cfg.model == "llama3.1"
    assert cfg.base_url == "http://localhost:11434"
    assert not needs_key(cfg)
    assert "ollama" in home_config.read_text(encoding="utf-8")


def test_wizard_mock_choice_saves_nothing(home_config, monkeypatch):
    _tty(True, monkeypatch)
    monkeypatch.setattr("builtins.input", lambda *a, **k: "4")
    cfg = ensure_api_key(Config())
    assert cfg.provider == "mock"
    assert cfg.api_key == ""
    assert not home_config.exists()


def test_wizard_custom_provider_requires_base_url(home_config, monkeypatch):
    _tty(True, monkeypatch)
    answers = iter(["2", "", "some-model"])  # empty base URL
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(answers))
    monkeypatch.setattr(onboarding.getpass, "getpass", lambda *a, **k: "sk-x")
    with pytest.raises(SetupRequired):
        ensure_api_key(Config())
    assert not home_config.exists()


def test_wizard_empty_key_aborts_without_saving(home_config, monkeypatch):
    _tty(True, monkeypatch)
    monkeypatch.setattr("builtins.input", lambda *a, **k: "1")
    monkeypatch.setattr(onboarding.getpass, "getpass", lambda *a, **k: "")
    with pytest.raises(SetupRequired):
        ensure_api_key(Config())
    assert not home_config.exists()


def test_force_setup_reconfigures(home_config, monkeypatch):
    _tty(True, monkeypatch)
    monkeypatch.setattr("builtins.input", lambda *a, **k: "1")
    monkeypatch.setattr(onboarding.getpass, "getpass", lambda *a, **k: "sk-new")
    cfg = Config(provider="openai_compatible", api_key="sk-old")
    assert ensure_api_key(cfg, force=True).api_key == "sk-new"
