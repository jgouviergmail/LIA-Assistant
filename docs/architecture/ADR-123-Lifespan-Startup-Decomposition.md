# ADR-123: Lifespan Startup Decomposition — Subsystem Init Modules, Lifespan as Sole Orchestrator

**Status**: ✅ IMPLEMENTED (2026-07-10)
**Author**: Claude Code (Fable 5)
**Related**: [ADR-122 (AgentService Stream Decomposition)](ADR-122-AgentService-Stream-Decomposition-B2.md) (same monolith finding, same verbatim-move discipline), [ADR-117 (Background Chat Runs)](ADR-117-Background-Chat-Runs.md) (shutdown drain ordering), [ADR-063 (cross-worker cache invalidation)](ADR_INDEX.md), file-size ratchet guard (`test_file_size_ratchet_guard.py`)

## Context

`src/main.py::lifespan` had grown into the backend's second-largest monolith:
**~780 logical SLOC (1,133 raw lines)** covering 23 startup steps and 20
shutdown steps — registries, fail-fast validation gates, 8 caches, the
checkpointer, ~16 agent registrations, MCP, Telegram, system RAG, 16
scheduler jobs behind leader election, two background tasks, and the ADR-117
producer drain. Every feature release appended to it (the ADR-117 drain being
the latest), and the startup **order is critical but was implicit**: nothing
documented why the checkpointer sits between two cache groups, why MCP must
run before the semantic tool selector, or why Redis closes last.

The 2026-07 audit's "monoliths" finding (B-series) already produced two
decompositions with a proven method (v1.21.15, ADR-122). The same treatment
was applied here, with one structural difference: the lifespan is a *linear
orchestration script*, not a hot-path function, so the risk is not behavioral
regression under load but **silent reordering or altered error handling**
during the move.

## Decision

Extract every lifespan step into a new package **`src/infrastructure/startup/`**
— seven subsystem modules, each exposing one typed function per *contiguous
segment* of the historical sequence:

| Module | Functions |
|---|---|
| `registries.py` | `import_domain_models()`, `run_failfast_validations()`, `init_tool_schemas()` |
| `observability.py` | `start_metrics_server()`, `init_langfuse()`, `start_lifetime_metrics()` |
| `caches.py` | `init_redis()`, `init_pricing_caches()`, `init_config_caches()`, `start_cache_invalidation_subscriber()` |
| `agents.py` | `init_checkpointer()`, `init_agent_registry()`, `init_semantic_services()`, `init_agent_graph()` |
| `integrations.py` | `init_mcp()`, `init_user_mcp_pool()`, `init_telegram_bot()`, `sync_currency_rates_at_startup()`, `index_system_rag_spaces()` |
| `schedulers.py` | `init_scheduler()` (single function: 15 job registrations + leader election, one try/except as before) |
| `shutdown.py` | `StartupHandles` dataclass + `shutdown_application()` (single function, 20 steps) |

**The lifespan remains the SINGLE orchestration point**: `main.py` (1,399 →
322 raw lines) now reads as a sequence of ~25 calls in the exact historical
order, headed by a comment block documenting the eight startup order
dependencies and the shutdown ordering (drain first — ADR-117; Redis last).
The CLAUDE.md "Startup initialization" checklist is unchanged: a new step
still means a call added to the lifespan, its body now living in the matching
startup module.

Location rationale: `infrastructure/` (not `core/`) because the step bodies
import `src.domains.*` and `src.infrastructure.*` liberally — an established
direction (all 14 `infrastructure/scheduler/` modules import domains), whereas
`core/` is the base layer. `core/bootstrap.py` (pure validation helpers) is
untouched and still called by the extracted steps.

### Strict-identity constraints (what "verbatim" means here)

- **Same structlog events** — zero renames, zero field changes, same levels
  (dashboards and debugging depend on them). Only the `logger` module path
  changes on moved lines, as in ADR-122's precedent.
- **Same per-step try/except** — non-fatal degradation preserved exception
  tuple by exception tuple; fail-fast gates still raise `RuntimeError`.
- **Partial-object semantics preserved** — on mid-step failure,
  `init_agent_registry`/`init_mcp` return the *partially built* object from
  the except path (not None), because downstream steps and the shutdown gates
  historically consume it.
- **Lazy imports stay lazy** — function-level imports were kept inside step
  bodies (identical import timing and `ImportError` surfaces, e.g. the
  playwright probe).
- **Cross-`yield` state** is an explicit `StartupHandles` dataclass
  (leader_elector, mcp_manager, telegram_bot, lifetime_metrics_task,
  cache_invalidation_task) owned by its sole consumer, `shutdown.py`.

## Alternatives rejected

- **One async function per module, strictly** (the initial spec): impossible
  without reordering — the checkpointer is initialized *between* two cache
  groups, MCP runs *between* the registry and the semantic selector (its
  tools must be in the catalogue before embeddings are built), and
  observability appears at three non-contiguous points. One function per
  contiguous segment preserves the exact order; `schedulers.py` and
  `shutdown.py` do get single functions.
- **`src/core/startup/`**: inverts the layering (core would import every
  domain at module-import time).
- **Reordering the boot to make subsystems contiguous**: explicitly out of
  scope — order identity was the primary constraint.

## Validation

- **Line-accounting script** (scratchpad, reproduced in the PR discussion):
  every non-blank line of the historical lifespan body is present verbatim in
  the new modules, except an explicit allowlist (step-header comments turned
  into docstrings, three typed pre-inits, `handles.` prefixes in shutdown);
  per-block subsequence checks confirm internal order — 14/14 OK.
- **Boot log diff in Docker dev**: identical ordered sequence of
  lifespan-driven structlog events before/after (see PR), `/health` and
  `/ready` 200, `scheduler_elected_jobs_summary` with the identical job list.
- **Suites**: unit + agents green; Black/Ruff/MyPy strict clean.
- Known dev-env limitation (pre-existing, reproduced *before* the change):
  uvicorn `--reload` cannot complete a graceful shutdown while host SSE
  connections are open, so the shutdown sequence is validated by the
  line-accounting script and suites rather than by a dev log capture.

## Consequences

- `main.py` drops from 982 frozen SLOC to well under the 600 global ratchet
  ceiling (`task ratchet:update` run as part of this change).
- New steps land in a named module with a typed signature instead of growing
  a 1,100-line function; order dependencies are now documented at the exact
  place where order is decided.
- `tests/core/test_config_constants.py` now checks the constants import at
  the new registration site (`startup/schedulers.py`).
