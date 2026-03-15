from __future__ import annotations

import logging
from typing import Any

from janitor.proxmox.client import ProxmoxClient

logger = logging.getLogger(__name__)


async def collect_cluster_health(client: ProxmoxClient) -> dict[str, Any] | None:
    try:
        status = await client.get_cluster_status()
        health: dict[str, Any] = {"nodes": [], "quorate": False}

        for entry in status:
            if entry.get("type") == "cluster":
                health["quorate"] = bool(entry.get("quorate", 0))
                health["cluster_name"] = entry.get("name", "unknown")
            elif entry.get("type") == "node":
                health["nodes"].append(
                    {
                        "name": entry.get("name"),
                        "online": bool(entry.get("online", 0)),
                        "ip": entry.get("ip"),
                    }
                )

        return health
    except Exception:
        logger.debug("Cluster status unavailable (standalone node?)")
        return None
