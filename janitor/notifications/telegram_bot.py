from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from janitor.actions.executor import ActionResult
from janitor.models.issue import Issue, IssueStatus
from janitor.notifications.base import BaseNotifier
from janitor.utils.formatting import severity_emoji, status_color

if TYPE_CHECKING:
    from janitor.ai.debugger import AIDebugger
    from janitor.config import TelegramConfig
    from janitor.models.registry import IssueRegistry
    from janitor.scheduler import Scheduler

logger = logging.getLogger(__name__)


class TelegramBot(BaseNotifier):
    def __init__(
        self,
        config: TelegramConfig,
        registry: IssueRegistry,
        scheduler: Scheduler,
        debugger: AIDebugger | None = None,
    ) -> None:
        self._config = config
        self._registry = registry
        self._scheduler = scheduler
        self._debugger = debugger
        self._app = None
        self._task: asyncio.Task[None] | None = None

    def _build_app(self):
        builder = ApplicationBuilder().token(self._config.bot_token)
        app = builder.build()

        app.add_handler(CommandHandler("status", self._cmd_status))
        app.add_handler(CommandHandler("nodes", self._cmd_nodes))
        app.add_handler(CommandHandler("vms", self._cmd_vms))
        app.add_handler(CommandHandler("issues", self._cmd_issues))
        app.add_handler(CommandHandler("fix", self._cmd_fix))
        app.add_handler(CommandHandler("deny", self._cmd_deny))
        app.add_handler(CommandHandler("debug", self._cmd_debug))

        return app

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        snapshots = await self._scheduler.collect_all_snapshots()
        if not snapshots:
            await update.message.reply_text("No servers configured or reachable.")
            return
        lines = []
        for snap in snapshots:
            lines.append(snap.summary_text())
        await update.message.reply_text("\n\n".join(lines) or "No data.")

    async def _cmd_nodes(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        snapshots = await self._scheduler.collect_all_snapshots()
        lines = []
        for snap in snapshots:
            for n in snap.nodes:
                lines.append(
                    f"{snap.server_name}/{n.node}: "
                    f"CPU {n.cpu_percent:.1f}% | RAM {n.ram_percent:.1f}% | "
                    f"Disk {n.disk_percent:.1f}%"
                )
        await update.message.reply_text("\n".join(lines) or "No nodes found.")

    async def _cmd_vms(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        snapshots = await self._scheduler.collect_all_snapshots()
        lines = []
        for snap in snapshots:
            for vm in snap.vms:
                icon = status_color(vm.status)
                lines.append(
                    f"{icon} {vm.vm_type.upper()} {vm.vmid} ({vm.name}) "
                    f"on {snap.server_name}/{vm.node} — {vm.status}"
                )
        text = "\n".join(lines) or "No VMs found."
        if len(text) > 4096:
            text = text[:4093] + "..."
        await update.message.reply_text(text)

    async def _cmd_issues(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        active = self._registry.list_active()
        if not active:
            await update.message.reply_text("No active issues.")
            return
        lines = []
        for issue in active:
            icon = severity_emoji(issue.severity.value)
            lines.append(
                f"{icon} {issue.id} [{issue.status.value}] {issue.title} ({issue.server_name})"
            )
        await update.message.reply_text("\n".join(lines))

    async def _cmd_fix(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        args = context.args
        if not args:
            await update.message.reply_text("Usage: /fix <issue_id>")
            return
        issue_id = args[0]
        issue = self._registry.get(issue_id)
        if not issue:
            await update.message.reply_text(f"Issue {issue_id} not found.")
            return
        if issue.status != IssueStatus.AWAITING_APPROVAL:
            await update.message.reply_text(f"Issue {issue_id} is not awaiting approval.")
            return
        issue.status = IssueStatus.APPROVED
        issue.resolve()
        self._registry.update(issue)
        await update.message.reply_text(f"Issue {issue_id} approved and resolved.")

    async def _cmd_deny(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        args = context.args
        if not args:
            await update.message.reply_text("Usage: /deny <issue_id>")
            return
        issue_id = args[0]
        issue = self._registry.get(issue_id)
        if not issue:
            await update.message.reply_text(f"Issue {issue_id} not found.")
            return
        issue.status = IssueStatus.DENIED
        issue.touch()
        self._registry.update(issue)
        await update.message.reply_text(f"Issue {issue_id} denied.")

    async def _cmd_debug(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._debugger:
            await update.message.reply_text("AI debugger not configured.")
            return
        query = " ".join(context.args) if context.args else "General health check"
        snapshots = await self._scheduler.collect_all_snapshots()
        if not snapshots:
            await update.message.reply_text("No servers reachable.")
            return
        response = await self._debugger.interactive_session(query, snapshots[0])
        if len(response) > 4096:
            response = response[:4093] + "..."
        await update.message.reply_text(response)

    async def send_alert(self, issue: Issue) -> None:
        if not self._app or not self._config.chat_id:
            return
        icon = severity_emoji(issue.severity.value)
        text = (
            f"{icon} *{issue.title}*\n"
            f"Server: {issue.server_name}\n"
            f"Severity: {issue.severity.value.upper()}\n"
            f"ID: `{issue.id}`\n\n"
            f"{issue.description}"
        )
        if issue.ai_analysis:
            text += f"\n\n*AI Analysis:*\n{issue.ai_analysis[:2000]}"
        if issue.status == IssueStatus.AWAITING_APPROVAL:
            text += f"\n\nUse /fix {issue.id} to approve or /deny {issue.id} to reject"
        await self._app.bot.send_message(
            chat_id=self._config.chat_id, text=text, parse_mode="Markdown"
        )

    async def send_message(self, text: str) -> None:
        if self._app and self._config.chat_id:
            await self._app.bot.send_message(chat_id=self._config.chat_id, text=text)

    async def send_action_result(self, result: ActionResult, issue: Issue) -> None:
        if not self._app or not self._config.chat_id:
            return
        text = f"Action Result — {issue.id}\n{result.message}"
        if result.output:
            text += f"\n```\n{result.output[:2000]}\n```"
        await self._app.bot.send_message(
            chat_id=self._config.chat_id, text=text, parse_mode="Markdown"
        )

    async def start(self) -> None:
        if not self._config.bot_token:
            logger.warning("Telegram bot token not configured, skipping")
            return
        self._app = self._build_app()
        await self._app.initialize()
        await self._app.start()
        self._task = asyncio.create_task(
            self._app.updater.start_polling(),
            name="telegram-bot",
        )
        logger.info("[bold green]Telegram bot started[/]")

    async def stop(self) -> None:
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
        if self._task:
            self._task.cancel()
