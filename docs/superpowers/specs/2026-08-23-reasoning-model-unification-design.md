# Reasoning Model Unification — one intent, a derived profile, a coercion contract — Design Specification

- **Date**: 2026-08-23
- **Status**: Approved design, pre-implementation. **Prototype built and validated** (§4).
- **ADR**: ADR-245 (companion to ADR-244)
- **Parent**: `2026-08-23-llm-model-policy-design.md` — this document owns the reasoning
  subsystem that §0 quater R1 of the parent proved untouchable by any registry import.
- **Origin**: the parent design excluded reasoning metadata from catalogue sync as a
  *precaution*. This document removes the need for the precaution by changing the model.

---

## 1. Why the current model resists

### 1.1 Measured surface

```
 31 SLOC  core/reasoning_types.py                  4 shapes in a discriminated union
223 SLOC  llm_config/reasoning_validation.py       cross-validation shape x widget
 99 SLOC  providers/reasoning_builders.py          7 builders + intra-family branching
353 SLOC  backend total
+ 261 / 64 / 50 lines of frontend (ReasoningWidget.tsx, reasoningHelpers.ts, reasoningDocText.ts)
+ 6 dedicated columns on llm_models, across 114 rows
```

### 1.2 Four structural defects

**a) The shape is *stored* per model instead of *derived*.** 114 catalogue rows describe about
six real behaviours. This is precisely what made the parent's R1 possible: an importable column
that no external source can fill correctly.

**b) "No reasoning" has four encodings.** Measured across every value present in the system:

```
{"effort": "off"}              21   DeepSeek / Anthropic-adaptive sentinel
{"effort": "none"}              8   OpenAI
ToggleBudget(enabled=False)    11   Qwen / Anthropic-manual
budget: 0                       0   declared sentinel, never used
```

**40 of the system's 46 values say the same thing three different ways.**

**c) Three authorities must agree** — the catalogue's `reasoning_widget`, the shape of the
stored JSONB, and the builder's `isinstance` check. A disagreement raises `RuntimeError` at
LLM instantiation. That is the failure mode R1 describes.

**d) Two parallel channels for the same output.** `LLMAgentConfig.reasoning_effort` produces
the Anthropic `effort` kwarg through `build_anthropic_reasoning`, **and**
`LLMAgentConfig.effort` produces it through `factory.py:365`. `additional_kwargs.update()`
means the builder silently wins.

**Dead weight**: the `budget_int` widget exists for 4 Gemini 2.5 models **no slot uses**, and
`ReasoningEffortBudget` appears nowhere in `LLM_DEFAULTS`.

---

## 2. State of the art — two gateways, one architecture

OpenRouter and Vercel AI Gateway converge on the same seven decisions:

| Decision | Both gateways |
|---|---|
| Intent | **one ordinal ladder**: `none < minimal < low < medium < high < xhigh (< max)`, plus a `provider-default` state |
| Alternative | a token budget, **mutually exclusive** with the level |
| Translation | **a function of (provider, family) in code** — no per-model stored data |
| Unsupported level | **coerced to the nearest + a warning**, never an error |
| Budget ↔ level | **a published ratio table, bidirectional**: `minimal≈10 %`, `low≈20 %`, `medium≈50 %`, `high≈80 %`, `xhigh≈95 %` of the output cap |
| Escape hatch | provider-native options with **explicit precedence** — *"never merged; providerOptions takes full precedence"* |
| Orthogonal concerns | separate fields (`exclude` = reason internally, do not return), outside the ladder |

**LIA is the exact inverse**: it stores everything and derives nothing.

---

## 3. The model

### 3.1 One value replaces four shapes

```python
LEVELS = ("provider_default", "none", "minimal", "low", "medium", "high", "xhigh", "max")

@dataclass(frozen=True)
class ReasoningIntent:
    level: Level = "provider_default"
    budget_tokens: int | None = None      # mutually exclusive with an explicit level
    exclude_from_output: bool = False     # orthogonal, ignored by families that lack it
```

### 3.2 The profile is derived — with one correction the harness forced

The first draft derived **everything** from the family. The validation harness refuted it: the
ladder is genuinely per-model (OpenAI documents *"supported values are model-dependent"*; `o1`
accepts `low/medium/high` but not `minimal/none`; `gpt-5.6` adds `max`). Measured: **29 ladder
divergences** between family defaults and curated catalogue values.

The corrected model separates two things the first draft conflated:

| | Nature | Source | If missing |
|---|---|---|---|
| **Family** — the *shape* of the translation | must never be wrong | **derived** from `(provider, model prefix)`, ordered rules | — (measured: **0 gaps** over 87 chat models) |
| **Ladder** — the accepted levels | affects the UI and coercion only | **optional per-model refinement** that can only *narrow* the family ladder | family ladder + coercion |

```python
@dataclass(frozen=True)
class ReasoningProfile:
    family: Family           # openai | anthropic_adaptive | anthropic_budget | gemini_level
                             # gemini_budget | deepseek_toggle | qwen_toggle_budget
                             # perplexity | none
    levels: tuple[Level, ...]
    supports_budget: bool
    budget_range: tuple[int, int] | None
    can_disable: bool        # improvement on the state of the art, see 3.4
    default_enabled: bool | None
    source: Literal["family", "model_refined"]
```

**Consequence: the catalogue becomes an optimisation, not a prerequisite.** An unknown model
works (family ladder + coercion) instead of raising `RuntimeError`. The 6 columns keep only an
optional narrowing role; none of them is load-bearing.

### 3.3 Coercion is a safety contract, not a convenience

The harness produced the decisive case. With ties broken **downward**:

```
deepseek-v4-flash, requested level="low", ladder ("none","high","max")
   tie-break down -> "none"    ==> reasoning SILENTLY DISABLED
   tie-break up   -> "high"
claude-opus-4-6,  requested level="minimal"
   tie-break down -> "none"    ==> reasoning SILENTLY DISABLED
   tie-break up   -> "low"
```

Downward coercion **re-creates R1's failure mode through a different door**. Two rules, both
enforced by tests:

1. **Ties break upward.** Doctrine already in the codebase: *"an uninformed guess must never
   under-budget a hard query"* (`utils/react_budget.py`).
2. **`none` is never a coercion target.** Only an explicit `level="none"` disables reasoning.

### 3.4 Three improvements on the gateways

1. **`can_disable`** — neither gateway models "reasoning cannot be turned off". LIA needs it:
   `gemini-3.5-flash` is `reasoning.mandatory=true` (OpenRouter, §0 quinquies of the parent), so
   an `ECONOMY` profile can never make it cheap. Without the field, a policy would believe it
   had a cheap mode and be wrong. Enforced invariant: a `can_disable=False` model **never**
   produces a disabling config.
2. **A typed escape hatch per family**, with the gateways' explicit precedence — instead of the
   untyped `provider_config` JSON.
3. **The admin UI derives from the same profile**: `levels` gives the buttons, `supports_budget`
   the numeric field, `can_disable` greys out "none". **One component replaces four renderers.**

### 3.5 The duplicate `effort` channel is removed

`LLMAgentConfig.effort` disappears; the Anthropic adaptive `effort` kwarg is produced by the
single translator, from `ReasoningIntent.level`. One field, one output, no precedence puzzle.

---

## 4. Validation — a prototype was built and run against production code

`resolve_reasoning_profile` + `coerce` + `translate` + `migrate` were implemented (**125 logical
SLOC**, against 353 replaced) and executed inside `lia-api-dev` against the live catalogue,
the live override cache and the **current builders**.

| Test | What it proves | Result |
|---|---|---|
| **T1 — golden equivalence** | For every slot, `stored value → migrate → resolve → translate` produces **byte-identical kwargs** to the current builder | **56 slots compared, 56 identical, 0 divergent** |
| **T2 — family coverage** | Every model the catalogue calls reasoning-capable resolves to a family | **0 gaps** over 87 chat models; 6 widenings, all corroborated as *catalogue* errors by the registry cross-check (`sonar-reasoning`, `sonar-reasoning-pro`, `o3/o4-mini-deep-research`, two `gemini-2.5-*-preview-09-2025`) |
| **T3 — coercion is a no-op on valid values** | Migration changes no behaviour | **139 currently-valid values, 0 coerced** |
| **T4 — exhaustive cross-product** | 87 models × 8 levels × 5 budgets | **3 480 combinations, 0 crashes** |
| **T5 — `can_disable` invariant** | A mandatory-reasoning model never gets a disabling config | **0 violations** |
| **T6 — migration totality** | Every stored value and every code default maps | **101 values, 0 failures** |
| **T7–T10 — extensibility** | see §5 | measured in lines |

Migration mapping, total and lossless — **46 values collapse to 7 targets**:

```
{"effort":"off"}             (21) -> level="none"
{"effort":"none"}            ( 8) -> level="none"
ToggleBudget(enabled=False)  (11) -> level="none"
{"effort":"high"}            ( 6) -> level="high"
{"effort":"minimal"}         (10) -> level="minimal"
{"effort":"low"}             ( 5) -> level="low"
{"effort":"medium"}          ( 1) -> level="medium"
ToggleBudget(True, 4096)     ( 3) -> budget_tokens=4096
ToggleBudget(True, 16384)    ( 2) -> budget_tokens=16384
null                         ( 1) -> level="provider_default"
```

---

## 5. Extensibility — measured, not asserted

| Scenario | Executed | Cost |
|---|---|---|
| **T7 — new model of a known family** (`gpt-5.7-nova`, absent from the catalogue) | resolves to `openai`, family ladder, `level=max` coerces to `xhigh`, translates correctly | **0 lines** |
| **T8 — new orthogonal mode** (OpenRouter's `context` / `mode`, GPT-5.6+) | added to the intent; `gpt-5.6-luna` emits them, `gpt-5.2` / `claude-opus-4-6` / `deepseek-v4-flash` ignore them **with no change** | **~6 lines** — 2 optional fields + 1 family predicate |
| **T9 — new provider with an unseen shape** (`mistral`, hypothetical `depth` 1–5) | one rule entry + one translation branch; the ladder and coercion work unchanged | **~8 lines** |

Today the same three scenarios cost, respectively: a curated catalogue row; a union class + a
widget enum value + a DB migration + a validation branch + a builder branch + a frontend
renderer + an i18n key; and all of that plus a provider adapter.

---

## 6. What ships, and what is deleted

**Added** (~125 backend SLOC + one frontend component):
`core/reasoning_intent.py` (the intent), `infrastructure/llm/reasoning/profiles.py` (the ordered
rules), `infrastructure/llm/reasoning/translate.py` (one branch per family),
`infrastructure/llm/reasoning/coerce.py`, a migration.

**Deleted**: `core/reasoning_types.py` (4 shapes), the shape × widget cross-validation in
`reasoning_validation.py`, the 7 builders in `reasoning_builders.py`, `LLMAgentConfig.effort`,
three of the four frontend renderers, and the `budget_int` dead path.

**Kept but demoted**: the 6 catalogue columns become an optional narrowing refinement; a NULL is
now valid and safe.

---

## 7. Risks and how each is closed

| Risk | Closure |
|---|---|
| A behaviour change on the hot path of 37 slots | **T1 golden harness becomes a permanent test**: every slot × its stored value, kwargs compared to a frozen golden captured before the change |
| A stale stored value after the migration | The migration is total (T6) and behaviour-preserving (T3); the old shapes are removed so no stale shape can survive |
| A family rule that is too broad | T2 runs in CI: a catalogue model with no family, or a family with no catalogue counterpart, fails the build. The 6 known widenings are an explicit allowlist with their evidence |
| Coercion silently degrading quality | Ties break upward, `none` is never a target, and every coercion is logged and counted (`llm_reasoning_coerced_total{model,from,to}`) |
| A `mandatory` model treated as having a cheap mode | T5 invariant, plus the parent's cost estimate rule (§0 quinquies) |
| The frontend and backend ladders drifting | Both read the same profile, served by `/llm-config/metadata`; a contract test pins them |

---

## 8. Delivery

Inserted into the parent's plan as **Lot 0c**, after 0b (which adds `llm_type`) and **before
Lot 1** — Layer 1's `effort_intent` mapper is this model, so building Layer 1 first would mean
building it twice.

| Step | Content |
|---|---|
| 0c.1 | Capture the golden: every slot × stored value → current kwargs, frozen as a fixture |
| 0c.2 | `ReasoningIntent`, `ReasoningProfile`, the ordered rules, `coerce`, `translate` |
| 0c.3 | Migration of the 37 DB rows and the 31 code defaults; removal of `LLMAgentConfig.effort` |
| 0c.4 | Adapter switched to the single translator; the 7 builders deleted |
| 0c.5 | One frontend component; three renderers deleted; i18n ×6 |
| 0c.6 | Catalogue columns demoted to optional; T2 coverage guard in CI |

Acceptance: T1–T6 green as permanent tests, `task ci:fast` green, and a runtime probe showing
the 37 slots resolving to the same provider kwargs as before the change.
