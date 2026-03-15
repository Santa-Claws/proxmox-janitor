from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class NodeMetrics:
    server_name: str
    node: str
    cpu_percent: float
    ram_used_bytes: int
    ram_total_bytes: int
    ram_percent: float
    disk_used_bytes: int
    disk_total_bytes: int
    disk_percent: float
    load_avg: tuple[float, float, float] = (0.0, 0.0, 0.0)
    network_in_bytes: int = 0
    network_out_bytes: int = 0
    uptime_seconds: int = 0
    collected_at: datetime = field(default_factory=_now)


@dataclass
class VMStatus:
    server_name: str
    node: str
    vmid: int
    name: str
    vm_type: Literal["qemu", "lxc"]
    status: str  # "running", "stopped", "paused", "error"
    cpu_percent: float = 0.0
    ram_used_bytes: int = 0
    ram_total_bytes: int = 0
    collected_at: datetime = field(default_factory=_now)


@dataclass
class StorageMetrics:
    server_name: str
    storage_id: str
    storage_type: str
    used_bytes: int
    total_bytes: int
    percent_used: float
    active: bool = True
    collected_at: datetime = field(default_factory=_now)


@dataclass
class SystemSnapshot:
    server_name: str
    nodes: list[NodeMetrics] = field(default_factory=list)
    vms: list[VMStatus] = field(default_factory=list)
    storages: list[StorageMetrics] = field(default_factory=list)
    cluster_health: dict[str, Any] | None = None
    service_statuses: dict[str, str] = field(default_factory=dict)
    smart_summary: str | None = None
    log_excerpt: str = ""
    collected_at: datetime = field(default_factory=_now)

    def summary_text(self) -> str:
        lines = [f"=== {self.server_name} @ {self.collected_at.isoformat()} ==="]
        for n in self.nodes:
            lines.append(
                f"  Node {n.node}: CPU {n.cpu_percent:.1f}% | "
                f"RAM {n.ram_percent:.1f}% | Disk {n.disk_percent:.1f}%"
            )
        for vm in self.vms:
            lines.append(f"  {vm.vm_type.upper()} {vm.vmid} ({vm.name}): {vm.status}")
        for s in self.storages:
            lines.append(f"  Storage {s.storage_id}: {s.percent_used:.1f}% used")
        if self.service_statuses:
            down = [k for k, v in self.service_statuses.items() if v != "active"]
            if down:
                lines.append(f"  Services DOWN: {', '.join(down)}")
        if self.smart_summary:
            lines.append(f"  SMART: {self.smart_summary}")
        return "\n".join(lines)
