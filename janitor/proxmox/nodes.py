from __future__ import annotations

from janitor.models.metrics import NodeMetrics
from janitor.proxmox.client import ProxmoxClient


async def collect_node_metrics(client: ProxmoxClient) -> list[NodeMetrics]:
    nodes = await client.get_nodes()
    metrics = []
    for node_info in nodes:
        node_name = node_info["node"]
        status = await client.get_node_status(node_name)

        cpu_percent = status.get("cpu", 0) * 100
        mem = status.get("memory", {})
        ram_used = mem.get("used", 0)
        ram_total = mem.get("total", 1)
        rootfs = status.get("rootfs", {})
        disk_used = rootfs.get("used", 0)
        disk_total = rootfs.get("total", 1)
        loadavg = status.get("loadavg", ["0", "0", "0"])

        metrics.append(
            NodeMetrics(
                server_name=client.config.name,
                node=node_name,
                cpu_percent=cpu_percent,
                ram_used_bytes=ram_used,
                ram_total_bytes=ram_total,
                ram_percent=(ram_used / ram_total * 100) if ram_total else 0,
                disk_used_bytes=disk_used,
                disk_total_bytes=disk_total,
                disk_percent=(disk_used / disk_total * 100) if disk_total else 0,
                load_avg=(float(loadavg[0]), float(loadavg[1]), float(loadavg[2])),
                uptime_seconds=int(status.get("uptime", 0)),
            )
        )
    return metrics
