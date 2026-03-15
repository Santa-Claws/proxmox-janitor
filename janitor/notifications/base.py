from __future__ import annotations

from abc import ABC, abstractmethod

from janitor.actions.executor import ActionResult
from janitor.models.issue import Issue


class BaseNotifier(ABC):
    @abstractmethod
    async def send_alert(self, issue: Issue) -> None: ...

    @abstractmethod
    async def send_message(self, text: str) -> None: ...

    @abstractmethod
    async def send_action_result(self, result: ActionResult, issue: Issue) -> None: ...

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...


class MultiNotifier(BaseNotifier):
    """Fan-out notifier that broadcasts to all enabled notifiers."""

    def __init__(self, notifiers: list[BaseNotifier]) -> None:
        self._notifiers = notifiers

    async def send_alert(self, issue: Issue) -> None:
        for n in self._notifiers:
            await n.send_alert(issue)

    async def send_message(self, text: str) -> None:
        for n in self._notifiers:
            await n.send_message(text)

    async def send_action_result(self, result: ActionResult, issue: Issue) -> None:
        for n in self._notifiers:
            await n.send_action_result(result, issue)

    async def start(self) -> None:
        for n in self._notifiers:
            await n.start()

    async def stop(self) -> None:
        for n in self._notifiers:
            await n.stop()
