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

Install Node.js from the official distribution. This guide used to recommend
`curl -fsSL https://deb.nodesource.com/setup_22.x | sudo bash -`, which **cannot
fail loudly**: a pipeline reports the status of its last command, so when curl
fails, `bash` reads an empty stdin and exits 0, and apt then installs Debian's
Node 18 — which does not ship npm. A one-hour outage of that endpoint on
2026-07-27 was enough to break the production image build this way. The
Dockerfiles now use the official distribution for the same reason.

```bash
# Node 24 LTS — the line CI, the web image and the `engines` lock all run on.
# The exact patch release is resolved from nodejs.org rather than written here,
# so this procedure does not go stale; the checksum is verified, not trusted.
NODE_MAJOR=24
case "$(dpkg --print-architecture)" in
  amd64) NODE_ARCH=x64 ;;
  arm64) NODE_ARCH=arm64 ;;   # Raspberry Pi 5 under a 64-bit OS
  *) echo "unsupported architecture" >&2; exit 1 ;;
esac
BASE="https://nodejs.org/dist/latest-v${NODE_MAJOR}.x"
cd /tmp
curl -fsSL -o SHASUMS256.txt "${BASE}/SHASUMS256.txt"
FILE=$(grep -oE "node-v[0-9]+\.[0-9]+\.[0-9]+-linux-${NODE_ARCH}\.tar\.xz" SHASUMS256.txt | head -1)
curl -fsSL -o "${FILE}" "${BASE}/${FILE}"
grep -F " ${FILE}" SHASUMS256.txt | sha256sum -c -   # must print "OK"
sudo tar -xJf "${FILE}" -C /usr/local --strip-components=1 --no-same-owner
rm -f "${FILE}" SHASUMS256.txt
node -v && npm -v   # verify BOTH: a Node without npm is the failure mode above
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

The `docker-compose.dev.yml` and `docker-compose.prod.yml` mount the host `~/.claude/` directory into the container:

```yaml
volumes:
  # Entire .claude directory (credentials + session data, writable)
  - ~/.claude:/root/.claude              # dev (root user)
  - ~/.claude:/home/appuser/.claude      # prod (appuser)
  # Docker socket for container management
  - /var/run/docker.sock:/var/run/docker.sock
  # Server context for Claude CLI
  - ./infrastructure/claude-cli/CLAUDE.server.md:/opt/claude-workspace/CLAUDE.md:ro
```

**Production Docker socket permissions**: The prod container runs as `appuser` (non-root), which needs access to the Docker socket. The `docker-compose.prod.yml` uses `group_add: "${DOCKER_GID:-999}"` to add the host's Docker group GID. The deploy scripts auto-detect this GID via `stat -c '%g' /var/run/docker.sock` and add `DOCKER_GID=<gid>` to the remote `.env`.

### Step 4: Verify inside the container

```bash
# Dev
docker exec lia-api-dev bash -c "claude auth status"

# Prod
docker exec lia-api-prod bash -c "claude auth status"
```

Expected output: `"loggedIn": true`

### Token renewal

Claude CLI OAuth tokens expire periodically. When you re-authenticate locally (`claude auth login`), the fresh credentials need to be propagated to the containers.

**Dev**: Automatic — the `~/.claude/` directory is bind-mounted from the host, so the container always reads the latest credentials.

**Prod**: Requires copying the fresh credentials to the remote host:
```bash
scp -P <SSH_PORT> ~/.claude/.credentials.json <USER>@<HOST>:~/.claude/.credentials.json
```
The container picks them up immediately (bind-mounted, no restart needed).

This copy is also done automatically at each `task deploy:prod` run. Between deployments, use the `scp` command above if you re-authenticate.

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DEVOPS_ENABLED` | `false` | Enable the DevOps feature |
| `DEVOPS_SSH_TIMEOUT` | `30` | SSH connection timeout (for SSH mode only) |
| `DEVOPS_COMMAND_TIMEOUT` | `300` | Claude CLI execution timeout in seconds |
| `DEVOPS_MAX_OUTPUT_CHARS` | `50000` | Max output chars before truncation |
| `DEVOPS_RATE_LIMIT_CALLS` | `5` | Max `claude_server_task_tool` calls per user per window (anti-runaway: each call is a paid Claude CLI run + real server actions) |
| `DEVOPS_RATE_LIMIT_WINDOW` | `600` | Rate limit window in seconds |
| `DEVOPS_SERVERS` | `[]` | JSON array of server configurations |
| `DOCKER_GID` | `999` | Host Docker group GID (auto-detected by deploy scripts via `stat -c '%g' /var/run/docker.sock`) |

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
| `max_turns` | int | No | ⚠️ **Accepted by the parser, never forwarded** — no code emits `--max-turns`, so this key bounds nothing (see *Layer 2* below). Kept documented as inert rather than removed, because existing `DEVOPS_SERVERS` values carry it. |
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

### SSH Mode (`host: "<your-server-ip>"`)

Claude CLI runs on a remote server via SSH (`asyncssh`). Useful if Claude CLI is installed on a separate host. Requires SSH key authentication.

---

## Security Model

> **State of this section.** It previously described controls that the code did
> not implement (a manifest-level admin role, a mandatory HITL confirmation, and
> a `--max-turns` cap). The confirmation now exists (FN-1, below); the other two
> claims are corrected in place — an operator must not assume a guard rail that
> is not there.

### Layer 1 — LIA (before execution)

- **Admin role check**: enforced **inside the tool**, not by the manifest. `claude_server_task_tool` calls `_check_user_is_admin(user_id)` and returns `FORBIDDEN` for non-superusers. The catalogue manifest carries `allowed_roles=[]`, because the catalogue has no role context at plan time — do not rely on the SemanticValidator for this.
- **Confirmation before execution (FN-1)**: the tool does **not** run the task. It returns a `DEVOPS_TASK` draft showing the target server, the full task text **and the `context` field** — the latter is model-produced and lands in `--append-system-prompt`, so it is the field an injection would use; approving what you cannot see is not approving. The SSH run happens in `execute_devops_task_draft` only after the user confirms, and the admin check is **re-run there**: a superuser revoked between the draft and its confirmation gets nothing executed. This holds **without exception** — including a `resume_session` follow-up, which drives the same CLI with the same powers, and regardless of how "read-only" the task sounds.
  The draft is the mechanism because it is the only one both execution modes honour: the pipeline ignores `hitl_required` (its `approval_gate` is a pass-through) and ReAct would otherwise ask twice. For the same reason the manifest **must keep** `hitl_required=False` — an invariant pinned by `test_hitl_required_consistency.py`.
- **Rate limit**: `@rate_limit` — `DEVOPS_RATE_LIMIT_CALLS` per `DEVOPS_RATE_LIMIT_WINDOW` per user.
- **Audit logging**: Every execution logged with structlog (user_id, server, task, duration)

### Layer 2 — Claude CLI (during execution)

- **`--allowedTools`**: Configurable per server. ⚠️ The default is `("Read", "Grep", "Glob", "Bash")` (`DEVOPS_DEFAULT_ALLOWED_TOOLS`), so a server entry that omits `allowed_claude_tools` **inherits `Bash`**.
- **`--disallowedTools`**: Passed after `--allowedTools`. It is a deny list of patterns, not an allowlist — treat it as defence in depth, not as a boundary.
- **`--max-turns`**: ⚠️ **not passed**. Neither `_build_claude_args` nor the streaming variant emits this flag, so a `max_turns` key in `DEVOPS_SERVERS` bounds nothing and the CLI applies its own default.
- **`--append-system-prompt`**: receives the tool's `context` parameter, which is produced by the model. Content reaching the agent from an untrusted source (email, web page, MCP result) can therefore influence the remote CLI's system prompt.

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
6. [ ] Deploy (rebuild Docker images): `task deploy:prod` (le script `scripts/deploy.sh` n'existe pas — le déploiement prod passe par cette tâche)
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

**Dev (root)**: Verify Docker socket is mounted:
```bash
docker exec lia-api-dev bash -c "docker ps"
```

**Prod (appuser)**: The container needs the host Docker group GID. The deploy scripts auto-detect this, but you can verify/fix manually:
```bash
# Check current groups inside container
docker exec lia-api-prod id
# Should show the Docker GID (e.g. groups=1000(appuser),984)

# If Docker GID is missing, check .env on the host
grep DOCKER_GID ~/lia/.env
# If absent, add it:
echo "DOCKER_GID=$(stat -c '%g' /var/run/docker.sock)" >> ~/lia/.env
# Then recreate the container:
docker compose -f docker-compose.prod.yml up -d --force-recreate api
```

### Automated deployment

The deploy scripts (`deploy.sh` and `deploy-prod.ps1`) handle all DevOps setup automatically:
1. **DOCKER_GID**: Auto-detected from host Docker socket and injected into `.env`
2. **Claude CLI credentials**: Copied from local `~/.claude/.credentials.json` to remote host
3. **CLAUDE.server.md**: Copied to `infrastructure/claude-cli/` on remote host
4. **Docker image**: Claude CLI + Docker CLI + Node.js baked in (Dockerfile.dev/prod)

No manual steps required after initial `claude auth login` on the host.

If permission denied, the socket permissions may need adjustment on the host.
