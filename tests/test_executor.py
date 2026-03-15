import pytest

from janitor.actions.executor import ActionExecutor, ActionResult
from janitor.config import PermissionsConfig, SSHServerConfig


class MockProxmoxClient:
    pass


class MockSSHManager:
    pass


def make_executor(level="semi_auto", allow=None, deny=None):
    perms = PermissionsConfig(
        level=level,
        allow_actions=allow or ["restart_vm", "restart_service"],
        deny_actions=deny or ["run_ssh_command"],
    )
    return ActionExecutor(
        permissions=perms,
        proxmox_clients={},
        ssh_manager=MockSSHManager(),
        ssh_configs={},
    )


@pytest.mark.asyncio
async def test_deny_actions_always_blocked():
    executor = make_executor(level="full_auto")
    result = await executor.execute("run_ssh_command", {"server_name": "x", "command": "ls"})
    assert result.status == "denied"


@pytest.mark.asyncio
async def test_read_only_blocks_all():
    executor = make_executor(level="read_only")
    result = await executor.execute("restart_vm", {"server_name": "x", "node": "n", "vmid": 100})
    assert result.status == "denied"


@pytest.mark.asyncio
async def test_suggest_queues_for_approval():
    executor = make_executor(level="suggest")
    result = await executor.execute("restart_vm", {"server_name": "x", "node": "n", "vmid": 100})
    assert result.status == "pending"


@pytest.mark.asyncio
async def test_semi_auto_allows_listed_actions():
    executor = make_executor(level="semi_auto", allow=["restart_vm"])
    # This will fail because there's no actual Proxmox client, but it should
    # get past the permission check and into dispatch
    result = await executor.execute("restart_vm", {"server_name": "nonexistent", "node": "n", "vmid": 100})
    assert result.status == "failed"  # fails because server not found, but permission passed


@pytest.mark.asyncio
async def test_semi_auto_queues_unlisted_actions():
    executor = make_executor(level="semi_auto", allow=["restart_service"])
    result = await executor.execute("restart_vm", {"server_name": "x", "node": "n", "vmid": 100})
    assert result.status == "pending"
