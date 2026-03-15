"""AI tool definitions — these are the tools the AI agent can invoke."""

TOOL_DEFINITIONS = [
    {
        "name": "get_node_metrics",
        "description": "Get current CPU, RAM, disk, and load metrics for a specific Proxmox node.",
        "input_schema": {
            "type": "object",
            "properties": {
                "server_name": {"type": "string", "description": "Name of the Proxmox server"},
                "node": {"type": "string", "description": "Node name"},
            },
            "required": ["server_name", "node"],
        },
    },
    {
        "name": "get_vm_list",
        "description": "List all VMs and LXC containers on a node with their current status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "server_name": {"type": "string", "description": "Name of the Proxmox server"},
                "node": {
                    "type": "string",
                    "description": "Node name (optional, lists all if omitted)",
                },
            },
            "required": ["server_name"],
        },
    },
    {
        "name": "get_logs",
        "description": "Retrieve recent system journal logs from a Proxmox node via SSH.",
        "input_schema": {
            "type": "object",
            "properties": {
                "server_name": {"type": "string", "description": "Name of the Proxmox server"},
                "lines": {
                    "type": "integer",
                    "description": "Number of log lines to retrieve",
                    "default": 100,
                },
                "unit": {"type": "string", "description": "Systemd unit to filter logs (optional)"},
            },
            "required": ["server_name"],
        },
    },
    {
        "name": "restart_vm",
        "description": "Restart (reboot) a VM or LXC container on a Proxmox node.",
        "input_schema": {
            "type": "object",
            "properties": {
                "server_name": {"type": "string", "description": "Name of the Proxmox server"},
                "node": {"type": "string", "description": "Node name"},
                "vmid": {"type": "integer", "description": "VM or container ID"},
                "vm_type": {"type": "string", "enum": ["qemu", "lxc"], "default": "qemu"},
            },
            "required": ["server_name", "node", "vmid"],
        },
    },
    {
        "name": "restart_service",
        "description": "Restart a systemd service on a Proxmox node via SSH.",
        "input_schema": {
            "type": "object",
            "properties": {
                "server_name": {"type": "string", "description": "Name of the Proxmox server"},
                "service": {"type": "string", "description": "Systemd service name to restart"},
            },
            "required": ["server_name", "service"],
        },
    },
    {
        "name": "run_ssh_command",
        "description": (
            "Run an arbitrary shell command on a Proxmox node via SSH."
            " Requires explicit permission."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "server_name": {"type": "string", "description": "Name of the Proxmox server"},
                "command": {"type": "string", "description": "Shell command to execute"},
            },
            "required": ["server_name", "command"],
        },
    },
]

# Tools that are always read-only and don't need permission gating
READ_ONLY_TOOLS = {"get_node_metrics", "get_vm_list", "get_logs"}
