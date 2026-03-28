# Guide: DevOps — Claude CLI Remote Server Management

**Version**: 1.0
**Last updated**: 2026-03-27
**Status**: Active

---

## Overview

The DevOps feature allows **admin users** to interact with Claude Code CLI installed inside the API Docker containers (dev and prod), enabling autonomous server inspection, log analysis, container management, and diagnostics — all through natural language via the LIA assistant.

**Key benefits**:
- Uses Claude Max/Pro subscription (no API cost)
- Full autonomy of Claude Code (reads logs, inspects containers, diagnoses issues)
- Single polyvalent tool — no need for dozens of specific DevOps tools
- Session persistence for multi-turn investigations (`--resume`)

### Architecture

```
┌─────────────────────────────────────────────────┐
│ Docker Container (lia-api-dev or lia-api-prod)   │
│                                                   │
│  FastAPI API ──→ claude_server_task_tool           │
│                    ↓                               │
│                 asyncio.subprocess                  │
│                    ↓                               │
│                 claude -p "task"                    │
│                    ↓                               │
│                 docker.sock (mounted)               │
│                    → docker logs, ps, stats...      │
│                                                   │
│  /opt/claude-workspace/CLAUDE.md (server context)  │
│  /root/.claude/.credentials.json (auth, mounted)   │
└─────────────────────────────────────────────────┘
```

---

## Prerequisites

Claude CLI requires authentication via OAuth. Since Docker containers are headless (no browser), the authentication must be done **on the host machine** first, and the credentials file is then mounted into the container.

### Step 1: Install Claude CLI on the host

This is needed **only for authentication** — the actual CLI runs inside the container.

**Windows (dev)**:
```bash
npm install -g @anthropic-ai/claude-code
```

**Raspberry Pi / Linux (prod)**:
```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo bash -
sudo apt-get install -y nodejs
sudo npm install -g @anthropic-ai/claude-code
```

### Step 2: Authenticate Claude CLI on the host

```bash
claude auth login
# Opens a browser link → authorize → done
claude auth status
# Should show: loggedIn: true, subscriptionType: max
```

This creates `~/.claude/.credentials.json` on the host.

### Step 3: Docker Compose mounts credentials automatically

The `docker-compose.dev.yml` and `docker-compose.prod.yml` already mount:

```yaml
volumes:
  # Auth credentials from host (read-only)
  - ~/.claude/.credentials.json:/root/.claude/.credentials.json:ro  # dev (root)
  - ~/.claude/.credentials.json:/home/appuser/.claude/.credentials.json:ro  # prod (appuser)
  # Docker socket for container management
  - /var/run/docker.sock:/var/run/docker.sock
  # Server context for Claude CLI
  - ./infrastructure/claude-cli/CLAUDE.server.md:/opt/claude-workspace/CLAUDE.md:ro
  # Persistent auth cache (session data, etc.)
  - claude_auth:/root/.claude  # or /home/appuser/.claude
```

### Step 4: Verify inside the container

```bash
# Dev
docker exec lia-api-dev bash -c "claude auth status"

# Prod
docker exec lia-api-prod bash -c "claude auth status"
```

Expected output: `"loggedIn": true`

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DEVOPS_ENABLED` | `false` | Enable the DevOps feature |
| `DEVOPS_SSH_TIMEOUT` | `30` | SSH connection timeout (for SSH mode only) |
| `DEVOPS_COMMAND_TIMEOUT` | `300` | Claude CLI execution timeout in seconds |
| `DEVOPS_MAX_OUTPUT_CHARS` | `50000` | Max output chars before truncation |
| `DEVOPS_SERVERS` | `[]` | JSON array of server configurations |

### Server Configuration

Each server in `DEVOPS_SERVERS` supports:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Server identifier (e.g. "dev", "prod") |
| `host` | string | Yes | `"local"` for subprocess, or IP/hostname for SSH |
| `port` | int | No | SSH port (SSH mode only, default 22) |
| `username` | string | No | SSH username (SSH mode only) |
| `working_directory` | string | No | Claude CLI working directory (default `/opt/claude-workspace`) |
| `allowed_claude_tools` | list | No | Claude CLI `--allowedTools` |
| `disallowed_claude_tools` | list | No | Claude CLI `--disallowedTools` (takes precedence) |
| `max_turns` | int | No | Claude CLI `--max-turns` (default 30) |
| `description` | string | No | Server description for the LLM planner |

### Example: Dev (full access)

```json
{
  "name": "dev",
  "host": "local",
  "working_directory": "/opt/claude-workspace",
  "max_turns": 30,
  "description": "Local dev container",
  "allowed_claude_tools": ["Read", "Grep", "Glob", "Bash"],
  "disallowed_claude_tools": [
    "Read(.env*)", "Read(*secret*)",
    "Bash(cat *.env*)", "Bash(printenv *)",
    "Bash(docker compose * down *)",
    "Bash(rm -rf *)", "Bash(reboot *)"
  ]
}
```

### Example: Prod (read-only investigation)

```json
{
  "name": "prod",
  "host": "local",
  "working_directory": "/opt/claude-workspace",
  "max_turns": 30,
  "description": "Prod container — read-only",
  "allowed_claude_tools": [
    "Read", "Grep", "Glob",
    "Bash(docker logs *)", "Bash(docker ps *)",
    "Bash(docker stats --no-stream *)", "Bash(docker inspect *)",
    "Bash(docker compose * ps *)", "Bash(docker compose * logs *)",
    "Bash(df *)", "Bash(free *)", "Bash(uptime *)",
    "Bash(journalctl *)", "Bash(curl *localhost*)", "Bash(ss *)"
  ],
  "disallowed_claude_tools": [
    "Edit", "Write",
    "Bash(docker restart *)", "Bash(docker stop *)",
    "Bash(docker rm *)", "Bash(docker exec *)",
    "Read(.env*)", "Read(*secret*)",
    "Bash(rm *)", "Bash(systemctl *)", "Bash(reboot *)"
  ]
}
```

---

## Execution Modes

### Local Mode (`host: "local"`)

Claude CLI runs directly inside the API container via `asyncio.create_subprocess_exec`. No SSH involved. This is the default for both dev and prod.

### SSH Mode (`host: "192.168.0.14"`)

Claude CLI runs on a remote server via SSH (`asyncssh`). Useful if Claude CLI is installed on a separate host. Requires SSH key authentication.

---

## Security Model

### Layer 1 — LIA (before execution)

- **Admin role check**: `PermissionProfile.allowed_roles=["admin"]` enforced by the SemanticValidator
- **HITL approval**: `hitl_required=True` — user must confirm before each execution
- **Audit logging**: Every execution logged with structlog (user_id, server, task, duration)

### Layer 2 — Claude CLI (during execution)

- **`--allowedTools`**: Configurable per server (granular Bash prefix patterns)
- **`--disallowedTools`**: Always takes precedence over allowed (deny > allow)
- **Shell-aware**: Claude CLI understands shell operators — `Bash(docker logs *)` does NOT permit `docker logs x && rm -rf /`
- **`--max-turns`**: Limits iterations (default 30)

### Layer 3 — Infrastructure

- **Docker socket**: Mounted read-write for container management
- **Credentials**: Mounted read-only from host
- **CLAUDE.md**: Contains security rules (never expose secrets, prefer read-only)

---

## Deployment Checklist

### First-time setup (per environment)

1. [ ] Install Claude CLI on the host: `npm install -g @anthropic-ai/claude-code`
2. [ ] Authenticate: `claude auth login` (creates `~/.claude/.credentials.json`)
3. [ ] Verify: `claude auth status` shows `loggedIn: true`
4. [ ] Configure `DEVOPS_ENABLED=true` in `.env` / `.env.prod`
5. [ ] Configure `DEVOPS_SERVERS=[...]` with appropriate permissions
6. [ ] Deploy (rebuild Docker images): `task dev` or `./scripts/deploy.sh`
7. [ ] Verify in container: `docker exec -it lia-api-dev claude auth status`

### Subsequent deployments

No action needed — credentials are mounted from host, Claude CLI is in the Docker image.

### Token refresh

Claude CLI OAuth tokens auto-refresh. If auth expires:
1. Re-run `claude auth login` on the host
2. Container picks up new credentials automatically (read-only mount)

---

## Usage Examples

From the LIA assistant (as admin):

- "Check the API logs for errors in the last hour"
- "What's the disk usage on the server?"
- "Why is the API responding slowly? Investigate."
- "Show me the status of all Docker containers"
- "Continue the previous investigation" (uses `--resume`)

---

## Troubleshooting

### Claude CLI not found in container

Rebuild the Docker image:
```bash
docker compose -f docker-compose.dev.yml build api --no-cache
docker compose -f docker-compose.dev.yml up -d api
```

### Auth not working in container

Check that credentials are mounted:
```bash
docker exec lia-api-dev bash -c "cat /root/.claude/.credentials.json | head -c 50"
```

If empty, verify host auth: `claude auth status` on the host machine.

### Docker commands fail inside container

Verify Docker socket is mounted:
```bash
docker exec lia-api-dev bash -c "docker ps"
```

If permission denied, the socket permissions may need adjustment on the host.
