from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from janitor.actions.executor import ActionResult
from janitor.models.issue import Issue, IssueStatus
from janitor.notifications.base import BaseNotifier
from janitor.utils.formatting import human_bytes, severity_emoji, status_color

if TYPE_CHECKING:
    from janitor.ai.debugger import AIDebugger
    from janitor.config import DiscordConfig
    from janitor.models.registry import IssueRegistry
    from janitor.scheduler import Scheduler

logger = logging.getLogger(__name__)


class DiscordBot(BaseNotifier):
    def __init__(
        self,
        config: DiscordConfig,
        registry: IssueRegistry,
        scheduler: Scheduler,
        debugger: AIDebugger | None = None,
    ) -> None:
        self._config = config
        self._registry = registry
        self._scheduler = scheduler
        self._debugger = debugger

        intents = discord.Intents.default()
        intents.message_content = True
        self._bot = commands.Bot(command_prefix="!", intents=intents)
        self._channel: discord.TextChannel | None = None
        self._alert_channel: discord.TextChannel | None = None
        self._task: asyncio.Task[None] | None = None

        self._register_commands()

    def _register_commands(self) -> None:
        bot = self._bot

        @bot.event
        async def on_ready() -> None:
            logger.info("[bold green]Discord bot ready[/] as %s", bot.user)
            if self._config.channel_id:
                self._channel = bot.get_channel(self._config.channel_id)  # type: ignore[assignment]
            if self._config.alert_channel_id:
                self._alert_channel = bot.get_channel(self._config.alert_channel_id)  # type: ignore[assignment]
            try:
                await bot.tree.sync()
                logger.info("Slash commands synced")
            except Exception:
                logger.exception("Failed to sync slash commands")

        @bot.tree.command(name="status", description="Health overview of all servers")
        async def cmd_status(interaction: discord.Interaction) -> None:
            await interaction.response.defer()
            snapshots = await self._scheduler.collect_all_snapshots()
            if not snapshots:
                await interaction.followup.send("No servers configured or reachable.")
                return
            embed = discord.Embed(title="Server Status", color=discord.Color.green())
            for snap in snapshots:
                value = snap.summary_text()
                if len(value) > 1024:
                    value = value[:1021] + "..."
                embed.add_field(name=snap.server_name, value=f"```\n{value}\n```", inline=False)
            await interaction.followup.send(embed=embed)

        @bot.tree.command(name="nodes", description="List all Proxmox nodes with metrics")
        async def cmd_nodes(interaction: discord.Interaction) -> None:
            await interaction.response.defer()
            snapshots = await self._scheduler.collect_all_snapshots()
            lines = []
            for snap in snapshots:
                for n in snap.nodes:
                    lines.append(
                        f"**{snap.server_name}/{n.node}**: "
                        f"CPU {n.cpu_percent:.1f}% | RAM {n.ram_percent:.1f}% | "
                        f"Disk {n.disk_percent:.1f}% | Up {n.uptime_seconds // 3600}h"
                    )
            await interaction.followup.send("\n".join(lines) or "No nodes found.")

        @bot.tree.command(name="vms", description="List VMs/containers")
        @app_commands.describe(server="Server name (optional)", node="Node name (optional)")
        async def cmd_vms(
            interaction: discord.Interaction,
            server: str | None = None,
            node: str | None = None,
        ) -> None:
            await interaction.response.defer()
            snapshots = await self._scheduler.collect_all_snapshots()
            lines = []
            for snap in snapshots:
                if server and snap.server_name != server:
                    continue
                for vm in snap.vms:
                    if node and vm.node != node:
                        continue
                    icon = status_color(vm.status)
                    lines.append(
                        f"{icon} **{vm.vm_type.upper()} {vm.vmid}** ({vm.name}) "
                        f"on {snap.server_name}/{vm.node} — {vm.status} | "
                        f"CPU {vm.cpu_percent:.1f}% | RAM {human_bytes(vm.ram_used_bytes)}"
                    )
            await interaction.followup.send("\n".join(lines) or "No VMs found.")

        @bot.tree.command(name="logs", description="Fetch recent system logs")
        @app_commands.describe(server="Server name", lines="Number of lines (default 50)")
        async def cmd_logs(
            interaction: discord.Interaction,
            server: str,
            lines: int = 50,
        ) -> None:
            await interaction.response.defer()
            from janitor.ssh.commands import get_journal_logs

            ssh_cfg = self._scheduler._ssh_configs.get(server)
            if not ssh_cfg:
                await interaction.followup.send(f"No SSH config for server '{server}'.")
                return
            log_text = await get_journal_logs(self._scheduler._ssh, ssh_cfg, lines=lines)
            # Discord message limit is 2000 chars
            if len(log_text) > 1900:
                log_text = log_text[-1900:]
            await interaction.followup.send(f"```\n{log_text}\n```")

        @bot.tree.command(name="issues", description="List open/pending issues")
        async def cmd_issues(interaction: discord.Interaction) -> None:
            active = self._registry.list_active()
            if not active:
                await interaction.response.send_message("No active issues.")
                return
            lines = []
            for issue in active:
                icon = severity_emoji(issue.severity.value)
                lines.append(
                    f"{icon} `{issue.id}` [{issue.status.value}] "
                    f"**{issue.title}** ({issue.server_name})"
                )
            await interaction.response.send_message("\n".join(lines))

        @bot.tree.command(name="fix", description="Approve a pending fix")
        @app_commands.describe(issue_id="Issue ID to approve")
        async def cmd_fix(interaction: discord.Interaction, issue_id: str) -> None:
            issue = self._registry.get(issue_id)
            if not issue:
                await interaction.response.send_message(f"Issue `{issue_id}` not found.")
                return
            if issue.status != IssueStatus.AWAITING_APPROVAL:
                await interaction.response.send_message(
                    f"Issue `{issue_id}` is not awaiting approval (status: {issue.status.value})."
                )
                return

            await interaction.response.defer()
            issue.status = IssueStatus.APPROVED

            if issue.action_type and issue.action_params:
                issue.status = IssueStatus.EXECUTING
                self._registry.update(issue)

                executor = (
                    self._scheduler._debugger._executor if self._scheduler._debugger else None
                )
                if executor:
                    result = await executor._dispatch(issue.action_type, issue.action_params)
                    if result.status == "ok":
                        issue.resolve()
                        msg = f"Fix applied for `{issue_id}`: {result.message}"
                    else:
                        issue.status = IssueStatus.FAILED
                        msg = f"Fix failed for `{issue_id}`: {result.message}"
                    self._registry.update(issue)
                    await interaction.followup.send(msg)
                else:
                    await interaction.followup.send("No executor available.")
            else:
                issue.resolve()
                self._registry.update(issue)
                await interaction.followup.send(f"Issue `{issue_id}` marked as resolved.")

        @bot.tree.command(name="deny", description="Reject a pending fix")
        @app_commands.describe(issue_id="Issue ID to deny")
        async def cmd_deny(interaction: discord.Interaction, issue_id: str) -> None:
            issue = self._registry.get(issue_id)
            if not issue:
                await interaction.response.send_message(f"Issue `{issue_id}` not found.")
                return
            issue.status = IssueStatus.DENIED
            issue.touch()
            self._registry.update(issue)
            await interaction.response.send_message(f"Issue `{issue_id}` denied.")

        @bot.tree.command(name="debug", description="Start an AI debug session")
        @app_commands.describe(description="Describe the problem or question")
        async def cmd_debug(interaction: discord.Interaction, description: str) -> None:
            if not self._debugger:
                await interaction.response.send_message("AI debugger is not configured.")
                return
            await interaction.response.defer()
            snapshots = await self._scheduler.collect_all_snapshots()
            if not snapshots:
                await interaction.followup.send("No servers reachable.")
                return
            # Use the first snapshot as context (could be extended to multi-server)
            response = await self._debugger.interactive_session(description, snapshots[0])
            # Discord limit
            if len(response) > 2000:
                response = response[:1997] + "..."
            await interaction.followup.send(response)

    async def send_alert(self, issue: Issue) -> None:
        channel = self._alert_channel or self._channel
        if not channel:
            logger.warning("No Discord channel configured for alerts")
            return

        icon = severity_emoji(issue.severity.value)
        embed = discord.Embed(
            title=f"{icon} {issue.title}",
            description=issue.description,
            color=discord.Color.red()
            if issue.severity.value == "critical"
            else discord.Color.orange(),
        )
        embed.add_field(name="Server", value=issue.server_name, inline=True)
        if issue.node:
            embed.add_field(name="Node", value=issue.node, inline=True)
        embed.add_field(name="Severity", value=issue.severity.value.upper(), inline=True)
        embed.add_field(name="ID", value=f"`{issue.id}`", inline=True)

        if issue.ai_analysis:
            analysis = issue.ai_analysis[:1024]
            embed.add_field(name="AI Analysis", value=analysis, inline=False)

        if issue.status == IssueStatus.AWAITING_APPROVAL:
            embed.set_footer(text=f"Use /fix {issue.id} to approve or /deny {issue.id} to reject")

        await channel.send(embed=embed)

    async def send_message(self, text: str) -> None:
        channel = self._channel
        if channel:
            await channel.send(text)

    async def send_action_result(self, result: ActionResult, issue: Issue) -> None:
        channel = self._channel
        if not channel:
            return
        color = discord.Color.green() if result.status == "ok" else discord.Color.red()
        embed = discord.Embed(
            title=f"Action Result — {issue.id}",
            description=result.message,
            color=color,
        )
        if result.output:
            embed.add_field(name="Output", value=f"```\n{result.output[:1024]}\n```", inline=False)
        await channel.send(embed=embed)

    async def start(self) -> None:
        if not self._config.bot_token:
            logger.warning("Discord bot token not configured, skipping")
            return
        self._task = asyncio.create_task(
            self._bot.start(self._config.bot_token),
            name="discord-bot",
        )

    async def stop(self) -> None:
        if self._bot and not self._bot.is_closed():
            await self._bot.close()
        if self._task:
            self._task.cancel()
