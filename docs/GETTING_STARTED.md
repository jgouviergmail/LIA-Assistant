# Getting Started - LIA

> Complete guide to install, configure, and get started with LIA - Multi-Agent AI Assistant v6.4

**Version**: 3.4
**Last Updated**: 2026-04-01
**Compatibility**: LIA v6.4.x (+ evolution Features: Web Fetch, MCP Per-User, Multi-Channel Telegram, Heartbeat Autonome, RAG Spaces, Sub-Agents, Browser Control, Personal Journals, Philips Hue Smart Home)

## Table of Contents

- [Project Overview](#project-overview)
- [What's New in v6.3](#whats-new-in-v63)
- [Prerequisites](#prerequisites)
- [Step-by-Step Installation](#step-by-step-installation)
- [Environment Configuration](#environment-configuration)
- [Starting the Services](#starting-the-services)
- [First Steps](#first-steps)
- [Advanced Features](#advanced-features)
  - [Recommended LLM Configuration](#recommended-llm-configuration-optimal-quality--cost)
- [Troubleshooting](#troubleshooting)
- [Next Steps](#next-steps)

---

## Project Overview

**LIA** is a multi-agent conversational AI assistant built with LangGraph. It orchestrates multiple specialized agents to interact with Google services (Contacts, Gmail, Calendar, Drive, Tasks), Places, Weather, Wikipedia, Perplexity, and Routes.

### v6.3 Highlights

| Feature | Description |
|---------|-------------|
| **Philips Hue Smart Home** | Control smart lights via natural language — local press-link or remote OAuth2 (v1.8.0) |
| **Personal Journals** | Assistant's introspective logbooks with semantic context injection (v1.7.1) |
| **System Knowledge Spaces** | Built-in FAQ knowledge base — LIA answers questions about itself (v1.6.1) |
| **Browser Control** | Interactive web browsing via Playwright with autonomous ReAct agent (v1.6.0) |
| **Sub-Agents** | Persistent specialized sub-agents for delegation (research, analysis, synthesis) (v1.5.0) |
| **RAG Knowledge Spaces** | Personal document spaces (15+ formats) with hybrid search and Drive sync (v1.4-v1.5) |
| **Multi-Channel Telegram** | Bidirectional chat via Telegram with HITL inline keyboards and voice STT |
| **MCP Per-User** | External per-user MCP servers with OAuth 2.1, structured parsing |
| **Web Fetch Tool** | Web page content extraction for agents |
| **Heartbeat Autonome** | LLM-driven proactive notifications: weather, calendar, interests |
| **Google API Tracking** | Automatic Google Maps Platform cost tracking |
| **Skills System** | 10 specialized Claude skills + built-in Skill Generator |
| **FOR_EACH Pattern** | Smart iteration with HITL confirmation for bulk operations |
| **Voice Mode** | Voice input with wake word, Push-to-Talk, and VAD |
| **Voice TTS Dual** | Standard (free Edge TTS) or HD (paid OpenAI/Gemini) |
| **Interest Learning** | Automatic interest extraction via LLM |
| **OAuth Health Check** | Proactive connector monitoring with notifications |
| **Hybrid Search** | Combined BM25 + semantic search (alpha=0.6) |

### Technical Architecture

| Layer | Technologies | Versions |
|-------|--------------|----------|
| **Backend** | FastAPI + LangGraph + SQLAlchemy | FastAPI 0.135.3, LangGraph 1.1.6 |
| **Frontend** | Next.js + React + TailwindCSS | Next.js 16.1.7, React 19.2.4 |
| **Database** | PostgreSQL + pgvector | PostgreSQL 16 |
| **Cache/Sessions** | Redis | Redis 7.4 |
| **Observability** | Prometheus + Grafana + Loki + Tempo + Langfuse | Grafana 11.3.0 |
| **LLM Providers** | OpenAI, Anthropic, DeepSeek, Google Gemini, Ollama | Multi-provider |

### Supported Domains

| Domain | Description | Connector |
|--------|-------------|-----------|
| **Contacts** | Google contact management | Google People API |
| **Emails** | Read/send emails | Gmail API |
| **Calendar** | Event management | Google Calendar API |
| **Drive** | File search | Google Drive API |
| **Tasks** | Task management | Google Tasks API |
| **Places** | Location search | Google Places API (New) |
| **Weather** | Real-time weather | OpenWeatherMap API |
| **Wikipedia** | Encyclopedia search | Wikipedia API |
| **Perplexity** | AI-powered web search | Perplexity API |
| **Routes** | Directions and itineraries | Google Routes API |
| **Brave Search** | AI web search | Per-user API key |
| **Web Fetch** | Web page extraction | Built-in |

---

## What's New in v6.3

This version introduces several transformative features.

### Skills System (Claude)

10 specialized skills integrated via `.claude/skills/`:

| Skill | Trigger | Description |
|-------|---------|-------------|
| `analyzing-bugs` | Bug, crash, error | Fact-based diagnosis |
| `designing-architecture` | Architecture, structure | Design patterns and modules |
| `developing-code` | Code, implement | Production-ready code |
| `reviewing-code` | Review, audit, validate | Gold Grade validation |
| `optimizing-performance` | Slow, performance, cost | Bottleneck analysis |
| `monitoring-systems` | Monitoring, alerting | SRE and observability |
| `innovating-products` | Idea, improve, UX | Product strategy |
| `specifying-features` | Behavior, workflow | Functional specifications |
| `upgrading-dependencies` | Update, upgrade | Safe migrations |
| `writing-documentation` | Document, README | Technical documentation |

### FOR_EACH Iteration Pattern

Smart execution of repetitive operations with granular control:

```python
# Example: Send an email to all contacts in a group
ExecutionStep(
    step_id="send_emails",
    tool_name="send_email",
    parameters={"to": "$item.email", "subject": "Newsletter"},
    for_each="$steps.get_contacts.contacts",  # Iteration
    for_each_max=10  # HITL limit
)
```

**HITL Confirmation**: Automatically requested for bulk mutations (>3 items).

### Voice Mode

| Mode | Description | Technology |
|------|-------------|------------|
| **Wake Word** | Activation by saying "OK" | Sherpa-onnx WASM (KWS) |
| **Push-to-Talk** | Hold to speak | WebRTC MediaRecorder |
| **VAD** | End-of-speech detection | Silero VAD WASM |
| **STT** | Transcription | Whisper Small (OpenAI) |
| **TTS Standard** | Free synthesis | Edge TTS |
| **TTS HD** | Premium synthesis | OpenAI TTS (nova/alloy) |

### OAuth Health Check

Proactive connector monitoring with:
- Periodic verification (5 min by default)
- FCM notification on error
- Automatic reconnection modal
- Dedicated Prometheus metrics

---

## Prerequisites

### Operating System

| OS | Version | Notes |
|----|---------|-------|
| **Linux** | Ubuntu 22.04+, Debian 11+, Fedora 38+ | Native, best performance |
| **macOS** | 12 (Monterey)+ | Docker Desktop required |
| **Windows** | 10/11 | WSL2 recommended or Docker Desktop |

### Required Tools

| Tool | Minimum Version | Installation | Verification |
|------|-----------------|--------------|--------------|
| **Python** | 3.12+ | [python.org](https://www.python.org/) | `python --version` |
| **Node.js** | 22.x+ (LTS) | [nodejs.org](https://nodejs.org/) | `node --version` |
| **pnpm** | 10.x+ | `npm install -g pnpm` | `pnpm --version` |
| **Docker** | 24.x+ | [docker.com](https://www.docker.com/) | `docker --version` |
| **Docker Compose** | 2.x+ | Included with Docker Desktop | `docker compose version` |
| **Git** | 2.40+ | [git-scm.com](https://git-scm.com/) | `git --version` |

### Recommended Tools (Optional)

| Tool | Usage | Installation |
|------|-------|--------------|
| **pyenv** | Python version management | `brew install pyenv` (macOS) |
| **nvm** | Node.js version management | [nvm-sh/nvm](https://github.com/nvm-sh/nvm) |
| **direnv** | Auto-load environment variables | `brew install direnv` |
| **jq** | JSON parsing (logs) | `apt install jq` / `brew install jq` |
| **Redis CLI** | Debug cache & sessions | `apt install redis-tools` |
| **Claude Code** | AI development assistant | [claude.ai/claude-code](https://claude.ai/claude-code) |

### Verifying Prerequisites

```bash
# Check all versions
python --version    # >= 3.12
node --version      # >= 20.0
pnpm --version      # >= 10.0
docker --version    # >= 24.0
docker compose version  # >= 2.0
git --version       # >= 2.40
```

### Required API Accounts

#### Mandatory

| Service | Usage | Sign Up |
|---------|-------|---------|
| **OpenAI** | Primary LLM provider (configured via Admin UI) | [platform.openai.com](https://platform.openai.com/api-keys) |
| **Google Cloud** | OAuth + Google APIs | [console.cloud.google.com](https://console.cloud.google.com/) |

#### Optional (Depending on Connectors)

| Service | Usage | Sign Up |
|---------|-------|---------|
| **Microsoft Azure** | Microsoft 365 connectors (Outlook, Calendar, Contacts, Tasks) | [portal.azure.com](https://portal.azure.com/) |
| **Firebase** | Push notifications (FCM) | [console.firebase.google.com](https://console.firebase.google.com/) |
| **Anthropic** | Claude (alternative LLM) | [console.anthropic.com](https://console.anthropic.com/) |
| **DeepSeek** | Budget-friendly LLM | [platform.deepseek.com](https://platform.deepseek.com/) |
| **Google Gemini** | Google LLM | [aistudio.google.com](https://aistudio.google.com/app/apikey) |
| **Perplexity** | AI-powered web search | [perplexity.ai/settings/api](https://www.perplexity.ai/settings/api) |
| **OpenWeatherMap** | Weather (free) | [openweathermap.org/api](https://openweathermap.org/api) |

---

## Step-by-Step Installation

### Step 1: Clone the Repository

```bash
# Clone the project
git clone https://github.com/jgouviergmail/LIA-Assistant.git lia
cd lia

# Check the branch
git branch  # Should display: * main
```

### Step 2: Set Up the Python Backend

```bash
cd apps/api

# Create the Python 3.12+ virtual environment
python -m venv venv

# Activate the virtual environment
# Linux/macOS:
source venv/bin/activate

# Windows CMD:
venv\Scripts\activate.bat

# Windows PowerShell:
venv\Scripts\Activate.ps1

# Install dependencies (development mode)
pip install -e ".[dev]"

# Verify the installation
pip list | grep fastapi     # fastapi 0.135.1
pip list | grep langgraph   # langgraph 1.1.2

# Install pre-commit hooks (recommended)
pre-commit install
```

> **Tip**: If you have [Task](https://taskfile.dev/) installed, you can use `task setup:backend` instead of manual steps above. Similarly, use `task setup:frontend` for Step 3.

**Estimated time**: 3-5 minutes depending on connection speed.

### Step 3: Set Up the Frontend

```bash
cd ../web  # From apps/api

# Install dependencies with pnpm
pnpm install

# Verify the installation
pnpm list next  # next 16.1.7
```

**Estimated time**: 1-3 minutes.

### Step 4: Configure Environment Variables

#### 4.1 Copy the Template

```bash
cd ../..  # Back to the project root

# Copy the environment template
cp .env.example .env

# Edit the .env file
# Linux/macOS: nano .env
# Windows: notepad .env
# VSCode: code .env
```

#### 4.2 Minimum Configuration (.env)

Here are the **mandatory** variables to configure:

```bash
# ============================================================================
# SECURITY (MANDATORY - Generate unique values!)
# ============================================================================

# Secret key for JWT and sessions (32+ characters)
# Generate with: openssl rand -hex 32
SECRET_KEY=YOUR_UNIQUE_SECRET_KEY_32_CHARACTERS_MINIMUM

# Encryption key for OAuth credentials (Fernet)
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FERNET_KEY=YOUR_UNIQUE_FERNET_KEY

# ============================================================================
# DATABASE (Default configuration for Docker)
# ============================================================================

# PostgreSQL user and password
POSTGRES_USER=lia
POSTGRES_PASSWORD=lia_password_secure
POSTGRES_DB=lia

# Connection URL (uses the variables above)
DATABASE_URL=postgresql+asyncpg://lia:lia_password_secure@postgres:5432/lia

# ============================================================================
# REDIS (Default configuration for Docker)
# ============================================================================

# Redis password (required for authentication)
# Generate with: openssl rand -base64 16
REDIS_PASSWORD=redis_password_secure
REDIS_URL=redis://:redis_password_secure@redis:6379/0

# ============================================================================
# LLM PROVIDERS
# ============================================================================
# NOTE: LLM provider API keys are NO LONGER configured here.
# They are managed via the Admin UI: Settings > Administration > LLM Configuration.
# Keys are encrypted (Fernet) in the database and hot-reloadable (no restart needed).
# .env keys are only used as fallback if no database key exists for a provider.
#
# Supported providers: OpenAI, Anthropic, DeepSeek, Google Gemini, Qwen, Perplexity, Ollama
# At least one provider (typically OpenAI) must be configured via Admin UI after first login.

# OpenWeatherMap (optional - for weather tool, still configured via .env)
OPENWEATHERMAP_API_KEY=...

# ============================================================================
# GOOGLE OAUTH (MANDATORY for Google connectors)
# ============================================================================

# Google Cloud Console > APIs & Services > Credentials
# Create an "OAuth 2.0 Client ID" of type "Web application"
GOOGLE_CLIENT_ID=YOUR_CLIENT_ID.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=YOUR_CLIENT_SECRET
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback

# Google API key (for Places photos, Drive thumbnails)
GOOGLE_API_KEY=...

# ============================================================================
# APPLICATION
# ============================================================================

ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=DEBUG
CORS_ORIGINS=http://localhost:3000,http://localhost:8000
FRONTEND_URL=http://localhost:3000
API_URL=http://localhost:8000

# ============================================================================
# GRAFANA (Dashboards)
# ============================================================================

GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=admin

# ============================================================================
# PGADMIN (DB Administration)
# ============================================================================

PGADMIN_DEFAULT_EMAIL=admin@lia.local
PGADMIN_DEFAULT_PASSWORD=admin
```

#### 4.3 Generating Cryptographic Keys

```bash
# Generate SECRET_KEY (32 bytes hex = 64 characters)
openssl rand -hex 32

# Generate FERNET_KEY (44 base64 characters)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Generate REDIS_PASSWORD (16 bytes base64)
openssl rand -base64 16
```

#### 4.4 LAN Access & SSL Configuration (Development)

If you need to access LIA from other devices on your local network (e.g., mobile testing), configure LAN access using [nip.io](https://nip.io):

1. **Find your local IP address** (e.g., `192.168.1.100`)

2. **Set SSL_DOMAIN in `.env`**:
   ```bash
   # Replace with your actual IP
   SSL_DOMAIN=192.168.1.100.nip.io
   ```

3. **Update related variables in `.env`**:
   ```bash
   NEXT_PUBLIC_API_URL=https://192.168.1.100.nip.io:8000
   NEXT_PUBLIC_APP_URL=https://192.168.1.100.nip.io:3000
   NEXT_PUBLIC_ALLOWED_DEV_ORIGINS=192.168.1.100.nip.io
   ```

4. **Accept the self-signed certificate** — after starting Docker, navigate to `https://192.168.1.100.nip.io:8000` in your browser and accept the certificate. This is required for the browser to make API calls.

> **Important**: `NEXT_PUBLIC_ALLOWED_DEV_ORIGINS` must be a **hostname only** (e.g., `192.168.1.100.nip.io`), NOT a full URL with protocol/port. Using `https://...` will cause WebSocket HMR failures and page refresh loops.

The `ssl-init` Docker service automatically generates self-signed certificates covering the configured domain. Certificates are shared between the API and Web containers via a Docker volume.

### Step 5: Start Docker Infrastructure

```bash
# From the project root

# Start all services (19 containers)
docker compose -f docker-compose.dev.yml up -d

# Verify all services are "healthy"
docker compose -f docker-compose.dev.yml ps

# View real-time logs
docker compose -f docker-compose.dev.yml logs -f
```

#### Launched Docker Services

| Service | Port | Description | URL |
|---------|------|-------------|-----|
| **ssl-init** | - | SSL certificate generator (runs once) | - |
| **postgres** | 5432 | PostgreSQL 16 + pgvector | - |
| **pgadmin** | 5050 | DB Administration | http://localhost:5050 |
| **redis** | 6379 | Cache & Sessions | - |
| **api** | 8000/5678 | FastAPI Backend | http://localhost:8000 |
| **web** | 3000 | Next.js Frontend | http://localhost:3000 |
| **prometheus** | 9090 | Metrics | http://localhost:9090 |
| **alertmanager** | 9094 | Alert management | http://localhost:9094 |
| **grafana** | 3001 | Dashboards | http://localhost:3001 |
| **loki** | 3100 | Log aggregation | - |
| **promtail** | 9080 | Log collection | - |
| **tempo** | 3200/4317/4318 | Distributed traces | http://localhost:3200 |
| **cadvisor** | 8080 | Container metrics | http://localhost:8080 |
| **postgres-exporter** | 9187 | PostgreSQL metrics | - |
| **redis-exporter** | 9121 | Redis metrics | - |
| **node-exporter** | 9100 | System metrics | - |
| **minio** | 9092/9093 | S3 for Langfuse | http://localhost:9093 |
| **langfuse-db** | - | Langfuse PostgreSQL | - |
| **langfuse-clickhouse** | - | ClickHouse analytics | - |
| **langfuse-redis** | - | Langfuse Redis | - |
| **langfuse-web** | 3002 | LLM Observability | http://localhost:3002 |
| **langfuse-worker** | 3030 | Langfuse Worker | - |

### Step 6: Apply Migrations

```bash
cd apps/api
source venv/bin/activate  # If not already activated

# Apply Alembic migrations
alembic upgrade head

# Verify the migration
alembic current
# Should display the latest revision
```

#### Step 7: Create Admin User and Seed Data

After migrations, create the initial admin account and seed development data:

```bash
# Option A: Full reset (migrate + admin + seed + SQL seeds) — recommended for first setup
task db:reset

# Option B: Step by step
task db:create-admin                    # Creates admin user (admin@example.com / admin123)
task db:seed                            # Seeds test users and connectors
task db:seed:sql                        # Seeds personalities and LLM pricing data

# Option C: Custom admin credentials
task db:create-admin -- --email you@example.com --password YourSecurePassword123
```

**Default admin account** (created by `task db:create-admin`):

| Field | Value |
|-------|-------|
| Email | `admin@example.com` |
| Password | `admin123` |
| Role | Superuser (full admin access) |

> **Important**: Change the default admin password after first login! Go to Settings > Account to update it.

> **Note**: `task db:seed:sql` populates assistant personalities and LLM pricing data. Without it, the assistant won't have a personality and cost tracking won't work.

> **Note**: System FAQ knowledge base (119 Q/A) is automatically indexed at app startup. No manual seed required. For manual indexation: `task db:seed:system-rag`.

#### Created Tables

Migrations automatically create:

**Main Tables**:
- `users` - User accounts
- `conversations`, `conversation_messages` - Conversation history
- `connectors` - User OAuth connections
- `personalities` - Assistant personalities
- `connector_preferences` - Per-connector user preferences

**LangGraph Tables**:
- `checkpoints`, `checkpoint_blobs`, `checkpoint_writes` - State persistence

**HITL Tables**:
- `plan_approvals` - Plan approvals (Human-in-the-Loop)

**Pricing Tables**:
- `llm_model_pricing` - Per-model LLM pricing
- `currency_exchange_rates` - USD/EUR exchange rates
- `token_usage_logs` - Token consumption tracking

---

## Starting the Services

### Method 1: Docker Compose (Recommended)

```bash
# From the project root

# Start all services
docker compose -f docker-compose.dev.yml up -d

# Check status
docker compose -f docker-compose.dev.yml ps

# API and Web services are started automatically
# - Backend: http://localhost:8000
# - Frontend: http://localhost:3000
```

### Method 2: Manual Launch (For Debugging)

If you want to debug the code with hot-reload:

#### Terminal 1: Infrastructure Only

```bash
# Start only infrastructure services (without api and web)
docker compose -f docker-compose.dev.yml up -d postgres redis prometheus grafana loki tempo langfuse-web

# Or stop api/web if already running
docker compose -f docker-compose.dev.yml stop api web
```

#### Terminal 2: Backend API

```bash
cd apps/api
source venv/bin/activate

# Start with automatic reload
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000 --log-level debug

# Or with Python debugging (debugpy)
python -m debugpy --listen 0.0.0.0:5678 -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

#### Terminal 3: Next.js Frontend

```bash
cd apps/web

# Start in development mode
pnpm dev

# Or on a different port
pnpm dev -- -p 3001
```

### Service Verification

```bash
# Verify Backend
curl http://localhost:8000/health
# Response: {"status":"healthy","database":"connected","redis":"connected"}

# Verify API Docs (Swagger)
# Open: http://localhost:8000/docs

# Verify Frontend
curl -s http://localhost:3000 | head -5
# Should return HTML

# Verify Grafana
# Open: http://localhost:3001
# Login: admin / admin

# Verify Langfuse
# Open: http://localhost:3002
# Login: admin@lia.local / admin123
```

---

## First Steps

### 1. Log In with the Admin Account

If you ran `task db:reset` or `task db:create-admin` in Step 7, an admin account is already available:

1. Open http://localhost:3000
2. Log in with `admin@example.com` / `admin123`
3. **Change your password** in Settings > Account

> The admin account has superuser privileges: access to the Administration panel (LLM configuration, user management, system settings).

### 2. Create Additional User Accounts (Optional)

#### Via Frontend

1. Open http://localhost:3000
2. Click "Sign Up"
3. Fill in the form:
   - Email
   - Password (8+ characters)
   - Full name
   - Language (fr, en, es, de, it, zh-CN)
   - Timezone

#### Via API

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePassword123!",
    "full_name": "Jean Dupont",
    "timezone": "Europe/Paris",
    "language": "fr"
  }'
```

### 3. Configure External Platform Accounts

LIA integrates with Google, Microsoft, and Firebase. Each platform requires specific configuration. Follow the sections relevant to your setup.

---

#### 3.1 Google Cloud Platform Setup

> **Required for**: Google OAuth login, Gmail, Calendar, Contacts, Drive, Tasks, Places, Routes, Geocoding.

##### 3.1.1 Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click the project selector (top bar) > **New Project**
3. Project name: `LIA` (or your preferred name)
4. Click **Create**, then select the project

##### 3.1.2 Configure the OAuth Consent Screen

1. Navigate to **APIs & Services** > **OAuth consent screen**
2. Choose **External** user type (unless you have a Google Workspace org) > **Create**
3. Fill in the required fields:
   - **App name**: `LIA`
   - **User support email**: your email
   - **Developer contact email**: your email
4. Click **Save and Continue**
5. On the **Scopes** page, click **Add or Remove Scopes** and add:

   | Scope | Purpose |
   |-------|---------|
   | `openid` | Authentication |
   | `email` | User email |
   | `profile` | User name & avatar |
   | `https://www.googleapis.com/auth/gmail.readonly` | Read emails |
   | `https://www.googleapis.com/auth/gmail.send` | Send emails |
   | `https://www.googleapis.com/auth/gmail.modify` | Modify emails (labels, trash) |
   | `https://www.googleapis.com/auth/contacts` | Manage contacts |
   | `https://www.googleapis.com/auth/contacts.readonly` | Read contacts |
   | `https://www.googleapis.com/auth/contacts.other.readonly` | Read "Other contacts" |
   | `https://www.googleapis.com/auth/calendar` | Full calendar access |
   | `https://www.googleapis.com/auth/calendar.readonly` | Read calendar |
   | `https://www.googleapis.com/auth/calendar.events` | Manage events |
   | `https://www.googleapis.com/auth/drive.readonly` | Read Drive files |
   | `https://www.googleapis.com/auth/drive.file` | Manage files created by LIA |
   | `https://www.googleapis.com/auth/drive` | Full Drive access |
   | `https://www.googleapis.com/auth/drive.metadata.readonly` | Read file metadata |
   | `https://www.googleapis.com/auth/tasks` | Manage tasks |
   | `https://www.googleapis.com/auth/tasks.readonly` | Read tasks |

6. Click **Save and Continue**
7. On the **Test Users** page, add the Google accounts that will use LIA during development (required while the app is in "Testing" mode — max 100 users)
8. Click **Save and Continue** > **Back to Dashboard**

> **Note**: While in "Testing" mode, only test users can authorize. To allow any Google user, submit the app for **Verification** (requires privacy policy URL and domain ownership). For development, testing mode is sufficient.

##### 3.1.3 Enable Google APIs

Navigate to **APIs & Services** > **Library** and enable each of these APIs:

| API | Usage in LIA | Search Term |
|-----|--------------|-------------|
| **People API** | Google Contacts | `People API` |
| **Gmail API** | Email read/send | `Gmail API` |
| **Google Calendar API** | Event management | `Google Calendar API` |
| **Google Drive API** | File search & RAG sync | `Google Drive API` |
| **Tasks API** | Task management | `Tasks API` |
| **Places API (New)** | Location search | `Places API (New)` |
| **Routes API** | Directions & itineraries | `Routes API` |
| **Geocoding API** | Address resolution | `Geocoding API` |

For each API: click it > click **Enable**.

##### 3.1.4 Create OAuth 2.0 Credentials

1. Navigate to **APIs & Services** > **Credentials**
2. Click **Create Credentials** > **OAuth 2.0 Client ID**
3. Application type: **Web application**
4. Name: `LIA Development`
5. **Authorized JavaScript origins**: `http://localhost:3000`
6. **Authorized redirect URIs** — add all of these:

   ```
   http://localhost:8000/api/v1/auth/google/callback
   http://localhost:8000/api/v1/connectors/gmail/callback
   http://localhost:8000/api/v1/connectors/google-calendar/callback
   http://localhost:8000/api/v1/connectors/google-contacts/callback
   http://localhost:8000/api/v1/connectors/google-drive/callback
   http://localhost:8000/api/v1/connectors/google-tasks/callback
   ```

7. Click **Create**
8. Copy the **Client ID** and **Client Secret** into `.env`:

   ```bash
   GOOGLE_CLIENT_ID=123456789-abcdef.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=GOCSPX-...
   GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback
   ```

> **Production**: Replace `http://localhost:8000` with your production API URL (e.g., `https://lia-back.yourdomain.com`) in both the redirect URIs and `.env`.

##### 3.1.5 Create an API Key (for Places, Routes, Geocoding)

Places, Routes, and Geocoding APIs use an API key (not OAuth):

1. In **APIs & Services** > **Credentials**, click **Create Credentials** > **API Key**
2. Click **Edit API key** (pencil icon) to restrict it:
   - **Name**: `LIA API Key`
   - **Application restrictions**: None (or HTTP referrers for production)
   - **API restrictions**: Select **Restrict key** and choose:
     - Places API (New)
     - Routes API
     - Geocoding API
3. Click **Save**
4. Copy the key into `.env`:

   ```bash
   GOOGLE_API_KEY=AIzaSy...
   ```

##### 3.1.6 Frontend Google Client ID

For the Google Sign-In button on the frontend, add to `apps/web/.env.local`:

```bash
NEXT_PUBLIC_GOOGLE_CLIENT_ID=123456789-abcdef.apps.googleusercontent.com
```

This is the **same Client ID** as the backend.

##### 3.1.7 Connect in the Application

1. Log in to the frontend
2. Go to **Settings** > **Connectors**
3. Click **Connect** on the desired Google services
4. Authorize OAuth access
5. You will be redirected with the connector activated

---

#### 3.2 Microsoft Azure Portal Setup (Optional)

> **Required for**: Microsoft Outlook (email), Calendar, Contacts, and To Do (tasks) via Microsoft Graph API.

##### 3.2.1 Register an Application

1. Go to [Azure Portal](https://portal.azure.com/)
2. Navigate to **Microsoft Entra ID** (formerly Azure Active Directory) > **App registrations**
3. Click **New registration**
4. Fill in:
   - **Name**: `LIA`
   - **Supported account types**: **Accounts in any organizational directory and personal Microsoft accounts** (this corresponds to `tenant=common`)
   - **Redirect URI**: Select **Web** and add:
     ```
     http://localhost:8000/api/v1/connectors/microsoft-outlook/callback
     ```
5. Click **Register**
6. On the app overview page, copy the **Application (client) ID**

##### 3.2.2 Add All Redirect URIs

1. In the app registration, go to **Authentication**
2. Under **Web** > **Redirect URIs**, click **Add URI** and add all 4 callback URLs:

   ```
   http://localhost:8000/api/v1/connectors/microsoft-outlook/callback
   http://localhost:8000/api/v1/connectors/microsoft-calendar/callback
   http://localhost:8000/api/v1/connectors/microsoft-contacts/callback
   http://localhost:8000/api/v1/connectors/microsoft-tasks/callback
   ```

3. Under **Implicit grant and hybrid flows**, ensure nothing is checked (LIA uses authorization code flow with PKCE)
4. Click **Save**

> **Production**: Add your production URLs as well (e.g., `https://lia-back.yourdomain.com/api/v1/connectors/microsoft-outlook/callback`).

##### 3.2.3 Configure API Permissions

1. Go to **API permissions** > **Add a permission** > **Microsoft Graph** > **Delegated permissions**
2. Add the following permissions:

   | Permission | Purpose |
   |-----------|---------|
   | `User.Read` | Read user profile |
   | `offline_access` | Refresh tokens (long-lived sessions) |
   | `Mail.Read` | Read emails |
   | `Mail.ReadWrite` | Modify emails |
   | `Mail.Send` | Send emails |
   | `Calendars.Read` | Read calendar events |
   | `Calendars.ReadWrite` | Create/update/delete events |
   | `Contacts.Read` | Read contacts |
   | `Contacts.ReadWrite` | Create/update/delete contacts |
   | `Tasks.Read` | Read To Do tasks |
   | `Tasks.ReadWrite` | Create/update/delete tasks |

3. Click **Add permissions**

> **Note**: These are all **delegated** permissions (acting on behalf of the user). No admin consent is required for personal accounts.

##### 3.2.4 Create a Client Secret

1. Go to **Certificates & secrets** > **Client secrets** > **New client secret**
2. Description: `LIA Development`
3. Expiry: Choose your preferred duration (24 months recommended for dev)
4. Click **Add**
5. **Immediately copy the secret Value** (it will only be shown once!)

##### 3.2.5 Configure Environment Variables

Add to your `.env`:

```bash
MICROSOFT_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
MICROSOFT_CLIENT_SECRET=your-client-secret-value
MICROSOFT_TENANT_ID=common
```

> **`MICROSOFT_TENANT_ID=common`** supports both personal Microsoft accounts (outlook.com, hotmail.com, live.com) and enterprise Azure AD accounts. Microsoft automatically detects the account type.

##### 3.2.6 Connect in the Application

1. Log in to the frontend
2. Go to **Settings** > **Connectors**
3. Click **Connect** on the desired Microsoft services (Outlook, Calendar, Contacts, Tasks)
4. Sign in with your Microsoft account and authorize

> **Mutual exclusivity**: Only one provider per category (email, calendar, contacts, tasks) can be active. Activating Microsoft deactivates Google/Apple for that category (and vice versa). Deactivated connectors are set to INACTIVE, not deleted.

> See [MICROSOFT_365_INTEGRATION.md](./technical/MICROSOFT_365_INTEGRATION.md) for full technical details.

---

#### 3.3 Firebase Console Setup (Optional)

> **Required for**: Push notifications (FCM) — OAuth health alerts, heartbeat proactive notifications, interest-based notifications.

##### 3.3.1 Create a Firebase Project

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Click **Add project**
3. Project name: `LIA` (you can link it to your existing Google Cloud project)
4. Disable Google Analytics (not needed) or enable it if desired
5. Click **Create project**

##### 3.3.2 Register a Web App

1. In the Firebase project dashboard, click the **Web** icon (`</>`) to add a web app
2. App nickname: `LIA Web`
3. Do **not** check "Also set up Firebase Hosting"
4. Click **Register app**
5. Firebase will display a config object. Copy these values into `apps/web/.env.local`:

   ```bash
   NEXT_PUBLIC_FIREBASE_API_KEY=AIzaSy...
   NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=lia-xxxxx.firebaseapp.com
   NEXT_PUBLIC_FIREBASE_PROJECT_ID=lia-xxxxx
   NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=lia-xxxxx.appspot.com
   NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=123456789012
   NEXT_PUBLIC_FIREBASE_APP_ID=1:123456789012:web:abcdef123456
   ```

6. Click **Continue to console**

##### 3.3.3 Enable Cloud Messaging

1. In the Firebase project, go to **Project Settings** (gear icon) > **Cloud Messaging** tab
2. Verify that **Firebase Cloud Messaging API (V1)** is enabled. If it shows "Disabled", click the three-dot menu and enable it via the Google Cloud Console link

##### 3.3.4 Generate a VAPID Key (Web Push)

1. Still in **Project Settings** > **Cloud Messaging** tab
2. Scroll down to **Web Push certificates**
3. Click **Generate key pair**
4. Copy the generated key into `apps/web/.env.local`:

   ```bash
   NEXT_PUBLIC_FIREBASE_VAPID_KEY=BLxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx...
   ```

##### 3.3.5 Create a Service Account Key (Backend)

1. Go to **Project Settings** > **Service accounts** tab
2. Select **Firebase Admin SDK** > **Node.js** (the language doesn't matter, the JSON key is universal)
3. Click **Generate new private key** > **Generate key**
4. Save the downloaded JSON file as `apps/api/config/firebase-service-account.json`
5. Configure in `.env`:

   ```bash
   FIREBASE_CREDENTIALS_PATH=config/firebase-service-account.json
   FIREBASE_PROJECT_ID=lia-xxxxx
   FCM_ENABLED=true
   ```

> **Security**: The `config/` directory is gitignored. Never commit the service account JSON to the repository.

##### 3.3.6 Verify the Configuration

After starting LIA, push notifications should work when:
- A user enables notifications in **Settings** > **Notifications** (browser permission prompt)
- An OAuth connector encounters an error (health check notification)
- A heartbeat proactive notification is triggered

Check the backend logs for:
```
FCM notification sent successfully
```

---

#### 3.4 Apple iCloud Connectors (Optional)

LIA supports Apple Email (IMAP), Calendar (CalDAV), and Contacts (CardDAV):

1. Generate an app-specific password at [appleid.apple.com](https://appleid.apple.com/)
2. Connect in Settings > Connectors with your Apple ID and app-specific password

> See [APPLE_ICLOUD_INTEGRATION.md](./technical/APPLE_ICLOUD_INTEGRATION.md) for details.

> **Note**: Only one provider per functional category (email, calendar, contacts) can be active at a time. Google, Apple, and Microsoft are mutually exclusive per category.

### 4. First Conversation

1. Go to http://localhost:3000/chat
2. Type a message

**Example Queries**:

```
# Simple conversation
Hello, who are you?

# Contacts (if connected)
Search my contacts named Jean

# Emails (if connected)
Show me my last 5 emails

# Calendar (if connected)
What are my events for this week?

# Weather (if API key configured)
What's the weather like in Paris?

# Wikipedia
Tell me about the Eiffel Tower

# Web search (if Perplexity configured)
What are the latest news about AI?

# Routes (if API key configured)
How do I get from Paris to Lyon by car?
What's the distance between my office and the airport?
```

### 5. Explore Grafana Dashboards

1. Open http://localhost:3001
2. Login: `admin` / `admin` (change on first login)
3. Go to "Dashboards" > "Browse"

**Available Dashboards**:

| Dashboard | Description |
|-----------|-------------|
| **01-app-performance** | API performance (latency, errors) |
| **02-infra-resources** | System resources (CPU, RAM) |
| **03-business-metrics** | Business metrics (conversations, users) |
| **04-agents-langgraph** | LangGraph agent flow |
| **05-llm-tokens-cost** | Token consumption and LLM costs |
| **06-conversations** | Conversation analytics |
| **08-oauth-security** | OAuth security |
| **09-logs-traces** | Logs and distributed traces |
| **10-redis-rate-limiting** | Redis rate limiting |
| **11-langgraph-framework** | Detailed LangGraph metrics |
| **12-recording-rules-health** | Recording rules health |
| **13-slo-tracking** | SLO tracking (Service Level Objectives) |
| **14-data-registry** | Agent Data Registry |
| **15-checkpoint-observability** | Checkpoint observability |

### 6. Explore Langfuse (LLM Observability)

1. Open http://localhost:3002
2. Login: `admin@lia.local` / `admin123`
3. Explore LLM traces

**Langfuse Metrics**:
- Traces for each LLM call
- Response time per model
- Tokens used (input/output)
- Estimated costs
- Quality evaluation (optional)

---

## Advanced Features

### Enable Voice Mode

#### TTS Configuration

```bash
# In .env

# Default mode: standard (free Edge TTS) or hd (paid OpenAI)
VOICE_TTS_DEFAULT_MODE=standard

# For TTS HD (OpenAI), OpenAI API key must be configured via Admin UI
# Available voices: alloy, echo, fable, onyx, nova, shimmer
VOICE_TTS_HD_VOICE=nova
```

#### STT Configuration

Voice Mode uses Sherpa-onnx (WASM) for wake word detection and Whisper Small (OpenAI) for transcription.

```bash
# In .env

# Enable/disable the "OK" wake word
VOICE_WAKE_WORD_ENABLED=true

# VAD sensitivity (Voice Activity Detection)
VOICE_VAD_THRESHOLD=0.5
```

#### Usage

1. Open the chat: http://localhost:3000/chat
2. Click the microphone icon
3. Choose the mode:
   - **Wake Word**: Say "OK" to activate
   - **Push-to-Talk**: Hold the button
4. Speak naturally
5. The transcription appears automatically

### Configure Interest Learning

The system automatically learns interests by analyzing conversations.

```bash
# In .env

# Enable automatic extraction
INTEREST_LEARNING_ENABLED=true

# Confidence threshold for creating an interest (Beta(2,1))
INTEREST_MIN_CONFIDENCE=0.6

# Decay factor for unused interests
INTEREST_DECAY_FACTOR=0.95
```

Interests are visible in **Settings > Interests**.

### Configure OAuth Health Check

Proactive monitoring of OAuth connectors.

```bash
# In .env

# Enable periodic verification
OAUTH_HEALTH_CHECK_ENABLED=true

# Verification interval (minutes)
OAUTH_HEALTH_CHECK_INTERVAL_MINUTES=5

# Enable FCM notifications
FCM_NOTIFICATIONS_ENABLED=true
```

### Configure Scheduled Actions

Scheduled actions allow you to program recurring actions executed automatically (email sending, verifications, reminders).

```bash
# In .env

# Global feature flag
SCHEDULED_ACTIONS_ENABLED=true
```

> See [SCHEDULED_ACTIONS.md](./technical/SCHEDULED_ACTIONS.md) and [GUIDE_SCHEDULED_ACTIONS.md](./guides/GUIDE_SCHEDULED_ACTIONS.md) for complete documentation.

### Configure MCP (Model Context Protocol)

MCP allows connecting external tool servers (admin or per-user).

```bash
# In .env

# Admin MCP (shared servers)
MCP_ENABLED=true

# Per-user MCP (each user connects their own servers)
MCP_USER_ENABLED=true  # Requires MCP_ENABLED=true

# Limits
MCP_MAX_TOOLS_PER_SERVER=50
MCP_CONNECTION_TIMEOUT=30

# MCP Apps (interactive iframe widgets)
MCP_APPS_MAX_HTML_SIZE=500000

# LLM-based domain description auto-generation
MCP_DESCRIPTION_LLM_PROVIDER=openai
MCP_DESCRIPTION_LLM_MODEL=gpt-4.1-mini

# Excalidraw Iterative Builder (diagrams)
MCP_EXCALIDRAW_LLM_PROVIDER=anthropic
MCP_EXCALIDRAW_LLM_MODEL=claude-opus-4-6
```

> See [MCP_INTEGRATION.md](./technical/MCP_INTEGRATION.md) and [GUIDE_MCP_INTEGRATION.md](./guides/GUIDE_MCP_INTEGRATION.md) for complete documentation.

### Configure Telegram (Multi-Channel Messaging)

The Telegram channel allows chatting with LIA directly from Telegram (text, voice, HITL).

```bash
# In .env

# Global channels feature flag
CHANNELS_ENABLED=true

# Telegram bot (obtain via @BotFather on Telegram)
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...

# Secret for webhook validation (generate with openssl rand -hex 32)
TELEGRAM_WEBHOOK_SECRET=your-secret-here
```

**Webhook configuration**:
1. Create a bot via [@BotFather](https://t.me/BotFather) on Telegram
2. Configure the webhook: `https://api.your-domain.com/api/v1/channels/telegram/webhook`
3. Users link their account via an OTP code in Settings > Telegram

> See [CHANNELS_INTEGRATION.md](./technical/CHANNELS_INTEGRATION.md) and [GUIDE_TELEGRAM_INTEGRATION.md](./guides/GUIDE_TELEGRAM_INTEGRATION.md) for complete documentation.

### Configure Heartbeat Autonome (Proactive Notifications)

LIA takes the initiative to inform you when relevant (upcoming events, weather changes, interests).

```bash
# In .env

# Global feature flag (must be true to enable)
HEARTBEAT_ENABLED=true

# Scheduler interval (minutes, 10-120)
HEARTBEAT_NOTIFICATION_INTERVAL_MINUTES=30

# Default maximum notifications per day (1-8)
# Users can adjust this from Settings
HEARTBEAT_MAX_PER_DAY_DEFAULT=3

# Global cooldown between notifications (hours)
HEARTBEAT_GLOBAL_COOLDOWN_HOURS=2

# LLM models (decision = budget-friendly, message = personality-aware)
HEARTBEAT_DECISION_LLM_MODEL=gpt-4.1-mini
HEARTBEAT_MESSAGE_LLM_MODEL=gpt-4.1-mini

# Weather change detection thresholds
HEARTBEAT_WEATHER_RAIN_THRESHOLD_HIGH=0.6
HEARTBEAT_WEATHER_TEMP_CHANGE_THRESHOLD=5.0
HEARTBEAT_WEATHER_WIND_THRESHOLD=14.0
```

**User side**: Settings > Proactive Notifications > Enable, choose max/day, enable/disable push, configure time windows (independent from interests).

> See [HEARTBEAT_AUTONOME.md](./technical/HEARTBEAT_AUTONOME.md) for complete technical documentation.

### Feature Flags Reference

All optional features are disabled by default. Enable them in `.env`:

| Flag | Feature | Dependencies |
|------|---------|-------------|
| `HEARTBEAT_ENABLED` | Autonomous proactive notifications | — |
| `CHANNELS_ENABLED` | Multi-channel messaging (Telegram) | `TELEGRAM_BOT_TOKEN` |
| `MCP_ENABLED` | Admin MCP servers | — |
| `MCP_USER_ENABLED` | Per-user MCP connections | `MCP_ENABLED=true` |
| `FCM_NOTIFICATIONS_ENABLED` | Firebase push notifications | FCM credentials |
| `SCHEDULED_ACTIONS_ENABLED` | User-scheduled deferred actions | — |
| `SUB_AGENTS_ENABLED` | Persistent specialized sub-agents (F6) | — |
| `SKILLS_ENABLED` | Skills system (SKILL.md) | — |
| `GEOIP_ENABLED` | IP geolocation in logs | DB-IP Lite MMDB file |
| `INTEREST_LEARNING_ENABLED` | Automatic interest extraction | — |
| `OAUTH_HEALTH_CHECK_ENABLED` | Proactive connector monitoring | — |
| `USAGE_LIMITS_ENABLED` | Per-user usage quotas (tokens, messages, cost) | — |

### Recommended LLM Configuration (Optimal Quality / Cost)

LIA uses **44 specialized LLM slots**, each independently configurable per provider, model, and parameters. The configuration below represents the **optimal balance between response quality and LLM costs**, tested in production. It is the default shipped with LIA.

> **Fully customizable**: Every slot can be changed at runtime via the **Admin UI** (Settings > Administration > LLM Configuration). You can use any supported provider (OpenAI, Anthropic, DeepSeek, Google Gemini, Ollama, Perplexity, Qwen) and mix them freely. Changes are hot-reloaded (no restart needed).

#### Pipeline (Orchestration & Routing)

| Slot | Provider | Model | Temp | Reasoning | Max Tokens | Rationale |
|------|----------|-------|------|-----------|------------|-----------|
| **Semantic Pivot** | OpenAI | `gpt-4.1-mini` | 0.2 | — | 5 000 | Fast deterministic classification |
| **Query Analyzer** | OpenAI | `gpt-4.1-mini` | 0.2 | — | 5 000 | Balanced intent analysis |
| **Router** | OpenAI | `gpt-4.1-mini` | 0.2 | — | 1 000 | Cheap, structured routing decision |
| **Planner** | Qwen | `qwen3.5-plus` | 0.2 | low | 10 000 | Cost-effective complex plan generation |
| **Semantic Validator** | OpenAI | `gpt-4.1-mini` | 0.2 | — | 1 000 | Strict plan validation |
| **Context Resolver** | OpenAI | `gpt-4.1-mini` | 0.2 | — | 1 000 | Fast context disambiguation |
| **Compaction** | OpenAI | `gpt-4.1-mini` | 0.2 | — | 4 000 | Context window compression |
| **Initiative** | OpenAI | `gpt-4.1-mini` | 0.2 | — | 5 000 | Proactive initiative detection |

#### Domain Agents (Tool-Calling)

| Slot | Provider | Model | Temp | Reasoning | Max Tokens | Rationale |
|------|----------|-------|------|-----------|------------|-----------|
| **Contacts** | OpenAI | `gpt-4.1-nano` | 0.0 | — | 2 000 | Cheapest, tool calls are structured |
| **Emails** | OpenAI | `gpt-4.1-nano` | 0.0 | — | 2 000 | Same — deterministic API calls |
| **Calendar** | OpenAI | `gpt-4.1-nano` | 0.0 | — | 2 000 | Same |
| **Drive** | OpenAI | `gpt-4.1-nano` | 0.0 | — | 2 000 | Same |
| **Tasks** | OpenAI | `gpt-4.1-nano` | 0.0 | — | 2 000 | Same |
| **Weather** | OpenAI | `gpt-4.1-nano` | 0.0 | — | 1 000 | Same, shorter output |
| **Wikipedia** | OpenAI | `gpt-4.1-nano` | 0.0 | — | 2 000 | Same |
| **Perplexity** | OpenAI | `gpt-4.1-nano` | 0.0 | — | 3 000 | Same |
| **Brave** | OpenAI | `gpt-4.1-nano` | 0.0 | — | 2 000 | Same |
| **Web Search** | OpenAI | `gpt-4.1-nano` | 0.3 | — | 4 000 | Slight creativity for search synthesis |
| **Web Fetch** | OpenAI | `gpt-4.1-nano` | 0.3 | — | 3 000 | Same |
| **Browser** | OpenAI | `gpt-5.4` | 0.2 | low | 8 000 | Needs strong reasoning for navigation |
| **Places** | OpenAI | `gpt-4.1-nano` | 0.0 | — | 2 000 | Structured API calls |
| **Routes** | OpenAI | `gpt-4.1-nano` | 0.0 | — | 2 000 | Same |
| **Hue** | OpenAI | `gpt-4.1-nano` | 0.0 | — | 1 000 | Smart home commands are structured |
| **Sub-Agent** | OpenAI | `gpt-5.4` | 0.5 | low | 8 000 | Delegation tasks need strong reasoning |
| **MCP React Agent** | OpenAI | `gpt-5.4` | 0.2 | low | 16 000 | External tool orchestration needs quality |

#### Query & Response

| Slot | Provider | Model | Temp | Reasoning | Max Tokens | Rationale |
|------|----------|-------|------|-----------|------------|-----------|
| **Query Agent** | OpenAI | `gpt-4.1-mini` | 0.0 | — | 5 000 | Balanced conversational answers |
| **Response** | Anthropic | `claude-sonnet-4-6` | 0.7 | low | 5 000 | Natural, personality-aware final output |

#### HITL (Human-in-the-Loop)

| Slot | Provider | Model | Temp | Reasoning | Max Tokens | Rationale |
|------|----------|-------|------|-----------|------------|-----------|
| **HITL Classifier** | OpenAI | `gpt-4.1-nano` | 0.0 | — | 300 | Fast binary classification |
| **HITL Question Gen** | Anthropic | `claude-sonnet-4-6` | 0.5 | low | 500 | Conversational question phrasing |
| **HITL Plan Approval** | Anthropic | `claude-sonnet-4-6` | 0.5 | low | 500 | Natural approval prompts |

#### Memory & Background

| Slot | Provider | Model | Temp | Reasoning | Max Tokens | Rationale |
|------|----------|-------|------|-----------|------------|-----------|
| **Memory Extraction** | Anthropic | `claude-sonnet-4-6` | 0.3 | low | 1 000 | Precise fact extraction |
| **Memory Reference** | OpenAI | `gpt-4.1-mini` | 0.0 | — | 500 | Coreference resolution |
| **Interest Extraction** | Anthropic | `claude-sonnet-4-6` | 0.3 | low | 500 | Background interest detection |
| **Interest Content** | Anthropic | `claude-sonnet-4-6` | 0.7 | low | 1 000 | Creative interest-related content |
| **Heartbeat Decision** | Qwen | `qwen3.5-plus` | 0.3 | none | 2 000 | Cost-effective send/skip decision |
| **Heartbeat Message** | Anthropic | `claude-sonnet-4-6` | 0.7 | low | 500 | Personality-aware proactive messages |
| **Broadcast Translator** | OpenAI | `gpt-4.1-mini` | 0.3 | — | 500 | Fast multilingual translation |
| **Journal Extraction** | Anthropic | `claude-sonnet-4-6` | 0.3 | low | 5 000 | Introspective journal entry creation |
| **Journal Consolidation** | Qwen | `qwen3.5-plus` | 0.5 | none | 10 000 | Daily journal synthesis |

#### Specialized

| Slot | Provider | Model | Temp | Reasoning | Max Tokens | Rationale |
|------|----------|-------|------|-----------|------------|-----------|
| **Voice Comment** | OpenAI | `gpt-4.1-mini` | 0.7 | — | 500 | Natural voice commentary |
| **MCP Description** | OpenAI | `gpt-4.1-mini` | 0.3 | — | 300 | Auto-describe MCP server tools |
| **MCP Excalidraw** | Anthropic | `claude-opus-4-6` | 0.2 | medium | 20 000 | Complex diagram generation |
| **Vision Analysis** | OpenAI | `gpt-4.1-mini` | 0.5 | — | 4 096 | Image understanding |
| **Skill Translator** | OpenAI | `gpt-4.1-mini` | 0.3 | — | 1 000 | Skill description i18n |
| **Evaluator** | OpenAI | `gpt-4.1-mini` | 0.0 | — | 1 000 | LLM-as-Judge scoring |
| **Image Generation** | OpenAI | `gpt-image-1` | 0.0 | — | 1 | AI image generation |

#### Design Principles

The configuration follows a **tiered strategy**:

1. **`gpt-4.1-nano`** (cheapest) — Domain agents doing structured tool calls. These don't need strong reasoning, just reliable function calling.
2. **`gpt-4.1-mini`** — Pipeline nodes, memory, background tasks. Good balanced reasoning at low cost.
3. **`qwen3.5-plus`** — Cost-effective reasoning for planning and background tasks (planner, heartbeat decision, journal consolidation).
4. **`gpt-5.4`** — Advanced agents needing strong autonomous reasoning (browser, sub-agent, MCP react).
5. **`claude-sonnet-4-6`** — Core intelligence: response, HITL, memory extraction. Best quality/cost ratio for personality-aware and nuanced output.
6. **`claude-opus-4-6`** — Reserved for demanding creative tasks (Excalidraw diagram generation).

> **Cost optimization tip**: Domain agents (`gpt-4.1-nano`) represent 50%+ of all LLM calls but a tiny fraction of cost. The real cost drivers are **Response** and **Planner** — switching these to cheaper models has the biggest cost impact (but also the biggest quality impact).

### Running Tests

#### Backend Tests

```bash
# Fast unit tests (no database required, used by pre-commit)
task test:backend:unit:fast

# All unit tests (including slow)
task test:backend:unit

# Integration tests (requires running infrastructure)
task test:backend:integration

# Full exhaustive suite
task test:backend:exhaustive

# Single test file
cd apps/api && .venv/Scripts/pytest tests/unit/test_specific.py -v
```

#### Frontend Tests

```bash
# Single run
task test:frontend

# Watch mode
cd apps/web && pnpm test:watch

# With coverage
cd apps/web && pnpm test:coverage
```

#### Pre-commit Hooks

Pre-commit hooks run automatically on `git commit` and check:
- **Security**: detects `.bak` files, hardcoded secrets
- **Backend**: Ruff + Black + MyPy + fast unit tests
- **Frontend**: ESLint + TypeScript type-check
- **LangGraph safety**: blocks synchronous Store calls (must use async variants)

```bash
# Run manually
task pre-commit

# Full CI locally
task ci
```

### Using Claude Skills

The 10 skills are auto-discovered via `.claude/skills/`. To use them:

1. Open Claude Code in the project
2. Formulate a request matching the skill:
   - "I have a bug in the router" -> `analyzing-bugs`
   - "Review this code" -> `reviewing-code`
   - "How to structure this feature" -> `designing-architecture`

See [CLAUDE.md](../CLAUDE.md) for the complete list.

---

## Troubleshooting

### Problem: Backend Won't Start

#### Error: `ModuleNotFoundError`

```bash
cd apps/api
source venv/bin/activate
pip install -e ".[dev]"
```

#### Error: `Connection refused` PostgreSQL

```bash
# Check that PostgreSQL is running
docker compose -f docker-compose.dev.yml ps postgres

# If not running
docker compose -f docker-compose.dev.yml up -d postgres

# Check the logs
docker compose -f docker-compose.dev.yml logs postgres
```

#### Error: `Connection refused` Redis

```bash
# Check Redis
docker compose -f docker-compose.dev.yml ps redis

# Test connectivity
docker compose -f docker-compose.dev.yml exec redis redis-cli -a "$REDIS_PASSWORD" ping
# Expected response: PONG
```

### Problem: Frontend Won't Start

#### Error: `Cannot find module 'next'`

```bash
cd apps/web
rm -rf node_modules
pnpm install
```

#### Error: `EADDRINUSE: port 3000 already in use`

```bash
# Linux/macOS
lsof -i :3000
kill -9 <PID>

# Windows
netstat -ano | findstr :3000
taskkill /PID <PID> /F

# Or start on a different port
pnpm dev -- -p 3001
```

### Problem: Alembic Migrations

#### Error: `Target database is not up to date`

```bash
cd apps/api
source venv/bin/activate

# Check the current state
alembic current

# Apply all migrations
alembic upgrade head

# If the error persists, reset (WARNING: data loss!)
alembic downgrade base
alembic upgrade head
```

### Problem: LLM API Keys

#### Error: `AuthenticationError: Incorrect API key`

LLM API keys are managed via the **Admin UI** (Settings > Administration > LLM Configuration), not in `.env`.

1. Log in as admin
2. Go to **Settings** > **Administration** > **LLM Configuration**
3. In the **Provider Keys** section, verify the key status for the failing provider
4. Update or re-enter the API key (keys are encrypted at rest)
5. Changes take effect immediately (no restart needed)

If the Admin UI is not accessible (e.g., first startup), you can temporarily set the key in `.env` as fallback:

```bash
# Temporary fallback only — prefer Admin UI
OPENAI_API_KEY=sk-proj-...
```

### Problem: Docker Desktop Network Access on Windows

#### Symptom: API inaccessible from the local network

On **Windows with Docker Desktop**, exposed ports are only accessible on `localhost` by default, not on the local network IP (e.g., `192.168.0.x`).

**Diagnosis**:
```bash
# From the Windows machine
curl -k https://localhost:8000/docs     # Works
curl -k https://YOUR_LOCAL_IP:8000/docs  # Timeout

# Inside the container, the API responds correctly
docker exec lia-api-dev python -c "import httpx; print(httpx.get('https://127.0.0.1:8000/docs', verify=False).status_code)"
# Output: 200
```

**Cause**: Docker Desktop on Windows uses WSL2 with a NAT that does not automatically expose ports on all network interfaces.

**Solution 1: Windows Port Forwarding (netsh)**

```powershell
# In Administrator PowerShell
# Replace YOUR_LOCAL_IP with your local IP (ipconfig)

# Add forwarding
netsh interface portproxy add v4tov4 listenaddress=YOUR_LOCAL_IP listenport=8000 connectaddress=127.0.0.1 connectport=8000

# Verify the configuration
netsh interface portproxy show v4tov4

# Remove forwarding (if needed)
netsh interface portproxy delete v4tov4 listenaddress=YOUR_LOCAL_IP listenport=8000
```

**Solution 2: Use 0.0.0.0 in Docker Desktop Settings**

1. Docker Desktop -> Settings -> Resources -> Network
2. Check "Enable host networking" (if available)
3. Restart Docker Desktop

**Solution 3: Use a Reverse Proxy (Caddy/nginx)**

```bash
# Example with Caddy (simple)
caddy reverse-proxy --from :8000 --to localhost:8000
```

**Note**: This issue does not exist on native Linux or macOS where ports are exposed on all interfaces by default.

**See also**: [Docker Desktop Networking](https://docs.docker.com/desktop/networking/)

---

### Problem: Docker Compose

#### Error: Services Won't Start

```bash
# View all service logs
docker compose -f docker-compose.dev.yml logs

# Logs for a specific service
docker compose -f docker-compose.dev.yml logs api

# Restart a service
docker compose -f docker-compose.dev.yml restart api

# Recreate containers
docker compose -f docker-compose.dev.yml up -d --force-recreate
```

#### Error: Corrupted Volumes

```bash
# Delete and recreate (WARNING: data loss!)
docker compose -f docker-compose.dev.yml down -v
docker compose -f docker-compose.dev.yml up -d
```

### Production Deployment

LIA supports multi-architecture Docker builds (`linux/amd64` + `linux/arm64`) for deployment on standard servers and Raspberry Pi.

#### Build Production Images

```bash
# Build all production images
task build

# Or manually
docker compose -f docker-compose.prod.yml build
```

#### Production Configuration

1. Copy `.env.prod.example` to `.env.prod` and configure all values
2. Production uses `docker-compose.prod.yml` (optimized, no dev tools)
3. SOPS encryption is available for secrets management (see below)

#### SOPS Secrets Encryption

LIA uses [SOPS](https://github.com/getsops/sops) with [Age](https://github.com/FiloSottile/age) for encrypting sensitive environment variables at rest.

```bash
# Install SOPS and Age
# Windows: choco install sops age
# macOS: brew install sops age
# Linux: apt install sops age

# Generate an Age key pair
age-keygen -o keys/age-key-prod.txt

# Encrypt .env.prod
export SOPS_AGE_KEY_FILE=keys/age-key-prod.txt
sops --encrypt --input-type dotenv --output-type dotenv .env.prod > .env.prod.encrypted

# Decrypt
sops --decrypt --input-type dotenv --output-type dotenv .env.prod.encrypted > .env.prod
```

> **Important**: The `keys/` directory is gitignored. Never commit Age private keys to the repository. Only the `.sops.yaml` configuration (with public keys) is tracked.

#### Deploy Script

```bash
# Deploy to production server (uses scripts/deploy/deploy-prod.ps1)
task deploy:prod

# Dry run (simulation)
task deploy:prod:dry-run
```

> See the [Deployment Guide](./guides/GUIDE_DEPLOYMENT.md) for detailed production setup instructions.

### Problem: Slow Performance

#### Diagnosis

```bash
# Check Prometheus metrics
curl http://localhost:9090/api/v1/query?query=llm_api_latency_seconds

# View backend logs with jq
docker compose -f docker-compose.dev.yml logs api | grep -i duration

# Check container resources
docker stats
```

#### Solutions

| Symptom | Diagnosis | Solution |
|---------|-----------|----------|
| **Slow LLM** | Model too heavy | Use gpt-4.1-nano vs gpt-4.1-mini |
| **Slow DB** | Missing indexes | Check `EXPLAIN ANALYZE` on queries |
| **Slow Redis** | Saturated memory | Increase `maxmemory` or cleanup |
| **Slow API** | N+1 queries | Enable SQLAlchemy eager loading |

### Problem: Voice Mode

#### Wake word not detecting

```bash
# Check that the browser has microphone access
# Chrome: chrome://settings/content/microphone

# Check console logs (F12)
# Look for: "Sherpa KWS initialized"
```

#### HD TTS not working

1. Verify OpenAI API key is configured in **Admin UI** (Settings > Administration > LLM Configuration > Provider Keys)
2. Check TTS mode in `.env`:

```bash
grep VOICE_TTS_DEFAULT_MODE .env
# Should be: VOICE_TTS_DEFAULT_MODE=hd
```

---

## Next Steps

### Recommended Reading

| Priority | Document | Description |
|----------|----------|-------------|
| **1** | [ARCHITECTURE.md](./ARCHITECTURE.md) | Overall system architecture |
| **2** | [technical/GRAPH_AND_AGENTS_ARCHITECTURE.md](./technical/GRAPH_AND_AGENTS_ARCHITECTURE.md) | LangGraph multi-agent system |
| **3** | [technical/HITL.md](./technical/HITL.md) | Human-in-the-Loop v6.0 |
| **4** | [technical/PLANNER.md](./technical/PLANNER.md) | ExecutionPlan DSL + FOR_EACH |
| **5** | [technical/VOICE_MODE.md](./technical/VOICE_MODE.md) | Voice Mode (STT + Wake Word) |

### v6.2-v6.3 Specific Documentation

| Document | Feature |
|----------|---------|
| [technical/INTERESTS.md](./technical/INTERESTS.md) | Interest Learning System |
| [technical/OAUTH_HEALTH_CHECK.md](./technical/OAUTH_HEALTH_CHECK.md) | OAuth Health Check |
| [technical/HYBRID_SEARCH.md](./technical/HYBRID_SEARCH.md) | BM25 hybrid search |
| [technical/SMART_SERVICES.md](./technical/SMART_SERVICES.md) | Smart Services v3 |
| [technical/SUB_AGENTS.md](./technical/SUB_AGENTS.md) | Sub-Agents (F6) |
| [technical/BROWSER_CONTROL.md](./technical/BROWSER_CONTROL.md) | Browser Control (F7) |
| [technical/JOURNALS.md](./technical/JOURNALS.md) | Personal Journals (F8) |

### Practical Tutorials

| Tutorial | Document |
|----------|----------|
| Create a New Agent | [guides/GUIDE_AGENT_CREATION.md](./guides/GUIDE_AGENT_CREATION.md) |
| Add a Tool | [technical/TOOLS.md](./technical/TOOLS.md) |
| Configure Monitoring | [guides/GUIDE_OBSERVABILITE.md](./guides/GUIDE_OBSERVABILITE.md) |
| Optimize Prompts | [technical/PROMPTS.md](./technical/PROMPTS.md) |
| Develop with Skills | [../CLAUDE.md](../CLAUDE.md) |

### Experimentation

```bash
# Run tests to understand the patterns
cd apps/api
pytest tests/unit -v --tb=short

# Explore v3 prompts
ls src/domains/agents/prompts/v*/

# Test different LLM providers
# Edit .env: QUERY_ANALYZER_LLM_PROVIDER=anthropic

# Explore Claude skills
ls .claude/skills/
```

### External Resources

| Resource | Description | Link |
|----------|-------------|------|
| **LangGraph Docs** | Official documentation | [langchain-ai.github.io/langgraph](https://langchain-ai.github.io/langgraph/) |
| **FastAPI Docs** | FastAPI reference | [fastapi.tiangolo.com](https://fastapi.tiangolo.com/) |
| **Next.js Docs** | Next.js reference | [nextjs.org/docs](https://nextjs.org/docs) |
| **Grafana Dashboards** | Dashboard examples | [grafana.com/grafana/dashboards](https://grafana.com/grafana/dashboards/) |
| **Langfuse Docs** | LLM Observability | [langfuse.com/docs](https://langfuse.com/docs) |
| **Claude Code** | AI CLI assistant | [claude.ai/claude-code](https://claude.ai/claude-code) |
| **Sherpa-onnx** | Wake word / KWS | [k2-fsa.github.io/sherpa](https://k2-fsa.github.io/sherpa/) |

---

## Final Checklist

Before considering your installation complete, verify:

### Infrastructure

- [ ] Docker Compose launched without errors (`docker compose ps` - all "healthy")
- [ ] PostgreSQL accessible (port 5432)
- [ ] Redis accessible (port 6379)
- [ ] Backend starts (`curl http://localhost:8000/health`)
- [ ] Frontend accessible (`http://localhost:3000`)

### Configuration

- [ ] SECRET_KEY and FERNET_KEY generated (unique!)
- [ ] At least 1 LLM provider API key configured via Admin UI (OpenAI minimum)
- [ ] Google Cloud: OAuth consent screen + APIs enabled + credentials created (if using Google connectors)
- [ ] Microsoft Azure: App registration + API permissions + client secret (if using Microsoft connectors)
- [ ] Firebase: Project created + FCM enabled + service account + VAPID key (if using push notifications)
- [ ] POSTGRES_* and REDIS_* variables configured

### Features

- [ ] User account created
- [ ] Login successful
- [ ] Simple conversation works
- [ ] API Docs accessible (`http://localhost:8000/docs`)

### v6.2-v6.3 Features

- [ ] Voice Mode works (microphone authorized, wake word detected)
- [ ] TTS responds (Standard or HD depending on config)
- [ ] Interest Learning enabled (visible in Settings)
- [ ] OAuth Health Check active (logs show "health check passed")

### Observability

- [ ] Grafana accessible (`http://localhost:3001`)
- [ ] Prometheus accessible (`http://localhost:9090`)
- [ ] Langfuse accessible (`http://localhost:3002`)
- [ ] 15 dashboards load correctly

### Tests

- [ ] Unit tests pass: `pytest tests/unit -v`
- [ ] Pre-commit hooks installed: `pre-commit run --all-files`

---

## Support

If you encounter issues not covered by this guide:

| Resource | Description |
|----------|-------------|
| **GitHub Issues** | Documented common problems |
| **docs/runbooks/** | Resolution procedures |
| **ADR Index** | [docs/architecture/ADR_INDEX.md](./architecture/ADR_INDEX.md) |
| **Security** | [../SECURITY.md](../SECURITY.md) |

### Creating an Issue

Include:
1. LIA version (`git describe --tags`)
2. OS and versions (Docker, Python, Node)
3. Complete logs (sanitized of secrets)
4. Steps to reproduce

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| **3.4** | 2026-04-01 | Added detailed platform setup guides (Google Cloud, Microsoft Azure, Firebase); updated LLM config to Admin UI (removed .env API keys); refreshed 44 LLM slot defaults to current production values |
| **3.2** | 2026-03-20 | Added v6.3 features (Sub-Agents, Browser Control, Personal Journals, System Knowledge Spaces) |
| **3.0** | 2026-03-13 | Added v6.2 features (Telegram, MCP, Heartbeat, Skills, SOPS, Testing, Production Deployment sections) |
| **2.0** | 2026-02-03 | Added v6.0 (Skills, FOR_EACH, Voice Mode, Interest Learning) |
| **1.5** | 2025-12-15 | Added Routes API, OAuth Health Check |
| **1.0** | 2025-10-01 | Initial version |

---

**Congratulations!**

You are now ready to use and develop with LIA v6.3.

**Recommended next step**: [ARCHITECTURE.md](./ARCHITECTURE.md)

---

<p align="center">
  <strong>LIA</strong> — Multi-Agent AI Assistant v6.2
</p>
