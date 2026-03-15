from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

from janitor.config import PermissionsConfig, SSHServerConfig
from janitor.models.metrics import NodeMetrics, VMStatus
from janitor.proxmox.client import ProxmoxClient
from janitor.proxmox.nodes import collect_node_metrics
from janitor.proxmox.vms import collect_vm_status
from janitor.ssh.client import SSHManager
from janitor.ssh.commands import get_journal_logs, restart_service

logger = logging.getLogger(__name__)


@dataclass
class ActionResult:
    status: Literal["ok", "pending", "denied", "failed"]
    message: str
    output: str | None = None


class ActionExecutor:
    """Central permission gate — all actions must go through here."""

    def __init__(
        self,
        permissions: PermissionsConfig,
        proxmox_clients: dict[str, ProxmoxClient],
        ssh_manager: SSHManager,
        ssh_configs: dict[str, SSHServerConfig],
    ) -> None:
        self._perms = permissions
        self._clients = proxmox_clients
        self._ssh = ssh_manager
        self._ssh_configs = ssh_configs

    async def execute(
        self,
        action_type: str,
        params: dict[str, Any],
        auto: bool = False,
    ) -> ActionResult:
        # Always denied
        if action_type in self._perms.deny_actions:
            logger.warning("Action %s DENIED (in deny_actions list)", action_type)
            return ActionResult("denied", f"Action '{action_type}' is denied by configuration.")

        level = self._perms.level

        # Read-only — no actions ever
        if level == "read_only":
            return ActionResult("denied", "Permission level is read_only. No actions allowed.")

        # Suggest — always queue
        if level == "suggest":
            return ActionResult(
                "pending",
                f"Action '{action_type}' queued for approval. Use /fix to approve.",
            )

        # Semi-auto — check allow list
        if level == "semi_auto":
            if action_type in self._perms.allow_actions:
                return await self._dispatch(action_type, params)
            return ActionResult(
                "pending",
                f"Action '{action_type}' not in allow_actions. Queued for approval.",
            )

        # Full-auto
        if level == "full_auto":
            return await self._dispatch(action_type, params)

        return ActionResult("denied", f"Unknown permission level: {level}")

    async def execute_read_only(self, tool_name: str, params: dict[str, Any]) -> str:
        """Execute read-only tools without permission checks."""
        server_name = params.get("server_name", "")
        client = self._clients.get(server_name)
        ssh_cfg = self._ssh_configs.get(server_name)

        if tool_name == "get_node_metrics":
            if not client:
                return f"Server '{server_name}' not found."
            metrics = await collect_node_metrics(client)
            node_name = params.get("node")
            if node_name:
                metrics = [m for m in metrics if m.node == node_name]
            return "\n".join(self._format_node_metrics(m) for m in metrics) or "No metrics found."

        elif tool_name == "get_vm_list":
            if not client:
                return f"Server '{server_name}' not found."
            vms = await collect_vm_status(client)
            node_name = params.get("node")
            if node_name:
                vms = [v for v in vms if v.node == node_name]
            return "\n".join(self._format_vm_status(v) for v in vms) or "No VMs found."

        elif tool_name == "get_logs":
            if not ssh_cfg:
                return f"No SSH config for server '{server_name}'."
            lines = params.get("lines", 100)
            unit = params.get("unit")
            return await get_journal_logs(self._ssh, ssh_cfg, lines=lines, unit=unit)

        return f"Unknown read-only tool: {tool_name}"

    async def _dispatch(self, action_type: str, params: dict[str, Any]) -> ActionResult:
        try:
            if action_type == "restart_vm":
                return await self._restart_vm(params)
            elif action_type == "restart_service":
                return await self._restart_service(params)
            elif action_type == "run_ssh_command":
                return await self._run_ssh_command(params)
            else:
                return ActionResult("failed", f"Unknown action type: {action_type}")
        except Exception as e:
            logger.exception("Action %s failed", action_type)
            return ActionResult("failed", f"Action failed: {e}")

    async def _restart_vm(self, params: dict[str, Any]) -> ActionResult:
        server_name = params["server_name"]
        node = params["node"]
        vmid = params["vmid"]
        vm_type = params.get("vm_type", "qemu")

        client = self._clients.get(server_name)
        if not client:
            return ActionResult("failed", f"Server '{server_name}' not found.")

        result = await client.vm_action(node, vmid, "reboot", vm_type)
        return ActionResult("ok", f"Restarted {vm_type} {vmid} on {node}", output=result)

    async def _restart_service(self, params: dict[str, Any]) -> ActionResult:
        server_name = params["server_name"]
        service = params["service"]

        ssh_cfg = self._ssh_configs.get(server_name)
        if not ssh_cfg:
            return ActionResult("failed", f"No SSH config for server '{server_name}'.")

        output = await restart_service(self._ssh, ssh_cfg, service)
        return ActionResult("ok", f"Restarted service {service} on {server_name}", output=output)

    async def _run_ssh_command(self, params: dict[str, Any]) -> ActionResult:
        server_name = params["server_name"]
        command = params["command"]

        ssh_cfg = self._ssh_configs.get(server_name)
        if not ssh_cfg:
            return ActionResult("failed", f"No SSH config for server '{server_name}'.")

        result = await self._ssh.run(ssh_cfg, command)
        return ActionResult(
            "ok" if result.exit_code == 0 else "failed",
            f"Command exited with code {result.exit_code}",
            output=result.stdout + ("\n" + result.stderr if result.stderr else ""),
        )

    @staticmethod
    def _format_node_metrics(m: NodeMetrics) -> str:
        return (
            f"Node {m.node}: CPU {m.cpu_percent:.1f}% | "
            f"RAM {m.ram_percent:.1f}% ({m.ram_used_bytes}/{m.ram_total_bytes}) | "
            f"Disk {m.disk_percent:.1f}% | Load {m.load_avg[0]:.2f}"
        )

    @staticmethod
    def _format_vm_status(v: VMStatus) -> str:
        return f"{v.vm_type.upper()} {v.vmid} ({v.name}): {v.status} | CPU {v.cpu_percent:.1f}%"
