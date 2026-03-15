from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

from janitor.actions.executor import ActionExecutor
from janitor.ai.debugger import AIDebugger
from janitor.ai.provider import create_provider
from janitor.config import JanitorConfig, SSHServerConfig, load_config
from janitor.models.registry import IssueRegistry
from janitor.notifications.base import MultiNotifier
from janitor.notifications.discord_bot import DiscordBot
from janitor.notifications.telegram_bot import TelegramBot
from janitor.proxmox.client import ProxmoxClient
from janitor.scheduler import Scheduler
from janitor.ssh.client import SSHManager
from janitor.utils.logging import setup_logging

logger = logging.getLogger(__name__)


def _resolve_ssh_configs(config: JanitorConfig) -> dict[str, SSHServerConfig]:
    """Build per-server SSH configs, falling back to global ssh settings."""
    configs: dict[str, SSHServerConfig] = {}
    for server in config.proxmox_servers:
        if server.ssh:
            cfg = server.ssh
            if not cfg.key_path:
                cfg = SSHServerConfig(
                    host=cfg.host,
                    port=cfg.port,
                    user=cfg.user,
                    key_path=config.ssh.key_path,
                )
            configs[server.name] = cfg
        else:
            # Use server host with global SSH defaults
            configs[server.name] = SSHServerConfig(
                host=server.host,
                port=22,
                user="root",
                key_path=config.ssh.key_path,
            )
    return configs


async def _run(config: JanitorConfig) -> None:
    # Initialize Proxmox clients
    proxmox_clients: dict[str, ProxmoxClient] = {}
    for server in config.proxmox_servers:
        client = ProxmoxClient(server)
        try:
            await client.connect()
            proxmox_clients[server.name] = client
        except Exception:
            logger.exception("Failed to connect to Proxmox server %s", server.name)

    if not proxmox_clients:
        logger.error("No Proxmox servers connected. Exiting.")
        return

    # SSH manager
    ssh_manager = SSHManager(config.ssh)
    ssh_configs = _resolve_ssh_configs(config)

    # Issue registry
    registry = IssueRegistry(persist_path="issues.json")

    # Action executor
    executor = ActionExecutor(
        permissions=config.permissions,
        proxmox_clients=proxmox_clients,
        ssh_manager=ssh_manager,
        ssh_configs=ssh_configs,
    )

    # AI provider + debugger
    debugger: AIDebugger | None = None
    try:
        provider = create_provider(config.ai)
        debugger = AIDebugger(provider=provider, executor=executor)
        logger.info("AI debugger initialized (%s / %s)", config.ai.provider, config.ai.model)
    except Exception:
        logger.warning("AI provider not available, running without AI analysis")

    # Build notifiers
    notifiers = []

    # Scheduler (need to create before bots so bots can reference it)
    # We'll set the notifier after building the bots
    scheduler = Scheduler(
        proxmox_clients=proxmox_clients,
        ssh_manager=ssh_manager,
        ssh_configs=ssh_configs,
        monitoring_cfg=config.monitoring,
        registry=registry,
        notifier=MultiNotifier([]),  # placeholder, replaced below
        debugger=debugger,
    )

    if config.notifications.discord.enabled:
        discord_bot = DiscordBot(
            config=config.notifications.discord,
            registry=registry,
            scheduler=scheduler,
            debugger=debugger,
        )
        notifiers.append(discord_bot)

    if config.notifications.telegram.enabled:
        telegram_bot = TelegramBot(
            config=config.notifications.telegram,
            registry=registry,
            scheduler=scheduler,
            debugger=debugger,
        )
        notifiers.append(telegram_bot)

    # Wire up the real notifier
    multi_notifier = MultiNotifier(notifiers)
    scheduler._notifier = multi_notifier

    # Graceful shutdown
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("Shutdown signal received")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    # Start notifiers
    for n in notifiers:
        await n.start()

    logger.info("[bold green]Janitor started[/] — monitoring %d server(s)", len(proxmox_clients))

    # Run scheduler until shutdown
    scheduler_task = asyncio.create_task(scheduler.run(), name="scheduler")

    await shutdown_event.wait()

    # Cleanup
    logger.info("Shutting down...")
    scheduler.stop()
    scheduler_task.cancel()
    for n in notifiers:
        await n.stop()
    await ssh_manager.close_all()


def main() -> None:
    setup_logging()

    config_path = "config.yaml"
    if len(sys.argv) > 1:
        config_path = sys.argv[1]

    if not Path(config_path).exists():
        logger.error(
            "Config file not found: %s\n"
            "Copy config.example.yaml to config.yaml and fill in your values.",
            config_path,
        )
        sys.exit(1)

    config = load_config(config_path)
    asyncio.run(_run(config))


if __name__ == "__main__":
    main()
