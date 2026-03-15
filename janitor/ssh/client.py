from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import asyncssh

from janitor.config import SSHConfig, SSHServerConfig

logger = logging.getLogger(__name__)


@dataclass
class SSHResult:
    stdout: str
    stderr: str
    exit_code: int


class SSHManager:
    """Manages asyncssh connections with automatic reconnection."""

    def __init__(self, global_cfg: SSHConfig) -> None:
        self._global_cfg = global_cfg
        self._connections: dict[str, asyncssh.SSHClientConnection] = {}

    def _conn_key(self, cfg: SSHServerConfig) -> str:
        return f"{cfg.user}@{cfg.host}:{cfg.port}"

    def _resolve_key_path(self, cfg: SSHServerConfig) -> str:
        path = cfg.key_path or self._global_cfg.key_path
        return str(Path(path).expanduser())

    async def _get_conn(self, cfg: SSHServerConfig) -> asyncssh.SSHClientConnection:
        key = self._conn_key(cfg)
        conn = self._connections.get(key)

        # Check if existing connection is still alive
        if conn is not None:
            try:
                # A simple check — if the transport is gone, this will fail
                if conn.get_extra_info("socket") is not None:
                    return conn
            except Exception:
                pass
            self._connections.pop(key, None)

        known_hosts = None
        if self._global_cfg.known_hosts_policy == "ignore":
            known_hosts = None
        elif self._global_cfg.known_hosts_policy == "auto_add":
            known_hosts = None  # asyncssh doesn't verify by default

        key_path = self._resolve_key_path(cfg)
        logger.debug("SSH connecting to %s with key %s", key, key_path)

        conn = await asyncssh.connect(
            cfg.host,
            port=cfg.port,
            username=cfg.user,
            client_keys=[key_path],
            known_hosts=known_hosts,
            connect_timeout=self._global_cfg.connect_timeout_seconds,
        )
        self._connections[key] = conn
        logger.info("[bold green]SSH connected[/] to %s", key)
        return conn

    async def run(self, cfg: SSHServerConfig, command: str) -> SSHResult:
        conn = await self._get_conn(cfg)
        result = await conn.run(command, check=False)
        return SSHResult(
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            exit_code=result.exit_status or 0,
        )

    async def close_all(self) -> None:
        for conn in self._connections.values():
            conn.close()
        self._connections.clear()
