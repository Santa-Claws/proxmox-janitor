from __future__ import annotations

import asyncio
import logging
from typing import Any

from proxmoxer import ProxmoxAPI

from janitor.config import ServerConfig

logger = logging.getLogger(__name__)


class ProxmoxClient:
    """Async wrapper around proxmoxer (sync library) using asyncio.to_thread."""

    def __init__(self, config: ServerConfig) -> None:
        self.config = config
        self._api: ProxmoxAPI | None = None

    async def connect(self) -> None:
        self._api = await asyncio.to_thread(self._create_api)
        logger.info(
            "[bold green]Connected to Proxmox[/] %s (%s)", self.config.name, self.config.host
        )

    def _create_api(self) -> ProxmoxAPI:
        cfg = self.config
        if cfg.auth.method == "token":
            return ProxmoxAPI(
                cfg.host,
                port=cfg.port,
                user=cfg.user,
                token_name=cfg.auth.token_name,
                token_value=cfg.auth.token_value,
                verify_ssl=cfg.verify_ssl,
            )
        # ssh_key method — use SSH backend
        key_path = cfg.ssh.key_path if cfg.ssh and cfg.ssh.key_path else "~/.ssh/id_ed25519"
        return ProxmoxAPI(
            cfg.host,
            port=cfg.port,
            user=cfg.user,
            backend="ssh_paramiko",
            private_key_file=key_path,
        )

    @property
    def api(self) -> ProxmoxAPI:
        if self._api is None:
            raise RuntimeError(
                f"ProxmoxClient for {self.config.name} not connected. Call connect() first."
            )
        return self._api

    async def get_nodes(self) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self.api.nodes.get)

    async def get_node_status(self, node: str) -> dict[str, Any]:
        return await asyncio.to_thread(self.api.nodes(node).status.get)

    async def get_vms(self, node: str) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self.api.nodes(node).qemu.get)

    async def get_containers(self, node: str) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self.api.nodes(node).lxc.get)

    async def get_storage(self, node: str) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self.api.nodes(node).storage.get)

    async def get_cluster_status(self) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self.api.cluster.status.get)

    async def vm_action(self, node: str, vmid: int, action: str, vm_type: str = "qemu") -> str:
        """Execute a VM/LXC action (start, stop, reboot, shutdown)."""
        if vm_type == "lxc":
            resource = self.api.nodes(node).lxc(vmid).status
        else:
            resource = self.api.nodes(node).qemu(vmid).status
        result = await asyncio.to_thread(getattr(resource, action).post)
        logger.info("VM action %s on %s/%s/%s: %s", action, self.config.name, node, vmid, result)
        return str(result)
