# ADR-244: the model catalogue tells the truth — two public registries, one provenance

**Status**: Accepted (2026-08-24)
**Deciders**: LIA core team
**Technical story**: LLM model-policy design (`docs/superpowers/specs/2026-08-23-llm-model-policy-design.md`), Lot 0a. The policy layers it prepares are separate lots; this ADR covers only the correctness prerequisite.

## Context

`llm_models` is the runtime authority on what a model can do: `ModelCapabilitiesCache`
loads it at boot and `get_model_profile` / `get_effective_context_window` read it on the
hot path. Measured on 2026-08-23, **89 of its 114 active rows carried the column
defaults** — `max_input_tokens = 8192`, `max_output_tokens = 4096`. Nobody had ever
curated them, and nothing in the code could tell a measurement from a default.

The consequences were not theoretical.

**The compaction threshold collapsed by a factor of 33 on any uncurated model.**
`get_effective_context_window` returned the cache value whenever it was positive, so
`gpt-5.2` answered 8 192 against a real 272 000. At `compaction_threshold_ratio = 0.4`
that is a summarization trigger at 3 277 tokens instead of 108 800.

**The fallback table was not a safety net either.** The hand-maintained
`MODEL_CONTEXT_WINDOWS` is wrong on 10 of its 56 entries — `gpt-5.2` at 1 047 576
(the *total* window), `claude-opus-4-6` at 200 000 against a real 1 000 000. Neither
internal source could be trusted over the other.

**Four configured targets pointed at models that were retired or absent.**
`SUMMARIZATION_MODEL_DEFAULT` and 21 `LLM_DEFAULTS` slots named `gpt-4.1-nano`, which
retires 2026-10-23; `LLM_DEFAULTS["image_generation"]` named `gpt-image-1`, same date;
`FALLBACK_MODELS_DEFAULT` named `claude-sonnet-4-5`, absent from the catalogue
entirely, and `deepseek-chat`, deactivated — so the failover chain had **no reachable
target at all**.

**One shipped slot named a model with no row.** `llm_config_seed.sql` pinned
`image_generation` to `gpt-image-2` and `image_generation_pricing_seed.sql` priced it,
but `llm_pricing_seed.sql` never created its `llm_models` row.
`ModelCapabilitiesCache.get` therefore answered `None` and the runtime fell back to
`CONSERVATIVE_DEFAULT`. `verify_reference_seeds.sql` could not catch it: its
postconditions were cardinalities only, and it did not even count `llm_models`.

## Decision

**Two public registries are vendored as a filtered snapshot, and a per-row provenance
records who filled the capability fields.**

`apps/api/src/infrastructure/llm/catalogue/snapshot.json` is a capability-only
extract of `BerriAI/litellm`'s `model_prices_and_context_window.json` (MIT) and
`models.dev`'s `api.json`, refreshed by `task llm:catalogue:fetch` and reviewed like
any other diff. **Nothing reaches the network on an execution path.**

`llm_models.capability_provenance` takes one of three values:

| value | meaning | producer |
|---|---|---|
| `declared` | the column defaults nobody curated — do not trust | the column default |
| `imported` | corroborated by the vendored snapshot | the catalogue sync |
| `verified` | a human confirmed it; the sync may only propose | `LLMModelService.update` |

`get_effective_context_window` then arbitrates instead of guessing: an `imported` or
`verified` row wins over `MODEL_CONTEXT_WINDOWS`; a `declared` one defers to it.

**The value is row-level; the evidence behind it is field-level**, and that distinction
has teeth. `imported` vouches for the columns the registries publish and those only —
`max_input_tokens`, `max_output_tokens`, `supports_tools`, `supports_structured_output`,
`supports_vision`. Every other column keeps whatever it had. Measured 2026-08-24: 41
active OpenAI rows are `imported` while still carrying an unfilled
`supports_strict_mode=false`, a field no registry publishes; a reader that treated
`imported` as evidence about it would switch `gpt-4.1`, `gpt-5.2` and 39 others off the
strict path in one commit. A reader of a column outside that set must therefore require
`verified`. The scope is written on the enum and pinned by a test.

### Every lookup is locked to the canonical provider

models.dev publishes 193 providers, and many republish the same id with contradictory
metadata: `deepseek-v4-flash` appears under 23 of them with output caps from 32 768 to
1 048 576, and `jiekou` declares `gpt-5.2` with the opposite reasoning flags to the
canonical `openai` entry. Matching by model id alone would ingest resale metadata, so
`registry_match.py` maps each LIA provider to the vendor ids that may serve it and
accepts nothing else.

### Four field families are excluded by measurement, not by caution

- **prices** — 85 of 87 models were price-stable over two months and the only two
  "changes" were tier-tracking artefacts; the registries publish one tier among six,
  follow promotions, and neither can express ADR-223 time slots;
- **reasoning metadata** — a naive import invalidates `effort: off` on 21 slots and
  silently switches the pipeline to thinking mode;
- **streaming and the sampling flags** — a false would break SSE on `response`, and no
  registry covers them reliably;
- **`kind`** — LiteLLM's `mode` names the API surface while LIA's `kind` classifies the
  product. Over the 103 matched rows, `mode=chat` maps to `kind=audio` six times and to
  `kind=tts` once. The divergence is legitimate, so no correct consumer exists.

Each exclusion is asserted as a test, so reopening the subject fails the suite.

### Precedence is per field, and each side was measured

LiteLLM documents `max_input_tokens` as the input budget but populates it with the
**total** window on some entries: over the 19 models where both registries state an
input budget, 13 agree and all six disagreements are exactly
`litellm.max_input_tokens == modelsdev.limit.context` — `gpt-5-pro` at 400 000 against
a real 272 000, the `gpt-5.4`/`gpt-5.5` family at 1 050 000 against 922 000. The
explicit `modelsdev.limit.input` therefore wins, LiteLLM comes next, and
`context - output` is the last resort.

models.dev in turn fills `limit.output` with the **embedding dimension** on embedding
models (3072 for `text-embedding-3-large`, 1536 for `-small`, 1 for
`gemini-embedding-001`), and publishes an output cap equal to the model's own context
on nine entries. A caller that knows its row is an embedding gets no output fact at
all, and a cap equal to the window falls through to LiteLLM. Registries also publish
`0` to mean "not applicable" — on all five image entries and the five moderation
entries — so a non-positive token count is treated as absence, never as a value.

### Deactivation requires corroboration; "announced" is not "gone"

Two retirement signals exist and they are complementary: LiteLLM publishes a
`deprecation_date`, models.dev flags `status="deprecated"` on the preview families
providers retire without a date. `is_retiring` (should a build warn?) and `is_retired`
(may the catalogue stop offering it?) are two predicates over those signals, with one
implementation each.

Retirement requires a published date **already in the past** and **no contradiction**.
Of the 71 LiteLLM entries past their date, models.dev corroborates 1, does not list 66
(it drops retired models, so silence is weak corroboration) and **contradicts 4** by
still listing them healthy — `gpt-5.2-chat-latest`, `gpt-5.3-chat-latest` (rolling
aliases OpenAI repoints, where the date expires the snapshot rather than the alias) and
two Gemini image previews. A `status="deprecated"` flag alone never deactivates either:
the seven LIA rows carrying it also carry a date two months in the future.

The asymmetry is deliberate, and it follows the doctrine already written in
`utils/react_budget.py`. Deactivating a live model drops it out of
`ModelCapabilitiesCache` and falls back to `CONSERVATIVE_DEFAULT`, whose
`is_reasoning_model=False` makes the adapter send sampling parameters to a reasoning
model and the provider answer 400. Leaving a dead model listed only leaves a stale
dropdown entry, which the guard surfaces anyway.

### Rejected: letting the registries drive prices

The design initially carried price synchronisation. It was removed on measurement:
over two months, 85 of 87 models were price-stable and the two apparent changes were
tier-tracking artefacts — **0 true positives, 2 false positives**. No official
machine-readable pricing API exists for OpenAI or Anthropic, the registries publish one
tier among six, and neither can express the ADR-223 windowed tariffs. Pricing stays
manual, in `llm_model_pricing` and the seeds.

## Consequences

**The catalogue converged.** The initial correction inserted the missing row, rewrote
3 rows' capabilities, promoted 91 rows to `imported`, stamped 40 deprecation dates and
deactivated 14 retired-and-unreferenced models, keeping **0** because something
referenced them. A re-run of `task llm:catalogue:sync` reports `AUTO 0 / REVIEW 0` and
9 retiring models, none of them uncontradicted.

**Runtime windows are now real**: `gpt-5.2` 272 000, `claude-opus-4-6` 1 000 000,
`gpt-5.4-mini` 272 000, `qwen3.5-plus` 991 808, `gpt-5.6-luna` 922 000. **No compaction
threshold moved**: every configured slot already pointed at a correctly curated model,
`deepseek-v4-flash` (27 slots) staying at a 1 000 000 window and a 400 000 threshold.

**Four time bombs were retargeted.** `SUMMARIZATION_MODEL_DEFAULT` to `gpt-5.6-luna`,
`FALLBACK_MODELS_DEFAULT` to `claude-sonnet-4-6,deepseek-v4-flash`, the image slot to
`gpt-image-2`, and the 21 agent slots on `gpt-4.1-nano` to `gpt-4.1-mini` — the only
candidate with an identical capability shape (non-reasoning, accepts
`temperature`/`top_p`, same 1 047 576 window) and no deprecation date. The cheaper
`gpt-5-nano` was rejected on evidence: it is a reasoning model that accepts neither
sampling parameter, so adopting it would mean rewriting 21 configurations — a
behavioural change that belongs to the execution-profile lot.

**`verified` gained the producer it lacked.** `LLMModelService.update` stamps it when a
human changes a registry-owned capability, so the admin UI and the ADR-228 Excel
round-trip both mark a row as humanly owned. Creation deliberately does not: the form's
untouched defaults are exactly what `declared` means, and claiming they were verified
would make the runtime trust an 8 192 placeholder.

**Five guards keep it honest**, each verified to fail on a reverted fix:

| guard | what it refuses |
|---|---|
| `test_model_capability_provenance_guard` | a configured model no registry knows and no shrink-only allowlist covers |
| `test_no_deprecated_model_referenced_guard` | a code default naming a retiring model |
| `test_llm_config_seed_references_guard` | a seed slot or code default naming a model with no catalogue row |
| `test_snapshot_freshness` | warns past 120 days; never reds, because the build must stay green offline |
| `verify_reference_seeds.sql` | an `llm_config_overrides` row naming a model `llm_models` does not carry |

**The residue is stated, not hidden.** The two registries disagree on the output cap
for 25 of the 143 comparable models with no structural pattern (16 times LiteLLM
smaller, 9 larger). No third source exists; the field feeds admin display and the
reasoning-budget ratio rather than any hard limit.

## Lot 0b — declared is enforced, observed, and reachable

The catalogue telling the truth is only useful if something reads it. Lot 0b
closes the gap between what LIA *declares* and what it *does*.

### Five slots declared what they need; the gate reports, it does not override

`query_analyzer`, `semantic_validator`, `document_generation`,
`memory_reference_extraction` and `open_loop_extraction` all ask their model for
a schema and none declared `structured_output`. They do now — and
`_model_has_capability` stops answering `True` to a capability it does not know,
so a typo in a declaration can no longer disable the constraint silently.

`capability_gate.py` is the single place that decides whether a model fits a
slot, and **what happens next depends on where the model came from**. A policy
candidate is hard-filtered; a model that came from `LLM_DEFAULTS` or from an
admin override is a human decision and is never rejected — the discrepancy is
counted (`llm_capability_mismatch_total{llm_type}`) and logged once per pair.
Absence of evidence is not a rejection either: a model outside the catalogue
yields no verdict at all, so a live Ollama pull stays usable.

Measured on the dev instance: 58 slots resolved, **0 mismatches**, and every
capability-gated slot has 52 to 70 eligible models.

### `supports_strict_mode` gets a reader — and it requires `verified`

See the provenance-scope note above: `imported` vouches for the five columns the
registries publish, and `supports_strict_mode` is not one of them. Only a human
edit is evidence there, so `resolve_strict_mode` narrows on `verified` alone.
Measured: **0 rows are `verified`**, so nothing changes behaviour until an admin
curates one.

### Four observation columns, filled from values that already existed

`token_usage_logs` gains `latency_ms`, `status`, `failure_kind` and `llm_type`,
nullable and unbacked-filled. Nothing had to be invented:
`create_instrumented_config` already put `llm_type` in the run metadata at every
instrumented call site, `duration_ms` was already measured for the debug panel,
and `MetricsCallbackHandler` already classified failures. The classifier moves to
`error_taxonomy.py` so the Prometheus label and the persisted column cannot
drift, and a new `on_llm_error` records a **zero-token row** for a failed call:
a policy that only ever sees successes cannot tell a model that works from one
that never answers.

Fixing the classifier in passing: Python's built-in `TimeoutError` — what
`asyncio.wait_for` raises — carried neither `APITimeoutError` in its type name
nor "timeout" in its message, so every one of them was classified `unknown`. A
timeout a policy cannot see is a timeout it cannot react to.

The controller-window index is `(llm_type, model_name, created_at DESC)`.
`node_name` is deliberately absent: 101 distinct unbounded values were measured,
some carrying prompt fragments.

### The failover chain is asserted where it can be checked

`usable_fallback_models` returns the entries the catalogue can actually serve,
and both the boot assertion and the middleware factory call it — so what is
announced and what is armed cannot differ. Assert, not crash: a chain with no
reachable target disables the middleware and logs loudly, and never prevents a
boot. Verified at runtime: `llm_failover_chain_verified models=["claude-sonnet-4-6",
"deepseek-v4-flash"]`.

### Dead code, and the live bug its removal exposed

`router` and `context_resolver` are gone — registry, defaults, `LLMType`
Literal, `CURRENT_CORE_LLM_TYPES`, the bootstrap critical-type list, 20 settings
fields with their 14 constants, three seed rows (with the `mcp_excalidraw`
orphan) and twelve translations. The derived provider set is unchanged
(`['deepseek', 'openai']`), so the installer questionnaire is untouched.

Closing `base_agent_builder`'s `llm_type_map.get(agent_name, "contact_agent")`
found a real defect the same minute: **`hue_agent` had no mapping at all**, so
every one of its LLM calls had been resolving to the *contacts* slot's
configuration — wrong model, wrong token budget, wrong cost line. A static
search had found nothing; the first boot after the change named it. The failure
now follows the doctrine `_import_tool_modules` already used: raise outside
production so CI catches a forgotten mapping, and in production log, count
(`llm_agent_unmapped_total`) and degrade, because one misconfigured agent must
not take a deployment down.

### The figures above describe the dev instance

The real per-agent configuration lives in `llm_config_overrides`, in the
database, and deployments do not run the same models. Every design decision is
per-instance safe by construction — the correction migration reads the
references of the database it runs on, the gate only reports on a configured
model, the failover assertion reads the instance's own catalogue, and every unit
test reads `LLM_DEFAULTS` rather than a database. What remains instance-specific
is checked before deploying by `task llm:catalogue:preflight`, read-only: it
reports which models *this* instance would deactivate and which it keeps because
it references them, which configured models fail their declarations, and whether
any `verified` row would lose strict structured output.

## Alternatives considered

**Curate the 89 rows by hand.** It fixes the snapshot and nothing else: the next model
lands `declared` and the same defect returns. The provenance column plus a reviewable
diff is what makes the fix repeatable.

**Trust `MODEL_CONTEXT_WINDOWS` and drop the catalogue's windows.** Refused on
measurement: the table is wrong on 10 of its 56 entries.

**One registry instead of two.** LiteLLM alone conflates the input budget with the
total window on six entries and publishes no `status`; models.dev alone states an input
budget on a minority of entries and fills `limit.output` with the embedding dimension.
Each one covers the other's blind spot.

**Import `kind` from the registries.** Refused: `mode` and `kind` answer different
questions, and the seven divergences over 103 matched rows are not errors.

## References

- Design: `docs/superpowers/specs/2026-08-23-llm-model-policy-design.md`
- Plan and its 16 measured amendments: `docs/superpowers/plans/2026-08-23-llm-catalogue-truth.md`
- Upstream licence and provenance: `apps/api/src/infrastructure/llm/catalogue/NOTICE.md`
- ADR-223 (time-slot pricing), ADR-228 (Excel catalogue round-trip), ADR-085 (boot-time registry completeness), ADR-155 (shrink-only allowlists)

## Amendment 2026-10-18 — a slot's budget is held to the output cap the catalogue vouches for

A slot's `max_tokens` is a figure an administrator chose for a MODEL, and it
outlives the model. On 2026-10-17 three production slots (`document_generation`,
`meeting_synthesis`, `subagent`) were switched to a model whose `verified` row
caps its output at 128 000 tokens, and kept the 200 000 chosen for their previous
model, whose cap is 384 000. The provider refused every call
(« max_tokens: 200000 > 128000 »): two document requests on 2026-10-18, each
retried three times, six `invalid_request` rows in `token_usage_logs`; the two
other slots had simply not run yet. The catalogue held the cap the whole time.
Only two branches of the provider adapter capped anything, each its own way (a
name heuristic on the legacy OpenAI path, the catalogue for one DeepSeek
family), and every other client sent the raw value.

**Decision.** One rule says whose output cap is known
(`infrastructure/llm/output_cap.py`): the `max_output_tokens` of a row whose
provenance vouches for it — `imported` or `verified`, the provenances that
column is corrected under (`sync_diff.CORRECTABLE_FIELDS`) — on a `chat` model,
served by a provider that enforces one. A `declared` row carries column
defaults, the discovered Ollama layer publishes a constant
(`OLLAMA_DISCOVERED_MAX_OUTPUT_TOKENS`), and a self-hosted runtime generates
until its context is full (`PROVIDERS_WITHOUT_OUTPUT_CAP`): none of them is a
cap. The column default (`LLM_MODEL_DEFAULT_MAX_OUTPUT_TOKENS`, which the ORM
column now declares itself with) needs evidence of its own, whatever the
provenance: provenance is row-level while its evidence is field-level, and two
writers leave the default under a vouching provenance — the sync promotes a
row as soon as ONE correctable field is corroborated
(`sync_diff._capability_updates`), and the catalogue editor stamps `verified`
on any save, resending the untouched default (`LLMModelService.update`). The
default is therefore a cap only where the vendored registries state that very
figure for the model (`is_unproven_default`, once per model per process, never
the network). Measured in production on 2026-10-18: four vouched chat rows hold
it; replayed against the registries, three carry a registry figure and are
capped, one carries the untouched default and is not. Doubt adds no cap. Three
readers ask the rule:

- the slot resolution (`get_llm_config_for_agent`, through `capped_config`), so
  every reader of a slot's budget — the factory, the document prompt's length
  budget, a meeting transcript's part size, the MCP description reserve — works
  with the capped figure. With the raw 200 000 the document prompt promised the
  model about 110 000 words it could not write;
- the client door (`ProviderAdapter.create_llm`), for a caller passing a budget
  of its own. Behind it, the DeepSeek families keep their own ceilings
  (`deepseek_limits`: the catalogue figure for the thinking family whatever its
  provenance, an unproven default now refused there too, else 64 000; the
  documented V3 literals) and the legacy OpenAI Chat Completions path keeps its
  name heuristic. Both only ever lower further;
- the admin metadata: `/llm-config/metadata` publishes the rule's figure as
  `vouched_max_output_tokens` (ADR-184), and the screen flags a slot whose
  budget exceeds it — a badge on its card, read from the STORED budget the admin
  listing keeps (pinned by a test), and a warning that describes the
  `max_tokens` field while it is edited, measured against the value the save
  will apply (the slot default once the field is cleared) and the model being
  chosen.

A capped budget is logged once per slot, model and value per process
(`llm_max_tokens_above_model_cap`), on the `report_configured_model` pattern;
the stored figure stays the administrator's to correct. The profile is read
defensively, as the reasoning seam reads it: an entry shaped otherwise means "no
known cap", never an error on the instantiation path.

**Not done, on purpose.** Saving a budget above the cap is not refused: the
warning shows it before the save, and the request stays valid either way.
Measured before shipping: applied to production's effective configuration of
2026-10-18 (the code defaults merged with the overrides, once the administrator
had lowered the three slots to 100 000), the rule caps no slot.

**Limits.** A registry figure smaller than the model's real cap now shortens a
budget the provider would accept — the two registries disagree on 25 of 143
output caps (`field_mapping._max_output`); the badge names every slot the rule
caps, and correcting the row lifts it. A real cap equal to the column default
that no registry states is not known, so it is not applied. A slot capped by a
provider branch's own ceiling, or configured on a hand-typed dated model id the
runtime resolves under its base name, is capped without a badge.

**Left open.** The structured-output door still turns any provider exception on
its auto-tool path into « produced no valid tool call » and retries it, so a
permanent refusal of another kind is still retried three times under a
misleading message. And the two provenance writers above also stand behind
`get_effective_context_window`, which trusts a vouched row's input figure, the
untouched input default included.

## Amendment 2026-10-18 b — the env settings of fourteen slots had no reader

The voice comment and the thirteen domain agents (contacts to routes) each kept
a family of nine env-backed settings (provider, provider config, model, the
four sampling values, budget, reasoning) and seven constants feeding them, long
after their LLM calls moved to `LLM_DEFAULTS` and the database overrides. A
census of every settings field over the committed tree found no reader for any
of the 126 fields but the validator listing their names; the model constants of
twelve of them still named `gpt-4.1-nano`, which retires on 2026-10-23.

**Decision.** The fourteen families leave with their 98 constants, their
validator entries, the ranges `scripts/validate_config.py` checked for them and
`scripts/validate_llm_config.py` — a validator no command ran, which no longer
imported and still checked the `router` family this ADR had removed. `Settings`
ignores unknown variables, and no environment template ever declared these keys.

**What the census missed, and the linter did not.** Two of those constants were
not dead: `openai_organization_id` defaulted to `CONTACTS_AGENT_LLM_MODEL_DEFAULT`
and `openweathermap_api_key` to `EMAILS_AGENT_LLM_MODEL_DEFAULT`, wired by a
configuration-alignment pass in 2026-03 — and the first constant was filled in
2026-08 with the maintainer's real organization id, copied from a production
environment. The adapter sends that setting as the `organization` of every
OpenAI client, so an installation whose environment carries no
`OPENAI_ORGANIZATION_ID` — every one the installer writes, since
`.env.min.prod.example` has no such key — presented a foreign organization with
its own key (read from the code, not measured on such an instance). Both fields
now default to an empty value, like their neighbours.

**The second pass, the same day.** The census, rerun by reader rather than by
name, found fourteen more families that only a test, a validator or a
docstring named — `planner`, `semantic_validator`, `semantic_pivot`, the three
HITL slots, the memory, interest, heartbeat, broadcast and query-agent slots —
and two partial ones: `response` and `query_analyzer` keep their timeout alone.
They left with 97 more constants, their validators and the LLM keys
`scripts/validate_config.py` still checked; the query analyzer's metric label
now names the model the slot RAN, not an env value nobody set. The same pass
compared every literal default with a production environment and found two
more of the alignment pass's values: `firebase_project_id` defaulted to the
maintainer's Firebase project — published to every Android shell beside the
operator's own three values, so the route now requires all four — and the
unread `telegram_bot_username` held the maintainer's bot. A default is read
from a constant of its own family, or the pair is declared with its reason
(`test_settings_default_family_guard.py`, shrink-only); the 57 spelling
variants inside one family are accepted.
