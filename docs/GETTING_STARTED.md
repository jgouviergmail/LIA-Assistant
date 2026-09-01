# Getting Started - LIA

> Complete guide to install, configure, and get started with LIA — Multi-Agent AI Assistant.
> Every default value in this guide is the **production-proven configuration** actually running in production; you can adopt them as-is with confidence.

**Version**: 4.0
**Last Updated**: 2026-08-22
**Compatibility**: LIA v1.38.4

## Table of Contents

- [Project Overview](#project-overview)
- [Prerequisites](#prerequisites)
- [Step-by-Step Installation](#step-by-step-installation)
- [Environment Configuration](#environment-configuration)
- [Starting the Services](#starting-the-services)
- [First Steps](#first-steps)
- [External Platform Setup](#external-platform-setup)
- [Feature Configuration Reference](#feature-configuration-reference)
- [LLM Configuration](#llm-configuration)
- [Python Dependency Management](#python-dependency-management)
- [Running Tests](#running-tests)
- [Troubleshooting](#troubleshooting)
- [Production Deployment](#production-deployment)
- [Next Steps](#next-steps)
- [Final Checklist](#final-checklist)

---

## Project Overview

**LIA** is a multi-agent conversational AI assistant built with **FastAPI**, **Next.js** and **LangGraph**. It orchestrates 19+ specialized agents and 76 tools across Google, Microsoft and Apple services (contacts, emails, calendar, files, tasks), plus Places, Routes, Weather, Wikipedia, Perplexity, Brave Search, web fetch, browser control, Philips Hue, image generation and per-user MCP servers.

Two user-toggleable execution modes (switchable in the chat header):

- **Pipeline mode** (default) — deterministic and economical: Router → Planner → Semantic Validator → Task Orchestrator → Domain Agents → Response. Roughly 4-8× fewer tokens than ReAct.
- **ReAct mode** — autonomous iterative reasoning loop for exploratory or ambiguous queries.

Both modes converge on the same streaming response (SSE) and the same HITL (Human-in-the-Loop) approval system.

### Key Figures

| | |
|---|---|
| Specialized agents | 19+ |
| Tools | 76 |
| LLM providers (text) | 7 — OpenAI, Anthropic, DeepSeek, Google Gemini, Qwen, Perplexity, Ollama |
| Voice providers | ElevenLabs (STT/TTS), Edge TTS (free), OpenAI TTS + local Whisper STT |
| Configurable LLM slots | 54 (admin UI, hot-reloaded) |
| UI languages | 6 — fr, en, es, de, it, zh |
| Prometheus metrics | 419 |
| Grafana dashboards | 25 |
| Built-in FAQ knowledge base | 200+ Q/A (auto-indexed at startup) |

### Technical Architecture

| Layer | Technologies | Versions |
|-------|--------------|----------|
| **Backend** | FastAPI + LangGraph + SQLAlchemy | FastAPI 0.136.3, LangGraph 1.2.11, LangChain 1.3.15, SQLAlchemy 2.0.50, Python 3.14 |
| **Frontend** | Next.js + React + TailwindCSS | Next.js 16.2.11, React 19.2.7 |
| **Database** | PostgreSQL + pgvector | PostgreSQL 16 (`pgvector/pgvector:pg16`) |
| **Cache/Sessions** | Redis | Redis 7.4 |
| **Observability** | Prometheus + Grafana + Loki + Tempo (+ Langfuse in dev) | Prometheus 3.0.0, Grafana 11.3.0, Loki 3.2.1, Tempo 2.6.1 |
| **Backups** | pg_dump sidecar with 3-tier rotation | `postgres-backup-local:16-alpine` |

### Capabilities & Integrations

| Capability | Description | Integration |
|--------|-------------|-----------|
| **Contacts** | Contact management | Google People API / Microsoft Graph / Apple CardDAV |
| **Emails** | Read/send/organize emails | Gmail API / Microsoft Graph / Apple IMAP-SMTP |
| **Calendar** | Event management | Google Calendar API / Microsoft Graph / Apple CalDAV |
| **Files** | File search | Google Drive API |
| **Tasks** | Task management | Google Tasks API / Microsoft To Do |
| **Places** | Location search | Google Places API (New) |
| **Routes** | Directions and itineraries | Google Routes API |
| **Weather** | Real-time weather & forecast | OpenWeatherMap (per-user API key connector) |
| **Wikipedia** | Encyclopedia search | Wikipedia API |
| **Perplexity** | AI-powered web search | Perplexity API |
| **Brave Search** | Web search | Per-user API key connector |
| **Web Fetch** | Web page extraction | Built-in |
| **Browser Control** | Autonomous interactive browsing | Playwright + ReAct agent |
| **Smart Home** | Philips Hue lights | Local press-link or remote OAuth2 |
| **Telegram** | Bidirectional chat channel (text, voice, HITL) | Telegram Bot API |
| **Health Metrics** | iPhone Shortcuts ingestion + insights | Token-authenticated API |
| **Image Generation** | AI image creation/editing | gpt-image / Imagen / Stability (admin catalogue) |
| **MCP** | External tool servers (admin + per-user, OAuth 2.1) | Model Context Protocol |
| **Sandboxed Python** | Short scripts the autonomous mode writes and runs to compute rather than estimate | Skills sandbox (Docker, no network) |

Beyond integrations, LIA ships assistant-level systems configured later in this guide: long-term memory, interest learning, personal journals, psychological state (Psyche), proactive Heartbeat notifications, Today Briefing home page, RAG knowledge spaces, sub-agents, skills, scheduled actions and per-user usage limits.

---

## Prerequisites

### Operating System

| OS | Version | Notes |
|----|---------|-------|
| **Linux** | Ubuntu 22.04+, Debian 11+, Fedora 38+ | Native, best performance |
| **macOS** | 12 (Monterey)+ | Docker Desktop required |
| **Windows** | 10/11 | Docker Desktop (WSL2) — the reference dev setup |

Production reference platform: Raspberry Pi 5 (linux/arm64) — all images are multi-arch (amd64 + arm64).

### Required Tools

| Tool | Minimum Version | Installation | Verification |
|------|-----------------|--------------|--------------|
| **Python** | 3.14+ | [python.org](https://www.python.org/) | `python --version` |
| **Node.js** | 24.x (LTS) | [nodejs.org](https://nodejs.org/) | `node --version` |
| **pnpm** | 10.x+ | `npm install -g pnpm` | `pnpm --version` |
| **Docker** | 24.x+ | [docker.com](https://www.docker.com/) | `docker --version` |
| **Docker Compose** | 2.x+ | Included with Docker Desktop | `docker compose version` |
| **Git** | 2.40+ | [git-scm.com](https://git-scm.com/) | `git --version` |
| **Task** | 3.x+ | [taskfile.dev](https://taskfile.dev/installation/) | `task --version` |

> **Task is the project's build tool** — every workflow command (`task setup`, `task dev`, `task test:*`, `task db:*`) is defined in `Taskfile.yml`. Manual equivalents are given where useful, but installing Task is strongly recommended.

### Optional Tools

| Tool | Usage | Installation |
|------|-------|--------------|
| **uv** | Regenerating Python lockfiles (`task deps:lock`) — not needed to install/run | [astral.sh/uv](https://docs.astral.sh/uv/) |
| **SOPS + Age** | Encrypting production secrets | `brew install sops age` / `choco install sops age` |
| **jq** | JSON parsing (logs) | `apt install jq` / `brew install jq` |
| **Redis CLI** | Debug cache & sessions | `apt install redis-tools` |

### Required API Accounts

#### Mandatory

| Service | Usage | Sign Up |
|---------|-------|---------|
| **At least one LLM provider** | Configured via Admin UI after first login (keys encrypted in DB) | OpenAI / Anthropic / DeepSeek / Gemini / Qwen — see [LLM Configuration](#llm-configuration) |

> The production configuration uses **DeepSeek** (primary), **OpenAI**, **Google Gemini** and **ElevenLabs** (voice). OpenAI alone is enough to start: every slot can be repointed from the Admin UI.

#### Optional (Depending on Features)

| Service | Usage | Sign Up |
|---------|-------|---------|
| **Google Cloud** | Google OAuth login + Google connectors + Places/Routes | [console.cloud.google.com](https://console.cloud.google.com/) |
| **Microsoft Azure** | Microsoft 365 connectors (Outlook, Calendar, Contacts, To Do) | [portal.azure.com](https://portal.azure.com/) |
| **Firebase** | Push notifications (FCM) | [console.firebase.google.com](https://console.firebase.google.com/) |
| **ElevenLabs** | Premium STT (Scribe) + TTS | [elevenlabs.io](https://elevenlabs.io/) |
| **Perplexity** | AI-powered web search | [perplexity.ai/settings/api](https://www.perplexity.ai/settings/api) |
| **OpenWeatherMap** | Weather (free tier) — connected per user in Settings > Connectors | [openweathermap.org/api](https://openweathermap.org/api) |
| **Telegram** | Multi-channel chat (bot via @BotFather) | [t.me/BotFather](https://t.me/BotFather) |

---

## Step-by-Step Installation

### Step 1: Clone the Repository

```bash
git clone https://github.com/jgouviergmail/LIA-Assistant.git lia
cd lia
git branch  # Should display: * main
```

### Step 2: Full Setup with Task (Recommended)

```bash
# Backend venv + lockfile install, frontend pnpm install, git hooks
task setup
```

This runs three sub-tasks you can also invoke individually: `task setup:backend`, `task setup:frontend`, `task setup:hooks`.

<details>
<summary><strong>Manual equivalent (without Task)</strong></summary>

#### Backend (from `apps/api/`)

```bash
cd apps/api

# Create the Python 3.14 virtual environment (named .venv)
python -m venv .venv

# Activate it
source .venv/bin/activate        # Linux/macOS
.venv\Scripts\Activate.ps1       # Windows PowerShell

# Install from the compiled universal lockfile (reproducible, hash-verified — ADR-112)
pip install --require-hashes -r requirements-dev.lock.txt
```

> **Do not** `pip install -r requirements.txt` — the `requirements*.txt` files are *intent manifests* with loose pins. Every environment (prod image, dev container, CI, local venv) installs from the compiled lockfiles `requirements.lock.txt` (runtime) / `requirements-dev.lock.txt` (dev). See [Python Dependency Management](#python-dependency-management).

#### Frontend (from `apps/web/`)

```bash
cd ../web
pnpm install
pnpm list next  # next 16.2.7
```

#### Git hooks

```bash
git config core.hooksPath .github/hooks
```

</details>

**Estimated time**: 4-6 minutes depending on connection speed.

### Step 3: Configure Environment Variables

```bash
# From the project root
cp .env.example .env
```

Then edit `.env` — see [Environment Configuration](#environment-configuration) for the mandatory minimum and key generation.

> **Single `.env` file**: all variables — backend, frontend `NEXT_PUBLIC_*`, observability — live in the **root `.env`**. Both the `api` and `web` containers load it via `env_file`. There is no `apps/web/.env.local` in the Docker workflow.

### Step 4: Start the Docker Infrastructure

```bash
# Start the dev environment — 17 services (foreground: task dev)
task dev:detach
# equivalent: docker compose -f docker-compose.dev.yml up -d --build

# Optional: start WITH the Langfuse LLM-tracing stack (6 extra services, opt-in compose profile)
task dev:langfuse

# Verify all services are "healthy"
docker compose -f docker-compose.dev.yml ps

# Follow logs
docker compose -f docker-compose.dev.yml logs -f api
```

See [Launched Docker Services](#launched-docker-services) for the full service/port table.

### Step 5: Apply Migrations

```bash
task db:migrate
# equivalent: cd apps/api && alembic upgrade head   (venv activated)
```

> Migrations are also applied automatically when the API container starts; running them explicitly here makes the first boot deterministic.

### Step 6: Create the Admin User and Seed Data

```bash
# Option A: Full reset (drop + migrate + admin + seed + SQL seeds) — recommended for first setup
task db:reset

# Option B: Step by step
task db:create-admin     # Creates admin user (admin@example.com / admin123)
task db:seed             # Seeds dev users and connectors
task db:seed:sql         # Seeds personalities and LLM pricing data

# Option C: Custom admin credentials
task db:create-admin -- --email you@example.com --password YourSecurePassword123
```

**Default admin account** (created by `task db:create-admin`):

| Field | Value |
|-------|-------|
| Email | `admin@example.com` |
| Password | `admin123` |
| Role | Superuser (full admin access) |

> **Important**: Change the default admin password after first login (Settings > Account).

> **Note**: `task db:seed:sql` populates assistant personalities and LLM pricing data. Without it, the assistant has no personality and cost tracking cannot price calls. This task targets the **dev** database directly; the production equivalent is the explicit `APPLY_SEEDS=true` procedure described in [Reference Content on a Fresh Production Install](#reference-content-on-a-fresh-production-install).

> **Note**: The built-in FAQ knowledge base (200+ Q/A) is automatically indexed at app startup. Manual re-indexation: `task db:seed:system-rag`.

### Step 7: Configure an LLM Provider Key (Mandatory First-Run Step)

LLM API keys are **not** read from `.env` in normal operation — they are managed in the database, encrypted (Fernet), via the Admin UI:

1. Open https://localhost:3000 and accept the self-signed certificate (dev serves HTTPS)
2. Also open https://localhost:8000/docs once and accept the API certificate
3. Log in with the admin account
4. Go to **Settings > Administration > LLM Configuration**
5. In **Provider Keys**, enter the API key for at least one provider (e.g. OpenAI)
6. Changes are hot-reloaded across workers — no restart needed

`.env` keys (e.g. `OPENAI_API_KEY`) are only a **fallback** used when no database key exists for a provider.

### Step 8 (later): moving this installation to a newer release

Installing is one procedure; upgrading is another, and the installer owns only
the first — `./install.sh --resume` is fail-closed and will refuse once the
release files change, which is the guard working rather than a defect. The
written upgrade procedure lives in
[GUIDE_SELF_HOSTING.md — Upgrading to a newer release](./guides/GUIDE_SELF_HOSTING.md#upgrading-to-a-newer-release).

Its first step is the database backup, and that ordering is not a style
preference: migrations are applied by the API container's entrypoint the moment
it starts, and this project ships no downgrade path.

---

## Environment Configuration

### Generating Cryptographic Keys

```bash
# SECRET_KEY (JWT & sessions, 32+ chars)
openssl rand -base64 32

# FERNET_KEY (encryption of OAuth credentials and provider API keys)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# REDIS_PASSWORD / POSTGRES_PASSWORD
openssl rand -base64 16
```

### Minimum Configuration (`.env`)

The mandatory variables, with the production-proven values as reference (`ENVIRONMENT`, `DEBUG`, `LOG_LEVEL` and URLs are the only ones that differ between dev and prod):

```bash
# ============================================================================
# [01] ENVIRONMENT
# ============================================================================
ENVIRONMENT=development          # production in prod
DEBUG=true                       # false in prod
LOG_LEVEL=DEBUG                  # INFO in prod

# ============================================================================
# [02] SECURITY & AUTHENTICATION (MANDATORY — generate unique values!)
# ============================================================================
SECRET_KEY=CHANGE_ME_MIN_32_CHARS          # openssl rand -base64 32
ALGORITHM=HS256                            # HMAC only: HS256 / HS384 / HS512
FERNET_KEY=CHANGE_ME_FERNET_KEY            # see command above

# Session cookies (production-proven)
SESSION_COOKIE_NAME=lia_session
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_HTTPONLY=true
SESSION_COOKIE_SAMESITE=lax
SESSION_COOKIE_MAX_AGE=604800              # 7 days
SESSION_COOKIE_MAX_AGE_REMEMBER=2592000    # 30 days ("remember me")

# ============================================================================
# [03] DATABASE (PostgreSQL)
# ============================================================================
POSTGRES_USER=lia
POSTGRES_PASSWORD=CHANGE_ME_PASSWORD
POSTGRES_DB=lia
DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}

# SQLAlchemy pool (production values)
DATABASE_POOL_SIZE=30
DATABASE_MAX_OVERFLOW=30
DATABASE_POOL_TIMEOUT=30
DATABASE_POOL_RECYCLE=1800

# LangGraph checkpoint/store connection pools, per worker (ADR-111)
LANGGRAPH_CHECKPOINT_POOL_MIN_SIZE=1
LANGGRAPH_CHECKPOINT_POOL_MAX_SIZE=8
LANGGRAPH_STORE_POOL_MIN_SIZE=1
LANGGRAPH_STORE_POOL_MAX_SIZE=4

# ============================================================================
# [04] REDIS
# ============================================================================
REDIS_PASSWORD=CHANGE_ME_PASSWORD
REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
REDIS_SESSION_DB=1
REDIS_CACHE_DB=2
REDIS_MAX_CONNECTIONS=100

# ============================================================================
# [05] URLS & CORS  (dev values; see .env.min.prod for the prod shape)
# ============================================================================
CORS_ORIGINS=https://localhost:3000,https://localhost:8000
FRONTEND_URL=https://localhost:3000
API_URL=https://localhost:8000
NEXT_PUBLIC_API_URL=https://localhost:8000
NEXT_PUBLIC_APP_URL=https://localhost:3000
NEXT_PUBLIC_APP_NAME=LIA
DEFAULT_LANGUAGE=fr

# ============================================================================
# [06] LLM PROVIDERS
# ============================================================================
# API keys are managed via the Admin UI (encrypted in DB, hot-reloaded).
# .env keys are only a fallback if no database key exists for a provider.
# Ollama needs no key, only a base URL:
OLLAMA_BASE_URL=http://host.docker.internal:11434/v1

# ============================================================================
# [07] GOOGLE OAUTH (required for Google login + Google connectors)
# ============================================================================
GOOGLE_CLIENT_ID=YOUR_CLIENT_ID.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=YOUR_CLIENT_SECRET
GOOGLE_REDIRECT_URI=https://localhost:8000/api/v1/auth/google/callback
NEXT_PUBLIC_GOOGLE_CLIENT_ID=YOUR_CLIENT_ID.apps.googleusercontent.com
# API key for Places / Routes / Geocoding (see External Platform Setup)
GOOGLE_API_KEY=...

# ============================================================================
# [08] DATABASE BACKUP (safe defaults apply if omitted — ADR-109)
# ============================================================================
POSTGRES_BACKUP_SCHEDULE=@daily
POSTGRES_BACKUP_KEEP_DAYS=7
POSTGRES_BACKUP_KEEP_WEEKS=4
POSTGRES_BACKUP_KEEP_MONTHS=6
POSTGRES_BACKUP_EXTRA_OPTS=-Z6 --clean --if-exists
POSTGRES_BACKUP_TZ=Etc/UTC

# ============================================================================
# [09] OBSERVABILITY UIS (dev)
# ============================================================================
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=admin
PGADMIN_DEFAULT_EMAIL=admin@lia.local
PGADMIN_DEFAULT_PASSWORD=admin
```

> For production, start from **`.env.min.prod`** (the minimal working set with `CHANGE_ME` placeholders) or **`.env.prod.example`** (the full template, ~740 settings). Everything not listed above has sensible defaults; the [Feature Configuration Reference](#feature-configuration-reference) documents the production values of every subsystem.

### LAN Access & SSL (Development)

Both dev containers serve **HTTPS with self-signed certificates** (required for Google OAuth and service workers). The `ssl-init` service generates certificates once and shares them with `api` and `web` via a Docker volume.

To access LIA from other devices on your network (e.g. mobile testing), use [nip.io](https://nip.io):

1. Find your local IP (e.g. `192.168.1.100`)
2. Set in `.env` (the nip.io domain replaces localhost in the public-facing URLs and is **added** to the CORS origins):

   ```bash
   SSL_DOMAIN=192.168.1.100.nip.io
   CORS_ORIGINS=https://localhost:3000,https://localhost:8000,https://192.168.1.100.nip.io:3000,https://192.168.1.100.nip.io:8000
   FRONTEND_URL=https://192.168.1.100.nip.io:3000
   API_URL=https://192.168.1.100.nip.io:8000
   NEXT_PUBLIC_API_URL=https://192.168.1.100.nip.io:8000
   NEXT_PUBLIC_APP_URL=https://192.168.1.100.nip.io:3000
   NEXT_PUBLIC_ALLOWED_DEV_ORIGINS=192.168.1.100.nip.io
   GOOGLE_REDIRECT_URI=https://192.168.1.100.nip.io:8000/api/v1/auth/google/callback
   ```

3. If you use Google OAuth, also add the nip.io redirect URIs (auth + connectors) to the OAuth client in the Google Cloud Console.

4. Restart, then browse to `https://192.168.1.100.nip.io:8000` **and** `:3000` and accept both certificates.

> **Important**: `NEXT_PUBLIC_ALLOWED_DEV_ORIGINS` must be a **hostname only** (no protocol/port). A full URL causes WebSocket HMR failures and refresh loops.

### WebAuthn / Passkeys in Development (Trusted Certificate Required)

Chromium **refuses every WebAuthn ceremony on a site whose TLS certificate is not trusted** — clicking through the interstitial is NOT enough. Symptom: `POST /auth/webauthn/register/options` succeeds (200) but `navigator.credentials.create()` immediately fails with `NotAllowedError: WebAuthn is not supported on sites with TLS certificate errors.` and no `register/verify` call ever reaches the API.

To enroll passkeys against the dev stack, trust the generated certificate once (per user, reversible):

```bash
task dev:trust-cert
```

The task extracts `cert.pem` from the shared `lia_ssl_certs` volume into `exports/lia-dev-cert.pem` and, on Windows, imports it into the current user's trusted root store (`certutil -f -user -addstore Root`; undo with `certutil -user -delstore Root "<SSL_DOMAIN>"`). On Linux/macOS, import the extracted file into your system/browser trust store manually.

Three traps:

1. **Fully restart the browser afterwards** (all windows) — certificate verdicts are cached for the browser process's lifetime; a simple reload keeps failing.
2. **Firefox has its own store** — import `exports/lia-dev-cert.pem` under Settings > Certificates.
3. **`ssl-init` regenerates the certificate** when it is older than ~30 days (or after `docker volume rm lia_ssl_certs`) — re-run `task dev:trust-cert` when that happens.

Production is unaffected: the public domains serve real certificates (Cloudflare), and the WebAuthn rpId/origin derive from `FRONTEND_URL` (see [GUIDE_DEPLOYMENT.md](./guides/GUIDE_DEPLOYMENT.md)).

---

## Starting the Services

### Method 1: Docker Compose (Recommended)

```bash
task dev            # foreground
task dev:detach     # background
task stop           # stop everything
```

- Backend: https://localhost:8000 (Swagger: https://localhost:8000/docs)
- Frontend: https://localhost:3000

**Both services reload on a host edit, but only in polling mode.** The sources
reach the containers through a bind mount that does not forward the host's
filesystem events on Windows or macOS, so a native watcher sees nothing at all
while the file on disk is already up to date — the edit simply never reaches
the browser. The backend handles this by itself (watchfiles auto-enables
polling on a WSL2 kernel); the frontend needs `WEB_WATCH_POLL_MS`, set to
5000 ms in `.env.example`. **Do not lower it to "get a faster reload"** — a
short interval stats the tree over a transport costing ~3 ms per stat and
keeps webpack's graph invalidated, so every page view pays a rebuild. Three
consecutive hits on an already compiled `/dashboard`, nothing edited between
them: 44.5 s / 3.4 s / 2.0 s at 1000 ms, against 5.6 s / 313 ms / 200 ms at
5000 ms. Reload lands in 12.4 s either way (4.8-14 s at 1000 ms). Set it to
`false` on a Linux host, where native events work.

**Never leave a generated tree inside `apps/web/`.** Tailwind detects its own
sources from that directory and turns every file it finds into a webpack
dependency, and each file costs a bind-mount round trip. Measured 2026-08-23,
three leftover `.next-e2e*` proof dists (33 938 files, 96 % of the scan) took
the first page compile from ~20 s to **10 min 32 s**. `apps/web/.gitignore`
and the explicit `@source` in `globals.css` now keep them out, and
`apps/web/src/styles/__tests__/tailwind-source-scope.test.ts` fails if that
protection is dropped — but a dist parked under a new name still wastes your disk.

### Method 2: Hybrid (Infrastructure in Docker, App Manual)

For debugging with a native (non-polling) hot-reload, or to attach a profiler:

```bash
# Stop the containerized app, keep the infrastructure
docker compose -f docker-compose.dev.yml stop api web

# Terminal 1 — Backend (from apps/api, venv activated)
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
# or with debugpy:
python -m debugpy --listen 0.0.0.0:5678 -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — Frontend (from apps/web)
pnpm dev
```

Or use the shortcuts `task dev:api` / `task dev:web` (require PostgreSQL + Redis already running).

### Launched Docker Services

Dev environment (`docker-compose.dev.yml`): 17 services by default, plus 6 opt-in Langfuse services (compose profile `langfuse`, started via `task dev:langfuse`):

| Service | Port(s) | Description | URL |
|---------|---------|-------------|-----|
| **ssl-init** | — | Self-signed certificate generator (runs once) | — |
| **postgres** | 5432 | PostgreSQL 16 + pgvector | — |
| **postgres-backup** | — | Scheduled pg_dump, daily/weekly/monthly rotation (ADR-109) | — |
| **pgadmin** | 5050 | DB administration | http://localhost:5050 |
| **redis** | 6379 | Cache & sessions | — |
| **api** | 8000, 5678 | FastAPI backend (HTTPS) + debugpy | https://localhost:8000 |
| **web** | 3000 | Next.js frontend (HTTPS) | https://localhost:3000 |
| **prometheus** | 9090 | Metrics | http://localhost:9090 |
| **alertmanager** | 9094 | Alert management | http://localhost:9094 |
| **blackbox-exporter** | — | HTTP probes (backup healthcheck, public URL) | — |
| **grafana** | 3001 | Dashboards | http://localhost:3001 |
| **loki** | 3100 | Log aggregation | — |
| **promtail** | 9080 | Log collection | — |
| **tempo** | 3200, 4317, 4318 | Distributed traces (OTLP) | — |
| **cadvisor** | 8080 | Container metrics | http://localhost:8080 |
| **postgres-exporter** | 9187 | PostgreSQL metrics | — |
| **redis-exporter** | 9121 | Redis metrics | — |
| **node-exporter** | 9100 | System metrics | — |
| **minio** * | 9092, 9093 | S3 storage for Langfuse | http://localhost:9093 |
| **langfuse-db** * | — | Langfuse PostgreSQL | — |
| **langfuse-clickhouse** * | — | ClickHouse analytics | — |
| **langfuse-redis** * | — | Langfuse Redis | — |
| **langfuse-web** * | 3002 | LLM observability UI | http://localhost:3002 |
| **langfuse-worker** * | 3030 | Langfuse worker | — |

\* Opt-in `langfuse` compose profile — started only by `task dev:langfuse`.

The production compose (`docker-compose.prod.yml`) runs a leaner 17-service stack: postgres, postgres-backup, redis, api, web, prometheus, alertmanager, blackbox-exporter, grafana, loki, promtail, tempo, node-exporter, cadvisor, postgres-exporter, redis-exporter, portainer — no pgAdmin, no Langfuse stack. Alertmanager delivers the 14-alert core by email (ADR-119, see [ALERTING.md](./technical/ALERTING.md)).

### Service Verification

```bash
# Backend liveness (self-signed cert → -k) — 200 even if PG/Redis are down
curl -k https://localhost:8000/health
# {"status":"healthy","environment":"development","checks":{"redis":"healthy","database":"healthy"}}

# Backend readiness — 200 only when PostgreSQL AND Redis answer (503 otherwise)
curl -k -s -o /dev/null -w "%{http_code}" https://localhost:8000/ready

# Frontend
curl -sk https://localhost:3000 | head -5

# Grafana: http://localhost:3001 (admin / admin)
# Langfuse (dev, opt-in via task dev:langfuse): http://localhost:3002 (admin@lia.local / admin123)
```

---

## First Steps

### 1. Log In and Secure the Admin Account

1. Open https://localhost:3000 (accept the certificate)
2. Log in with `admin@example.com` / `admin123`
3. **Change the password** in Settings > Account
4. Configure at least one LLM provider key (Settings > Administration > LLM Configuration) if not done in Step 7

### 2. Create User Accounts (Optional)

Via the frontend ("Sign Up") or via API:

```bash
curl -k -X POST https://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePassword123!",
    "full_name": "Jean Dupont",
    "timezone": "Europe/Paris",
    "language": "fr"
  }'
```

Supported languages: `fr`, `en`, `es`, `de`, `it`, `zh-CN`.

### 3. First Conversation

Open https://localhost:3000/chat and try:

```
# Simple conversation
Hello, who are you?

# Execution mode: use the toggle in the chat header to switch Pipeline ↔ ReAct

# Contacts / Emails / Calendar (once a provider is connected)
Search my contacts named Jean
Show me my last 5 emails
What are my events for this week?

# Weather (once the OpenWeatherMap connector is set in Settings > Connectors)
What's the weather like in Paris?

# Knowledge & web
Tell me about the Eiffel Tower
What are the latest news about AI?

# Routes
How do I get from Paris to Lyon by car?
```

The **Today Briefing** home page aggregates agenda, emails, birthdays, reminders, weather and health into a daily ritual view with an LLM synthesis.

### 4. Explore Grafana Dashboards

Open http://localhost:3001 (`admin` / `admin`), then Dashboards > Browse:

| Dashboard | Focus |
|-----------|-------|
| 01-app-overview | Global API health & latency |
| 02-slo-tracking | Service Level Objectives |
| 03-infra-resources | CPU, RAM, disk, containers |
| 04-http-api | Endpoint-level HTTP metrics |
| 05-llm-tokens-cost | Token consumption & LLM costs |
| 06-logs-traces | Loki logs + Tempo traces |
| 07-agents-pipeline | LangGraph pipeline flow |
| 08-hitl | Human-in-the-Loop approvals |
| 09-conversations-users | Conversation analytics |
| 10-oauth-connectors-mcp | OAuth health, connectors, MCP |
| 11-voice-websocket | Voice mode & WebSocket |
| 12-channels | Telegram channel |
| 13-proactive-heartbeat | Heartbeat & interest notifications |
| 14-compaction | Context compaction |
| 14-registry-checkpoints | Data registry & checkpoints |
| 15-langgraph-deep | Detailed LangGraph internals |
| 16-meta-health | Recording rules & scrape health |
| 17-user-analytics-geo | User analytics & GeoIP |
| 18-rag-spaces | RAG knowledge spaces |
| 19-subagents-skills | Sub-agents & skills |
| 20-react-browser | ReAct mode & browser control |
| 21-health-metrics | Health metrics ingestion |

### 5. Explore Langfuse (LLM Observability, Dev)

The Langfuse stack is opt-in: start it with `task dev:langfuse` and set `LANGFUSE_ENABLED=true`. Then open http://localhost:3002 (`admin@lia.local` / `admin123`) to inspect per-call LLM traces, latency, tokens and costs. It is **disabled in production**, where cost tracking relies on the built-in token/pricing pipeline and Grafana dashboard 05.

---

## External Platform Setup

LIA integrates with Google, Microsoft, Apple, Firebase and Philips Hue. Follow the sections relevant to your setup. All callback URLs below use the dev API URL — for production, replace `https://localhost:8000` with your API domain.

### 1. Google Cloud Platform

> **Required for**: Google OAuth login, Gmail, Calendar, Contacts, Drive, Tasks, Places, Routes, Geocoding.

#### 1.1 Create a Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/) > **New Project** (e.g. `LIA`)

#### 1.2 Configure the OAuth Consent Screen

1. **APIs & Services** > **OAuth consent screen** > **External** > **Create**
2. Fill app name, support email, developer email
3. On **Scopes**, add:

   | Scope | Purpose |
   |-------|---------|
   | `openid`, `email`, `profile` | Authentication & profile |
   | `https://www.googleapis.com/auth/gmail.readonly` | Read emails |
   | `https://www.googleapis.com/auth/gmail.send` | Send emails |
   | `https://www.googleapis.com/auth/gmail.modify` | Labels, trash |
   | `https://www.googleapis.com/auth/contacts` + `contacts.readonly` + `contacts.other.readonly` | Contacts |
   | `https://www.googleapis.com/auth/calendar` + `calendar.readonly` + `calendar.events` | Calendar |
   | `https://www.googleapis.com/auth/drive.readonly` + `drive.file` + `drive` + `drive.metadata.readonly` | Drive |
   | `https://www.googleapis.com/auth/tasks` + `tasks.readonly` | Tasks |

4. On **Test Users**, add the Google accounts that will use LIA (required in "Testing" mode, max 100)

> While in "Testing" mode only test users can authorize. Public access requires Google **verification** (privacy policy URL + domain ownership); testing mode is sufficient for development and self-hosting.

#### 1.3 Enable the APIs

**APIs & Services** > **Library**, enable: **People API**, **Gmail API**, **Google Calendar API**, **Google Drive API**, **Tasks API**, **Places API (New)**, **Routes API**, **Geocoding API**.

#### 1.4 Create OAuth 2.0 Credentials

1. **Credentials** > **Create Credentials** > **OAuth 2.0 Client ID** > type **Web application**
2. **Authorized JavaScript origins**: `https://localhost:3000`
3. **Authorized redirect URIs** — add all of these:

   ```
   https://localhost:8000/api/v1/auth/google/callback
   https://localhost:8000/api/v1/connectors/gmail/callback
   https://localhost:8000/api/v1/connectors/google-calendar/callback
   https://localhost:8000/api/v1/connectors/google-contacts/callback
   https://localhost:8000/api/v1/connectors/google-drive/callback
   https://localhost:8000/api/v1/connectors/google-tasks/callback
   ```

4. Copy the credentials into `.env` (root — used by both backend and frontend):

   ```bash
   GOOGLE_CLIENT_ID=123456789-abcdef.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=GOCSPX-...
   GOOGLE_REDIRECT_URI=https://localhost:8000/api/v1/auth/google/callback
   NEXT_PUBLIC_GOOGLE_CLIENT_ID=123456789-abcdef.apps.googleusercontent.com
   ```

#### 1.5 Create an API Key (Places, Routes, Geocoding)

1. **Credentials** > **Create Credentials** > **API Key**
2. Restrict it to **Places API (New)**, **Routes API**, **Geocoding API**
3. `GOOGLE_API_KEY=AIzaSy...` in `.env`

#### 1.6 Connect in the Application

Settings > **Connectors** > **Connect** on the desired Google services.

### 2. Microsoft Azure (Optional)

> **Required for**: Outlook (email), Calendar, Contacts and To Do via Microsoft Graph.

1. [Azure Portal](https://portal.azure.com/) > **Microsoft Entra ID** > **App registrations** > **New registration**
   - Supported account types: **Accounts in any organizational directory and personal Microsoft accounts** (`tenant=common`)
2. **Authentication** > **Web** > add the 4 redirect URIs:

   ```
   https://localhost:8000/api/v1/connectors/microsoft-outlook/callback
   https://localhost:8000/api/v1/connectors/microsoft-calendar/callback
   https://localhost:8000/api/v1/connectors/microsoft-contacts/callback
   https://localhost:8000/api/v1/connectors/microsoft-tasks/callback
   ```

   Leave implicit grant unchecked (LIA uses authorization code flow with PKCE).
3. **API permissions** > **Microsoft Graph** > **Delegated**: `User.Read`, `offline_access`, `Mail.Read`, `Mail.ReadWrite`, `Mail.Send`, `Calendars.Read`, `Calendars.ReadWrite`, `Contacts.Read`, `Contacts.ReadWrite`, `Tasks.Read`, `Tasks.ReadWrite` (no admin consent needed for personal accounts)
4. **Certificates & secrets** > **New client secret** — copy the value immediately
5. In `.env`:

   ```bash
   MICROSOFT_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   MICROSOFT_CLIENT_SECRET=your-client-secret-value
   MICROSOFT_TENANT_ID=common
   ```

6. Connect in Settings > Connectors

> **Mutual exclusivity**: only one provider per functional category (email, calendar, contacts, tasks) can be active. Activating Microsoft deactivates Google/Apple for that category (deactivated connectors are set INACTIVE, not deleted).

> See [MICROSOFT_365_INTEGRATION.md](./technical/MICROSOFT_365_INTEGRATION.md).

### 3. Firebase / FCM Push Notifications (Optional)

> **Required for**: OAuth health alerts, Heartbeat proactive notifications, interest notifications.

1. [Firebase Console](https://console.firebase.google.com/) > **Add project** (can be linked to your Google Cloud project)
2. Register a **Web app** and copy the config into the **root `.env`**:

   ```bash
   NEXT_PUBLIC_FIREBASE_API_KEY=AIzaSy...
   NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=lia-xxxxx.firebaseapp.com
   NEXT_PUBLIC_FIREBASE_PROJECT_ID=lia-xxxxx
   NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=lia-xxxxx.appspot.com
   NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=123456789012
   NEXT_PUBLIC_FIREBASE_APP_ID=1:123456789012:web:abcdef123456
   ```

3. **Project Settings > Cloud Messaging**: ensure **FCM API (V1)** is enabled; under **Web Push certificates**, **Generate key pair**:

   ```bash
   NEXT_PUBLIC_FIREBASE_VAPID_KEY=BLxxxxxxxx...
   ```

4. **Project Settings > Service accounts** > **Generate new private key**, save as `apps/api/config/firebase-service-account.json`:

   ```bash
   FIREBASE_CREDENTIALS_PATH=config/firebase-service-account.json
   FIREBASE_PROJECT_ID=lia-xxxxx
   FCM_ENABLED=true
   ```

> **Security**: `config/` is gitignored — never commit the service account JSON.

Verification: enable notifications in Settings > Notifications (browser prompt), then look for `FCM notification sent successfully` in the API logs. Guide: [GUIDE_FCM_PUSH_NOTIFICATIONS.md](./guides/GUIDE_FCM_PUSH_NOTIFICATIONS.md).

### 4. Apple iCloud (Optional)

Apple Email (IMAP/SMTP), Calendar (CalDAV) and Contacts (CardDAV):

1. Generate an app-specific password at [appleid.apple.com](https://appleid.apple.com/)
2. Connect in Settings > Connectors with your Apple ID and that password

The IMAP/SMTP/DAV endpoints are preconfigured (`imap.mail.me.com`, `smtp.mail.me.com`, `caldav.icloud.com`, `contacts.icloud.com`). See [APPLE_ICLOUD_INTEGRATION.md](./technical/APPLE_ICLOUD_INTEGRATION.md).

### 5. Philips Hue (Optional)

Two pairing modes:

- **Local** (same network): press the bridge link button when prompted in Settings > Connectors — no configuration needed.
- **Remote** (cloud OAuth2): create an app on the [Hue Developer Portal](https://developers.meethue.com/) and set `HUE_REMOTE_CLIENT_ID`, `HUE_REMOTE_CLIENT_SECRET`, `HUE_REMOTE_APP_ID` in `.env`.

See [CONNECTOR_PHILIPS_HUE.md](./technical/CONNECTOR_PHILIPS_HUE.md).

### 6. OpenWeatherMap & Brave Search (Per-User Connectors)

Weather and Brave Search are **per-user API-key connectors**: each user enters their own key in **Settings > Connectors** (keys encrypted in DB). Get free keys at [openweathermap.org/api](https://openweathermap.org/api) and [brave.com/search/api](https://brave.com/search/api/).

---

## Feature Configuration Reference

Every subsystem below ships with working defaults; the values shown are the **production configuration**. All of them can be tuned in `.env`.

### Feature Flags (Production Values)

| Flag | Feature | Prod |
|------|---------|------|
| `ATTACHMENTS_ENABLED` | File attachments in chat (images, PDF) | `true` |
| `SKILLS_ENABLED` / `SKILLS_SCRIPTS_ENABLED` | Skills system (SKILL.md) + skill scripts | `true` / `true` |
| `INITIATIVE_ENABLED` | Proactive initiative phase after responses | `true` |
| `RAG_SPACES_ENABLED` | Personal document knowledge spaces | `true` |
| `RAG_SPACES_SYSTEM_ENABLED` | Built-in FAQ knowledge base | `true` |
| `RAG_SPACES_DRIVE_SYNC_ENABLED` | Google Drive sync for RAG spaces | `true` |
| `SUB_AGENTS_ENABLED` | Persistent specialized sub-agents | `true` |
| `JOURNALS_ENABLED` | Assistant introspective journals | `true` |
| `PSYCHE_ENABLED` | Dynamic psychological state | `true` |
| `USAGE_LIMITS_ENABLED` | Per-user usage quotas | `true` |
| `IMAGE_GENERATION_ENABLED` | AI image generation | `true` |
| `HEALTH_METRICS_ENABLED` | iPhone health metrics ingestion | `true` |
| `HEARTBEAT_ENABLED` | Autonomous proactive notifications | `true` |
| `CHANNELS_ENABLED` | Multi-channel messaging (Telegram) | `true` |
| `MCP_ENABLED` / `MCP_USER_ENABLED` / `MCP_REACT_ENABLED` | Admin MCP / per-user MCP / MCP ReAct loop | `true` |
| `REACT_AGENT_ENABLED` | ReAct execution mode toggle | `true` |
| `FCM_ENABLED` | Firebase push notifications | `true` |
| `PUSH_RELAY_URL` | iOS wake relay for the native app (no default: pointing it somewhere is a privacy decision you take, not a constant) | *(unset)* |
| `FIREBASE_ANDROID_APP_ID` / `FIREBASE_API_KEY` / `FIREBASE_SENDER_ID` | Android native-app push from YOUR Firebase project (all three or none) | *(unset)* |
| `MFA_ENABLED` | Passkeys WebAuthn + TOTP + step-up (ADR-143) | `false`¹ |
| `ACCOUNT_EXPORT_ENABLED` | Full GDPR account export (ADR-145) | `false`¹ |
| `GEOIP_ENABLED` | IP geolocation in logs (DB-IP Lite MMDB) | `true` |
| `OAUTH_HEALTH_CHECK_ENABLED` | Proactive connector monitoring | `true` |
| `MEMORY_EXTRACTION_ENABLED` / `MEMORY_CONSOLIDATION_ENABLED` | Long-term memory | `true` |
| `INTEREST_EXTRACTION_ENABLED` / `INTEREST_NOTIFICATIONS_ENABLED` | Interest learning | `true` |
| `EVALUATOR_ENABLED` | LLM-as-judge response evaluation | `true` |
| `DEVOPS_ENABLED` | In-container DevOps Claude CLI (read-only investigation) | `true` |
| `COMPACTION_ENABLED` | Conversation context compaction | `true` |
| `RATE_LIMIT_ENABLED` | Per-user API rate limiting | `true` |
| `VOICE_STT_ENABLED` / `ELEVENLABS_STT_ENABLED` | Local Whisper STT / ElevenLabs Scribe STT | `true` |
| `LANGFUSE_ENABLED` | Langfuse LLM tracing | **`false`** (dev-only tool) |
| `PLAN_PATTERN_TRAINING_ENABLED` | Plan pattern learning | `false` |
| `ENABLE_FALLBACK_MIDDLEWARE` | LLM fallback model chain | `false` |
| `BROWSER_SCREENSHOT_ENABLED` | Browser session screenshots | `false` |

¹ Shipped disabled: enabled in production only after the post-release smoke test (MFA needs `WEBAUTHN_RP_ID`/`WEBAUTHN_ORIGIN` matching the public domain).

### Memory (Long-Term)

```bash
MEMORY_EXTRACTION_ENABLED=true
MEMORY_EMBEDDING_MODEL=models/gemini-embedding-001   # requires a Gemini API key
MEMORY_EMBEDDING_DIMENSIONS=1536
MEMORY_MIN_SEARCH_SCORE=0.70
MEMORY_RELEVANCE_THRESHOLD=0.76
MEMORY_CONSOLIDATION_ENABLED=true
MEMORY_CONSOLIDATION_HOUR=5          # daily dedup/merge pass
MEMORY_CLEANUP_HOUR=4                # daily retention pass
MEMORY_RECENCY_DECAY_DAYS=45
MEMORY_RETENTION_WEIGHT_IMPORTANCE=0.7
MEMORY_RETENTION_WEIGHT_RECENCY=0.3
```

> All embeddings (memory, interests, journals, RAG spaces) use Gemini `gemini-embedding-001` in production — configure a Google Gemini API key in the Admin UI (or `GOOGLE_GEMINI_API_KEY` as fallback).

### Interest Learning

```bash
INTEREST_EXTRACTION_ENABLED=true
INTEREST_NOTIFICATIONS_ENABLED=true
INTEREST_NOTIFY_START_HOUR=9          # notification window 9:00–22:00
INTEREST_NOTIFY_END_HOUR=22
INTEREST_NOTIFICATION_INTERVAL_MINUTES=5
INTEREST_GLOBAL_COOLDOWN_HOURS=1
INTEREST_PER_TOPIC_COOLDOWN_HOURS=12
INTEREST_PRIOR_ALPHA=2                # Beta(2,1) confidence prior
INTEREST_PRIOR_BETA=1
INTEREST_DECAY_RATE_PER_DAY=0.005
INTEREST_DORMANT_THRESHOLD_DAYS=15
INTEREST_DELETION_THRESHOLD_DAYS=30
```

Interests are visible in **Settings > Interests**. See [INTERESTS.md](./technical/INTERESTS.md).

### Heartbeat (Proactive Notifications)

```bash
HEARTBEAT_ENABLED=true
HEARTBEAT_NOTIFICATION_INTERVAL_MINUTES=30   # scheduler tick
HEARTBEAT_GLOBAL_COOLDOWN_HOURS=1
HEARTBEAT_ACTIVITY_COOLDOWN_MINUTES=15
HEARTBEAT_CONTEXT_CALENDAR_HOURS=4
HEARTBEAT_WEATHER_RAIN_THRESHOLD_HIGH=0.6
HEARTBEAT_WEATHER_TEMP_CHANGE_THRESHOLD=5.0
HEARTBEAT_WEATHER_WIND_THRESHOLD=14.0
HEARTBEAT_INACTIVE_SKIP_DAYS=7
```

The per-user daily cap (1-8/day) is a **user setting** (Settings > Proactive Notifications), not an env var. See [HEARTBEAT_AUTONOME.md](./technical/HEARTBEAT_AUTONOME.md).

### Journals & Psyche

```bash
JOURNALS_ENABLED=true
JOURNAL_EXTRACTION_ENABLED=true
JOURNAL_CONSOLIDATION_INTERVAL_HOURS=5
JOURNAL_CONSOLIDATION_COOLDOWN_HOURS=6
JOURNAL_MAX_ENTRY_CHARS=300

PSYCHE_ENABLED=true
PSYCHE_EMBODIED_INJECTION=true
PSYCHE_MOOD_DECAY_RATE=0.1
PSYCHE_EMOTION_DECAY_RATE=0.4
PSYCHE_EMOTION_MAX_ACTIVE=4
PSYCHE_HISTORY_RETENTION_DAYS=90
```

See [JOURNALS.md](./technical/JOURNALS.md) and [PSYCHE_ENGINE.md](./technical/PSYCHE_ENGINE.md).

### Today Briefing

```bash
BRIEFING_MAX_AGENDA_ITEMS=10
BRIEFING_AGENDA_LOOKAHEAD_HOURS=24
BRIEFING_MAX_MAILS_ITEMS=10
BRIEFING_MAX_BIRTHDAYS_ITEMS=5
BRIEFING_MAX_BIRTHDAYS_HORIZON_DAYS=14
BRIEFING_HEALTH_WINDOW_DAYS=14
BRIEFING_WEATHER_DAILY_FORECAST_DAYS=5
```

See [BRIEFING_DOMAIN.md](./technical/BRIEFING_DOMAIN.md).

### RAG Knowledge Spaces

```bash
RAG_SPACES_ENABLED=true
RAG_SPACES_MAX_SPACES_PER_USER=10
RAG_SPACES_MAX_DOCS_PER_SPACE=100
RAG_SPACES_MAX_FILE_SIZE_MB=20
RAG_SPACES_CHUNK_SIZE=1000
RAG_SPACES_CHUNK_OVERLAP=200
RAG_SPACES_RETRIEVAL_LIMIT=5
RAG_SPACES_RETRIEVAL_MIN_SCORE=0.62   # Minimum SEMANTIC similarity (ADR-242)
RAG_SPACES_BM25_BONUS_WEIGHT=0.05     # BM25 re-ordering bonus, never a gate
RAG_SPACES_DRIVE_SYNC_ENABLED=true
RAG_DRIVE_MAX_SOURCES_PER_SPACE=5
```

15+ document formats supported (PDF, DOCX, PPTX, XLSX, ODT, EPUB, HTML, Markdown…). See [GUIDE_RAG_SPACES.md](./guides/GUIDE_RAG_SPACES.md).

### Sub-Agents & Skills

```bash
SUB_AGENTS_ENABLED=true
SUBAGENT_DEFAULT_MAX_ITERATIONS=20
SUBAGENT_TOOL_TIMEOUT_SECONDS=300.0
SUBAGENT_RESEARCH_TOOLS_WHITELIST=perplexity_search_tool,brave_search_tool,fetch_web_page_tool

SKILLS_ENABLED=true
SKILLS_MAX_PER_USER=20
SKILLS_SCRIPTS_ENABLED=true
SKILLS_SCRIPT_TIMEOUT_SECONDS=30
```

See [SUB_AGENTS.md](./technical/SUB_AGENTS.md).

### ReAct Mode & Browser Control

```bash
REACT_AGENT_ENABLED=true
REACT_AGENT_MAX_ITERATIONS=90
REACT_AGENT_TIMEOUT_SECONDS=300
REACT_AGENT_HISTORY_WINDOW_TURNS=5

BROWSER_REACT_MAX_ITERATIONS=50
BROWSER_MAX_CONCURRENT_SESSIONS=1
BROWSER_SESSION_TIMEOUT_SECONDS=300
BROWSER_MAX_NAVIGATIONS_PER_SESSION=30
BROWSER_AX_TREE_MAX_TOKENS=30000
BROWSER_MEMORY_LIMIT_MB=1024
```

See [BROWSER_CONTROL.md](./technical/BROWSER_CONTROL.md).

### MCP (Model Context Protocol)

```bash
MCP_ENABLED=true                       # admin (shared) MCP servers
MCP_USER_ENABLED=true                  # per-user servers (OAuth 2.1)
MCP_REACT_ENABLED=true
MCP_MAX_SERVERS=20
MCP_MAX_TOOLS_PER_SERVER=40
MCP_TOOL_TIMEOUT_SECONDS=120
MCP_REACT_MAX_ITERATIONS=50
MCP_RATE_LIMIT_CALLS=60                # per 60s window
MCP_USER_MAX_SERVERS_PER_USER=20
MCP_USER_POOL_MAX_TOTAL=50
MCP_USER_POOL_TTL_SECONDS=900
MCP_USER_OAUTH_CALLBACK_BASE_URL=https://your-api-domain   # public API URL

# Admin servers are declared as JSON (production example: Excalidraw diagrams)
MCP_SERVERS_CONFIG={"excalidraw":{"transport":"streamable_http","url":"https://mcp.excalidraw.com","timeout_seconds":60,"enabled":true,"hitl_required":false,"iterative_mode":true,"description":"..."}}
```

See [MCP_INTEGRATION.md](./technical/MCP_INTEGRATION.md) and [GUIDE_MCP_INTEGRATION.md](./guides/GUIDE_MCP_INTEGRATION.md).

### Telegram Channel

```bash
CHANNELS_ENABLED=true
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...              # via @BotFather
TELEGRAM_WEBHOOK_SECRET=...                        # openssl rand -hex 32
TELEGRAM_WEBHOOK_URL=https://your-api-domain/api/v1/channels/telegram/webhook
TELEGRAM_BOT_USERNAME=@your_bot
CHANNEL_OTP_TTL_SECONDS=300                        # account linking OTP
CHANNEL_RATE_LIMIT_PER_USER_PER_MINUTE=10
```

Users link their account with an OTP code in Settings > Telegram. Requires a publicly reachable API URL for the webhook. See [GUIDE_TELEGRAM_INTEGRATION.md](./guides/GUIDE_TELEGRAM_INTEGRATION.md).

### Voice Mode

**Input (STT)** — two engines, both enabled in production:

```bash
VOICE_STT_ENABLED=true                 # local Sherpa-onnx Whisper Small (free)
VOICE_STT_MODEL_PATH=/models/whisper-small
VOICE_STT_NUM_THREADS=4
VOICE_STT_MAX_DURATION_SECONDS=60
ELEVENLABS_STT_ENABLED=true            # ElevenLabs Scribe (premium, ~$0.22/h)
ELEVENLABS_STT_MAX_AUDIO_DURATION_SECONDS=300
```

Wake word ("OK") and VAD run **in the browser** (Sherpa-onnx / Silero WASM) — no server configuration.

**Output (TTS) and the voice-comment LLM are configured in the Admin UI** (LLM slots `voice_tts`, `voice_transcription`, `voice_comment`), not in `.env`. Production uses ElevenLabs `eleven_flash_v2_5` (TTS) and `scribe_v2` (STT); Edge TTS is the free default and always available. For a paid provider, set its API key in the Provider Keys admin section (ElevenLabs keys need the `voices_read` scope for the live voice catalogue).

```bash
# Remaining .env knobs
VOICE_MAX_SENTENCES=3                  # sentences per TTS chunk in voice mode
VOICE_CHAT_MODE_MAX_SENTENCES=15      # sentence cap for chat-mode read-aloud
```

See [VOICE_MODE.md](./technical/VOICE_MODE.md).

### Image Generation & Attachments

```bash
IMAGE_GENERATION_ENABLED=true
IMAGE_GENERATION_MAX_IMAGES_PER_REQUEST=1
IMAGE_GENERATION_TOOL_TIMEOUT_SECONDS=90.0
IMAGE_GENERATION_RATE_LIMIT_CALLS=10      # Per-user anti-runaway ceiling (v1.23.4)
IMAGE_GENERATION_RATE_LIMIT_WINDOW=300    # Sliding window in seconds

ATTACHMENTS_ENABLED=true
ATTACHMENTS_MAX_IMAGE_SIZE_MB=10
ATTACHMENTS_MAX_DOC_SIZE_MB=20
ATTACHMENTS_MAX_PER_MESSAGE=5
ATTACHMENTS_TTL_HOURS=24
```

The image model (production: `gpt-image-2`) and its pricing matrix are managed in the Admin UI. See [IMAGE_GENERATION.md](./technical/IMAGE_GENERATION.md) and [ATTACHMENTS_INTEGRATION.md](./technical/ATTACHMENTS_INTEGRATION.md).

### Health Metrics (iPhone Shortcuts)

```bash
HEALTH_METRICS_ENABLED=true
HEALTH_METRICS_RATE_LIMIT_PER_HOUR=60
HEALTH_METRICS_MAX_SAMPLES_PER_REQUEST=1000
HEALTH_METRICS_BASELINE_MIN_DAYS=7
```

Per-user opt-in toggle + ingestion token in Settings. Setup guide: [GUIDE_IPHONE_SHORTCUTS_HEALTH.md](./guides/GUIDE_IPHONE_SHORTCUTS_HEALTH.md).

### Usage Limits & Rate Limiting

```bash
USAGE_LIMITS_ENABLED=true              # per-user quotas (tokens, messages, cost) — set per user in the Admin UI
USAGE_LIMIT_CACHE_TTL_SECONDS=60

RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_BURST=10
RATE_LIMIT_SCOPE=user
```

See [USAGE_LIMITS.md](./technical/USAGE_LIMITS.md) and [RATE_LIMITING.md](./technical/RATE_LIMITING.md).

### Scheduled Actions & Reminders

Scheduled actions (deferred/recurring actions created conversationally) and one-shot reminders are always available — no feature flag.

```bash
SCHEDULED_ACTIONS_EXECUTION_TIMEOUT_SECONDS=300
SCHEDULED_ACTIONS_STALE_TIMEOUT_MINUTES=10
```

See [SCHEDULED_ACTIONS.md](./technical/SCHEDULED_ACTIONS.md) and [GUIDE_SCHEDULED_ACTIONS.md](./guides/GUIDE_SCHEDULED_ACTIONS.md).

### OAuth Health Check

```bash
OAUTH_HEALTH_CHECK_ENABLED=true
OAUTH_HEALTH_CHECK_INTERVAL_MINUTES=5
OAUTH_PROACTIVE_REFRESH_INTERVAL_MINUTES=15
OAUTH_PROACTIVE_REFRESH_MARGIN_SECONDS=1800
OAUTH_HEALTH_CRITICAL_COOLDOWN_HOURS=12
```

Failing connectors trigger an FCM notification and a reconnection modal. See [OAUTH_HEALTH_CHECK.md](./technical/OAUTH_HEALTH_CHECK.md).

### Context Management

```bash
COMPACTION_ENABLED=true
COMPACTION_THRESHOLD_RATIO=0.4
COMPACTION_PRESERVE_RECENT_MESSAGES=10
TOKEN_THRESHOLD_SAFE=50000
TOKEN_THRESHOLD_WARNING=65000
TOKEN_THRESHOLD_CRITICAL=85000
TOKEN_THRESHOLD_MAX=100000
MAX_MESSAGES_HISTORY=150
TOKEN_ENCODING_NAME=o200k_base
```

### Database Backups (ADR-109)

The `postgres-backup` sidecar runs scheduled `pg_dump` with three-tier rotation in **both** dev and prod:

```bash
POSTGRES_BACKUP_SCHEDULE=@daily
POSTGRES_BACKUP_KEEP_DAYS=7
POSTGRES_BACKUP_KEEP_WEEKS=4
POSTGRES_BACKUP_KEEP_MONTHS=6
POSTGRES_BACKUP_EXTRA_OPTS=-Z6 --clean --if-exists
POSTGRES_BACKUP_HOST_DIR=../lia-data/postgres-backups  # prod only, OUTSIDE the deployed dir (dev uses a named volume)
```

```bash
task backup:now      # trigger an immediate backup
task backup:verify   # restore the latest dump into a throwaway container and compare schema/row counts
```

Restore procedure: [runbooks/DATABASE_BACKUP_RESTORE.md](./runbooks/DATABASE_BACKUP_RESTORE.md).

---

## LLM Configuration

LIA drives **54 independently configurable LLM slots** — every pipeline node, domain agent and background task has its own provider/model/parameters. Configuration is resolved as: **code defaults (`LLM_DEFAULTS`) → database overrides** (admin UI), hot-reloaded across workers.

- **Admin UI**: Settings > Administration > LLM Configuration (per-slot provider, model, temperature, max tokens, reasoning effort; provider API keys encrypted at rest).
- **Providers**: OpenAI, Anthropic, DeepSeek, Google Gemini, Qwen, Perplexity, Ollama (text) + ElevenLabs and Edge (voice). Ollama needs only `OLLAMA_BASE_URL`; Perplexity/Qwen base URLs are parameterizable.
- Model catalogue and pricing are database-driven: adding a model is an admin operation, no deploy needed.

The tables below show the **effective production configuration** (code defaults merged with the production database overrides) — a battle-tested quality/cost balance you can reproduce as-is. *Reasoning* is the per-slot reasoning-effort setting (`off` = thinking disabled, `—` = non-reasoning model).

#### Pipeline (Orchestration & Routing)

| Slot | Provider | Model | Temp | Max Tokens | Reasoning |
|------|----------|-------|------|------------|-----------|
| `semantic_pivot` | DeepSeek | `deepseek-v4-flash` | 0.2 | 5 000 | off |
| `query_analyzer` | DeepSeek | `deepseek-v4-flash` | 0.2 | 10 000 | off |
| `router` | DeepSeek | `deepseek-v4-flash` | 0.2 | 5 000 | off |
| `planner` | DeepSeek | `deepseek-v4-flash` | 0.2 | 10 000 | off |
| `semantic_validator` | DeepSeek | `deepseek-v4-flash` | 0.2 | 5 000 | off |
| `context_resolver` | DeepSeek | `deepseek-v4-flash` | 0.2 | 5 000 | off |
| `compaction` | DeepSeek | `deepseek-v4-flash` | 0.5 | 50 000 | high |
| `initiative` | DeepSeek | `deepseek-v4-flash` | 0.2 | 10 000 | off |

#### Domain Agents (Tool-Calling)

| Slot | Provider | Model | Temp | Max Tokens | Reasoning |
|------|----------|-------|------|------------|-----------|
| `contacts_agent` | OpenAI | `gpt-4.1-nano` | 0.0 | 2 000 | — |
| `emails_agent` | OpenAI | `gpt-4.1-nano` | 0.0 | 2 000 | — |
| `calendar_agent` | OpenAI | `gpt-4.1-nano` | 0.0 | 2 000 | — |
| `drive_agent` | OpenAI | `gpt-4.1-nano` | 0.0 | 2 000 | — |
| `tasks_agent` | OpenAI | `gpt-4.1-nano` | 0.0 | 2 000 | — |
| `weather_agent` | OpenAI | `gpt-4.1-nano` | 0.0 | 1 000 | — |
| `wikipedia_agent` | OpenAI | `gpt-4.1-nano` | 0.0 | 2 000 | — |
| `perplexity_agent` | OpenAI | `gpt-4.1-nano` | 0.0 | 3 000 | — |
| `brave_agent` | OpenAI | `gpt-4.1-nano` | 0.0 | 2 000 | — |
| `web_search_agent` | OpenAI | `gpt-4.1-nano` | 0.0 | 4 000 | — |
| `web_fetch_agent` | OpenAI | `gpt-4.1-nano` | 0.3 | 3 000 | — |
| `places_agent` | OpenAI | `gpt-4.1-nano` | 0.0 | 2 000 | — |
| `routes_agent` | OpenAI | `gpt-4.1-nano` | 0.0 | 2 000 | — |
| `hue_agent` | OpenAI | `gpt-4.1-nano` | 0.0 | 1 000 | — |
| `health_agent` | OpenAI | `gpt-4.1-nano` | 0.0 | 1 500 | — |
| `browser_agent` | DeepSeek | `deepseek-v4-flash` | 0.5 | 20 000 | off |
| `react_agent` | DeepSeek | `deepseek-v4-flash` | 0.2 | 20 000 | off |
| `mcp_react_agent` | DeepSeek | `deepseek-v4-flash` | 0.5 | 30 000 | off |
| `subagent` | DeepSeek | `deepseek-v4-flash` | 1.0 | 10 000 | off |

#### Query & Response

| Slot | Provider | Model | Temp | Max Tokens | Reasoning |
|------|----------|-------|------|------------|-----------|
| `query_agent` | DeepSeek | `deepseek-v4-flash` | 0.2 | 10 000 | off |
| `response` | DeepSeek | `deepseek-v4-flash` | 1.0 | 10 000 | off |

#### HITL (Human-in-the-Loop)

| Slot | Provider | Model | Temp | Max Tokens | Reasoning |
|------|----------|-------|------|------------|-----------|
| `hitl_classifier` | DeepSeek | `deepseek-v4-flash` | 0.2 | 5 000 | off |
| `hitl_question_generator` | DeepSeek | `deepseek-v4-flash` | 1.0 | 5 000 | off |
| `hitl_plan_approval_question_generator` | DeepSeek | `deepseek-v4-flash` | 1.0 | 5 000 | off |

#### Memory & Background

| Slot | Provider | Model | Temp | Max Tokens | Reasoning |
|------|----------|-------|------|------------|-----------|
| `memory_extraction` | OpenAI | `gpt-5.2` | 0.2 | 10 000 | none |
| `memory_reference_extraction` | DeepSeek | `deepseek-v4-flash` | 0.2 | 5 000 | off |
| `memory_reference_resolution` | DeepSeek | `deepseek-v4-flash` | 0.2 | 5 000 | off |
| `interest_extraction` | OpenAI | `gpt-5.2` | 0.2 | 10 000 | none |
| `interest_content` | DeepSeek | `deepseek-v4-flash` | 1.0 | 10 000 | high |
| `journal_extraction` | OpenAI | `gpt-5.2` | 0.2 | 10 000 | none |
| `journal_consolidation` | DeepSeek | `deepseek-v4-flash` | 0.5 | 50 000 | high |
| `heartbeat_decision` | DeepSeek | `deepseek-v4-flash` | 0.5 | 10 000 | high |
| `heartbeat_message` | DeepSeek | `deepseek-v4-flash` | 1.0 | 10 000 | high |
| `psyche_summary` | DeepSeek | `deepseek-v4-flash` | 1.0 | 5 000 | off |
| `briefing` | OpenAI | `gpt-5.4-mini` | 1.0 | 5 000 | none |
| `broadcast_translator` | DeepSeek | `deepseek-v4-flash` | 0.5 | 5 000 | off |
| `personality_translation` | OpenAI | `gpt-4.1-nano` | 0.3 | 500 | — |

#### Specialized

| Slot | Provider | Model | Temp | Max Tokens | Reasoning |
|------|----------|-------|------|------------|-----------|
| `vision_analysis` | Gemini | `gemini-3.5-flash` | 1.0 | 5 000 | — |
| `image_generation` | OpenAI | `gpt-image-2` | — | — | — |
| `voice_comment` | OpenAI | `gpt-5.4-mini` | 1.0 | 5 000 | none |
| `voice_transcription` | ElevenLabs | `scribe_v2` | — | — | — |
| `voice_tts` | ElevenLabs | `eleven_flash_v2_5` | — | — | — |
| `mcp_description` | DeepSeek | `deepseek-v4-flash` | 0.5 | 5 000 | off |
| `mcp_app_react_agent` | Anthropic | `claude-opus-4-6` | 1.0 | 30 000 | medium |
| `skill_description_translator` | DeepSeek | `deepseek-v4-flash` | 0.5 | 5 000 | off |
| `evaluator` | OpenAI | `gpt-4.1-mini` | 0.0 | 500 | — |

#### Design Principles of the Production Configuration

1. **DeepSeek V4 Flash** carries the bulk of the pipeline (routing, planning, response, ReAct, HITL, heartbeat): near-frontier quality at a fraction of the cost, with thinking (`high`) enabled only where depth pays (compaction, journal consolidation, heartbeat) and disabled (`off`) on latency-sensitive nodes.
2. **`gpt-4.1-nano`** powers the structured tool-calling domain agents — they need reliable function calling, not reasoning, and they represent the majority of calls for a tiny fraction of cost.
3. **`gpt-5.2`** handles precision extraction (memory, journals, interests) where structured-output quality matters most.
4. **`gemini-3.5-flash`** (vision), **`claude-opus-4-6`** (interactive MCP apps / diagram generation), **`gpt-image-2`** (images) and **ElevenLabs** (voice) cover the specialized slots.

> **Cost tip**: the dominant cost drivers are `response`, `planner` and the ReAct/browser loops. The domain agents are almost free. Any slot can be repointed at runtime from the Admin UI — including to a local Ollama model — without restart.

---

## Python Dependency Management

Since ADR-112, Python dependencies are **locked and reproducible**:

| File | Role |
|------|------|
| `apps/api/requirements.txt` / `requirements-dev.txt` | **Intent manifests** — direct dependencies, loose pins allowed |
| `apps/api/requirements.lock.txt` | **Universal runtime lockfile** — 195 exact pins + SHA256 hashes, one file for linux/amd64, linux/arm64 and Windows; installed by `Dockerfile.prod` |
| `apps/api/requirements-dev.lock.txt` | **Dev lockfile** — layered on the runtime lock (identical runtime versions); installed by `Dockerfile.dev`, CI and the local venv |

Workflow when changing a dependency:

```bash
# 1. Edit the manifest (requirements.txt or requirements-dev.txt)
# 2. Regenerate the lockfiles (requires uv; stable — only manifest changes move versions)
task deps:lock

# Targeted upgrade of one package, or everything:
task deps:upgrade -- <package>
task deps:upgrade:all

# 3. Reinstall locally
pip install --require-hashes -r apps/api/requirements-dev.lock.txt

# 4. Commit manifest AND lockfiles together
```

The CI `code-hygiene` job runs `scripts/check_requirements_lock.py` and **fails any manifest change that skips lockfile regeneration**. `uv` is a compile-time tool only — installs use vanilla pip with hash verification, and uv is absent from the final images. `pyproject.toml` declares no dependencies; it only configures tools (black, ruff, mypy, pytest).

Security: `pip-audit` and the SBOM (CI + release) audit the **full transitive tree** from the lockfile.

---

## Running Tests

### Backend Tests

```bash
task test:backend:unit:fast        # fast unit tests, xdist, no coverage (hook scope)
task test:backend:unit:coverage    # the CI command verbatim, including the 60% floor
task test:backend:unit             # all unit tests
task test:backend:integration      # integration tests (requires PostgreSQL + Redis)
task test:backend:agents           # agent-specific tests
task test:markers                  # F006 gate: no test may run in zero CI jobs
task test:backend:exhaustive       # full suite with coverage (long)

# Single test file / test name
cd apps/api && .venv/Scripts/pytest tests/unit/path/to/test_file.py -v
cd apps/api && .venv/Scripts/pytest tests/ -k "test_name" -v
```

### Frontend Tests

```bash
task test:frontend                 # vitest run
task test:frontend:coverage        # + the per-file coverage thresholds CI enforces
task test:e2e                      # Playwright + axe journeys (hermetic, mocked API)
cd apps/web && pnpm test:watch     # watch mode
```

### Pre-commit & CI

Git hooks (installed by `task setup:hooks`) run on every commit, on **staged files only**: `.bak`/secret/real-infrastructure detection, Ruff + Black + MyPy + fast unit tests (backend), ESLint + TypeScript check (frontend), i18n key parity across the 6 locales, LangGraph safety checks.

```bash
task pre-commit    # ~5 min — what the git hook runs
task ci:fast       # ~10 min — every CI gate that needs no external service (before pushing)
task ci            # + PostgreSQL, Redis, Docker, a browser
```

`.github/workflows/ci.yml` calls these same tasks rather than restating their commands ([ADR-151](architecture/ADR-151-Thin-CI-Workflow.md)), so a local run and a CI job execute literally the same thing. When a job goes red, read its `task ...` call and replay it.

---

## Troubleshooting

### Backend Won't Start

#### `ModuleNotFoundError`

```bash
cd apps/api
source .venv/bin/activate    # Windows: .venv\Scripts\Activate.ps1
pip install --require-hashes -r requirements-dev.lock.txt
```

#### `pip` fails with a hash mismatch

The lockfile and manifest are out of sync — never hand-edit a `.lock.txt` file:

```bash
task deps:lock    # regenerate from the manifests, then reinstall
```

#### `Connection refused` — PostgreSQL / Redis

```bash
docker compose -f docker-compose.dev.yml ps postgres redis
docker compose -f docker-compose.dev.yml up -d postgres redis
docker compose -f docker-compose.dev.yml logs postgres

# Redis connectivity test
docker compose -f docker-compose.dev.yml exec redis redis-cli -a "$REDIS_PASSWORD" ping   # PONG
```

### Browser Can't Reach the App / API Calls Fail

Dev serves **HTTPS with self-signed certificates**. Visit https://localhost:8000 **and** https://localhost:3000 once each and accept both certificates — until then, frontend API calls fail silently. With `curl`, use `-k`.

Note: accepting the interstitial is enough for browsing, but **NOT for WebAuthn/passkeys** — see [WebAuthn / Passkeys in Development](#webauthn--passkeys-in-development-trusted-certificate-required) (`task dev:trust-cert`).

### Frontend Won't Start

```bash
# Cannot find module 'next'
cd apps/web && rm -rf node_modules && pnpm install

# EADDRINUSE: port 3000
# Linux/macOS: lsof -i :3000 && kill -9 <PID>
# Windows: netstat -ano | findstr :3000 && taskkill /PID <PID> /F
```

### Alembic Migrations

```bash
cd apps/api && source .venv/bin/activate
alembic current
alembic upgrade head

# Last resort (WARNING: data loss!)
alembic downgrade base && alembic upgrade head
```

### LLM Errors (`AuthenticationError`, empty responses)

LLM keys live in the database, not `.env`:

1. Log in as admin > **Settings > Administration > LLM Configuration**
2. Check the **Provider Keys** status for the failing provider and re-enter the key
3. Changes apply immediately (no restart)

If the Admin UI is unreachable (e.g. first boot), a temporary `.env` fallback works: `OPENAI_API_KEY=sk-...`

### Docker Desktop Network Access on Windows

On Windows, exposed ports are only reachable on `localhost` by default, not on the LAN IP.

```powershell
# Administrator PowerShell — forward the LAN IP to localhost
netsh interface portproxy add v4tov4 listenaddress=YOUR_LOCAL_IP listenport=8000 connectaddress=127.0.0.1 connectport=8000
netsh interface portproxy show v4tov4
# Remove: netsh interface portproxy delete v4tov4 listenaddress=YOUR_LOCAL_IP listenport=8000
```

Alternatives: Docker Desktop host networking (Settings > Resources > Network), or a reverse proxy. This issue does not exist on native Linux/macOS.

### Docker Compose

```bash
docker compose -f docker-compose.dev.yml logs api          # service logs
docker compose -f docker-compose.dev.yml restart api       # restart one service
docker compose -f docker-compose.dev.yml up -d --force-recreate

# Corrupted volumes (WARNING: data loss!)
docker compose -f docker-compose.dev.yml down -v && docker compose -f docker-compose.dev.yml up -d
```

### Slow Performance

```bash
docker stats                                    # container resources
docker compose -f docker-compose.dev.yml logs api | grep -i duration
```

| Symptom | Check | Lever |
|---------|-------|-------|
| Slow LLM responses | Grafana dashboard 05 (llm-tokens-cost) | Repoint heavy slots (`response`, `planner`) to a faster model in the Admin UI |
| Slow DB | `EXPLAIN ANALYZE`, dashboard 03 | Indexes, `DATABASE_POOL_SIZE` |
| Checkpoint contention | `checkpoint_errors_total{error_type="timeout"}` | Increase `LANGGRAPH_CHECKPOINT_POOL_MAX_SIZE` |
| Saturated Redis | dashboard 03 | `REDIS_MAX_CONNECTIONS`, eviction policy |

### Voice Mode

**Wake word not detected**: check browser microphone permission (`chrome://settings/content/microphone`) and look for "Sherpa KWS initialized" in the browser console (F12).

**Paid TTS not working (OpenAI / ElevenLabs)**:

1. Verify the provider key in the admin Provider Keys section
2. In the `voice_tts` slot config, confirm provider/model and that both `voice_male`/`voice_female` are set (ElevenLabs voice dropdown requires the `voices_read` key scope)
3. ElevenLabs Voice Library (community) voices require a paid plan — the free tier rejects them with HTTP 402; use the default voices
4. Edge TTS is free and always available as fallback

---

## Production Deployment

LIA ships multi-architecture images (`linux/amd64` + `linux/arm64`) — the reference production platform is a Raspberry Pi 5.

### Guided self-host installer (`./install.sh`)

For a fresh production machine, the guided installer (ADR-215) automates the
whole sequence below — see the complete
[self-hosting guide](./guides/GUIDE_SELF_HOSTING.md) for every setting and
failure mode. Its mode is conditional — the same rule holds before
and after release qualification:

- a **complete source checkout** defaults to a **local build**;
- an **official release directory** defaults to **prebuilt digests** only
  when its adjacent `lia-self-host-manifest.json` is qualified
  (`qualification="passed"`); absent or candidate manifests keep local;
- `./install.sh --local-build` in a release directory builds from the
  release's **verified embedded source context**;
- with neither a complete checkout nor a valid embedded context, it fails
  **before any mutation** and prints the exact qualified release asset
  required.

`./install.sh --resume` continues an interrupted install (re-prompting only
the ephemeral secrets when bootstrap had not completed);
`./install.sh --reconfigure` changes routing/capability choices without
touching data, seeds, or secrets. The manual path below remains fully
supported.

### Configuration

1. Start from **`.env.min.prod`** (minimal working set) or `.env.prod.example` (full template) → `.env.prod`
2. Replace every `CHANGE_ME_*` placeholder; set your real domains (CORS, URLs, cookie domain, OAuth redirect URIs on Google/Azure side)
3. Production hardening baked into the defaults: `DEBUG=false`, `LOG_LEVEL=INFO`, secure cookies, per-user rate limiting, no pgAdmin/Langfuse

### Secrets Encryption (SOPS + Age)

```bash
# Generate an Age key pair (keys/ is gitignored)
age-keygen -o keys/age-key-prod.txt

# Encrypt / decrypt .env.prod
export SOPS_AGE_KEY_FILE=keys/age-key-prod.txt
sops --encrypt --input-type dotenv --output-type dotenv .env.prod > .env.prod.encrypted
sops --decrypt --input-type dotenv --output-type dotenv .env.prod.encrypted > .env.prod
```

### Build & Deploy

```bash
task build                 # build all production images (docker-compose.prod.yml)

task deploy:prod           # full pipeline: encrypt + prepare bundle + scp + remote build & up
task deploy:prod:dry-run   # simulate without executing
task deploy:prepare        # prepare the PROD/ bundle only
```

`task deploy:prod` runs `scripts/deploy/deploy-prod.ps1`, which prepares a `PROD/` bundle (compose file, configs, `requirements.lock.txt`, generated `deploy.sh`), ships it to the server and **rebuilds the images on the target** before `up --force-recreate`. The production stack is the 15-service compose described [above](#launched-docker-services).

### Reference Content on a Fresh Production Install

A brand-new production database has **no assistant personalities and no LLM pricing table** — the assistant cannot take a personality, and cost tracking cannot price a single call. The reference content lives in `infrastructure/database/seeds/` and is mounted read-only into the API container.

It is applied **only** when you ask for it, on a **fresh install or a restore onto an empty database**:

```bash
# On the server, from the deployed directory (~/lia)
APPLY_SEEDS=true docker compose -f docker-compose.prod.yml up -d --force-recreate api

# Then remove the flag: the next normal deploy must NOT carry it
docker compose -f docker-compose.prod.yml up -d --force-recreate api
```

> **Warning — these files are destructive by design.** Each one empties its table before re-inserting the reference rows, and `personalities` cascades: `users.personality_id` is `ON DELETE SET NULL`, so applying the seeds to a **populated** database would reset the personality every user has chosen.

Two **independent** conditions must hold, and both fail closed:

| Condition | Meaning | If it cannot be established |
|-----------|---------|-----------------------------|
| Intent | `APPLY_SEEDS=true` | absent by default → seeds skipped |
| Target | the `personalities` table is verifiably **empty** | unreadable **or** non-empty → seeds refused |

The second one is what protects a live installation. `APPLY_SEEDS` is interpolated by Compose from the shell **and** from the project `.env`, so a value left behind in an env file would otherwise re-arm the deletion on every later deploy — the emptiness check makes that stale value harmless. The row count is used strictly as a **veto**: it used to be the *trigger* (`count == 0` meant "fresh install"), which also fired whenever the count could not be read, because a failed query yielded `0`.

Verify afterwards — the deploy log prints one of three unambiguous lines:

- `APPLY_SEEDS=true and database empty - applying SQL seeds ...` followed by one line per file, then the personalities appear in **Settings > Administration**;
- `ERROR: APPLY_SEEDS=true but personalities already holds N row(s) - SQL seeds SKIPPED` — the database was not empty, nothing was touched;
- `Skipping SQL seeds (set APPLY_SEEDS=true for a fresh install only)` — the normal line on every ordinary deploy.

In development the equivalent is `task db:seed:sql` (or `task db:reset`), which targets the dev database directly and does not go through this gate.

### Post-Deploy Operations

- **Backups**: the `postgres-backup` sidecar starts with the stack; the prod deploy pipeline (`scripts/deploy/deploy-prod.ps1` → `prepare-prod.ps1`) creates the host backup directory (chmod 700). Verify restores periodically with `task backup:verify` — the restore path is documented and tested ([runbook](./runbooks/DATABASE_BACKUP_RESTORE.md)).
- **Migrations** run automatically on API startup.
- **Monitoring**: Grafana/Prometheus/Loki/Tempo are part of the prod stack; Portainer provides container administration.

> Full server setup (reverse proxy/tunnel, systemd, first-boot checklist): [GUIDE_DEPLOYMENT.md](./guides/GUIDE_DEPLOYMENT.md).

---

## Next Steps

### Recommended Reading

| Priority | Document | Description |
|----------|----------|-------------|
| **1** | [ARCHITECTURE.md](./ARCHITECTURE.md) | Overall system architecture |
| **2** | [ARCHITECTURE_LANGRAPH.md](./ARCHITECTURE_LANGRAPH.md) | LangGraph multi-agent system (Pipeline + ReAct) |
| **3** | [technical/HITL.md](./technical/HITL.md) | Human-in-the-Loop approval system |
| **4** | [technical/PLANNER.md](./technical/PLANNER.md) | ExecutionPlan DSL + FOR_EACH iteration |
| **5** | [technical/LLM_CONFIG_ADMIN.md](./technical/LLM_CONFIG_ADMIN.md) | LLM slots administration |

### Feature Deep-Dives

| Document | Feature |
|----------|---------|
| [technical/BRIEFING_DOMAIN.md](./technical/BRIEFING_DOMAIN.md) | Today Briefing |
| [technical/JOURNALS.md](./technical/JOURNALS.md) | Personal journals |
| [technical/PSYCHE_ENGINE.md](./technical/PSYCHE_ENGINE.md) | Psychological state |
| [technical/HEALTH_METRICS.md](./technical/HEALTH_METRICS.md) | Health metrics |
| [technical/SUB_AGENTS.md](./technical/SUB_AGENTS.md) | Sub-agents |
| [technical/BROWSER_CONTROL.md](./technical/BROWSER_CONTROL.md) | Browser control |
| [technical/VOICE_MODE.md](./technical/VOICE_MODE.md) | Voice mode |
| [guides/GUIDE_RAG_SPACES.md](./guides/GUIDE_RAG_SPACES.md) | RAG knowledge spaces |
| [technical/LONG_TERM_MEMORY.md](./technical/LONG_TERM_MEMORY.md) | Long-term memory |
| [technical/SMART_SERVICES.md](./technical/SMART_SERVICES.md) | Smart services (caching, pattern learning) |

### Practical Tutorials

| Tutorial | Document |
|----------|----------|
| Create a new agent | [guides/GUIDE_AGENT_CREATION.md](./guides/GUIDE_AGENT_CREATION.md) |
| Add a tool | [guides/GUIDE_TOOL_CREATION.md](./guides/GUIDE_TOOL_CREATION.md) |
| Observability & dashboards | [technical/GRAFANA_DASHBOARDS.md](./technical/GRAFANA_DASHBOARDS.md) · [technical/METRICS_REFERENCE.md](./technical/METRICS_REFERENCE.md) |
| Prompts | [guides/GUIDE_PROMPTS.md](./guides/GUIDE_PROMPTS.md) |
| Testing strategy | [guides/GUIDE_TESTING.md](./guides/GUIDE_TESTING.md) |
| Development workflow | [guides/GUIDE_DEVELOPPEMENT.md](./guides/GUIDE_DEVELOPPEMENT.md) |

### External Resources

| Resource | Link |
|----------|------|
| **LangGraph Docs** | [langchain-ai.github.io/langgraph](https://langchain-ai.github.io/langgraph/) |
| **FastAPI Docs** | [fastapi.tiangolo.com](https://fastapi.tiangolo.com/) |
| **Next.js Docs** | [nextjs.org/docs](https://nextjs.org/docs) |
| **Task** | [taskfile.dev](https://taskfile.dev/) |
| **uv** | [docs.astral.sh/uv](https://docs.astral.sh/uv/) |
| **Langfuse Docs** | [langfuse.com/docs](https://langfuse.com/docs) |
| **Sherpa-onnx** | [k2-fsa.github.io/sherpa](https://k2-fsa.github.io/sherpa/) |

---

## Final Checklist

### Infrastructure

- [ ] `docker compose -f docker-compose.dev.yml ps` — all services healthy (17 in dev, 23 with the Langfuse profile)
- [ ] Backend answers: `curl -k https://localhost:8000/health` (liveness) and `curl -k https://localhost:8000/ready` returns 200 (readiness — DB + Redis up)
- [ ] Frontend reachable: https://localhost:3000 (certificate accepted on **both** :3000 and :8000)
- [ ] Migrations applied (`task db:migrate`), admin created, seeds loaded (`task db:seed:sql`)

### Configuration

- [ ] `SECRET_KEY` and `FERNET_KEY` generated (unique!)
- [ ] `POSTGRES_*` and `REDIS_*` credentials set
- [ ] At least one LLM provider key configured **via the Admin UI**
- [ ] A Gemini key configured if you use memory/interests/journals/RAG (embeddings)
- [ ] Google Cloud OAuth + APIs (if using Google login/connectors)
- [ ] Microsoft app registration (if using Microsoft connectors)
- [ ] Firebase + VAPID (if using push notifications)

### Features

- [ ] Login works, first conversation streams a response
- [ ] Execution mode toggle (Pipeline ↔ ReAct) visible in the chat header
- [ ] Connectors connect and appear ACTIVE in Settings > Connectors
- [ ] Voice mode: microphone authorized, transcription works, TTS speaks
- [ ] Today Briefing renders on the home page

### Observability

- [ ] Grafana up (http://localhost:3001) — 25 dashboards load
- [ ] Prometheus up (http://localhost:9090)
- [ ] Langfuse up in dev (http://localhost:3002) if started via `task dev:langfuse` with `LANGFUSE_ENABLED=true`

### Tests

- [ ] `task test:backend:unit:fast` passes
- [ ] Pre-commit hooks installed (`task setup:hooks`)

---

## Support

| Resource | Description |
|----------|-------------|
| **GitHub Issues** | Bug reports & questions |
| **docs/runbooks/** | Operational procedures (backups, restore…) |
| **ADR Index** | [docs/architecture/ADR_INDEX.md](./architecture/ADR_INDEX.md) — 100+ architecture decisions |
| **Security** | [../SECURITY.md](../SECURITY.md) |

When creating an issue, include: LIA version (`git describe --tags`), OS and tool versions (Docker, Python, Node), sanitized logs, steps to reproduce.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| **4.0** | 2026-07-08 | Full realignment on LIA v1.21.20: lockfile-based install (ADR-112) with dependency-management section; all defaults set to the production-proven values (`.env.prod`); LLM section rebuilt from the live production configuration (54 slots, DeepSeek-centric); HTTPS dev URLs; single root `.env` (incl. `NEXT_PUBLIC_*`); services/ports/dashboards/versions refreshed (17 dev services + opt-in Langfuse profile, 22 dashboards); added Briefing, Psyche, Health Metrics, RAG Spaces, Journals, Sub-agents, Usage Limits, Image Generation, Attachments, DevOps CLI, backups (ADR-109) and LangGraph pooling (ADR-111); removed legacy v6.x numbering, dead env vars and obsolete Claude-skills sections |
| **3.4** | 2026-04-01 | Platform setup guides (Google Cloud, Microsoft Azure, Firebase); LLM config moved to Admin UI |
| **3.2** | 2026-03-20 | Sub-Agents, Browser Control, Personal Journals, System Knowledge Spaces |
| **3.0** | 2026-03-13 | Telegram, MCP, Heartbeat, Skills, SOPS, Testing, Production Deployment sections |
| **2.0** | 2026-02-03 | Skills, FOR_EACH, Voice Mode, Interest Learning |
| **1.5** | 2025-12-15 | Routes API, OAuth Health Check |
| **1.0** | 2025-10-01 | Initial version |

---

**Congratulations!** You are now ready to use, operate and develop with LIA.

**Recommended next step**: [ARCHITECTURE.md](./ARCHITECTURE.md)

---

<p align="center">
  <strong>LIA</strong> — Multi-Agent AI Assistant
</p>
