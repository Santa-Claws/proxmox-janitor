from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, field_validator


class AuthConfig(BaseModel):
    method: Literal["token", "ssh_key"]
    token_name: str | None = None
    token_value: str | None = None

    @field_validator("token_name", "token_value", mode="before")
    @classmethod
    def resolve_env(cls, v: str | None) -> str | None:
        if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
            return os.environ.get(v[2:-1], v)
        return v


class SSHServerConfig(BaseModel):
    host: str
    port: int = 22
    user: str = "root"
    key_path: str | None = None


class ServerConfig(BaseModel):
    name: str
    host: str
    port: int = 8006
    user: str = "root@pam"
    auth: AuthConfig
    verify_ssl: bool = False
    ssh: SSHServerConfig | None = None


class DiscordConfig(BaseModel):
    enabled: bool = False
    bot_token: str | None = None
    channel_id: int | None = None
    alert_channel_id: int | None = None

    @field_validator("bot_token", mode="before")
    @classmethod
    def resolve_env(cls, v: str | None) -> str | None:
        if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
            return os.environ.get(v[2:-1], v)
        return v


class TelegramConfig(BaseModel):
    enabled: bool = False
    bot_token: str | None = None
    chat_id: int | None = None

    @field_validator("bot_token", mode="before")
    @classmethod
    def resolve_env(cls, v: str | None) -> str | None:
        if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
            return os.environ.get(v[2:-1], v)
        return v


class NotificationsConfig(BaseModel):
    discord: DiscordConfig = DiscordConfig()
    telegram: TelegramConfig = TelegramConfig()


class AIConfig(BaseModel):
    provider: Literal["anthropic", "openai", "openrouter", "ollama"]
    model: str
    api_key: str | None = None
    base_url: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.2

    @field_validator("api_key", mode="before")
    @classmethod
    def resolve_env(cls, v: str | None) -> str | None:
        if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
            return os.environ.get(v[2:-1], v)
        return v


class PermissionsConfig(BaseModel):
    level: Literal["read_only", "suggest", "semi_auto", "full_auto"] = "semi_auto"
    allow_actions: list[str] = ["restart_vm", "restart_service"]
    deny_actions: list[str] = ["run_ssh_command"]


class ThresholdConfig(BaseModel):
    cpu_percent: float = 90.0
    ram_percent: float = 85.0
    disk_percent: float = 80.0
    load_avg_1m: float = 8.0
    network_errors_per_min: float = 50.0


class ChecksConfig(BaseModel):
    node_metrics: bool = True
    vm_status: bool = True
    cluster_health: bool = True
    storage_pools: bool = True
    smart_disk_health: bool = True
    proxmox_services: bool = True
    system_logs: bool = True


class MonitoringConfig(BaseModel):
    check_interval_seconds: int = 60
    alert_cooldown_seconds: int = 300
    thresholds: ThresholdConfig = ThresholdConfig()
    checks: ChecksConfig = ChecksConfig()
    log_lines_for_context: int = 100


class SSHConfig(BaseModel):
    key_path: str = "~/.ssh/id_ed25519"
    known_hosts_policy: Literal["strict", "auto_add", "ignore"] = "auto_add"
    connect_timeout_seconds: int = 10


class JanitorConfig(BaseModel):
    proxmox_servers: list[ServerConfig]
    notifications: NotificationsConfig = NotificationsConfig()
    ai: AIConfig
    permissions: PermissionsConfig = PermissionsConfig()
    monitoring: MonitoringConfig = MonitoringConfig()
    ssh: SSHConfig = SSHConfig()


def load_config(path: str | Path = "config.yaml") -> JanitorConfig:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path) as f:
        raw = yaml.safe_load(f)
    return JanitorConfig(**raw)
