# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
Always check the available plugins/skills at session start and use the ones relevant to the current task.

Scoped guidance: `apps/web/CLAUDE.md` (frontend conventions) applies on top of this file when working under `apps/web/`; `infrastructure/claude-cli/CLAUDE.server.md` is the system prompt of the in-container DevOps CLI (not coding guidance).

## Project Overview

LIA is a multi-agent conversational AI assistant built with **FastAPI** (backend), **Next.js 16** (frontend), and **LangGraph 1.0** (agent orchestration). It integrates Google/Apple/Microsoft APIs, supports HITL (Human-in-the-Loop) approval flows, and features enterprise observability (Prometheus, Grafana, Langfuse).

## Build & Development Commands

This project uses [Task](https://taskfile.dev/) as its build tool. All commands are defined in `Taskfile.yml`.

```bash
# Full setup (backend + frontend + git hooks)
task setup

# Start dev environment (Docker Compose: API + Web + PostgreSQL + Redis + observability)
task dev                    # foreground
task dev:detach             # background

# Run services individually (requires PostgreSQL + Redis already running)
task dev:api                # Backend on :8000
task dev:web                # Frontend on :3000

# Stop
task stop
```

### Backend Testing (from apps/api/)

```bash
task test:backend:unit:fast        # Fast unit tests (pre-commit, excludes integration)
task test:backend:unit             # All unit tests
task test:backend:integration      # Integration tests (requires PostgreSQL + Redis)
task test:backend:agents           # Agent-specific tests
task test:backend:exhaustive       # Full suite with coverage (do not use, too long)

# Run a single test file
cd apps/api && .venv/Scripts/pytest tests/unit/path/to/test_file.py -v

# Run a single test by name
cd apps/api && .venv/Scripts/pytest tests/ -k "test_name" -v
```

### Frontend Testing (from apps/web/)

```bash
task test:frontend          # vitest run
cd apps/web && pnpm test    # equivalent
```

### Linting & Formatting

```bash
task lint                   # All linters (backend + frontend)
task format                 # Auto-format all code

# Backend: Black (formatter) + Ruff (linter) + MyPy (type checker)
task lint:backend
task format:backend

# Frontend: ESLint + Prettier + TypeScript check
task lint:frontend
task format:frontend
```

### CI & Pre-commit

```bash
task pre-commit             # format + lint + fast unit tests (run before committing)
task ci                     # Full CI pipeline: lint + test + security scan
```

Git hooks are installed via `task setup:hooks` and live in `.github/hooks/` (configured via `git config core.hooksPath`).

### Database

```bash
task db:migrate                          # Run migrations (alembic upgrade head)
task db:migrate:create -- "description"  # Create new migration
task db:migrate:down                     # Rollback last migration
task db:seed                             # Seed dev data
task db:seed:sql                         # Apply SQL seeds (personalities, pricing)
task db:reset                            # Drop all + migrate + seed
task db:create-admin                     # Create admin user for first-time setup
```

## Architecture

### Monorepo Structure

- `apps/api/` — Python 3.12+ FastAPI backend (source in `src/`, tests in `tests/`)
- `apps/web/` — Next.js 16 + React 19 + TypeScript frontend
- `infrastructure/` — Docker, database seeds, observability config (Prometheus, Grafana)
- `docs/` — 280+ documentation files, ADRs, guides, runbooks
- `scripts/` — Deployment, analysis, and utility scripts

### Backend Architecture (DDD)

The backend follows Domain-Driven Design. Entry point: `apps/api/src/main.py`.

- `src/core/config/` — Modular settings composed via multiple inheritance into a single `Settings` class. Access via `from src.core.config import settings`. Each domain module (agents, llm, database, security, etc.) is a separate Pydantic `BaseSettings` subclass.
- `src/core/constants.py` — Global constants and default values used by config modules.
- `src/domains/agents/` — The main domain. Contains the LangGraph graph, nodes, tools, services, and orchestration.
- `src/domains/` — Other bounded contexts: `auth/`, `connectors/`, `voice/`, `interests/`, `heartbeat/`, `user_mcp/`, `users/`, `conversations/`, `reminders/`, etc.
- `src/infrastructure/` — Cross-cutting: Redis cache, LLM factory/providers, MCP client pool, rate limiting, observability.
- `src/api/v1/routes.py` — FastAPI route definitions.

### LangGraph Agent Flow

Two execution modes are user-toggleable in the chat header (ADR-070):

**Pipeline mode** (default — economical, deterministic, ~4-8× fewer tokens than ReAct):

```
User Message → Router Node → (conversation → Response)
                           → (actionable → Planner → Semantic Validator → Approval Gate → Task Orchestrator → Domain Agents → Response)
```

**ReAct mode** (autonomous, iterative — for exploratory or ambiguous queries):

```
User Message → Router Node → (react mode → ReAct Setup → ReAct Call Model ↔ ReAct Execute Tools → ReAct Finalize → Response)
```

Both modes converge on the same Response Node and stream via SSE. The `react_agent` LLM type in `LLM_TYPES_REGISTRY` is dedicated to the ReAct loop.

Key files:
- `src/domains/agents/nodes/routing.py` — Conditional routing functions between nodes
- `src/domains/agents/nodes/planner_node_v3.py` — Plan generation (ExecutionPlan DSL)
- `src/domains/agents/nodes/task_orchestrator_node.py` — Parallel task execution
- `src/domains/agents/nodes/response_node.py` — Final response synthesis
- `src/domains/agents/nodes/react_*.py` — ReAct mode 4-node loop (setup, call model, execute tools, finalize)
- `src/domains/agents/models.py` — `MessagesState` (LangGraph TypedDict state with message truncation reducer)
- `src/domains/agents/orchestration/` — ExecutionPlan schemas, parallel executor, validators

### Alternative orchestration: read-only domains without LangGraph

Not every feature needs the LangGraph pipeline. The **`domains/briefing/`** bounded context (Today Briefing home page, v1.18.0+, [BRIEFING_DOMAIN.md](docs/technical/BRIEFING_DOMAIN.md)) demonstrates a deliberate alternative pattern for read-only aggregation:

- Direct orchestration via `asyncio.gather` of independent fetchers (each acquires its own `AsyncSession` via `get_db_context()` — `AsyncSession` is **not safe for concurrent use** from a shared session).
- Per-section Redis cache with TTL adapted to each source's natural change rate.
- Split endpoints (`/cards` fast + `/synthesis` LLM-bound) for non-blocking progressive rendering.
- LLM cost computed via the in-memory pricing cache (`get_cached_cost_usd_eur`) and surfaced in the API payload (`LLMUsage`) without going through the full token-tracking detour.

When a new feature is read-only, latency-sensitive, and would be unnatural in the LangGraph state machine (e.g. dashboards, periodic snapshots), follow the briefing pattern instead of bolting nodes onto the main graph.

### State Management

LangGraph state is a `TypedDict` (`MessagesState`) with a custom `add_messages_with_truncate` reducer that handles token-based truncation, message windowing, and OpenAI message sequence validation. State is checkpointed to PostgreSQL.

Two traps when touching state:
- Any key a node writes **must be declared in `MessagesState`** — undeclared keys are silently dropped by LangGraph (recurring trap: writing an object "mirror" of a dict field under an undeclared key; only the declared dict survives the checkpoint).
- State survives msgpack round-trips: custom objects must be stored as dicts (`to_serializable_dict`) and reconstructed on read — keep both sides in sync (see Systemic Rules, round-trip test).

### Tool System

Tools live in `src/domains/agents/tools/`. Each file groups tools by domain (e.g., `calendar_tools.py`, `emails_tools.py`, `google_contacts_tools.py`). Tools use LangChain's `@tool` decorator and return standardized responses via `ToolResponse` and `ToolErrorModel` from `src/domains/agents/tools/common.py`:

```python
from src.domains.agents.tools.common import ToolResponse, ToolErrorModel

async def my_tool(...) -> dict:
    try:
        result = await do_something()
        return ToolResponse(success=True, data=result).model_dump()
    except Exception as e:
        return ToolErrorModel.from_exception(e, context={"tool": "my_tool"}).to_response()
```

### Prompt System

Prompts are versioned files in `src/domains/agents/prompts/v1/` (`.txt` files). Loaded via `load_prompt()` / `load_prompt_with_fallback()` from `src/domains/agents/prompts/prompt_loader.py`. Versions are configurable via environment variables (e.g., `ROUTER_PROMPT_VERSION=v1`).

### Configuration

Settings are composed from domain-specific Pydantic modules in `src/core/config/`. All settings read from environment variables. Feature flags control optional subsystems: `MCP_ENABLED`, `CHANNELS_ENABLED`, `HEARTBEAT_ENABLED`, `SCHEDULED_ACTIONS_ENABLED`, `SKILLS_ENABLED`.

Dependencies are managed in `apps/api/requirements.txt` (runtime) and `requirements-dev.txt` (dev tools) — these are **intent manifests**; the compiled universal lockfiles `requirements.lock.txt` / `requirements-dev.lock.txt` are what every environment actually installs (ADR-112). After editing a manifest, run `task deps:lock` and commit manifest + locks together (CI enforces it). `pyproject.toml` is only used for tool configuration (black, ruff, mypy, pytest).

### Mermaid diagrams in guides

The HOW / WHY guides (`apps/web/src/data/guides/{how,why}.{lang}.md`) and any future markdown rendered through `<GuideMarkdown>` support inline Mermaid diagrams via fenced ``` ```mermaid ``` blocks. Rendering is handled client-side by `apps/web/src/components/guides/MermaidDiagram.tsx` (`'use client'`, dynamic-imported, dark-mode aware via `useTheme()`). Use this for any architecture/flow diagram instead of ASCII art — both modes (light + dark) are tracked automatically.

## Code Standards

- **Python**: Black (line-length=100), Ruff, MyPy strict. Target: Python 3.12+.
- **Ruff rules**: E (pycodestyle errors), W (warnings), F (pyflakes), I (isort), B (bugbear), C4 (comprehensions), UP (pyupgrade). E501 ignored (handled by Black).
- **TypeScript**: ESLint + Prettier.
- **Commits**: Conventional Commits (`feat(agents):`, `fix(auth):`, etc.)
- **Tests**: pytest with `asyncio_mode = "auto"`. Coverage threshold: 45% (ratchet: +2 per release, never lowered — see GUIDE_TESTING.md). Markers: `e2e`, `integration`, `slow`, `benchmark`, `multiprocess`.
- **Logging**: structlog (structured JSON). Use `structlog.get_logger(__name__)`, never `print()`.
- **i18n**: 6 languages (en, fr, de, es, it, zh). Frontend uses react-i18next with locale files in `apps/web/locales/{lang}/translation.json`. **The pre-commit hook enforces strict key parity** vs `en/translation.json` — every key present in `en` MUST exist in the 5 other locales (the hook diffs `en` keys against each language and aborts the commit on any missing/extra). When using i18next pluralization (`_one` / `_other` suffixes), zh has no plural form per CLDR — duplicate the value to `_one` anyway so parity passes.

## Systemic Rules (hard-won)

These rules close recurring bug classes identified by the 2026-07 full-codebase audit. Each cites the canonical in-repo example to imitate. They are **mandatory** for all new code and for any file being touched (Boy Scout Rule).

### Concurrency & async

- An `AsyncSession` must **never** be shared across concurrent tasks (`asyncio.gather`): SQLAlchemy forbids concurrent operations on one session. Give each parallel fetcher its own session via `get_db_context()` — imitate `domains/briefing/fetchers.py` (documents the trap as CRITICAL). For a handful of indexed queries, a plain sequential loop is fine and simpler.
- No synchronous network or CPU-heavy call on an async path (it freezes the whole event loop, SSE included): use native async clients (`aembed_documents`, never `embed_documents` — good example: `domains/journals/service.py`) or `asyncio.to_thread` for Pillow/Firebase/disk I/O (good example: `domains/skills/executor.py`).
- Singletons and module-level tool instances must **not** store per-request state on `self` (runtime, user language, metrics, contexts): under concurrency it leaks between users. Pass values as parameters, use a `ContextVar`, or instantiate per call — see the `_LANGUAGE_RESULT_KEY` pattern in `agents/tools/base.py` and per-call instantiation in `labels_tools.py`.
- All datetimes are timezone-aware UTC (`datetime.now(UTC)`; `utcnow()`, naive `now()` and `date.today()` are forbidden). The user's display timezone comes from their preferences / `DEFAULT_USER_DISPLAY_TIMEZONE` — never a hardcoded `"Europe/Paris"` literal or default. Enforced in CI by the AST guard `apps/api/tests/unit/test_no_hardcoded_timezone_guard.py`.

### Persistence

- Never mutate a JSONB column in place (`obj.meta["k"] = v`, `obj.meta.update(...)`, or re-assigning the **same** dict object): SQLAlchemy silently skips the UPDATE. Always build a **new** dict: `obj.meta = {**(obj.meta or {}), **updates}`. `flag_modified`/`MutableDict` are intentionally absent from this codebase — new-dict reassignment is the convention. Enforced in CI by the AST guard `apps/api/tests/unit/test_jsonb_mutation_guard.py`.
- Concurrent counters use server-side atomic UPSERTs (`pg_insert ... ON CONFLICT DO UPDATE` with column arithmetic) — imitate `ChatRepository.create_or_update_token_summary`. Never SELECT → increment in Python → flush (lost updates).
- Rows consumed by schedulers use `FOR UPDATE SKIP LOCKED` + an atomic status transition in the same transaction — imitate `scheduled_actions/repository.py`.

### Registries & vocabulary

- The domain vocabulary is **singular** (`contact`, `email`, `event`, `file`, `task`, `place`, `route`) with `DOMAIN_REGISTRY` (`registry/domain_taxonomy.py`) as the single source of truth; `result_key` is derived there. Never create a new hand-maintained domain table or mapping — extend the registry.
- Every new registry/mapping keyed by an enum or domain gets a **boot-time completeness assert** (model: `drafts/display.py::assert_registry_completeness`, ADR-085 — the app refuses to boot on a missing entry). Silent fallbacks on unknown keys are how features die invisibly.
- Serialization pairs (`to_serializable_dict` / `reconstruct_*`) must have a **round-trip equality test over all serialized fields**. Adding a field on one side only is a recurring, silent bug (fields lost after every HITL checkpoint resume).

### i18n & prompts

- Backend user-visible strings go through the central i18n mechanisms (`core.i18n_*`, `APIMessages`, `HitlMessages`, `i18n_drafts`) — never inline French (or any language) in Python, **including fallbacks, parameter defaults, and LLM scaffolding around versioned prompts**. All 6 languages, zh included.
- The Chinese language code is `zh` (User.language, frontend locales). Normalize any locale via `_normalize_language` (`utils/i18n_location.py`) — never key a table on `"zh-CN"` directly.
- Prompt text — including few-shot examples and system scaffolding — lives in versioned files under `prompts/v1/`, loaded via `load_prompt()`. Never inline prompt fragments in `.py`.

### Tools

- Every tool carries `@track_tool_metrics` **and** `@rate_limit` (settings-driven via lambda), especially tools hitting paid external APIs (image generation, Perplexity, Brave). This is a policy, not a per-file choice.
- Tool-module imports must fail **loudly** in dev/CI: a swallowed `ImportError` silently removes an entire tool family from the registry. Never `except Exception: pass` around module imports. Enforced: `_import_tool_modules` raises outside production (counts `tool_module_import_failures_total` in prod) and the registry smoke test `tests/unit/domains/agents/tools/test_tool_registry_smoke.py` imports + invokes every registered tool in CI.
- Error payloads returned to the LLM must not embed raw tracebacks or raw user params (token waste + PII in prompts). Classify with the `ToolErrorCode` taxonomy — never by string-matching on exception messages.

### Observability & honesty

- **No PII at INFO level**: names, emails, GPS coordinates, memory/journal content, message bodies. Counters and IDs at INFO; contents at DEBUG or redacted. The DB encrypts what the logs must not leak.
- An `except` handler whose body is only `pass` is forbidden (CodeQL `py/empty-except`; 193 sites purged 2026-07). Intentional best-effort swallows use `contextlib.suppress(SpecificError)` with the justification comment ABOVE the block (canonical example: metrics emission in `infrastructure/database/session.py`); when one branch must swallow while another logs, nest `with suppress(...)` inside the `try` (canonical example: `agents/api/sse_keepalive.py`). A swallow that hides a real signal gets a `logger.debug(...)` instead. Enforced in CI by the AST guard `apps/api/tests/unit/test_no_empty_except_guard.py`.
- A docstring describing behavior the code does not have **is a bug**: fix the code or the doc in the same change — never leave the contradiction (audited examples: "uses asyncio.to_thread" without to_thread, "connection pool" on a single connection, "streaming check" that loads everything in RAM).
- Dead code is deleted, not kept "for later": an unwired subsystem with settings/i18n/tests attached costs maintenance on every change and fakes coverage. Wire it or remove it — record the decision in a short ADR.

## Key Patterns

- **Connector abstraction**: Google, Apple, Microsoft APIs share a common connector pattern with provider resolver (`src/domains/connectors/`). Only one provider active per functional category (email, calendar, contacts, tasks). When touching a provider client, check the **other providers' behavior for the same operation** (cache invalidation, reply-all semantics, multi-valued field updates) — provider asymmetries are a recurring bug source; parity is the rule.
- **HITL (Human-in-the-Loop)**: 6 approval levels (plan approval, clarification, draft critique, destructive confirm, FOR_EACH confirm, modifier review). Classified in `src/domains/agents/services/hitl_classifier.py`. Note: the plan-approval level is currently auto-approved (`approval_gate_node` is a pass-through — tool-level HITL supersedes it); do not build on plan-level interrupts without re-wiring the gate.
- **Smart Services**: QueryAnalyzerService, SmartPlannerService, SmartCatalogueService use LRU caching and pattern learning to reduce LLM token usage.
- **SSE Streaming**: Responses stream to the frontend via Server-Sent Events.
- **Observability**: 500+ Prometheus metrics defined in `src/infrastructure/observability/`. Langfuse for LLM tracing.
- **LLM Factory**: `src/infrastructure/llm/factory.py` provides multi-provider LLM instantiation (OpenAI, Anthropic, Google, DeepSeek, Ollama). Provider adapters in `src/infrastructure/llm/providers/`.

## Good Practices

The review checklists below are the **process** (what to verify on every plan/PR); the Systemic Rules above are the **hard constraints** (what must never ship). Where they overlap (prompts, logging, i18n), the Systemic Rules entry gives the canonical example to imitate — checklist numbering is stable and referenced elsewhere (e.g. "rule #18"), do not renumber.

- Pull Request Process :
1. Analyze impact and potential incompatibilities.
2. Present findings and wait for approval (green light).
3. Merge only after validation.
4. Test thoroughly.
5. Commit/Push only upon request.

- This is an open-source repo — follow all best practices rigorously.
- Comments, docstrings, and documentation must always be in English.
- Never perform git actions — let the user handle git operations.
- Never work around problems. Analyze root causes thoroughly with evidence (not assumptions) and fix the actual source of the issue.

- Before validating a plan or implementation, be sure to be fully satisfied intellectually (functional logic), functionally (correct execution), and technically (correct, compliant, optimal implementation) and complete.

- Review all plan and code on substance and form:
  — PLAN & COMPLETENESS —
  1.  Validate completeness of the implementation plan
  2.  Conformity with existing codebase patterns (reuse existing classes, methods, helpers, constants, mixins, base classes)
  — PYTHON TYPING & STYLE —
  3.  Complete type hints on every function (args + return) — MyPy strict mode, no untyped defs, no implicit Optional, prefer PEP 604 `X | None` over `Optional[X]`
  4.  Follow the Google Python Style Guide — Google-style docstrings with Args, Returns, Raises sections; module-level docstrings on every file
  5.  Import ordering: stdlib → third-party → local (enforced by Ruff/isort), use `TYPE_CHECKING` block for circular import avoidance
  — NAMING & STRUCTURE —
  6.  Verify naming consistency (imports, classes, methods, variables, constants) and that all arguments are properly defined and passed
  7.  Private helpers use `_method_name` prefix; internal modules use `_` convention
  — FRAMEWORK PATTERNS —
  8.  Pydantic v2: `Field()` with description on every field, `field_validator` with `ValidationInfo`, `model_config = ConfigDict(from_attributes=True)` for ORM models, separate request/response schemas, reuse validator mixins (`TimezoneValidatorMixin`, `LanguageValidatorMixin`, etc.)
  9.  SQLAlchemy v2: `Mapped[Type]` + `mapped_column()`, `ondelete="CASCADE"` on FKs, UTC timestamps (`DateTime(timezone=True)`), inherit `UUIDMixin`/ `TimestampMixin`, `selectinload()` for async eager loading
  10. Repository layer: inherit `BaseRepository[T]`, domain-specific queries with comprehensive docstrings, pagination returns `tuple[list[T], int]`
  11. Service layer: constructor receives `AsyncSession` and creates repositories, uses centralized exception raisers (never raw `HTTPException`), business logic encapsulated with structured logging
  12. Router layer: `Depends(get_current_active_session)` for auth, `Depends(get_db)` for sessions, `check_resource_ownership()` with correct `hide_existence` value, response models declared
  13. Tool system: return `ToolResponse.model_dump()` / `ToolErrorModel.from_exception()` with `ToolErrorCode`, use `safe_parse_json()` and `parse_list_field()` helpers
  14. Respect framework patterns and versions (LangChain 1.x, LangGraph 1.x, FastAPI 0.135+, Pydantic 2.x, SQLAlchemy 2.x — look up docs if needed)
  — CONFIGURATION & CONSTANTS —
  15. Centralize constants and magic strings → `src/core/constants.py` for defaults, `src/core/field_names.py` for field name constants, `.env` for configurable settings, Enums for constrained values (prevents invalid config)
  16. Prompts into versioned files in `src/domains/agents/prompts/v1/`, loaded via `load_prompt()` / `load_prompt_with_fallback()`
  — CROSS-CUTTING CONCERNS —
  17. Logging: `structlog.get_logger(__name__)` exclusively — never `print()` or `logging.getLogger()`. Structured fields on every log call, `logger.exception()` for tracebacks, snake_case event names
  18. Error handling: use centralized exception raisers (`raise_user_not_found`, `raise_permission_denied`, etc.) — never raw `HTTPException`. Tools use `ToolErrorModel` with `ToolErrorCode` enum
  19. Security: `check_resource_ownership()` on every resource access (public → `hide_existence=False`, private → `hide_existence=True`), `encrypt_data()` for PII, `validate_password_strict()` for passwords
  20. Handle internationalization (6 languages: fr, en, es, de, it, zh) — all locale files updated, feature namespace grouping, `useTranslation()` in frontend
  — DESIGN PRINCIPLES —
  21. Respect DRY, YAGNI, KISS, SRP, SoC, Boy Scout Rule, Composition over Inheritance
  22. Write generic, extensible code — no duplication, reuse validator mixins and base classes
  — TESTS —
  23. Tests mirror source structure, proper pytest markers (`@pytest.mark.unit`, `integration`, `slow`), fixtures properly scoped, `asyncio_mode = "auto"`
  — DOCUMENTATION —
  24. Update documentation in `docs/` as well as all cross-cutting docs, `README.md`, ADR if architectural decision, `docs/INDEX.md` index, `docs/technical`, `docs/guide`, `docs/architecture.md`, `docs/architecture_agent.md`, `docs/architecture_langraph.md`, `docs/getting_started.md`, and every other impacted document

  - Verify all runtime integration points on completeness and correctness:
  1. **Config composition** — New settings module added to `Settings` MRO in `src/core/config/__init__.py`, feature flag (`{FEATURE}_ENABLED`) defined, `.env.example` and `.env.prod.example` and `.env.min.prod` (if necessary) updated with all new env vars
  2. **Constants centralization** — All magic values, defaults, scheduler job names, and thresholds extracted to `src/core/constants.py` and referenced (not inlined) in config/code
  3. **Database model registration** — Models imported in 3 places: `alembic/env.py`, `src/infrastructure/database/registry.py` (`import_all_models`), and `main.py` lifespan startup
  4. **Migration integrity** — Alembic migration file created, `upgrade()`/`downgrade()` correct, revision chain unbroken (`alembic heads` returns single head)
  5. **Router wiring** — Domain router included in `src/api/v1/routes.py` with feature-flag guard (`if getattr(settings, "{feature}_enabled", False)`), correct prefix and tags
  6. **Startup initialization** — Required services, caches, or registrations added to `main.py` lifespan context manager in correct order, with error handling and structured logging
  7. **Scheduler registration** — Background jobs registered in `main.py` startup with correct trigger (cron/interval), job ID from constants, `replace_existing=True`, and feature-flag guard
  8. **Prompt files** — New prompts placed in `src/domains/agents/prompts/v1/`, loaded via `load_prompt()` / `load_prompt_with_fallback()`, prompt name added to `PromptName` Literal
  9. **LangGraph wiring** — New agents registered via `registry.register_agent()` in `main.py`, tools using `@tool` + `ToolResponse`/`ToolErrorModel`, catalogue entries present
  10. **Frontend API integration** — Hook created in `src/hooks/use{Feature}.ts` using `useApiQuery`/`useApiMutation`, component/page wired in App Router under `app/[lng]/`
  11. **Internationalization (6 languages)** — Translation keys added to all 6 locale files (en, fr, de, es, it, zh) in `apps/web/locales/`, backend i18n strings handled
  12. **Observability** — Structured logging via `structlog.get_logger(__name__)` (no `print()`), Prometheus metrics defined if domain-critical, error paths logged with context
  13. **Exception handling** — Custom exceptions from `src/core/exceptions.py` used (not raw HTTPException), error responses consistent with existing API contract
  14. **Dependencies** — New packages pinned in `requirements.txt` (runtime) or `requirements-dev.txt` (dev), lockfiles regenerated via `task deps:lock` (ADR-112), Docker image rebuild considered
  15. **Middleware & security** — New endpoints respect rate limiting, auth guards (`Depends`), CORS implications verified, no new security surface exposed unintentionally
  16. **Documentation** — `docs/` updated (ADR if architectural decision, technical doc if new system), `docs/INDEX.md` and `docs/architecture/ADR_INDEX.md` cross-referenced, `README.md` updated if user-facing

## Dev Container Pitfalls

Three traps observed repeatedly when working from the dev environment:

1. **Lockfile sync after `pnpm add` in the container** — The `lia-web-dev` container has its own `/monorepo/pnpm-lock.yaml` that is **not bind-mounted** to the host (only `./apps/web` is mounted, not the monorepo root). Running `pnpm add X` inside the container updates the container's lockfile but the host stays stale, which then breaks `pnpm install --frozen-lockfile` in the prod Docker build. After any `pnpm add`/`pnpm remove` in the container:
   ```bash
   docker cp lia-web-dev:/monorepo/pnpm-lock.yaml d:/Developpement/LIA/pnpm-lock.yaml
   cd apps/web && pnpm install   # re-sync host node_modules so tsc/eslint find the package
   ```
2. **MyPy alignment between venv (host) and Docker** — The pre-commit hook runs MyPy via the host's `apps/api/.venv` (Windows), not via Docker. Some packages without type stubs trigger `[import-untyped]` on one side and `unused-ignore` on the other (e.g. `striprtf`). The fix is to add the offending module to `[[tool.mypy.overrides]] module = [...]` with `ignore_missing_imports = true` in `pyproject.toml` so both runners agree.
3. **Pre-commit hook runs on the host, not in Docker** — The hook executes `ruff`, `black`, `mypy`, `pytest`, `eslint`, `tsc` and i18n parity check from the host. Any new dependency must therefore be installed on **both** sides (container for runtime, host for the hook to find it). Skipping the hook with `--no-verify` is forbidden — fix the underlying issue instead.

When working with settings-driven thresholds in tests (e.g. `mcp_user_max_servers_per_user`, `subagent_max_total_tokens_per_day`), **never hardcode the threshold in the test** — read it from `settings` and compute relative values. Configs change, hard-coded thresholds silently drift the assertion.

## Useful Documentation Pointers

- Full documentation index: `docs/INDEX.md`
- Agent creation guide: `docs/guides/GUIDE_AGENT_CREATION.md`
- Tool creation guide: `docs/guides/GUIDE_TOOL_CREATION.md`
- Testing strategy: `docs/guides/GUIDE_TESTING.md`
- ADR index (111 architectural decisions, ADR-118 latest): `docs/architecture/ADR_INDEX.md`
- 360° audit protocol (recurring; on "run the audit and update the public report", follow it end-to-end including the publication pipeline): `docs/audit/AUDIT_PROTOCOL.md` — public report: `docs/audit/README.md`, size metrics: `scripts/audit/measure_sloc.py`
