# ADR-095: Systemic Guards from the Wave-2 Audit

**Status**: ✅ IMPLEMENTED (2026-07-03)
**Author**: Claude Code (Fable 5)
**Related**: [ADR-027](ADR-027-Structured-Logging.md) (structured logging), [ADR-085](ADR_INDEX.md) (boot-time completeness asserts), [ADR-094](ADR-094-Remove-Dead-Per-Node-Windowing-Helpers.md) (wave-1 dead-code removal), [PII_LOGGING_SECURITY.md](../technical/PII_LOGGING_SECURITY.md)

## Context

Wave 2 of the 2026-07 full-codebase audit targeted seven classes of
near-zero-risk *systemic* defect. Each class had a handful of live
occurrences, but the point of the wave was to close the **class**, not just
its instances — the "definition of done" was that a permanent guard (a CI
test, a Prometheus metric, or a written convention) prevents recurrence.

The seven classes were:

1. **Silent JSONB write loss** — SQLAlchemy does not detect in-place mutation
   of a JSONB column (`obj.meta["k"] = v`, `.update(...)`, `.extend(...)`): it
   skips the UPDATE and the write is lost. Four live sites (API-key
   `last_used_at`, connector auth-failure diagnostics, two psyche-state
   writes). This is the same class as wave 1's HITL-metadata bug — recurring.
2. **PII at INFO** — home address/GPS, resolved contact names/emails, email
   recipients/subjects, memory previews, raw tool params were logged at
   `INFO`/`WARNING`/`ERROR`, against the CLAUDE.md "no PII at INFO" rule and
   GDPR data-minimization.
3. **Silent tool-capability loss** — a swallowed `ImportError` around a tool
   module removes an entire tool family from the registry invisibly (the class
   that shipped as N-140).
4. **Billing-cycle counter leak** — three cycle-rollover paths hand-reset
   different subsets of the `cycle_*` counters, so silos (STT/TTS/image/Google/
   tokens) leaked across the boundary depending on which event crossed it.
5. **Chinese language-code divergence** — `zh` (frontend) vs `zh-CN` (backend)
   handled by multiple divergent normalizers; two tables were keyed so that
   `language="zh"` never reached their `zh-CN` entries.
6. **Non-localized last-resort fallback** — a hardcoded accent-less French
   string shown to every user when the pipeline and fallback LLM both fail.
7. **Docstrings describing behavior the code does not have** — a CLAUDE.md
   "docstring lying about behavior is a bug" violation (5 instances).

## Decision

Fix every live occurrence **and** attach a class-closing guard:

| Class | Fix | Permanent guard |
|-------|-----|-----------------|
| JSONB in-place mutation | New-object reassignment at 4 sites | **AST CI test** (`tests/unit/test_jsonb_mutation_guard.py`) — discovers every model's JSONB columns from their ASTs, fails CI on any in-place mutation of a same-named attribute in `src/`. Convention documented on the models + CLAUDE.md. |
| PII at INFO | Contents demoted to DEBUG twins at the 7 call sites | **Level-sensitive net** in `pii_filter.py` — `CONTENT_FIELD_NAMES` redacted at INFO and above, passed through at DEBUG, driven by the structlog `method_name`. |
| Silent tool-import loss | `_import_tool_modules` **raises outside production**; conditional imports log + count | **Prometheus counter** `tool_module_import_failures_total` (prod) + **3-layer registry smoke test** (`test_tool_registry_smoke.py`): import every module, assert each family's sentinel, invoke all ~95 tools with mocks and reject escaping/embedded programming errors. |
| Billing-cycle leak | 3 paths delegate to `UserStatistics.reset_cycle()` | `reset_cycle()` zeroes **every** `cycle_*` column by **introspection** (future silos covered automatically) + a multi-silo test with a coverage sentinel that fails when a new `cycle_*` column is added untested. |
| zh/zh-CN divergence | Two tables normalize through one chokepoint | **Single canonical `normalize_language`** in `core/i18n.py`; the former copies (`agents/utils/i18n_location.py`, `core/i18n_drafts.py`) delegate to it. Tests assert both spellings reach `zh-CN`. |
| Non-localized fallback | `get_simple_fallback_message(language)` via `SSEErrorMessages` (6 languages) | Test asserts an EN user gets English, and all 6 locales (incl. `zh` spelling) yield a message. |
| Lying docstrings | 5 docstrings corrected to match code | The CLAUDE.md rule itself (written convention). |

The most architecturally significant change is the **PII logging boundary**:
it alters the platform-wide logging contract. Content-bearing fields are now a
first-class category in `pii_filter.py` alongside `SENSITIVE_FIELD_NAMES`
(redacted always), `PII_FIELD_NAMES` (pseudonymized) and `PHONE_FIELD_NAMES`
(masked) — but `CONTENT_FIELD_NAMES` is **level-sensitive**: redacted at INFO
and above, allowed at DEBUG. This keeps counters/IDs observable at INFO for
production troubleshooting while guaranteeing contents never leak above DEBUG,
even from a future call site that forgets the rule.

## Consequences

- **No behavioral change for end users beyond the fixes themselves.** No DB
  schema change, no migration, no new `.env` key; one new Prometheus metric
  (`tool_module_import_failures_total`).
- **Defense in depth for logging.** The call-site discipline (don't log
  content at INFO) remains the first line; the net is the backstop. A DEBUG
  log still sees full content for troubleshooting.
- **`reset_cycle()` is now the single source of truth** for billing-cycle
  boundaries — any new `cycle_*` column is reset automatically and the sentinel
  test forces it into the multi-silo coverage.
- **The registry smoke test doubles as a broad tool-health check** — it caught
  two latent `runtime`-handling bugs (an unguarded `runtime.config` on `None`,
  five bare `runtime.store` accesses) that had nothing to do with imports.
- **Guards raise the cost of reintroducing each class to "CI goes red"**,
  which is the intended outcome: the audit's value compounds only if the
  classes stay closed.

## Alternatives considered

- **Fix occurrences only (no guards).** Rejected — it is exactly what let
  these classes recur (wave 1 already fixed one JSONB-persistence instance; a
  new one appeared here). The guard is the deliverable, not the fix.
- **Redact content fields at all levels (including DEBUG).** Rejected — DEBUG
  is where operators need full context to diagnose; the level-sensitive net
  preserves that while closing the INFO leak.
- **An allowlist of "safe to log at INFO" fields instead of a content
  blocklist.** Rejected as too invasive for this wave (every existing INFO log
  would need re-classification); the blocklist net is additive and low-risk.
  A future move to allowlisting can build on `CONTENT_FIELD_NAMES`.
