from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from janitor.config import MonitoringConfig, SSHServerConfig
from janitor.models.issue import Issue, IssueSeverity
from janitor.models.metrics import SystemSnapshot
from janitor.models.registry import IssueRegistry
from janitor.proxmox.cluster import collect_cluster_health
from janitor.proxmox.nodes import collect_node_metrics
from janitor.proxmox.services import collect_service_statuses
from janitor.proxmox.storage import collect_storage_metrics
from janitor.proxmox.vms import collect_vm_status
from janitor.ssh.commands import get_journal_logs, get_smart_summary

if TYPE_CHECKING:
    from janitor.ai.debugger import AIDebugger
    from janitor.notifications.base import BaseNotifier
    from janitor.proxmox.client import ProxmoxClient
    from janitor.ssh.client import SSHManager

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(
        self,
        proxmox_clients: dict[str, ProxmoxClient],
        ssh_manager: SSHManager,
        ssh_configs: dict[str, SSHServerConfig],
        monitoring_cfg: MonitoringConfig,
        registry: IssueRegistry,
        notifier: BaseNotifier,
        debugger: AIDebugger | None = None,
    ) -> None:
        self._clients = proxmox_clients
        self._ssh = ssh_manager
        self._ssh_configs = ssh_configs
        self._cfg = monitoring_cfg
        self._registry = registry
        self._notifier = notifier
        self._debugger = debugger
        self._last_alert: dict[str, datetime] = {}
        self._running = False

    async def run(self) -> None:
        self._running = True
        logger.info(
            "[bold]Scheduler started[/] — checking every %ds", self._cfg.check_interval_seconds
        )
        while self._running:
            try:
                await self._tick()
            except Exception:
                logger.exception("Scheduler tick failed")
            await asyncio.sleep(self._cfg.check_interval_seconds)

    def stop(self) -> None:
        self._running = False

    async def _tick(self) -> None:
        snapshots = await asyncio.gather(
            *(self._collect_snapshot(name, client) for name, client in self._clients.items()),
            return_exceptions=True,
        )

        for snap in snapshots:
            if isinstance(snap, Exception):
                logger.error("Snapshot collection failed: %s", snap)
                continue
            anomalies = self._detect_anomalies(snap)
            for issue in anomalies:
                existing = self._registry.find_open(issue.server_name, issue.title)
                if existing:
                    existing.metrics_snapshot = issue.metrics_snapshot
                    existing.log_excerpt = issue.log_excerpt
                    self._registry.update(existing)
                    continue  # don't re-alert

                self._registry.add(issue)

                # AI analysis
                if self._debugger:
                    try:
                        issue = await self._debugger.analyze_issue(issue, snap)
                        self._registry.update(issue)
                    except Exception:
                        logger.exception("AI analysis failed for issue %s", issue.id)

                # Notify if not in cooldown
                if self._should_alert(issue):
                    await self._notifier.send_alert(issue)
                    issue.notified = True
                    self._registry.update(issue)

    async def _collect_snapshot(self, name: str, client: ProxmoxClient) -> SystemSnapshot:
        checks = self._cfg.checks
        ssh_cfg = self._ssh_configs.get(name)

        nodes = await collect_node_metrics(client) if checks.node_metrics else []
        vms = await collect_vm_status(client) if checks.vm_status else []
        storages = await collect_storage_metrics(client) if checks.storage_pools else []
        cluster = await collect_cluster_health(client) if checks.cluster_health else None

        service_statuses: dict[str, str] = {}
        smart_summary = None
        log_excerpt = ""

        if ssh_cfg:
            if checks.proxmox_services:
                service_statuses = await collect_service_statuses(self._ssh, ssh_cfg)
            if checks.smart_disk_health:
                try:
                    smart_summary = await get_smart_summary(self._ssh, ssh_cfg)
                except Exception:
                    logger.debug("SMART check failed for %s", name)
            if checks.system_logs:
                try:
                    log_excerpt = await get_journal_logs(
                        self._ssh, ssh_cfg, lines=self._cfg.log_lines_for_context
                    )
                except Exception:
                    logger.debug("Log collection failed for %s", name)

        return SystemSnapshot(
            server_name=name,
            nodes=nodes,
            vms=vms,
            storages=storages,
            cluster_health=cluster,
            service_statuses=service_statuses,
            smart_summary=smart_summary,
            log_excerpt=log_excerpt,
        )

    def _detect_anomalies(self, snapshot: SystemSnapshot) -> list[Issue]:
        issues: list[Issue] = []
        thresholds = self._cfg.thresholds

        for node in snapshot.nodes:
            if node.cpu_percent >= thresholds.cpu_percent:
                issues.append(
                    Issue(
                        server_name=snapshot.server_name,
                        node=node.node,
                        resource="cpu",
                        severity=IssueSeverity.CRITICAL
                        if node.cpu_percent >= 98
                        else IssueSeverity.WARNING,
                        title=f"High CPU on {node.node}",
                        description=(
                            f"CPU at {node.cpu_percent:.1f}%"
                            f" (threshold: {thresholds.cpu_percent}%)"
                        ),
                        metrics_snapshot={"cpu_percent": node.cpu_percent},
                        log_excerpt=snapshot.log_excerpt,
                    )
                )

            if node.ram_percent >= thresholds.ram_percent:
                issues.append(
                    Issue(
                        server_name=snapshot.server_name,
                        node=node.node,
                        resource="ram",
                        severity=IssueSeverity.CRITICAL
                        if node.ram_percent >= 95
                        else IssueSeverity.WARNING,
                        title=f"High RAM on {node.node}",
                        description=(
                            f"RAM at {node.ram_percent:.1f}%"
                            f" (threshold: {thresholds.ram_percent}%)"
                        ),
                        metrics_snapshot={"ram_percent": node.ram_percent},
                        log_excerpt=snapshot.log_excerpt,
                    )
                )

            if node.disk_percent >= thresholds.disk_percent:
                issues.append(
                    Issue(
                        server_name=snapshot.server_name,
                        node=node.node,
                        resource="disk",
                        severity=IssueSeverity.CRITICAL
                        if node.disk_percent >= 95
                        else IssueSeverity.WARNING,
                        title=f"High disk usage on {node.node}",
                        description=(
                            f"Disk at {node.disk_percent:.1f}%"
                            f" (threshold: {thresholds.disk_percent}%)"
                        ),
                        metrics_snapshot={"disk_percent": node.disk_percent},
                        log_excerpt=snapshot.log_excerpt,
                    )
                )

            if node.load_avg[0] >= thresholds.load_avg_1m:
                issues.append(
                    Issue(
                        server_name=snapshot.server_name,
                        node=node.node,
                        resource="load",
                        severity=IssueSeverity.WARNING,
                        title=f"High load average on {node.node}",
                        description=(
                            f"1m load avg {node.load_avg[0]:.2f}"
                            f" (threshold: {thresholds.load_avg_1m})"
                        ),
                        metrics_snapshot={"load_avg_1m": node.load_avg[0]},
                        log_excerpt=snapshot.log_excerpt,
                    )
                )

        # VM/container issues
        for vm in snapshot.vms:
            if vm.status in ("error", "unknown"):
                issues.append(
                    Issue(
                        server_name=snapshot.server_name,
                        node=vm.node,
                        resource=f"{vm.vm_type}/{vm.vmid}",
                        severity=IssueSeverity.CRITICAL,
                        title=f"{vm.vm_type.upper()} {vm.vmid} ({vm.name}) in {vm.status} state",
                        description=(
                            f"VM {vm.vmid} ({vm.name}) on {vm.node}"
                            f" is in '{vm.status}' state"
                        ),
                        metrics_snapshot={"vmid": vm.vmid, "status": vm.status},
                        log_excerpt=snapshot.log_excerpt,
                    )
                )

        # Storage issues
        for storage in snapshot.storages:
            if storage.percent_used >= thresholds.disk_percent:
                issues.append(
                    Issue(
                        server_name=snapshot.server_name,
                        resource=f"storage/{storage.storage_id}",
                        severity=IssueSeverity.WARNING,
                        title=f"Storage {storage.storage_id} high usage",
                        description=f"Storage {storage.storage_id} at {storage.percent_used:.1f}%",
                        metrics_snapshot={"percent_used": storage.percent_used},
                    )
                )

        # Service issues
        for svc, status in snapshot.service_statuses.items():
            if status not in ("active", "unknown"):
                issues.append(
                    Issue(
                        server_name=snapshot.server_name,
                        resource=f"service/{svc}",
                        severity=IssueSeverity.CRITICAL,
                        title=f"Service {svc} is {status}",
                        description=f"Proxmox service {svc} is {status} on {snapshot.server_name}",
                        metrics_snapshot={"service": svc, "status": status},
                        log_excerpt=snapshot.log_excerpt,
                    )
                )

        # SMART issues
        if snapshot.smart_summary and "FAILED" in snapshot.smart_summary.upper():
            issues.append(
                Issue(
                    server_name=snapshot.server_name,
                    resource="disk/smart",
                    severity=IssueSeverity.CRITICAL,
                    title=f"SMART failure detected on {snapshot.server_name}",
                    description=snapshot.smart_summary[:500],
                    metrics_snapshot={},
                    log_excerpt=snapshot.log_excerpt,
                )
            )

        return issues

    def _should_alert(self, issue: Issue) -> bool:
        key = f"{issue.server_name}:{issue.title}"
        now = datetime.now(UTC)
        last = self._last_alert.get(key)
        if last and (now - last).total_seconds() < self._cfg.alert_cooldown_seconds:
            return False
        self._last_alert[key] = now
        return True

    async def collect_snapshot_for(self, server_name: str) -> SystemSnapshot | None:
        """Public method for on-demand snapshot collection (used by bot commands)."""
        client = self._clients.get(server_name)
        if not client:
            return None
        return await self._collect_snapshot(server_name, client)

    async def collect_all_snapshots(self) -> list[SystemSnapshot]:
        results = await asyncio.gather(
            *(self._collect_snapshot(name, client) for name, client in self._clients.items()),
            return_exceptions=True,
        )
        return [r for r in results if isinstance(r, SystemSnapshot)]
