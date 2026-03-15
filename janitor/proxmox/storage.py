from __future__ import annotations

from janitor.models.metrics import StorageMetrics
from janitor.proxmox.client import ProxmoxClient


async def collect_storage_metrics(client: ProxmoxClient) -> list[StorageMetrics]:
    nodes = await client.get_nodes()
    results: list[StorageMetrics] = []
    seen: set[str] = set()

    for node_info in nodes:
        node_name = node_info["node"]
        for storage in await client.get_storage(node_name):
            sid = storage["storage"]
            if sid in seen:
                continue
            seen.add(sid)

            total = storage.get("total", 0)
            used = storage.get("used", 0)

            results.append(
                StorageMetrics(
                    server_name=client.config.name,
                    storage_id=sid,
                    storage_type=storage.get("type", "unknown"),
                    used_bytes=used,
                    total_bytes=total,
                    percent_used=(used / total * 100) if total else 0,
                    active=bool(storage.get("active", 1)),
                )
            )

    return results
