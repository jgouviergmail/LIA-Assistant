# AGENTS.md

<!-- GENERATED FILE — do not edit.
     Source: CLAUDE.md. Regenerate with `task docs:sync-agents`.
     Verified by `task lint:docs`. -->

This file provides guidance to coding agents working in this repository. It is a
generated mirror of [CLAUDE.md](CLAUDE.md), which is the single source: the two
must never be edited separately.

Always check the available plugins/skills at session start and use the ones
relevant to the current task.

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
task test:backend:unit:coverage    # The CI command verbatim, including the 67% floor
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
task test:frontend:coverage # + aggregate global and scoped-glob thresholds enforced by CI
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
task lint:docs              # documentation drift: broken links, stale code paths,
                            # orphans, quoted facts vs their sources, AGENTS.md mirror
```

**Documentation is gated on what it STATES, not only on how it links.**
`task lint:docs` runs three instruments (all with `--fix`-style companions where
repair is mechanical):

| Instrument | Answers | Repair |
|---|---|---|
| `scripts/audit/doc_audit.py` | Do the links resolve? Are the code paths real? Is any living document unreachable? | by hand |
| `scripts/audit/doc_facts.py` | Does a quoted version or threshold equal its source? | `task docs:fix-facts` |
| `scripts/audit/agents_mirror.py` | Is `AGENTS.md` the current render of `CLAUDE.md`? | `task docs:sync-agents` |

`lint:docs` decides existence from the **git index**, so its verdict matches a
fresh clone: a file you moved but have not staged is invisible to it, and the
links pointing at its new home read as broken. That is correct and deliberate.
When those findings are the ones you just created, `task lint:docs:preview`
re-runs the same audit over *tracked files plus what `git add -A` would stage* —
the answer you will get after committing. Never "fix" a finding the preview
clears; stage instead.

Three rules follow, and they are not stylistic:

1. **Never restate a value the code owns.** The coverage floor, a pinned
   version, a derived count — quote it and `doc_facts` will hold you to it, or
   point at the source instead. Measured 2026-08-27: six documents stated six
   different wrong coverage floors while every gate was green.
2. **A document may choose its precision, not be precise and wrong.**
   `Next.js 16` and `Next.js 16.2.11` both pass; `LangGraph 1.0` against a
   pinned `1.2.11` fails. When you mean the generation, write `1.x`.
3. **`AGENTS.md` is generated — never edit it.** Edit `CLAUDE.md`, then run
   `task docs:sync-agents`. Kept by hand it had silently become a strict subset
   missing all of Systemic Rules.

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

### Release surfaces

The version lives in ~25 places (6 manifests, 18 guide stamps, README, GETTING_STARTED)
and three public counts are derived from their source (ADR files, latest ADR number,
CHANGELOG entries). All of it is mechanical, so none of it belongs in a checklist:

```bash
task release:check                # report any version/count drift (read-only)
task release:bump -- 1.32.0       # write every mechanical surface + realign the counts
task release:sync-counts          # realign the ADR/CHANGELOG counts alone
```

### Model capability catalogue (ADR-244)

`llm_models` is the runtime authority on what a model can do, and its capability
columns are curated from two vendored public registries — never from the network on
an execution path:

```bash
task llm:catalogue:fetch          # refresh the vendored snapshot (network; review the diff)
task llm:catalogue:sync           # print the reviewable diff + the retirement report (read-only)
```

`llm_models.capability_provenance` says who filled the capabilities: `declared` (the
column defaults nobody curated — `get_effective_context_window` refuses to trust it),
`imported` (corroborated by the snapshot) or `verified` (a human edited a
registry-owned capability through `LLMModelService.update`). **It is row-level but its
evidence is field-level**: `imported` vouches for `sync_diff.CORRECTABLE_FIELDS` and
nothing else, so a reader of any other column (`supports_strict_mode`, the sampling
flags) must require `verified`. **Prices, reasoning
metadata, streaming, the sampling flags and `kind` are never imported** — each
exclusion is a measured decision asserted by a test in
`apps/api/tests/unit/infrastructure/llm/catalogue/`. Deactivating a model requires an
uncontradicted past deprecation date **and** no reference: `is_retiring` (warn) and
`is_retired` (may deactivate) are two predicates, one implementation each, in
`catalogue/field_mapping.py`.

**The real per-agent configuration lives in `llm_config_overrides`, in the database,
and deployments do not run the same models.** Before deploying a catalogue change, run
`task llm:catalogue:preflight` against the target instance: read-only, it reports which
models that instance would deactivate, which it keeps because it references them, which
configured models fail their slot's declared capabilities, and whether any `verified`
row would lose strict structured output. A unit test must read `LLM_DEFAULTS`, never a
database — two of them hard-coded a model name until ADR-244 and broke on the retarget.

### Reasoning configuration (ADR-245)

Asking a model to think has **one stored shape for every provider** —
`ReasoningIntent(level, budget_tokens, exclude_from_output)`, in
`core/reasoning_intent.py`. The four widget-dispatched shapes it replaced are
still READ (`intent_from_legacy`, shared by the migration, the reference seeds and the
golden test) so no deployment needs a flag day, but nothing writes them.

- **The ladder is ordinal and provider-independent**: `provider_default < none <
  minimal < low < medium < high < xhigh < max`. `provider_default` is the identity —
  it produces no kwarg on any family — never a depth.
- **What a model accepts is a derived `ReasoningProfile`**, not a catalogue column:
  `resolve_reasoning_profile(provider, model, model_levels=...)`
  (`llm/reasoning/profiles.py`). A new provider is one rule entry plus
  one renderer in `translate.py`; never a branch inside an existing family.
- **`kwargs_for(provider, model, stored)` is the ONLY seam** an adapter may call. It
  never raises: an unknown model resolves to no family and produces no kwarg.
- **Runtime coerces, the write path rejects.** Coercion ties break **upward**, `none`
  is **never** a coercion target, and **`can_disable` — not ladder membership** —
  governs whether reasoning can be switched off (a catalogue row narrows the DEPTHS a
  model offers, never its off switch; reading the ladder there silently ENABLES
  reasoning on an explicit `none`). Every coercion is counted and logged
  (`llm_reasoning_coerced_total`).
- **The UI is offered exactly what the API accepts**: `/llm-config/metadata` publishes
  the resolved profile (`LLMConfigService._reasoning_metadata`), never the raw
  catalogue declaration. Publishing the declaration while
  enforcing the rules is how the dropdown came to offer `minimal` on a model whose API
  refuses it (ADR-184's rule, applied to reasoning).
- `llm_models.reasoning_widget` and `reasoning_budget_range` are **gone** (v1.32.0):
  demoted first, then dropped with the enum type that had no other user, because the
  admin form kept offering them for editing while nothing read them. The only catalogue
  value the resolution reads is `reasoning_enum_values` — the ladder narrowing, and it
  must speak the LADDER's vocabulary: four rows declared `off`, the narrowing
  intersection dropped it, and the resulting ladder had no off switch (only
  `can_disable` rescued it). A seed guard now refuses any level off the ladder.
- **The registries are visible where the catalogue is**: every model row shows its
  `capability_provenance`, and `GET /admin/llm/catalogue-status` reports the same
  read-only verdict as `task llm:catalogue:sync`, computed by the same code
  (`llm/catalogue/status.py`). Applying a correction stays a reviewed
  migration — no endpoint writes.
- `tests/unit/infrastructure/llm/reasoning/golden_kwargs.json` freezes what the
  pre-change builders produced. Adding a family means extending it, never editing an
  existing entry.

`scripts/release/version_surfaces.py` is the single declaration, shared by the bump
script and the CI guard `test_version_surface_consistency_guard.py` — what a release
writes is exactly what CI verifies. Guide stamps are **discovered**, so a new stamped
guide must be declared tracked or exempt (with a reason) or the build reds. What the
tool deliberately does NOT write is printed after every bump: the CHANGELOG entry, the
FAQ changelog, the README theme sentence, and `LANDING_STATS.tests` (a real
measurement, never derived).

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
```

Both modes converge on the same Response Node and stream via SSE. The `react_agent` LLM type in `LLM_TYPES_REGISTRY` is dedicated to the ReAct loop.

**Four ReAct invariants (ADR-248), each paid for by a production defect:**

1. **A message that still carries `tool_calls` is never an answer.** On a budget
   exit those calls will never run, and the text is the model narrating what it
   was about to do. `react_finalize_node` publishes an EMPTY `final_message`
   instead (the path the draft handoff already uses), so the response node
   synthesises from the tool results that did come back — and the stop reason
   travels to a versioned directive that forbids announcing future work, because
   **a turn ends when its answer is sent**. That directive is deliberately not
   gated on `DIAGNOSTICS_ENABLED`.
2. **The stop condition is ONE predicate** (`react_exit_reason`), read by the
   router to decide and by the finalize node to explain. Two copies let the loop
   stop for a reason the answer never mentions.
3. **The loop knows what the pipeline knows.** `react_setup_node` injects the
   psychological profile through `build_psychological_profile` — the same
   builder, settings and gates as the pipeline. A behavioural rule that only
   reaches the response node can reword a promise, never turn it into an action.
4. **A turn that stops mid-flight closes its own books.** Invariant 1 makes the
   ANSWER honest; it leaves the STATE broken. The `AIMessage` keeps `tool_calls`
   nobody will answer, LangGraph persists that, and every later turn on the
   thread is rejected by the provider — the conversation is bricked, not merely
   cut short (measured 2026-09-02: one budget exit, eight requests dead on
   *"No tool output found for function call …"*, the same call id each time).
   `react_finalize_node` therefore emits one explicit `ToolMessage` per
   abandoned call (`status="error"`, saying it never ran and what to do next),
   so the history is valid BY CONSTRUCTION. Two corollaries: a call with no
   `id` is skipped rather than paired by guesswork (`AIMessage` validates
   `tool_calls` at construction only, so `id: None` survives a checkpoint
   round-trip), and the turn-start repair stays the safety net for what no node
   can close — a hard kill. **That repair must purge BOTH shapes of a call**:
   `tool_calls` AND the typed block inside list-shaped `content`
   (`function_call` under `responses/v1`, `tool_use` on Anthropic), which
   langchain serializes independently. Purging one and not the other kept the
   poison and silenced the detector.
   Context blocks live in `nodes/react_context.py`, one best-effort builder each.

**Ephemeral Python (ADR-249, ReAct only).** The agent may write a short script
and run it in the SKILLS sandbox (SEC-001) when a step needs computation a model
does badly — `run_python_tool`. Three rules that are not conventions: the
manifest declares `execution_modes={"react"}` and nothing may OFFER it to a
planner that cannot run it — a planner which SEES such a tool plans an invented
dead end. Two shapes enforce that, because two kinds of reader exist (measured
2026-09-10: seven modules read the manifest list and three filter): a CATALOGUE
reader applies `manifests_for_mode`, while the initiative node builds its own
catalogue and is bounded by `is_initiative_eligible`, which refuses by
CAPABILITY ahead of every preference — a per-manifest `initiative_eligible=False`
was a memory the second ReAct-only tool would have had to repeat; `execute_source` refuses any sandbox mode other
than `container`, because the legacy path only isolates when the API runs as
root and this is code a model wrote while reading an email; and the turn's
collected data reaches the script on stdin, never re-typed into the source. The
code is admin-visible in the debug panel and nowhere else.

The iteration budget is ADR-238's domain-span value as a STARTING allowance,
extended while the loop keeps producing results (`react_progress_extension_enabled`);
`react_agent_max_iterations` and the compute timeout stay the hard bounds. A
tool result that is `success: false` or empty is not production — otherwise a
loop buys iterations with its own failures.

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

Three traps when touching state:
- Any key a node writes **must be declared in `MessagesState`** — undeclared keys are silently dropped by LangGraph (recurring trap: writing an object "mirror" of a dict field under an undeclared key; only the declared dict survives the checkpoint).
- State survives msgpack round-trips: custom objects must be stored as dicts (`to_serializable_dict`) and reconstructed on read — keep both sides in sync (see Systemic Rules, round-trip test).
- **A counter charged as `previous + spent` is a debt for the life of the thread unless the turn start resets it.** The checkpoint restores it on every turn, and a chat conversation, a routine (one thread per action) and a ticket (one thread per ticket) each live for weeks. `react_tool_seconds` was added to the state by ADR-256 and never to the router's hand-maintained reset list: one conversation accumulated 913.8 s over six days and every later ReAct turn died at iteration 1 with its tool calls abandoned — three « ko », no error (2026-09-11). What a ReAct turn starts with is now ONE declaration, `react_turn_reset()` in `utils/react_budget.py`, spread by the router and AST-guarded against every key the stop predicate reads (`test_react_turn_reset_guard.py`). Adding an accumulator means adding it there, never to a list in a node.

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

- **Python**: Black (line-length=100), Ruff, MyPy strict. Target: Python 3.14.
- **Ruff rules**: E (pycodestyle errors), W (warnings), F (pyflakes), I (isort), B (bugbear), C4 (comprehensions), UP (pyupgrade). E501 ignored (handled by Black).
- **TypeScript**: ESLint + Prettier.
- **Commits**: Conventional Commits (`feat(agents):`, `fix(auth):`, etc.)
- **Tests**: pytest with `asyncio_mode = "auto"`. Coverage threshold: 72% (ratchet: never lowered — raise the floor after coverage-improving work to lock the gains, keeping ≥2 pts margin vs measured; see GUIDE_TESTING.md). Markers: `e2e`, `integration`, `slow`, `benchmark`, `multiprocess`.
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

# Frontend coverage: aggregate global and scoped-glob thresholds (blanks
# NEXT_PUBLIC_API_URL, which the Taskfile's global `dotenv: .env` would otherwise
# inject and which measurably changes branch coverage; `thresholds.perFile` is not enabled)
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
- **Periodic jobs that share a divisor align forever.** An `IntervalTrigger` counts from scheduler start, so periods of 5, 15 and 60 minutes fire on the same second every hour — for the life of the process. Every interval job carries `jitter=jitter_seconds_for(...)` or an entry in `JITTER_EXEMPT` with the reason it must stay exact (measured 2026-09-01: six jobs in one second, each running an agent, each agent embedding — 11 provider failures out of 24 calls while a steady 4/minute passed without one). Enforced by `apps/api/tests/unit/infrastructure/startup/test_scheduler_jitter.py`. The corollary belongs to the callee: **an external call needs a shock absorber sized for the burst, not for the volume** — the shaper's window is short because a per-minute ceiling cannot see six calls in one second (ADR-254), it composes the existing `RedisRateLimiter` rather than adding a second one, and it **expires open** on both timeout and Redis failure. Our own throttle must never be the reason a request fails.
- **Two endpoints serving one screen make ONE act, not two.** When a page
  fetches from several routes in parallel and they need the same expensive
  thing, each obtaining it alone opens the person's sources twice in the same
  second — measured on the dashboard: 151 bundle builds over seven days, **44
  duplicates, 39 % of page loads**, every connector called twice, and two
  batches of consultation rows filed for one act. The seam is
  `infrastructure/utils/single_flight.py` (ADR-271): whoever asks first runs it,
  whoever asks while it runs is handed the SAME object — which is also what
  keeps the two responses from contradicting each other (ADR-185). It takes a
  FACTORY like `retry_async`, its key is the WHOLE identity (a forced refresh
  must never join an unforced build), waiters are `shield`ed (one client
  disconnecting must not cancel the work the others await), and it is
  deliberately **not a cache** — a finished run is never handed to a later
  caller. The register repairs itself for free: the shared task runs in the
  starting caller's context, so a joiner collects nothing and files no decision.
  **And it only coalesces within ONE process**: uvicorn honours
  `WEB_CONCURRENCY`, which production sets to 4, so a page load's two
  requests share a worker about one time in four (measured on production
  2026-09-07: three overlapping pairs, none joined). Checking the
  Dockerfile `CMD` for `--workers` and the compose for `replicas` is NOT
  enough to conclude a service is single-process — read the environment.
  And the cache does NOT absorb the difference: measured on production, a
  consultation row is written only on a LIVE fetch and `briefing:mails` carried
  five of them for two page loads. The other half is
  `infrastructure/utils/shared_flight.py` — one worker CLAIMS the build in
  Redis, the others wait for what it publishes (the cache it fills anyway, so
  no payload of the seam's own crosses Redis). The claim is released by its
  OWNER (compare-and-delete on a token — `SET NX` then an unconditional
  `DELETE` is the forbidden shape), waiting is BOUNDED and a waiter that times
  out builds, every failure falls back to building, and a FORCED refresh never
  waits because what a holder publishes IS the cache it asked to bypass. The
  caller composes the whole key including its declared family head: a key whose
  family only appears after a helper prepends it is a key the ADR-260 guard
  cannot read, and it caught exactly that.
  And the predicate that decides whether to redo the work asks **"has this been
  built?"**, never **"does it hold anything interesting?"** — the second cannot
  tell a cold cache from a legitimately empty day, and it was a SECOND
  implementation of a threshold another module already owned (ADR-248 pointing
  at freshness). A corollary on the cache under it: **a value with no TTL is
  never written, and is therefore invisible to every cache-only reader** — the
  reminders section sat at `0` and the prompt branch that reads it, written long
  before, could not be reached by any ordinary page load.
- **A retry needs a FACTORY, not an awaitable.** A coroutine is awaitable exactly once: a seam holding `client.acall(...)` cannot retry it — the second `await` raises instead of calling again. `retry_async` (`infrastructure/utils/retry.py`) is the functional core and `retry_with_backoff` delegates to it, so the backoff policy has one implementation. And **classify retryability structurally**: read the status code through `__cause__` (langchain re-raises every provider failure wrapped), never the message — a vendor rewording silently turns a retry into a hard failure. When a code exists it is final; the message is a fallback for when the chain carries none (`apps/api/src/infrastructure/llm/embedding_errors.py`, one classifier for every embedding caller).

### Persistence

- Never mutate a JSONB column in place (`obj.meta["k"] = v`, `obj.meta.update(...)`, or re-assigning the **same** dict object): SQLAlchemy silently skips the UPDATE. Always build a **new** dict: `obj.meta = {**(obj.meta or {}), **updates}`. `flag_modified`/`MutableDict` are intentionally absent from this codebase — new-dict reassignment is the convention. Enforced in CI by the AST guard `apps/api/tests/unit/test_jsonb_mutation_guard.py`.
- Concurrent counters use server-side atomic UPSERTs (`pg_insert ... ON CONFLICT DO UPDATE` with column arithmetic) — imitate `ChatRepository.create_or_update_token_summary`. Never SELECT → increment in Python → flush (lost updates).
- Rows consumed by schedulers use `FOR UPDATE SKIP LOCKED` + an atomic status transition in the same transaction — imitate `scheduled_actions/repository.py`.
- Every distributed lock, lease, or durable claim has a unique owner token and, where stale writers can commit, a monotonic fencing token. Acquire, renew, release, heartbeat, complete, fail, and retry are atomic and conditioned on the current owner/token. A failed heartbeat immediately aborts all later effects. `SET NX` followed by unconditional `EXPIRE`/`DELETE`, and `SKIP LOCKED` followed by work outside the claiming transaction, are forbidden. Test expiry, takeover, stale completion/failure, and stale shutdown with two independent actors.
- **A bare enum member as the RESULT of a SQL expression is bound as `NullType`.** `case((cond, MeetingStatus.FAILED), else_=MeetingStatus.STOPPED)` runs no bind processor: the member's VALUE reaches a `native_enum=False` column that stores its NAME, a `RETURNING` on that column cannot read it back, and the transaction rolls back — the row keeps its old status forever (measured 2026-09-05: one meeting re-driven every 15 minutes for two hours, `background_task_failed` with a one-line message). Carry the column's type on the literal (`literal(member, Model.column.type)` — `_status_literal` in `meetings/repository.py`) and prove every repository transition on real PostgreSQL (`tests/integration/domains/meetings/test_repository_jobs.py`): a unit test that mocks the repository never executes the statement. Enforced by the AST guard `apps/api/tests/unit/test_no_bare_enum_in_sql_case_guard.py`.
- Absence of an exception is not proof of delivery. Durable work may enter `DELIVERED` or `SUCCEEDED` only from an explicit successful result. Claim before external effects, persist attempts and errors, propagate a stable idempotency key, and test total failure, partial success, crash after effect before commit, and two-worker execution.
- **A Redis key named by a user id declares the scope of its family** in `apps/api/src/infrastructure/cache/key_families.py` (`CONVERSATION`, `USER_CACHE`, `USER_LEARNING`, `USER_RUNTIME`, `GLOBAL`). The conversation reset purges by declared family, never by pattern alone, and an undeclared family is kept and counted — the reset used to wipe the recurrence ledger, the Gmail delta anchor and the adaptive thresholds 161 times in 56 days because they were named like caches (ADR-260). Two guards fail the build otherwise: the boot assert over `core.constants` prefixes and `apps/api/tests/unit/test_redis_key_family_guard.py` over literal f-string keys. Account deletion and « Tout oublier » are the surfaces that remove learning keys; a reset never is.

### Registries & vocabulary

- The domain vocabulary is **singular** (`contact`, `email`, `event`, `file`, `task`, `place`, `route`) with `DOMAIN_REGISTRY` (`registry/domain_taxonomy.py`) as the single source of truth; `result_key` is derived there. Never create a new hand-maintained domain table or mapping — extend the registry.
- Every new registry/mapping keyed by an enum or domain gets a **boot-time completeness assert** (model: `drafts/display.py::assert_registry_completeness`, ADR-085 — the app refuses to boot on a missing entry). Silent fallbacks on unknown keys are how features die invisibly.
- Serialization pairs (`to_serializable_dict` / `reconstruct_*`) must have a **round-trip equality test over all serialized fields**. Adding a field on one side only is a recurring, silent bug (fields lost after every HITL checkpoint resume).

### i18n & prompts

- Backend user-visible strings go through the central i18n mechanisms (`core.i18n_*`, `APIMessages`, `HitlMessages`, `i18n_drafts`) — never inline French (or any language) in Python, **including fallbacks, parameter defaults, and LLM scaffolding around versioned prompts**. All 6 languages, zh included.
- Chinese has TWO canonical codes by layer: **backend canonical is `zh-CN`** (`User.language`, `SUPPORTED_LANGUAGES`, all backend i18n table keys), **frontend canonical is `zh`** (URL locales, `apps/web/locales/zh/`). Never key a backend table on `zh` (it would break the nominal path) and never do ad-hoc normalization (`language[:2]`…): route every raw locale through the single chokepoint `normalize_language` (`core/i18n.py`), which maps any variant (`zh`, `zh_CN`, `fr-FR`…) to the backend-canonical code.
- Prompt text — including few-shot examples and system scaffolding — lives in versioned files under `prompts/v1/`, loaded via `load_prompt()`. Never inline prompt fragments in `.py`.
- A prompt never carries a **tunable numeric value** in prose: it reads it from settings via a placeholder (model: `{semantic_broad_batch}` in `smart_planner_prompt.txt`, ADR-184). A number written in a prompt cannot be reconciled with the limit some other layer enforces — and the model gets blamed for obeying.

### Constraints & verdicts

- A constraint the system **enforces** must be **published** to whoever produces the value. `_manifest_to_dict` enforces this for the planner catalogue (`min`/`max` on every bounded parameter); an enforced-but-hidden bound is not a contract, it is a trap (ADR-184: `max_results` capped at 10 while the planner only ever saw `required: false`). Whatever a validator can reject, its producer must be able to read.
- What is **mechanically repairable** is repaired before validation, never reported as a defect: out-of-bounds numeric parameters are clamped in `SmartPlannerService._build_plan` (`planner/parameter_bounds.py`), same doctrine as the `for_each_max` auto-correction next to it. What cannot be repaired without inventing intent (`pattern`, `enum`, wrong types) stays a real error the validator must keep reporting.
- **A count shown to the user is a claim: it is exact, or it does not exist.** Deriving it from the length of a capped page under-reports the moment the data outgrows the page, and says nothing about what it dropped — the CRM counted rows from a 120-row window and a 200/500-row detail fetch, so a busy relationship silently under-reported and one whose only activity fell outside the window had no card at all (ADR-185). Count with an aggregate over the whole set (`GROUP BY`, `COUNT(*)`), page the ROWS only, and ship the exact total next to the page so a cap is stated rather than applied in silence.
- **Folding identity has exactly one implementation.** When a lens must query rows for one person, resolve the raw spellings from an aggregate and match them EXACTLY in SQL (`IN (...)`) — never re-express `fold_name` as `unaccent`+`lower`, which diverges on `ß` and ligatures and quietly makes SQL a second authority on who is the same person (`_spellings_for` in `relations/service.py`, ADR-185).
- **A validation verdict is not a failure.** `route_from_planner` never reads `is_valid` — a rejected plan executes unchanged and usually succeeds. Nothing may tell the user an operation was blocked on the strength of a verdict alone: the claim requires the capability to have actually produced nothing (`executed_tool_names` in `plan_blockers.py`, ADR-184). Reporting a stale verdict as a failure is the same invented diagnosis ADR-182 removed, pointing the other way.

### Tools

- Every tool carries `@track_tool_metrics` **and** `@rate_limit` (settings-driven via lambda), especially tools hitting paid external APIs (image generation, Perplexity, Brave). This is a policy, not a per-file choice.
- Tool-module imports must fail **loudly** in dev/CI: a swallowed `ImportError` silently removes an entire tool family from the registry. Never `except Exception: pass` around module imports. Enforced: `_import_tool_modules` raises outside production (counts `tool_module_import_failures_total` in prod) and the registry smoke test `tests/unit/domains/agents/tools/test_tool_registry_smoke.py` imports + invokes every registered tool in CI.
- **A tool that acts declares what it owes the user.** `mutation_policy` on the manifest
  (`read`, `draft`, `confirm`, `reversible`, `artefact`, `sandboxed` — the last three with a
  written reason) is checked at boot by `assert_mutation_policy_completeness`, which refuses
  to start on an omission. Only the `search` category is exempt: it comes from an explicit
  `get_`/`search_`/`list_` name, whereas `readonly` is the inference FALLBACK — and that is
  where `claude_server_task_tool`, `run_python_tool` and `delegate_to_sub_agent_tool` sit
  (measured 2026-09-03: 13 native tools ran unconfirmed in both execution modes, and nothing
  said whether that was a decision). A third-party MCP tool never declares it: the policy is
  DERIVED from the server's own annotations and never looser than they are (ADR-263/ADR-255).
- **A boot-time completeness assert must actually stop the boot.** `init_agent_registry`
  caught its own guards' `RuntimeError` and only logged, so three ADR-085 guards left the
  instance up with an EMPTY catalogue. Completeness failures raise
  `StartupCompletenessError` and are re-raised by the step; unrelated failures keep their
  resilience (ADR-263).
- Error payloads returned to the LLM must not embed raw tracebacks or raw user params (token waste + PII in prompts). Classify with the `ToolErrorCode` taxonomy — never by string-matching on exception messages.
- **What reaches a provider SDK is an EXACT `str`.** `HumanMessage.text` is a `TextAccessor`, a `str` subclass, and google-genai's request model validates it into an EMPTY request (`"content": {}` on the wire, `500 INTERNAL` back — measured 2026-09-05, every RAG query of every turn, while the memory path survived only because slicing yields a plain `str`). Normalise at the funnel (`GeminiRetrievalEmbeddings._exact_str`) and at the chokepoint that names the user's message, never caller by caller (ADR-266).
- **A provider branch never hands a STORED value to an SDK.** `kwargs_for(provider, model, stored)`
  is the only seam between a stored `ReasoningIntent` and a client kwarg, on EVERY branch of
  `_prepare_provider_config` — two of seven skipped it and passed the intent object itself to
  `ChatOpenAI`, which failed validation on every turn of any slot configured on Ollama or
  Perplexity (prod 2026-09-05; 29 of 58 slot defaults inherit a non-null intent). Enforced by
  `test_reasoning_seam_guard.py`: every `ProviderType` member × every level, no intent object and
  nothing non-JSON in the constructor kwargs. Two corollaries from the same incident: a value an
  operator types is normalised ONCE for every reader (`providers/ollama_urls.py` — the discovery
  tolerated a stray `/v1`, the adapter did not), and a kwarg several sources write (`extra_body`)
  is merged, never assigned. And the lesson behind the defect: **a provider is served by its
  native client, never by an OpenAI-compatible shim** — the shim cannot say what the bridge does
  not spell (Ollama: `think`, `num_ctx`, the thinking trace), and its silence reads as a model
  defect (ADR-267: twelve tokens requested, twelve tokens of thinking, an empty answer).

### Observability & honesty

- **No PII at INFO level**: names, emails, GPS coordinates, memory/journal content, message bodies. Counters and IDs at INFO; contents at DEBUG or redacted. The DB encrypts what the logs must not leak.
- An `except` handler whose body is only `pass` is forbidden (CodeQL `py/empty-except`; 193 sites purged 2026-07). Intentional best-effort swallows use `contextlib.suppress(SpecificError)` with the justification comment ABOVE the block (canonical example: metrics emission in `infrastructure/database/session.py`); when one branch must swallow while another logs, nest `with suppress(...)` inside the `try` (canonical example: `agents/api/sse_keepalive.py`). A swallow that hides a real signal gets a `logger.debug(...)` instead. Enforced in CI by the AST guard `apps/api/tests/unit/test_no_empty_except_guard.py`.
- A docstring describing behavior the code does not have **is a bug**: fix the code or the doc in the same change — never leave the contradiction (audited examples: "uses asyncio.to_thread" without to_thread, "connection pool" on a single connection, "streaming check" that loads everything in RAM).
- **A metric nobody can see is a metric nobody acts on.** Every Prometheus metric defined in code must be referenced by a Grafana panel, a recording rule or an alert. ADR-148 is the cost of ignoring this: `heartbeat_health_signals_timeout` had no metric at all, so a source failing open dropped the health signals on **46.5 % of heartbeat ticks for a week** with nothing to notice it. Enforced by the shrink-only ratchet `apps/api/tests/unit/test_metric_coverage_ratchet_guard.py` (+ `metric_coverage_baseline.json`): a newly blind metric fails the build, and a metric that becomes wired must leave the baseline (`task ratchet:metrics` — it only removes, never adds). Two traps the guard closes by construction: a labelled counter that never fired exposes **no series**, so a panel watching for a rare failure needs `... or vector(0)` and `"noValue": "0"` or it renders "No data" where an operator expects a green 0; and coverage is read from panel/rule **expressions only** — a metric named in a comment is not wired.
- Dead code is deleted, not kept "for later": an unwired subsystem with settings/i18n/tests attached costs maintenance on every change and fakes coverage. Wire it or remove it — record the decision in a short ADR.
- Optional configuration is validated as a matrix, not only in the empty and fully configured cases. Every supported Alertmanager receiver combination must start and route representative labels correctly; every dashboard query must resolve to an actual metric producer, recording rule, or documented datasource. Syntax-only validation is insufficient.

### Spend, quota and authorship

- **Where a module's model spend is recorded is DECLARED, never inferred**
  (`infrastructure/llm/spend_roads.py`). Accounting here is AMBIENT — a node
  spends through a `TrackingContext` an ancestor published, so its own file
  mentions no tracker — and reading files to answer "is this tracked?" produced
  **nine wrong conclusions in one session** (2026-09-07), in both directions.
  Four roads: `TURN` (ambient), `ACCOUNTED` (its own accounting, out of turn),
  `CALLER` (a NAMED accountant, itself checked), `INSTANCE` (no owner). The
  guard reads AST calls, refuses an omission, a stale entry, an `instance` road
  without a written reason, and a road whose module does not do what it claims
  — it caught 6 of the author's own 46 classifications.
- **A euro nobody owns still reaches a ledger.** Self-diagnosis, catalogue
  translations and the broadcast translator run for no account, so they must
  NOT touch `user_statistics` — but « no account » had been read as « no
  ledger », and 84 personality translations left no trace anywhere while the
  ledger recorded 5 976 other rows. `domains/usage_limits/instance_spend.py`
  feeds `InstanceDailyBudget`; `token_usage_logs.user_id` is `NOT NULL`, so it
  is a separate path by construction. **Recording is only half a ledger — the
  other half is asking first**, and the first version of this rule checked only
  the recording half: four of the five instance-road modules called
  `is_instance_spend_blocked` and the fifth did not, invisibly. `INSTANCE_GATE_EXEMPT`
  now makes an ungated module declare, in writing, why it cannot skip its call
  (the evaluation harness must produce a measurement or fail; a fabricated score
  an operator reads as real is worse than the spend).
- **Who pays decides who is billed** (`domains/usage_limits/cost_bearers.py`).
  `provider_api_keys` has no `user_id`, so LLM, TTS, STT, image and Maps run on
  the deployment's key; `get_api_key_credentials(user_id, …)` is per-account, so
  Perplexity, Brave, the weather connector and telephony run on the person's
  own. The guard compares the declaration to the sum `check_user_allowed`
  actually enforces, in BOTH directions: an instance family missing from it is
  a spend no ceiling sees, a user family present in it charges someone twice.
- **The authorship of a register row is declared by the CALL SITE.**
  `track_proactive_tokens` is named for the plumbing, not for the initiative:
  nothing schedules the briefing (it is reached from `GET /briefing/*` only), a
  reminder is the person's own deferred instruction (`scheduled`), and only a
  runner sweep is `proactive`. The parameter has no default — a default would
  have filed all three identically. One predicate decides it
  (`effects/source.py`), extracted from FOUR copies before the third value was
  added.
- **A capability that is not a TOOL records no consultation, by construction.**
  `record_treatment` fires from one place — the tool gate — so every surface
  that reads through direct calls was silent: the briefing (nine sources), the
  relationship debrief (seven; a reader who generated one found a neighbouring
  briefing row and took it for theirs), the heartbeat sweep (sixteen, **824
  runs over thirty days without a single row** — the case where nobody can
  reconstruct what was read). Three found one at a time is not a method, so
  `effects/user_data_readers.py` makes every out-of-turn surface declare its
  recorder module or a written reason it opens nothing, over a COMPLETE list
  (every funnel `task_type` plus every `ProactiveTask.task_type`).
  **A cache hit is not a consultation** (Redis answered; the mailbox was never
  opened), a section the person hid was never opened either, and a source that
  refused reads `failed` — never a silent success.
- **The register is OFFERED, never fetched.** `agents` imports `relations`, so
  a domain importing `agents/effects` back closes a cycle — and the coupling
  ratchet counts LOCAL imports, so hiding it in a function only hides the edge.
  `domains/shared/consultation_sink` holds the seam, the register installs
  itself into it at import, and the seam's contract is NAMED rather than
  `**Any`: a seam accepting anything lets a caller misspell a field and write a
  row with a missing column.
- **Every direct client caller is ENUMERATED, and the list is the guard**
  (`effects/direct_client_callers.py`). Four surfaces were found one at a time
  — briefing, debrief, heartbeat sweep, interest sweep — each because a person
  noticed an absence. They are one family: a module importing from
  `connectors/clients` never meets the tool gate. The import graph is complete
  by construction, so it is walked: **22 modules**, each declaring itself a
  recorder (naming its surface), not-a-read (with the reason), or a debt. The
  debt table is empty and shrink-only. Two entries were WRONG on first
  classification — `email_enricher` and `rag_spaces/mail_render` import the
  Gmail client for its PARSERS and make no call at all — which is why a reason
  must be verified rather than inferred from an import.
- **A capability reached through its CLIENT is invisible to the gate.** The
  same question — « does this surface use a tool? » — has two answers, and only
  one of them is the register's. An interest sweep queries Brave, Perplexity
  and Wikipedia through `connectors/clients/*` directly, never through the
  `@tool` layer, so the tool gate never sees them: the same Brave search is
  recorded when a person asks for it in a conversation and silent when LIA runs
  it alone (owner correction, 2026-09-07). It had been filed `NOT_A_READER` on
  the argument that it « explores PUBLIC content » — which answers *whose
  data*, while the register answers *which capability LIA used*. Recorded at
  `_try_source`, the one place every source runs.
- **A proactive notification is an ACTION, and it is CLAIMED.** The effect
  register is fed by the tool gate alone, and the proactive pipeline calls no
  tool — so `agent_effects` had never held a single `proactive` row on any
  deployment, and « Actions menées d'elle-même » was empty BY CONSTRUCTION
  whatever LIA did (reported from production, 2026-09-07). It is the sharpest
  possible version of the gap: a notification is the one act of LIA's own
  initiative a person actually experiences. `effects/out_of_turn_effects.py`
  keeps ADR-263's two stages — claimed BEFORE the push leaves, settled from
  `NotificationResult`, never from the absence of an exception — and covers
  every runner-driven sweep, heartbeat and interest alike. **One claim per
  THING SAID, not per run**: the key was `{run_id}:notification`, written for
  sweeps that speak once, and a workboard run speaks up to three times —
  measured 2026-09-09, « finished » was dispatched and its row lost as a
  replay of « started ». The seam names the `occurrence`; a surface that
  speaks once passes none and keeps its key.
- **A direct-read surface DECLARES its vocabulary; nobody transcribes it**
  (`domains/shared/consultation_surfaces.py`). Fixing the three surfaces one at
  a time produced three copies of one shape — a prefix, a section→domain table,
  a recording loop — and the drift was measured a day later: the register kept
  a THIRD, hand-typed copy of all 31 capability names; two tables written to
  bridge that gap (`HEARTBEAT_DOMAIN_OVERRIDES`, `DEBRIEF_DOMAIN_OVERRIDES`)
  were exported and read by NOBODY; the boot guard walked `get_all_tools()`
  alone, so none of the 31 was checked where every other completeness rule is;
  one surface guarded its capabilities against orphans and the other two did
  not; and the authorship was a free string typed at three call sites, checked
  by a guard that only read two other doors. Now: `TREATMENT_DOMAIN_OVERRIDES`
  MERGES the declaration, `assert_treatment_domain_completeness` checks the
  capabilities too — on a STRICTER rule, because `unknown` is itself a
  translatable key and a DECLARED capability resolving to it is a declaration
  error, not a third-party name we could not read — the authorship is a
  property of the surface, and `record_surface_consultations` is the ONE door
  (a guard refuses any other caller of the seam). The surface key is shared
  with `CONSULTATION_RECORDERS`, so the two registries cannot name two
  different sets.
- **Every token the PLATFORM pays for answers to BOTH ceilings** (ADR-272):
  what one account may consume, and what the instance may spend in a day. Only
  what a person pays with their OWN connector key is outside — `cost_bearers`
  draws that line, and it puts the whole `llm` family on `INSTANCE`, so every
  model call is in scope. Measured 2026-09-07: of the 46 sites `LLM_SPEND_ROADS`
  declares, **5 were bounded by nothing**. Three shapes produced them, and each
  is now closed by construction. **A chokepoint is the INNERMOST door, never its
  wrapper** — the registry named `get_structured_output_with_retry` while nine
  modules called `get_structured_output` directly, one of two siblings in the
  same file, and the completeness test could not see it because it only checks
  DECLARED doors. **A gate that returns early bounds nothing**: the shared guard
  short-circuited on `usage_limits_enabled`, which switched off the INSTANCE
  ceiling too — although `check_user_allowed` deliberately keeps that one
  outside the flag — and on a call having no owner, which is true of the
  account's ceiling and beside the point for the deployment's key that paid.
  **How a caller RECEIVES a refusal follows its transport; the verdict never
  does**: a request path raises (`enforce_usage_limit`, one raiser in
  `usage_limits/enforcement.py` so an instance pause names itself and says when
  it lifts), a background path degrades (`spend_blocked`, the non-raising
  sibling of `is_instance_spend_blocked`) — the reminder still fires, the
  dashboard still renders, and it logs **skipped**, never *failed*, because a
  quota refusal is not a generation failure. `test_every_spend_site_is_bounded`
  walks the registry and refuses a site that reaches no ceiling.
- **One usage guard, and `LLM_CHOKEPOINTS` names every door**
  (`infrastructure/llm/usage_guard.py`). `get_structured_output_with_retry` did
  not even accept a `user_id`, so the debrief, the telephony synthesis and the
  self-diagnosis spent where no ceiling could refuse them. Two refusals it must
  NOT make: a call with no owner is never blocked (its bound is the instance
  ledger), and `"system"` is not an account.
- **Reading a provider's usage metadata has ONE implementation**
  (`infrastructure/llm/usage_metadata.py`). It was written eight times and the
  copies disagreed: only one read Anthropic's `cache_read_input_tokens` and only
  that one clamped at zero, so seven billed cached prompts at full price and
  could compute a negative token count. `model_name_of` likewise replaced seven
  readings with three different fallbacks.

### Size & structure

- A logical file never grows: it stays under **600 logical SLOC** (tokenize + AST, no docstrings/comments/blanks — the `scripts/audit/measure_sloc.py` semantics), and pre-existing larger files are frozen at their audited size +2% in `apps/api/tests/unit/file_size_baseline.json` — they may only shrink (`task ratchet:update` lowers caps, never raises). Data modules (`core/i18n_*`, `core/config/`, `core/constants`, `domains/llm_config/constants`) are exempt. When a feature outgrows a file, extract a cohesive module — never bump the cap. Enforced in CI by the guard `apps/api/tests/unit/test_file_size_ratchet_guard.py`; doctrine in `docs/guides/GUIDE_DEVELOPPEMENT.md`.

## Key Patterns

- **Connector abstraction**: Google, Apple, Microsoft APIs share a common connector pattern with provider resolver (`src/domains/connectors/`). Only one provider active per functional category (email, calendar, contacts, tasks). When touching a provider client, check the **other providers' behavior for the same operation** (cache invalidation, reply-all semantics, multi-valued field updates) — provider asymmetries are a recurring bug source; parity is the rule.
- **HITL (Human-in-the-Loop)**: 6 approval levels (plan approval, clarification, draft critique, destructive confirm, FOR_EACH confirm, modifier review). Classified in `src/domains/agents/services/hitl_classifier.py`. Note: the plan-approval level is currently auto-approved (`approval_gate_node` is a pass-through — tool-level HITL supersedes it); do not build on plan-level interrupts without re-wiring the gate.
- **Smart Services**: QueryAnalyzerService, SmartPlannerService, SmartCatalogueService use LRU caching and pattern learning to reduce LLM token usage.
- **SSE Streaming**: Responses stream to the frontend via Server-Sent Events.
- **Observability**: 555 Prometheus metrics defined in `src/infrastructure/observability/`. Langfuse for LLM tracing.
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
  3. **Database model registration** — A new model is declared in ONE place: `import_all_models` in `src/infrastructure/database/registry.py`. `alembic/env.py` and the lifespan startup (`startup/registries.py::import_domain_models`) both CALL it — they are readers, not a second and third list, and editing them instead is the wrong fix (verified 2026-09-11)
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

When working with settings-driven thresholds in tests (e.g. `mcp_user_max_servers_per_user`, `react_agent_max_iterations`), **never hardcode the threshold in the test** — read it from `settings` and compute relative values. Configs change, hard-coded thresholds silently drift the assertion.

## Native mobile shells (measured, not assumed)

LIA ships **one published app per store**, a client for a **self-hosted** LIA
server: the WebView loads the **remote web origin** and the user types their
server URL at first launch. This is not a preference — the API accepts nothing
but its session cookie (`core/session_dependencies.py`, `Cookie()` only), so a
locally bundled build or a native REST client would have no session at all. The
UI is never duplicated; the native layer only adds what the web cannot do, and
where possible it just opens an existing web route (share → `/{lng}/share?…`,
notification → `?intent=` under ADR-210).

Invariants, each backed by a measurement in `scripts/mobile-probe/`:

- **`CapacitorHttp` and `CapacitorCookies` stay disabled** (their default). They
  replace `window.fetch` / `document.cookie` for the whole application.
- **Push is native on BOTH platforms, and asymmetric** (ADR-246). The Push API
  does not exist in either WebView. **Android** initialises Firebase at runtime
  with options its own server publishes, so a self-hoster's notifications never
  leave their own Firebase project — never bake a `google-services.json` in, that
  would tie every install to the publisher's project. **iOS cannot**: APNs
  authenticates against the Apple team owning the bundle id, and a `.p8` key
  covers the whole team, so a self-hosted server can never notify the published
  app. It goes through a **wake relay** carrying an opaque handle and a fixed
  contentless sentence. `PUSH_RELAY_URL` has **no default** — pointing it
  somewhere by default would be a privacy decision taken by a constant. The
  delivery route travels **with the token** (`relay:` prefix), never inferred
  from configuration: only the shell knows which route it used. And **doubt never
  deletes** — only "handle unreadable" and "device gone" may drop a token; an
  unreachable relay or a topic *we* mistyped must not.
- **The wake word is lost in the shell, on both platforms.** No cross-origin
  isolation, even under COEP `require-corp` (measured twice).
  `isSherpaKwsSupported()` already degrades to tap-to-speak.
- **Android: `CookieManager.flush()` on pause is mandatory.** The cookie store is
  written on a ~30 s timer and Capacitor never flushes; a restart 28 s after
  sign-in loses the session, at 60 s it survives.
- **iOS: no Service Worker**, because `WKAppBoundDomains` is a static list frozen
  at build time and cannot follow a runtime server URL. `apps/mobile/www/offline.html`
  replaces the ADR-146 page, loaded by Capacitor's `server.errorPath`. Do not
  "fix" this by adopting per-deployment builds: that would require an Apple
  developer account from every self-hoster.
- **Anything the shell must fetch from a host that is not the user's server is
  NATIVE, not `fetch`.** The page runs on the user's own origin, so such a call
  is cross-origin, and neither a relay nor an arbitrary self-hosted server can
  enumerate every origin in a CORS policy. Caught twice before shipping — the
  health probe and the relay registration — both now in `LiaShell`.
- **iOS: the API must be same-site as the web app.** WebKit's ITP blocks
  cross-**site** credentialed cookies (`lia.` / `lia-back.` under one registrable
  domain is fine; a different domain is not).
- **OAuth never runs inside the WebView** (`disallowed_useragent` on both
  engines). The API side exists: a `native_challenge` on `/auth/google/login`, a
  `lia://auth-callback?code=…` return, and `POST /auth/native/callback` to redeem
  it (`domains/auth/native_handoff.py` + `oauth_router.py`). The code is bound to
  a verifier the shell keeps, because the return is a **custom scheme** — App
  Links pin domains at build time and one app serves every self-hoster, so the
  link must be assumed intercepted. Connectors need no handoff at all: their
  callbacks are stateless, the user id travels in the server-side OAuth state.
- **Provider sign-in enforces the second factor**, since 2026-08-24. It did not
  before, so a TOTP-active account could walk past it by signing in with Google.
  A redirect cannot answer with JSON, so the pending token travels in an httpOnly
  cookie (`set_mfa_pending_cookie`) and `/auth/mfa/verify` reads it from there
  when the body carries none.
- **A new auth route's NAME is a security decision**: `forbid_federated_signin_in_demo`
  classifies by path SHAPE (`…/auth/<provider>/<login|callback>`), so
  `/auth/native/callback` inherits the demonstrator's refusal while
  `/auth/native/handoff` would have bypassed it in silence.
- **The shell's version is decoupled from LIA's** — do NOT add it to
  `scripts/release/version_surfaces.py`, or every LIA release would force a store
  submission. A LIA release ships nothing to the stores.

`task mobile:probe:{android,ios}` re-measures both engines under the production
CSP/COEP, which it **imports** from `apps/web/src/lib/csp.ts` rather than copying.
Run it after any Capacitor upgrade or any CSP change.

## Useful Documentation Pointers

- Full documentation index: `docs/INDEX.md`
- Agent creation guide: `docs/guides/GUIDE_AGENT_CREATION.md`
- Tool creation guide: `docs/guides/GUIDE_TOOL_CREATION.md`
- Testing strategy: `docs/guides/GUIDE_TESTING.md`
- The workboard — a ticket has a lifecycle, a holder and a result (ADR-276): `docs/technical/WORKBOARD.md` — ONE row per ticket shared by its owner and its holder (the board of U is « owner = U or assignee = U », so the two sides cannot disagree); **a NULL assignee means « the owner holds it » and the FK is SET NULL**, because four paths hard-delete a `users` row and only ONE runs the account purge — CASCADE would destroy the OWNER's ticket when their peer leaves, RESTRICT would block the three paths that never release, and the purge still releases EXPLICITLY since account deletion SCRUBS the users row so no FK action fires there. **No CHECK constraint spans two columns a foreign-key action can touch**: measured 2026-09-09 on a real PostgreSQL server, deleting a peer's account fires two independent FK actions on one row and the CHECK rejects whichever intermediate state comes first — no cascade ORDER is guaranteed and `CHECK` cannot be `DEFERRABLE`, so the `peer_connection_id` column went rather than the invariant (the PAIR is the connection: `peer_connections` holds one row per pair for life, and the service re-resolves it at every write). A defect invisible to 20 green model tests and to the migration replay, found at the first real INSERT followed by a `DELETE FROM users`. A page and its column counts come from the SAME filtered statement (ADR-185) and every ordering ends on the primary key. **A narrowing filter is more permissive than the decider, never less**: an `ILIKE` on the raw needle is stricter than the `fold_name` it feeds, so it discarded exactly the rows folding exists to catch (« reserver la salle » found nothing while the board held « Réserver la salle »). Cross-account delegation is refused from BOTH sides — the instruction is the owner's words, and running it unattended with the other account's tools would put that account's data in a comment the owner reads. `users` imports no workboard module: the release of what a departing account HELD is written inline in `build_workboard_release`, on `Base.metadata`, like the peers block beside it. **Every module that queries the message table outside its repository DECLARES how it reads** (`conversations/message_readers.py`, `VISIBLE_ONLY` or `WHOLE_RECORD` with a written reason, AST guard): the repository's `hidden` predicate says nothing about a module's own `select`, and the heartbeat's « last user message » took a run's synthetic question for the person's last words — and the declaration found an older defect: the journals consolidation filtered roles the repository never writes (`human`/`ai`), dead since v1.7.0 and invisible to every unit test that stubs the session. And **`context_domain` on a read tool is a promise the context system only keeps with a `RegistryItemType`, a registered `ContextTypeDefinition`, emitted `registry_updates` and a `context_key` on the manifest** (the loader validates the key at boot) — declared alone it was inert, and a confirmed deletion left the ticket « current » (`agents/workboard/context.py`). **A ticket run ASKS instead of refusing** (lot 7): the gate lets an origin that can carry a draft to the person build the confirmation the chat would show (`carrier`), the engine reads the interrupt from the chunks the stream actually emits (`hitl_interrupt_metadata` → `hitl_interrupt_complete` — measured 2026-09-09, the bare `hitl_interrupt` chunk it waited for is emitted by nothing, so a clarification settled as a SUCCESS), the ticket carries the draft in « à confirmer » (a column drawn only while it holds one), the owner's LAST note classifies the answer without a model (approve / refuse / everything else is an amendment, six languages), and the replay runs IN the graph under a digest lock (`nodes/draft_preapproval.py`): identical to what was shown → confirmed, anything else → asked again. **The pending-question probe reads the Redis record the chat routes on, never the checkpoint** — the checkpoint says « interrupted » until the next input, and read there every later ticket of the account stood aside for a question nobody could see. **A turn archives THREE rows, not two** — the person's question, the answer, and, when it stops on an interrupt, the question LIA asked instead of answering — so every archived metadata is built by a `build_*_metadata` (`agents/api/archive_metadata.py`, AST-guarded against an inline dict): the third path was written at its call site, so a ticket run's full deletion preview landed in the chat as an ordinary message AND left a row the retention sweep can never match (it needs `hidden` AND the stamp). A NOTIFICATION is not a row of the run: it carries the run's id and is meant to be READ, so a repair keyed on `run_id` alone hides ten bubbles that exist to be seen — a repair predicate names the KIND of row, never only its correlation key. **The follow flag governs LIA's questions too** (D59, owner arbitration): « waiting » and « confirming » stopped bypassing it once three later lots removed the premise that a question nobody hears is a ticket that never moves — the board draws the column, the hub badge counts it, and the heartbeat raises it WITHOUT reading the flag. A question is offered to the HOLDER alone (the side that cannot answer never gets it, subscribed or not) and gated by the HOLDER's own flag; `assigned` remains the one event no flag filters. **The execution mode is a column of the ROW** (lot 10): every ticket and every scheduled action carries its own (`execution_mode`, NOT NULL, `react` by default), editable through the ticket's whole life and read at the NEXT run — the instance setting that decided for everyone was deleted with its constant and its `.env` lines, because two authorities on one question is one too many and the one that stays is the one the person can see. **A ticket's spend is the ACCOUNT's**: the `total_*` columns are the ADDITION of `last_run_*` by column arithmetic inside the settle's transaction, read from the row the account's own tracker already writes — the ticket creates no accounting, it reads its own. **Sending the comment IS the answer** (lot 9): on a « confirming » ticket the owner's comment classifies the answer, hands the ticket back to LIA in « to do » and resets its attempt counters, with the run cap checked BEFORE the relaunch. **The HITL preview speaks ONE form vocabulary, and it is Markdown** (lot 13): it used to emit `<br/>` opening EVERY row and joining them too, so every preview began with a blank line and every field was separated by two — the chat renders Markdown with no hard-break plugin, so a LIST is what keeps one field per line without markup, and a surface that renders NEITHER (a ticket comment is escaped text) can flatten Markdown into something readable where `<br/>` was read out as typed. Flattening has ONE door too (`markdown_to_plain_text`, beside `strip_html_if_markup`), called where LIA's words are written, and it only ever SHORTENS so the comment cap still holds. The same pass found a cascade ending in `f"Draft ({type.value})"` that **9 of the 26 draft types reached** — an enum value, in English, in all six languages, on the card asking someone to approve a deletion: it became a dispatch table with a boot completeness assert (`drafts/summary_renderer.py`, ADR-085), and the punctuation between a label and its value now travels with the LABELS (unbreakable space before a French colon, full-width in Chinese) rather than being a `": "` literal publishing English punctuation in six languages. **The confirmation card has ONE author, and it is the renderer** (lot 14): the model used to WRITE the card under a prompt describing it, so its shape was whatever the model produced that day — measured 2026-09-09, fields spaced out as paragraphs and a `---` glued to a line, which `_with_markdown_hard_breaks` turned into `---<br/>`, three literal characters — and the ticket then appended the renderer's own preview to it, so the e-mail was read twice. `render_confirmation_card` (emoji and title from the display registry, body = the lot-13 preview) streams BEFORE the model's first token, then `---` between two blank lines, then the question the prompt now asks for ALONE (ADR-274's doctrine applied to HITL, and fewer tokens: the model copies no field). The fallback shows the same card, which deleted `draft_fallback_summary.py` and `_DRAFT_SUMMARIES` — a THIRD copy of the card vocabulary read by the fallback alone. On the ticket the comment is the streamed question (it CARRIES the card) plus how to answer; `WorkboardMessages.confirming` takes no `preview` any more. **The ticket's detail is seven panels of one frame** (lot 15): each section is a `Panel` with its theme-icon title and a labelled region, each on its own line at the full width (side by side, half a dialog folded the cost line in two), the cost is ONE line in the chat meter's legend (🟠 IN · 🟢 OUT · 🔵 CACHE · 🟣 GOOGLE · euros) with the run count beside the title, the last run names its VERDICT (the six of `RunOutcome`, a postponed run named and never blamed) rather than the column the ticket happens to sit in, the history's label punctuation travels with the labels (`workboard.history.separator`), the namespace's register was measured against the app's and aligned (German and Chinese « Sie »/« 您 », Spanish « tú »), and no setting carries a paragraph under it — the execution mode offers « Mode Pipeline » / « Mode ReAct », the header toggle's own words. On the card the bell and the holder lead, above the title, the menu at their right; the priority is the EDGE (and `urgent`'s ground), never a badge, its name kept `sr-only` because colour is never the only carrier. A comment re-reads the board (the answer to a confirmation moves the ticket server-side) and so does closing the panel. **The bell precedes the due date under the title, and « late » is a second line under the date, never its replacement** (lot 17); comments have no rules — the dated head of each turn on a pastel theme band separates them; there is no refresh button (the board re-reads itself); below `lg` nothing drags — a horizontal swipe changes the column, the title's door stretches over the whole card through a pseudo-element with the menu raised above it, the column and the holder are LISTS on the card between the title and the date, the holder UNDER the column (lot 19: `StatusSelect` and the shared `HolderSelect`, named with the ticket, the same patches the panel writes, drawn only where nothing drags), and they also lead the panel's settings; since lot 20 those lists are the application's own listbox through ONE `GlyphSelect` — every item wears its glyph before its name (`columnIcon`, and `partyIcon` moved to `lib/workboard/icons.tsx` so the badge and the list share one mark), because a native `<option>` holds text only, the D17 premise (a portalled list fighting the drag sensors) holds nowhere the lists are drawn, and a gesture started inside the open list stays the list's (the React tree runs through the portal — probed); « En retard » is boxed under the bell so the word starts under the date, and a late card wears a 2 px INNER frame (a `::before` on the padding box, so the priority edge stays OUTSIDE it) that breathes from the normal border colour to `destructive` on a 2.8 s cycle under `motion-safe` only — still, at full strength, for a reader who asked for less motion; every list of the workboard is that same `GlyphSelect` (lot 21: `PrioritySelect` with ranked marks in the edge's own ink, `ExecutionModeField` with the header toggle's `Workflow`/`Zap`, the three filters with an asterisk for « any », the creation form's two copied selects gone), and every person glyph wears the theme colour (`partyIcon`, `unknown` left neutral); the detail's panels are CARDS (`bg-card`, a full border, a shadow) because a muted wash at 20 % was invisible in light mode; the filters START from the URL (`?overdue=1&assignee=lia`) and the URL follows them, never the reverse while a person types. **The settings section is the board at a glance** (lot 18, `GET /workboard/summary`, `workboard/summary_queries.py` beside the repository, which is under the size cap): every figure an aggregate over its WHOLE set and a link into the narrowed board, counts over what the account SEES and sums over what it OWNS (a run is billed to the owner), the cap published and drawn as a gauge, the cost in the chat meter's vocabulary.
- Pinned settings sections in a floating dock (ADR-277, amending ADR-227, ADR-172, ADR-184, ADR-252): `docs/architecture/ADR-277-Settings-Shortcuts-Dock.md` — WHAT is pinned belongs to the ACCOUNT (`users.settings_shortcuts`, one nullable JSONB column, full-replace `PUT /users/me/settings-shortcuts`, the cap a published runtime setting), WHERE the dock sits belongs to the DEVICE (`lia_shortcuts_dock_prefs`, outside the purge registry like the eyes'); the backend keeps the tokens' SHAPE and never their list — the vocabulary is the frontend's `SettingsSectionToken`, and a section renamed since it was pinned is dropped at read time rather than shown as a dead link; the list travels with the profile through a tolerant `before` validator on `UserBase`, so `/auth/me` carries it and the dock makes NO request of its own; ONE floating mechanic (`useFloatingDrag`, the eyes' hook generalised — a press on an interactive DESCENDANT is never a drag while a surface that is itself a button, the folded dock or the eyes' restore dot, drags like any other and swallows the click a drop leaves behind; the arrows move only the surface that holds the focus; the fold button sits above the first shortcut; unfolded from the lower half the capsule grows UPWARD by a CSS `bottom` pinned to the button's foot, the stored spot untouched, the direction decided at unfold time and dropped by a drag); and the picker lists the shell's own model under `useSettingsAvailability`, extracted from the settings page, so it cannot offer a section the shell would not show
- Meeting recording & structured minutes (ADR-258), minutes template library, automatic selection and reformatting (ADR-259): `docs/technical/MEETINGS.md` — the meeting row is the durable job, two audio sources behind one interface, a `TemplateRef` rather than a row, ONE precedence for the format, a `transcript` section rewritten part by part, and a reformat that is never a « copy »
- Learned habits × proactive notifications, audited by execution (ADR-214 amendment c, amending ADR-280 and ADR-281; runbook `docs/runbooks/alerts/RecurrenceLedgerSilent.md`): `docs/architecture/ADR-214-Habitudes-Utilisateur-Apprentissage-Deterministe.md` — every finding carries a simulation on docker dev, and seven were structural. **A row's status must reach every consumer**: the heartbeat block, the tick scoring and the ambient block read the PROFILE while the panel edits the mirror rows, so a blocked window kept steering ticks — one consumption predicate now (`habits/consumption.py::load_consumable_profile`), and the window key has one producer (`window_keys.window_habit_key`). **A learned thing has a lifecycle owned by the nightly job**, never by the chat suggestion (`recurrence_sync.sync_recurring_habits`: promote, refresh, keep, DEMOTE — active rows only, never on doubt; `offer_dates` preserved, the stop-rule mute lifted on the next occurrence). **The learning gate closes every door** (`learning_gate.read_learning_gate`, fail-closed): the ledger write, the initiative detector and the seed, and the ledger follows `HABITS_ENABLED` plus the `habits` capability switch read AT THE ACT — `habits` and `heartbeat` left ADR-280's router-guarded family for the service-enforced one, because the routes are the ARCHIVE. **The decision DECLARES its offer** (`HeartbeatDecision.habit_offered`, rule 24): the offer budget used to hang on the `sources_used` label the model picked. **The offer has an object**: the analyzer's `immediate_intent` is a bounded histogram INSIDE the ledger payload (`recurrence_store.record_intent`/`dominant_intent`), never part of the key — composing it would fragment every ledger — and `usual_intent` reaches the row, the prompt and the panel through the closed `IMMEDIATE_INTENTS` vocabulary. **The consultation register is fed around the whole run** (`_serve_user`), not around one step: the aggregator reads in `select_target`, the collector opened in `generate_content` — 824 runs, zero rows. Also: the availability probes are one complete table (`source_availability.py`), the decision reads the person's clock (`prompts.message_clock`), last-seen counts a presence ping (`activity_probe.fetch_last_seen_at`), presence is ON by default, a wake bypasses the rhythm but stands aside for a meeting, the agenda verdict carries `next_start` so the rhythm never hides an appointment, the tick scoring lives in `habits/tick_scoring.py` with one `TickSurface` per sweep pinned to its checker (the interest sweep applies both gates too), and a fast job's lock is sized by `scheduler_lock.ttl_for_interval` — the wake sweep skipped every other tick under the default TTL.
- Anticipated moments, and a watch served to the minute (ADR-281, amending ADR-261, ADR-268, ADR-184, ADR-214, ADR-263, ADR-280): `docs/architecture/ADR-281-Anticipated-Moments-And-Mail-Watches.md` — the heartbeat is PERIODIC, so it cannot serve an INSTANT: a meeting ends at 15:00 and the next pass falls at 15:22 on a batch the person may not be in, while the context's calendar window starts at `now` and looks FORWARD, so a finished meeting is invisible to the decision. A `proactive_moments` row is one instant for one account, unique on `(user_id, kind, source_ref)` so a meeting never produces two, claimed by `FOR UPDATE SKIP LOCKED` plus a conditional `UPDATE` in the SAME transaction with an owner token, and REVALIDATED before it is served (the meeting may have been cancelled, the person may already have written). It runs under the FULL eligibility checker and bypasses only the probabilistic smoothing and the learned rhythm, exactly like an ADR-261 wake and for the same reason: **an instant does not defer** — postponing "how did it go?" by two hours is not asking it. The question is ASKED, never the evaluation: one open question, at most two facts, no judgement of the person, no two moments stacked, never the same question twice. The in-meeting guard reads the calendar behind a Redis verdict cache and **records no consultation on a cache hit** (Redis answered; the mailbox was never opened, ADR-263), a failed read declaring `failed` rather than reading as silence. Control ships WITH the capability (ADR-214): each kind switches off alone, the capability has its own switch (ADR-280), reads are forgiving and writes are strict. **A false negative was corrected before any code**: the response loop already existed (`_inject_proactive_messages`), so the planned lot was deleted and replaced by thirteen characterization tests. A finished routine now CLOSES (`is_enabled = false`, `status = completed`) — `SeriesEnd` already ended a series three ways, all landing on the same NULL trigger, but nothing closed the ROW, which stayed "active" for ever and indistinguishable from a pause; an `expires_at` column was written and then REMOVED before delivery, because it would have been a second authority on when a routine ends beside a `SeriesEnd` already stored, validated, edited in the studio and told in six languages. The ADR-261 wake serves `mail_match` watches from the Gmail delta it already holds, BEFORE the pre-filter's verdict (which answers "is this worth waking the heartbeat" where a watch answers "is this what I am waiting for"): it advances `next_trigger_at` and **never runs the routine** — the executor stays the sole judge — deduplicates nothing a second time (`condition_state` already decides), can only bring a run FORWARD and never resurrect an exhausted series, and arms PAST the published Gmail search-cache TTL because a cache filled before the mail arrived would answer "not met" and **that verdict consumes the arming**. The two readings of "does this mail match" are unavoidable (raw resource vs display projection) and therefore PINNED by an agreement test over eleven mails, its one legitimate divergence written down rather than discovered. The briefing's "Watch" chip WRITES where its neighbours open the chat — the chat cannot author a condition routine — keys on the SENDER and never the subject, ends through the `SeriesEnd`, and **reads what the account already holds before writing**: two mails from one sender are ordinary, and two identical watches would announce one awaited reply TWICE.
- A kept answer belongs to the PERSON, not to the conversation (ADR-282, amending ADR-279, ADR-280, ADR-185, ADR-184, ADR-276): `docs/technical/BOOKMARKS.md` — a bookmark is a **COPY, not a pointer**: the answer (markdown or a `lia-response` document, verbatim), the request that produced it and the answer's date are copied at the click into `message_bookmarks`; `message_id` / `conversation_id` are `SET NULL` and serve the bubble's toggle alone, so a conversation reset never touches a bookmark. **The request is resolved SERVER-SIDE under `visible_only`** (the bookmarks repository is declared `VISIBLE_ONLY` in `message_readers`): the last visible `user` message before the answer, never a run's synthetic question, and a `proactive_*` notification keeps NO request rather than a wrong one — that prefix is declared ONCE (`PROACTIVE_MESSAGE_TYPE_PREFIX`) and read by its five writers. The toggle is idempotent by a PARTIAL unique index (keeping twice answers 200, and the cap bounds new rows only); `BOOKMARKS_MAX_PER_USER` is published because it is enforced, its refusal a class of its own (`BookmarkLimitReachedError`) whose sentence is translated; page and exact total come from one `WHERE`, ordered by the ANSWER's date then the primary key. `PlatformCapability.BOOKMARKS` guards the `POST` alone — listing, state, deleting and exporting stay open — and its map node is counted and routed to the TAB of the generated-files section through `CAPABILITY_SECTION_TAB`, because `CAPABILITY_SECTION` is a bijection and that section belongs to `generated_files`. The chat reads the state ONCE per mount (`GET /bookmarks/state`, a context inert outside its provider); the card renders through `MarkdownContent` and exports through the chat's own `.md` path with the request quoted on top. The domain's raisers live in `bookmarks/errors.py` on the central taxonomy, because `core/exceptions.py` is size-frozen (the attachments' and meetings' precedent).
- A worker API has a declared, measured anatomy (ADR-283, amending ADR-119, ADR-123, ADR-148, ADR-184 and audit F004): `docs/architecture/ADR-283-Worker-Memory-Anatomy.md` — nothing here was a leak, and every figure was measured on the host in a throwaway process BEFORE being touched (three of them were wrong on first reading: an import cost measured on x86_64 dev does not transfer to arm64 — PyMuPDF 118 MB there, 43 MB in production; `pg_settings.setting` of `shared_buffers` is in 8 kB blocks, so `setting||unit` prints `655368kB` that reads as 640 MB; the production whisper model is ALREADY int8, the 1.6 GB is ONNX Runtime's working memory, not weights). **The supervisor never imports the application**: `uvicorn.main.run` calls `config.load_app()` in the parent for an early error it then discards, and that parent held 437 MB while serving no request — `python -m src.serve` drives the same `Config → Server → Multiprocess` chain without the call, imports nothing from `src` (AST guard), and hands the early-error job to the health check the deploy already reads (34 MB measured). **A heavy library is imported where it is used**: `LAZY_ONLY` in `test_lazy_heavy_imports_guard.py` declares each measured cost and refuses a module-level import anywhere under `src/`, module-level `try` included. **What a singleton loads is multiplied by the worker count**: the STT kept one whisper recognizer PER LANGUAGE ever asked, in a singleton PER PROCESS — 1.6 GB per worker and growing on every decode, two voice sessions on two workers took the container from 4.2 to 7.0 GB against 8 GiB — so the cache is bounded (`VOICE_STT_MAX_RECOGNIZERS`, 1, least recently used out, nothing loaded at construction) and an eviction is proven to return memory (−1 166 MB measured); a decode in flight keeps its own reference. **Every worker publishes what it holds**: cAdvisor sees the container and prometheus_client's multiprocess mode exports no `process_*` metric, so a container climbing from 2.5 to 5.3 GB over two days could blame no process — `lia_worker_memory_bytes{kind}` (`liveall`, one series per live worker, read from its own `/proc/self/status`) plus `voice_stt_recognizers_loaded`, two panels on dashboard 03 and the alert `ApiWorkerMemoryHigh` that names the `pid`. **A connection budget has a FLOOR as well as a ceiling**: F004 bounded the burst; the persistent pools (20 per worker × 4 = 88 idle backends at 7 MB each, next to 512 MB of `shared_buffers`) were 110 % of the Postgres container's 1 GiB — the reason it oscillated at 95-99 % every morning and swapped the database to zram. `ConnectionBudget.persistent_total` names it and `test_postgres_memory_floor_guard.py` reads compose and profile together (`floor ≤ limit / 2`): pool 5 / overflow 15 per worker, limit 2 GiB. Left open, on purpose and in writing: the multi-day growth of a worker without STT, now measurable; the LangGraph checkpoint retention (3 GB of a 3.25 GB database).
- ADR index (282 ADR files, ADR-283 latest — ADR-008 has no separate file, so the highest number runs one above the file count): `docs/architecture/ADR_INDEX.md`
- A written debrief per relationship, and what a dated synthesis may claim (ADR-269, amending ADR-176, ADR-184, ADR-190): `docs/architecture/ADR-269-Relationship-Debrief.md` — the 360° evidence assembly is EXTRACTED from `get_person_overview_tool` into `domains/relations/overview` and frozen by a golden file captured BEFORE the extraction (18 scope cases, payload and message compared byte for byte), because the tool and the debrief must never disagree about who someone is (ADR-185); the provider half is now read only for the sections the scope asks for — it used to be read whole and then dropped, up to **eleven external calls** billed against a selection the reader had already made, which is ADR-184 pointing at cost, and the narrowing needs a THIRD status, `NOT_REQUESTED` ("I did not look, on purpose" is neither "found nothing" nor "could not look"). A debrief is built lazily at card open, **never by a scheduler** (`relations_total` is unbounded), at most once per the reader's LOCAL day, with exactly three legitimate rebuilds: language, scope, and an explicit ask. **The evidence digest is compared only with the evidence in hand** — a passive "the data moved" flag would state a negative nobody verified — and the shortcut it earns (a forced rebuild over identical evidence calls no model and carries the DAY forward without touching the date the words were written) is NOT taken when the language or the scope changed, or the debrief would stay in the old language for good. Nothing is invented: no evidence settles `empty` with no call, and a failure KEEPS the previous text under a line saying the refresh failed — replacing a usable synthesis with an empty panel turns "I could not refresh this" into "there is nothing". The claim is ONE statement (`ON CONFLICT … WHERE … RETURNING`), `held_until` carrying two meanings that read alike (a dead builder's lease, a failure's cooldown) and every settle quoting its `claim_owner`. **In the chat the debrief JOINS the peer block rather than replacing it, with the OPPOSITE directive**: the peer block says its facts are EXACT because it reads them in the turn itself, and the same sentence over a dated synthesis is a false-claim machine — the debrief's template says it is dated and sends every date, count and status to the tools; an ambiguous name match injects NOTHING, because the debrief directory holds every relationship ever opened and a false positive hands one person's file to a question about another. The injection reuses the EXISTING slot (`_inject_peer_context`): `fetch_response_context` carries a cyclomatic complexity of 67 the audit gate freezes, and its `gather` stops at six awaitables. The account switches it off from the Relations page, where the result is shown, and off it collapses to the row that turns it back on. Three duplications died on the way: `_resolve_provider_client` (which returned a client bound to an already-closed session), **three copies** of the path-based prompt reader (now `core/prompt_store.py`), and the name-mention matcher (now `shared/name_mentions.py`, because `relations` needs it and `agents` imports `relations` — a local import would only have hidden the cycle).
- Generic recurrence, and a reminder that can repeat (ADR-268, amending ADR-051, ADR-198, ADR-265): `docs/architecture/ADR-268-Generic-Recurrence-And-Reminder-Management.md` — ONE engine in `src/core/recurrence` (a product: which calendar days × which moments), `anchor_date` mandatory or a series is not a series, caps INJECTED per consumer (12 a day for a routine, 48 for a reminder), and the post-it becomes a CASE of the general rule: `rearm_after` answers `None` for a consumed single occurrence, which is what "delete after notification" always was — so no branch anywhere reads "does this repeat". A reminder's `trigger_at` therefore stays NOT NULL (a reminder with no future is deleted) where a routine's `next_trigger_at` is nullable (its configuration is the thing of value). `retry_count` is reset on success and a repeated failure abandons the OCCURRENCE, not the series. ONE authority for when something fires: `POST /reminders` refuses `trigger_at` and `recurrence` together, `PATCH` refuses a bare instant on a repeating reminder. A wall clock follows the person — a timezone change moves routines AND reminders, composed in `infrastructure/scheduler/timezone_propagation.py` because calling both domain services from `users` closes a cycle. The notification prompt learned that a recurring occurrence must NOT cite the day it was set up. `core/recurrence` must import with no domain and **no configuration**: reaching for `core.time_utils` there closes a chain on a partially-initialised `core.config` and nothing boots. **What the model may SAY is declared once** (`agents/registry/recurrence_parameters.py`) and translated once (`core/recurrence/dictation.py`): the two scheduling tools take the same FLAT parameters — `compact_schema` flattens a nested object into the very `parent.child` names it then forbids — and each publishes the caps IT enforces (ADR-184), so an out-of-bounds number is CLAMPED by the planner's own repair rather than reported as a defect. `create_reminder_tool` declares `mutation_policy="reversible"` — it acts, and until ADR-268 it inherited `readonly` from a fallback (ADR-263). How well a model actually transcribes a spoken schedule is MEASURED, never assumed: 18 families × 6 languages in `tests/unit/core/recurrence/transcription_corpus.json`, whose deterministic half is a unit test and whose provider half is a script (`task recurrence:corpus:measure`, the `mobile:probe` shape) because a test that skips on a missing key is decoration (ADR-155). **The oracle is the INSTANTS, not the parameters** — two wordings that fire at the same moments are the same schedule, and comparing fields would report a failure for a right answer (ADR-182). **A STORED selector is a READ selector** (`SELECTORS_READ_BY`): the engine hands each frequency only its own, so anything else was accepted, stored, displayed and DROPPED — a `daily` rule declaring weekdays rang all weekend and a `monthly` one declaring months fired twelve times a year, both reachable from the chat. That is ADR-184's trap pointing the other way — there a bound was enforced without being published, here a value was published without being enforced — and both end with a producer believing it was obeyed. The model refuses one, the dictation REPAIRS the two exact identities before it (`daily`+weekdays at interval 1 IS weekly; `monthly`+months IS yearly) and the repair is VISIBLE because the confirmation is built by `describe`, and `withFreq` clears what the new frequency cannot read — the two tables being uncrossable between languages, a test parses both. Corollaries from the same pass: a sentence that names only `bymonth[0]` hides half a series the engine fires correctly, a language's day mark belongs to the NUMBER and not to the sentence (`Am 1 und 15.` had one ordinal for two), and a function documenting `Raises: RecurrenceError` must UNWRAP Pydantic's `ValidationError` or every caller's `except` misses it.
- Silent-loops programme (ADR-260/261/262), each OFF by default where it adds a subsystem: `docs/architecture/ADR-260-Redis-Key-Families-Scope-And-Reset-Purge.md` (a Redis key family declares its scope; a reset purges by family, never by glob), `docs/architecture/ADR-261-Push-Driven-Heartbeat-Wake-And-Incremental-Drive-Sync.md` (a processed push queues a wake; the sweep serves it under the FULL eligibility, only the probabilistic smoothing bypassed), `docs/architecture/ADR-262-Opt-In-Mail-Label-RAG-Source.md` (a space follows a Gmail LABEL, never the mailbox; removing the label removes the document)
- Execution authority chain and effect register (ADR-263): `docs/architecture/ADR-263-Execution-Authority-Chain-And-Effect-Register.md` — a capability DECLARES what it owes the user (`mutation_policy`), an effect is CLAIMED before it happens and CLOSED from an explicit result, the gate is installed on the capability at REGISTRATION (the MCP adapters gate themselves, inside `_arun`, where their three call doors meet), an unconfirmed `confirm` ASKS instead of failing (`DraftType.TOOL_CALL`), and every proof surface READS the register — nothing writes it. Dashboard 28 + three core alerts; a read costs 0.64 µs and zero database sessions. **Two registers, never one list with a filter** (owner arbitration): `agent_effects` takes one row per ACTION, `agent_treatments` one row per CONSULTATION — the latter collected in a LIVE LIST the turn's parent publishes (a `ContextVar.set()` in a child task does not reach its parent, so it would work in ReAct and silently lose the pipeline) and written in ONE shielded batch beside the token tracker. A consultation records the capability, never the call, and reads as its DOMAIN (`DOMAIN_REGISTRY`, 31 nouns) rather than a per-tool wording. No purge ships: retention runs to account deletion and the growth is instrumented instead (`lia_ledger_rows`, `lia_ledger_bytes`). One renderer serves the four extractions (user readable, account archive, admin readable over one/several/all accounts masked-unless-audited, admin technical). **Lot 5 seals both registers into a per-ACCOUNT hash chain** (`ledger_chain`, `LEDGER_CHAIN_ENABLED`, OFF by default): per account and never global, because that is what lets inalterability and the right to erasure coexist — deleting an account removes a COMPLETE chain instead of punching a permanent hole in everyone else's. Notarising is ASYNCHRONOUS on a measurement (6,0 ms per row against 0,21 ms for the write itself, ×28 on the critical path), so it has a WINDOW: that window is published (`lia_ledger_chain_lag_seconds`), alerted and named on every surface, never implied away by the word « verified ». An action takes TWO stages (`EFFECT_CLAIMED` then `EFFECT_SETTLED`) because a ledger row is MUTATED — one digest at claim time would make every legitimate close read as tampering. The pending set is found by a NULL marker on a partial index, never a timestamp watermark (a watermark misses a row whose transaction committed after the pass) and never a join (9,93 ms against 0,64 ms, and it grows with the register instead of the backlog). **Nothing repairs a chain** — a repair tool serves an attacker as well as an operator — and what the chain does NOT prove is written down in `docs/technical/AI_ACT_TRACEABILITY.md` rather than left to be discovered. **Lot 6 adds a THIRD register, `agent_decisions`: one row per TURN** — the spine the other two hang off, since both file their rows under a `run_id` that pointed at nothing until now. It **points** at the request and the answer (`SET NULL`, so a deleted conversation leaves a dated tombstone) and copies neither: the words stay in the one place already purged with the account. A HITL resumption is the SAME turn, so the write is an upsert that MERGES — earliest start, latest end, ACCUMULATED duration (a human deciding for twenty minutes is not a turn running for twenty minutes), and a `segments` counter, because overwriting in silence would make an interrupted turn indistinguishable from a straight one. The outcome is DERIVED by the context manager from what actually happened — `interrupted` until an explicit success says `answered`, and an explicit success is never downgraded by a stream that broke after the answer — never asked of callers, because there is always one more exit path someone forgets. The three registers never add up. **Lots 7-9 close the Article-12 shape**: the parameters of the inference are read from what LangChain actually SENT (`invocation_params`), normalised to ONE vocabulary — three providers spell the output cap three ways — and stored on `token_usage_logs`, which was already the per-call record; capture is an ALLOWLIST, never a dump, because a register is the last place a credential should land. Of everything Article 12 calls a risk, only FOUR situations left no durable trace: a turn stopping short became a `stop_reason` COLUMN (read from `react_exit_reason`, the one predicate that decides it), and the three that mean « the record itself is incomplete » became `agent_integrity_events` — written at the point that already increments the metric, one detection and two destinations, never a second detector. `/admin/effects/export/article12` composes the five records into one JSONL with a NAMESPACED `lia_record` per line (a plain `kind` was silently overwritten by the integrity register's own column), the ceiling stated PER SOURCE because a file complete in four records of five is not complete. The account holder gets the technical format too — the SAME contract, not a user variant: it makes their file safe to HAND ON, and a second contract for the same rows would be a second place for a column to slip from « forbidden » to « exported ». **`token_usage_logs` is BILLING_RETAINED and therefore outlives the account** — the one record that does, said out loud in `docs/technical/AI_ACT_TRACEABILITY.md`. **A capped read states which END it kept** — and since ADR-273 no extraction is capped at all: the five reads carried a `LIMIT` and no `ORDER BY`, so PostgreSQL returned the OLDEST rows — an export read on 2026-09-05 covered January to March and named models the instance no longer configures, while its header truthfully said « capped ». The ordering rule survives its cause and lives in one place (`infrastructure/database/export_stream.py` — in `infrastructure/` because the chat domain reads it too, and beside the registers it closed an import cycle a local import would only have hidden). The corollary the design already held: a model change stays VISIBLE, because every LLM row stores the model actually used and nothing resolves a name at read time. **The registers are also DRAWN**, as a third tab and on the admin surface: ONE component for both audiences (two renderings would be two places for a figure to be right on one screen and wrong on the other), nothing counted client-side, the EXACT total beside every set of bars including whatever the top-N folded into `other` (ADR-185), and BOUNDED labels only — `sub-agent: <title>` and `MCP Iterative: <server>` collapse to one word, because those two carry user-authored text and third-party server names. **A figure DECLARES what it is** (`SeriesKind`): a count, two measures stacked on one bar, or a MEAN — a sum of means is not a quantity, and a total covering half a stacked bar is shorter than the bar; averages are therefore computed from a SUM and its OBSERVATIONS so the badge and the folded bar are both weighted, and the badge wording is derived from the kind, never passed by the caller. **A guard that matches a NAME validates a name**: the property test that checked every admin route for `require_superuser` passed on two routes where it was wired as `Depends` — an imperative `(current_user, action=…)` helper, which FastAPI turns into a required QUERY parameter, so both answered 422 and authorised nothing. The guards now read an AST CALL, refuse the helper as a dependency, and refuse any required query parameter an endpoint never declared.
- A register extraction is complete, or it is not an extraction (ADR-273, amending ADR-263, ADR-185, ADR-184): `docs/architecture/ADR-273-Complete-Register-Extractions.md` — the five downloadable records carried a row ceiling that was MEASURED (five sources at 5 000 rows peaked at 33,9 MB on the Raspberry Pi 5 this deploys to) and applied to the WRONG variable: the whole document was assembled in memory, so the only lever was to read fewer rows. **What was scarce was memory; what was bounded was the truth** — a person exercising a portability right received a sample of their own record, and the header saying « truncated » repairs nothing. A server-side cursor replaces the ceiling (`infrastructure/database/export_stream.py`, `EFFECT_EXPORT_BATCH_ROWS`), so a download holds one partition rather than a register. Rows are detached ONE BY ONE: `expunge_all` REPLACES the session's identity map and kills the old one, which the open cursor is still loading into — the second partition died on « this identity map is no longer valid », found by the PostgreSQL integration tests and invisible to the unit ones, because a stubbed stream has no identity map at all. The count is EXACT (an aggregate over the same statement the body streams) and published before the first row, so an extraction with no upper bound is given one — the instant of generation — and that bound is NAMED in the header rather than pinned in silence. **Completeness is CLAIMED, never inferred from silence**: `truncated: false` and `X-Register-Truncated` stay, `row_cap` and `cap_per_source` go, because dropping the claim would make a reader tell a complete file from a partial one by the ABSENCE of a warning. The download is gzipped when the client offers to decompress — transport, so the file NAME does not change; a `.gz` artefact would be a different contract. The screen (`/admin/effects/readable`) keeps its page size and the newest-window rule with it.
- Document craft: the renderer owns the form, the model owns the meaning (ADR-274, amending ADR-226 and ADR-184): `docs/architecture/ADR-274-Document-Craft-Renderer-Owned-Model-Semantic.md` — the prompt was suspected and was NOT the cause: it already asked for more than the renderer could produce. Two ceilings, both MEASURED: a vocabulary of four block kinds and `title + bullets` slides, and a renderer using **2 of the template's 11 pptx layouts**, **4 of Word's 164 named styles** and **no PDF stylesheet at all**. The model now says what a thing IS (`numbered`, `quote`, `callout`, a table `caption`, a slide `kind`) and the renderer draws it with NATIVE mechanisms — Word fields and numbering definitions, PowerPoint layouts and placeholders, a named Excel Table over TYPED columns, PDF bookmarks and exact page numbers. **Nothing overflows, by construction**: `fit.py` is calibrated against PowerPoint 16 on 54 combinations (any glyph width in [0.426, 0.493] em counts lines exactly; ×1.05 turns 18 under-predictions into none), text is shrunk to 14 pt then SPLIT, and a bullet too long for a slide is cut at sentence boundaries, never clipped — `fit_text` from python-pptx was measured wrong by a factor of two. Every incoherence is REPAIRED (ADR-184), and the `level` bound is REMOVED from the schema because a bound fails the whole document three paid times over one heading (ADR-269). ONE predicate switches the table of contents, the heading numbering and the part breaks TOGETHER; meeting minutes pin `structure="plain"` and keep their shape. Word's contents is pre-rendered WITHOUT page numbers (the field is empty until F9, so a document printed straight away would show a blank page); the PDF's carries EXACT numbers because the body is laid out once — it never contains the contents — and the front matter is concatenated in front of it, which also gives the contents its own page. Traps that are measured, not assumed: **Excel REFUSES a workbook** whose Table has a duplicate or empty header; **`TOC Heading` inherits `Heading 1`**, so untouched it becomes chapter 1 of its own contents; **MuPDF repaints a phantom header rectangle** on continuation pages when a `th` has a background under `border-collapse` (the oracle counts fills covering no text: 0 on the shipped recipe, 42 on the dangerous one); and **writing an INHERITED pptx placeholder position freezes it at height 0**. **A full-width glyph is one em BY DEFINITION** — every calibration measurement was Latin, so counting an ideograph at 0.46 em measured a dense Chinese slide at 238 pt where it takes 442 in a 356 pt frame, and the overflow ORACLE agreed with the renderer because both read `fit.py` (PowerPoint: 2 overflows, one of 124.1 pt, against 0 once corrected); the rule is a strict generalisation, so the 54 fixtures hold, and ONE notion of width now serves the line count, the pptx column weights and the xlsx column widths — all three counted code points. **The length budget is per FAMILY**: prose and slides converge to 0.69 words per output token and a workbook to 0.25, so a single factor published a number 2.2× too generous for a spreadsheet. **The characters XML forbids are removed in the canonical form** — python-docx and openpyxl REFUSE them, so a model echoing a form feed killed the render after the call was paid for. The corpus of 13 documents is rendered by the unit tests and MEASURED by Office itself (`task documents:corpus:measure`): 0 overflows on 69 slides, Word computing `Page 1 / 10` and `第 1 页，共 7 页`.
- A truncated structured output is a refusal, never a rescue (ADR-275, amending ADR-220, ADR-226, ADR-258, ADR-272): `docs/architecture/ADR-275-Truncated-Structured-Output-Is-A-Refusal.md` — `json_recovery` closes an open structure and the shortened object VALIDATES: measured, **12 of 100 report cuts and 14 of 100 deck cuts became shorter documents announced « generated successfully »**, and a cut that did NOT validate was replayed three times at full price. `is_output_truncated` reads the provider's OWN verdict (five shapes, each read in the installed adapter) at all THREE doors — the buffered native path, the auto-tool path, and the JSON-mode fallback where `json_recovery` is called deliberately and its own comment names truncation as a case it « handles ». **A complete answer is never refused**: the verdict is consulted only once no complete answer exists, since a payload the provider parsed without repair is syntactically closed. Nothing retries it — not the wrapper, not the semantic validator (whose retry exists for a residual EMPTY-answer rate), and not the meeting job, where every `StructuredOutputError` was `transient=True`, so a cut synthesis was re-driven until the attempt budget ran out: a truncation is PERMANENT (`synthesis_too_long`). The document tool names the budget instead of merely refusing. And the document service now passes `user_id` to the structured door: `resolve_owner` reads `config.metadata.user_id`, which LangGraph never sets (probed — only `thread_id` is merged), so a « bounded caller » accepted by NAME carried no owner at all.
- Traceability and what the sealing proves — and does not (ADR-263 lot 5): `docs/technical/AI_ACT_TRACEABILITY.md` — the Article-12 map lot by lot, the published window, the four limits stated before the capabilities
- Routines' week view and run history (ADR-265): `docs/architecture/ADR-265-Routine-Week-Timeline-And-Run-History.md` — the cards sort at the DISPLAY (the API's `next_trigger_at` order has three other readers); one row per tick in `scheduled_action_runs`, written AT THE RESULT inside a savepoint, never a gate on the routine; a week cell takes the LAST run whose `slot_at` EQUALS the week's instant (reset on change and on Monday by construction, no column, no window); `GET /scheduled-actions/week` is declared BEFORE `/{action_id}`; the grid is a `<table>` that only PAINTS and never re-reads the cron; three pre-existing defects closed on the way (a poll unmounted the cards, a paused routine kept the old zone after a move, APScheduler SKIPS the day for a 00:xx routine in a zone whose DST gap opens at midnight — `_next_fire` is the only reader of the cron in the helpers)
- Ollama as a native provider with server-declared capabilities (ADR-267, amending ADR-245, ADR-220 and ADR-244): `docs/architecture/ADR-267-Ollama-Native-Provider-And-Discovered-Capabilities.md` — `ChatOllama` replaces the OpenAI-compatible shim (`_create_ollama_llm`); a DISCOVERED layer of `ModelCapabilitiesCache` holds what `/api/show` says (tools, vision, thinking, context length), in memory only, refreshed when the ADDRESS changes (never on every admin save, which would wait for the discovery timeout) plus on the admin's model listing, and WINNING over a seed row of the same name; the `ollama` reasoning family has a ladder declared PER MODEL (full for `thinking`, `("none",)` otherwise, unknown when undiscovered — `ladder_from_catalogue`), so a positive `think` only ever reaches a model that can think and `none` reaches any; when nothing is asked on a thinking model the server default is made explicit (`reasoning=True`) so the trace is SEPARATED into `reasoning_content` rather than dropped; **what LIA accounts with is what LIA requests** — since ADR-278 the number is a column of the configured SLOT (`llm_config_overrides.context_window`, pre-filled from what the server says about the tag), else the model's own maximum, capped by `OLLAMA_NUM_CTX_DEFAULT_CAP` for a LOCAL tag and left whole for a CLOUD one; it is the `num_ctx` sent on every call and the number `get_effective_context_window_for_slot` hands the compaction threshold (before: 51 200 = 128 000 × 0.4 for an unknown model against a server allocating by VRAM tier); usage `native`, structured output through the native `format` (`native_structured_method`); the two OpenAI penalties are not expressible and are hidden from the admin UI
- **A guard that runs for no model guards nothing** (ADR-245 amendment, 2026-09-06): `_create_with_dedicated_client` is consulted BEFORE `_prepare_provider_config`, so the named "reasoning model parameter filter" in the OpenAI branch is unreachable for every real model — only `o0`, which does not exist, still lands there, and its test patches `is_responses_api_eligible` to `False` to reach it. The protection that RUNS is in `create_responses_llm`, and it keyed on the EFFORT rather than the MODEL: at `provider_default` the translator renders nothing, so a reasoning model took the standard branch and got `temperature` and `top_p` (measured on the real API: `top_p=1.0` tolerated, `top_p=0.9` → 400). Both now read ONE predicate, `model_capabilities_cache.is_reasoning_model`, pinned by a single-reader guard. And the sampling flags are NOT read from the catalogue: they are absent from `sync_diff.COMPARED_FIELDS`, so `imported` does not vouch for them — measured, the catalogue marks `temperature` unsupported on a model that accepts it.
- The context window belongs to the configured SLOT, never to the instance (ADR-278, amending ADR-267 and ADR-244): `docs/architecture/ADR-278-Per-Slot-Context-Window.md` — `OLLAMA_NUM_CTX` was ONE environment variable served to every Ollama tag whatever its size (measured on production 2026-09-10: 128 000 requested for a 4 B model and a 27 B one alike) and it is GONE. The window is `llm_config_overrides.context_window`, nullable, pre-filled from what the server says, so two slots on the same tag may legitimately differ; `get_effective_context_window_for_slot` is the ONE door its four readers use (compaction, ReAct budget, summarisation middleware, meetings synthesis), all of which start from a slot. Discovery reads `GET /api/tags` FIRST — measured, it carries capabilities AND `context_length` for every tag, cloud included — and `POST /api/show` is the fallback for a tag the listing left incomplete, because it answers NOTHING for four of eight cloud tags and **that silence was published as a declaration**: those tags were profiled as tool-less, thought-less and capped, and a `discovered` profile WINS over any catalogue row an administrator can edit. A tag nobody described now gets NO profile and is named. A cloud tag is recognised by its HOST (`remote_host`), never by a `-cloud` suffix, and keeps its whole window: the cap protects THIS machine's VRAM, and there is none of ours on somebody else's. Asking for nothing is not neutral — the server picks a VRAM tier and truncates a longer prompt in silence — so an unreported window requests the cap.
- A file LIA produced belongs to the PERSON, not to the conversation (ADR-279, amending ADR-226, ADR-185, ADR-184 and ADR-260): `docs/architecture/ADR-279-Generated-Assets-Gallery.md` — generated images, generated documents and browser screenshots were written to `attachments` **indistinguishable from an upload**: nothing listed them, the only route to yesterday's report was the conversation that produced it, and `ConversationService.reset` called `delete_all_for_user(user_id)` with no filter, so « clear this conversation » also cleared last week's images in other conversations. `origin` names the producer on a CLOSED vocabulary — `upload` plus `GENERATED_ORIGINS` partition the enum, checked by a test — and a value nobody declared is **never** read as generated, because the safe side is the one that does not accumulate strangers in a gallery. The reset now passes `origins={upload}` (ADR-260's doctrine applied to files: a purge removes what its family DECLARES, never what merely looks like it), while the TTL still expires everything — **the retention stays 24 h**, the gallery makes the deadline VISIBLE without pushing it back, and an unreadable deadline reads as PAST because « you have time » about a date nobody could parse is the wrong way to be wrong. The backfill reads the SHAPE each producer stamped (`generated_` / `browser_`, at the START of the name only) and refuses to guess further: a document is named after the person's request, so it is recognised from the MESSAGE METADATA pointing at it, and whatever neither pass proves stays `upload` — which is what the row already was. Three galleries, screenshots having their OWN (owner arbitration: they are not looked for the way a requested visual is); `upload` is not listable at all — `GalleryFilters` refuses it at construction rather than returning an empty page. A page and its EXACT total come from ONE `WHERE` (ADR-185), every ordering ends on the primary key, the needle goes through `escape_like`, and `max_limit` is PUBLISHED because it is enforced (ADR-184). **`capability_dependencies(ATTACHMENTS)` moved from the ROUTER to `POST /attachments/upload` alone**: uploading and consulting are two capabilities sharing a table, and switching the first off closed the door on files a person legitimately keeps and could no longer delete — the wiring guard learned to read a route-level guard. « Deleted » means gone: an id the caller does not own, an upload, or a row the cleanup removed between the listing and the click is SKIPPED, never counted. And why a file went is recorded on the label the dashboard already groups by — `reason` becomes the closed `expired | conversation_reset | user_deleted`, **no new metric**: before, a person emptying their gallery was indistinguishable from a conversation reset.
- One switch per capability, and a map that does not lie (ADR-280, amending ADR-216, ADR-085, ADR-185 and ADR-279): `docs/architecture/ADR-280-Complete-Capability-Control.md` — the admin panel offered TWELVE capabilities while the product also shipped a workboard, journals, habits, proactive notifications, peer connections, a psychological profile, external channels, open loops, long-term memory, interest tracking, relationship debriefs, delegated sub-agents and an ephemeral Python sandbox: **thirteen features an operator could neither see nor switch off without redeploying**, which is ADR-085's drift pointed at the switch registry itself. `PlatformCapability` holds twenty-five members and the partition is checked BOTH WAYS against a list a PERSON maintains — a feature shipped without a switch fails, a switch nobody decided to ship fails too — and every spec is checked piece by piece (the ceiling really exists on `settings`, since a misspelled attribute reads False and switches the feature off for good; the key is named after ITS capability; the label follows the convention the frontend resolves). **A switch removes the CAPABILITY, never the RECORD** — ADR-279 generalised: where the router IS the ability the guard sits on the router (eight of them), and where the ability is a BACKGROUND act filling a record the person keeps reading — extracting a memory, learning an interest, writing a debrief — the guard sits at the ACT and the record's router stays open. The five service chokepoints read `is_capability_enabled` AT CALL TIME, not `settings.<flag>`: a switch flipped after boot must take effect without a restart, and two of them became async for it. **A node says what it counts**: measured 2026-09-10, the star keyed `relations` and labelled « Relationships » counted `OpenLoop` rows and pointed at the open-loops settings section, so a reader was told they had four relationships when the figure was four unfinished threads; it becomes `open_loops`, and a real « Relations » returns as a SWITCH node with no tally, because the Relations page is a LENS over contacts and messages owning no rows — inventing a count there is what ADR-185 forbids. Five nodes join the map (`open_loops`, `workboard`, `reminders`, `generated_files`, `relations`), two capabilities stay off it with a written reason, and two tallies go through the module that OWNS their rule (`visible_predicate` for the board, `GENERATED_ORIGINS` for the files) rather than re-expressing it. Finally `enforced_on_routes` was `route_enforced or service_enforced` — the field named routes and carried both — so the panel announced « enforced on routes » about a service gate: the two are split, and the panel groups its twenty-five rows into six families DECLARED BY THE BACKEND spec (two tables would drift), in the declaration's order and never the payload's, an unknown family drawn LAST rather than lost — an invisible switch is worse than a misplaced one.
- Diagnosis evidence at diagnosis time and exact-`str` embedding inputs (ADR-266, amending ADR-254 and ADR-247): `docs/architecture/ADR-266-Diagnosis-Evidence-At-Diagnosis-Time-And-Exact-Str-Embedding-Inputs.md` — the evidence pack is collected by the PUMP, never by the self-check tick (ADR-254's constraint stands), per `EvidenceRecipe` keyed by correlation key (boot assert + CI test over every loaded alert and every named event), fail-open SOURCE BY SOURCE (a blind source is named, never read as silence), allowlisted and PII-sanitised, once per incident after the budget gate, stored with the diagnosis and drawn for the admin; the runbooks are STAGED by `prepare-prod.ps1` (they never reached production before) and their absence is counted, shown and warned about; no sample-size floor on `embedding_failure_rate` — the check was right on eight operations
- Living brows and mouth of the expressive eyes (ADR-264, amending ADR-252): `docs/architecture/ADR-264-Living-Brows-And-Mouth.md` — the brow has an ARCH (`browArc`) and is faintly PRESENT at rest; ONE breath carries the mass, the brows and the mouth width on the same period; the gaze and the blink couple to the brows in the RIG (never a `calc()` in the sheet), written as ABSOLUTE contributions because the idle fast path only rewrites what a loop rides — a `+=` there drifts for the whole session, and a test compares 20 000 small steps against one; speech has PHRASES (an envelope through the closure, opening bounded in [0, 1]) and brows that punctuate on an irregular pattern, at a measured 0.11 ms per frame; the moving hold is a PIXEL budget in the tests (0.6 to 2 px at rest, 0 on `focused`); the eye beats carry the face (a perk raises the brows, a squint knits them, a tilt smirks) and the mouth has a LIFE of its own (`rig/life.ts`: eight relative mimics at a random cadence, scheduled by the rig) — drawn from a SEPARATE entropy stream (`lifeRandom`, seeded once per mount), because a draw on `Math.random` at construction shifted the once-sequences the widget tests pin and failed four of them; without that stream nothing plays, so the pixel budget measures the hold alone; and ten SKETCHES (`rig/sketches.ts`, 3 to 5 s scenes every 45 to 120 s on a resting face, dropped by any expression change, the face exactly where it was when the curtain falls — tested against a twin rig) — every tape-writing module shares `rig/choreo.ts`
- CI/CD pipeline and the thin-CI doctrine (ADR-151): `docs/technical/CI_CD.md`
- Native mobile shells: `docs/guides/GUIDE_MOBILE_ANDROID.md`, `docs/guides/GUIDE_MOBILE_IOS.md` — measured platform behaviour, not assumptions
- 360° audit protocol (recurring; on "run the audit and update the public report", follow it end-to-end including the publication pipeline): `docs/audit/AUDIT_PROTOCOL.md` — public report: `docs/audit/README.md`, size metrics: `scripts/audit/measure_sloc.py`, complexity metrics: `scripts/audit/measure_cc.py`
