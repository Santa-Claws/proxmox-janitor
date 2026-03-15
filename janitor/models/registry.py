from __future__ import annotations

import json
import logging
from pathlib import Path

from janitor.models.issue import Issue, IssueStatus

logger = logging.getLogger(__name__)


class IssueRegistry:
    """In-memory issue store with optional JSON persistence for crash recovery."""

    def __init__(self, persist_path: str | Path | None = None) -> None:
        self._issues: dict[str, Issue] = {}
        self._persist_path = Path(persist_path) if persist_path else None

    def add(self, issue: Issue) -> None:
        self._issues[issue.id] = issue
        self._save()

    def get(self, issue_id: str) -> Issue | None:
        return self._issues.get(issue_id)

    def update(self, issue: Issue) -> None:
        issue.touch()
        self._issues[issue.id] = issue
        self._save()

    def find_open(self, server_name: str, title: str) -> Issue | None:
        """Find an existing open issue for the same server and title to avoid duplicates."""
        for issue in self._issues.values():
            if (
                issue.server_name == server_name
                and issue.title == title
                and issue.status
                not in (IssueStatus.RESOLVED, IssueStatus.DENIED, IssueStatus.FAILED)
            ):
                return issue
        return None

    def list_all(self) -> list[Issue]:
        return list(self._issues.values())

    def list_active(self) -> list[Issue]:
        terminal = {IssueStatus.RESOLVED, IssueStatus.DENIED, IssueStatus.FAILED}
        return [i for i in self._issues.values() if i.status not in terminal]

    def list_pending_approval(self) -> list[Issue]:
        return [i for i in self._issues.values() if i.status == IssueStatus.AWAITING_APPROVAL]

    def _save(self) -> None:
        if not self._persist_path:
            return
        try:
            data = [issue.to_dict() for issue in self._issues.values()]
            self._persist_path.write_text(json.dumps(data, indent=2))
        except Exception:
            logger.exception("Failed to persist issue registry")
