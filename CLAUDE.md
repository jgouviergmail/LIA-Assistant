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
task test:backend:unit:fast        # Fast unit tests, xdist, no coverage (pre-commit)
task test:backend:unit:coverage    # The CI command verbatim, including the 62% floor
task test:backend:unit             # All unit tests
task test:backend:integration      # Integration tests (requires PostgreSQL + Redis)
task test:backend:agents           # Agent-specific tests
task test:markers                  # F006 gate: no test may run in zero CI jobs
task test:backend:exhaustive       # Full suite with coverage (do not use, too long)

# Run a single test file
cd apps/api && .venv/Scripts/pytest tests/unit/path/to/test_file.py -v

# Run a single test by name
cd apps/api && .venv/Scripts/pytest tests/ -k "test_name" -v
```

### Frontend Testing (from apps/web/)

```bash
task test:frontend          # vitest run
task test:frontend:coverage # + the per-file coverage thresholds CI enforces
task test:e2e               # Playwright + axe journeys (hermetic, mocked API)
```

Prefer the task over `pnpm test` directly: it blanks `NEXT_PUBLIC_API_URL`, which the Taskfile's global `dotenv: .env` would otherwise inject and which changes measured branch coverage.

### Linting & Formatting

```bash
task lint                   # All linters + ratchets + hygiene + lockfiles + CI parity
task format                 # Auto-format all code

# Backend: Black (formatter) + Ruff (linter) + MyPy (type checker)
task lint:backend
task format:backend

# Frontend: ESLint + a11y/react-hooks/complexity ratchets + non-incremental tsc
task lint:frontend
task format:frontend

# Cross-cutting gates (all included in `task lint`)
task lint:hygiene           # .bak, sync Store calls, Redis setex, raw HTTPException, alembic heads, .env.example
task lint:lockfiles         # manifests vs compiled lockfiles (ADR-112)
task lint:ci-parity         # the workflow orchestrates, it never implements (ADR-151)
task lint:i18n              # strict key parity across the 6 locales
task lint:docs              # documentation drift (broken links, stale code paths)
```

### CI & Pre-commit

```bash
task pre-commit             # format + lint + fast unit tests (~5 min, what the git hook runs)
task ci:fast                # every CI gate that needs no service (~10 min) — run this before pushing
task ci                     # ci:fast + suites needing PostgreSQL, Redis, Docker, a browser
```

**`.github/workflows/ci.yml` orchestrates, `Taskfile.yml` implements** (ADR-151): every CI step is a `task <name>` call, so the pipeline runs literally the command a developer runs. A gate added inline in the workflow is a gate nobody can run before pushing — `task lint:ci-parity` fails on any `run:` step that is neither a task call nor declared runner provisioning. Genuine CI-only steps live in `CI_ONLY` in `scripts/audit/check_ci_parity.py`, each with a written reason.

`task pre-commit` is deliberately narrower than `ci:fast`: it skips the ratchets, the marker-coverage gate, the deploy tests and the frontend coverage thresholds to stay inside its ~5 min budget. Every one of those has redded a build after a green local run.

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
- `docs/` — 320+ documentation files, ADRs, guides, runbooks
- `scripts/` — Deployment, analysis, and utility scripts

### Backend Architecture (DDD)

The backend follows Domain-Driven Design. Entry point: `apps/api/src/main.py`.

- `src/core/config/` — Modular settings composed via multiple inheritance into a single `Settings` class. Access via `from src.core.config import settings`. Each domain module (agents, llm, database, security, etc.) is a separate Pydantic `BaseSettings` subclass.
- `src/core/constants.py` — Global constants and default values used by config modules.
- `src/domains/agents/` — The main domain. Contains the LangGraph graph, nodes, tools, services, and orchestration.
- `src/domains/` — Other bounded contexts: `auth/`, `connectors/`, `voice/`, `interests/`, `heartbeat/`, `user_mcp/`, `users/`, `conversations/`, `reminders/`, etc.
- `src/infrastructure/` — Cross-cutting: Redis cache, LLM factory/providers, MCP client pool, rate limiting, observability.
- `src/infrastructure/startup/` — Lifespan step modules (ADR-123): one module per subsystem (registries, caches, agents, integrations, schedulers, observability, shutdown), one typed function per contiguous boot segment. The `lifespan` in `main.py` remains the single orchestration point — a new startup step means a function in the matching module AND a call in the lifespan, in the position dictated by the order-dependency header comment.
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

Settings are composed from domain-specific Pydantic modules in `src/core/config/`. All settings read from environment variables. Feature flags control optional subsystems: `MCP_ENABLED`, `CHANNELS_ENABLED`, `HEARTBEAT_ENABLED`, `SKILLS_ENABLED`. (There is **no** `SCHEDULED_ACTIONS_ENABLED` flag — scheduled actions are always wired: the router is included unconditionally and only timeout settings exist. Long-documented but never implemented; do not add a guard on it without creating the setting first.)

Dependencies are managed in `apps/api/requirements.txt` (runtime) and `requirements-dev.txt` (dev tools) — these are **intent manifests**; the compiled universal lockfiles `requirements.lock.txt` / `requirements-dev.lock.txt` are what every environment actually installs (ADR-112). After editing a manifest, run `task deps:lock` and commit manifest + locks together (CI enforces it). `pyproject.toml` is only used for tool configuration (black, ruff, mypy, pytest).

### Mermaid diagrams in guides

The HOW / WHY guides (`apps/web/src/data/guides/{how,why}.{lang}.md`) and any future markdown rendered through `<GuideMarkdown>` support inline Mermaid diagrams via fenced ``` ```mermaid ``` blocks. Rendering is handled client-side by `apps/web/src/components/guides/MermaidDiagram.tsx` (`'use client'`, dynamic-imported, dark-mode aware via `useTheme()`). Use this for any architecture/flow diagram instead of ASCII art — both modes (light + dark) are tracked automatically.

## Code Standards

- **Python**: Black (line-length=100), Ruff, MyPy strict. Target: Python 3.12+.
- **Ruff rules**: E (pycodestyle errors), W (warnings), F (pyflakes), I (isort), B (bugbear), C4 (comprehensions), UP (pyupgrade). E501 ignored (handled by Black).
- **TypeScript**: ESLint + Prettier.
- **Commits**: Conventional Commits (`feat(agents):`, `fix(auth):`, etc.)
- **Tests**: pytest with `asyncio_mode = "auto"`. Coverage threshold: 62% (ratchet: never lowered — raise the floor after coverage-improving work to lock the gains, keeping ≥2 pts margin vs measured; see GUIDE_TESTING.md). Markers: `e2e`, `integration`, `slow`, `benchmark`, `multiprocess`.
- **Logging**: structlog (structured JSON). Use `structlog.get_logger(__name__)`, never `print()`.
- **i18n**: 6 languages (en, fr, de, es, it, zh). Frontend uses react-i18next with locale files in `apps/web/locales/{lang}/translation.json`. **The pre-commit hook enforces strict key parity** vs `en/translation.json` — every key present in `en` MUST exist in the 5 other locales (the hook diffs `en` keys against each language and aborts the commit on any missing/extra). When using i18next pluralization (`_one` / `_other` suffixes), zh has no plural form per CLDR — duplicate the value to `_one` anyway so parity passes.

## Audit-Derived Quality Gates (Security Excluded)

These mandatory **non-security** gates apply to new code and every touched file. The detailed subsystem rules below remain authoritative; this section defines the cross-cutting release contract.

### Release contract

- Coverage thresholds and the cycle, complexity, MyPy-debt, React-hooks, accessibility, and file-size baselines are **shrink-only**. Never lower a threshold, raise a baseline, suppress a rule, or exclude business code to absorb a regression. Generated/vendor/unreachable-code exclusions require a written rationale and a comparable measurement.
- Completion requires fresh evidence from the current snapshot: exact commands, exit status, test counts, warnings, and material limits. A targeted or cached success does not replace the relevant clean gate when types, discovery, configuration, migrations, or generated artifacts changed.
- Test code obeys production contracts. Builders use precise override types (for example `Partial<Props>`) and return the declared type without `Any`, double assertions, ignored diagnostics, or mocks that bypass the boundary under test.
- Fix root causes: do not relocate complexity, split one violation into several files, weaken an oracle, substitute a real integration boundary, or update a baseline before measured debt actually decreases.

### Architecture and reliability

- New dependencies must not add runtime import cycles or invert domain/layer boundaries. Break cycles with ports/`Protocol`s, injection, events, or composition modules — not local imports that hide graph edges. Do not add a function with cyclomatic complexity >= 15 or grow an existing hotspot; characterize behavior, then extract cohesive rules/state machines/pure helpers.
- MyPy strict and the logical-SLOC cap remain defaults. New/broader overrides, `Any`, generic ignores, unjustified casts, speculative layers, and unwired code are forbidden. A touched exempt or oversized area must shrink when the change can safely do so.
- Every async client, pool, transport, task, and executor has one owner and is closed/awaited on its owning loop before teardown. Resource warnings, unclosed transports, or stderr emitted after the test summary are failures.
- Persistence transitions are atomic or explicitly resumable and are tested for rollback, crash, retry, and concurrency against the real database when semantics matter. Rebuilds keep the last known-good path serving until validation and an atomic switch; a RAG reindex must never purge or disable the active generation before its replacement is ready.

### Assurance

- Tests are risk-driven and behavioral: cover relevant success, empty/loading, partial failure, retry, cancellation, concurrency, idempotency, cache invalidation, time/timezone, i18n, and recovery paths. Snapshots, CSS assertions, and broad mocks cannot be the sole oracle for business behavior.
- Interactive UI correctness includes native semantics, a stable translated accessible name, keyboard equivalence, deterministic focus, and disabled/error states. Critical changed journeys require hermetic browser coverage with controlled API/SSE traffic; periodic evidence extends Chromium smoke to Firefox/WebKit, zoom/reflow, and assistive technologies.
- Coverage grows by business risk: prioritize orchestration, App Router pages, chat/SSE, connectors, uploads, voice/audio, persistence transitions, and error paths before trivial wrappers.
- A test module never disables itself on a missing provider key (`pytestmark = skipif(not os.getenv("OPENAI_API_KEY"))`): a skipped test is green, so the suite silently leaves CI and rots (measured 2026-07-26: 219 test functions that had never run, 142 of them red on re-enable against a since-migrated API). Mock the provider and keep the tests unconditional, or mark the file `integration`/`e2e` so the exclusion is visible in the CI `-m` filter. Enforced in CI by `apps/api/tests/unit/test_no_env_skipped_suite_guard.py` (shrink-only allowlist, ADR-155).

### Minimum verification by impact

```bash
# Every code change: all static gates plus the smallest relevant behavioral suite
task lint                         # backend + frontend + i18n + docs + the shrink-only ratchets
task test:backend:unit:fast       # backend changes
task test:frontend                # frontend changes

# Frontend coverage: the per-file thresholds CI enforces (blanks NEXT_PUBLIC_API_URL,
# which the Taskfile's global `dotenv: .env` would otherwise inject and which
# measurably changes branch coverage)
task test:frontend:coverage

# Before pushing: every CI gate that needs no service
task ci:fast

# Database or deployment paths: use disposable/hermetic targets only
task db:migrate:replay-check      # migration/model changes
task test:deploy                  # deployment-script changes
```

`task lint:frontend` already runs the three shrink-only ratchets (a11y, react-hooks, complexity) and a **non-incremental** `tsc --noEmit`; run them through the task rather than by hand, so the local gate cannot be the more permissive of the two. The typecheck is non-incremental on purpose: `apps/web/tsconfig.json` sets `"incremental": true` and `*.tsbuildinfo` is gitignored, so a cached local run could pass where the runner's cold one fails.

Choose additional integration, agents, E2E, load, or multi-platform suites from the actual impact. Never run `task test:backend:exhaustive` by default; it remains intentionally excluded because of duration.

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
- Chinese has TWO canonical codes by layer: **backend canonical is `zh-CN`** (`User.language`, `SUPPORTED_LANGUAGES`, all backend i18n table keys), **frontend canonical is `zh`** (URL locales, `apps/web/locales/zh/`). Never key a backend table on `zh` (it would break the nominal path) and never do ad-hoc normalization (`language[:2]`…): route every raw locale through the single chokepoint `normalize_language` (`core/i18n.py`), which maps any variant (`zh`, `zh_CN`, `fr-FR`…) to the backend-canonical code.
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

### Size & structure

- A logical file never grows: it stays under **600 logical SLOC** (tokenize + AST, no docstrings/comments/blanks — the `scripts/audit/measure_sloc.py` semantics), and pre-existing larger files are frozen at their audited size +2% in `apps/api/tests/unit/file_size_baseline.json` — they may only shrink (`task ratchet:update` lowers caps, never raises). Data modules (`core/i18n_*`, `core/config/`, `core/constants`, `domains/llm_config/constants`) are exempt. When a feature outgrows a file, extract a cohesive module — never bump the cap. Enforced in CI by the guard `apps/api/tests/unit/test_file_size_ratchet_guard.py`; doctrine in `docs/guides/GUIDE_DEVELOPPEMENT.md`.

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
  24. Update documentation in `docs/` as well as all cross-cutting docs, `README.md`, ADR if architectural decision, `docs/INDEX.md` index, `docs/technical`, `docs/guides`, `docs/ARCHITECTURE.md`, `docs/ARCHITECTURE_AGENT.md`, `docs/ARCHITECTURE_LANGRAPH.md`, `docs/GETTING_STARTED.md`, and every other impacted document

  - Verify all runtime integration points on completeness and correctness:
  1. **Config composition** — New settings module added to `Settings` MRO in `src/core/config/__init__.py`, feature flag (`{FEATURE}_ENABLED`) defined, `.env.example` and `.env.prod.example` and `.env.min.prod` (if necessary) updated with all new env vars
  2. **Constants centralization** — All magic values, defaults, scheduler job names, and thresholds extracted to `src/core/constants.py` and referenced (not inlined) in config/code
  3. **Database model registration** — Models imported in 3 places: `alembic/env.py`, `src/infrastructure/database/registry.py` (`import_all_models`), and the lifespan startup (`startup/registries.py::import_domain_models`)
  4. **Migration integrity** — Alembic migration file created, `upgrade()`/`downgrade()` correct, revision chain unbroken (`alembic heads` returns single head)
  5. **Router wiring** — Domain router included in `src/api/v1/routes.py` with feature-flag guard (`if getattr(settings, "{feature}_enabled", False)`), correct prefix and tags
  6. **Startup initialization** — Required services, caches, or registrations added to `main.py` lifespan context manager in correct order, with error handling and structured logging (step bodies live in `src/infrastructure/startup/` — ADR-123; the lifespan stays the single ordering point)
  7. **Scheduler registration** — Background jobs registered in `startup/schedulers.py::init_scheduler` (before `leader_elector.start()`) with correct trigger (cron/interval), job ID from constants, `replace_existing=True`, and feature-flag guard
  8. **Prompt files** — New prompts placed in `src/domains/agents/prompts/v1/`, loaded via `load_prompt()` / `load_prompt_with_fallback()`, prompt name added to `PromptName` Literal
  9. **LangGraph wiring** — New agents registered via `registry.register_agent()` in `startup/agents.py::init_agent_registry`, tools using `@tool` + `ToolResponse`/`ToolErrorModel`, catalogue entries present
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
- ADR index (163 architectural decisions, ADR-163 latest): `docs/architecture/ADR_INDEX.md`
- CI/CD pipeline and the thin-CI doctrine (ADR-151): `docs/technical/CI_CD.md`
- 360° audit protocol (recurring; on "run the audit and update the public report", follow it end-to-end including the publication pipeline): `docs/audit/AUDIT_PROTOCOL.md` — public report: `docs/audit/README.md`, size metrics: `scripts/audit/measure_sloc.py`, complexity metrics: `scripts/audit/measure_cc.py`
