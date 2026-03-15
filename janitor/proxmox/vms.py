from __future__ import annotations

from janitor.models.metrics import VMStatus
from janitor.proxmox.client import ProxmoxClient


async def collect_vm_status(client: ProxmoxClient) -> list[VMStatus]:
    nodes = await client.get_nodes()
    results: list[VMStatus] = []

    for node_info in nodes:
        node_name = node_info["node"]

        # QEMU VMs
        for vm in await client.get_vms(node_name):
            results.append(
                VMStatus(
                    server_name=client.config.name,
                    node=node_name,
                    vmid=vm["vmid"],
                    name=vm.get("name", f"vm-{vm['vmid']}"),
                    vm_type="qemu",
                    status=vm.get("status", "unknown"),
                    cpu_percent=vm.get("cpu", 0) * 100,
                    ram_used_bytes=vm.get("mem", 0),
                    ram_total_bytes=vm.get("maxmem", 0),
                )
            )

        # LXC containers
        for ct in await client.get_containers(node_name):
            results.append(
                VMStatus(
                    server_name=client.config.name,
                    node=node_name,
                    vmid=ct["vmid"],
                    name=ct.get("name", f"ct-{ct['vmid']}"),
                    vm_type="lxc",
                    status=ct.get("status", "unknown"),
                    cpu_percent=ct.get("cpu", 0) * 100,
                    ram_used_bytes=ct.get("mem", 0),
                    ram_total_bytes=ct.get("maxmem", 0),
                )
            )

    return results
