# LLM Model Policy — bounded, deterministic model selection per slot — Design Specification

- **Date**: 2026-08-23
- **Version**: v3.3 — two adversarial rounds, price-sync removal, primary-source review (§0 to §0 quinquies)
- **Status**: Approved design, pre-implementation
- **ADR**: ADR-244 (to be written in Lot 0 — ADR-243 is the OLED display mode, shipped in v1.31.3)
- **Origin**: a proposal to add a "god mode" delegating model choice to the agents themselves
- **Verdict**: the objective is right, the mechanism is not. A deterministic, bounded
  **policy** replaces the proposed autonomous **agent** — same goal, measured cost, no loss
  of reproducibility.
- **Patterns mirrored**: `infrastructure/adaptive/threshold_controller.py` (hard bounds,
  hysteresis, kill-switch), `domains/feature_switches/registry.py` (two bounds, smallest
  wins), registry completeness assert (ADR-085), published-constraint doctrine (ADR-184),
  shrink-only allowlist (ADR-155), conservative-fallback doctrine (`utils/react_budget.py`),
  reviewable-import doctrine (`domains/llm/pricing_import_service.py`)

---

## 0. What changed in v2

v1 was written from repository evidence and the dev database alone. v2 adds an external
practice review (10 sources, §2.8) and six new measurements. Three of v1's conclusions were
**wrong** and are corrected here.

| # | Change | Cause |
|---|---|---|
| 1 | **§2.1 recomputed.** The blocking/background split is 43.7 / 44.3 / 8.5, not 64.7 / 35.3 | v1 mis-filed `initiative` (11.9 % of spend) as background; it runs *before* `response` |
| 2 | **`cache_locality` no longer drives the move interval.** Uniform 24 h; one rule instead: never move inside a burst | measured: 89 % of cached tokens come from calls under 5 min apart — LIA's cache is a *burst* cache |
| 3 | **The context-window fix is rewritten.** v1 preferred `MODEL_CONTEXT_WINDOWS` on `declared` provenance — but that table is itself wrong on 10 of its 56 entries | cross-check against two public registries |
| 4 | **Layer 0 becomes an import, not a curation.** Two public registries fill ~104 of 114 models | LiteLLM (MIT) + models.dev |
| 5 | **Deprecation becomes an eligibility criterion** | 17 active models are already past their deprecation date |
| 6 | **Switch-spend budget** replaces the calendar bound per locality | DigitalOcean cache-aware router |
| 7 | **The A/B campaign is promoted** from optional Lot 5 to an activation condition of Layer 2 | *"a quality score sliding while the error rate stays at zero is the signature of a silent regression"* |
| 8 | **Pilot metric** is `cost-per-successful-task`, not cost per call | routing practice literature |
| 9 | **Cascade and semantic cache** added as argued non-goals with re-examination conditions | arXiv 2605.06350; production semantic-cache hit-rate data |
| 10 | **Three catalogue mechanisms specified** (initial correction, continuous correction, create/edit assist) | requested |

---

## 0 bis. Adversarial review (v2 → v3)

v2 was red-teamed claim by claim. **Nine defects were found — two in the analysis itself, seven
in the design.** Everything below is a correction, not a refinement.

### Defects in the v2 *analysis*

**A1 — Registry matching was provider-blind.** v2 matched a model id against the registries by
name alone. models.dev publishes **193 providers**, many of which republish the same id with
different metadata: `deepseek-v4-flash` appears under **23 providers** with output caps from
32 768 to 1 048 576 and prices from 0 to 0.396; `jiekou` declares `gpt-5.2` as
`reasoning=False, temperature=True`, the opposite of the canonical `openai` entry. LiteLLM's
suffix index had the same weakness.

Consequences: coverage was overstated (**97/114**, not ~104 — LiteLLM 95, models.dev 60), and
the capability-divergence lists were contaminated. **This is also a design hazard**, not just
an analysis bug: a naive import would ingest resale providers' metadata. §5.1 now locks the
canonical provider.

**A2 — The headline saving ignored time-slot pricing.** v2 priced everything at DeepSeek's
base (off-peak) rate. Measured: **30.1 % of background spend falls inside the peak windows**
(01:00–04:00 and 06:00–10:00 UTC, ×2). Corrected figures below. LIA's own accounting is
correct (`pricing_cache.py:453` applies `find_active_slot`) — only the simulation was wrong.

| | v2 (wrong) | v3 (time-aware) |
|---|---|---|
| Baseline | 25.90 USD | **27.80 USD** (+7.3 %) |
| **S1** background right-sizing | −36.4 % | **−32.4 %** |
| **S1′** S1 + background jobs shifted off-peak | — | **−36.7 %** |
| S2 balanced | −49.8 % | −45.8 % |
| **S0** scheduling alone, no model change | — | **−2.7 %** |

S0 is a **new, free lever**: moving background jobs out of the peak windows saves 2.7 % with
no model policy at all (§6.5).

### Defects in the v2 *design*

**D1 — No numeric-compatibility gate.** The eligibility gate checked capabilities and kind but
never that the slot's configured `max_tokens` fits the candidate's `max_output_tokens`.
`compaction` and `journal_consolidation` both request **50 000** output tokens; several
catalogue models cap far below. Fixed in §6.2.

**D2 — The gate would have rejected explicit configuration.** `vision_analysis`'s own default
model is `gpt-5-mini`, which the LIA catalogue declares `supports_vision=false` (only 12 of 87
chat models declare it true, against 55 more per the registries). Shipping the gate before the
import would reject the slot's own default and break image analysis. **The gate now filters
policy candidates only; an explicit choice (code default or admin override) is warned about,
never substituted.** §5.2.

**D3 — Deactivating a model is not a benign UI change.** A model removed from `is_active`
disappears from `ModelCapabilitiesCache`, so `get_model_profile` falls back to
`CONSERVATIVE_DEFAULT` (`model_profiles.py:127`): `is_reasoning_model=False`,
`supports_temperature=True`, `max_input_tokens=8192`. The adapter would then **send sampling
parameters to a reasoning model → provider 400**, and the compaction threshold would collapse.
Migration rule added in §5.1: never deactivate a model referenced by a live
`llm_config_overrides` row **on that instance** — retarget first, deactivate second. (Verified
on the dev instance: **0 of 38 explicit slot models** point at one of the 17 deprecated ids.)

**D4 — Storage contradiction on the controller's effective index.** §6.2 placed it in the
in-memory/DB cache family while §9 described a Redis flush resetting it. Resolved: the index
is **durable in PostgreSQL**, mirrored in memory like `LLMConfigOverrideCache`. A Redis flush
silently reverting a slot's model would be a silent configuration change — forbidden.

**D5 — "MANUAL is byte-for-byte today's behaviour" was false for Lot 0a.** The context-window
correction changes *derived* values even under `MANUAL`: with `COMPACTION_THRESHOLD_RATIO=0.4`
and `COMPACTION_TOKEN_THRESHOLD=0`, an instance whose `response` slot is `gpt-5.2` currently
compacts at **3 277 tokens** and would compact at **108 800** after the fix (×33). The claim is
now scoped precisely in §10: `MANUAL` guarantees identical **provider/model/parameter
resolution**; Lot 0a deliberately corrects derived thresholds, and each correction is measured
and announced. For the **reference seed** (`response` = `deepseek-v4-flash`, already 1 000 000)
the threshold does not move at all.

**D6 — Campaign replay sends user content to a candidate provider.** The A/B harness replays
real user inputs; a candidate may be a provider that instance has never sent data to. Consent
constraint added in §7.3.

**D7 — Controller cost estimates must be time-slot aware.** Estimating with base prices
under-costs a time-slotted model by ~30 % on background traffic. The controller must price
through `pricing_cache.get_cached_cost_usd_eur`, never from base columns. §7.2.

### Claims that survived the review

| Claim | Attack | Result |
|---|---|---|
| Burst cache = 89 % under 5 min | Partition ignored `user_id` across 20 distinct users | **88.6 %** per-user — holds |
| Context windows wrong on 5 of 7 in-use models | Provider-blind matching | Confirmed under strict matching |
| 17 deprecated models are safe to deactivate | Only code references were checked | Also **0 references** in the dev DB's 38 explicit slot models |
| The import is safe for the current configuration | Could it *narrow* a capability and break a gate? | **0 narrowing changes** on in-use models — every change widens |
| LIA under-bills time-slotted models | Read `pricing_cache.py:453` | **No defect** — `find_active_slot` is applied |
| Meta-LLM disqualification | — | Unaffected |

---

## 0 ter. Price synchronisation removed (v3 → v3.1)

v3 still carried prices as *proposals* in a review queue. That is now **deleted**: prices are
100 % manual, through the pricing sheet that already exists
(`domains/llm/pricing_import_service.py`, `AdminLLMPricingSection`).

The decision is measured, not stylistic. Two registry snapshots of LIA's own catalogue were
diffed — 2026-06-21 against 2026-08-22, a two-month window:

```
models present at both dates and price-STABLE : 85 / 87
models present at both dates and price-CHANGED:  2 / 87
```

And the two "changes" are **not price moves at all**:

```
deepseek-v4-flash   input 0.1400 -> 0.4400   output 0.2800 -> 1.3200   cache 0.0028 -> 0.0140
deepseek-v4-pro     input 0.4350 -> 1.3200   output 0.8700 -> 3.9600   cache 0.0036 -> 0.0440
```

The August values are **exactly LIA's peak-window tariff** (`time_slots`), the June ones a
third tier again. The registry did not observe a provider raising prices; it switched which
tier it publishes. A proposal engine would have raised **two alerts, both false, and zero true
positives** — on the single model family where LIA's own data is already richer than the
registry's (ADR-223 time slots).

**Verdict: negative signal-to-noise.** Price sync is removed from every mechanism. What remains
is a completeness check on LIA's *own* data, needing no registry at all: **a candidate with no
active `llm_model_pricing` row cannot be cost-arbitrated and is therefore ineligible**
(measured today: 6 of 87 chat models — two 2024 Claude snapshots, one Ollama tag, three legacy
Perplexity Sonar ids).

Consequences: the registry import covers **capabilities only**; class B of the continuous sync
narrows to deactivations and overwrites of `verified` capability values; the multi-tier flag,
the promo caveat and the price-precedence rows disappear from §5.1 — they no longer describe
anything the system does.

---

## 0 quater. Second adversarial round (v3.1 → v3.2)

A second red-team attacked six surfaces the first round never touched. **Two critical defects,
two design corrections, four claims verified as sound.**

### R1 (CRITICAL) — importing reasoning metadata would silently switch reasoning ON across the pipeline

`deepseek-v4-flash` carries, in LIA, `reasoning_widget=enum` with values
`["off", "high", "max"]`. models.dev declares
`reasoning_options = [{type: "toggle"}, {type: "effort", values: ["low", "high", "max"]}]` —
**`off` does not exist in it**, and the first option would map the widget to `toggle_budget`.

Either mapping makes the stored `{"effort": "off"}` incompatible, so
`_reconcile_reasoning_effort` drops it to `None` and the model's own default applies — which
for DeepSeek is thinking **ON**. Executed against the live configuration:

```
slots whose reasoning_effort would become INVALID after a naive import : 21
  response . query_analyzer . planner . react_agent . semantic_validator . query_agent
  browser_agent . mcp_react_agent . mcp_description . subagent . psyche_summary
  memory_extraction . memory_reference_extraction . memory_reference_resolution
  open_loop_extraction . interest_extraction . journal_extraction
  hitl_question_generator . hitl_plan_approval_question_generator
  broadcast_translator . skill_description_translator
```

That is the whole conversational pipeline plus most of the background, silently switching to
reasoning mode — a cost and latency regression with no error anywhere. It is precisely the
incident `merge_config`'s own docstring records for 2026-07-27, at **seven times the scale**.

**Fix (short term): reasoning metadata is never auto-imported.** **Fix (structural, ADR-245):**
the stored per-model shape disappears entirely — the translation family is *derived* from
`(provider, model prefix)` and the catalogue keeps only an optional narrowing role. With no
stored shape there is nothing for an import to corrupt, so R1 stops being a precaution and
becomes impossible by construction. Prototype validated; see the companion spec.

In detail: `reasoning_widget`,
`reasoning_enum_values`, `reasoning_budget_range` and `effort_values` join prices and the
sampling flags as **LIA-owned**. models.dev may *propose* them inside the create/edit assist,
where a human sees the value before saving; the sync must never write them.

Consequence, stated honestly: models.dev's headline contribution shrinks. It keeps
`supports_temperature` (unique, 97 %) and better coverage on `tool_call` / `attachment`, so it
stays a second source — but it no longer solves the reasoning-widget problem, which stays
manual.

### R2 (CRITICAL) — the controller cannot aggregate per slot, and `node_name` leaks prompt text

The controller's core query is "the last N calls for slot X". **`token_usage_logs` has no slot
column.** It stores `node_name`, which does not map to slots:

| Reality | Consequence |
|---|---|
| `react_call_model` → slot `react_agent` | rename, no mapping table exists |
| `planner`, `planner_single_domain`, `planner_multi_domain` → slot `planner` | three names, one slot |
| `proactive_briefing` → slot `briefing`, `proactive_interest` → `interest_content` | rename |
| `proactive_heartbeat` → `heartbeat_message`? `heartbeat_decision`? | **ambiguous** |
| `MCP Iterative: <server>` → slot `mcp_react_agent` | **unbounded**, carries a server name |
| `sub-agent: <prompt prefix>` → slot `subagent` | **unbounded**, carries truncated prompt text |
| `unknown` | 44 calls attributed to nothing |

Measured: **101 distinct `node_name` values in the database, 24 of them `sub-agent:` variants
and 4 `MCP Iterative:` variants.** And these values are Prometheus labels
(`llm_api_calls_total`, `llm_api_latency_seconds`, `llm_cost_total`,
`agent_node_duration_seconds`): **113 label values live in Prometheus, 28 unbounded**, several
carrying French prompt fragments exported to Grafana.

Two problems, one of them live today and independent of this project:

1. **Unbounded metric cardinality** — every new sub-agent prompt creates new time series across
   several metrics.
2. **Prompt content in a metric label and a DB column** — worse than a log line, because it is
   scraped, retained and rendered.

**Fix**: `token_usage_logs` gains an **`llm_type`** column (the slot, from the closed
`LLM_TYPES_REGISTRY` vocabulary), written next to the existing `node_name`. The controller
aggregates on `llm_type`; `node_name` stays exactly as it is for the debug panel. Ships in Lot
0b beside the other observation columns, with a backfill only where the mapping is
unambiguous — never guessed for `proactive_heartbeat` or `unknown`.

Separately, and as a **prerequisite recorded in the ADR rather than solved here**: the
unbounded label values must be bounded at the metric boundary (server key and sub-agent id
instead of free text). This is a pre-existing defect; the spec names it and does not pretend to
own it.

### R3 — `supports_streaming` also stays LIA-owned

`streaming` is a pure function of the slot (`response`, `hitl_question_generator`,
`hitl_plan_approval_question_generator` — `factory.py`). All 87 chat models currently declare
`supports_streaming=true`, but that is the **column default**, and LiteLLM's
`supports_native_streaming` covers only 42 %. Importing it could flip a model to `false` and
break SSE on `response`. It joins the never-imported set, and the eligibility gate additionally
requires `supports_streaming` for those three slots.

### R4 — the effective index must be keyed on (slot, **profile**)

v3.1 stored one index per slot and applied it as `candidates[profile][index:]`. Index 2 of
`ECONOMY` is a different model from index 2 of `QUALITY`, and the lists have different lengths,
so a profile change would carry a meaningless offset — or overflow. **Fix**: the index is keyed
`(slot, profile)`; a profile never visited starts at 0; the audit trail already records the
profile alongside every move.

### Claims verified as sound in this round

| Claim | Test run | Result |
|---|---|---|
| `MANUAL` resolution is identical to today | `merge_config(defaults, override)` vs `get_llm_config_for_agent` over **all 58 slots**, live catalogue and override cache loaded | **0 divergences** — including the subtle case where a slot has no override and v3.1's pseudo-code adds a reconciliation pass the current code skips |
| No in-scope slot depends on `provider_config` | queried every override outside the 3 non-chat slots | **0 rows** — a provider switch cannot invalidate provider-specific JSON |
| A non-streaming model could be picked for `response` | catalogue scan | not possible **today** (87/87 stream); R3 keeps it that way |
| The vision gate exposure is real | `gpt-5-mini` (code default of `vision_analysis`) vs `gemini-3.5-flash` (seeded effective) | **refined**: the seeded configuration passes (`vision=true`); the exposure is a **seedless install or the admin "Reset" button**, which restores `LLM_DEFAULTS` and lands on `gpt-5-mini` (`vision=false`) |

### Second accepted limitation — the controller will be sparse at this volume

Measured over 30 days, calls per node:

```
>= 200 (nominal window) :  3 nodes   (one of them out of scope: embedding_embed_query)
50-199 (bare minimum)   : 15 nodes
10-49  (insufficient)   :  4 nodes
< 10   (inert)          :  7 nodes
~24 of the 53 in-scope slots have NO traffic at all in 30 days
```

At 117 `response` calls per 30 days, a 200-call window takes about **51 days** to fill; most
slots never fill one. **Layer 2 will therefore act on roughly five slots and make a handful of
moves per quarter** — the busiest ones, which are also where the spend is
(`proactive_briefing` 984, `memory_reference_extraction` 285, `proactive_heartbeat` 189,
`journal_consolidation` 165, `query_analyzer` 144).

This is not fatal, but the design must not promise more autonomy than the data can feed. Two
consequences, both binding:

1. The window is **count-bounded AND time-bounded**; a slot below `min_window_calls` is
   reported on the autopilot screen as **"insufficient evidence"**, never silently skipped —
   the operator must be able to see that the controller is idle *because there is no data*,
   not because it decided nothing was wrong.
2. **Layer 1 carries the value** (S1 = −32.4 %, no controller needed). Layer 2 is an
   optimisation on top, and its business case rests on the five busy slots — not on the 53.

### Install contract — verified unaffected by the dead-slot removal

Removing `router` and `context_resolver` from `CURRENT_CORE_LLM_TYPES` was asserted safe in
v3; it is now measured. Both resolve to `openai`, which four surviving core slots also resolve
to, so the derived set is unchanged:

```
required providers before : ['deepseek', 'openai']
required providers after  : ['deepseek', 'openai']
declared constant         : ['deepseek', 'openai']   -> no change, questionnaire untouched
```

### Accepted limitation, stated rather than hidden

**A candidate's latency cannot be pre-verified.** Prometheus holds 15 days and only ever
measured the models actually configured (2 of 114). The gate therefore cannot check a candidate
against a slot's `timeout_seconds` (300 s on `browser_agent`, `subagent`,
`mcp_app_react_agent`; 250 s on `journal_consolidation`) before trying it. The honest safety net
is the controller's **immediate, non-rate-limited step-up on `failure_kind=timeout`** (§7.2),
plus the campaign harness measuring latency on replayed inputs before a move. This is a real
residual risk, documented rather than engineered away.

---

## 0 quinquies. Primary-source review of the three exclusions

The three things this design refuses to import — **prices** (§0 ter), **reasoning metadata**
(§0 quater R1) and **candidate latency** (accepted limitation) — were re-examined against
primary and adjacent sources rather than aggregators. All three exclusions are confirmed; two
gain a much stronger rationale, and one third registry earns a narrow role.

### Reasoning metadata — the exclusion is structural, not precautionary

Provider documentation shows five **different API shapes**, none of them a shared vocabulary:

| Provider | API contract |
|---|---|
| OpenAI | `reasoning.effort` ∈ `none, minimal, low, medium, high, xhigh, max` — a model-dependent subset |
| Anthropic | `effort` plus `thinking`; adaptive family vs explicit `budget_tokens` family |
| DeepSeek | `thinking: {type: enabled\|disabled}` — a boolean, and it **defaults to enabled** |
| Gemini | `thinking_budget` (int) up to 2.5, `thinking_level` (enum) from 3.x |
| Qwen | `enable_thinking` (bool) + `thinking_budget` (int, 1–32768, default 4000) |

LIA's own code already encodes exactly this, as a deliberate abstraction:
`providers/reasoning_builders.py` maps `"off"` → `{"thinking": {"type": "disabled"}}` for
DeepSeek V4 and documents its enum as *"the 3 effective"* values; the Anthropic builder calls
`"off"` an **enum sentinel**. In other words `reasoning_enum_values` is **LIA's control
vocabulary**, not a description of any provider's API — so no external catalogue can be
authoritative for it, by construction.

The decisive measurement: three catalogues, three vocabularies, same model.

```
deepseek-v4-flash — supported reasoning efforts
  LIA         : ["off", "high", "max"]      (sentinel + the 2 LIA exposes)
  models.dev  : ["low", "high", "max"]
  OpenRouter  : ["xhigh", "high"]
```

Each describes its own gateway's contract. Only LIA's is consistent with LIA's own builder.
**R1's fix is structural**, and would have been needed even if the values had happened to match.

### Prices — there is no primary source to switch to

- **Neither OpenAI nor Anthropic publishes an official machine-readable pricing endpoint.**
  Every programmatic source available is a third party scraping the same public pricing pages —
  the same class of source as LiteLLM, with the same tier and promotion problems (§0 ter).
- OpenRouter's prices are **reseller** prices. For `deepseek-v4-flash` it lists **17 endpoints**
  priced from `0.0000000517` to `0.00000044` per token — an **8.5× spread**, and **DeepSeek
  itself is not among them**.

There is nothing better than the admin pricing sheet to move to. The exclusion stands, now for
a stronger reason than churn alone.

### Candidate latency — no external source exists; the probe is the answer

| Source | Verdict |
|---|---|
| **Artificial Analysis** | Publishes TTFT and output speed as a P50 over 72 h, 8 runs/day on 1k–10k workloads. **No public API, no data export**, reuse terms unstated. Measures *its own* endpoints. |
| **OpenRouter `/models/{id}/endpoints`** | The schema *does* carry `latency_last_30m`, `throughput_last_30m`, `uptime_last_{5m,30m,1d}`. Verified on 3 models / 28 endpoints: **latency and throughput are `null` in every one**. And the endpoints are resellers — for `gpt-5.2` the list is Azure and OpenAI, for `deepseek-v4-flash` seventeen intermediaries and no DeepSeek. |

**The limitation is irreducible from outside.** The answer stays the internal one already in the
design: the campaign harness (§7.3) measures the candidate's latency on replayed real inputs
before any move, and `failure_kind=timeout` triggers an immediate, non-rate-limited step-up
after one. What changes is the confidence: this is no longer "we could not find a source", it is
"there is no usable source, and here is what was checked".

### OpenRouter earns a narrow role: cross-check, never an import

Two facts it carries that neither other catalogue does, both directly useful to the policy:

- **`reasoning.mandatory`** — whether reasoning can be disabled at all. Measured:
  `gemini-3.5-flash` is **`mandatory: true`**, so an `ECONOMY` profile can never turn its
  reasoning off. A policy that assumes every model has a cheap mode is wrong about that model.
- **`reasoning.default_enabled`** — varies *within* a provider (`gpt-5.6-luna` true,
  `gpt-5.4-mini` false), which is exactly the fact that makes a dropped `effort` dangerous.

It is nonetheless **reseller-contaminated**: a model's top-level `supported_parameters` differs
from its per-endpoint list (`deepseek-v4-flash` shows all four sampling parameters at model
level but only `temperature` and `top_p` on the StreamLake endpoint), and
`claude-opus-4-6` and `qwen3.5-plus` are absent entirely. So OpenRouter is wired into the
**create/edit assist as a third opinion shown to the human**, and never into the sync.

### One more thing this surfaced

OpenRouter reports **no sampling parameters at all** for `gpt-5.2`, `gpt-5.6-luna` and
`gpt-5.4-mini`, while LIA's catalogue carries `supports_temperature=true` for them — the column
default, never curated. No live defect, because the adapter's `is_reasoning_model` filter strips
sampling parameters before the call. But it confirms that the four sampling columns are
**unreliable by default across the whole GPT-5 family**, which is why they stay LIA-owned and
why the admin UI's "raw truth" philosophy is, today, aspirational rather than realised.

---

## 1. Goal

Exploit the model catalogue LIA already pays for — **9 provider keys, 114 active models,
6 models actually used across 58 slots** — without giving up the determinism, the
reproducibility and the auditability of the current static configuration.

Explicitly **not** a goal: an LLM that chooses models. §2.5 disqualifies it with measurements.

---

## 2. Evidence base

Every figure was produced against this repository, against the **52 708 real LLM calls** in
the dev database (`token_usage_logs`, 2026-01-31 → 2026-08-23, 90-day window unless stated),
or against a downloaded snapshot of the two public registries. No figure is estimated.

### 2.1 Where the money actually goes

Classification by **graph position**, not node name. `initiative` runs *before* `response`
(`graph.py:784`, agents → initiative → response), so the user waits for it; the six
post-response extractions are fire-and-forget (`nodes/post_response_extractions.py`), so the
user never does. v1 mis-filed `initiative` and reported 64.7 / 35.3.

| Class | Calls | Cost (90 d) | Share |
|---|---|---|---|
| **Chat-blocking** (react, response, query_analyzer, planner, semantic_*, **initiative**, memory refs, HITL, MCP/skill loops) | 9 525 | 8.50 EUR | **43.7 %** |
| **Background** (post-response extractions, journals, interests, heartbeat, scheduled) | 4 118 | 8.62 EUR | **44.3 %** |
| **User-facing off the chat path** (dashboard briefing, split endpoint) | 1 716 | 1.66 EUR | 8.5 % |
| Unattributed (`node_name='unknown'`) | 44 | 0.68 EUR | 3.5 % |

Roughly half and half. Layer 1 (per-slot right-sizing, no per-request switching) therefore
matters on the blocking path too; Layer 2's offline controller is the only mechanism that
reaches the 52.8 % nobody is waiting on.

### 2.2 Prompt caching — LIA's cache is a *burst* cache

Recomputed from catalogue pricing, same models, cache kept vs lost:

```
baseline (real models, current caching) : 22.30 USD
same models, prompt cache LOST          : 30.33 USD   (+36.0 %)
```

v1 stopped there and concluded that `cross_turn` slots must move rarely. The external
sources disagreed with each other — DigitalOcean measured a single switch on a 90 k-token
cached agent session costing **1.6× more** despite a lower per-token rate, while LiteLLM
measured **99.3 % of switch-backs still warm** at a 1-hour TTL over 4 684 real switches. So
the effective cache horizon was measured **on LIA's own data**:

| Gap since the previous call on the same (node, model) | Calls | % cached |
|---|---|---|
| < 5 min | **11 602** | **57.7 %** |
| 5 min – 1 h | 1 574 | 26.0 % |
| 1 h – 6 h | 1 295 | 20.6 % |
| 6 h – 24 h | 666 | 25.9 % |
| > 24 h | 234 | 16.4 % |

**89 % of all cached tokens come from calls less than 5 minutes apart** (81–100 % per model).
The dev database holds **20 distinct users**, so the partition was re-derived per
`(node, model, user_id)` to rule out cross-user adjacency: **88.6 %** — the conclusion holds.
LIA's prompt cache is not a persistent cross-turn cache; it is a **burst** cache that works
because calls cluster (a conversation, a batch job).

```
extra cost if the burst is broken (per-request switching) : 7.41 USD / 90 d  (+33.2 %)
extra cost if the cache is lost entirely                  : 8.07 USD / 90 d  (+36.2 %)
  -> 92 % of the cache's value lives inside bursts

cost of a DURABLE move = one burst re-warm
  3 843 bursts / 90 d, 6 901 cached tokens per burst on average -> ~0.0015 USD
```

**A durable move costs ~0.0015 USD; per-request switching costs 7.41 USD over 90 days — a
ratio of about 1 : 5 000.** The governing rule is therefore not a taxonomy of localities:

> **Never change a slot's model inside a burst.** An offline controller running outside
> traffic hours satisfies this by construction.

`cache_locality` survives only as **diagnostic information** on the admin screen. The move
interval becomes uniform (24 h): what must be slow is statistical confidence, not the cache.

### 2.1 bis The decision table: class × cache locality

| Class | Cache locality | Cost | Share | Freedom to move |
|---|---|---|---|---|
| Background | `none` | 8.62 EUR | 44.3 % | free |
| Chat-blocking | `none` | 4.03 EUR | 20.7 % | free (SLA-bounded) |
| Chat-blocking | `intra_turn` | 3.88 EUR | 20.0 % | once per run, pinned for the run |
| Briefing | `none` | 1.66 EUR | 8.5 % | free |
| Chat-blocking | `cross_turn` | 0.58 EUR | **3.0 %** | rare moves only |

**73.5 % of the spend carries no cross-turn cache at all**, and the constrained family is
only 3.0 %.

### 2.3 The size of the prize — measured on realistic policies

Not theoretical bounds: actual per-slot policies replayed over the real 90 days.

> **Note on the baseline.** §2.2 recomputes 22.30 USD over the 58 (node, model) groups whose
> model carries active catalogue pricing; this section recomputes over 73 of the 74 groups,
> using a hand-completed price table so that no scenario is advantaged by a group silently
> dropping out, **and applying DeepSeek's UTC time slots per call hour** (peak 01:00–04:00 and
> 06:00–10:00, ×2 — `pricing_time_slots.py`). v2 omitted the slots and understated the
> baseline by 7.3 %; 30.1 % of background spend falls inside a peak window.

| Scenario | Cost | Δ |
|---|---|---|
| Current baseline (time-aware) | 27.80 USD | — |
| **S0 scheduling only** — background jobs shifted off-peak, **no model change at all** | 27.05 USD | **−2.7 %** |
| **S1 conservative** — background slots move down, **chat path untouched** | **18.79 USD** | **−32.4 %** |
| **S1′ = S1 + S0** | **17.61 USD** | **−36.7 %** |
| S1″ background → `gpt-5.6-luna` (no time slots at all) | 19.30 USD | −30.6 % |
| S2 balanced — plus non-critical blocking slots | 15.05 USD | −45.8 % |
| S3 aggressive — everything on the cheapest capable model | ~2.9 USD | ≈ −89 % |
| S4 quality chat — blocking path moved *up* | ~59 USD | **≈ +129 %** |

**S1 is the target: −32.4 % from Layer 1 alone**, no controller, no judge, no risk to the
conversational path, no cache impact (background is `none` locality). **S1′ reaches −36.7 %**
by adding a scheduling change that costs nothing (§6.5). Both sit inside the 40–85 % range the
literature reports. S4 is equally informative: the `Quality` profile costs **≈ +129 %**, and
the admin must see that price before choosing it.

> **S1″ matters for a different reason.** During a peak window DeepSeek's input price (0.44)
> exceeds `gpt-5.6-luna`'s (0.20), so the cheapest model is **not constant in time**. The
> policy nonetheless stays time-invariant — one model per slot — because switching by the hour
> would break the burst cache (§2.2) for a gain smaller than S0 delivers by rescheduling.

### 2.4 The catalogue is partly fiction — and so is the hand-maintained table

| Fact | Measurement |
|---|---|
| Models carrying the column defaults `max_input_tokens=8192 / max_output_tokens=4096` | **89 / 114** active (70 / 87 chat) |
| `get_effective_context_window("gpt-5.2")` | **8 192** |
| Entries of `MODEL_CONTEXT_WINDOWS` that diverge from the public registries | **10 / 56**, up to ×5 |
| Already-*curated* LIA rows that diverge | 4, incl. `gpt-5.6-luna` at 1 047 576 vs a measured 922 000 |

On the models LIA **actually uses**, the two independent registries agree with each other and
LIA is wrong on 5 of 7:

| Model | LIA today | LiteLLM | models.dev | Verdict |
|---|---|---|---|---|
| `gpt-5.2` | **8 192** | 272 000 | 272 000 | LIA wrong ×33 |
| `claude-opus-4-6` | **8 192** | 1 000 000 | 1 000 000 | LIA wrong ×122 |
| `gpt-5.4-mini` | **8 192** | 272 000 | 272 000 | LIA wrong ×33 |
| `qwen3.5-plus` | **8 192** | 991 808 | 1 000 000 | LIA wrong ×121 |
| `gpt-5.6-luna` | **1 047 576** | 922 000 | 922 000 | LIA over by 13.6 % |
| `deepseek-v4-flash` | 1 000 000 | 1 000 000 | 1 048 560 | agree |
| `gemini-3.5-flash` | 1 048 576 | 1 048 576 | 1 048 576 | agree |

`gpt-5.6-luna` is the direction that hurts: the reference seed pins it on 11 of 42 slots, and
an over-estimated window means compaction fires too late, i.e. a context overflow.

This drives the compaction threshold (`compaction_service.py:152`). It is a **live defect
today**, masked only because the reference seed pins `response` to `deepseek-v4-flash`.

### 2.5 Why a meta-LLM selector is disqualified

```
median cost of a full run            : 0.00102 EUR
mean cost of ONE query_analyzer call : 0.000517 EUR
```

A selection call priced like the pipeline's smallest slot is **+50 % of the median turn's
cost**. Latency: `router_v3` p50 = **3.5 s** (Prometheus). One extra round trip is **+1 to
+3.5 s of TTFT on every message**. The literature agrees independently: *"the inference
latency of the routing model is at least at the same level as that of single LLMs"* and
*"most production routing is conditional logic"*.

### 2.6 There is no quality signal today

| Source | State |
|---|---|
| `infrastructure/llm/evaluation_pipeline.py` | exported in `__init__.py`, **never instantiated**, zero callers, zero tests |
| `evaluator_pipeline_send_to_langfuse` | exists, default `False`; the pipeline never calls Langfuse anyway (Prometheus histogram only) |
| Langfuse | `LANGFUSE_ENABLED=false` in `.env` and `.env.example`; `profiles: ["langfuse"]`, opt-in; **no container running** |
| Human thumbs on ordinary answers | wired (`conversations/router.py:236`), persisted with `run_id`, joinable to `token_usage_logs.run_id` (join verified) — but **1 verdict in the entire dev database** |
| Latency | **not persisted**; Prometheus only, 15-day retention, only **2 of 114 models** have data |

Judge cost is **not** the obstacle — measured on real volumes (800 `response` nodes / 90 d,
529-token average answer, two judges):

| Judge model | 1 call | 100 % of answers | 5 % | Share of the 90-day bill |
|---|---|---|---|---|
| `qwen3.5-flash` | 0.000087 USD | 0.14 USD | 0.007 USD | **0.63 %** |
| `deepseek-v4-flash` | 0.000358 USD | 0.57 USD | 0.029 USD | **2.57 %** |
| `gpt-5.2` | 0.004601 USD | 7.36 USD | 0.368 USD | 33.01 % |

**Volume is the obstacle.** At 5 % sampling that is **40 judged answers in three months** —
statistically useless for a per-slot, per-model comparison. Continuous sampling is the wrong
instrument at LIA's traffic; §7.3 replaces it with bounded comparison campaigns.

### 2.7 Declared-but-unenforced constraints

| Finding | Evidence |
|---|---|
| `required_capabilities` declared on all 58 slots, **enforced nowhere** | `_model_has_capability` has one caller: the *optional* `?capability=` filter of `/metadata/models` (`llm_config/service.py:596`); the frontend sends only `?kinds=` (`useLLMConfig.ts:50`) |
| 5 slots use structured output **without declaring it** | `query_analyzer`, `semantic_validator`, `document_generation`, `memory_reference_extraction`, `open_loop_extraction` — each verified at its call site (2 further heuristic hits, `heartbeat_message` and `contacts_agent`, checked and **discarded as false positives**) |
| `supports_strict_mode` | column + import sheet + 6 translations, **zero runtime reader**; the runtime decides on `provider == "openai"` alone (`structured_output.py:602`) |
| The `LLMType` `Literal` guard is not load-bearing | `pyproject.toml` disables `arg-type` for `src.domains.agents.nodes.*` and `…graphs.base_agent_builder` (documented shrink-only MyPy-debt surface, F020). Verified: a deliberately bogus slot name in `response_node.py` produces **no** MyPy error |
| Failover chain points at non-existent models | `FALLBACK_MODELS_DEFAULT = "claude-sonnet-4-5,deepseek-chat"` (`core/constants.py:2509`): the first is absent from the catalogue, the second deactivated. Mounted only by `base_agent_builder` — the core pipeline has **no** failover |
| Two dead slots, one required at install | `router` and `context_resolver` have no `get_llm()` caller (all 6 `get_llm("router")` occurrences are docstrings); both listed in `CURRENT_CORE_LLM_TYPES` |
| Orphan seed row | `mcp_excalidraw` is not in `LLM_TYPES_REGISTRY` (42 seed rows, 1 orphan, 17 registry slots with no row) |
| Silent fallback on unknown key | `llm_type_map.get(agent_name, "contact_agent")` (`base_agent_builder.py:250`) |
| **Deprecated models offered in the admin UI** | **17 active models are past their deprecation date**; 10 more within 90 days. Safety-checked: the 17 have **zero references** (not in `LLM_DEFAULTS`, the seed, or constants) — deactivating them breaks nothing |
| Two time bombs the mechanism would have caught | `SUMMARIZATION_MODEL_DEFAULT = gpt-4.1-nano` and `LLM_DEFAULTS["image_generation"] = gpt-image-1`, both deprecated **2026-10-23** |

### 2.8 External practice review

Ten sources (§15). What they confirm, and what they changed.

**Confirmed**: no meta-LLM selector (routing latency ≈ a full model call; production routing
is conditional logic); per-slot right-sizing before per-request finesse (*"start with static
routing and caching; add semantic and cascade routing only when you've measured the
benefit"*); switching a model on a large cached prefix costs more than it saves
(DigitalOcean: 90 k cached tokens, staying 0.043 USD vs switching 0.07 USD, **×1.6**); the
40–85 % savings range (RouteLLM: −85 % cost at 95 % of GPT-4 Turbo quality).

**Changed** (items 2, 3, 6, 7, 8, 9 of §0), and one mechanism borrowed: DigitalOcean's
`X-Routing-Max-Switch-Spend-Pct` bounds the cumulative cost of switching **relative to what
staying would have cost** — an economic gate rather than a calendar one, which self-adapts to
prefix size. Adopted in §7.2.

**Public registries measured** (see §5.1):

```
LiteLLM model_prices_and_context_window.json : 3 175 entries, ~27 commits/day, MIT
  (the file sits at the repo root, outside enterprise/, so the MIT half applies)
models.dev api.json                          : 193 providers

Coverage under STRICT canonical-provider matching (see 0 bis / A1):
  both registries : 58      LiteLLM only : 37      models.dev only : 2      neither : 17
  totals          : LiteLLM 95/114 . models.dev 60/114 . union 97/114

filtered snapshot (LIA's 9 providers, CAPABILITY fields only, zero price field):
  133 KB, 512 entries, 294 chat models
```

The 17 uncovered models are the local and voice ones — Ollama tags, ElevenLabs, Edge TTS, two
2024 Claude snapshots, two legacy Perplexity Sonar ids, `computer-use-preview`, `o1-mini` — plus
two Gemini embedding rows. They stay hand-curated and are marked `verified` so no sync touches
them.

---

## 3. Scope

### 3.1 In scope — 53 slots

58 registry slots − 3 non-chat − 2 dead = **53**.

### 3.2 Out of scope, and why

| Excluded | Reason (verified) |
|---|---|
| `image_generation` (`required_kind=image`), `voice_transcription` (`audio`), `voice_tts` (`tts`) | The only 3 slots with a non-chat `required_kind`, and **none passes through `get_llm`** — they are served by `image_generation/client.py`, `voice/stt/factory.py`, `voice/factory.py`. The policy layer lives in `get_llm_config_for_agent` / `get_llm`; these never cross it. Their price units differ (`per_audio_hour`, per image), so token arbitration is meaningless. They remain in the catalogue and keep the sync mechanisms of §5 — only the *policy* excludes them. |
| Embeddings (`MEMORY_`, `RAG_SPACES_`, `JOURNAL_`, `INTEREST_EMBEDDING_MODEL`) | **Not LLM slots at all** — `.env` settings, absent from `LLM_TYPES_REGISTRY`. Structurally non-swappable: the model fixes the vector dimension of **6 pgvector columns** (`memories`, `journal_entries` ×2 each, `rag_chunks`, `store_vectors`); changing it is a full re-index, not a routing decision. |
| `router`, `context_resolver` | No runtime consumer (§2.7). Lot 0 removes them. |

The exclusion is **declared, not implicit**: `SLOT_POLICIES` covers exactly the in-scope
slots and a boot assert (ADR-085 family) fails the app if a registry slot is neither covered
nor listed in `POLICY_EXEMPT` with a written reason.

---

## 4. Architecture

```
  +--------------------------------------------------------+
  |  Layer 2 - offline adaptive controller (scheduled)      |
  |  moves ONE step, inside hard bounds, with hysteresis    |
  +---------------------------+----------------------------+
                              | writes: llm_policy_decisions + effective index
  +---------------------------v----------------------------+
  |  Layer 1 - execution profiles (deterministic, sync)     |
  |  slot -> ordered candidates -> first eligible           |
  +---------------------------+----------------------------+
                              | consumed by
  +---------------------------v----------------------------+
  |  Layer 0 - trustworthy substrate                        |
  |  registry-backed catalogue . runtime capability gate .  |
  |  persisted latency/status . verified failover           |
  +--------------------------------------------------------+
```

The single chokepoint is unchanged: **`get_llm_config_for_agent`**
(`core/llm_config_helper.py:46`), consumed by `get_llm` (`infrastructure/llm/factory.py:198`),
which already accepts a fully resolved `LLMAgentConfig` as `config_override`. **None of the
~45 `get_llm` call sites is modified.**

---

## 5. Layer 0 — trustworthy substrate

### 5.1 The catalogue becomes a reviewed import

**Canonical-provider lock — the first rule, before any field mapping.** A registry entry is
accepted **only** when its provider matches LIA's provider for that row, through a declared
mapping (`openai→openai`, `anthropic→anthropic`, `deepseek→deepseek`,
`gemini→google|google-vertex` / `gemini|vertex_ai-language-models`,
`qwen→alibaba|alibaba-cn` / `dashscope`, `perplexity→perplexity`, `ollama→ollama`,
`elevenlabs→elevenlabs`). Matching by model id alone is **forbidden**: models.dev publishes 193
providers and `deepseek-v4-flash` appears under **23** of them with output caps from 32 768 to
1 048 576 and prices from 0 to 0.396, while `jiekou` declares `gpt-5.2` as
`reasoning=False, temperature=True` — the opposite of the canonical `openai` entry. A guard
test pins the mapping and fails on an unmapped provider.

**Sources and per-field precedence.** Neither registry alone is sufficient; the precedence is
declared per field and measured (coverage on LIA's own models, strict matching):

| LIA column | Source of truth | Coverage |
|---|---|---|
| `max_input_tokens` | **LiteLLM** `max_input_tokens` → models.dev `limit.input` → `limit.context − limit.output` | 95 % |
| `max_output_tokens` | models.dev `limit.output` → LiteLLM `max_output_tokens` | 100 % |
| `kind` | LiteLLM `mode` | 100 % |
| `supports_tools` | models.dev `tool_call` → LiteLLM `supports_function_calling` | 100 % |
| `supports_vision` | models.dev `attachment` → LiteLLM `supports_vision` | 100 % |
| `is_reasoning_model` | models.dev `reasoning` → LiteLLM `supports_reasoning` | 100 % |
| `supports_structured_output` | models.dev `structured_output` → LiteLLM `supports_response_schema` | 81 % |
| `supports_temperature` | **models.dev only** (`temperature`) | 97 % |
| `reasoning_widget` + `reasoning_enum_values` / `reasoning_budget_range` / `effort_values` | ⛔ **never imported** (§0 quater R1) — proposed in the create/edit assist only; a naive import invalidates `effort: off` on **21 slots** | — |
| `deprecation_date` (new column) | **LiteLLM only** | 41 % |
| `supports_top_p` / `frequency_penalty` / `presence_penalty` | ⛔ neither — stays LIA-owned | — |
| `supports_streaming` | ⛔ **never imported** (§0 quater R3) — a false would break SSE on `response` | — |
| **all prices** | ⛔ **out of scope entirely** (§0 ter) — manual, via the existing pricing sheet | — |

> **`limit.context` is the total window, not the input budget.** 56 of 75 models.dev entries
> expose only `context`; using it as `max_input_tokens` over-estimates. Hence LiteLLM first.

**Prices are not part of this mechanism at all.** §0 ter measured the churn — 85 of 87 models
price-stable over two months, and the only two "changes" were registry tier-tracking artefacts
on the DeepSeek family, where LIA's `time_slots` data is already richer. The registry also
publishes one tier among six (`_flex`, `_priority`, `_batches`, `_above_272k_tokens`; 11.9 % of
entries carry several) and tracks promotions — commit `apply the GPT-5.6 Sol promotional
pricing cut`, 2026-08-21. Importing any of it would trade a contractual rate for a transient
one, to detect changes that do not happen. Prices stay where they are: the admin pricing sheet.

**What replaces it costs nothing and needs no registry**: a candidate with no active
`llm_model_pricing` row is **ineligible**, because the policy cannot arbitrate a cost it does
not know. Six of 87 chat models are in that state today; they simply never become candidates.

**Provenance.** New column `capability_provenance` on `llm_models`:
`declared` (column defaults) / `imported` (registry sync or pricing sheet) / `verified`
(a human confirmed it). Default `declared`.

**Snapshot, not a live dependency.** A **filtered snapshot** (LIA's 9 providers, capability
fields only, **no price field at all** — 133 KB) is vendored in the repository with the
upstream MIT notice. It is the floor:
an offline install works with it. Network refresh is a job, never on an execution path.

#### Mechanism ① — initial correction (`task llm:catalogue:sync`)

Produces a **reviewable diff**, applied as one migration:

- the placeholder capability rows repaired with real values (capabilities only — no price is touched);
- 4 already-"curated" rows corrected (`gpt-5.6-luna`/`sol`/`terra`, `llama3.1`);
- **17 deprecated models deactivated**, under a hard migration rule (see below);
- `SUMMARIZATION_MODEL_DEFAULT` and `LLM_DEFAULTS["image_generation"]` retargeted off
  `gpt-4.1-nano` / `gpt-image-1` (both deprecated 2026-10-23);
- `FALLBACK_MODELS_DEFAULT` retargeted onto catalogue-valid ids.

Rows the registries do not know (17 of 114, §2.8) stay hand-curated and are marked `verified`
so no later sync touches them.

> **Deactivation is never benign — hard migration rule.** A model dropped from `is_active`
> leaves `ModelCapabilitiesCache`, so `get_model_profile` falls back to `CONSERVATIVE_DEFAULT`
> (`model_profiles.py:127`): `is_reasoning_model=False`, `supports_temperature=True`,
> `max_input_tokens=8192`. The adapter would then send sampling parameters to a reasoning
> model — a provider 400 — and the compaction threshold would collapse.
>
> The migration therefore **queries the target instance** and deactivates a model only when no
> `llm_config_overrides` row, no `LLM_DEFAULTS` entry, no seed row and no constant references
> it. A referenced deprecated model is **retargeted first, deactivated second**; if no
> retarget is possible it is left active and raised as a class-C alert. Verified on the dev
> instance: **0 of the 38 explicit slot models** point at one of the 17.

#### Mechanism ② — continuous correction (scheduled)

Three severity classes, so a human decision is never silently overwritten:

| Class | Content | Action |
|---|---|---|
| **A — auto-applied** | capability fields of a model whose provenance is `declared` (never curated by a human) | direct write + audit entry |
| **B — proposed** | anything overwriting a `verified` capability value, and every deactivation | review queue in the admin UI |
| **C — alert only** | deprecation within N days on a model referenced by a slot or a policy | notification, never a write |

Two bounds, smallest wins (`feature_switches` doctrine): `LLM_CATALOGUE_SYNC_ENABLED` as the
deployment ceiling (**default off** for self-host) **and** the admin switch. Registered in
`startup/schedulers.py` before `leader_elector.start()`, job id from `core/constants.py`.

Every sync run writes to `llm_catalogue_sync_log` (source, snapshot version, rows examined,
class-A writes, class-B proposals, class-C alerts) — the screen reads that table.

#### Mechanism ③ — create/edit assist

`GET /admin/llm-config/catalogue/lookup?provider=…&model=…` returns the **merged** entry from
both registries, mapped onto LIA's columns, **with the source of each field**. The admin form
pre-fills as soon as provider + model name are entered; every field carries a provenance
badge and stays editable. A model unknown to both registries is still hand-enterable — the
form says so, it does not block.

#### Guards

- `test_model_capability_provenance_guard.py`: **a model referenced by a slot override or by
  any `SLOT_POLICIES` candidate may not carry `declared` provenance.** Shrink-only allowlist,
  ADR-155 shape.
- `test_no_deprecated_model_referenced.py`: no slot, default, seed row or policy candidate
  points at a model past its deprecation date.
- `test_catalogue_snapshot_freshness.py`: the vendored snapshot is not older than N days
  (warning, not a failure — an old snapshot must not red a build).

**`get_effective_context_window` is rewritten**: the catalogue wins when provenance is
`imported`/`verified`; `MODEL_CONTEXT_WINDOWS` is the last resort for models outside the
catalogue **and is itself corrected** from the registries in Lot 0 (10 of 56 entries were
wrong). The provenance decides which authority wins — never a second hard-coded rule.

### 5.2 Runtime capability gate

- Complete the 5 missing `required_capabilities` declarations (§2.7) **before** switching the
  gate on — a gate over incomplete declarations is worse than none.
- **The gate filters policy candidates only — never an explicit choice.** This distinction is
  load-bearing, and v2 got it wrong. `vision_analysis`'s own code default is `gpt-5-mini`,
  which today's catalogue declares `supports_vision=false` (only 12 of 87 chat models declare
  it true, against 55 more per the registries). A gate applied to explicit configuration would
  reject the slot's own default and break image analysis.

  | Origin of the model | Gate behaviour |
  |---|---|
  | `SLOT_POLICIES` candidate | **hard filter** — skip, log `llm_policy_candidate_rejected` with the reason, try the next |
  | `LLM_DEFAULTS` or an admin DB override | **warning only** — the call proceeds with the configured model; the discrepancy is counted, logged, and shown on the slot's card |

  If no candidate survives the filter, fall back to `LLM_DEFAULTS` and raise a counter. Never a
  silent substitution, and never a silent override of a human decision.
- The frontend sends `?capability=` when populating a slot's dropdown, so the admin sees the
  constraint the runtime applies (ADR-184).
- **`supports_strict_mode` gets a reader, arbitrated by provenance** — the same rule as the
  context window, applied twice:

  ```
  use_strict_mode = is_strict_compatible
                    and provider == "openai"
                    and (provenance == "declared"  or  caps.supports_strict_mode)
  ```

  `declared` (never filled) keeps today's provider heuristic — **zero regression on the 83
  models whose column is an unfilled `false`**. `imported`/`verified` lets the column
  narrow. A test pins the current behaviour for `declared` rows.

### 5.3 Observation columns

`token_usage_logs` gains three nullable columns (no backfill):

| Column | Type | Meaning |
|---|---|---|
| `latency_ms` | `Integer` | wall time, already computed in `observability/callbacks.py:208` |
| `status` | `String(16)` | `success` / `error` |
| `failure_kind` | `String(32)` | `structured_output` / `timeout` / `rate_limit` / `context_overflow` / `provider_error` / `json_recovered` |
| `llm_type` | `String(64)` | **the slot**, from the closed `LLM_TYPES_REGISTRY` vocabulary (§0 quater R2). `node_name` does not map to slots and carries unbounded free text, so the controller aggregates on this column and never on `node_name`. Written from the calling slot, backfilled only where the mapping is unambiguous. |

They are the controller's only step-down veto and step-up trigger, they cost nothing (the
values already exist in memory), and they answer §2.6: objective failure, not inferred
quality. A new index `(llm_type, model_name, created_at DESC)` serves the controller window;
the existing `ix_token_usage_logs_lifetime_aggregation` stays for the lifetime metrics.

### 5.4 Verified failover

Boot assert: every `FALLBACK_MODELS` entry must exist, be active, be non-deprecated, and have
a registered provider key — otherwise log loudly and **disable** the middleware rather than
pretend. Assert, not crash: a broken failover list must not prevent a boot. The ADR records
explicitly that the core pipeline has no failover today and that extending it is out of scope.

### 5.5 Dead-code removal

- Delete the `router` and `context_resolver` slots (registry, defaults, `LLMType`,
  `CURRENT_CORE_LLM_TYPES`, i18n keys ×6, seed rows, the legacy `context_resolver_llm_*`
  settings). Re-derive `CURRENT_CORE_PROVIDER_IDS`.
- Delete the orphan `mcp_excalidraw` seed row.
- Replace `llm_type_map.get(agent_name, "contact_agent")` with an explicit `KeyError` path.
- `evaluation_pipeline.py` is neither deleted nor left dormant: §7.3 wires it behind the
  campaign harness. Until Lot 5 lands, its module docstring states it is unwired pending that
  work, so it stops reading as live machinery.

**Acceptance**: `task ci:fast` green; each new guard red on a deliberately reverted fix;
`get_effective_context_window("gpt-5.2")` returns 272 000.

---

## 6. Layer 1 — execution profiles

### 6.1 Data model (code, not a free-form table)

New module `src/domains/llm_config/policies.py` — a declaration, sibling of `LLM_DEFAULTS`,
sized as a data module (exempt from the 600-SLOC cap like `llm_config/constants.py`):

```python
class CacheLocality(str, Enum):
    """Diagnostic only since v2 — it no longer drives the move interval."""
    CROSS_TURN = "cross_turn"
    INTRA_TURN = "intra_turn"
    NONE = "none"


@dataclass(frozen=True)
class SlotPolicy:
    slot: str
    cache_locality: CacheLocality              # displayed, not enforced
    latency_sla_p95_seconds: float | None      # None = background, no SLA
    effort_intent: EffortIntent                # minimal | low | medium | high
    candidates: dict[Profile, tuple[str, ...]] # ordered, best-first, per profile
```

`Profile` is `ECONOMY | BALANCED | QUALITY | MANUAL`. Bounds are a design decision, exactly
like `PERIMETERS` in `threshold_controller.py:66` — widening them requires replaying the
calibration evidence.

**The profile is per instance; the differentiation is per slot.** `latency_sla_p95_seconds`
(`None` for background, a ceiling for blocking slots) plus per-slot candidate lists let
`ECONOMY` keep `gpt-5.6-luna` on `response` while dropping `journal_extraction` to
`qwen3.5-flash`. The chat/background asymmetry lives in the lists, not on the screen — which
is why no per-category profile is needed (§14.1).

### 6.2 Resolution

```
1. canonical   = alias resolution                       (unchanged)
2. defaults    = LLM_DEFAULTS[canonical]                (unchanged)
3. db_override = LLMConfigOverrideCache.get_override()  (unchanged)
4. if the slot is PINNED, or profile == MANUAL, or the policy is disabled
       -> return merge_config(defaults, db_override)    (EXACTLY today's behaviour)
5. otherwise:
       index = effective index for (this slot, this profile)   -- default 0, section 0 quater R4
       for model in candidates[profile][index:]:
           if     capability gate passes        (required_capabilities, required_kind)
              and not deprecated
              and provider key present
              and an ACTIVE PRICING ROW exists    (else uncostable, section 0 ter)
              and supports_streaming              (for response / the two HITL question slots)
              and NUMERIC FIT                   (see below)
               -> return merge_config(defaults, db_override | {model, provider})
       -> log llm_policy_no_candidate, return merge_config(defaults, db_override)
```

**Numeric fit — missing from v2, and it would have broken compaction.** Capabilities are not
enough: the slot's own numeric configuration must fit the candidate.

| Check | Why |
|---|---|
| `effective max_tokens ≤ candidate.max_output_tokens` | `compaction` and `journal_consolidation` both request **50 000** output tokens; a candidate capping lower fails at call time. Today every slot sits on `deepseek-v4-flash` (384 000) so nothing bites — a policy would change that. |
| `candidate.max_input_tokens ≥ the slot's observed p95 input` | measured from `token_usage_logs`; refuses a candidate that would overflow on real traffic rather than discovering it in production |
| `candidate.max_input_tokens × compaction_threshold_ratio` is coherent for the `response` slot | the compaction trigger is derived from this slot's model (`compaction_service.py:152`) |

A candidate failing a numeric check is skipped with `reason=numeric_fit`, exactly like a
capability failure. The p95 input figure is recomputed by the same maintenance job that feeds
the controller, never hard-coded.

Properties preserved: synchronous and I/O-free; the DB override always wins over the policy,
so pinning needs no new concept; **`MANUAL` reproduces today's provider/model/parameter
resolution exactly** (with the scope stated in §10); `reasoning_effort` keeps going through
`merge_config`'s existing reconciliation.

**Where the effective index lives — durable, not advisory.** v2 contradicted itself (in-memory
cache family in §6.2, Redis flush in §9). Resolved: the index is a **PostgreSQL column**,
mirrored in memory exactly like `LLMConfigOverrideCache` (boot-loaded, cross-worker
invalidated via the ADR-063 pub/sub). Redis is used for nothing here. Rationale: a Redis flush
silently reverting a slot to a different model is a **silent configuration change**, which the
audit trail exists to make impossible. Losing the index must never be a way to change what
runs.

### 6.3 Normalised effort intent — delivered by ADR-245

> Since v3.3 this section is **implemented by the companion design**
> `2026-08-23-reasoning-model-unification-design.md` (Lot 0c). What follows states the
> requirement; that document owns the model, the validated prototype and the migration.

The catalogue exposes **4 reasoning widget shapes** (`none` 37, `enum` 38, `budget_int` 4,
`toggle_budget` 8). A slot declares `effort_intent`; a pure function maps it to the concrete
shape of the chosen model from `reasoning_widget`, `reasoning_enum_values` and
`reasoning_budget_range` — all three now registry-fed (§5.1). Unmappable ⇒ `None` (model
default), logged.

This closes a real gap: a model change can today silently erase the admin's chosen effort
(`merge_config` documents the 2026-07-27 incident where three background extractors ran with
no reasoning block at all).

### 6.4 LLM instance cache

`LLM_INSTANCE_CACHE_MAX_SIZE = 64` with FIFO eviction. Only **one candidate per slot is live
at a time**, so the steady-state key count is unchanged (≈ 53). A step evicts one entry, not
the cache. No change required; a test asserts the steady-state count stays ≤ 64.

### 6.5 Time-slot-aware scheduling (S0) — a free 2.7 %

Discovered during the v3 review: **30.1 % of background spend falls inside DeepSeek's peak
windows** (01:00–04:00 and 06:00–10:00 UTC, ×2). Shifting the schedulable background jobs —
journal consolidation, interest clustering, heartbeat sweeps, the proactive tasks — out of
those windows saves **2.7 % with no model change, no cache impact and no quality risk**
(§2.3, S0). Combined with S1 it recovers the four points the time-aware correction cost:
**−36.7 %**.

Mechanics: each scheduled job whose trigger has no user-facing timing constraint declares a
`preferred_utc_windows` hint; the scheduler avoids the peak windows of the providers actually
serving that job's slot, derived from `llm_model_pricing.time_slots` — never hard-coded hours.
When a slot's model has no time slots the hint is a no-op.

This is scheduling, not routing, and it ships in Lot 1 alongside the policy because it shares
the same price source and is measurable the same way.

---

## 7. Layer 2 — offline adaptive controller

### 7.1 Shape

A scheduled job, `threshold_controller` transposed from a float to an **ordinal index** into
`SlotPolicy.candidates`, with the same four rails: hard bounds; hysteresis (one step per
interval); observability (every move persisted and logged); kill-switch
(`LLM_AUTOPILOT_ENABLED` **AND** the admin switch, smallest wins).

**Runs outside traffic hours.** That single scheduling choice satisfies §2.2's governing rule
— never move inside a burst — without any locality taxonomy.

### 7.2 Move rules (deterministic, published in the UI)

Over the last `N` calls for the slot (default 200, minimum 50 — settings-driven, never
hard-coded in tests):

- **step down** (cheaper) if **all** hold: `status='error'` rate 0, `failure_kind` rate 0,
  `latency_ms` p95 ≤ `latency_sla_p95_seconds` (skipped when `None`), no thumbs-down on a run
  using this slot, the 24 h interval has elapsed, **and the switch-spend gate passes**;
- **step up** if **any** holds: `failure_kind='structured_output'`, timeout, or
  ReAct-iteration-exhaustion rate above threshold; or a thumbs-down landed on a run using the
  model this slot moved to since the last move;
- **do nothing** otherwise (dead band).

**Switch-spend gate** (adapted from DigitalOcean's `X-Routing-Max-Switch-Spend-Pct`): before
moving, estimate the re-warm cost (measured: ~0.0015 USD per burst — average 6 901 cached
tokens over 3 843 bursts) and refuse the move if it exceeds `X %` of the expected saving over
the window. Economic rather than calendar, and it self-adapts to prefix size. It replaces v1's
per-locality intervals; the interval is now uniform at 24 h.

Step-up is **never** rate-limited: a degradation is repaired immediately. The asymmetry
mirrors `react_budget`'s doctrine — *the adaptive path only ever saves on provably simple
cases*.

**Pilot metric**: `cost-per-successful-task`, not cost per call. A model 3× cheaper that
fails a quarter of the time is more expensive.

**All cost estimates go through `pricing_cache.get_cached_cost_usd_eur`, never through the
base price columns.** With time-slot pricing (ADR-223) a base-column estimate under-costs a
slotted model by about 30 % on background traffic — exactly the error v2's own simulation
made. The controller prices a candidate by replaying the slot's real hourly token distribution
against the effective tariff, so a model that is cheap off-peak and expensive on-peak is
compared honestly against a flat-rate one.

### 7.3 Quality signal — bounded comparison campaigns

Continuous sampling is the wrong instrument at LIA's volume (§2.6). Instead:

**When the controller wants to move a slot, it triggers a campaign**: replay `N = 50` recent
real inputs of that slot through both candidates, judge both outputs with a **fixed, pinned**
judge model — never one of the candidates (self-preference bias) — with **both presentation
orders** and only consistent wins counted (position-bias mitigation, the standard practice),
then decide.

Measured campaign cost:

| Comparison | Judge | Total | Share of the 90-day bill |
|---|---|---|---|
| `deepseek-v4-flash` vs `qwen3.5-flash` | `gpt-5.6-luna` | 0.124 USD | 0.56 % |
| `gpt-5.6-luna` vs `deepseek-v4-flash` | `gpt-5.6-luna` | 0.186 USD | 0.83 % |
| `gpt-5.2` vs `gpt-5.6-luna` | `gpt-5.2` | 1.290 USD | 5.78 % |

**Under 1 % of the quarterly bill for a statistically defensible verdict**, where three months
of sampling yields none.

**Replay sends real user content to a candidate provider — explicit consent required.** The
harness re-sends captured user inputs, and a candidate may belong to a provider that instance
has never sent data to. Three hard constraints:

1. a candidate provider must already have a **registered API key on that instance** — a
   campaign never introduces a new provider relationship;
2. a campaign whose candidate provider is **not already serving traffic** requires an explicit
   per-campaign admin acknowledgement naming the provider, recorded in the audit trail;
3. `LLM_CAMPAIGN_REPLAY_ENABLED` is a deployment ceiling, default **off**, so a self-hosted
   instance never replays user content without a deliberate decision.

The harness stays server-side, is never exported, and its captures are purged after the
campaign. Scores persist in PostgreSQL
(`llm_quality_scores`: run_id, slot, model, metric, score, order) — never in Langfuse, because
the controller must not depend on an opt-in, off-by-default, undeployed observability stack.

**Human feedback is a veto, never a motor**: with 1 verdict in the whole database, a
thumbs-down can only cancel a recent step-down.

**Activation condition**: without the campaign harness, Layer 2 is a **cost minimiser under
failure constraints**, and the UI says so in those words. The literature names the exact blind
spot — *"a quality score sliding while the error rate stays at zero is the signature of a
silent regression"* — so the campaign ships **with** Layer 2, not after it.

### 7.4 Audit trail

`llm_policy_decisions` (append-only): `slot`, `profile`, `model_before`, `model_after`,
`direction` (`down`/`up`/`revert`), `reason` (machine code), `window_calls`, `error_rate`,
`p95_latency_ms`, `thumbs_down`, `campaign_id`, `decided_at`, `decided_by`
(`autopilot`/`admin`). This table **is** the admin screen; it is not optional.

### 7.5 What the controller never touches

Pinned slots, `MANUAL`, the 3 non-chat slots, any slot whose current or candidate model
carries `declared` provenance or is deprecated, and any slot below `min_window_calls`.

---

## 8. Administration

### 8.1 Screen 1 — Model catalogue *(exists: Settings → Admin → LLM Pricing)*

Adds: a provenance badge per row; an "unverified capabilities" warning; a **deprecation**
column with three states (past / within 90 days / later); a **"no active pricing"** marker on
the 6 uncostable rows; the **review queue** of class-B proposals with a per-row accept/reject;
and the last sync report. Prices remain edited exactly as today, by hand, through this screen
and its import sheet — the sync never proposes one.

### 8.2 Screen 2 — LLM configuration *(exists: `AdminLLMConfigSection`, 58 cards)*

Instance header above the cards:

```
Instance profile   ( ) Economy   (*) Balanced   ( ) Quality   ( ) Manual
Active providers : openai, deepseek, anthropic, gemini, ... (9)
Policed slots : 38  .  pinned : 15  .  out of scope : 3        (total 56 after Lot 0)
```

The three counts always sum to the registry size after Lot 0 removed the two dead slots
(58 − 2 = 56): 53 in-scope slots split into policed and pinned, plus the 3 non-chat ones.

`Manual` reproduces today's behaviour exactly — the migration's safety net. The `Quality`
profile displays its measured price (**+129 %**, §2.3) before it can be selected.

Each in-scope card gains a candidate strip (retained model, alternatives with their measured
delta, excluded ones with the reason) and a **Pin** toggle.

### 8.3 Screen 3 — Autopilot *(new, mostly read-only)*

State (active/frozen, last and next pass), the `llm_policy_decisions` feed per slot with the
triggering evidence and the campaign verdict, the bounds, and three actions: **Freeze all**,
**Revert to profile** (per slot), **Pin** (per slot). When no campaign harness is active, a
persistent banner states that the controller optimises cost under failure constraints only.

### 8.4 Model create/edit dialog *(exists, gains the assist)*

Provider + model name entered ⇒ the form pre-fills from `/catalogue/lookup`, each field
badged with its source (`litellm` / `models.dev` / `manual`) and freely editable. Unknown
models stay hand-enterable, with a notice.

### 8.5 i18n

All new strings in the 6 locales, `zh` duplicated for `_one`/`_other`. The `reason` column
stores a **machine code**, translated at render time — never a pre-rendered sentence.

---

## 9. Edge cases

| Case | Required behaviour |
|---|---|
| Provider key removed while a slot points at that provider | Candidate rejected at resolution, next candidate; counter + log. No 500. |
| Model deactivated (or newly deprecated) mid-run | Cache reload clears the instance cache; the next `get_llm` re-resolves. A run in flight keeps its instance — accepted, bounded by the run. |
| Profile changed **during** a run | Resolution is per `get_llm` call. Mitigation: the controller's effective index is **read once per run** and carried in `MessagesState` for `intra_turn` slots (a new **declared** key — undeclared keys are silently dropped by LangGraph). |
| HITL interrupt resumed after a move | The checkpoint holds messages, not the model. Allowed for `none`-locality slots; for `intra_turn` slots the pinned per-run model is restored from state. Cross-provider tool-call replay covered by an integration test. |
| No candidate survives the gate | Fall back to `LLM_DEFAULTS` (never an arbitrary model), log, count, surface in Screen 3. |
| Controller state lost (Redis flush) | Index resets to 0 (the profile's preferred model). Costs a relearn, never a wrong value. |
| Two workers move the same slot concurrently | Atomic conditional UPDATE on `(slot, decided_at)`, guarded by the scheduler's existing leader election. |
| Registry sync proposes a change to a model in active use | Class B ⇒ review queue, never auto-applied. |
| Registry unreachable / snapshot stale | Sync is skipped with a warning; the vendored snapshot keeps serving. Freshness guard warns, never reds a build. |
| Registry disagrees with LIA on a price | Not observed at all — prices are outside the sync (§0 ter). |
| A candidate has no active pricing row | Ineligible, `reason=uncostable`. Never chosen, never silently priced at zero. |
| An `ECONOMY` profile targets a model whose reasoning cannot be disabled | Measured: `gemini-3.5-flash` is `reasoning.mandatory=true` (§0 quinquies). The candidate stays eligible but its cost estimate must assume reasoning ON — never assume a cheap mode exists. |
| A registry would change a reasoning widget or enum values | Never written (§0 quater R1). Surfaced only in the create/edit assist, where a human sees it. |
| The profile changes while a slot sits at a non-zero index | The index is keyed `(slot, profile)`; the new profile starts at its own index, 0 if never visited. |
| A row has an unmapped or free-text `node_name` | `llm_type` is written from the calling slot, never derived from `node_name`; an unmapped legacy row stays NULL and is excluded from the controller window rather than mis-attributed. |
| The two registries disagree with **each other** on a field | The declared precedence picks one, and the disagreement is **flagged for review** rather than resolved silently. |
| A registry entry comes from a resale/proxy provider | Rejected by the canonical-provider lock (§5.1) before any mapping. |
| A deprecated model is still referenced by a slot on the target instance | Not deactivated. Retarget first; otherwise leave active and raise a class-C alert (§5.1). |
| A model is deactivated while a slot still points at it | `CONSERVATIVE_DEFAULT` applies — sampling params would reach a reasoning model. Prevented by the migration rule; an integration test reproduces the failure to keep the guard honest. |
| A candidate's `max_output_tokens` is below the slot's `max_tokens` | Skipped with `reason=numeric_fit` (§6.2), never attempted. |
| Compaction threshold moves because a context window was corrected | Deliberate, measured, announced per model in the Lot 0a report; zero movement for the reference seed (`response` = `deepseek-v4-flash`). |
| A background job's peak-window hint conflicts with a user-facing deadline | The hint is advisory; a job with a timing constraint keeps its trigger. |
| A campaign cannot gather `N` real inputs | The move is refused and reported as "insufficient evidence", not silently allowed. |
| `reasoning_effort` incompatible with the new model | Handled by `_reconcile_reasoning_effort`; the `effort_intent` mapper makes the degradation intentional rather than a silent drop. |
| Instance budget nearly exhausted | **Out of scope.** Budget-driven downgrade is Layer 3, deliberately deferred. |

---

## 10. Non-regression plan

Anchor: **`MANUAL` + autopilot off must produce identical provider/model/parameter resolution
to today.**

> **Scope of the anchor, stated precisely (v2 overstated it).** The guarantee covers what
> `get_llm_config_for_agent` returns. It does **not** cover values *derived* from the catalogue,
> which Lot 0a deliberately corrects: the compaction threshold moves with the context window
> (`gpt-5.2`: 3 277 → 108 800 tokens at ratio 0.4; `gpt-5.6-luna`: 419 030 → 368 800), and
> strict mode may narrow where provenance allows. For the **reference seed** (`response` =
> `deepseek-v4-flash`, window already 1 000 000) the threshold does not move at all. Each
> correction is measured per model and published in the Lot 0a report — none ships silently.

| Test | Nature |
|---|---|
| `test_policy_manual_is_identity` | All 58 slots × seeded overrides, golden comparison on `model_dump()` |
| `test_gate_never_overrides_explicit_choice` | A `LLM_DEFAULTS`/override model failing the gate still resolves; only a warning + counter (the `vision_analysis` / `gpt-5-mini` case is a fixture) |
| `test_numeric_fit_rejects_small_output_cap` | A candidate capping below `compaction`'s 50 000 is skipped with `reason=numeric_fit` |
| `test_registry_match_requires_canonical_provider` | A resale-provider entry for a known id is never matched; the mapping table is pinned |
| `test_registries_disagreement_is_flagged` | Conflicting fields raise a review item instead of silently resolving |
| `test_deactivation_blocked_when_referenced` | A deprecated model referenced by an override is not deactivated |
| `test_deactivated_model_falls_back_conservatively` | Reproduces the `CONSERVATIVE_DEFAULT` hazard so the migration guard cannot rot |
| `test_effective_index_survives_redis_flush` | The index is durable; flushing Redis changes no model |
| `test_controller_costs_use_time_slots` | A slotted candidate priced through `pricing_cache`, not base columns |
| `test_compaction_threshold_movement_reported` | Lot 0a emits the per-model before/after; the seeded `response` model moves by 0 |
| `test_campaign_requires_registered_provider_key` | A candidate on an unconfigured provider is refused |
| `test_capability_gate_rejects_and_reports` | A tool-less candidate on a `tools` slot falls through and logs; never substitutes silently |
| `test_deprecated_candidate_rejected` | A deprecated candidate is skipped with its reason |
| `test_no_candidate_falls_back_to_defaults` | Empty candidate set ⇒ `LLM_DEFAULTS`, counter incremented |
| `test_strict_mode_declared_provenance_unchanged` | The 83 `declared` rows keep today's provider heuristic |
| `test_controller_respects_bounds_and_hysteresis` | Property test over random windows |
| `test_controller_step_up_is_immediate` | A failure spike moves up regardless of the interval |
| `test_switch_spend_gate_blocks_expensive_move` | A move whose re-warm exceeds X % of the expected saving is refused |
| `test_slot_policy_registry_completeness` | Boot assert: every slot covered or exempt with a reason (ADR-085) |
| `test_model_capability_provenance_guard` | No policed slot references a `declared`-provenance model (shrink-only allowlist) |
| `test_no_deprecated_model_referenced` | No slot/default/seed/candidate points at a deprecated model |
| `test_catalogue_sync_classes` | Class A writes, class B queues, class C only alerts; a `verified` row is never auto-overwritten |
| `test_catalogue_sync_never_reads_prices` | No price field is ever read, proposed or written by the sync |
| `test_uncostable_candidate_rejected` | A candidate without an active pricing row is skipped with `reason=uncostable` |
| `test_mandatory_reasoning_costed_as_on` | A candidate with `reasoning.mandatory` is never costed as if reasoning could be disabled |
| `test_sync_never_touches_reasoning_fields` | Golden over all 58 slots: no reasoning_effort changes after a sync against a fixture snapshot (the 21-slot regression of §0 quater R1 is the fixture) |
| `test_sync_never_touches_streaming` | `supports_streaming` is never written by the sync |
| `test_effective_index_is_keyed_by_profile` | Switching profile does not carry the previous profile offset |
| `test_llm_type_written_for_every_call` | Every new `token_usage_logs` row carries a slot from the closed vocabulary; free-text `node_name` never leaks into it |
| `test_effort_intent_maps_all_widgets` | 4 widget shapes × 4 intents, exhaustive |
| `test_llm_instance_cache_steady_state` | Full policy ⇒ ≤ 64 distinct keys |
| `test_fallback_models_exist_in_catalogue` | Boot assert on `FALLBACK_MODELS` |
| `test_judge_order_randomised` | Both presentation orders; only consistent wins counted |
| Integration | HITL resume across a move; two-worker concurrent move; provider key removal mid-flight; sync against a fixture snapshot |

Coverage floors are **raised**, never lowered, after the work.

---

## 11. Observability

- Counters: `llm_policy_candidate_rejected_total{slot,reason}`,
  `llm_policy_no_candidate_total{slot}`, `llm_policy_moves_total{slot,direction}`,
  `llm_catalogue_sync_changes_total{class}`, `llm_model_deprecated_referenced_total{slot}`.
- Gauges: `llm_policy_effective_index{slot}`, `llm_catalogue_snapshot_age_days`.
- Derived: `cost-per-successful-task` per slot, from `token_usage_logs.status`.
- Every move logged at INFO with counters and ids only — **never** prompt content (PII rule).
- The debug panel already shows the effective model via `execution_metadata` /
  `LLMCallsSection`; the policy adds the **reason** it was chosen.

---

## 12. Delivery order

| Lot | Content | Independently revertible |
|---|---|---|
| **0a** | ADR-244 + catalogue: vendored snapshot, canonical-provider lock, `task llm:catalogue:sync`, provenance and deprecation columns, initial correction (rows repaired/corrected, deprecated models deactivated **under the reference-check rule**, constants retargeted), context-window fix **plus the per-model compaction-threshold movement report**, guards | yes |
| **0c** | **Reasoning model unification (ADR-245)** — see `2026-08-23-reasoning-model-unification-design.md`. Prototype built and validated: 56/56 golden equivalence, 0 family gaps over 87 models, 0 coercions on valid values, 3 480 combinations without a crash. Ships **before** Lot 1, because Layer 1's `effort_intent` mapper *is* this model | yes |
| **0b** | Capability gate scoped to candidates + the 5 missing declarations, `supports_strict_mode` reader, observation columns **including `llm_type`** (§0 quater R2), failover assert, dead-slot removal | yes |
| **1** | `SLOT_POLICIES`, `resolve_slot_config` (capability **and numeric** gates), effort-intent mapper, durable effective index, **time-slot-aware scheduling (S0)**, `MANUAL` identity guard | yes (profile stays `MANUAL`) |
| **2** | Admin screens 1 and 2 + create/edit assist + i18n ×6 | yes |
| **3** | Continuous sync (classes A/B/C), review queue, scheduler, kill-switch | yes (flag off) |
| **4** | Campaign harness + `llm_quality_scores` | yes |
| **5** | Controller, `llm_policy_decisions`, switch-spend gate, autopilot screen + i18n ×6 | yes (flag off) |

Lot 4 **precedes** Lot 5: the controller does not ship without the instrument that detects
its own silent regressions. Each lot ends green on `task ci:fast`; lots touching migrations
also run `task db:migrate:replay-check`.

---

## 13. Non-goals, argued

- **No meta-LLM selector.** +50 % of the median turn cost, +1 to +3.5 s TTFT (§2.5).
- **No per-request model switching.** Breaking the burst costs +33 % (§2.2).
- **No cascade (FrugalGPT-style), for now.** The decision-theoretic characterisation gives the
  conditions under which a cascade *loses*: high deferral rate, imprecise judge, low cost
  ratio, low quality gap. LIA has **no judge** and its deferral cost is a full duplicate call.
  The operational warning is explicit: *"monitor your escalation rate — a cascade that
  silently escalates 90 % of traffic costs more than no routing at all."* **Re-examine after
  Lot 4**, never before.
- **No semantic response cache.** Production hit rates are 10–70 %, not the advertised 95 %,
  and the three failure modes — similarity false positives, stale answers, and **one user's
  personalised answer returned to another** — are disqualifying on an encrypted personal
  assistant. The existing `cache_llm_response` decorator stays limited to deterministic calls.
- **No synchronisation of reasoning metadata, sampling flags or streaming** — measured: a naive reasoning import invalidates `effort: off` on **21 slots** and silently switches the pipeline to thinking mode (§0 quater R1).
- **No price synchronisation of any kind** — not even as a proposal. Measured: 85 of 87 models price-stable over two months, 0 true positives, 2 false positives (§0 ter). Prices stay manual.
- **No budget-driven downgrade** (Layer 3) — deliberately deferred.
- **No failover for the core pipeline** — recorded as a known gap.

---

## 14. Decisions taken (v1's open questions)

### 14.1 Profile granularity — per instance, with a per-slot SLA

The admin category taxonomy aligns with latency for 6 of 8 categories and **breaks on two**:
`memory` is mixed (`memory_reference_extraction`/`_resolution` are pre-planner and blocking,
`memory_extraction`/`open_loop_extraction` are post-response), and so is `specialized`.
`memory` alone is 13 % of the spend. Eight selectors would also mean 6 561 combinations — the
combinatorics the design exists to remove. **Decision**: one instance profile;
`latency_sla_p95_seconds` per slot; the chat/background asymmetry encoded in the candidate
lists. `SlotPolicy` already carries what a per-category profile would need, should it ever be
wanted.

### 14.2 Quality signal — bounded campaigns, shipped with the controller

Sampling is cost-cheap (+2.6 % at 100 %) but **volume-poor**: 40 judged answers in three
months at 5 %. Campaigns give a defensible verdict for under 1 % of the quarterly bill.
Lot 4 precedes Lot 5.

### 14.3 `supports_strict_mode` — a reader, arbitrated by provenance

Wiring the column as-is would **disable strict mode on 83 of 87 models**, because `false` is
an unfilled column default, not a measurement. The provenance rule (§5.2) reads the column
where it is trustworthy and keeps the provider heuristic where it is not — the same rule as
the context window, applied twice.

---

## 15. Sources

Repository and dev-database evidence is cited inline. External practice review:

1. LLM Model Routing in 2026 — DigitalApplied
2. DigitalOcean Inference Router, Now Cache-Aware (switch-spend budget, ×1.6 measurement)
3. LiteLLM — Auto-Routing + Prompt Caching benchmark (99.3 % warm switch-backs)
4. `BerriAI/litellm` — `model_prices_and_context_window.json` (MIT, ~27 commits/day)
5. `models.dev` — `api.json` (reasoning options, sampling flags)
6. *Is Escalation Worth It? A Decision-Theoretic Characterization of LLM Cascades*, arXiv 2605.06350
7. FrugalGPT — Portkey
8. *Multi-LLM routing in production: the failure modes nobody warns you about*
9. LLM-as-judge evaluation best practices — Openlayer
10. *LLM Semantic Caching: the 95 % hit rate myth* — production hit-rate data
11. Retries, fallbacks and circuit breakers in LLM apps — Portkey
12. OpenAI — Reasoning models guide (`reasoning.effort` values)
13. DeepSeek API — Thinking Mode guide (thinking defaults to enabled)
14. Google — Gemini API thinking (`thinking_budget` / `thinking_level`)
15. Alibaba Model Studio — deep thinking via API (`enable_thinking`, `thinking_budget`)
16. Artificial Analysis — performance benchmarking methodology (P50/72 h, no public API)
17. OpenRouter — public `/api/v1/models` and `/models/{id}/endpoints` (reasoning flags; latency fields null)
