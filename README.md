<p align="center">
  <img src="docs/assets/logo.png" alt="LIA — Your life. Your AI. Your rules." width="600" />
</p>

<h1 align="center">LIA</h1>

<p align="center">
  <strong>Intelligent multi-agent conversational assistant with LangGraph orchestration, Human-in-the-Loop, enterprise-grade observability, and full i18n support (6 languages)</strong>
</p>

<p align="center">
  <a href="https://lia.jeyswork.com/"><img src="https://img.shields.io/badge/🚀_Try_LIA-lia.jeyswork.com-0EA5E9?style=for-the-badge" alt="Try LIA"></a>
  &nbsp;&nbsp;
  <a href="https://github.com/jgouviergmail/LIA-Assistant/stargazers"><img src="https://img.shields.io/github/stars/jgouviergmail/LIA-Assistant?style=for-the-badge&logo=github&label=Star&color=gold" alt="GitHub Stars"></a>
</p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.12%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+"></a>
  <a href="https://nodejs.org/"><img src="https://img.shields.io/badge/Node.js-22%20LTS-5FA04E?style=flat-square&logo=nodedotjs&logoColor=white" alt="Node.js 22 LTS"></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-0.135.1-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI"></a>
  <a href="https://nextjs.org/"><img src="https://img.shields.io/badge/Next.js-16-000000?style=flat-square&logo=nextdotjs&logoColor=white" alt="Next.js 16"></a>
  <a href="https://langchain-ai.github.io/langgraph/"><img src="https://img.shields.io/badge/LangGraph-1.1.2-FF6F00?style=flat-square" alt="LangGraph"></a>
  <a href="https://python.langchain.com/"><img src="https://img.shields.io/badge/LangChain-1.2.12-4B8BBE?style=flat-square" alt="LangChain"></a>
  <a href="#internationalization-i18n--6-languages"><img src="https://img.shields.io/badge/i18n-6%20languages-E040FB?style=flat-square" alt="6 languages"></a>
  <a href="#license"><img src="https://img.shields.io/badge/License-AGPL--3.0-blue?style=flat-square" alt="License"></a>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#administration--monitoring">Admin & Monitoring</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#documentation">Documentation</a> •
  <a href="#contributing">Contributing</a>
</p>

<p align="center">
  <strong>Version 1.9.5</strong> — Context Store Fix, HITL Enhancements, Cross-Provider Email Improvements — March 2026
</p>

---

## Table of Contents

- [Why LIA?](#why-lia)
- [Try LIA Online](#try-lia-online)
- [Screenshots](#screenshots)
- [Features](#features)
- [Administration & Monitoring](#administration--monitoring)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Technologies](#technologies)
- [Documentation](#documentation)
- [Tests](#tests)
- [CI/CD](#cicd)
- [Performance](#performance)
- [Security](#security)
- [Contributing](#contributing)
- [Support](#support)
- [License](#license)
- [Acknowledgments](#acknowledgments)

---

## Why LIA?

**LIA** solves the fundamental problems of today's AI assistants:

| Problem | LIA Solution |
|---------|---------------------|
| **Unpredictable LLM costs** | Real-time token tracking, budget alerts, 93% optimization |
| **Uncontrolled hallucinations** | Human-in-the-Loop (HITL) with 6 approval levels |
| **Fragmented integrations** | Unified multi-domain orchestration (18 agents + MCP + sub-agents) |
| **Limited observability** | 500+ Prometheus metrics, 18 Grafana dashboards, GeoIP analytics |
| **Inconsistent performance** | Local E5 embeddings (~50ms), semantic routing +48% accuracy |

### Primary Use Cases

```
📅 "Find my meetings for tomorrow and send a reminder to all participants"
📧 "Summarize my unread emails from this week that have attachments"
👥 "Update the companies of my contacts who work at startups"
🔔 "Remind me tomorrow at 9am to call Marie for her birthday"
```

---

## Try LIA Online

<p align="center">
  <a href="https://lia.jeyswork.com/"><img src="https://img.shields.io/badge/🚀_Try_LIA-lia.jeyswork.com-0EA5E9?style=for-the-badge" alt="Try LIA"></a>
</p>

LIA is available as a hosted service at **https://lia.jeyswork.com/** — no installation required.

> **Closed beta**: Access is currently limited to a restricted number of users, at the administrator's discretion. To request an invitation, contact **liamyassistant@gmail.com**.

---

## Screenshots

<p align="center">
  <img src="docs/assets/screenshot-homepage.png" alt="Dashboard — Homepage with usage statistics" width="800" />
  <br /><em>Dashboard — Homepage with quick access, usage statistics, and personalized greeting</em>
</p>

<p align="center">
  <img src="docs/assets/screenshot-chat.png" alt="Chat — Multi-agent conversation with debug panel" width="800" />
  <br /><em>Chat — Multi-agent conversation with real-time debug panel (right sidebar)</em>
</p>

<details>
<summary><strong>More screenshots</strong></summary>

<p align="center">
  <img src="docs/assets/screenshot-settings-preferences.png" alt="Settings — Preferences (connectors, MCP, themes)" width="800" />
  <br /><em>Settings — Preferences: connectors, MCP servers, language, timezone, and themes</em>
</p>

<p align="center">
  <img src="docs/assets/screenshot-settings-features.png" alt="Settings — Features (memory, interests, notifications)" width="800" />
  <br /><em>Settings — Features: LIA Style, long-term memory, interests, proactive notifications, scheduled actions, sub-agents, channels</em>
</p>

<p align="center">
  <img src="docs/assets/screenshot-settings-administration.png" alt="Settings — Administration panel" width="800" />
  <br /><em>Settings — Administration: LLM config, RAG Spaces, users, connectors, pricing, skills, voice, broadcast, debug</em>
</p>

<p align="center">
  <img src="docs/assets/screenshot-settings-administration-oneclick.png" alt="Settings — One-click administration" width="800" />
  <br /><em>Administration — One-click simplicity: every admin action is accessible in a single click, no technical skills required</em>
</p>

<p align="center">
  <img src="docs/assets/screenshot-settings-administration-llm.png" alt="Settings — LLM Configuration with multi-provider support" width="800" />
  <br /><em>Administration — LLM Configuration: 7 providers (OpenAI, Anthropic, DeepSeek, Qwen, Perplexity, Ollama, Gemini), per-node model selection</em>
</p>

<p align="center">
  <img src="docs/assets/screenshot-faq.png" alt="FAQ — Searchable help center" width="800" />
  <br /><em>FAQ — Searchable help center with categorized Q&A sections</em>
</p>

</details>

---

## Features

### Multi-Agent Intelligence (LangGraph 1.x)

- **19+ Specialized Agents**: Contacts, Emails, Calendar, Drive, Tasks, Reminders, Places, Routes, Weather, Wikipedia, Perplexity, Brave, Web Search, Web Fetch, Browser Control, Smart Home (Philips Hue), Context, Query + dynamic MCP agents
- **MCP (Model Context Protocol)**: Per-user external tool servers with OAuth 2.1, SSRF protection, structured items parsing, MCP Apps (interactive iframe widgets), Excalidraw Iterative Builder
- **Skills (agentskills.io)**: Open standard for expert instructions (SKILL.md), model-driven activation, progressive disclosure (L1/L2/L3), sandboxed scripts, marketplace import, auto-translated multi-language descriptions, ZIP download, admin management. **Planner skill guard**: multi-domain deterministic skills are protected from false-positive early clarification requests via domain overlap detection (`_has_potential_skill_match`). **Built-in Skill Generator**: create custom skills in natural language — the assistant guides you through need analysis, archetype selection, and produces a ready-to-import SKILL.md with automatic validation
- **File Attachments (Images, PDF)**: Upload with client-side compression, configurable LLM vision analysis, PDF text extraction, strict per-user isolation
- **Semantic Routing**: Binary classification with confidence scoring (high >0.85, medium >0.65)
- **Multi-Step Planning**: ExecutionPlan DSL with dependencies and conditions
- **Parallel Execution**: asyncio.gather for independent domains
- **Intelligent Context Compaction**: LLM-based conversation history summarization when token count exceeds dynamic threshold (ratio of response model context window). Preserves identifiers (UUIDs, URLs, emails). `/resume` command for manual trigger. 4 HITL safety conditions prevent compaction during active approval flows

### Voice TTS Dual-Mode

| Mode | Provider | Cost | Quality |
|------|----------|------|---------|
| **Standard** | Edge TTS (Microsoft Neural) | Free | High |
| **HD** | OpenAI TTS | $15-30/1M chars | Premium |
| **HD** | Gemini TTS | Variable | Premium |

- **Factory Pattern**: Interchangeable implementations
- **Admin Control**: Mode controlled via System Settings
- **Graceful Degradation**: Automatic HD to Standard fallback

### FOR_EACH Iteration Pattern

```python
# DSL Syntax
ExecutionStep(
    tool_name="send_email",
    for_each="$steps.get_contacts.contacts",
    for_each_max=10
)
```

- **HITL Thresholds**: Mutations >= 1 trigger mandatory approval
- **Bulk Operations**: Send emails, update contacts, mass deletions

### Smart Services (Token Savings 89%)

| Service | Role | Optimization |
|---------|------|--------------|
| QueryAnalyzerService | Routing decision | LRU Cache |
| SmartPlannerService | ExecutionPlan generation | Pattern Learning |
| SmartCatalogueService | Tool filtering | 96% token reduction |
| PlanPatternLearner | Bayesian learning | Bypass >90% confidence |

### Google Integrations (OAuth 2.1 + PKCE)

- **Gmail**: Search, read, send, reply, trash
- **Contacts**: Fuzzy search, list, details (14+ schemas)
- **Calendar**: Search, create, update events
- **Drive**: Search, file/folder listing
- **Tasks**: Full CRUD with completion

### Apple iCloud Integrations

- **Apple Mail**: Search, read, send, reply, forward, trash (IMAP/SMTP)
- **Apple Calendar**: Search, create, update, delete events (CalDAV)
- **Apple Contacts**: Search, list, create, update, delete (CardDAV)

### Microsoft 365 Integrations (OAuth 2.0 + PKCE)

- **Outlook**: Search, read, send, reply, forward, trash (Graph API)
- **Calendar**: Search, create, update, delete events (calendarView)
- **Contacts**: Search, list, create, update, delete
- **To Do**: Full CRUD with completion (task lists + tasks)
- **Multi-tenant**: Personal accounts (outlook.com) and business accounts (Azure AD) via `tenant=common`

### 3-Way Mutual Exclusivity

- Only one provider per functional category (email, calendar, contacts, tasks)
- 3 supported providers: Google, Apple, Microsoft
- Activating a new provider automatically deactivates the active competitor

### Smart Home — Philips Hue

- **Voice-controlled lighting**: Turn lights on/off, adjust brightness and colors via natural language
- **Room & scene management**: Control entire rooms or activate predefined scenes ("dim the living room", "activate movie mode")
- **Local or cloud connection**: Connect via local bridge IP or Philips Hue cloud API
- **Feature flag**: `PHILIPS_HUE_ENABLED=true` to enable

### Human-in-the-Loop (HITL)

| Type | Trigger | Severity |
|------|---------|----------|
| Plan Approval | Destructive actions | CRITICAL |
| Clarification | Detected ambiguity | WARNING |
| Draft Critique | Email/Event review | INFO |
| Destructive Confirm | Deletion of >= 3 items | CRITICAL |
| FOR_EACH Confirm | Bulk mutations | WARNING |
| Modifier Review | Review and approve AI-suggested modifications to draft content | INFO |

### Enterprise Observability

- **Prometheus**: 500+ custom metrics (agents, LLM, infrastructure)
- **Grafana**: 18 production-ready dashboards
- **Langfuse**: LLM-specific tracing with prompt versions
- **Loki**: Structured JSON logs with PII filtering
- **Tempo**: Distributed cross-service tracing

### Cost Tracking & Billing

| Type | Tracking | Export |
|------|----------|--------|
| **LLM Tokens** | Per node, per provider | Detailed CSV |
| **Google API** | Per endpoint, per user | Detailed CSV |
| **Aggregated** | Per user, per period | CSV summary |

- **Google Maps Platform**: Places, Routes, Geocoding, Static Maps
- **Dynamic Pricing**: Admin UI for pricing CRUD
- **ContextVar Pattern**: Implicit tracking without explicit parameter passing
- **Admin CSV Exports**: Token usage, Google API usage, Consumption summary (all users or filtered by user)
- **User CSV Exports** (v1.9.1): Personal consumption export in Settings > Features — users export their own data only (`user_id` forced server-side, IDOR-safe)

### Security & Compliance

- **OAuth 2.1**: PKCE (S256), single-use state token
- **BFF Pattern**: HTTP-only cookies, Redis session with 24h TTL
- **Encryption**: Fernet (credentials), bcrypt (passwords)
- **GDPR**: Automatic PII filtering, pseudonymization, personal data export (Art. 20 data portability)
- **Per-User Usage Limits**: Token, message, and cost quotas (period/global) with 5-layer defense-in-depth enforcement, admin kill switch, real-time dashboard with WebSocket gauges. Feature flag: `USAGE_LIMITS_ENABLED=true`

### MCP (Model Context Protocol)

- **Per-user external servers**: Each user connects their own MCP servers (third-party tools)
- **Flexible authentication**: None, API Key, Bearer Token, OAuth 2.1 (DCR + PKCE S256)
- **Enhanced security**: HTTPS-only, SSRF prevention (DNS resolution + IP blocklist), encrypted credentials (Fernet)
- **Structured Items Parsing**: Automatic JSON array detection into individual items with McpResultCard HTML
- **Auto-generated descriptions**: LLM analysis of discovered tools to generate domain descriptions optimized for intelligent routing
- **Per-server rate limiting**: Redis sliding window per server/tool
- **Feature flag**: `MCP_USER_ENABLED=true` to enable per-user

### Multi-Channel Messaging (Telegram)

- **Bidirectional Telegram**: Full chat with LIA via Telegram (text, voice, HITL)
- **OTP Linking**: Secure account-to-Telegram linking via 6-digit OTP code (single-use, 5min TTL, brute-force protection)
- **HITL Inline Keyboards**: Approval/rejection buttons localized in 6 languages directly in Telegram
- **Voice Transcription**: Telegram voice messages to STT (Sherpa Whisper) to text processing
- **Proactive Notifications**: Reminders and interest alerts also sent via Telegram
- **Extensible Architecture**: `BaseChannelSender`/`BaseChannelWebhookHandler` abstraction for future channels (Discord, WhatsApp)
- **Observability**: 12 dedicated Prometheus RED metrics (latency, errors, volumes)
- **Feature flag**: `CHANNELS_ENABLED=true` to enable

### Autonomous Heartbeat — Proactive Notifications

- **LLM-driven proactivity**: LIA takes the initiative to inform you when relevant (weather, calendar, interests)
- **Multi-source aggregation**: Calendar, Weather (with change detection), Tasks, Interests, Memories, Activity — parallel fetch
- **2-phase LLM decision**: Phase 1 (structured output, cost-effective model) decides whether to notify, Phase 2 rewrites with user personality and language
- **Intelligent anti-redundancy**: Recent history + cross-type dedup (heartbeat vs. interests) in the decision prompt
- **User control**: Push notifications (FCM/Telegram) independently toggleable, configurable daily max (1-8), dedicated time windows (independent from interests)
- **Weather change detection**: Rain start/end, temperature drops, wind alerts — truly actionable notifications
- **Feature flag**: `HEARTBEAT_ENABLED=true` to enable

### Scheduled Actions

- **Recurring actions**: Schedule repetitive actions executed automatically (send emails, checks, reminders)
- **Timezone-aware**: Correct timezone handling per user
- **Retry logic**: Automatic retries on failure with back-off
- **Auto-disable**: Automatic deactivation after N consecutive failures
- **Multi-channel integration**: Result notifications via FCM, SSE, and Telegram
- **Feature flag**: `SCHEDULED_ACTIONS_ENABLED=true` to enable

### Sub-Agents (F6)

- **Persistent specialized agents**: Create sub-agents with custom instructions, skills, and LLM configuration
- **Read-only V1**: Sub-agents perform research, analysis, and synthesis — no write operations
- **Template-based creation**: Pre-defined templates (Research Assistant, Writing Assistant, Data Analyst)
- **Invisible to user**: The principal assistant orchestrates sub-agents and presents results naturally
- **Token guard-rails**: Per-execution budget, daily budget, auto-disable after consecutive failures
- **Feature flag**: `SUB_AGENTS_ENABLED=true` to enable (default: false)

### RAG Knowledge Spaces

- **Personal knowledge bases**: Create spaces, upload documents in 15+ formats (PDF, DOCX, PPTX, XLSX, CSV, RTF, HTML, EPUB, and more), automatic chunking and embedding
- **Google Drive folder sync**: Link Google Drive folders to spaces for automatic file vectorization with incremental change detection (new, modified, deleted). Feature flag: `RAG_SPACES_DRIVE_SYNC_ENABLED`
- **Hybrid search**: Semantic similarity (pgvector cosine) + BM25 keyword matching with configurable alpha fusion
- **Response enrichment**: RAG context automatically injected into assistant responses when active spaces exist
- **Full cost transparency**: Embedding costs tracked per document and per query, visible in chat bubbles and dashboard
- **System knowledge spaces**: Built-in FAQ knowledge base (119+ Q/A across 17 sections) indexed from Markdown files (`docs/knowledge/`). `is_app_help_query` detection by QueryAnalyzer, RoutingDecider Rule 0 override, App Identity Prompt injection with lazy loading (zero overhead on normal queries). Auto-indexed at startup with SHA-256 hash-based staleness. Admin UI for reindex and staleness monitoring. [ADR-058](./docs/architecture/ADR-058-System-RAG-Spaces.md)
- **Admin reindexation**: Full reindex when embedding model changes, with Redis mutual exclusion and automatic dimension ALTER. System spaces have independent reindex via admin API
- **Observability**: 17 Prometheus metrics (14 user + 3 system), dedicated Grafana dashboard
- **Feature flags**: `RAG_SPACES_ENABLED=true` (user spaces), `RAG_SPACES_SYSTEM_ENABLED=true` (system FAQ spaces)

### Personal Journals (Carnets de Bord)

- **Introspective notebooks**: The assistant maintains thematic journals (self-reflection, user observations, ideas & analyses, learnings) written in first person, colored by its active personality
- **Dual trigger**: Post-conversation extraction (fire-and-forget) + periodic consolidation (APScheduler). The assistant decides freely what to write
- **Semantic context injection**: Journal entries injected into both response AND planner prompts via E5-small embedding similarity search with configurable minimum score prefiltering (`JOURNAL_CONTEXT_MIN_SCORE`). Results include scores — the LLM decides relevance autonomously
- **Prompt-driven lifecycle**: The assistant manages its own journals — no hardcoded auto-archival. Size constraints guide cleanup via prompt engineering
- **Heartbeat integration**: Journal entries enrich proactive notifications via dynamic second-pass query built from aggregated context (calendar, weather, emails). Toggleable source badge in heartbeat settings
- **Full user control**: Enable/disable (data preserved), consolidation toggle, conversation history analysis (with cost warning), 4 configurable numeric settings, full CRUD in Settings
- **Anti-hallucination guards**: Three-layer defense against LLM UUID hallucination — prompt guidance with ID reference tables, `field_validator` on entry IDs, and known-ID filtering in both extraction and consolidation services
- **Debug panel**: Dedicated "Personal Journals" section showing injection metrics (per-entry scores with visual bars, budget indicators) AND background extraction results (actions parsed/applied, CREATE/UPDATE/DELETE badges, themes, moods). Extraction data arrives via supplementary `debug_metrics_update` SSE event after background tasks complete
- **Cost transparency**: Real token costs tracked via TrackingContext, visible in Settings and dashboard
- **Feature flags**: `JOURNALS_ENABLED=false` (system), user-level toggle in Settings > Features. [ADR-057](./docs/architecture/ADR-057-Personal-Journals.md)

### MCP Apps — Interactive Widgets

- **Sandboxed iframes**: MCP applications rendered in secure iframes (CSP + COEP `credentialless`)
- **JSON-RPC Bridge**: Bidirectional communication between iframe app and chat via PostMessage JSON-RPC 2.0
- **Excalidraw Iterative Builder**: Diagram generation via a single LLM call (all elements) with automatic position correction
- **`read_me` convention**: MCP servers exposing a `read_me` tool have their content auto-injected into the planner prompt
- **Auto-generated descriptions**: LLM analysis of discovered tools for domain description optimized for routing
- **App-only tools**: Tools with `visibility: ["app"]` filtered from the LLM catalogue (iframe only)

### Internationalization (i18n) — 6 Languages

LIA is fully translated in **6 languages**: English, French, German, Spanish, Italian, and Chinese.

- **Complete UI coverage**: All interfaces, dialogs, notifications, error messages, FAQ, and landing page
- **HITL localized**: Human-in-the-Loop approval prompts adapted per language
- **Proactive notifications**: Heartbeat and reminders delivered in the user's language
- **Telegram**: Inline keyboards and messages localized
- **Skills**: Auto-translated descriptions in all 6 languages
- **react-i18next**: Namespace-based translations with `locales/{lang}/translation.json`

### Landing Page

- **Presentation page**: Responsive landing page with animated components (Hero, Features, Architecture, Security, Stats, Use Cases, How It Works, CTA)
- **SEO & OpenGraph**: Dynamically generated OG image for social media previews
- **Authenticated redirect**: Automatic redirect to dashboard if already logged in

---

## Administration & Monitoring

LIA includes a **full-featured administration interface** — giving operators complete control and real-time visibility over the system without touching configuration files or the database.

### Admin Dashboard

A web-based administration panel covering every operational aspect:

| Section | Capabilities |
|---------|-------------|
| **LLM Configuration** | Model selection per node, provider parameters, temperature/token limits, prompt versions |
| **RAG Knowledge Spaces** | Manage document spaces, embedding configuration, user reindex operations, system knowledge spaces (FAQ staleness, reindex) |
| **Personalities** | Create and manage assistant personalities (tone, language, behavior rules) |
| **User Management** | User accounts, roles, permissions, connector status overview |
| **Connector Management** | Google/Apple/Microsoft OAuth status, token health, per-user provider activation |
| **Skills Management** | Enable/disable skills, edit descriptions, translate in 6 languages, delete |
| **MCP Servers** | Admin-level MCP server configuration, tool discovery, domain descriptions |
| **LLM Pricing** | CRUD for per-model pricing (input/output/cache tokens), used for cost tracking |
| **Google API Pricing** | Per-endpoint pricing configuration for Google Maps Platform services |
| **Voice Settings** | TTS mode selection (Standard/HD), provider configuration |
| **Broadcasting** | Send system-wide notifications to all users or targeted groups |
| **Debug Settings** | Toggle debug panel visibility, configure diagnostic verbosity per user |
| **Usage Limits** | Per-user token/message/cost quotas (period + global), real-time gauges, manual block/unblock, WebSocket live updates |
| **Consumption Export** | CSV export of token usage, Google API usage, and aggregated consumption per user/period |

### Real-Time Debug Panel

A multi-section debug panel embedded in the chat interface, providing real-time introspection into every aspect of a conversation turn:

| Category | Sections |
|----------|----------|
| **Intent Analysis** | Intent classification, Domain detection, Routing decision (with confidence scores) |
| **Execution Pipeline** | Planner output, Execution waves, Tool calls (inputs/outputs), ForEach analysis |
| **LLM Internals** | LLM call details (model, tokens, latency), Token budget tracking, Google API calls |
| **Context & Memory** | Context resolution, Memory injection, Knowledge enrichment, RAG injection (scores), Interest profile |
| **Intelligence** | Intelligent mechanisms (cache hits, pattern learning, semantic expansion) |
| **Lifecycle** | Full request lifecycle with timing breakdown per phase |

> The debug panel is designed for **developers and operators** to diagnose issues, optimize prompts, and understand the agent's decision-making process in real time — without needing external tools or log access.

---

## Quick Start

### Prerequisites

| Software | Version | Required |
|----------|---------|----------|
| Python | 3.12+ | Yes |
| Node.js | 22 LTS | Yes |
| Docker | 24+ | Yes |
| pnpm | 10+ | Yes |
| [Task](https://taskfile.dev/) | 3+ | Yes (build tool) |

All commands are defined in `Taskfile.yml`. Quick start: `task setup` then `task dev`.

### Express Setup (5 minutes)

```bash
# 1. Clone the repository
git clone https://github.com/jgouviergmail/LIA-Assistant.git
cd LIA-Assistant

# 2. Configure environment
cp .env.example .env  # Edit with your API keys

# 3. Full setup (backend + frontend + git hooks)
task setup

# 4. Start all services (API + Web + PostgreSQL + Redis + observability)
task dev
```

<details>
<summary><strong>Manual setup (without Task)</strong></summary>

```bash
# 1. Start the infrastructure
docker compose up -d postgres redis prometheus grafana

# 2. Backend setup
cd apps/api
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../../.env.example .env  # Configure your API keys

# 3. Database migrations
alembic upgrade head

# 4. Frontend setup
cd ../web
pnpm install

# 5. Start the services
# Terminal 1 - Backend:
cd apps/api && uvicorn src.main:app --reload --port 8000

# Terminal 2 - Frontend:
cd apps/web && pnpm dev
```

</details>

### Development URLs

| Service | URL | Credentials |
|---------|-----|-------------|
| Frontend | http://localhost:3000 | — |
| API Docs | http://localhost:8000/docs | — |
| Grafana | http://localhost:3001 | admin/admin |
| Prometheus | http://localhost:9090 | — |

### Minimal Configuration (.env)

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/lia
REDIS_URL=redis://localhost:6379/0

# Security (REQUIRED - change in production)
SECRET_KEY=change-me-in-production-use-openssl-rand-base64-32
FERNET_KEY=your-fernet-key-here

# LLM Provider (at least one required)
OPENAI_API_KEY=sk-...

# Google OAuth (optional)
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...

# Feature Flags (optional, disabled by default)
MCP_ENABLED=false              # Admin MCP servers
MCP_USER_ENABLED=false         # Per-user MCP (requires MCP_ENABLED)
CHANNELS_ENABLED=false         # Multi-channel messaging (Telegram)
HEARTBEAT_ENABLED=false        # Autonomous proactive notifications
SCHEDULED_ACTIONS_ENABLED=false # Recurring scheduled actions
SUB_AGENTS_ENABLED=false       # Persistent specialized sub-agents
SKILLS_ENABLED=false           # Skills system (agentskills.io standard)
RAG_SPACES_ENABLED=true        # RAG Knowledge Spaces (document upload & retrieval)
FCM_NOTIFICATIONS_ENABLED=false # Firebase push notifications
```

---

## Architecture

### Overview

Production targets include Raspberry Pi (ARM64) via multi-arch Docker builds (`linux/amd64,linux/arm64`).

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Next.js 16 + React 19)                  │
│    Chat UI • Settings • i18n (6 languages) • SSE Streaming • Voice Mode  │
└─────────────────────────────┬───────────────────────────────────────────┘
                              │ HTTP-only cookies (session_id, 24h TTL)
┌─────────────────────────────┴───────────────────────────────────────────┐
│                     BACKEND (FastAPI + LangGraph 1.x)                    │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                 LangGraph Multi-Agent Orchestration                 │ │
│  │                                                                      │ │
│  │   Router → QueryAnalyzer → Planner → ApprovalGate → Orchestrator   │ │
│  │      ↓                                        ↓                     │ │
│  │   ┌─────────────────────────────────────────────────────────────┐  │ │
│  │   │  Contacts │ Emails │ Calendar │ Drive │ Tasks │ Reminders  │  │ │
│  │   │  Places │ Routes │ Weather │ Wikipedia │ Perplexity      │  │ │
│  │   │  Brave │ Web Search │ Web Fetch │ Browser │ Context │ Query│  │ │
│  │   └─────────────────────────────────────────────────────────────┘  │ │
│  │                              ↓                                      │ │
│  │               MCP Tools (per-user external servers)                │ │
│  │                              ↓                                      │ │
│  │                       Response Node (synthesis)                     │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │  Domain Services: Auth, Users, Connectors, RAG, Voice, Skills...    ││
│  └─────────────────────────────────────────────────────────────────────┘│
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │  Infrastructure: Redis (cache) • PostgreSQL (checkpoints) •         ││
│  │  MCP Client Pool • Prometheus (metrics) • Langfuse (traces)       ││
│  └─────────────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────────────┘
```

### Conversation Flow

```mermaid
graph TD
    A[User Message] --> B[Router Node]
    B -->|conversation| C[Response Node]
    B -->|actionable| D[Planner Node]
    D --> E[Semantic Validator]
    E --> F{Approval Gate}
    F -->|approved| G[Task Orchestrator]
    F -->|rejected sub-agents| D
    F -->|rejected| C
    G --> H[Domain Agents + Tools]
    G --> L[Sub-Agent Delegation]
    H --> I[External APIs]
    L --> M[Sub-Agent Pipeline]
    M --> G
    I --> G
    G --> C
    C --> J[SSE Stream]
```

### Code Structure (DDD)

```
apps/api/src/
├── core/                    # Modular configuration (9 modules)
│   ├── config/              # Settings per domain
│   ├── constants.py         # Global constants
│   └── bootstrap.py         # Initialization functions
├── domains/                 # Bounded Contexts (DDD)
│   ├── agents/              # LangGraph nodes, services, tools
│   │   ├── nodes/           # 7 nodes (router, planner, response...)
│   │   ├── services/        # Smart services, HITL
│   │   ├── tools/           # Domain-specific tools
│   │   └── orchestration/   # ExecutionPlan, parallel executor
│   ├── auth/                # JWT, sessions, OAuth
│   ├── connectors/          # Google + Apple + Microsoft clients, provider resolver
│   ├── conversations/       # Conversation CRUD & history
│   ├── google_api/          # Google API pricing & usage tracking
│   ├── rag_spaces/          # RAG Knowledge Spaces (upload, embed, retrieve, system FAQ)
│   ├── user_mcp/            # Per-user MCP servers (CRUD, OAuth, domain routing)
│   ├── voice/               # TTS factory, STT, Wake Word
│   ├── skills/              # Skills system (agentskills.io standard)
│   ├── sub_agents/          # Persistent specialized sub-agents (F6)
│   ├── interests/           # Interest Learning System
│   ├── heartbeat/           # Autonomous Heartbeat (Proactive Notifications)
│   ├── channels/            # Multi-channel messaging (Telegram)
│   ├── reminders/           # Reminder & notification scheduling
│   ├── scheduled_actions/   # Recurring scheduled actions
│   ├── journals/            # Personal Journals (introspective notebooks)
│   └── users/               # User management
└── infrastructure/          # Cross-cutting concerns
    ├── cache/               # Redis sessions, LLM cache
    ├── llm/                 # Factory, providers, embeddings
    ├── mcp/                 # MCP client pool, auth, security, tool adapters
    ├── browser/             # Playwright session pool, CDP accessibility
    ├── rate_limiting/       # Distributed rate limiter
    └── observability/       # Metrics, logging, tracing
```

---

## Technologies

### Backend

| Technology | Version | Role |
|------------|---------|------|
| Python | 3.12+ | Primary runtime |
| FastAPI | 0.135.1 | REST API + SSE framework |
| LangGraph | 1.1.2 | Multi-agent orchestration |
| LangChain | 1.2.12 | LLM abstraction + tools |
| SQLAlchemy | 2.0.48 | Async ORM |
| Alembic | latest | Database migrations |
| PostgreSQL | 16 + pgvector | Database + vector search |
| Redis | 7.3.0 | Cache, sessions, rate limiting |
| Pydantic | 2.12.5 | Validation + serialization |
| structlog | latest | Structured JSON logging |
| sentence-transformers | 5.0+ | Local E5 embeddings |
| Edge TTS | 6.1+ | Voice synthesis (free) |
| mcp | 1.9+ | Model Context Protocol SDK (Streamable HTTP) |
| Docker | 24+ | Containerization (multi-arch amd64/arm64) |

### Frontend

| Technology | Version | Role |
|------------|---------|------|
| Node.js | 22 LTS | JavaScript runtime |
| Next.js | 16.1.7 | React framework |
| React | 19.2.4 | UI library |
| TypeScript | 5.9.3 | Type safety |
| TailwindCSS | 4.2.1 | Styling |
| TanStack Query | 5.90.16 | Server state management |
| react-i18next | 16.5.1 | i18n (6 languages) |
| Radix UI | latest | Accessible UI primitives |

**Responsive Design**: Fully optimized for desktop, tablet, and smartphone. Adaptive layouts, touch-friendly interactions, and mobile-first components ensure a seamless experience on any device.

### Supported LLM Providers

| Provider | Models | Use Case |
|----------|--------|----------|
| OpenAI | GPT-5.2, GPT-5.1, GPT-5, GPT-5-mini/nano, GPT-4.1, GPT-4.1-mini/nano, GPT-4o, o1, o3-mini | Primary (prompt caching, reasoning) |
| Anthropic | Claude Opus 4.6/4.5/4, Claude Sonnet 4.6/4.5/4, Claude Haiku 4.5 | Alternative (extended thinking) |
| Google | Gemini 3.1/3/2.5 Pro, Gemini 3/2.5/2.0 Flash | Multimodal |
| DeepSeek | deepseek-chat (V3), deepseek-reasoner (R1) | Cost-effective reasoning |
| Perplexity | sonar-small/large-128k-online | Web-augmented responses |
| Qwen | qwen3-max, qwen3.5-plus, qwen3.5-flash | Thinking + tools + vision (Alibaba Cloud) |
| Ollama | Any local model (dynamic discovery) | Zero API cost, self-hosted |

### Observability

| Technology | Role |
|------------|------|
| Prometheus | 500+ metrics |
| Grafana | 18 dashboards |
| Loki | Aggregated logs |
| Tempo | Distributed tracing |
| Langfuse | LLM observability |
| structlog | Structured JSON logs |

---

## Documentation

### Main Documentation

| Document | Description |
|----------|-------------|
| [GETTING_STARTED.md](./docs/GETTING_STARTED.md) | Detailed installation guide |
| [ARCHITECTURE.md](./docs/ARCHITECTURE.md) | Complete system architecture |
| [INDEX.md](./docs/INDEX.md) | Full documentation map (190+ docs) |

### Technical Documentation

| Domain | Documents |
|--------|-----------|
| **Agents & LLM** | [GRAPH_AND_AGENTS_ARCHITECTURE](./docs/technical/GRAPH_AND_AGENTS_ARCHITECTURE.md) • [PLANNER](./docs/technical/PLANNER.md) • [SEMANTIC_ROUTER](./docs/technical/SEMANTIC_ROUTER.md) |
| **HITL** | [HITL](./docs/technical/HITL.md) • [PLAN_HITL_STREAMING_VALIDATION](./docs/technical/PLAN_HITL_STREAMING_VALIDATION.md) |
| **Voice** | [VOICE](./docs/technical/VOICE.md) • [VOICE_MODE](./docs/technical/VOICE_MODE.md) |
| **Memory** | [LONG_TERM_MEMORY](./docs/technical/LONG_TERM_MEMORY.md) • [MEMORY_RESOLUTION](./docs/technical/MEMORY_RESOLUTION.md) |
| **MCP** | [MCP_INTEGRATION](./docs/technical/MCP_INTEGRATION.md) • [GUIDE_MCP_INTEGRATION](./docs/guides/GUIDE_MCP_INTEGRATION.md) |
| **Heartbeat** | [HEARTBEAT_AUTONOME](./docs/technical/HEARTBEAT_AUTONOME.md) • [GUIDE_HEARTBEAT](./docs/guides/GUIDE_HEARTBEAT_PROACTIVE_NOTIFICATIONS.md) |
| **Channels** | [CHANNELS_INTEGRATION](./docs/technical/CHANNELS_INTEGRATION.md) • [GUIDE_TELEGRAM](./docs/guides/GUIDE_TELEGRAM_INTEGRATION.md) |
| **Scheduled Actions** | [SCHEDULED_ACTIONS](./docs/technical/SCHEDULED_ACTIONS.md) • [GUIDE_SCHEDULED_ACTIONS](./docs/guides/GUIDE_SCHEDULED_ACTIONS.md) |
| **Skills** | [SKILLS_INTEGRATION](./docs/technical/SKILLS_INTEGRATION.md) |
| **Sub-Agents** | [SUB_AGENTS](./docs/technical/SUB_AGENTS.md) |
| **RAG Spaces** | [GUIDE_RAG_SPACES](./docs/guides/GUIDE_RAG_SPACES.md) • [ADR-055](./docs/architecture/ADR-055-RAG-Spaces-Architecture.md) • [ADR-058](./docs/architecture/ADR-058-System-RAG-Spaces.md) |
| **Browser Control** | [BROWSER_CONTROL](./docs/technical/BROWSER_CONTROL.md) • [ADR-059](./docs/architecture/ADR-059-Browser-Control.md) |
| **Personal Journals** | [JOURNALS](./docs/technical/JOURNALS.md) • [ADR-057](./docs/architecture/ADR-057-Personal-Journals.md) |
| **LLM Providers** | [LLM_PROVIDERS](./docs/technical/LLM_PROVIDERS.md) |
| **CI/CD** | [CI_CD](./docs/technical/CI_CD.md) |
| **Security** | [SECURITY](./docs/technical/SECURITY.md) • [OAUTH](./docs/technical/OAUTH.md) • [RATE_LIMITING](./docs/technical/RATE_LIMITING.md) |
| **Observability** | [OBSERVABILITY_AGENTS](./docs/technical/OBSERVABILITY_AGENTS.md) • [METRICS_REFERENCE](./docs/technical/METRICS_REFERENCE.md) |
| **Cost Tracking** | [LLM_PRICING_MANAGEMENT](./docs/technical/LLM_PRICING_MANAGEMENT.md) • [GOOGLE_API_TRACKING](./docs/technical/GOOGLE_API_TRACKING.md) |

### Practical Guides

| Guide | Description |
|-------|-------------|
| [GUIDE_DEVELOPPEMENT](./docs/guides/GUIDE_DEVELOPPEMENT.md) | Complete development workflow |
| [GUIDE_AGENT_CREATION](./docs/guides/GUIDE_AGENT_CREATION.md) | How to create a new agent |
| [GUIDE_TOOL_CREATION](./docs/guides/GUIDE_TOOL_CREATION.md) | How to create a new tool |
| [GUIDE_TESTING](./docs/guides/GUIDE_TESTING.md) | Testing strategy (2,300+ tests) |
| [GUIDE_DEBUGGING](./docs/guides/GUIDE_DEBUGGING.md) | LangGraph and log debugging |

### Architecture Decision Records (ADR)

59 ADRs documenting major architectural decisions:

- [ADR-007: Service Layer Pattern for Node Complexity](./docs/architecture/ADR-007-Service-Layer-Pattern-For-Node-Complexity.md)
- [ADR-048: Semantic Tool Router](./docs/architecture/ADR-048-Semantic-Tool-Router.md)
- [ADR-051: Reminder & Notification System](./docs/architecture/ADR-051-Reminder-Notification-System.md)
- [View all ADRs](./docs/architecture/ADR_INDEX.md)

---

## Tests

### Running Tests

```bash
cd apps/api

# Unit tests (fast, ~30s)
pytest tests/unit -v

# Integration tests (require PostgreSQL + Redis)
pytest tests/integration -v

# LangGraph agent tests
pytest tests/agents -v

# Full coverage
pytest --cov=src --cov-report=html -v
# Report: htmlcov/index.html
```

### Statistics

| Metric | Value |
|--------|-------|
| Total tests | 2,300+ |
| Reusable fixtures | 170+ |
| Coverage target | 43% |
| CI Workflows | 3 (CI, Security, Release) |

---

## CI/CD

LIA uses a two-layer quality gate: a **local pre-commit hook** (fast, on staged files only) and a **GitHub Actions CI pipeline** (comprehensive, on every push/PR to `main`).

### Pipeline Overview

```
Pre-commit (local)              GitHub Actions CI
===================             ==================
.bak files check                Lint Backend (Ruff + Black + MyPy)
Secrets grep                    Lint Frontend (ESLint + TypeScript)
Ruff + Black + MyPy             Fast unit tests + coverage (43%)
Fast unit tests                 Code Hygiene (i18n, Alembic, .env.example, patterns)
Critical pattern detection      Docker build smoke test
i18n keys sync                  Secret scan (Gitleaks)
Alembic migration conflicts     ──────────────────────
.env.example completeness       Security workflow (weekly)
ESLint + TypeScript check         CodeQL (Python + JS)
                                  Dependency audit (pip-audit + pnpm audit)
                                  Trivy filesystem scan
                                  SBOM generation
```

### Key Practices

| Practice | Implementation |
|----------|---------------|
| **SHA-pinned Actions** | All GitHub Actions pinned by commit SHA (supply-chain security) |
| **Least privilege** | `permissions: contents: read` on CI workflow |
| **Branch protection** | PR required (external contributors), 7 status checks, force push forbidden |
| **Dependabot** | Weekly updates for pip, npm, Docker, Actions — minor/patch grouped |
| **Pre-commit / CI alignment** | CI covers everything the pre-commit does (and more) |
| **Coverage threshold** | 43% minimum enforced in CI |

### Workflows

| Workflow | Trigger | Jobs |
|----------|---------|------|
| **CI** (`ci.yml`) | Push to `main`, PR | 7 jobs: lint, test, code hygiene, docker build, secret scan |
| **Security** (`security.yml`) | PR, weekly schedule, manual | CodeQL, dependency audit, Trivy, SBOM |
| **Release** (`release.yml`) | Tag `v*` | Docker multi-arch build + push (ghcr.io), GitHub Release |

> Full details: [CI/CD Documentation](./docs/technical/CI_CD.md)

---

## Performance

### Key Metrics (P95)

| Metric | Value | SLO |
|--------|-------|-----|
| API Latency | 450ms | < 500ms |
| TTFT (Time To First Token) | 380ms | < 500ms |
| Router Latency | 800ms | < 2s |
| Planner Latency | 2.5s | < 5s |
| E5 Embedding (local) | ~50ms | < 100ms |
| Token Reduction (Windowing) | 93% | > 80% |
| Context Compaction Savings | ~60% per compaction | — |

### Implemented Optimizations

- **Message Windowing**: 5/10/20 turns depending on node
- **Context Compaction**: LLM summarization of old messages (dynamic threshold from response model context window, configurable via `COMPACTION_*` settings)
- **Prompt Caching**: OpenAI/Anthropic (90% discount)
- **Local Embeddings**: Multilingual E5 (zero API cost)
- **Parallel Execution**: asyncio.gather for independent domains
- **Redis O(1)**: Optimized operations (vs O(N) SCAN)
- **Connection Pooling**: httpx persistent connections

---

## Security

### Compliance

| Standard | Status |
|----------|--------|
| GDPR | PII filtering, data minimization |
| OWASP Top 10 | XSS, SQL injection, CSRF protection |
| Prompt Injection | External content wrapping (`<external_content>` safety markers) |
| OAuth 2.1 | Mandatory PKCE |

### Reporting a Vulnerability

**DO NOT create a GitHub Issue for security vulnerabilities.**

Send an email to **liamyassistant@gmail.com** with:
- Description of the vulnerability
- Steps to reproduce
- Potential impact

We respond within 48 hours.

---

## Contributing

We welcome all contributions! See our [Contributing Guide](./CONTRIBUTING.md) to get started.

### Quick Start for Contributors

```bash
# 1. Fork and clone
git clone https://github.com/YOUR-USERNAME/LIA-Assistant.git
cd LIA-Assistant

# 2. Create a branch
git checkout -b feature/my-feature

# 3. Full setup (backend + frontend + git hooks)
task setup

# 4. Develop and test
task test:backend:unit:fast

# 5. Commit (Conventional Commits)
git commit -m "feat(agents): add weather forecast agent"

# 6. Push and create PR
git push origin feature/my-feature
```

### Types of Contributions

- Bug fixes
- New features
- Documentation
- Tests
- i18n translations (6 supported languages)
- Performance optimizations

### Standards

- **Python**: Black + Ruff + MyPy (strict)
- **TypeScript**: ESLint + Prettier
- **Commits**: [Conventional Commits](https://www.conventionalcommits.org/)
- **Coverage**: >= 43% enforced in CI
- **Pre-commit hook**: Installed via `task setup` — runs linters + tests on staged files
- **CI**: All PRs must pass 7 status checks before merge (see [CI/CD](#cicd))

---

## Support

### Getting Help

| Channel | Usage |
|---------|-------|
| [GitHub Issues](https://github.com/jgouviergmail/LIA-Assistant/issues) | Bugs, feature requests |
| [GitHub Discussions](https://github.com/jgouviergmail/LIA-Assistant/discussions) | Questions, ideas |
| liamyassistant@gmail.com | General inquiries |

### Resources

- [Full documentation](./docs/INDEX.md)
- [Practical guides](./docs/guides/)
- [Operational runbooks](./docs/runbooks/)

---

## License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.

See [LICENSE](./LICENSE) for details.

A commercial license is also available for organizations that cannot comply with AGPL-3.0 terms. Contact liamyassistant@gmail.com for details.

---

## Acknowledgments

### Open Source Technologies

This project builds on excellent open source technologies:

**Backend & Infrastructure**
- [Python](https://www.python.org/) - Primary runtime
- [FastAPI](https://fastapi.tiangolo.com/) - Modern async web framework
- [LangGraph](https://github.com/langchain-ai/langgraph) - Multi-agent orchestration
- [LangChain](https://python.langchain.com/) - LLM abstraction & tools
- [SQLAlchemy](https://www.sqlalchemy.org/) - Async ORM
- [Pydantic](https://docs.pydantic.dev/) - Data validation & settings
- [Alembic](https://alembic.sqlalchemy.org/) - Database migrations
- [PostgreSQL](https://www.postgresql.org/) + [pgvector](https://github.com/pgvector/pgvector) - Database & vector search
- [Redis](https://redis.io/) - Cache, sessions, rate limiting
- [sentence-transformers](https://www.sbert.net/) - Local E5 embeddings
- [Edge TTS](https://github.com/rany2/edge-tts) - Free neural voice synthesis
- [structlog](https://www.structlog.org/) - Structured JSON logging
- [Docker](https://www.docker.com/) - Containerization & multi-arch builds

**Frontend**
- [Node.js](https://nodejs.org/) - JavaScript runtime
- [Next.js](https://nextjs.org/) - React framework
- [React](https://react.dev/) - UI library
- [TypeScript](https://www.typescriptlang.org/) - Type safety
- [TailwindCSS](https://tailwindcss.com/) - Utility-first styling
- [Radix UI](https://www.radix-ui.com/) - Accessible UI primitives
- [TanStack Query](https://tanstack.com/query/) - Server state management
- [react-i18next](https://react.i18next.com/) - Internationalization (6 languages)

**Observability**
- [Prometheus](https://prometheus.io/) - Metrics & alerting
- [Grafana](https://grafana.com/) - Dashboards & visualization
- [Loki](https://grafana.com/oss/loki/) - Log aggregation
- [Tempo](https://grafana.com/oss/tempo/) - Distributed tracing
- [Langfuse](https://langfuse.com/) - LLM observability & prompt management

### Inspirations

- [OpenAI Assistants API](https://platform.openai.com/docs/assistants/overview)
- [Anthropic Claude](https://www.anthropic.com/)
- [Model Context Protocol](https://modelcontextprotocol.io/)

---

<p align="center">
  <strong>LIA</strong> — Next-Generation Intelligent Conversational Assistant
</p>

<p align="center">
  Built with ❤️ using Python, Node.js, FastAPI, LangGraph, and Next.js
</p>

<p align="center">
  <a href="#lia">Back to top</a>
</p>
