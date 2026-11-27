"""Config loading: defaults, YAML, env overrides, explicit overrides."""

from __future__ import annotations

import pytest

from aether.config import Config, load_config


def test_defaults():
    cfg = Config()
    assert cfg.provider == "openai_compatible"
    assert cfg.max_iterations == 40
    assert cfg.max_delegate_depth == 1
    assert cfg.delegate_max_iterations == 15
    assert cfg.custom_tools_dir == ""
    assert cfg.allow_outside_workspace is False


def test_workspace_resolution(config, workspace):
    assert config.resolved_workspace() == workspace.resolve()
    assert config.resolved_memory_dir() == workspace.resolve() / ".aether"


def test_memory_dir_override(workspace):
    cfg = Config(workspace=str(workspace), memory_dir=str(workspace / "mem"))
    assert cfg.resolved_memory_dir() == (workspace / "mem").resolve()


def test_yaml_roundtrip(tmp_path, workspace):
    path = tmp_path / "config.yaml"
    path.write_text(
        "provider: ollama\n"
        f"workspace: {workspace}\n"
        "max_iterations: 7\n"
        "max_delegate_depth: 2\n"
        "delegate_max_iterations: 5\n"
    )
    cfg = load_config(str(path))
    assert cfg.provider == "ollama"
    assert cfg.max_iterations == 7
    assert cfg.max_delegate_depth == 2
    assert cfg.delegate_max_iterations == 5


def test_env_overrides(tmp_path, workspace, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text("provider: mock\n")
    monkeypatch.setenv("AETHER_MAX_ITERATIONS", "9")
    monkeypatch.setenv("AETHER_MAX_DELEGATE_DEPTH", "3")
    monkeypatch.setenv("AETHER_DELEGATE_MAX_ITERATIONS", "4")
    monkeypatch.setenv("AETHER_AUTO_APPROVE", "1")
    cfg = load_config(str(path), workspace=str(workspace))
    assert cfg.max_iterations == 9
    assert cfg.max_delegate_depth == 3
    assert cfg.delegate_max_iterations == 4
    assert cfg.auto_approve is True


def test_explicit_overrides_beat_env(tmp_path, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text("provider: mock\n")
    monkeypatch.setenv("AETHER_MAX_ITERATIONS", "9")
    cfg = load_config(str(path), max_iterations=3)
    assert cfg.max_iterations == 3


def test_mock_provider_gets_placeholder_base_url(workspace):
    cfg = load_config(None, provider="mock", workspace=str(workspace))
    assert cfg.base_url == "mock://local"


def test_unknown_yaml_keys_are_ignored(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("provider: mock\nnonexistent_key: 42\n")
    cfg = load_config(str(path))  # must not raise
    assert cfg.provider == "mock"
