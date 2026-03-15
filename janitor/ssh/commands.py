from __future__ import annotations

from janitor.config import SSHServerConfig
from janitor.ssh.client import SSHManager


async def get_journal_logs(
    ssh: SSHManager, cfg: SSHServerConfig, lines: int = 100, unit: str | None = None
) -> str:
    cmd = f"journalctl --no-pager -n {lines}"
    if unit:
        cmd += f" -u {unit}"
    result = await ssh.run(cfg, cmd)
    return result.stdout


async def get_syslog(ssh: SSHManager, cfg: SSHServerConfig, lines: int = 100) -> str:
    cmd = (
        f"tail -n {lines} /var/log/syslog 2>/dev/null"
        f" || tail -n {lines} /var/log/messages 2>/dev/null"
        " || echo 'No syslog found'"
    )
    result = await ssh.run(cfg, cmd)
    return result.stdout


async def get_smart_summary(ssh: SSHManager, cfg: SSHServerConfig) -> str:
    # List block devices then get SMART info for each
    result = await ssh.run(cfg, "lsblk -dnpo NAME,TYPE | awk '$2==\"disk\"{print $1}'")
    disks = result.stdout.strip().split("\n")
    summaries = []
    for disk in disks:
        disk = disk.strip()
        if not disk:
            continue
        smart = await ssh.run(
            cfg, f"smartctl -H {disk} 2>/dev/null || echo 'SMART unavailable for {disk}'"
        )
        summaries.append(f"--- {disk} ---\n{smart.stdout.strip()}")
    return "\n".join(summaries) if summaries else "No disks found"


async def get_service_status(ssh: SSHManager, cfg: SSHServerConfig, service: str) -> str:
    result = await ssh.run(cfg, f"systemctl status {service} --no-pager -l 2>/dev/null")
    return result.stdout


async def restart_service(ssh: SSHManager, cfg: SSHServerConfig, service: str) -> str:
    result = await ssh.run(cfg, f"systemctl restart {service}")
    if result.exit_code != 0:
        return f"Failed to restart {service}: {result.stderr}"
    return f"Successfully restarted {service}"
