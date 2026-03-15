# Proxmox Janitor

An AI-powered monitoring agent for Proxmox VE servers. It watches your nodes, detects issues, uses AI to analyze and debug problems, and communicates with you through Discord (or Telegram).

## Features

- **Automated Monitoring** — Polls Proxmox nodes on a configurable interval for CPU, RAM, disk, load, VM/container status, storage pools, SMART health, and service status
- **AI Debugging** — When an anomaly is detected, an AI agent analyzes metrics and logs, uses tools to gather more context, and produces a root cause analysis with a suggested fix
- **Discord Bot** — Slash commands for on-demand status checks, log retrieval, and interactive AI debug sessions
- **Permission-Gated Actions** — Four permission levels control what the AI can do autonomously vs. what requires your approval
- **Multi-Server** — Monitor multiple Proxmox servers from a single instance
- **Multi-Provider AI** — Supports Anthropic (Claude), OpenAI, OpenRouter, and Ollama (local models)

## Quick Start

### 1. Configure

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` with your:
- Proxmox server IPs and API tokens (or SSH keys)
- Discord bot token and channel ID
- AI provider and API key
- Permission level and thresholds

### 2. Run with Docker

```bash
docker compose up -d
```

### 3. Run without Docker

```bash
python -m venv .venv
source .venv/bin/activate
pip install .
janitor
```

Or specify a custom config path:

```bash
janitor /path/to/config.yaml
```

## Discord Commands

| Command | Description |
|---|---|
| `/status` | Health overview of all servers |
| `/nodes` | List all Proxmox nodes with metrics |
| `/vms [server] [node]` | List VMs/containers and their status |
| `/logs <server> [lines]` | Fetch recent system journal |
| `/debug <description>` | Start an interactive AI debug session |
| `/issues` | List open/pending issues |
| `/fix <issue_id>` | Approve a pending AI-suggested fix |
| `/deny <issue_id>` | Reject a pending fix |

## Permission Levels

| Level | Behavior |
|---|---|
| `read_only` | Monitor and alert only — no actions taken |
| `suggest` | AI proposes fixes, you must `/fix` to approve each one |
| `semi_auto` | AI auto-executes actions in `allow_actions`, asks for the rest |
| `full_auto` | AI executes everything not in `deny_actions` |

Default is `semi_auto`. Fine-tune with `allow_actions` and `deny_actions` lists in config.

## Proxmox Authentication

Two methods supported per server:

- **API Token** (recommended) — Create a token in Proxmox UI under Datacenter > Permissions > API Tokens
- **SSH Key** — Uses SSH backend for API access; the same key handles both API and shell commands

## AI Providers

| Provider | Config |
|---|---|
| Anthropic (Claude) | `provider: "anthropic"`, set `api_key` |
| OpenAI | `provider: "openai"`, set `api_key` |
| OpenRouter | `provider: "openrouter"`, set `api_key` and `base_url` |
| Ollama (local) | `provider: "ollama"`, set `base_url` (defaults to `http://localhost:11434/v1`) |

## Configuration Reference

See [`config.example.yaml`](config.example.yaml) for the full schema with comments. Sensitive values support `${ENV_VAR}` syntax for environment variable injection.

## License

MIT
