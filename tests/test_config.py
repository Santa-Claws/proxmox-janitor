import tempfile
from pathlib import Path

import pytest
import yaml

from janitor.config import JanitorConfig, load_config


MINIMAL_CONFIG = {
    "proxmox_servers": [
        {
            "name": "test-pve",
            "host": "10.0.0.1",
            "user": "root@pam",
            "auth": {"method": "token", "token_name": "test", "token_value": "secret"},
        }
    ],
    "ai": {
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
        "api_key": "sk-test",
    },
}


def test_load_minimal_config():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(MINIMAL_CONFIG, f)
        f.flush()
        config = load_config(f.name)

    assert isinstance(config, JanitorConfig)
    assert len(config.proxmox_servers) == 1
    assert config.proxmox_servers[0].name == "test-pve"
    assert config.proxmox_servers[0].auth.method == "token"
    assert config.ai.provider == "anthropic"


def test_defaults():
    config = JanitorConfig(**MINIMAL_CONFIG)
    assert config.permissions.level == "semi_auto"
    assert config.monitoring.check_interval_seconds == 60
    assert config.monitoring.thresholds.cpu_percent == 90.0
    assert config.ssh.key_path == "~/.ssh/id_ed25519"
    assert config.notifications.discord.enabled is False


def test_missing_config_file():
    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/config.yaml")


def test_env_var_resolution(monkeypatch):
    monkeypatch.setenv("TEST_TOKEN", "resolved_value")
    cfg = {
        **MINIMAL_CONFIG,
        "ai": {
            "provider": "anthropic",
            "model": "test",
            "api_key": "${TEST_TOKEN}",
        },
    }
    config = JanitorConfig(**cfg)
    assert config.ai.api_key == "resolved_value"
