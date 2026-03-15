from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class IssueSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class IssueStatus(StrEnum):
    OPEN = "open"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    EXECUTING = "executing"
    RESOLVED = "resolved"
    DENIED = "denied"
    FAILED = "failed"


def _short_id() -> str:
    return uuid.uuid4().hex[:8]


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class Issue:
    server_name: str
    title: str
    description: str
    severity: IssueSeverity = IssueSeverity.WARNING
    status: IssueStatus = IssueStatus.OPEN
    id: str = field(default_factory=_short_id)
    node: str | None = None
    resource: str | None = None
    metrics_snapshot: dict[str, Any] = field(default_factory=dict)
    log_excerpt: str = ""
    ai_analysis: str | None = None
    ai_suggested_action: str | None = None
    action_type: str | None = None
    action_params: dict[str, Any] | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    resolved_at: datetime | None = None
    notified: bool = False

    def touch(self) -> None:
        self.updated_at = _now()

    def resolve(self) -> None:
        self.status = IssueStatus.RESOLVED
        self.resolved_at = _now()
        self.touch()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "server_name": self.server_name,
            "node": self.node,
            "resource": self.resource,
            "severity": self.severity.value,
            "status": self.status.value,
            "title": self.title,
            "description": self.description,
            "ai_analysis": self.ai_analysis,
            "ai_suggested_action": self.ai_suggested_action,
            "action_type": self.action_type,
            "action_params": self.action_params,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }
