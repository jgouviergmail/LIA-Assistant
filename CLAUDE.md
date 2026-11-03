# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
Always check the available plugins/skills at session start and use the ones relevant to the current task.

Scoped guidance: `apps/web/CLAUDE.md` (frontend conventions) applies on top of this file when working under `apps/web/`; `infrastructure/claude-cli/CLAUDE.server.md` is the system prompt of the in-container DevOps CLI (not coding guidance).

## Project Overview

LIA is a multi-agent conversational AI assistant built with **FastAPI** (backend), **Next.js 16** (frontend), and **LangGraph 1.x** (agent orchestration). It integrates Google/Apple/Microsoft APIs, supports HITL (Human-in-the-Loop) approval flows, and features enterprise observability (Prometheus, Grafana, Langfuse).

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
task test:backend:unit:coverage    # The CI unit suite verbatim, measuring coverage (no floor of its own)
task test:backend:coverage         # The floor, on unit + integration together (AC-030b; both suites first)
task test:backend:diff-coverage    # Changed apps/api/src lines covered at the floor (after test:backend:coverage)
task test:backend:unit             # All unit tests
task test:backend:integration      # Integration tests (PostgreSQL + explicit disposable TEST_REDIS_URL on /15)
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
task test:frontend:coverage # + aggregate global and scoped-glob thresholds enforced by CI
task test:e2e               # Playwright + axe journeys (hermetic, mocked API)
```

Prefer the task over `pnpm test` directly: it blanks `NEXT_PUBLIC_API_URL`, which the Taskfile's global `dotenv: .env` would otherwise inject and which changes measured branch coverage.

### Native shell generator tests (from the repository root)

```bash
task mobile:test            # Node built-in tests for native preparation/build contracts
```

Node 24 runs these filesystem and invocation tests without Android or iOS SDKs. The same task runs in CI before native compilation and in `ci:fast`.

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
task lint:docs              # documentation drift: broken links, stale code paths,
                            # orphans, quoted facts vs their sources, AGENTS.md mirror,
                            # living maps
task docs:maps              # living maps: stamp new translations, regenerate facts + French docs
```

**Documentation is gated on what it STATES, not only on how it links.** `task lint:docs` runs seven instruments:

| Instrument | Answers | Repair |
|---|---|---|
| `scripts/audit/doc_audit.py` | Do the links resolve? Are the code paths real? Is any living document unreachable? | by hand |
| `scripts/audit/doc_facts.py` | Does a quoted version or threshold equal its source? | `task docs:fix-facts` |
| `scripts/audit/agents_mirror.py` | Is `AGENTS.md` the current render of `CLAUDE.md`? | `task docs:sync-agents` |
| `scripts/audit/doc_maps.py` | Do the living maps know every ADR, backend domain and infrastructure module, in every language of the site with no stale translation, and is every generated file what its data renders? | `task docs:maps` (`--restamp` after a re-translation) |
| `scripts/audit/findings_register.py` | Does `docs/audit/findings_register.json` agree with every audit report and proof? Is an open P1 past its horizon? (`release:check` fails on it unless deferred) | by hand |
| `scripts/audit/doc_language.py` | Is any new document French? Has a frozen French one been translated? | `task docs:language:update` |
| `scripts/audit/claude_md_budget.py` | Is this file within its budget (total size, length of a block, what a default Codex reaches)? | `task docs:budget -- --update` tightens; a justified addition lifts a limit with one sentence: `-- --raise "<why>"`, `-- --allow "<start>" "<why>"` |

`lint:docs` decides existence from the **git index**, so its verdict matches a fresh clone: a file moved but not staged is invisible to it, and the links to its new home read as broken. `task lint:docs:preview` re-runs the audit over tracked files plus what `git add -A` would stage. Never "fix" a finding the preview clears; stage instead.

Four rules follow, and they are not stylistic:

1. **Never restate a value the code owns.** The coverage floor, a pinned version, a derived count: quote it and `doc_facts` holds you to it, or point at the source.
2. **A document may choose its precision, not be precise and wrong.** `Next.js 16` and the exact pinned version both pass; `LangGraph 1.0` against a pinned `1.2.11` fails. When you mean the generation, write `1.x`.
3. **`AGENTS.md` is generated — never edit it.** Edit `CLAUDE.md`, then run `task docs:sync-agents`; the pre-commit hook refuses a staged pair that disagrees.
4. **This file is a budget, not a record.** It opens every session: a rule takes 2-4 lines (the rule, what enforces it, the ADR), and the measurements and the story go to the ADR. An addition that earns its place lifts the limit with one sentence.

### CI & Pre-commit

```bash
task pre-commit             # format + lint + fast unit tests (commit gate)
task ci:fast                # every CI gate that needs no service — run this before pushing
task ci                     # ci:fast + suites needing PostgreSQL, Redis, Docker, a browser
```

**`.github/workflows/ci.yml` orchestrates, `Taskfile.yml` implements** (ADR-151): every CI step is a `task <name>` call, so a gate added inline is a gate nobody can run before pushing. `task lint:ci-parity` fails on a `run:` step that is neither a task call nor declared runner provisioning; genuine CI-only steps live in `CI_ONLY` in `scripts/audit/check_ci_parity.py`, each with a written reason.

`task pre-commit` is deliberately narrower than `ci:fast`: it skips the ratchets, the marker-coverage gate, the deploy tests and the frontend coverage thresholds, and each of those has redded a build after a green local run.

Git hooks are installed via `task setup:hooks` and live in `.github/hooks/` (`git config core.hooksPath`). The pre-push hook runs the CI's secret scan on what the push sends (`task security:secrets`, gitleaks in Docker): a secret on the remote cannot be taken back.

### Database

```bash
task db:migrate                          # Run migrations (alembic upgrade head)
task db:migrate:create -- "description"  # Create new migration
task db:migrate:down -- REVISION          # Roll back to an explicitly reviewed target
task db:seed                             # Seed dev data
task db:seed:sql                         # Apply SQL seeds (personalities, pricing)
task db:reset                            # Drop all + migrate + seed
task db:create-admin                     # Create admin user for first-time setup
```

### Release surfaces

The version lives in ~25 places (6 manifests, 18 guide stamps, README, GETTING_STARTED)
and three public counts are derived from their source (ADR files, latest ADR number,
CHANGELOG entries). All of it is mechanical, so none of it belongs in a checklist:

```bash
task release:check                # report any version/count drift; refuse an overdue P1 finding (read-only)
task release:bump -- 1.32.0       # write every mechanical surface + realign the counts
task release:sync-counts          # realign the ADR/CHANGELOG counts alone
```

`scripts/release/version_surfaces.py` is the single declaration, shared by the bump
script and the CI guard `test_version_surface_consistency_guard.py` — what a release
writes is exactly what CI verifies. Guide stamps are **discovered**, so a new stamped
guide must be declared tracked or exempt (with a reason) or the build reds. What the
tool deliberately does NOT write is printed after every bump: the CHANGELOG entry, the
FAQ changelog, the README theme sentence, and `LANDING_STATS.tests` (a real
measurement, never derived).

## Good Practices

The review checklists below are the **process** (what to verify on every plan/PR); the Systemic Rules are the **hard constraints** (what must never ship). Where they overlap (prompts, logging, i18n), the Systemic Rules entry gives the canonical example to imitate. Checklist numbering is stable and referenced elsewhere (e.g. "rule #18"): do not renumber.

- Pull Request Process :
1. Analyze impact and potential incompatibilities.
2. Present findings and wait for approval (green light).
3. Merge only after validation.
4. Test thoroughly.
5. Commit/Push only upon request.

- This is an open-source repo — follow all best practices rigorously.
- Comments, docstrings, and documentation are in English; every NEW document is. An existing French document may be edited in French, but the frozen list of French documents only shrinks (`doc_language.py`, in `task lint:docs`). Exempt by decision: living maps, dated plans (`docs/superpowers/plans/`), audit reports (`docs/audit/`).
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
  14. Respect framework patterns and versions (LangChain 1.x, LangGraph 1.x, FastAPI 0.x, Pydantic 2.x, SQLAlchemy 2.x — look up docs if needed)
  — CONFIGURATION & CONSTANTS —
  15. Centralize constants and magic strings → `src/core/constants.py` for defaults, `src/core/field_names.py` for field name constants, `.env` for configurable settings, Enums for constrained values (prevents invalid config)
  16. Prompts into versioned files in `src/domains/agents/prompts/v1/`, loaded via `load_prompt()` (no inline fallback — ADR-284)
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
  3. **Database model registration** — A new model is declared in ONE place: `import_all_models` in `src/infrastructure/database/registry.py`. `alembic/env.py` and the lifespan startup (`startup/registries.py::import_domain_models`) both CALL it — they are readers, not a second and third list, and editing them instead is the wrong fix (verified 2026-09-11)
  4. **Migration integrity** — Alembic migration file created, `upgrade()`/`downgrade()` correct, revision chain unbroken (`alembic heads` returns single head)
  5. **Router wiring** — Domain router included in `src/api/v1/routes.py` with feature-flag guard (`if getattr(settings, "{feature}_enabled", False)`), correct prefix and tags
  6. **Startup initialization** — Required services, caches, or registrations added to `main.py` lifespan context manager in correct order, with error handling and structured logging (step bodies live in `src/infrastructure/startup/` — ADR-123; the lifespan stays the single ordering point)
  7. **Scheduler registration** — Background jobs registered in `startup/schedulers.py::init_scheduler` (before `leader_elector.start()`) with correct trigger (cron/interval), job ID from constants, `replace_existing=True`, and feature-flag guard
  8. **Prompt files** — New prompts placed in `src/domains/agents/prompts/v1/`, loaded via `load_prompt()`, prompt name added to `PromptName` Literal; every `{placeholder}` produced by the loader (guarded), one-line scaffolds in a `key|template` lines file read by `parse_prompt_sections`
  9. **LangGraph wiring** — New agents registered via `registry.register_agent()` in `startup/agents.py::init_agent_registry`, tools using `@tool` + `ToolResponse`/`ToolErrorModel`, catalogue entries present
  10. **Frontend API integration** — Hook created in `src/hooks/use{Feature}.ts` using `useApiQuery`/`useApiMutation`, component/page wired in App Router under `app/[lng]/`
  11. **Internationalization (6 languages)** — Translation keys added to all 6 locale files (en, fr, de, es, it, zh) in `apps/web/locales/`, backend i18n strings handled
  12. **Observability** — Structured logging via `structlog.get_logger(__name__)` (no `print()`), Prometheus metrics defined if domain-critical, error paths logged with context
  13. **Exception handling** — Custom exceptions from `src/core/exceptions.py` used (not raw HTTPException), error responses consistent with existing API contract
  14. **Dependencies** — New packages pinned in `requirements.txt` (runtime) or `requirements-dev.txt` (dev), lockfiles regenerated via `task deps:lock` (ADR-112), Docker image rebuild considered
  15. **Middleware & security** — New endpoints respect rate limiting, auth guards (`Depends`), CORS implications verified, no new security surface exposed unintentionally
  16. **Documentation** — `docs/` updated (ADR if architectural decision, technical doc if new system), `docs/INDEX.md` and `docs/architecture/ADR_INDEX.md` cross-referenced, `README.md` updated if user-facing

## Code Standards

- **Python**: Black (line-length=100), Ruff, MyPy strict. Target: Python 3.14.
- **Ruff rules**: E (pycodestyle errors), W (warnings), F (pyflakes), I (isort), B (bugbear), C4 (comprehensions), UP (pyupgrade), ASYNC2 (blocking calls in async code, `src` only — AC-035). E501 ignored (handled by Black).
- **TypeScript**: ESLint + Prettier.
- **Commits**: Conventional Commits (`feat(agents):`, `fix(auth):`, etc.)
- **Tests**: pytest with `asyncio_mode = "auto"`. Coverage threshold: 78% (ratchet: never lowered — raise the floor after coverage-improving work to lock the gains, keeping ≥2 pts margin vs measured; see GUIDE_TESTING.md). Markers: `e2e`, `integration`, `slow`, `benchmark`, `multiprocess`.
- **Logging**: structlog (structured JSON). Use `structlog.get_logger(__name__)`, never `print()`.
- **i18n**: 6 languages (en, fr, de, es, it, zh). Frontend uses react-i18next with locale files in `apps/web/locales/{lang}/translation.json`. **The pre-commit hook enforces strict key parity** vs `en/translation.json` — every key present in `en` MUST exist in the 5 other locales (the hook diffs `en` keys against each language and aborts the commit on any missing/extra). When using i18next pluralization (`_one` / `_other` suffixes), zh has no plural form per CLDR — duplicate the value to `_one` anyway so parity passes.

## Audit-Derived Quality Gates (Security Excluded)

These mandatory **non-security** gates apply to new code and every touched file. The detailed subsystem rules below remain authoritative; this section defines the cross-cutting release contract.

### Release contract

- Coverage thresholds and the cycle, complexity, MyPy-debt, React-hooks, accessibility, and file-size baselines are **shrink-only**. Never lower a threshold, raise a baseline, suppress a rule, or exclude business code to absorb a regression. Generated/vendor/unreachable-code exclusions require a written rationale and a comparable measurement.
- Completion requires fresh evidence from the current snapshot: exact commands, exit status, test counts, warnings, and material limits. A targeted or cached success does not replace the relevant clean gate when types, discovery, configuration, migrations, or generated artifacts changed.
- Test code obeys production contracts. Builders use precise override types (for example `Partial<Props>`) and return the declared type without `Any`, double assertions, ignored diagnostics, or mocks that bypass the boundary under test.
- Fix root causes: do not relocate complexity, split one violation into several files, weaken an oracle, substitute a real integration boundary, or update a baseline before measured debt actually decreases.
- Production build inputs are explicit and immutable: no `latest` image, unversioned global installation, or undeclared transitive import. Pin production base images by version and digest, pin globally installed tools, declare every imported package directly, and validate through a clean frozen install and no-cache production build.

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
- A test double that receives a coroutine owns it: it must await it, schedule it, or explicitly capture and close it. A no-op mock of a fire-and-forget boundary is forbidden. Any unawaited coroutine, `PytestUnraisableExceptionWarning`, unclosed transport, or post-summary stderr is a test failure. Changes to background execution must pass both the fast xdist gate and the sequential coverage gate.

### Minimum verification by impact

```bash
# Every code change: all static gates plus the smallest relevant behavioral suite
task lint                         # backend + frontend + i18n + docs + the shrink-only ratchets
task test:backend:unit:fast       # backend changes
task test:frontend                # frontend changes

# Frontend coverage: aggregate global and scoped-glob thresholds (`thresholds.perFile` is not enabled)
task test:frontend:coverage

# Before pushing: every CI gate that needs no service
task ci:fast

# Database or deployment paths: use disposable/hermetic targets only
task db:migrate:replay-check      # migration/model changes
task test:deploy                  # deployment-script changes
```

`task lint:frontend` already runs the shrink-only ratchets (a11y, react-hooks, complexity, double assertions) and a **non-incremental** `tsc --noEmit`: run them through the task, so the local gate cannot be the more permissive of the two (`apps/web/tsconfig.json` sets `"incremental": true`, and a cached local run could pass where the runner's cold one fails).

Choose additional integration, agents, E2E, load, or multi-platform suites from the actual impact. Never run `task test:backend:exhaustive` by default; it remains intentionally excluded because of duration.

## Systemic Rules (hard-won)

These rules close recurring bug classes identified by the 2026-07 full-codebase audit. Each cites the canonical in-repo example to imitate. They are **mandatory** for all new code and for any file being touched (Boy Scout Rule).

Nine principles run through them; where no rule fits a new case, apply these:

1. **One fact, one door**: what several places read goes through ONE function, and a guard forbids a second.
2. **Declared, never inferred**: what cannot be read from a file (who pays, who files, how it reads) lives in a registry a guard holds complete.
3. **Enforced means published, published means enforced** (ADR-184).
4. **A count is exact, or it does not exist; a cut is stated** (ADR-185).
5. **A failure is said, never guessed, never read as success** (ADR-303).
6. **An effect is claimed before it happens and closed from an explicit result** (ADR-263).
7. **A switch removes the capability, never the record** (ADR-280).
8. **Nothing is held across a wait**: no session, transaction or lock around a network call (ADR-304).
9. **A prompt states what the code enforces, and nothing else** (ADR-284).

### Concurrency & async

- **An `AsyncSession` is never shared across concurrent tasks** (SQLAlchemy forbids it): each parallel fetcher opens its own through `get_db_context()`, imitate `domains/briefing/fetchers.py`. For a handful of indexed queries a sequential loop is simpler.
- **A session lives no longer than the queries it serves, never around a wait**: `get_db_context()` and `get_db` commit at exit, and the pooled connection returns only at commit/rollback. A `yield` dependency lives as long as the response, so a route that STREAMS authenticates through `get_current_active_session_for_stream` (guard `test_streaming_routes_hold_no_session_guard.py`); a runner drives a model turn with NO session open. Measure with `pg_stat_activity` (`state`, `xact_start`) during the act, never by reading the code.
- **No transaction stays open across a network call** (ADR-304). A connector client is never built on `ConnectorService(db)`: hand it a `DetachedConnectorService` or open it through `connectors/active_client.open_active_client` (guard `test_connector_client_on_session_guard.py`). A job that keeps its session commits its reads before every wait, in a session it owns. The chat turn's connector operations each end their transaction (`ConcurrencySafeConnectorService`), a client's own writes running on a short session of their own.
- **The server bounds it too** (ADR-304 amendment 2026-10-23): every application connection starts with `DATABASE_LOCK_TIMEOUT_MS` and `DATABASE_IDLE_IN_TRANSACTION_TIMEOUT_MS` (`database/server_bounds.py`; the migration engine carries none), and each one reached is counted (`db_bound_reached_total`).
- **A credential read writes nothing on its caller's session, and a claim that only `flush`es is no claim** (ADR-304): the API-key stamp is one atomic `||` merge apart, under a bounded `lock_timeout` (`connectors/api_key_use.py`); reminders are claimed ONE at a time, committed, settled conditioned on the claim, stale claims released on `updated_at`. A bot-global resource (the Telegram webhook) is set by the scheduler LEADER alone, never deleted by one stopping worker.
- **A token has ONE refresh door** (`connectors/oauth_refresh.py`, ADR-302 amendment 2026-10-23): one exchange per token across callers and workers, a write conditioned on the token it started from and bounded in its wait, `invalid_grant` re-verified before anyone is disconnected; a caller owning its session reads (`read_connector_credentials`) THEN asks `fresh()`. Only `oauth_refresh_exchange.py` sends `grant_type=refresh_token` (guarded).
- **No synchronous network or CPU-heavy call on an async path**: it freezes the whole event loop, SSE included. Use native async clients (`aembed_documents`, never `embed_documents`: `domains/journals/service.py`) or `asyncio.to_thread` for Pillow, Firebase, disk I/O (`domains/skills/executor.py`). Ruff ASYNC2 refuses what it can type (`open`, `pathlib`, `os.path`, `time.sleep`), never a path a helper returned; a file upload streams through `infrastructure/multipart_upload.py` (AC-035).
- **Singletons and module-level tool instances store no per-request state on `self`** (runtime, user language, metrics, contexts): it leaks between users. Pass parameters, use a `ContextVar`, or instantiate per call: `_LANGUAGE_RESULT_KEY` in `agents/tools/base.py`, `labels_tools.py`.
- **All datetimes are timezone-aware UTC** (`datetime.now(UTC)`; `utcnow()`, naive `now()` and `date.today()` are forbidden). The display timezone comes from preferences / `DEFAULT_USER_DISPLAY_TIMEZONE`, never a `"Europe/Paris"` literal or default (guard `apps/api/tests/unit/test_no_hardcoded_timezone_guard.py`).
- **Elapsed time is computed on absolute instants**: Python subtracts two datetimes sharing a `tzinfo` on their wall clocks, 24 h for the 25 of a clock change (ADR-318).
- **Periodic jobs that share a divisor align forever**: an `IntervalTrigger` counts from scheduler start. Every interval job carries `jitter=jitter_seconds_for(...)` or an entry in `JITTER_EXEMPT` with the reason it must stay exact (guard `apps/api/tests/unit/infrastructure/startup/test_scheduler_jitter.py`).
- **An external call needs a shock absorber sized for the burst, not for the volume** (ADR-254): the shaper's window is short, it composes the existing `RedisRateLimiter`, and it **expires open** on timeout and Redis failure: our own throttle is never why a request fails.
- **A provider's 429 is backpressure on ONE key, never the service's health** (ADR-108 amendment 2026-10-13): the API-key client records it as an answer, retries it jittered and hands a spent one back typed (`ConnectorAPIError` 429 with `Retry-After`).
- **A generation whose outcome is unknown is never relaunched** (ADR-221 amendment 2026-10-28): ONE policy for every LLM family (`providers/retry_policy.py`, applied by `create_llm`): never after a timeout or a loss once sent, at most `LLM_TRANSIENT_RETRY_MAX` after a 429, a 5xx or a connection that never left, never a stream after its first byte, nor answered by another form of the call (`client_retries.may_send_in_another_form`).
- **A connector request too** (ADR-221 amendment 2026-10-29): a transport failure is resent only when it cannot repeat an act (`connectors/clients/retry_policy.may_resend`); an event create carries the provider's idempotency derived from the effect key; a create with none to carry (contacts, tasks, mail) is sent once, its lost answer a failure.
- **Two endpoints serving one screen make ONE act** (ADR-271): `infrastructure/utils/single_flight.py`: whoever asks first runs it, whoever asks meanwhile gets the SAME object. It takes a FACTORY, its key is the WHOLE identity (a forced refresh never joins an unforced build), waiters are `shield`ed, and it is deliberately not a cache. A joiner collects nothing and files no decision.
- **It coalesces within ONE process only**: production sets `WEB_CONCURRENCY` to 4, so the Dockerfile `CMD` and the compose `replicas` do not prove a service single-process: read the environment. Across workers, `infrastructure/utils/shared_flight.py`: one worker CLAIMS the build in Redis, the others wait for the cache it fills; the OWNER releases by compare-and-delete on a token, waiting is bounded, a waiter that times out builds, a failure falls back to building, a FORCED refresh never waits, and the caller composes the whole key with its declared family head.
- **The predicate that redoes work asks « has this been built? »**, never « does it hold anything interesting? », which cannot tell a cold cache from an empty day and re-implements a threshold another module owns (ADR-248). A value with no TTL is never written, so it is invisible to every cache-only reader.
- **A retry needs a FACTORY, not an awaitable**: a coroutine is awaitable once. `retry_async` (`infrastructure/utils/retry.py`) is the core, `retry_with_backoff` delegates to it. Classify retryability structurally: the status code through `__cause__`, never the message; the message is a fallback when the chain carries none (`apps/api/src/infrastructure/llm/embedding_errors.py`, one classifier for every embedding caller).
- **A text flattener is linear by construction, and a validated URL is fetched on the address the check saw** (ADR-326): every paired span a flattening rule reads is bounded (`MARKDOWN_SPAN_MAX_CHARS`), no character belongs to two neighbouring classes (growth and exhaustive-equivalence tests, API and browser twins), and a validated URL leaves through `pinned_stream` alone, one validated hop at a time, never a client that follows redirects.

### Persistence

- **Never mutate a JSONB column in place** (`obj.meta["k"] = v`, `obj.meta.update(...)`, the same dict reassigned): SQLAlchemy silently skips the UPDATE. Always build a **new** dict: `obj.meta = {**(obj.meta or {}), **updates}`. `flag_modified`/`MutableDict` are intentionally absent (guard `apps/api/tests/unit/test_jsonb_mutation_guard.py`).
- **Concurrent counters use server-side atomic UPSERTs** (`pg_insert ... ON CONFLICT DO UPDATE` with column arithmetic): imitate `ChatRepository.create_or_update_token_summary`. Never SELECT → increment in Python → flush (lost updates).
- **Rows consumed by schedulers use `FOR UPDATE SKIP LOCKED` + an atomic status transition in the same transaction**: imitate `scheduled_actions/repository.py`.
- **Every distributed lock, lease or durable claim has a unique owner token** and, where stale writers can commit, a monotonic fencing token. Acquire, renew, release, heartbeat, complete, fail and retry are atomic and conditioned on the current owner/token; a failed heartbeat immediately aborts all later effects. `SET NX` then unconditional `EXPIRE`/`DELETE`, and `SKIP LOCKED` then work outside the claiming transaction, are forbidden. Test expiry, takeover, stale completion/failure and stale shutdown with two actors.
- **A bare enum member as the RESULT of a SQL expression is bound as `NullType`**: in `case((cond, Status.X), else_=...)` its VALUE reaches a `native_enum=False` column storing its NAME, and the transaction rolls back. Carry the column's type (`literal(member, Model.column.type)`, `_status_literal` in `meetings/repository.py`) and prove every repository transition on real PostgreSQL (`tests/integration/domains/meetings/test_repository_jobs.py`; guard `apps/api/tests/unit/test_no_bare_enum_in_sql_case_guard.py`).
- **Absence of an exception is not proof of delivery.** Durable work reaches `DELIVERED` or `SUCCEEDED` only from an explicit successful result: claim before external effects, persist attempts and errors, propagate a stable idempotency key; test total failure, partial success, crash after effect before commit, two workers. **And test a cancellation**: `except Exception` never sees `CancelledError`, so a claim's owner closes it `abandoned` through it (`write_through_cancellation`, ADR-263 amendment 2026-09-27 b).
- **A notification is delivered when `NotificationResult.durably_delivered` says so**: archived, pushed or sent on a channel, never an SSE event alone. A consumer filing « delivered » passes `require_durable=True` and counts a failure on a session of its own (guard `test_durable_delivery_guard.py`, ADR-263 amendment 2026-10-23).
- **A worker rebuilds a cached table from the DATABASE at startup, never from a shared blob**; only a cross-worker invalidation adopts the blob, because the writer republished it just before notifying (`load_published_pricing_cache`, ADR-063). Every writer of such a table publishes that invalidation after its commit, rebuild then notify (`refresh_and_publish_pricing_cache`). A cached value has as many writers as the tables it is built from: find them all.
- **A Redis key named by a user id declares the scope of its family** in `apps/api/src/infrastructure/cache/key_families.py` (`CONVERSATION`, `USER_CACHE`, `USER_LEARNING`, `USER_RUNTIME`, `GLOBAL`). The reset purges by declared family, never by pattern alone; an undeclared family is kept and counted (ADR-260; boot assert over `core.constants` prefixes, `apps/api/tests/unit/test_redis_key_family_guard.py`). Account deletion and « Tout oublier » remove learning keys; a reset never does.
- **No `CHECK` spans two columns a foreign-key action can touch**: a delete fires the FK actions independently, the CHECK rejects whichever intermediate state comes first, and `CHECK` cannot be `DEFERRABLE`: drop the column, not the invariant (ADR-276; only a real `INSERT` then `DELETE` on PostgreSQL proves it).
- **A Python `None` on a JSONB column is the JSON `null`, which `IS NULL` does not match**: `JSONB(none_as_null=True)` where a constraint or a query reads the column's NULL, proven on PostgreSQL (ADR-322).
- **A same-named parameter bound in a select list and a comparison is two types under asyncpg**: bind each once, typed (ADR-305).
- **Every module reading the message table outside its repository declares how it reads** (`conversations/message_readers.py`: `VISIBLE_ONLY` or `WHOLE_RECORD` with a reason, AST guard), and every archived metadata is built by a `build_*_metadata` (`agents/api/archive_metadata.py`, AST guard). A turn archives up to THREE rows, and a repair predicate names the KIND of row, never only its correlation key (ADR-276).

### Registries & vocabulary

- **The domain vocabulary is singular** (`contact`, `email`, `event`, `file`, `task`, `place`, `route`), `DOMAIN_REGISTRY` (`registry/domain_taxonomy.py`) the single source of truth, `result_key` derived there. Extend the registry, never a new hand-maintained table.
- **Every registry keyed by an enum or domain gets a boot-time completeness assert** (model: `drafts/display.py::assert_registry_completeness`, ADR-085): the app refuses to boot on a missing entry. Silent fallbacks on unknown keys are how features die invisibly.
- **Serialization pairs (`to_serializable_dict` / `reconstruct_*`) have a round-trip equality test over all serialized fields**: a field added on one side is lost after every HITL checkpoint resume.
- **A status vocabulary is a contract: every member is PRODUCED somewhere and READ somewhere else** (ADR-303). `AgentResultStatus` is binary (`SUCCESS`/`ERROR`), a partial failure is a `SUCCESS` carrying `AgentResult.failed_steps`. `test_agent_status_vocabulary_guard.py`: the `Literal` IS the enum, no reader compares a status to a retired value, every member lives in at least two modules. Writer and reader share the field CONSTANT (`FIELD_SUCCESS`, `FIELD_ERROR`, `FIELD_ERROR_CODE`), never a convention.
- **A graph config's run id has ONE reader** (`core/run_config.run_id_of`, guard `test_run_id_single_reader_guard.py`): it lives in `metadata`, and a reader of `configurable`, a key no writer writes, files its acts under the THREAD id.
- **A ReAct answer reaches the response model as PROSE, and it never sees a tool result** (ADR-263 §23): the register's succeeded acts are stated in a directive of their OWN, as the model's own acts (`response_directive_performed_actions.txt`), never as data lines beside the answer.

### i18n & prompts

- **Backend user-visible strings go through the central i18n mechanisms** (`core.i18n_*`, `APIMessages`, `HitlMessages`, `i18n_drafts`): never inline French or any language in Python, fallbacks, parameter defaults and LLM scaffolding around versioned prompts included. All 6 languages, zh included.
- **A language nobody passed is the DECLARED one** (ADR-323): `resolve_language(x)` answers an explicit `x` normalised, else the language declared where the person became known (`Accept-Language` through `RequestLanguageMiddleware`, the account in `_authenticate` / `get_optional_session`, `language_scope` for out-of-turn runs, sweeps, Telegram and voice lookups), else `DEFAULT_LANGUAGE`, validated at boot. A stored language is read through `normalize_language`; a code bound for a PROVIDER passes verbatim (`language or resolve_language()`) and is mapped at the client boundary.
- **Language guards** (ADR-323): no parameter, field or constant defaults to a language (`test_no_language_default_guard.py`); every table keyed by language holds exactly the six canonical codes (`test_language_table_completeness_guard.py`); gettext catalogs hold exactly the msgids the code names, translated in six languages, `.mo` equal to `.po` (`test_gettext_catalog_guard.py`, kept by `apps/api/scripts/i18n/sync_catalogs.py`); an `Annotated` never sits inside a union (`test_annotated_metadata_guard.py`).
- **What only the MODEL reads is technical English or a versioned prompt**, never a translation of one language. ADR-323 lists what remains French or translated (prompt files, section headers, `memories/emotional_state.py`, classifier action types, tool messages through `_()`), changed only after a measurement.
- **Chinese has TWO canonical codes by layer**: backend `zh-CN` (`User.language`, `SUPPORTED_LANGUAGES`, all backend table keys), frontend `zh` (URL locales, `apps/web/locales/zh/`). Never key a backend table on `zh`, never do ad-hoc normalization (`language[:2]`…): every raw locale goes through the chokepoint `normalize_language` (`core/i18n.py`).
- **Prompt text lives in versioned files under `prompts/v1/`**, few-shot examples and system scaffolding included, loaded via `load_prompt()`; never inline in `.py`.
- **A prompt never carries a tunable numeric value in prose**: it reads settings via a placeholder (model: `{semantic_broad_batch}` in `smart_planner_prompt.txt`, ADR-184).
- **Every `{placeholder}` of a prompt has a producer in the module that loads it**, and a file containing `{{` is rendered by `.format()`, never `.replace()` (ADR-284; `test_prompt_placeholders_are_produced.py`, `RENDERED_BY`, `PROVIDER_TEMPLATE_SYNTAX`).
- **One instruction per context, emitted only when the content exists** (ADR-284): `response_context_sections.txt` declares `key|Tag|description` in injection order, and `get_response_prompt` neither wraps nor escapes anything itself.
- **The bound a prompt publishes is the bound the tool enforces, from ONE constant, and a prompt promises only what the turn can run** (ADR-284): `<Computation>` is rendered iff `run_python_tool` is bound AND the capability is on, with the enforced budget.
- **Prose never lives in a `.py`, and neither does a fallback** (ADR-284): one-line scaffolds go in a `key|template` lines file read by `parse_prompt_sections` (`core/prompt_store.py`, ONE parser); tool payload messages are technical English (ADR-256); a language's NAME goes through `core.i18n.get_language_name`; every `*_prompt_version` setting has a reader (`test_prompt_version_settings_have_readers.py`).

### Constraints & verdicts

- **A constraint the system enforces is published to whoever produces the value** (ADR-184): `_manifest_to_dict` gives the planner `min`/`max` on every bounded parameter. Whatever a validator can reject, its producer must be able to read.
- **What is mechanically repairable is repaired before validation**, never reported as a defect: out-of-bounds numbers are clamped in `SmartPlannerService._build_plan` (`planner/parameter_bounds.py`), beside the `for_each_max` auto-correction. What needs invented intent (`pattern`, `enum`, wrong types) stays a real error.
- **A count shown to the user is a claim: it is exact, or it does not exist** (ADR-185): an aggregate over the whole set (`GROUP BY`, `COUNT(*)`), the ROWS paged alone, the exact total shipped beside the page so a cap is stated. A page and its counts come from ONE filtered statement, and every ordering ends on the primary key.
- **Folding identity has exactly one implementation** (ADR-185): resolve the raw spellings from an aggregate and match them EXACTLY in SQL (`IN (...)`), never re-express `fold_name` as `unaccent`+`lower` (`_spellings_for` in `relations/service.py`).
- **A validation verdict is not a failure**: `route_from_planner` never reads `is_valid`, a rejected plan executes unchanged. Telling the user an operation was blocked requires the capability never to have run (`attempted_tool_names` in `plan_blockers.py`, ADR-184); one that ran and failed is told by the failures directive.
- **A Google scope judges only the provider it describes** (ADR-184 amendment 2026-10-13): a scope verdict reads `ungranted_scopes` (the category from the tool CLASS, the account's connectors from `active_connector_types_ctx`), never `required ⊆ granted` alone.
- **A step that ran is never « blocked », and nothing offers a tool no connector serves** (ADR-184 amendment 2026-10-14): a failure has ONE channel, the failures directive, or the CARD for a confirmed draft; « no connector is active » is `ToolErrorCode.CONNECTOR_NOT_ACTIVATED`; a card never shows a code or an error's text (census guard, ADR-303); a provider-bound tool no ACTIVE connector serves leaves the turn's and the voice's catalogue.
- **A narrowing filter is more permissive than the decider, never less**: an `ILIKE` on the raw needle is stricter than the `fold_name` it feeds and discards the rows folding exists to catch (ADR-276).
- **A source says why it has nothing**: `used | empty | disabled | unavailable` (ADR-292), `NOT_REQUESTED` (ADR-269): « I did not look » is neither « found nothing » nor « could not look », and a blind source is named, never read as empty.
- **What is stored is read** (`SELECTORS_READ_BY`, ADR-268): a value accepted, stored, displayed and dropped is ADR-184 pointing the other way.

### Tools

- **Every tool carries `@track_tool_metrics` and `@rate_limit`** (settings-driven via lambda), especially tools hitting paid external APIs. This is a policy, not a per-file choice.
- **Tool-module imports fail loudly in dev/CI**: a swallowed `ImportError` silently removes a tool family, so never `except Exception: pass` around them. `_import_tool_modules` raises outside production (counts `tool_module_import_failures_total` in prod); `tests/unit/domains/agents/tools/test_tool_registry_smoke.py` imports and invokes every registered tool.
- **A tool that acts declares what it owes the user**: `mutation_policy` on the manifest (`read`, `draft`, `confirm`, `reversible`, `artefact`, `sandboxed`, the last three with a written reason), checked at boot by `assert_mutation_policy_completeness`. Only the `search` category (an explicit `get_`/`search_`/`list_` name) is exempt; `readonly` is the inference fallback, no exemption. A third-party MCP tool never declares it: the policy is DERIVED from the server's annotations and never looser than they are (ADR-263/ADR-255).
- **A boot-time completeness assert must actually stop the boot**: completeness failures raise `StartupCompletenessError` and are re-raised by the step; unrelated failures keep their resilience (ADR-263).
- **Error payloads returned to the LLM embed no raw traceback or user params.** Classify with the `ToolErrorCode` taxonomy, never by string-matching an exception message: shrink-only ratchet `test_no_message_substring_classification_guard.py`, over the whole of `src/`, following the alias a message is read through.
- **A tool fails by RETURNING, and what it returns is READ by one predicate** (`core/tool_outcome.explicit_success`, ADR-303): `ToolErrorModel.to_response()` and `UnifiedToolOutput.failure()` never raise, so a reader watching for exceptions counts every failure as a success. The register, the metrics decorator and the ReAct loop share it; a failure log carries the error CODE, never the message.
- **What a failure means reaches the model** (ADR-303): pipeline step failures through the runtime failures directive (the exact total, the tool named), ReAct failures through a STRUCTURAL marker (`ToolMessage.status="error"`), because told nothing a model invents a diagnosis. A declared failure buys NO iteration (ADR-256; `bool(pydantic_model)` defeats it).
- **What reaches a provider SDK is an EXACT `str`**: `HumanMessage.text` is a `TextAccessor`, a `str` subclass google-genai validates into an EMPTY request. Normalise at the funnel (`GeminiRetrievalEmbeddings._exact_str`) and at the chokepoint naming the user's message, never caller by caller (ADR-266).
- **A provider branch never hands a STORED value to an SDK**: `kwargs_for` is the only seam on EVERY branch of `_prepare_provider_config` (`test_reasoning_seam_guard.py`: every `ProviderType` × every level, nothing non-JSON in the constructor kwargs). A value an operator types is normalised ONCE for every reader (`providers/ollama_urls.py`); a kwarg several sources write (`extra_body`) is merged, never assigned.
- **A provider is served by its native client, never by an OpenAI-compatible shim** (ADR-267): the shim cannot say what the bridge does not spell, and its silence reads as a model defect.
- **A sub-loop's budget end is a closing pass, never an answer of LangGraph's** (ADR-083 amendment 2026-10-13 b): `ReactSubAgentRunner` gives its last call no tool (`react_runner_closing`), its limits count graph STEPS (`react_runner_budget`), and every reader maps the typed `outcome`, never the text, the partial in its own fields.
- **A read tool's data reaches the answer through its data block, in both modes, and a payload's declared failure is never returned as a success** (ADR-347): put facts in `structured_data` (the message is a header); a tool whose message renders its data declares `pipeline_data_channel` with a reason; formatters answer a failure with `failure()`; a connector tool runs in registry mode.
- **What a turn may offer is filtered once** (ADR-280 amendment 2026-10-18): a switched-off capability, a disabled MCP server, a missing connector and a forbidden application operation all apply in `services/turn_catalogue.build_turn_catalogue`; the planner, the ReAct loop, the router, the initiative, a sub-agent and a skill's plan read that snapshot (`test_turn_catalogue_single_authority_guard.py`).
- **An MCP tool is confirmed on ONE rule in every mode** (ADR-263 amendment 2026-10-30 (b)): the gate reads the turn's offered manifest, ReAct asks on `registry/confirmation_rule`, a Pipeline step reading, or ordered after, a pending act waits and resumes on its real result, the answer telling the work done beside it (`nodes/plan_resume`) and what a confirmed tool call returned (ADR-368 §10); a routine confirms only what its FORM pre-approved.
- **`context_domain` on a read tool needs its whole chain**: a `RegistryItemType`, a registered `ContextTypeDefinition`, emitted `registry_updates` and a `context_key` on the manifest (the loader validates the key at boot); declared alone it is inert (ADR-276, `agents/workboard/context.py`).

### Observability & honesty

- **No PII above DEBUG** (ADR-317): names, emails, GPS coordinates, memory/journal content, message bodies, and every text a person wrote or a model wrote about them (queries, topics, instructions, answers, file and label names, URLs). A line above DEBUG carries FACTS (counts, lengths, identifiers, codes, a URL's host). Enforced by the VALUE, not the field name: `tests/unit/test_log_content_guard.py` refuses a preview or a value derived from content, each allowance with a written reason.
- **Under a content NAME the filter keeps a count, a flag or an absence and nothing else** (a coordinate name, nothing at all), so a fact is logged under a name saying what it is (`origin_id=`, never `origin=`). Other containers' lines reach Loki through the same URL rules, applied by Alloy (`test_promtail_query_redaction_guard.py`). An unparsable output goes through `log_unreadable_text`.
- **What an error TEXT quotes is withheld by the filter** (`observability/quoted_content.py`: PostgreSQL `DETAIL`/`CONTEXT`, SQLAlchemy parameters, Pydantic `input_value=`, tracebacks). A database failure is logged by its facts (`infrastructure/database/errors.py`: SQLSTATE, constraint, table, never `str(e)`), every engine hides its parameters (`test_sql_parameters_hidden_guard.py`), and a vendor's refusal by status and bounded code (`voice/vendor_refusal.py`, ADR-345; shrink-only `test_vendor_body_excerpt_guard.py`). The DB encrypts what the logs must not leak.
- **Logging is configured before the application is imported, and a logger is bound where it logs**: whatever logs before `configure_logging()` keeps structlog's defaults, no level or PII filter. The configuration is `main.py`'s first application import (`observability/logging_bootstrap.py`, guard `test_logging_configured_first_guard.py`), and the tool bases expose `logger` as a property (`_ToolLoggerMixin`), never bound in a singleton's `__init__`.
- **A latency SLI observes only a turn a person waits for** (ADR-119 amendment 2026-10-18): `streaming/latency_sli.py` is the one door to the two latency histograms (AST-guarded), and a quantile alert evaluates only from `1 / (1 − q)` observations up.
- **An `except` handler whose body is only `pass` is forbidden** (CodeQL `py/empty-except`): use `contextlib.suppress(SpecificError)` with the justification ABOVE the block (`infrastructure/database/session.py`); when one branch swallows while another logs, nest `with suppress(...)` inside the `try` (`agents/api/sse_keepalive.py`). A swallow hiding a real signal gets a `logger.debug(...)`. Guard `apps/api/tests/unit/test_no_empty_except_guard.py`.
- **A docstring describing behavior the code does not have is a bug**: fix the code or the doc in the same change.
- **A metric nobody can see is a metric nobody acts on**: every Prometheus metric is referenced by a Grafana panel, a recording rule or an alert, read from their EXPRESSIONS only (shrink-only ratchet `apps/api/tests/unit/test_metric_coverage_ratchet_guard.py` + `metric_coverage_baseline.json`; `task ratchet:metrics` only removes). A labelled counter that never fired exposes no series: a panel watching a rare failure needs `... or vector(0)` and `"noValue": "0"`.
- **Dead code is deleted, not kept "for later"**: wire it or remove it, and record the decision in a short ADR.
- **Optional configuration is validated as a matrix**, not only empty and fully configured: every supported Alertmanager receiver combination starts and routes representative labels; every dashboard query resolves to a metric producer, recording rule or documented datasource. Syntax-only validation is insufficient.
- **A guard that runs for no case guards nothing, and one that matches a NAME validates a name**: prove it on a failing fixture and read AST calls (ADR-245 amendment, ADR-263).
- **A figure declares what it is** (`SeriesKind`: a count, two measures stacked, a mean), a mean computed from a SUM and its observations: a sum of means is not a quantity (ADR-263).

### Spend, quota and authorship

- **Where a module's model spend is recorded is DECLARED, never inferred** (`LLM_SPEND_ROADS`, `infrastructure/llm/spend_roads.py`): accounting is ambient, so a file cannot answer it. Four roads: `TURN` (ambient), `ACCOUNTED` (its own, out of turn), `CALLER` (a NAMED accountant, itself checked), `INSTANCE` (no owner, a written reason). The guard reads AST calls and refuses an omission, a stale entry, or a road the module does not take.
- **A euro nobody owns still reaches a ledger**: self-diagnosis, catalogue translations and the broadcast translator must NOT touch `user_statistics`; `domains/usage_limits/instance_spend.py` feeds `InstanceDailyBudget`, a separate path since `token_usage_logs.user_id` is `NOT NULL`. Recording is half a ledger, asking first the other: modules call `is_instance_spend_blocked`, and an ungated one declares why in `INSTANCE_GATE_EXEMPT`.
- **Who pays decides who is billed** (`domains/usage_limits/cost_bearers.py`): `provider_api_keys` has no `user_id`, so LLM, TTS, STT, image and Maps run on the deployment's key; `get_api_key_credentials(user_id, …)` is per-account, so Perplexity, Brave, the weather connector and telephony run on the person's own. The guard compares the declaration to what `check_user_allowed` enforces, in BOTH directions.
- **The authorship of a register row is declared by the CALL SITE**: `track_proactive_tokens` has no default, one predicate decides it (`effects/source.py`). The briefing is reached from `GET /briefing/*`, a reminder is `scheduled`, only a runner sweep is `proactive`.
- **A capability that is not a TOOL records no consultation by construction** (`record_treatment` fires from the tool gate alone): `effects/user_data_readers.py` makes every out-of-turn surface declare its recorder module or a written reason, over a COMPLETE list (every funnel `task_type` plus every `ProactiveTask.task_type`). A cache hit is not a consultation, a hidden section was never opened, a source that refused reads `failed`.
- **A row recorded outside a published collector is DROPPED**: a surface running alone opens its own run (`consultation_collector`) when `collector_is_active()` says nobody did, and joins the turn otherwise.
- **The register is OFFERED, never fetched**: `agents` imports `relations`, so `domains/shared/consultation_sink` holds the seam, the register installs itself at import, and the contract is NAMED, never `**Any`. The coupling ratchet counts LOCAL imports: a function-level import only hides the edge.
- **Every direct client caller is ENUMERATED** (`effects/direct_client_callers.py`): a module importing from `connectors/clients` never meets the tool gate, so the import graph is walked and each declares itself a recorder (naming its surface), not-a-read (with the verified reason) or a debt (empty, shrink-only).
- **A capability reached through its CLIENT is invisible to the gate**: the register answers « which capability LIA used », never « whose data »: an interest sweep's Brave query is recorded at `_try_source`, the one place every source runs.
- **A proactive notification is an ACTION, and it is CLAIMED** (`effects/out_of_turn_effects.py`): claimed before the push leaves, settled from `NotificationResult`, never from the absence of an exception. One claim per THING SAID, not per run: the seam names the `occurrence`.
- **A direct-read surface DECLARES its vocabulary; nobody transcribes it** (`domains/shared/consultation_surfaces.py`): `TREATMENT_DOMAIN_OVERRIDES` merges the declaration, `assert_treatment_domain_completeness` checks the capabilities too, `record_surface_consultations` is the ONE door (a guard refuses any other caller of the seam), and the surface key is shared with `CONSULTATION_RECORDERS`.
- **Every accounted run names who files it in the decision register** (ADR-263 amendment 2026-09-27): a module opening `TrackingContext(` or `out_of_turn_spend(` is declared in `effects/decision_filers.py` (AST guard); a one-shot act is filed once (`record_decision_once`); a click that acts is an ACTION (`shared/action_sink.py`).
- **Every token the PLATFORM pays for answers to BOTH ceilings** (ADR-272): the account's and the instance's day; only what a person pays with their OWN connector key is outside. A chokepoint is the INNERMOST door (`get_structured_output`), never its wrapper; a gate that returns early bounds nothing. The verdict is one, the transport decides how it is received: a request path raises (`enforce_usage_limit`, `usage_limits/enforcement.py`), a background path degrades (`spend_blocked`) and logs **skipped**, never *failed*. `test_every_spend_site_is_bounded` walks the registry.
- **One usage guard, and `LLM_CHOKEPOINTS` names every door** (`infrastructure/llm/usage_guard.py`): a call with no owner is never blocked (its bound is the instance ledger), and `"system"` is not an account.
- **Reading a provider's usage metadata has ONE implementation** (`infrastructure/llm/usage_metadata.py`), with `model_name_of`.
- **Every euro the platform pays for a person is traced, displayed, attributed and counted for that person, whatever the modality or the path** (owner rule, ADR-272 amendment 2026-09-20): `pending_families()` is the ONE persistence predicate (a guard refuses a `_*_records` bucket it does not read); a counter never fails open (`track_google_api_call` counts `google_api_calls_unaccounted_total`, alert `GoogleApiCallsUnaccounted`); an out-of-turn surface opens its accounting around the WHOLE act; the road is declared in `domains/google_api/spend_roads.py`.
- **A billed Google Maps image is counted where Google bills it**: at the proxy, on the 200, through ONE helper, never pre-counted when the URL is built, joined to its turn by a run id SIGNED over (run id, account). One figure for what a run cost: `MessageTokenSummary.billed_cost_eur`.
- **A Maps call is filed at the SKU its REQUEST triggers, and a price is the vendor's, read** (migration `d5f8b2a6c9e3`): Places by field mask (`:lite`), Routes by request features (`routes_sku_suffix`), a Route Matrix per ELEMENT (`units`, persisted as `request_count`). A correction migration replaces only a value LIA shipped, never an administrator's.

### Size & structure

- **A logical file stays under 600 logical SLOC** (tokenize + AST, no docstrings/comments/blanks: `scripts/audit/measure_sloc.py`). Larger files are frozen at their audited size +2% in `apps/api/tests/unit/file_size_baseline.json` and only shrink (`task ratchet:update` lowers, never raises; guard `apps/api/tests/unit/test_file_size_ratchet_guard.py`; doctrine `docs/guides/GUIDE_DEVELOPPEMENT.md`). Data modules (`core/i18n_*`, `core/config/`, `core/constants`, `domains/llm_config/constants`) are exempt. Extract a cohesive module, never bump the cap.
- **What a worker holds for its whole life takes its compact form, once** (ADR-283 amendment 2026-10-12): an embedding vector is a `float32` array, never a `list[float]` (`agents/services/tool_vectors.py`), a per-user MCP catalogue is parsed once per worker (`ServerVectorCache`), an argument model class is built once per JSON schema (`build_args_schema`), the startup heap is frozen last (`startup/process_heap.py`), a BM25 index is one per key. A census walks types and sizes only: a referrer walk killed a production worker.
- **What a singleton loads is multiplied by the worker count**: bound it (`VOICE_STT_MAX_RECOGNIZERS`, least recently used out), a decode in flight keeping its own reference (ADR-283).
- **A heavy library is imported where it is used**: `LAZY_ONLY` in `test_lazy_heavy_imports_guard.py` declares each measured cost and refuses a module-level import under `src/`, module-level `try` included (ADR-283).
- **A connection budget has a FLOOR as well as a ceiling**: `ConnectionBudget.persistent_total`, with `test_postgres_memory_floor_guard.py` reading compose and profile together (ADR-283).

## Architecture

### Monorepo Structure

- `apps/api/` — Python 3.14 FastAPI backend (source in `src/`, tests in `tests/`)
- `apps/web/` — Next.js 16 + React 19 + TypeScript frontend
- `infrastructure/` — Docker, database seeds, observability config (Prometheus, Grafana)
- `docs/` — 320+ documentation files, ADRs, guides, runbooks
- `scripts/` — Deployment, analysis, and utility scripts

### Backend Architecture (DDD)

The backend follows Domain-Driven Design. Entry point: `apps/api/src/main.py`.

- `src/core/config/` — Modular settings composed via multiple inheritance into a single `Settings` class. Access via `from src.core.config import settings`. Each domain module (agents, llm, database, security, etc.) is a separate Pydantic `BaseSettings` subclass.
- `src/core/constants.py` — Global constants and default values used by config modules.
- `src/domains/agents/` — The main domain. Contains the LangGraph graph, nodes, tools, services, and orchestration.
- `src/domains/` — Other bounded contexts: `auth/`, `connectors/`, `voice/`, `interests/`, `habits/`, `heartbeat/`, `user_mcp/`, `users/`, `conversations/`, `reminders/`, etc.
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
                                                                 ↕ ReAct Recovery (a declared gap, bounded passes — ADR-310)
```

Both modes converge on the same Response Node and stream via SSE. The `react_agent` LLM type in `LLM_TYPES_REGISTRY` is dedicated to the ReAct loop.

**Six ReAct invariants (ADR-248, ADR-286, ADR-310), each paid for by a defect measured on a real turn:**

1. **A message that still carries `tool_calls` is never an answer**, nor is a reply the provider cut at its output budget: it never reaches `messages` and stops the loop as `output_truncated` (`react_output_guard.py`, ADR-275 amendment). On a budget exit `react_finalize_node` publishes an EMPTY `final_message`, the response node synthesises from the tool results, and the stop reason travels to a versioned directive forbidding announced work, deliberately not gated on `DIAGNOSTICS_ENABLED`: a turn ends when its answer is sent.
2. **The stop condition is ONE predicate** (`react_exit_reason`), read by the router to decide and by the finalize node to explain.
3. **The loop knows what the pipeline knows.** `react_setup_node` injects the psychological profile through `build_psychological_profile` and the KNOWLEDGE SPACES through `build_knowledge_block` (the pipeline's own `<UserDocuments>`, from the bundle the router prefetched, read with `peek_response_context`, never consumed); the tool cap keeps every family reachable (ADR-293). A rule that only reaches the response node can reword a promise, never turn it into an action. Context blocks live in `nodes/react_context.py`, one best-effort builder each.
4. **A turn that stops mid-flight closes its own books**: the persisted `AIMessage` keeps `tool_calls` nobody will answer, and every later turn on the thread would be rejected by the provider. `react_finalize_node` emits one `ToolMessage` (`status="error"`, saying it never ran and what to do next) per abandoned call; a call with no `id` is skipped, never paired by guesswork. The turn-start repair stays the net for a hard kill and purges BOTH shapes of a call: `tool_calls` and the typed block in list-shaped `content` (`function_call`, `tool_use`).
5. **A tool result is projected item by item under a token budget, and the cut is stated** (ADR-286): `render_data_block` (`tools/react_tool_wrapper.py`) pages the heaviest list of `structured_data` at ITEM boundaries, the first item whole, under `min(react_tool_result_max_tokens, window × react_tool_result_window_fraction)`; `compose_tool_message` appends `tool_result_budget_note` AFTER `</external_content>` and counts it (`react_tool_result_truncated_total`).
   - The provider's raw tree never leaves the builder (`build_emails_output` pops `payload`); a tool whose data only the executor injects declares `execution_modes={pipeline}` (`local_query_engine_tool`). The block fails CLOSED: `mark_untrusted_data` wraps it as external unless every registry item it carries is INTERNAL.
6. **A turn is judged on its RESULT: a gap it declares buys a bounded recovery pass** (ADR-310). Every fact the loop SET OUT to obtain (the person's, and each cross-check it started) ends obtained or declared in an `<unresolved>` block with the rungs tried; a detail nobody asked for is no gap. A result answering ANOTHER question is an obstacle like an error. The ladder: the call corrected, another source marked `(fallback)`, the declaration.
   - `should_recover` CALLS `react_exit_reason` and routes a declared gap to `react_recovery` while a pass is left (`REACT_RECOVERY_PASSES_MAX`, `0` = off). The node calls no model and removes the draft; later calls are SHOWN the draft and a directive, never written to `messages`. The final message REPLACES the draft, so it restates every finding, and a pass ending with no usable answer hands the draft back.
   - Relative dates become ISO 8601 before any tool parameter, and **a tool never replaces a value it cannot read**: it refuses it (`INVALID_INPUT`, the format, today's date), under ONE constant read by the manifest AND the `@tool` schema (the loop binds the schema, never the manifest).

**Ephemeral Python (ADR-249, ReAct only).** `run_python_tool` runs a short script in the SKILLS sandbox (SEC-001) when a step needs computation a model does badly. The manifest declares `execution_modes={"react"}`, and nothing may OFFER it to a planner that cannot run it: a CATALOGUE reader applies `manifests_for_mode`, the initiative node is bounded by `is_initiative_eligible`, which refuses by CAPABILITY ahead of every preference.

`execute_source` refuses any sandbox mode but `container`. The turn's data reaches the script on stdin, never re-typed into the source; the code is admin-visible in the debug panel and nowhere else.

The iteration budget is ADR-238's domain-span value as a STARTING allowance, extended while the loop keeps producing results (`react_progress_extension_enabled`); `react_agent_max_iterations` and the compute timeout stay the hard bounds. A `success: false` or empty result is not production.

Key files:
- `src/domains/agents/nodes/routing.py` — Conditional routing functions between nodes
- `src/domains/agents/nodes/planner_node_v3.py` — Plan generation (ExecutionPlan DSL)
- `src/domains/agents/nodes/task_orchestrator_node.py` — Parallel task execution
- `src/domains/agents/nodes/response_node.py` — Final response synthesis
- `src/domains/agents/nodes/react_*.py` — ReAct mode 5-node loop (setup, call model, execute tools, recovery, finalize)
- `src/domains/agents/models.py` — `MessagesState` (LangGraph TypedDict state with message truncation reducer)
- `src/domains/agents/orchestration/` — ExecutionPlan schemas, parallel executor, validators

### Alternative orchestration: read-only domains without LangGraph

Not every feature needs the LangGraph pipeline. **`domains/briefing/`** (Today Briefing, [BRIEFING_DOMAIN.md](docs/technical/BRIEFING_DOMAIN.md)) is the pattern for a read-only, latency-sensitive feature that would be unnatural in the state machine (dashboards, periodic snapshots): follow it instead of bolting nodes onto the main graph.

- Direct orchestration via `asyncio.gather` of independent fetchers, each on its own `AsyncSession` from `get_db_context()`.
- Per-section Redis cache with a TTL adapted to each source's change rate; split endpoints (`/cards` fast + `/synthesis` LLM-bound) for progressive rendering.
- LLM cost through the in-memory pricing cache (`get_cached_cost_usd_eur`), surfaced in the payload (`LLMUsage`).

### State Management

LangGraph state is a `TypedDict` (`MessagesState`) with a custom `add_messages_with_truncate` reducer (token-based truncation, message windowing, OpenAI message sequence validation), checkpointed to PostgreSQL.

Six traps when touching state:
- Any key a node writes **must be declared in `MessagesState`**: undeclared keys are silently dropped by LangGraph (recurring: an object "mirror" of a dict field under an undeclared key; only the declared dict survives the checkpoint).
- State survives msgpack round-trips: custom objects are stored as dicts (`to_serializable_dict`) and reconstructed on read, both sides in sync (round-trip test).
- **A counter charged as `previous + spent` is a debt for the life of the thread unless the turn start resets it**: the checkpoint restores it every turn, and the account's ONE thread (`get_or_create_conversation`) lives for weeks. What a ReAct turn starts with is ONE declaration, `react_turn_reset()` (`utils/react_budget.py`, spread by the router, `test_react_turn_reset_guard.py`); a list in state is an accumulator too. Never a list in a node.
- **A per-turn value lives in the turn's `query_intelligence`**, never in a state key of its own: the router rewrites it every turn, while a copy written only when non-empty is inherited by every later turn (ADR-120 amendment 2026-10-11).
- **The graph input is the turn's DIFF, never the restored state** (ADR-022 amendment 2026-10-12): the loader keeps a deep copy (`orchestration/turn_input.snapshot_restored_state`), the stream hands the graph what changed (`turn_input.prepare_graph_input`); a writer between the two declares nothing.
- **Nothing that must hold for a whole turn is derived from the LENGTH of `messages`**: the reducer trims the head by tokens on every update. Anchor on `current_turn_id`, or count from the END (ADR-309 amendment).

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

Prompts are versioned files in `src/domains/agents/prompts/v1/` (`.txt` files). Loaded via `load_prompt()` from `src/domains/agents/prompts/prompt_loader.py` — there is no fallback loader: a prompt has one text, the versioned file (ADR-284). Versions are configurable via environment variables (e.g., `RESPONSE_PROMPT_VERSION=v1`), and every `*_prompt_version` setting must have a reader (guarded).

### Configuration

Settings are composed from domain-specific Pydantic modules in `src/core/config/`, all read from environment variables. Feature flags control optional subsystems: `MCP_ENABLED`, `CHANNELS_ENABLED`, `HEARTBEAT_ENABLED`, `SKILLS_ENABLED`. There is **no** `SCHEDULED_ACTIONS_ENABLED` flag: scheduled actions are always wired; do not add a guard on it without creating the setting first.

**The database overrides the environment, which overrides the constants** (owner rule): an env template states the code's default, omits the key, or says why it differs (`# … — differs from default: <reason>`); the templates carry production's proven values except the documented opt-ins, and a `(default: X)` a comment states must be the code's — `test_env_template_parity_guard.py`, [GUIDE_CONFIG_ARCHITECTURE.md](docs/guides/GUIDE_CONFIG_ARCHITECTURE.md) (AC-036).

Dependencies are managed in `apps/api/requirements.txt` (runtime) and `requirements-dev.txt` (dev tools) — these are **intent manifests**; the compiled universal lockfiles `requirements.lock.txt` / `requirements-dev.lock.txt` are what every environment actually installs (ADR-112). After editing a manifest, run `task deps:lock` and commit manifest + locks together (CI enforces it). `pyproject.toml` is only used for tool configuration (black, ruff, mypy, pytest).

### Model capability catalogue (ADR-244)

`llm_models` is the runtime authority on what a model can do; its capability columns are curated from two vendored public registries, never from the network on an execution path.

```bash
task llm:catalogue:fetch          # refresh the vendored snapshot (network; review the diff)
task llm:catalogue:sync           # print the reviewable diff + the retirement report (read-only)
task llm:catalogue:preflight      # before deploying a catalogue change, on the target instance (read-only)
```

- `llm_models.capability_provenance` says who filled the capabilities: `declared` (defaults nobody curated; `get_effective_context_window` refuses to trust it), `imported` (corroborated by the snapshot) or `verified` (a human edit through `LLMModelService.update`). It is row-level, its evidence field-level: `imported` vouches for `sync_diff.CORRECTABLE_FIELDS` alone, so a reader of any other column (`supports_strict_mode`, the sampling flags) must require `verified`.
- Prices, reasoning metadata, streaming, the sampling flags and `kind` are never imported (each exclusion asserted in `apps/api/tests/unit/infrastructure/llm/catalogue/`). Deactivating a model takes an uncontradicted past deprecation date AND no reference: `is_retiring` (warn) and `is_retired` (may deactivate), in `catalogue/field_mapping.py`.
- A slot's `max_tokens` is held to the output cap a vouched row declares (`infrastructure/llm/output_cap.py`, read by the slot resolution, the client door and the admin metadata; `declared`, discovered, Ollama or a default no registry states = no cap).
- The real per-agent configuration lives in `llm_config_overrides`, in the database, and deployments do not run the same models: the preflight reports what the instance would deactivate, what it keeps because it references it, which configured models fail their slot's capabilities, and whether a `verified` row would lose strict structured output. A unit test reads `LLM_DEFAULTS`, never a database.

### Reasoning configuration (ADR-245)

Asking a model to think has one stored shape for every provider: `ReasoningIntent(level, budget_tokens, exclude_from_output)` (`core/reasoning_intent.py`). The former shapes are still READ (`intent_from_legacy`, shared by the migration, the reference seeds and the golden test); nothing writes them.

- **The ladder is ordinal and provider-independent**: `provider_default < none < minimal < low < medium < high < xhigh < max`. `provider_default` is the identity: it produces no kwarg on any family.
- **What a model accepts is a derived `ReasoningProfile`**, not a column: `resolve_reasoning_profile(provider, model, model_levels=...)` (`core/reasoning_profiles.py`, re-exported by `llm/reasoning/profiles.py`). A new provider is one rule entry plus one renderer in `translate.py`, never a branch inside an existing family.
- **`kwargs_for(provider, model, stored)` is the ONLY seam** an adapter may call. It never raises: an unknown model produces no kwarg.
- **Runtime coerces, the write path rejects.** Ties break upward, `none` is never a coercion target, and `can_disable`, not ladder membership, governs the off switch: a catalogue row narrows the DEPTHS, never the switch. Every coercion is counted and logged (`llm_reasoning_coerced_total`).
- **The UI is offered exactly what the API accepts**: `/llm-config/metadata` publishes the resolved profile (`LLMConfigService._reasoning_metadata`), never the raw catalogue declaration.
- The only catalogue value the resolution reads is `reasoning_enum_values`, in the LADDER's vocabulary (a seed guard refuses any level off it). `llm_models.reasoning_widget` and `reasoning_budget_range` are gone.
- Every model row shows its `capability_provenance`, and `GET /admin/llm/catalogue-status` reports the verdict of `task llm:catalogue:sync` by the same code (`llm/catalogue/status.py`). A correction stays a reviewed migration: no endpoint writes.
- `tests/unit/infrastructure/llm/reasoning/golden_kwargs.json` freezes what the builders produced: a new family extends it, never edits an existing entry.

### Native JEV decisions (ADR-325)

JEV is a native `decision` provider, never a chat adapter. Every integration belongs to `domains/llm_config/jev_registry.py`: one configuration slot and one independently switchable usage, behind a general switch. Each operation reads its routing from PostgreSQL and retains that snapshot; switching off affects subsequent operations.

`infrastructure/llm/jev_runtime.py` owns native execution, usage limits, spend attribution and bounded diagnostics; a paid failure and its fallback both count. Uncertain decisions fall back: relevance previews never remove canonical results, extraction observers never suppress writes, HITL exclusions never approve execution. Read [the integration guide](docs/technical/JEV_INTEGRATION.md) before adding a usage.

### Third-party skills and the skill library (ADR-327)

- A skill name is unique per ACCOUNT: every lookup names its scope, deletes go by id. `skills.provenance` `url`/`plugin`/`library` is third-party, asked of `skills/trust.py` only (unbound request = third-party): isolated runner, `untrusted_markdown`, external content, no frame.
- The library installs at the commit its preview read, through `import_directory`. The chat's import tool only PROPOSES: the card's click installs (`skills/proposal_service.py`), never a version it did not describe.
- `run_skill_command` runs a skill's command in a COPY of its folder (tar in, tar out, the command as `$1` of a constant bootstrap); files under `out/` are filed by name AND first bytes, a page as text. Every sandbox run starts from `Dockerfile.sandbox` (no Docker client, no code), proven by `task sandbox:libraries:check`.
- A command's `hosts` go through ADR-298's decision (`skills/command_network.py`): an unknown host is asked in the ReAct loop only, refused elsewhere naming the settings; a third-party skill never reaches a connector.
- Peer sharing (2026-10-18) is decided by the same trust seam: server-owned `peer` provenance, or `plugin` with server-owned `peer_authored`, gets the recipient-authored execution policy after activation; a received copy commits disabled, without credentials, grants or an HITL override; client metadata confers nothing, origin metadata is informational. See [peer capability transfers](docs/technical/PEER_CAPABILITY_TRANSFERS.md).

### Mermaid diagrams in guides

Markdown rendered through `<GuideMarkdown>` (the HOW / WHY guides, `apps/web/src/data/guides/{how,why}.{lang}.md`) supports fenced `mermaid` blocks, rendered client-side by `apps/web/src/components/guides/MermaidDiagram.tsx` (dark-mode aware). Use them for any architecture or flow diagram, never ASCII art.

## Key Patterns

- **Connector abstraction**: Google, Apple, Microsoft APIs share a common connector pattern with provider resolver (`src/domains/connectors/`). Only one provider active per functional category (email, calendar, contacts, tasks). When touching a provider client, check the **other providers' behavior for the same operation** (cache invalidation, reply-all semantics, multi-valued field updates): provider asymmetries are a recurring bug source, parity is the rule.
- **An e-mail speaks ONE vocabulary at the client boundary** (`EmailMessage`, ADR-287): clean text body, quoted history and signature removed, no fabricated Gmail tree. A digest is computed once per message and cached (`EmailDigestService`, family `email:digest`); `get_emails_tool` chooses what it serves through `detail` (`metadata` | `summary` | `full`), and a tool's model spend travels on the runtime's `RunnableConfig`.
- **A Graph query is ONE request Graph accepts** (`graph_mail_query`): what it cannot carry is checked on the page and the count set aside published (`set_aside_on_page`). An IMAP id carries its folder (`imap_handles`): a UID names a message within one folder (ADR-287 amendment 2026-10-13).
- **HITL (Human-in-the-Loop)**: the approval types of `HitlInteractionType` (clarification, draft critique, entity disambiguation, tool confirmation, FOR_EACH confirmation, plus the plan approval and destructive confirm of the note below), classified in `src/domains/agents/services/hitl_classifier.py`. Note: the plan-approval level is auto-approved (`approval_gate_node` is a pass-through, tool-level HITL supersedes it) and the destructive-confirm level is emitted by no node (ADR-323): do not build on either without wiring it.
- **The confirmation card has ONE author, the renderer** (`render_confirmation_card`, streamed before the model's first token; the model only asks the question). The HITL preview speaks Markdown, a plain surface flattens through ONE door (`markdown_to_plain_text`, which only ever shortens), `drafts/summary_renderer.py` is a dispatch table with a boot assert, and the punctuation between a label and its value travels with the labels (ADR-276).
- **Smart Services**: QueryAnalyzerService, SmartPlannerService, SmartCatalogueService use LRU caching and pattern learning to reduce LLM token usage.
- **SSE Streaming**: Responses stream to the frontend via Server-Sent Events.
- **Observability**: 658 Prometheus metrics defined in `src/infrastructure/observability/`. Langfuse for LLM tracing.
- **LLM Factory**: `src/infrastructure/llm/factory.py` provides multi-provider LLM instantiation (OpenAI, Anthropic, Google, DeepSeek, Ollama). Provider adapters in `src/infrastructure/llm/providers/`.

## Dev Container Pitfalls

Three traps observed repeatedly when working from the dev environment:

1. **Lockfile sync after `pnpm add` in the container** — The `lia-web-dev` container has its own `/monorepo/pnpm-lock.yaml` that is **not bind-mounted** to the host (only `./apps/web` is mounted, not the monorepo root). Running `pnpm add X` inside the container updates the container's lockfile but the host stays stale, which then breaks `pnpm install --frozen-lockfile` in the prod Docker build. After any `pnpm add`/`pnpm remove` in the container:
   ```bash
   docker cp lia-web-dev:/monorepo/pnpm-lock.yaml d:/Developpement/LIA/pnpm-lock.yaml
   cd apps/web && pnpm install   # re-sync host node_modules so tsc/eslint find the package
   ```
2. **MyPy alignment between venv (host) and Docker** — The pre-commit hook runs MyPy via the host's `apps/api/.venv` (Windows), not via Docker. Some packages without type stubs trigger `[import-untyped]` on one side and `unused-ignore` on the other (e.g. `striprtf`). The fix is to add the offending module to `[[tool.mypy.overrides]] module = [...]` with `ignore_missing_imports = true` in `pyproject.toml` so both runners agree.
3. **Pre-commit hook runs on the host, not in Docker** — The hook executes `ruff`, `black`, `mypy`, `pytest`, `eslint`, `tsc` and i18n parity check from the host. Any new dependency must therefore be installed on **both** sides (container for runtime, host for the hook to find it). Skipping the hook with `--no-verify` is forbidden — fix the underlying issue instead.

When working with settings-driven thresholds in tests (e.g. `mcp_user_max_servers_per_user`, `react_agent_max_iterations`), **never hardcode the threshold in the test** — read it from `settings` and compute relative values. Configs change, hard-coded thresholds silently drift the assertion.

## Native mobile shells (measured, not assumed)

LIA ships **one published app per store**, a client for a **self-hosted** LIA server: the WebView loads the **remote web origin** and the user types their server URL at first launch, because the API accepts nothing but its session cookie (`core/session_dependencies.py`, `Cookie()` only). The UI is never duplicated: the native layer only adds what the web cannot do, and where possible opens an existing web route (share → `/{lng}/share?…`, notification → `?intent=` under ADR-210).

Invariants, each backed by a measurement in `scripts/mobile-probe/`:

- **`CapacitorHttp` and `CapacitorCookies` stay disabled** (their default): they replace `window.fetch` / `document.cookie` for the whole application.
- **Push is native on BOTH platforms, and asymmetric** (ADR-246): the Push API exists in neither WebView. **Android** initialises Firebase at runtime with options its own server publishes: never bake a `google-services.json` in. **iOS cannot** (APNs authenticates against the Apple team owning the bundle id): it goes through a **wake relay** carrying an opaque handle and a fixed contentless sentence, and `PUSH_RELAY_URL` has **no default**: a default would be a privacy decision taken by a constant.
- The delivery route travels **with the token** (`relay:` prefix), never inferred from configuration: only the shell knows which route it used. **Doubt never deletes**: only "handle unreadable" and "device gone" may drop a token.
- **No cross-origin isolation in either shell**, even under COEP `require-corp`; the wake word's engine is single-threaded (ADR-329).
- **Android: `CookieManager.flush()` on pause is mandatory**: the cookie store is written on a ~30 s timer and Capacitor never flushes.
- **iOS: no Service Worker**, because `WKAppBoundDomains` is frozen at build time and cannot follow a runtime server URL; `apps/mobile/www/offline.html` replaces the ADR-146 page, loaded by Capacitor's `server.errorPath`. Do not "fix" this with per-deployment builds: that would require an Apple developer account from every self-hoster.
- **Anything the shell must fetch from a host that is not the user's server is NATIVE, not `fetch`** (`LiaShell`): the page runs on the user's own origin, and neither a relay nor a self-hosted server can enumerate every origin in a CORS policy.
- **iOS: the API must be same-site as the web app**: WebKit's ITP blocks cross-**site** credentialed cookies (`lia.` / `lia-back.` under one registrable domain is fine).
- **OAuth never runs inside the WebView** (`disallowed_useragent` on both engines): a `native_challenge` on `/auth/google/login`, a `lia://auth-callback?code=…` return, `POST /auth/native/callback` to redeem it (`domains/auth/native_handoff.py` + `oauth_router.py`). The code is bound to a verifier the shell keeps, because a **custom scheme** must be assumed intercepted. Connectors need no handoff: the user id travels in the server-side OAuth state.
- **Provider sign-in enforces the second factor**: a redirect cannot answer with JSON, so the pending token travels in an httpOnly cookie (`set_mfa_pending_cookie`) and `/auth/mfa/verify` reads it from there when the body carries none.
- **A new auth route's NAME is a security decision**: `forbid_federated_signin_in_demo` classifies by path SHAPE (`…/auth/<provider>/<login|callback>`), so `/auth/native/callback` inherits the demonstrator's refusal while `/auth/native/handoff` would have bypassed it in silence.
- **The shell's version is decoupled from LIA's**: do NOT add it to `scripts/release/version_surfaces.py`, or every LIA release would force a store submission.

`task mobile:probe:{android,ios}` re-measures both engines under the production CSP/COEP, which it **imports** from `apps/web/src/lib/csp.ts`. Run it after any Capacitor upgrade or any CSP change.

## Useful Documentation Pointers

`ADR-NNN` means `docs/architecture/ADR-NNN-*.md`. Each line says what to know before touching the area; **read the named document before designing there**: it holds the reasons, the measurements and the remaining rules. The longer text this file carried until November 2026: `git show 69e9f7ad1:CLAUDE.md`.

### Index and process

- Full documentation index: `docs/INDEX.md`
- ADR index (367 ADR files, ADR-369 latest — ADR-008 has no separate file and ADR-349 remains reserved): `docs/architecture/ADR_INDEX.md`
- Living maps (site `/maps` in six languages, French `docs/maps/`), from ONE set of data in `apps/web/src/data/maps/`: every commit keeps them true. A new ADR gets its entry and its words in the SIX languages, a new backend domain or infrastructure module is claimed by its brick, then `task docs:maps`; a changed French sentence stays STALE until translated and `--restamp`ed. `lint:docs` and `test_doc_maps_guard.py` refuse otherwise. Procedure: `docs/maps/README.md`.
- Agent creation guide: `docs/guides/GUIDE_AGENT_CREATION.md`
- Tool creation guide: `docs/guides/GUIDE_TOOL_CREATION.md`
- Testing strategy: `docs/guides/GUIDE_TESTING.md`
- CI/CD pipeline and the thin-CI doctrine (ADR-151): `docs/technical/CI_CD.md`
- Native mobile shells: `docs/guides/GUIDE_MOBILE_ANDROID.md`, `docs/guides/GUIDE_MOBILE_IOS.md` — measured platform behaviour, not assumptions
- 360° audit protocol (recurring; on "run the audit and update the public report", follow it end-to-end including the publication pipeline): `docs/audit/AUDIT_PROTOCOL.md` — public report: `docs/audit/README.md`, size metrics: `scripts/audit/measure_sloc.py`, complexity metrics: `scripts/audit/measure_cc.py`
- Dependencies (ADR-331): `task deps:watch` reads what no gate sees against the dated acceptances of `scripts/audit/dependency_watch_accepted.json` (weekly issue and every release, never a PR gate); `task deps:refresh` moves Python after its cooldown, never backwards; a security fix is a manifest floor.
- Traceability, and what the sealing proves and does not (ADR-263): `docs/technical/AI_ACT_TRACEABILITY.md`

### The agent turn, tools and confirmations

- **Execution authority** (ADR-263): a capability declares `mutation_policy`; an effect is CLAIMED before it happens and closed from an explicit result; the gate is installed on the capability at REGISTRATION (MCP adapters gate themselves inside `_arun`); an unconfirmed `confirm` ASKS (`DraftType.TOOL_CALL`). Every proof surface READS the register, nothing writes it.
- **Three registers that never add up** (ADR-263): `agent_effects` (an action), `agent_treatments` (a consultation, collected in a LIVE LIST the turn's parent publishes because a child's `ContextVar.set()` never reaches it, written in ONE shielded batch), `agent_decisions` (a turn: points at its messages with `SET NULL`, a HITL resumption merges, the outcome is derived). No purge ships: growth is instrumented (`lia_ledger_rows`, `lia_ledger_bytes`).
- **Register surfaces** (ADR-263): one renderer for the extractions, ONE component for both audiences, nothing counted client-side, bounded labels only, inference parameters captured by allowlist from `invocation_params`; `agent_integrity_events` is written where the metric increments; `token_usage_logs` is `BILLING_RETAINED` and outlives the account. `ledger_chain` (`LEDGER_CHAIN_ENABLED`, off by default) seals per ACCOUNT, asynchronously with a published lag, in two stages; nothing repairs a chain.
- **Register extractions are complete** (ADR-273): a server-side cursor (`infrastructure/database/export_stream.py`, `EFFECT_EXPORT_BATCH_ROWS`) replaces any row ceiling, the exact count is published first, `truncated: false` is CLAIMED, gzip is transport only; rows detach ONE BY ONE (`expunge_all` kills the identity map an open cursor loads into). The screen keeps its page size.
- **Several drafts in one turn** (ADR-288): reviewed one at a time (`nodes/draft_sequence.py`); the producer declares the mode (`pending_drafts_grouped`, true only for a FOR_EACH lot approved this turn); each decision banks in `confirmed_drafts`, the last answer `settle`s one ordered `confirm_batch`, a terminal cancel reports what was queued; a new turn starts clean (`draft_turn_reset()`, spread by the router).
- **Draft cards** (ADR-289): described once (`drafts/card_spec.py`: `Row`, `Note`, `Block`), drawn per surface (`to_markdown_lines`, `card_html.to_html_card`); `card_surface()` decides the surface, never a caller; `filter_for_llm_context` flattens a `lia-draft*` card to its words; `describe_execution_result` describes the result.
- **A tool failure is said, never guessed** (ADR-303): one status vocabulary whose every member is produced and read, a binary aggregate with `failed_steps` carrying the partial, one fact on one channel (the honesty directive, not gated on `DIAGNOSTICS_ENABLED`), a structural verdict in ReAct, one success predicate, and a ratchet against classifying an error by its words.
- **A pipeline failure is said, never replayed** (ADR-346): the advisory re-planner is gone; a failed step reaches the response whole, a transient one is retried in its client, a plan-caused one is caught BEFORE execution by the validator's re-plan loop; `pipeline_step_failures_total{error_code}` counts through the directive's predicate; `StepType` is held equal to the executor's dispatch.
- **Read tool data reaches the pipeline's answer** (ADR-347): the executor projects what `structured_data` carries beyond the registry items (`orchestration/tool_data_projection.py`), the response reads it after the summary inside the chain alone (`formatters/tool_data.py`); `keep_declared_failure` holds a connector payload's failure; a partial FOR_EACH keeps its successes.
- **ReAct tool binding** (ADR-293, `docs/technical/REACT_EXECUTION_MODE.md`): `rank_tools` orders every manifest into `tool_selection_result["global_ranking"]`; the loop binds by composition, no tool name written anywhere (detected domains, then `CATALOGUE_DOMAIN_COVERAGE_TOP_N` per family, then `REACT_TOOL_SEMANTIC_TOP_K`); the cap is a safety net. A binding unit (`ToolManifest.binding_unit`) binds whole, through its domain. The planner keeps its catalogue. Replay: `task react:selection:measure`.
- **A ReAct turn is judged on its result** (ADR-310; invariant 6 above): `task react:recovery:measure` compares a doctrine with its predecessor. A page a tool cut at its cap is not an observed gap (ADR-336 amendment): among started reads only a FAILED one reaches the recovery pass.
- **Exchange rhythm** (ADR-311): `users.exchange_rhythm` (`frequent` | `occasional`; NULL follows `REACT_CROSS_TURN_CACHE_ENABLED`) decides the three cross-turn effects together; `core/exchange_rhythm` is the ONE reader of the setting; the router publishes it into the state, so a HITL resume keeps the rhythm its turn started with.
- **Sandbox network** (ADR-298, `docs/technical/REACT_EXECUTION_MODE.md` § « Network runs »): ONE proxy, the only routed member of the `internal` network `lia-sandbox`; every declared host has one of four statuses (`connector`, `operator`, `grant`, `unknown`); a credential is a per-run token (`LIA_KEY_<CONNECTOR>`) the proxy swaps for the person's own key, never OAuth, an instance key or a secret in the container.
- **Sandbox questions** (ADR-298): an unknown host is ASKED with three answers, settled IN the loop (`nodes/react_egress_question.py`), and `interrupt()` must be re-raised through the tool-error net; a network run is claimed before the container starts (`in_turn_effects.py`); a refused proxy reload is a run that never starts; the libraries a prompt promises live in ONE table (`task sandbox:libraries:check`).
- **Long-term memory lookup** (ADR-313): ONE door, `domains/memories/search.py` (`embed_lookup`, `search_memories`), read by every caller; a routable `memory` domain with `search_memories_tool`; a failure is never « nothing remembered »; outside `PHONE_DOMAINS`.
- **E-mail to oneself** (ADR-314): `send_email_to_me_tool` has no recipient parameter and is `reversible`: the connected mailbox's own address (`get_own_address`), else LIA's relay to the VERIFIED address; a typed own address in `send_email_tool` still asks. A draft refused unattended names its stand-in (`ToolManifest.stands_in_unattended_for`).
- **Exact answers and LIA's records** (ADR-318): six read-only tools for both modes: `calculate_tool` (an `ast` tree walked, never executed), `date_time_tool`, `convert_currency_tool`, `search_journal_tool`, `get_my_activity_tool`, `find_generated_files_tool`. Dates through `core/date_contract.py`; every enforced bound is a setting stated in the wording the manifest AND the schema read.
- **Efficacy is learned from evidence, never from its own grade** (ADR-348): two axes never merged (verified result, expressed usefulness), an index only from several observations, one bounded adjustment (verify / clarify / state a limit) read by planner, ReAct and synthesis.
- **A shown item designated by what it is** (ADR-367): the analyzer says HOW (`descriptive`), ONE matcher decides WHICH over the turn-stamped registry, never the context list; several → the `reference_disambiguation` node asks, read without a model. What an answer showed is recorded (`context/shown_items.py`), a fresh lookup an act takes `[0]` of asks when it finds several (`nodes/plan_choice.py`), a new turn never resumes a checkpoint (`turn_input.fresh_run_config`).
- **When LIA asks before an MCP tool** (ADR-368): tool → server → account → instance (`infrastructure/mcp/confirmation.py`); a dedicated agent is asked once before its task (`task_requires_confirmation`); the synthesis is computed (`domains/user_mcp/behavior.py`); the chat only tightens.
- **Personal MCP catalogue** (ADR-366): a snapshot, served while it is revalidated and verified at use. The progressive dashboard is one act across requests (ADR-271 amendment 2026-10-28, `docs/technical/BRIEFING_DOMAIN.md`).
- **Truncated structured output is a refusal, never a rescue** (ADR-275): `is_output_truncated` reads the provider's verdict at all three doors, only once no complete answer exists; nothing retries it (a meeting's is permanent: `synthesis_too_long`); the document tool names the budget. `resolve_owner` reads `config.metadata.user_id`, which LangGraph never sets: pass `user_id` to the structured door.

### Models, reasoning and prompt cache

- **A prompt states what the code enforces** (ADR-284): the six proven defects and their guards; see i18n & prompts.
- **Short answers and model families** (ADR-285): a caller needing two sentences declares `none` through the seam and keeps its small budget only where the resolved profile `can_disable` (`short_answer_config`): the thinking counts inside the cap. An empty or truncated answer is a refusal, the written fallback goes out. The DeepSeek thinking family is declared ONCE (`DEEPSEEK_THINKING_PREFIXES`, read through `is_deepseek_thinking_model`, AST guard); `model_name_of_response` / `reasoning_tokens_of` live in `usage_metadata.py`.
- **Ollama, native** (ADR-267): `ChatOllama`, never the OpenAI shim; a DISCOVERED layer of `ModelCapabilitiesCache` holds what the server declares, in memory, wins over a seed row, refreshed when the ADDRESS changes; a per-model ladder; with nothing asked on a thinking model `reasoning=True` keeps the trace separated; what LIA accounts with is what it requests (`num_ctx`).
- **The context window belongs to the SLOT** (ADR-278): `llm_config_overrides.context_window`, through `get_effective_context_window_for_slot` alone; `GET /api/tags` first, `POST /api/show` as fallback; a tag nobody described gets NO profile and is named; a cloud tag is recognised by its HOST (`remote_host`) and keeps its whole window; `OLLAMA_NUM_CTX_DEFAULT_CAP` protects local VRAM; asking for nothing is not neutral.
- **Reasoning models** (ADR-245 amendment): `_create_with_dedicated_client` runs BEFORE `_prepare_provider_config`, so the protection that runs is in `create_responses_llm`; it and the filter read ONE predicate, `model_capabilities_cache.is_reasoning_model` (single-reader guard). The sampling flags are never read from the catalogue.
- **Claude request surface** (ADR-306): what each generation accepts is MEASURED and lives in ONE table, `core/claude_surface.py`; the reasoning rules, `providers/anthropic_kwargs.py`, the structured door and the admin lock read it, never a model name. `ReasoningProfile.implicit_level` reads an empty level as the depth it runs at.
- **The prompt cache is shaped and billed as the vendor measures it** (ADR-306): `providers/anthropic_payload.py` and `providers/openai_payload.py`, ONE policy each, mark the static prefix at `DYNAMIC CONTEXT`. `UsageTokens.cache_write` is the fourth count of the one reader, the tariff says its price (`cache_write_multiplier`), every pricing door takes it (`test_cache_write_reaches_every_price`). `prompt_cache_key` goes to the DECLARED families alone (a guard holds the list).
- **ReAct across turns** (ADR-308): under `REACT_CROSS_TURN_CACHE_ENABLED`, every tool bound in registration order AND the turn's context after the question (`nodes/react_turn_layout.py`), both or neither; « after the question » has one shape per provider, declared (`CONTEXT_PLACEMENT`, boot-checked); what cannot be bound falls back to relevance, counted (`react_cross_turn_cache_fallback_total{reason}`).
- **One prompt layout for every cache mechanism** (ADR-309): stable before volatile; `core/prompt_layout.split_at_marker` is the one boundary each adapter translates; a single call sends its static part as the system message (`single_call_messages`, AST-guarded); the response sends the conversation ONCE, as its messages; under the flag the loop's history drops by blocks, counted by the turn counter from the END (`get_block_windowed_messages`), never aligned on the thread's length. Owner rule: never reason on one provider, aim at the best AVERAGE.
- **Claude across turns** (ADR-362): in a tool loop the history's end is a read point; a frequent turn writes its two read points for the hour (`prompt_cache_horizon`, ONE writer), billed 2x on every path (`anthropic_hooks`); an earlier turn's thinking returns to its model only where kept unbound (`anthropic_thinking`, `ClaudeSurface.preserves_prior_turn_thinking`); the loop's call carries the node metrics (`enrich_config_with_node_metadata`).
- **An image model declares its offer** (ADR-305, `docs/technical/IMAGE_GENERATION.md`): a FAMILY (`image_generation/families.py`) declares what a model accepts; every surface reads it, and a model no family declares cannot be priced, offered, selected or run. One client per provider under `providers/`, the model that runs is the model that is priced. A preference is an intent, mapped at run time by ONE resolver (`preferences.py`). `ImageGenerationError` carries facts, never wording.
- **An image prompt may be rewritten, never distorted** (ADR-315): the person's opt-in, the operator's withdrawal (`IMAGE_PROMPT_ENHANCEMENT_ENABLED`), a slot of its own; every failed check sends the ORIGINAL prompt; generations only; the gallery keeps the person's words.

### Voice

- **The phone as a channel** (ADR-290): LIA calls the PERSON on a number VERIFIED by a spoken code (`TelephonyIdentityService.verified_number`, the ONE seam the no-card exception rests on; the third-party tool refuses that number), through the same vendor agent under a per-call `conversation_config_override` rendered server-side (`telephony/mandates.py`, one mandate per `CallKind`, boot-asserted). `call_me_tool` is `reversible`.
- **Phone transcript** (ADR-290): it returns as the person's OWN turn (`infrastructure/scheduler/phone_relay_runner.py`, `StreamRequest.spoken_by_person`), claimed `RELAYING` before the turn, settled by conditional update; ten `RelayOutcome`s tell « nobody picked up » and « the line failed » from « someone else answered »; the call carries the chat's context under a token budget (`self_call_context.py`).
- **Phone lookups** (ADR-290, `TELEPHONY_LIVE_TOOLS_ENABLED`): read-only by construction: a RULE over the catalogue (`derive_live_tool_specs`, `shared/phone_domains.PHONE_DOMAINS`), results reduced to what a voice can say (`voice_projection.py`), every euro under one run id (`telephony/spend.phone_call_run_id`), switches in `users.phone_disabled_domains`. Vendor tools attach to the AGENT for the owner's call alone, detached when it ends and again before any stranger is dialled. What the agent SOUNDS like is the portal's, never a setting.
- **Live voice mode** (ADR-299, `docs/technical/LIVE_MODE.md`): speech-to-speech on the PERSON's own provider key (connector category `live`). The voice model owns the conversation and delegates every data or action request through ONE `NON_BLOCKING` function, `send_to_lia`, an ordinary `POST /chat/stream` with the person's cookie: the turn runs in the graph. The voice holds no tool, credential or row of its own, and the mode is not bridled.
- **Live session rules** (ADR-299): a used single-use credential cannot reconnect (`POST /live/sessions/{id}/credential`); a voice name is validated against the vendored list, never by the provider; one session per account (`live:session`), `live:active` caps the instance; a voice-only exchange is archived at `turnComplete` as two `live_turn` rows; ONE `live_session_summary` card sums the delegated runs. Web: `LiveSessionController`, `useLiveHoldsMicrophone`, CSP `LIVE_PROVIDER_CONNECT_SRC`.
- **Live providers: one seam, two wires** (ADR-300): a provider DECLARES its wire and the seam never branches on its name: `connection` (`token` | `offer`), `delegation_wire` (`tool` | `native`), `billing` (`tariff` | `vendor`). The transport derives what the seam needs (`transports/openai-webrtc.ts`). The `live` category is ADDITIVE (`CONNECTOR_ADDITIVE_CATEGORIES`), sessions on the account's choice (`users.live_preferences.provider`).
- **Live settings and cost** (ADR-300): a connector remembers every model's settings (`live/model_settings.py`); a `tariff` model is offered only when the table declares it (`domains/live/pricing.py`, `model_unpriced`); the cost is SHOWN, never recorded (`lib/live/meter.ts`, `LiveRates`); the PCM player is ONE AudioWorklet reading a queue; Gemini's `enableAffectiveDialog` is measured OUT; the two voices are exclusive.
- **Direct sessions and ElevenLabs Agents** (ADR-300): a DIRECT session holds LIA's READ-ONLY tools through ONE door (`POST /live/sessions/{id}/tools`, `tool_door.py`, `LIVE_DIRECT_TOOL_CALLS_MAX`) where `LiveModelCapabilities.direct_tools` says so. ElevenLabs: the person's AGENT stands where a model stands, `VendorBilling` is shown and recorded nowhere, a refused creation cancels its siblings (`TaskGroup`, never `gather`). The tariff table knows the SIMPLE API's grid only.
- **Voice sessions: one policy per mode, whichever the line** (ADR-301): `delegated` « Live » (every request a chat turn) or `direct` « Live direct » (the voice reads, acts on nothing, the words relayed at the end as the person's own turn). ONE closing (`infrastructure/scheduler/voice_session_closing.close_voice_session`); shared code in `domains/voice_sessions/`, runners in `infrastructure/scheduler/`; `POST /live/sessions/{id}/end` calls no model, and a voice runner holds no session across the turn.
- **Phone delegation** (ADR-301, `docs/technical/TELEPHONY.md`): `voice_delegation.delegate` mirrors the browser bridge: the newest request wins (a Redis marker), a question LIA asked IS the result, the next request resumes that run (`original_run_id`). Live needs a public callback host (`telephony/callback.py`); a refused delegation tool degrades the call to DIRECT and says so; a call nobody answered has no mode; the lookup admission is one sequence (`voice_lookup.serve_voice_lookup`).
- **Live standby and wake word** (ADR-329): asleep, no provider connection and nothing billed, only the person ends it; a wake opens a NEW connection; one trained phrase per interface language on ONNX Runtime Web in a worker, model files held to their manifest (`lib/audio/wake-word/`); training: `docs/technical/WAKE_WORD_TRAINING.md`.
- **Fish Audio** (ADR-345): a heard sentence goes through ONE door (`voice/spoken.py`), billed once in the unit of the engine that spoke; one Redis allowance per vendor account (`voice/provider_capacity.py`); the remote dictation engine is the `voice_transcription` slot's (`core/remote_stt.py`); a clone needs an attestation filed in the audit log first.

### The person's records

- **Workboard** (ADR-276, `docs/technical/WORKBOARD.md`): ONE row per ticket shared by owner and holder; a NULL assignee means « the owner holds it » and the FK is `SET NULL`, the account purge releasing explicitly (`build_workboard_release`); cross-account delegation is refused from both sides; the execution mode is a column of the ROW, read at the next run; a ticket's spend is the ACCOUNT's (`total_*` adds `last_run_*` in the settle's transaction).
- **Ticket runs and questions** (ADR-276): a run ASKS instead of refusing: the ticket carries the draft in « à confirmer », the owner's last note classifies the answer without a model, the replay runs in the graph under a digest lock (`nodes/draft_preapproval.py`). The pending-question probe reads the Redis record the chat routes on, never the checkpoint. A question goes to the HOLDER alone, under the holder's flag; `assigned` is the one event no flag filters.
- **Workboard UI** (ADR-276): every list is `GlyphSelect`; below `lg` nothing drags; the priority is the card's EDGE, never a badge; `GET /workboard/summary` figures are aggregates over the WHOLE set, counts over what the account SEES, sums over what it OWNS.
- **Kept answers** (ADR-282, `docs/technical/BOOKMARKS.md`): a bookmark is a COPY: `message_id` / `conversation_id` are `SET NULL` and serve the toggle alone, so a reset never touches it; the request is resolved server-side under `visible_only`; keeping twice answers 200 (partial unique index); `BOOKMARKS_MAX_PER_USER` is published; `PlatformCapability.BOOKMARKS` guards the `POST` alone.
- **Kept answers in their space** (ADR-291): projected into a per-account space found by ROLE (`rag_spaces.kind = 'bookmarks'`); the bookmark stays the record, the state is derived (`bookmarks/projection.py`); a projection is claimed first (`claim_for_projection`) and gates leave honest states (`disabled`, `deferred`, `error`). HTML becomes text through `html_to_markdown` alone. A managed document refuses a move or a delete by ONE table (`MANAGED_DOCUMENT_CODES`); a space managed by role is not deletable by hand.
- **The portrait** (ADR-343, ADR-292, `docs/technical/JOURNALS.md`): nine records read whole under one share of the slot's window (`JOURNAL_CONSOLIDATION_SOURCES_WINDOW_FRACTION`), a cut stated; an ANALYSIS on seven facets, never an inventory; no model reviews the readings, what refuses invention is structural (`admit_portrait_claims`); a journal change marks it STALE, an erasure withdraws its claims (`withdraw_journal_supports`). Measure: `task journals:portrait:measure`.
- **Portrait sources** (ADR-292): `journals` imports no source domain: they are OFFERED through `domains/shared/portrait_sources.py`, the boot installs them and refuses an incomplete registry; a reader answers `used | empty | disabled | unavailable` with an EXACT total and never raises; the provenance is persisted with the portrait (`users.journal_portrait_sources`).
- **Relationship debrief** (ADR-269): the evidence assembly lives in `domains/relations/overview`, frozen by a golden file, shared with `get_person_overview_tool`; built lazily at card open, NEVER by a scheduler, once per the reader's local day, three legitimate rebuilds; no evidence settles `empty`, a failure keeps the previous text. In the chat it JOINS the peer block with the opposite directive (dated, facts go to the tools); an ambiguous name injects nothing.
- **Meetings** (ADR-258, ADR-259, `docs/technical/MEETINGS.md`): the meeting row is the durable job, two audio sources behind one interface, a `TemplateRef` rather than a row, ONE precedence for the format, a `transcript` section rewritten part by part, a reformat never a « copy ».
- **Generated files** (ADR-279): `origin` names the producer on a closed vocabulary, undeclared is never generated; the reset removes `origins={upload}` only; `capability_dependencies(ATTACHMENTS)` sits on `POST /attachments/upload` alone; an unreadable deadline reads as PAST; `reason` is `expired | conversation_reset | user_deleted`.
- **Keeping a file** (ADR-319): a kept file has no deadline (`attachments.expires_at IS NULL`), a CHECK keeps every upload's; two ceilings (`GENERATED_ASSETS_KEEP_MAX_FILES`, `GENERATED_ASSETS_KEEP_MAX_MB`) under ONE per-account advisory lock (`infrastructure/database/owner_lock.py`); history restates each card from its row (`attachments/card_lifetimes.py`).
- **Sharing an image** (ADR-316): the click is the confirmation; two daily quotas under an advisory lock; a copy, a gallery row and a ledger row in one transaction. A third party's words in someone else's chat are quoted LITERALLY (`domains/shared/markdown_literal`), by numeric character references, never backslashes.
- **Sending by e-mail** (ADR-321): ONE outgoing MIME (`infrastructure/email/outgoing.py`), `send_email(…, attachments)` on the three clients, Gmail's upload URI for a file; each road publishes its limit (`OUTGOING_FILE_MAX_BYTES`); the click is the confirmation; committed before the send; `PlatformCapability.EMAIL_SHARE`.
- **A document attached from a space** (ADR-295, `docs/technical/ATTACHMENTS_INTEGRATION.md`): a COPY (`attachments/knowledge_copy.py`), paused space or not, from `ready` documents alone (`GET /rag-spaces/documents`, mounted BEFORE `/{space_id}`); a cut is stated to the model; hint labels through `normalize_language`.
- **Reading a mail attachment** (ADR-296, `docs/technical/REACT_EXECUTION_MODE.md`): `download_attachment` on the three clients, ONE selection (`clients/email_attachments.select_attachment`); a Gmail handle EXPIRES between two reads, so resolve by name and pass both; magic bytes decide the route (`agents/emails/attachment_content.py`), text or the `vision_analysis` slot.
- **Drive folders** (ADR-297): a linked folder is a TREE, walked by ONE bounded walk (`rag_spaces/drive_walk.py`) shared by the sync and the preflight, which states the exact figures past `rag_drive_sync_confirm_threshold`; the walked set travels with the source (`rag_drive_sources.folder_ids`); a nested link is refused.
- **A personal radio** (ADR-324, `docs/technical/RADIO.md`): a NEWSROOM for the instance (no model, reads only while someone listens) and an ANTENNA per listener; a deterministic grid decides what airs, the `radio_writer` / `radio_analyst` / `radio_verifier` slots only write, every line cites a fact and a deterministic editor repairs, drops or refuses. The music is the PLAYER's; a segment is the voice alone; nothing the radio does is an action.
- **Radio state and money** (ADR-324): every euro on the session's run row, shown live; `RADIO_BUDGET_24H_EUR` is asked at the start, before every production and translation; the instance cap is taken by JOINING the live set, then counting; an end the core decides is WRITTEN before it is published (`session.ended_for`); what was heard is filed once the player passes it; `RadioNewsroomStalled` reads a stamp written only by a completed tick.

### Proactivity and schedules

- **Learned habits** (ADR-214 amendment c, runbook `docs/runbooks/alerts/RecurrenceLedgerSilent.md`): every consumer goes through `habits/consumption.py::load_consumable_profile`, the window key has one producer (`window_keys.window_habit_key`), the nightly job owns the lifecycle (`recurrence_sync.sync_recurring_habits`), the learning gate closes every door (`learning_gate.read_learning_gate`, fail-closed), the decision declares its offer (`HeartbeatDecision.habit_offered`), the consultation register is fed around the whole run (`_serve_user`).
- **Anticipated moments** (ADR-281): a `proactive_moments` row is one instant for one account, unique on `(user_id, kind, source_ref)`, claimed with an owner token, REVALIDATED before it is served, under the full eligibility checker: an instant does not defer. The question is ASKED, never the evaluation. Each kind switches off alone.
- **Mail watches** (ADR-281): the wake serves `mail_match` watches from the Gmail delta, BEFORE the pre-filter's verdict: it advances `next_trigger_at` and NEVER runs the routine, the executor stays the sole judge, and it arms past the published search-cache TTL. A finished routine CLOSES (`is_enabled = false`, `status = completed`) through its `SeriesEnd`, no second authority. Two readings of « does this mail match » are pinned by an agreement test.
- **The heartbeat has no daily quota** (ADR-328): `EligibilityChecker`'s per-day bounds are both or neither, and the heartbeat's checker has none: ticks, push wakes and moments are bounded by the window and the cooldowns alone.
- **Proactive discussions** (ADR-358, ADR-359, ADR-360, `docs/technical/PROACTIVE_DISCUSSIONS.md`): the prompt ceiling is the slot's; a rebuild covers every admitted fact pass after pass; a run reserves the smaller of its ceiling and the day's room; every bound is a `DISCUSSION_*` setting; a run records why it ended, one that never starts names why (`discussion_run_not_started`); an unanswered opening holds the next one back for a bounded time.
- **Recurrence** (ADR-268): ONE engine, `src/core/recurrence`, importing no domain and no configuration; `anchor_date` is mandatory; caps are INJECTED per consumer (a routine's through `scheduled_actions/recurrence_limits`, published and enforced on what is WRITTEN); `rearm_after` answers `None` for a consumed occurrence (a reminder with no future is deleted), so no branch reads « does this repeat ». `POST /reminders` refuses `trigger_at` with `recurrence`. A timezone change moves routines AND reminders (`infrastructure/scheduler/timezone_propagation.py`).
- **Dictating a schedule** (ADR-268): what the model may say is declared once (`agents/registry/recurrence_parameters.py`, flat parameters) and translated once (`core/recurrence/dictation.py`); the oracle is the INSTANTS (`task recurrence:corpus:measure`); a stored selector is a read selector (`SELECTORS_READ_BY`); `RecurrenceError` is raised, never Pydantic's `ValidationError`.
- **Routine history** (ADR-265): the cards sort at the DISPLAY; one row per tick in `scheduled_action_runs`, written at the result inside a savepoint, never a gate; `GET /scheduled-actions/week` is declared BEFORE `/{action_id}`; `_next_fire` is the only reader of the cron in the helpers.
- **One clock per routine** (ADR-322): a `time` routine has a `RecurrenceSpec`, a `condition` routine a condition and no recurrence: ONE rule (`schemas.trigger_mode_refusal`) and `ck_scheduled_actions_one_clock`. The system's clock is declared in `scheduled_actions/trigger.py` (`CONDITION_CHECKS`, `TriggerPlan`); a fact is new when its hashed KEY was never seen (`condition_ledger.py`); an unmet check writes no run row.
- **Silent-loops programme** (ADR-260, ADR-261, ADR-262), off by default where it adds a subsystem: a Redis key family declares its scope; a processed push queues a wake served under the FULL eligibility; a space follows a Gmail LABEL, never the mailbox.

### Platform, accounts and surfaces

- **One switch per capability** (ADR-280): `PlatformCapability` is partitioned against a list a person maintains, each spec checked. A switch removes the CAPABILITY, never the RECORD: the guard sits on the router where the router is the ability, at the ACT where it is a background act, read through `is_capability_enabled` AT CALL TIME. A map node says what it counts. `enforced_on_routes` and the service gate are separate fields.
- **Worker anatomy** (ADR-283): the supervisor imports nothing from `src` (`python -m src.serve`, AST guard); every worker publishes what it holds (`lia_worker_memory_bytes{kind}`, alert `ApiWorkerMemoryHigh`); see Size & structure.
- **No transaction across a network call** (ADR-304): see Concurrency & async. Also: the Drive push drain is bounded and resumable, wakes are served one at a time (`PushWakeSweepStalled`), WebSockets run on uvicorn's sans-I/O implementation.
- **Keyless connectors belong to the instance** (ADR-307): ONE predicate (`connectors/keyless.py`), no per-account row, what `ConnectorService.is_connector_active` answers; Google Weather is the DEFAULT, the person's own provider wins (`provider_resolver._instance_default`); `APIKeyActivationRequest` refuses a keyless type; a withheld one answers `CONFIGURATION_ERROR`.
- **Broadcasts** (ADR-312): `admin_broadcasts.audience` + `admin_broadcast_recipients`, the audience RESOLVED before the row is written, a selection addressing no active account refused.
- **Logs carry facts, never words** (ADR-317, `docs/technical/PII_LOGGING_SECURITY.md`): see Observability & honesty.
- **The chat follows the server without a reload** (ADR-320): `archive_message`, the ONE door, arms a signal that leaves on the session's `after_commit` (`conversations/sync_signal.py`); the person's channel has one name (`infrastructure/cache/user_channel.py`); the thread is MERGED, never replaced (`lib/chat-merge.ts`, `lib/chat-sync.ts`); a notification never builds its own bubble.
- **One declared language** (ADR-323): see i18n & prompts. Left on purpose and listed there: what only the model reads and is not yet in technical English.
- **Landing media** (ADR-330): blog illustrations are pre-generated (`scripts/build-article-images.mjs`), never the image optimizer; the video is the OPERATOR's (`LANDING_MEDIA_BASE_URL`); ONE `<video>` element for the visit (`LandingVideoHost`, `lib/landing/player-routes.ts`).
- **Deterministic cards** (ADR-332, `docs/technical/HTML_CARDS.md`): a received fact is shown whole and never invented, the model reads a versioned semantic view, an action belongs to the message that showed its source, a browser map is admitted, budgeted and recorded.
- **Linked signals** (ADR-333): log → trace → logs/metrics → exemplar links, the observability stack scraped on keep-lists, every dashboard on 7 days (logs/traces 4 h) behind one menu, guarded.
- **Diagnosis evidence** (ADR-266): the evidence pack is collected by the PUMP, per `EvidenceRecipe` (boot assert + CI test), fail-open source by source, a blind source named; runbooks are staged by `prepare-prod.ps1`.
- **Mailbox drafts** (ADR-344): kept, edited and trashed with no confirmation (`reversible`), sent only through `DraftType.MAILBOX_DRAFT_SEND`, whose executor refuses a draft changed since it was shown.
- **Password reset** (ADR-363): ONE decision (`auth/password_reset_policy.decide_reset`) at the request AND at the use; one budget per account; a link is bound to the stored hash, so a changed password retires it; a rate-limit `key_prefix` carries no address or id. Administrator's way back: `python -m scripts.data.set_password`.
- **Turnstile** (ADR-364): `auth/turnstile_gate.py` guards the password doors after the per-IP limiter; with no usable answer from Cloudflare only the SIGN-IN proceeds, judged by the server's own view; off until the operator's widget.
- **The person's own hands** (ADR-369, `docs/technical/WORKBENCH.md`): « Tools » acts with no model and no register row (`NOT_A_CAPABILITY_READ`); one door, one refusal seam, a provider descriptor; what a client gains reaches the assistant's tools in the same lot.
- **Settings dock** (ADR-277): WHAT is pinned is the ACCOUNT's (`users.settings_shortcuts`, the list riding the profile), WHERE the dock sits the DEVICE's (`lia_shortcuts_dock_prefs`); the backend keeps the tokens' SHAPE, the vocabulary is `SettingsSectionToken`; ONE floating mechanic, `useFloatingDrag`.
- **Document craft** (ADR-274): the renderer owns the form, the model the meaning: it says what a thing IS, the renderer draws it natively; nothing overflows by construction (`fit.py`, a full-width glyph is one em); every incoherence is repaired; ONE predicate switches contents, numbering and part breaks. Corpus: `task documents:corpus:measure`.
- **The expressive face** (ADR-264, ADR-294): the moving hold is a PIXEL budget; couplings are ABSOLUTE contributions, never `+=`; a `SketchClock` the host keeps counts resting time; speech is generated (`rig/speech.ts`), never rewound; every tape module shares `rig/choreo.ts`.
