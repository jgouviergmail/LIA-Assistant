# ADR-102: Domain Vocabulary Single Source (singular name vs result_key)

**Status**: ✅ IMPLEMENTED (2026-07-04)
**Related**: [ADR-085](ADR_INDEX.md) (Draft Display Registry — the parity-guard model), [ADR-070](ADR_INDEX.md) (Pipeline vs ReAct)

## Context

The multi-agent system names domains on **two axes**, both derived from the
single source of truth `DOMAIN_REGISTRY`
(`src/domains/agents/registry/domain_taxonomy.py`):

- **Singular axis** — the domain *name* (registry key): `place`, `contact`,
  `email`… This is what `QueryIntelligence.primary_domain`,
  `QueryIntelligence.domains` and `source_domain` hold at runtime (they are all
  populated from `get_routable_domains()`, which returns registry keys).
- **Result-key axis** — the plural `DomainConfig.result_key`: `places`,
  `contacts`, `emails`… This is what `$context.<key>` references,
  `CONTEXT_DOMAIN_*` constants and `structured_data` carry.

Several derived tables drifted over time: a domain token was written on the
wrong axis relative to what it is compared against. Such a comparison **silently
never matches** — producing either a silent functional error or a wasted LLM
retry — and unit tests that fed the *same* wrong form masked the bug. A
full-codebase audit of every domain-token comparison / lookup site found **four
distinct inert comparisons** (and confirmed the remaining sites were benign or
display-only alias maps that tolerate both forms):

| # | Site | Compared against (axis) | Was | Fixed to | Impact |
|---|------|-------------------------|-----|----------|--------|
| A | `CROSS_DOMAIN_MAPPINGS` target (`planner/domain_constants.py`) | `primary_domain` (**singular**) | `places` | `place` | `CrossDomainBypassStrategy` never fired → every "restaurant of this meeting"-style cross-domain reference paid ~800 ms of avoidable multi-domain LLM planning. |
| B | `_GOAL_PATTERNS` domain (`analysis/goal_inferrer.py`) | `intelligence.domains` (**singular**) | `contacts, emails, events, tasks, drive` | `contact, email, event, task, file` | Goal-inference fast-path (strategy 1) inert for those domains; `drive` is not even a domain. |
| C | `valid_context_domains` (`orchestration/validator.py`) | `$context.<result_key>` (**result_key**) | `{…, drive}`, missing `files` | `{…, files}` | Legitimate `$context.files.0` references were **rejected** and the whole plan invalidated; the bogus `drive` (never emitted) was accepted. |
| D | `_detect_domain_from_agent_results` map (`context_resolution_service.py`) | `item.meta.domain` / `_derive_domain_from_type` (**result_key**) | `files→drive, weather, articles→wikipedia, results→perplexity` | `files, weathers, wikipedias, perplexitys` | `item_domain == detected_domain` (STRATEGY 3) never matched for file/weather/wikipedia/perplexity → domain-based ordinal reference resolution silently degraded. |

## Decision

**`DOMAIN_REGISTRY` is the single source of truth for the domain vocabulary.**
Each domain declares exactly one singular *name* (the registry key) and one
plural *result_key*. Every derived table carries a domain token on exactly one
of those two axes, chosen by what it is compared against at runtime — never a
legacy alias (`drive`), never the wrong number.

### 1. Permanent parity guard

`tests/unit/domains/agents/registry/test_domain_vocabulary_parity.py`
(modelled on `drafts/display.py::assert_registry_completeness`, ADR-085) derives
both axes from `DOMAIN_REGISTRY` and fails on any off-vocabulary token:

- **Strict, axis-aware** on the comparison-consumer tables — `CROSS_DOMAIN_MAPPINGS`
  target and `_GOAL_PATTERNS` domain must be canonical **singular** names;
  `VALID_CONTEXT_REFERENCE_DOMAINS` and `_DATA_KEY_TO_RESULT_KEY` values must be
  canonical **result_keys**.
- **Tolerant, non-orphan** on the definitional / display tables
  (`TYPE_TO_DOMAIN_MAP`, `CONTEXT_DOMAIN_*`, `HtmlRenderer` components): every
  token must resolve to a canonical domain, tolerating a small documented set of
  auxiliary result types (`calendar(s)`, `location(s)`, `mcp_app(s)`,
  `skill_app(s)`) and legacy display aliases (`drive`, `articles`, `search`) —
  which are NOT condition tests. A brand-new typo still fails.

The test was **RED** before the fixes (proving the plurals/legacy tokens) and is
**GREEN** after; it fails in the future on any new off-vocabulary token.

### 2. The four fixes

A, B, C, D per the table above. For C and D the previously-inline tables were
promoted to documented module constants (`VALID_CONTEXT_REFERENCE_DOMAINS`,
derived from `get_result_key`; `_DATA_KEY_TO_RESULT_KEY`) so they are importable,
testable and guarded. The masking unit tests (which fed plural domains to
`GoalInferrer.infer`) were corrected to the real singular runtime form.

### 3. Kill switch for the reactivated bypass (A)

Fixing A re-enables a code path that was effectively dead in production. Per the
"parameterizable ⇒ `.env`" rule, `CrossDomainBypassStrategy.can_handle` is gated
by the new setting **`planner_cross_domain_bypass_enabled`** (default `True`;
`.env*` updated). Flag OFF = fall back to the LLM planner (behaviour unchanged
from before the fix).

## Consequences

- Cross-domain reference queries bypass the LLM planner again (~800 ms and the
  multi-domain LLM tokens saved), with a prod kill switch.
- Goal inference, `$context.files` references and domain-based ordinal reference
  resolution work for all affected domains.
- Any future domain-vocabulary drift is caught at CI by the parity test.
- Out of scope (documented, not touched): the display alias maps
  (`html_renderer`, `text_summary`, `icons`, `detect_domain_from_item`) keep
  their defensive aliases — they are alias-tolerant lookups, not condition tests,
  and their misleading docstrings are noted for a separate cleanup.

Non-regression: full fast unit suite green (8800 passed, +23 new tests), Black /
Ruff / MyPy (strict, 865 source files) clean, wired services instantiate at
runtime. No migration.
