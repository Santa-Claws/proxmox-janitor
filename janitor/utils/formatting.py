from __future__ import annotations


def human_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.1f} PB"


def human_uptime(seconds: int) -> str:
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def severity_emoji(severity: str) -> str:
    return {"info": "ℹ️", "warning": "⚠️", "critical": "🔴"}.get(severity, "❓")


def status_color(status: str) -> str:
    return {
        "running": "🟢",
        "stopped": "🔴",
        "paused": "🟡",
        "error": "🔴",
    }.get(status, "⚪")
