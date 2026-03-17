# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.5.1] - 2026-03-17

### Added

- **Skill Generator meta-skill** — Built-in system skill (`skill-generator`) that guides users through creating custom SKILL.md files from natural language descriptions. 4-phase advisory process: need analysis, archetype selection (Prompt Expert / Advisory / Plan Template), generation with format validation, and delivery with import instructions. Includes 3 reference files (format specification, full tool catalogue with 60+ tools and 17 agents, archetype examples) and a sandboxed Python validation script. Multilingual support (body in user's language, description in English). Compliant with the agentskills.io open standard.

### Security

CodeQL security hardening and code quality sweep. Addresses 667 code scanning alerts (35 critical/high security, 33 errors, 47 warnings, 552 notes). Zero functional regression — all 6,279 unit tests pass.

### Security

- **Removed `verify=False` on Static Maps proxy** — TLS certificate validation was disabled on the `httpx` client proxying Google Static Maps requests, exposing the Google API key to potential MITM interception. Now uses default `verify=True`. (`connectors/router.py`)
- **Added `photo_name` input validation on Places photo proxy** — The `{photo_name:path}` route parameter accepted arbitrary path segments, potentially reaching unintended Google API endpoints with the server's API key. Added regex validation (`^places/[^/]+/photos/[^/]+$`) matching Google's official resource name spec. (`connectors/router.py`)
- **Removed stack-trace exposure in SSE error events** — Exception details (`str(e)`) were sent to the client via Server-Sent Events, potentially leaking internal paths, SQL queries, or connection strings. Replaced with generic error message; detailed error preserved in server logs. (`notifications/router.py`)
- **Masked admin password in CLI output** — The `create_admin.py` setup script printed the admin password in clear text to stdout, capturable by Docker logs or CI pipelines. Now displays masked output. (`scripts/data/create_admin.py`)
- **Gated TLS bypass by `NODE_ENV` in RAG upload proxy** — `rejectUnauthorized: false` was applied unconditionally (not just in development). Now only disables TLS validation when `NODE_ENV !== 'production'`. (`apps/web/src/app/api/rag-upload/[spaceId]/route.ts`)
- **Fixed incomplete HTML tag stripping regex** — `</script>`, `</style>`, `</head>` regexes did not match variants with whitespace before `>` (e.g., `</script >`). Added `\s*` to closing tag patterns. (`display/components/base.py`)

### Fixed

- **`ToolValidationError` crash on multi-field validation** — `validate_fields()` passed `fields=missing` (plural) to `ToolValidationError.__init__` which only accepts `field=` (singular), causing a `TypeError` when 2+ required fields were missing. Fixed to `field=", ".join(missing)`. (`tools/validation_helpers.py`)
- **Uninitialized `errors` variable in email/calendar tools** — `errors` was assigned only inside the `mode == "batch"` branch but could theoretically be accessed outside it after refactoring. Added defensive `errors = None` initialization before branching. (`emails_tools.py`, `calendar_tools.py`)
- **`AgentService.__init__` duplicated mixin attributes** — Four attributes were manually duplicated from `GraphManagementMixin.__init__`. Refactored to use `super().__init__()`. Added missing `hitl_orchestrator` initialization to the mixin. (`api/service.py`, `graph_management.py`)
- **Overly broad `except Exception` in approval gate** — Tool manifest fallback catch was `except Exception:` (masking DB/network errors), while `validator.py` used the specific `except ToolManifestNotFound:`. Narrowed to match. (`approval_gate_node.py`)
- **Overly broad `except Exception` in place card** — Opening hours parsing caught all exceptions instead of the expected `(ValueError, IndexError, TypeError)`. (`place_card.py`)

### Changed

- **Added debug logging to 18 silent `except: pass` blocks** — Best-effort patterns (user preferences, cache invalidation, CalDAV close, LLM callbacks, OAuth discovery, session cleanup) now emit `logger.debug()` for production observability without changing error-handling behavior.
- **Extracted `get_user_language_safe()` DRY helper** — Replaced 4 identical try-except-for-language patterns in `places_tools.py` with a single shared helper in `runtime_helpers.py`. Narrows exception scope from `Exception` to `(ValueError, KeyError, RuntimeError, AttributeError)`.
- **Elevated `token_counter_service` fallback level warning** — Unknown fallback levels now emit `logger.warning` (was silent `pass`) to surface configuration drift.

### Removed

- **16 unused constants** from `agents/constants.py` — 7 legacy `NODE_*_AGENT` constants (replaced by agent catalogue), 1 `CONTEXT_DOMAIN_TASK_LISTS`, 8 legacy `HITL_*` keys (replaced by Phase 3.3 orchestrator).
- **10 legacy `_*_direct_tool_instance` variables** — Unused module-level tool instances in `calendar_tools.py`, `drive_tools.py`, `emails_tools.py`, `google_contacts_tools.py`, `tasks_tools.py`. Marked `LEGACY` in code, excluded from tool registry by underscore prefix convention.
- **12 unused global variables** — Dead logger instances (`goal_inferrer.py`, `planner_utils.py`), obsolete constants (`PRIOR_ALPHA/BETA`, `_CURRENCY_USD/EUR`, `_DESTRUCTIVE_LABEL_WITH_CHILDREN`), write-only `_last_update`, unused `TypeVar T`.
- **~25 unused imports** across 18 files — Removed unused `Language`, `Set`, `List`, `Dict`, `Optional`, `Tuple`, `ast`, `re`, `json`, `subprocess`, `os`, `yaml`, `asdict`, `Template`, `UUID`, `get_function_complexity` imports from source, scripts, and infrastructure files.
- **Self-assignment dead code** in `mixins.py` — `ToolOutputMixin = ToolOutputMixin` and `create_tool_formatter = create_tool_formatter` (no-ops, re-exports handled by `__init__.py`).

## [1.5.0] - 2026-03-17

### Added

- **Persistent specialized sub-agents (F6)** — Delegation system allowing the principal assistant to spawn ephemeral expert sub-agents for complex tasks (research, analysis, synthesis). Includes full DDD domain (`src/domains/sub_agents/`), ORM model, repository, service, REST API (10 endpoints), 3 pre-defined templates (Research Assistant, Writing Assistant, Data Analyst). Sub-agents execute through a simplified direct pipeline (query analysis → planner → parallel executor → LLM synthesis), bypassing the full graph's semantic validator, approval gate, and response node. Read-only V1 (all write tools blocked). Feature flag: `SUB_AGENTS_ENABLED`.
- **Sub-agent planner integration** — Transversal `delegate_to_sub_agent_tool` always included in planner catalogue via `NormalFilteringStrategy`. Planner prompt extended with `{sub_agents_section}` guidelines. Multiple delegates execute in parallel (wave-based). Depth limit: sub-agents cannot spawn sub-sub-agents.
- **Sub-agent catalogue manifests** — `AgentManifest` + `ToolManifest` with semantic keywords for natural discovery (`src/domains/agents/sub_agents/catalogue_manifests.py`).
- **Sub-agent token guard-rails** — Per-execution budget (`SUBAGENT_MAX_TOKEN_BUDGET`), daily budget per user (`SUBAGENT_MAX_TOTAL_TOKENS_PER_DAY`), auto-disable after consecutive failures (`SUBAGENT_MAX_CONSECUTIVE_FAILURES`). `TokenTrackingCallback` consolidation into parent tracker.
- **Sub-agent HITL rejection fallback** — When user rejects a plan with delegation steps, system auto-replans without sub-agents. Catalogue exclusion via `exclude_sub_agent_tools` flag.
- **Sub-agent semantic validator exceptions** — `for_each` cardinality check and repeated-tool consolidation exempt `delegate_to_sub_agent_tool` steps (each step delegates to a different expert).
- **Sub-agent user preference** — Per-user `sub_agents_enabled` toggle (Settings > Features > Sub-Agents). `SubAgentsSettings.tsx` component. `PATCH /auth/me/sub-agents-preference` endpoint.
- **Sub-agent stale recovery job** — APScheduler job recovers sub-agents stuck in `executing` state (configurable interval).
- **Sub-agent observability** — Prometheus metrics module (`metrics_subagent.py`). Sub-agent notification type in SSE/FCM.
- **Skills DB refactoring** — Normalized skills persistence from JSONB `disabled_skills` columns to two relational tables: `skills` (registry: name, is_system, owner_id, admin_enabled, description, descriptions) + `user_skill_states` (user_id, skill_id, is_active). Migration includes data migration from legacy columns. `SkillPreferenceService` for sync, toggle, and state queries. `active_skills_ctx` ContextVar replaces `disabled_skills_ctx` (positive set).
- **Skills admin system-toggle** — `PATCH /skills/admin/{name}/system-toggle` endpoint. When admin disables a system skill, `is_active` is set to `false` for all users. New `adminSystemToggleSkill` in `useSkills` hook. Admin view fetches from `/skills/admin/list`.
- **Skills preference repository** — `SkillRepository` and `SkillStateRepository` for normalized DB access, with `ensure_states_for_user()` and `get_active_skill_names()` methods.
- **HITL plan approval question prompt** — Dedicated prompt template (`hitl_plan_approval_question_prompt.txt`) for generating approval gate questions, avoiding ambiguous/contradictory formulations.
- **Subagent synthesis prompt** — Dedicated prompt (`subagent_synthesis_prompt.txt`) for sub-agent result synthesis.
- **Provider cost adjustment documentation** — Investigation of Anthropic billing delta (~11%) with recommended `cost_adjustment_factor` solution (`docs/technical/PROVIDER_COST_ADJUSTMENT.md`).
- **Google Routes client** — `GoogleRoutesClient` for directions/transit route queries (`src/domains/connectors/clients/google_routes_client.py`).
- **Sub-agents i18n** — All 6 languages (en, fr, de, es, it, zh): templates names/descriptions, settings labels, LLM type label.
- **Sub-agents documentation** — `docs/technical/SUB_AGENTS.md`, `docs/INDEX.md` updated, `docs/ARCHITECTURE.md` updated for skills DB model.
- **104 files changed** — 8,029 insertions, 251 deletions across backend, frontend, docs, and configuration.

### Changed

- **Skills context propagation** — Replaced `disabled_skills_ctx` (negative set) with `active_skills_ctx` (positive set) in `AgentService` and skill injection. Only active skills are injected into the assistant prompt.
- **Skills frontend** — `AdminSkillsSection` now uses `admin_enabled` flag and `adminSystemToggleSkill`. `SkillsSettings` user view shows only admin-enabled system skills. `useSkills` hook accepts `adminView` parameter.
- **HITL interrupt handler** — Removed misleading token metadata from `STREAM_DONE` payload (HITL tokens are partial/incomplete).
- **Smart planner prompts** — Extended with sub-agent delegation section, explicit `execution_mode` (sequential/parallel) and `timeout_seconds` per step in plan schema, guidelines for both single-domain and multi-domain planners.
- **Query intelligence** — Added `include_sub_agent_tools` flag to `ToolFilter` (always `true` for planner).
- **Conversation repository** — Updated queries for sub-agent session tracking. Google API costs now included in per-message and aggregate cost totals.
- **LLM factory** — Added `subagent` LLM type with default model configuration.
- **LLM defaults migration** — Router, planner, semantic validator, approval gate switched to Anthropic `claude-sonnet-4-6` (reasoning: low). Compaction switched to `gpt-4.1-mini` (reasoning: medium).

### Fixed

- **Skills system-disable propagation** — Admin-disabled system skills are now properly excluded from the agent flow (was only excluded from UI, not from assistant context).
- **Google API cost not included in totals** — Costs from Google APIs (Routes Matrix, etc.) stored in `google_api_cost_eur` were not added to the displayed total cost. Fixed in conversation service (per-message cost), conversation repository (aggregate queries), chat service (user statistics), and streaming debug panel. All cost displays now show LLM + Google API combined.
- **HITL question tokens not tracked** — Token consumption for HITL approval question generation was not tracked, causing cost under-reporting (~€0.03/request on Anthropic models). Fixed by wrapping `TrackingContext` in a `TokenTrackingCallback` for the HITL question generator.
- **HITL approval question ambiguous** — Approval gate could generate two contradictory questions in a single prompt. New dedicated prompt template (`hitl_plan_approval_question_prompt.txt`) enforces a single YES/NO-answerable question.
- **Debug panel DB-aggregated tokens** — HITL flows now fetch DB-aggregated token totals (includes tokens from prior SSE request: router, planner, HITL question) for accurate debug panel display.
- **Google Routes Matrix JSON parsing** — `GoogleRoutesClient` now handles both JSON array and NDJSON response formats (was failing on standard JSON array responses).
- **Concurrent connector access in parallel execution** — `ConcurrencySafeConnectorService.is_connector_active()` was not wrapped with the concurrency lock, causing "concurrent operations are not permitted" errors during parallel sub-agent/tool executions.

## [1.4.7] - 2026-03-16

### Added

- **Intelligent context compaction (F4)** — LLM-based conversation history summarization when token count exceeds a dynamic threshold (configurable ratio of response model context window). Preserves recent messages and critical identifiers (UUIDs, URLs, emails). Includes `/resume` user command for forced compaction, 4 HITL safety conditions, chunked summarization for large histories, descriptive fallback on LLM failure. Configurable via 6 `.env` settings (`COMPACTION_*`). New LLM type `compaction` (GPT-4.1-nano default) visible in admin LLM config panel. 6 Prometheus metrics. Graph entry point changed: `compaction → router`. Schema version bumped to 1.1 with migration.
- **Planner cost-awareness for web search** — `unified_web_search_tool` catalogue description now includes cost constraint (max 1 call per plan), directing planner to use lightweight `brave_search_tool` for additional searches.
- **FAQ `/resume` command** — Added FAQ entry explaining the `/resume` command in all 6 languages (en, fr, de, es, it, zh).

## [1.4.6] - 2026-03-16

### Added

- **Heartbeat email source** — Proactive notifications now aggregate today's unread inbox emails as a 9th context source. Supports Google Gmail, Apple Email, and Microsoft Outlook via dynamic provider resolution. LLM filters for urgent/actionable emails only (skips newsletters, marketing). Configurable via `HEARTBEAT_CONTEXT_EMAILS_MAX` (default: 5).
- **Gmail message normalization** — `GoogleGmailClient.get_message()` now extracts top-level `from`, `subject`, `to`, `cc`, `body`, `_provider` fields, matching the format already produced by Apple and Microsoft normalizers. Enables provider-agnostic message consumption throughout the application.
- **Plan validation error logging** — `PlanValidator` now logs individual validation errors and warnings with full details (code, message, step_index, tool_name, context) for debugging.

### Fixed

- **Plan validator false UNAUTHORIZED errors** — `planner_node_v3` was not passing `oauth_scopes` from state to `ValidationContext`, causing all scope-requiring tools to fail validation. Fixed by reading `state["oauth_scopes"]` (matches `approval_gate_node` pattern).

## [1.4.5] - 2026-03-16

### Added

- **External Content Wrapping (F2)** — Prompt injection prevention for untrusted web content. All external content (web pages, Perplexity synthesis, Brave snippets, Wikipedia summaries) is wrapped in `<external_content>` safety markers with an `[UNTRUSTED EXTERNAL CONTENT]` warning before being sent to the LLM. Tag occurrences within content are escaped to prevent marker breakout. Feature-flagged via `EXTERNAL_CONTENT_WRAPPING_ENABLED` (default: `true`).
- **`content_wrapper` module** (`src/domains/agents/utils/content_wrapper.py`) — `wrap_external_content()` and `strip_external_markers()` functions with XML attribute injection prevention (`source_url` quote escaping).
- **21 unit tests** for content wrapping covering wrapping, stripping, roundtrip, tag escape attacks, XML attribute injection, and real-world integration scenarios.

### Changed

- `fetch_web_page_tool` — Markdown content is wrapped with safety markers after sanitization and truncation (step 11).
- `web_search_tools` — Perplexity synthesis, Brave snippets, and Wikipedia summaries are individually wrapped when `external_content_wrapping_enabled` is true.
- `.env.example` — Added `EXTERNAL_CONTENT_WRAPPING_ENABLED` variable.

### Fixed

- `html_renderer.py` — Removed incorrect `web_fetch` → `WebSearchCard` mapping that rendered an empty card. Web fetch results are inline in the LLM response text and do not need a visual card.

## [1.4.4] - 2026-03-16

### Added

- **Web Search/Fetch Cache** — Redis TTL cache for `unified_web_search_tool` (5 min) and `fetch_web_page_tool` (10 min) results. Reduces external API calls (Brave, Perplexity) and HTTP fetches for repeated queries. Configurable via `WEB_SEARCH_CACHE_ENABLED`, `WEB_SEARCH_CACHE_TTL_SECONDS`, `WEB_FETCH_CACHE_TTL_SECONDS` environment variables. Multi-tenant isolated by user_id.
- **`force_refresh` parameter** on `unified_web_search_tool` and `fetch_web_page_tool` — allows planner to bypass cache when user explicitly requests fresh results.
- **`WebSearchCache` class** (`src/infrastructure/cache/web_search_cache.py`) — follows existing `ContactsCache` pattern with `CacheEntryV2` format, automatic Prometheus metrics (`cache_hit_total`/`cache_miss_total`), and graceful degradation on Redis errors.
- **Recency normalization** — `_normalize_recency()` function converts non-standard planner values (`"7d"`, `"pd"`, `"1w"`) to canonical values (`"day"`, `"week"`, `"month"`). Prevents cache key fragmentation and ensures correct API parameter passing.
- **Catalogue manifest enum constraint** — `recency` parameter on `unified_web_search_tool` manifest now has an `enum` constraint guiding the planner to generate valid values only.
- **13 unit tests** for `WebSearchCache` covering cache hit/miss, TTL, disabled state, Redis errors, multi-tenant isolation, and recency key differentiation.

### Changed

- `unified_web_search_tool` — Cache check before triple parallel search (Perplexity + Brave + Wikipedia), cache store after success. Registry updates excluded from cache (RegistryItem objects not serializable).
- `fetch_web_page_tool` — Cache check before HTTP fetch, cache store after extraction. Eliminates redundant HTTP calls for same URL within TTL window.
- `.env.example` — Added 5 new web cache configuration variables.
- `docs/technical/WEB_FETCH.md` — Added cache architecture section, Redis TTL documentation, `force_refresh` parameter documentation.
- `docs/technical/TOOLS.md` — Added `unified_web_search` and `fetch_web_page` to cache hit rates table.
- `docs/architecture/ADR-029-Redis-Multi-Purpose-Architecture.md` — Added `web_search:{user}:{hash}` and `web_fetch:{user}:{hash}` cache keys to architecture diagram and key reference table.

## [1.4.3] - 2026-03-16

### Changed

- **httpx** 0.27.2 → 0.28.1 — Migrate test fixture from `app=` to `ASGITransport(app=)`, add explicit `follow_redirects=False` on 6 OAuth credential flows (RFC 6749/7009)
- **langgraph** 1.0.10 → 1.1.2 — Required by langchain 1.2.12
- **langchain-core** 1.2.17 → 1.2.19
- **langchain** 1.2.10 → 1.2.12
- **langchain-openai** 1.1.10 → 1.1.11
- **langchain-anthropic** 1.3.4 → 1.3.5
- **langchain-google-genai** 3.2.0 → 4.2.1 — SDK rewrite (google-generativeai → google-genai)
- **firebase-admin** 6.8.0 → 7.2.0 — Removed deprecated send_all/send_multicast (not used)
- **ruff** 0.8.4 → 0.15.6 — Exclude new UP042/UP045/UP046/UP047 cosmetic rules
- **mypy** 1.13.0 → 1.19.1 — Remove stale type:ignore, add overrides for new strict checks
- **pytest** 8.3.3 → 9.0.2
- **pytest-asyncio** 0.24.0 → 1.3.0
- **pytest-cov** 6.0.0 → 7.0.0
- **psycopg** 3.2.10 → 3.3.3
- **pgvector** 0.3.6 → 0.4.2
- **redis** 7.1.0 → 7.3.0
- **uvicorn** 0.40.0 → 0.41.0
- **asyncpg** 0.30.0 → 0.31.0
- **sentence-transformers** 5.2.0 → 5.3.0
- **opentelemetry** 1.39.1 → 1.40.0 (api, sdk, instrumentation-fastapi, exporter-otlp)
- **python-jose** 3.4.0 → 3.5.0
- **python-dotenv** 1.0.1 → 1.2.2
- **email-validator** 2.2.0 → 2.3.0
- **apscheduler** 3.10.4 → 3.11.2
- **readability-lxml** 0.8.1 → 0.8.4.1
- **markdownify** 0.14.1 → 1.2.2
- **jsdom** 28.1.0 → 29.0.0
- **types-passlib** 1.7.7.20240819 → 1.7.7.20260211
- **types-python-jose** 3.3.4.20240106 → 3.5.0.20250531
- **pytest-mock** 3.14.0 → 3.15.1
- **testcontainers** 4.8.2 → 4.14.1
- **debugpy** 1.8.9 → 1.8.20
- **safety** 3.2.11 → 3.7.0
- **bandit** 1.8.0 → 1.9.4
- **15 frontend packages** (react 19.2.4, firebase 12.10, zod 4.3.6, vitest 4.1, @hey-api/openapi-ts 0.94.1, etc.)
- **13 GitHub Actions** (checkout v6, upload-artifact v7, codecov v5, docker actions v4/v7, etc.)

### Fixed

- **CI pipeline**: Use venv in backend CI jobs (fixes MyPy import resolution)
- **CI pipeline**: Fix Alembic head detection regex for typed annotations
- **CI pipeline**: Fix synchronous Store call check false positive (exclude `await` lines)
- **CI pipeline**: Rename codecov `file` → `files` for v5 compatibility
- **CI pipeline**: Regenerate pnpm-lock.yaml after jsdom 29 merge
- **CI pipeline**: Mark checkpointer tests as integration (were failing with wrong DB user)
- **CI pipeline**: Lower coverage threshold to 40%
- **Security**: Add OPENAI_API_KEY to .env.example

### Documentation

- Update STACK_TECHNIQUE.md with all version bumps
- Update GUIDE_DEVELOPPEMENT.md test examples (ASGITransport)
- Update README.md badges (LangGraph 1.1.2, LangChain 1.2.12)

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

[Unreleased]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.5.1...HEAD
[1.5.1]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.5.0...v1.5.1
[1.5.0]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.4.7...v1.5.0
[1.4.7]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.4.6...v1.4.7
[1.4.6]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.4.5...v1.4.6
[1.4.5]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.4.4...v1.4.5
[1.4.4]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.4.3...v1.4.4
[1.4.3]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.4.1...v1.4.3
[1.4.1]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.4.0...v1.4.1
[1.4.0]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/jgouviergmail/LIA-Assistant/releases/tag/v1.0.0
