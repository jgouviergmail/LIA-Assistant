# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.4.1] - 2026-03-15

### Fixed

- **Heartbeat timezone conversion**: Proactive calendar notifications now display event times in the user's local timezone instead of raw ISO/UTC strings. Fixes notifications reporting events 1 hour early (LLM misinterpreting UTC as local time)
  - Multi-provider support: Google (offset in ISO), Microsoft (naive + timeZone field), Apple CalDAV (naive local times)
  - Naive datetimes (no offset, no timeZone) now default to user timezone instead of UTC, fixing a 1-hour-late display for CalDAV events
  - Task due dates cleaned to date-only format (prevents misleading midnight-UTC timezone shifts)
  - Recent heartbeat/interest notification timestamps converted to user timezone
  - Prompt header now includes "(times in user's local timezone)" for LLM clarity
  - DRY refactor: `_resolve_user_tz()` replaces 3 duplicated timezone fallback blocks
- **Interest notification 0 tokens / 0€**: Token tracking now correctly accumulates tokens from both LLM phases (content generation + presentation formatting). Previously only the presentation phase was counted, and generation phase tokens (LLM reflection) were lost
  - Added `tokens_in`/`tokens_out` fields to `ContentResult` dataclass
  - `LLMReflectionContentSource` now returns tokens in `ContentResult` (in addition to persisting via TrackingContext)
  - `_extract_llm_tokens()` helper with `response_metadata` fallback for non-standard providers
- **Interest presentation LLM provider mismatch**: `LLMAgentConfig` was created without `provider` parameter, defaulting to `"openai"` while model was `claude-sonnet-4-6` (Anthropic) — causing silent 404 errors and raw unformatted content as fallback

### Added

- **CI/CD hardening for public repo**: Comprehensive pipeline overhaul for open-source best practices
  - **Branch protection on `main`**: PR required with 1 review (external contributors), 7 required status checks, force push forbidden, stale review dismissal, conversation resolution required. Admins can bypass for direct pushes
  - **SHA-pinned GitHub Actions**: All actions across 3 workflows (`ci.yml`, `security.yml`, `release.yml`) pinned by commit SHA with version comments — prevents supply-chain attacks via tag mutation
  - **`permissions: contents: read`** on CI workflow (least privilege principle)
  - **Code Hygiene CI job**: New job with 6 checks — `.bak` files, sync Store calls, Redis setex without `json.dumps`, i18n keys sync (EN vs 5 languages), Alembic migration conflicts (revision chain parsing), `.env.example` completeness
  - **Docker build smoke test CI job**: Builds API and Web production images without pushing (catches broken Dockerfiles), with GHA cache
  - **Pre-commit hook aligned with CI**: Added i18n keys sync, Alembic migration conflict detection (date prefix), `.env.example` completeness checks to local pre-commit hook
  - **Repo settings**: `delete_branch_on_merge`, `allow_update_branch`, `allow_auto_merge` enabled; homepage URL set
  - **Dependabot groups**: Minor/patch updates grouped per ecosystem (pip, npm) to reduce PR noise; GitHub Actions updates grouped
  - **`.editorconfig`**: New file enforcing consistent formatting across IDEs (indent 4 for Python, indent 2 for TS/JS/JSON, LF line endings, CRLF for Windows scripts)
  - **GitHub labels**: Added `security`, `ci`, `docker`, `python`, `frontend`, `agents`, `priority:high`, `priority:low`
  - **CI tests aligned with pre-commit**: Fast unit tests only (excluding slow/integration/e2e/benchmark markers + 10 ignored files), coverage threshold 75%
  - **CI/CD documentation**: New `docs/technical/CI_CD.md` with full pipeline architecture, check matrix, troubleshooting
- **`extract_llm_tokens()` centralized helper**: New `src/infrastructure/llm/token_utils.py` — single reusable function for extracting token usage from LangChain AIMessage across all providers (DRY refactor from 2 duplicated implementations)

### Changed

- Updated heartbeat context source tables in docs to reflect multi-provider support (Google/Apple/Microsoft Calendar, Google Tasks/Microsoft To Do)
- Ruff and Black now lint `tests/` in addition to `src/` (aligned with pre-commit hook)
- Interest LLM reflection prompt: heading level fix (`##` → `###`), free-form format with paragraphs instead of strict sentence limits

### Fixed

- **i18n desync**: 3 keys missing in fr/de/es/it/zh (`chat.voice_mode.processing`, `speaking`, `error_permission`), 87 keys missing in en/fr (`settings.interests.*` section). All 6 languages now have 2,587 keys in perfect sync
- **Mixed language in docs**: French documentation files (`GUIDE_HEARTBEAT_PROACTIVE_NOTIFICATIONS.md`, `INTERESTS.md`) contained English sentences — translated to French

## [1.4.0] - 2026-03-14

### Added

- **RAG Knowledge Spaces**: Users can create personal knowledge spaces containing their own documents (PDF, TXT, MD, DOCX) to enrich AI assistant responses
  - **Space management**: Create, edit, delete, and toggle activation of knowledge spaces per user
  - **Document processing pipeline**: Background processing with text extraction, chunking (RecursiveCharacterTextSplitter), and embedding (OpenAI `text-embedding-3-small` via TrackedOpenAIEmbeddings)
  - **Hybrid search retrieval**: Semantic similarity (pgvector cosine) + BM25 keyword matching with configurable alpha fusion
  - **Response Node injection**: RAG context automatically injected into assistant responses when active spaces exist
  - **Full cost transparency**: Embedding costs tracked per document (indexing) and per query (retrieval) in TokenUsageLog, MessageTokenSummary, and UserStatistics
  - **Admin reindexation**: Endpoint to reindex all documents after embedding model change, with Redis flag to disable RAG during migration and automatic vector dimension ALTER
  - **14 Prometheus metrics**: Document processing RED, retrieval performance, space lifecycle Gauges, reindex tracking
  - **Grafana dashboard**: Dedicated RAG Spaces dashboard (18th) with 21 panels
  - **Full frontend**: Space list, detail, document upload (drag & drop + progress), processing status polling, activation toggle, active spaces indicator in chat, settings section
  - **i18n**: Full translation support in 6 languages (en, fr, de, es, it, zh)
  - **Feature flag**: `RAG_SPACES_ENABLED=true` to enable (default: true)

## [1.3.0] - 2026-03-14

### Changed

- **FastAPI 0.128.0 → 0.135.1**: Major framework upgrade pulling Starlette 0.50.0
- **Removed Starlette UTF-8 patch**: Starlette 0.50 natively defaults to `encoding="utf-8"` in Config, making the `patch_starlette_utf8()` monkey-patch obsolete
- **SSE ClientDisconnect handling**: Added graceful catch for `starlette.requests.ClientDisconnect` (raised since Starlette 0.42) — client disconnections during streaming are now logged as info instead of errors

### Fixed

- **SSE CancelledError log level**: Client disconnections during streaming are now logged as `info` instead of `error` in orchestration and streaming services — prevents false error alerts and inflated error metrics
- **DB connection leak on client disconnect**: `session.close()` in `get_db_session()`/`get_db_context()` and `tracker.commit()` in the graph streaming finally block are now shielded with `asyncio.shield()`, preventing SQLAlchemy connection pool exhaustion when clients disconnect mid-stream
- **Stale tests**: Fixed 8 pre-existing test failures in semantic validation and routing modules (obsolete feature flag test, incorrect planner_iteration assertions, incomplete mock settings)

## [1.2.0] - 2026-03-14

### Changed

- **Node.js 20 → 22 LTS**: Upgraded Docker images, CI workflows, and engine requirements to Node.js 22 LTS (supported until April 2027)
- Closed Dependabot PR #4 (Node 25 — not LTS) and PR #6 (Python 3.14 — still in beta)

## [1.1.0] - 2026-03-14

### Added

- **LAN Access & SSL Configuration**: Configurable `SSL_DOMAIN` env var for self-signed certificates covering nip.io domains, enabling LAN access from mobile/other devices
- **SSL cert sharing**: Web container now uses ssl-init certificates via `--experimental-https-key`/`--experimental-https-cert`, ensuring consistent certs across API and Web
- **Documentation**: Added section 4.4 "LAN Access & SSL Configuration" in Getting Started guide

### Fixed

- **Token tracking upsert**: Replaced two-step UPDATE-then-INSERT with PostgreSQL native `INSERT ... ON CONFLICT DO UPDATE` for atomic, race-condition-free token summary persistence
- **Tracking resilience**: Token tracking failures no longer break the chat flow (graceful error handling in `TrackingContext.commit()`)
- **WebSocket HMR refresh loops**: Fixed `NEXT_PUBLIC_ALLOWED_DEV_ORIGINS` format — must be hostname only (e.g., `192.168.1.100.nip.io`), not full URL with protocol/port
- **SSL key permissions**: Changed key.pem to 644 so non-root containers (Next.js `node` user) can read it

### Changed

- `.env.example` is now a development template (was production), `.env.prod.example` remains the production template
- `generate-certs.sh` is fully configurable via `SSL_DOMAIN` and `SSL_IP` env vars (no hardcoded IP)
- Frontend dependencies updated: Next.js 16.1.6, i18next 25.8.18, lucide-react 0.577.0, tailwindcss 4.2.1

## [1.0.0] - 2026-03-13

First public open-source release of LIA.

### Features

- **Multi-Agent Orchestration**: LangGraph-based pipeline with Router, Planner, Orchestrator, and Response nodes
- **16+ Domain Agents**: Contacts, Email, Calendar, Drive, Tasks, Weather, Wikipedia, Perplexity, Brave Search, Web Search, Web Fetch, Places, Routes, Reminders, Context, Query, and dynamic MCP agents
- **Human-in-the-Loop (HITL)**: 6 interaction types — Plan Approval, Clarification, Draft Critique, Destructive Confirm, FOR_EACH Confirm, Modifier Review
- **Smart Planner**: LLM-based execution plan generation with dependency graphs and wave-by-wave parallel execution
- **Plan Pattern Learner**: Redis-based Bayesian learning; high-confidence patterns (>=90%) bypass semantic validation
- **Model Context Protocol (MCP)**: Admin MCP (persistent) + Per-User MCP (ephemeral) with OAuth flow support
- **MCP Apps**: Interactive HTML widgets in sandboxed iframes via PostMessage JSON-RPC bridge
- **Excalidraw Integration**: LLM-driven diagram builder with intent-based element generation
- **Skills System**: agentskills.io standard SKILL.md files with per-user toggle and deterministic bypass strategies
- **Multi-Channel Messaging**: Generic abstraction with Telegram as first implementation (webhook, OTP binding, voice)
- **Autonomous Heartbeat**: LLM-driven proactive notifications with two-phase approach (decision + personality-aware rewrite)
- **Voice Mode**: TTS (Edge/OpenAI/Gemini) + STT (Sherpa-onnx Whisper, CPU-only)
- **Multi-Provider LLM**: 6 providers (OpenAI, Anthropic, Gemini, DeepSeek, Perplexity, Ollama) with dynamic config via Admin UI
- **Multi-Provider Connectors**: Google, Apple iCloud, and Microsoft 365 with mutual exclusivity per functional category
- **Scheduled Actions**: User-scheduled deferred task execution
- **Session-based Auth (BFF)**: HTTP-only cookies in Redis, no JWT exposed to frontend
- **Enterprise Observability**: OpenTelemetry traces, Prometheus metrics, Grafana dashboards, Langfuse LLM analytics
- **Internationalization**: 6 languages (fr, en, es, de, it, zh)
- **Multi-arch Docker**: `linux/amd64` + `linux/arm64` builds for Raspberry Pi deployment
- **Comprehensive Test Suite**: 2,300+ tests (unit, integration, e2e, benchmark)

### Infrastructure

- FastAPI 0.128 backend (Python 3.12+) with async SQLAlchemy 2.0 + asyncpg
- Next.js 16 frontend (React 19, TypeScript) with TailwindCSS 4
- PostgreSQL 16 (+ pgvector) for data and vector search
- Redis 7 for sessions, cache, distributed locks, and pattern learning
- APScheduler for 9 background jobs
- Circuit breaker, rate limiting, and distributed locks
- SOPS/Age encryption for secrets management

[Unreleased]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.4.0...HEAD
[1.4.0]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/jgouviergmail/LIA-Assistant/releases/tag/v1.0.0
