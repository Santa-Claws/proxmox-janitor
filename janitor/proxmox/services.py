from __future__ import annotations

import logging

from janitor.config import SSHServerConfig
from janitor.ssh.client import SSHManager

logger = logging.getLogger(__name__)

PVE_SERVICES = [
    "pve-cluster",
    "pvedaemon",
    "pveproxy",
    "pvestatd",
    "pve-firewall",
    "corosync",
]


async def collect_service_statuses(ssh: SSHManager, ssh_cfg: SSHServerConfig) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for service in PVE_SERVICES:
        try:
            result = await ssh.run(
                ssh_cfg,
                f"systemctl is-active {service} 2>/dev/null || echo inactive",
            )
            statuses[service] = result.stdout.strip()
        except Exception:
            statuses[service] = "unknown"
    return statuses
