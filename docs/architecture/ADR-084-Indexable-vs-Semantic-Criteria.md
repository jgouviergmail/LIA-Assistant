# ADR-084: Indexable vs Semantic Criteria — Universal Planning Principle + Leak Detector

**Status**: ✅ IMPLEMENTED — Phase 1 shipped in `observe` mode (2026-05-15)
**Author**: Claude Opus 4.7 (with `jgouviergmail`)
**Related**: ADR-014 (ExecutionPlan + Parallel Executor — origin of `PlanValidator`), ADR-019 (Agent Manifest Catalogue System — `ToolManifest` extended), ADR-025 (Prompt Engineering Versioning — `smart_planner_prompt` v1 modified)

> **Amended by ADR-184 (2026-07-31).** The `20–50` batch this ADR asked the
> planner to fetch was written as a literal in `smart_planner_prompt.txt`, and
> the catalogue published no bound to contradict it — so on any tool capped
> lower (5 of 8 domains in production), obeying this rule produced a
> `CONSTRAINT_VIOLATION` on every turn. Since ADR-184 the batch size comes from
> `PLANNER_SEMANTIC_BROAD_BATCH`, each parameter's `minimum`/`maximum` is
> published to the planner, and out-of-range values are clamped before
> validation. The principle below is unchanged; only the way its batch size is
> expressed and bounded has moved.

---

## Context

### The diagnostic that triggered this ADR

Repeated runs of `"mes deux prochains rdv médicaux"` (after `semantic_pivot` → `"my next two medical appointments"`) returned **0 events** on every model except `gpt-5.2`. Forensic tracing of three successive test runs against the same calendar exposed two distinct failure modes at the query_analyzer / planner boundary — both invisible to existing validations.

#### Failure mode #1 — `deepseek-v4-flash` without `reasoning_effort`

| Pipeline stage | Output |
|---|---|
| `query_analyzer` | `intent=action, primary_domain=event, **skill_name="briefing-quotidien"**` (mis-classification) |
| `routing_decider` | rule 1 fires (`detected_skill_name` non-null) → `planner` |
| `smart_planner_service` strategy chain | priority-1 `SkillBypassStrategy` matches → returns the deterministic 5-step briefing template |
| `planner_v3_success` | `steps=5, tokens_used=0, used_template=true` (LLM planner never invoked) |
| Generated plan | `get_events(query=None, time_max=+2j, max_results=5) + get_tasks + get_weather + get_emails + list_reminders` |
| Registry items | 0 events (2-day window too short and category-agnostic) |
| User experience | A generic morning briefing instead of an answer about medical appointments |

#### Failure mode #2 — `deepseek-v4-flash` with `reasoning_effort="high"`

Enabling reasoning fixed the skill mis-classification (`skill_name=null`), so `routing_decider` rule 3 fired and the LLM planner was invoked. But the plan it emitted ran into a *different* failure:

```python
get_events_tool(
    query="medical",                    # ← semantic qualifier as text search
    time_min=now, time_max=now+1y,
    max_results=2,                      # ← took "deux" literally
)
```

Google Calendar searches event titles by *literal text match* — events are titled "Dr Dupont", "Dentiste", "RDV labo", "Mammographie", virtually never "medical". Result: **0 events returned**, despite real medical appointments existing in the calendar.

#### Failure mode #3 — `gpt-5.2` (the only working baseline)

```python
get_events_tool(
    query=None,                         # ← left empty: "medical" is non-indexable
    time_min=now, time_max=now+30j,     # ← reasonable horizon
    max_results=30,                     # ← broad batch; clamped to the manifest cap before validation (ADR-184)
)
```

→ 7 events returned → Response LLM filters by content → 2 medical appointments surfaced correctly.

### Why only `gpt-5.2` succeeded

The pre-existing `smart_planner_prompt.txt` rule 4 (`SEARCH LANGUAGE`) already stated *"Non-searchable field criteria → retrieve broad results, Response LLM filters"*. But the rule required three abstractions chained together:

1. **Recognize that "medical" has no literal counterpart** in any structured field of Google Calendar (title, location, organizer, calendar_id) — requires inferring the connector's indexing semantics from the tool description.
2. **Respect the Planner / Response separation** — the planner fetches broad, the Response LLM filters and ranks. This is a *role-allocation* abstraction.
3. **Anticipate the cardinality × filter interaction** — "two" is the final count; `max_results` must be larger to leave the Response LLM filtering room.

Top-tier reasoning models combine these naturally. Weaker models — even with `reasoning_effort=high` — collapse the decision into "encode the filter in the tool parameters" because that *seems* like the locally optimal move.

### Five structural gaps the diagnostic exposed

1. **The rule was casuistic and connector-named**: examples cited Google Calendar / Gmail, biasing the model towards "this rule only applies when I see those names" rather than "this is a universal principle". A new connector (Notion, Slack, JIRA, future MCPs) would re-instantiate the failure.
2. **No structured signal between `query_analyzer` and `planner`**: the analyzer already reads the user query and could flag the semantic terms it spots — but never communicated this to the planner, so each LLM redid the inference from scratch.
3. **No runtime backstop**: even if the prompt was perfect, a non-deterministic LLM can still leak. There was no validation step that recognized the pattern after generation.
4. **No metric**: we did not even know the leak frequency in production. The diagnostic only surfaced because we had a repro on a specific query — the same pattern in different phrasings would silently degrade UX.
5. **No way for a tool to opt out**: future tools doing semantic/vector search natively (Notion AI, embedding-backed stores) would be wrongly caught by any blanket rule.

These map 1:1 onto the four layers shipped.

---

## Decision

Introduce **a universal planning principle backed by a defense-in-depth pipeline**, agnostic to the connector or domain. Ship Phase 1 in `observe` mode (zero plan mutation, log + metrics only). Promote to `autocorrect` mode in Phase 2 after operational telemetry confirms the leak frequency and absence of false positives.

The principle, the structured signal, and the runtime check are all framed in terms of two universal classes of criteria:

| Class | Definition | Destination |
|---|---|---|
| **Indexable** | Value that exists as-is in a structured field of the target store: dates, IDs, sender/recipient, label/category id, status, calendar id, location, has_attachment, language… | Pass to the corresponding tool parameter |
| **Semantic** | Adjective, category, or quality-judgment qualifying *what kind* of item the user wants — with no literal counterpart in any structured field. Concept-level subclasses: nature/category (medical, professional, personal), priority/urgency (urgent, important, critical), quality/ranking (best, favorite, top, most relevant), relative time without a date (recent, old, latest). | Filter+rank downstream by the Response LLM |

A `cardinality × semantic` rule formalizes the interaction: when the user requests *"the N <semantic> X"*, N is the **final count** after Response filtering, not `max_results`. The planner must fetch a broad batch — sized by `PLANNER_SEMANTIC_BROAD_BATCH` and always capped by the parameter's published `maximum` (ADR-184; originally a literal `20–50` in the prompt).

Two exceptions preserve legitimate cases:
1. User explicitly cites the term as a literal string to match (quoted, or "with X in the title/subject").
2. Tool's manifest declares `text_search_mode != "literal"` — the store performs semantic/vector search and the term is a legitimate query.

### Working hypotheses (used to frame the design)

- **H1**: A principle stated *before* the planning rules and at the conceptual level generalizes better than a rule buried among others — placement and framing matter as much as content. *Validated by the prompt-section position chosen.*
- **H2**: A probabilistic structured signal from the analyzer to the planner reduces the redundant inference cost AND gives downstream validators a non-LLM signal to work from. *Validated by the schema field shipped.*
- **H3**: Defense-in-depth must default to non-mutating observation, because false positives are worse than the original problem (they silently corrupt legitimate queries). *Encoded in the three-mode rollout flag.*
- **H4**: Tool metadata is the right place to declare "this tool's `query` does literal vs semantic matching" — it co-locates with the tool's other contractual properties and is consultable by any future validator. *Shipped as `ToolManifest.text_search_mode`.*

---

## What shipped (Phase 1, all 4 layers)

### Layer 1 — Universal prompt section

New section `INDEXABLE vs SEMANTIC CRITERIA (universal planning principle)` in [`smart_planner_prompt.txt`](../../apps/api/src/domains/agents/prompts/v1/smart_planner_prompt.txt), placed **before** `PLANNING RULES` so it acts as a conceptual frame for every rule that follows. Generic, English (coherent with the post-`semantic_pivot` pipeline), connector-agnostic. Covers the two-class taxonomy, the concept-level example list (non-exhaustive, grouped by subclass), the cardinality × semantic trap, and the two exceptions. Interpolates `{semantic_filter_terms_hint}` — `(none)` placeholder when empty keeps the prompt cache-friendly.

**Prompt size impact**: ~370 tokens added. Steady-state cost null after the first call thanks to provider prompt caching (Anthropic 5-min TTL, OpenAI Responses API caching).

### Layer 2 — Structured analyzer hint

New `semantic_filter_terms: list[str]` field on [`QueryAnalysisOutput`](../../apps/api/src/domains/agents/services/query_analyzer_service.py) (Pydantic). Description explicitly frames it as a **probabilistic hint, NOT authoritative** — the planner still owns the decision. `default_factory=list` keeps the schema backwards-compatible: if the LLM omits the field, current behavior is preserved bit-for-bit.

Propagated through:
- `QueryAnalysisResult.semantic_filter_terms: list[str]` (lower-cased, stripped)
- `QueryIntelligence.semantic_filter_terms: tuple[str, ...]` (frozen for the immutable dataclass)
- `ValidationContext.semantic_filter_terms: tuple[str, ...]` (consumed by the validator)
- Interpolated into the planner prompt as `{semantic_filter_terms_hint}` (cf. Layer 1)

The existing `chat_override` block (lines 1162–1173 of `query_analyzer_service.py`, which clears `skill_name` when the LLM reclassifies a turn as conversation) also clears `semantic_filter_terms` for the same hygiene rationale.

Corresponding new section `INDEXABLE vs SEMANTIC HINT` in [`query_analyzer_prompt.txt`](../../apps/api/src/domains/agents/prompts/v1/query_analyzer_prompt.txt) telling the LLM what to emit (English-pivoted form, leave empty when user cites the term as a literal value, never include indexable values like dates/names/IDs).

### Layer 3 — Universal validator (`observe` / `autocorrect`)

New `_check_semantic_leak` method on [`PlanValidator`](../../apps/api/src/domains/agents/orchestration/validator.py), invoked from `validate_execution_plan` for every step of every plan (single-domain, multi-domain, future strategies — no per-strategy duplication). Connector-agnostic: iterates over `TEXT_SEARCH_PARAM_NAMES` (`query`, `q`, `search`, `search_query`, `text`, `keywords`) on each TOOL step. Word-boundary match against the term set after split + strip on punctuation — `"medical"` matches `"medical clinic Paris"` but not `"medicalign software"`.

Gated by `PLANNER_SEMANTIC_LEAK_MODE` (settings field `planner_semantic_leak_mode: Literal["off", "observe", "autocorrect"]`):

| Mode | Action |
|---|---|
| `off` | Kill switch. Nothing logged, no metric emitted. |
| `observe` (default) | Log `semantic_leak_in_plan` warning + emit `lia_planner_semantic_leak_detected_total{tool_name, param_name, mode}` metric. **Plan untouched** — zero regression guarantee. |
| `autocorrect` | NULL the leaky parameter and bump `max_results` to `PLANNER_SEMANTIC_BROAD_BATCH` (default `25`, range `10–100`) **only when** the existing `max_results < PLANNER_SEMANTIC_BROAD_BATCH_MIN` (= `20`). Already-broad values are preserved. Emits `lia_planner_semantic_leak_autocorrected_total{tool_name, param_name}`. |

Both exceptions from the prompt are honored by the validator:
1. **Quoted literal**: presence of `"` or `'` anywhere in the param value → skip (literal-match intent).
2. **Semantic-search tool**: tool's manifest `text_search_mode != "literal"` → skip (the store performs semantic search natively).

The leaky `query` value itself is **not logged** (potential PII); only the matched semantic terms, the step id, the param name, and the tool name appear in the warning.

### Layer 4 — Structural opt-out via `ToolManifest`

New field `text_search_mode: Literal["literal", "semantic", "hybrid"] = "literal"` on [`ToolManifest`](../../apps/api/src/domains/agents/registry/catalogue.py). Default `"literal"` preserves the current behavior of every existing tool — **no tool needs to be updated to ship Phase 1**. Future MCP tools, Notion AI search, vector-search backends can declare `"semantic"` or `"hybrid"` to opt out of the leak detector cleanly.

The field is documented inline with reference to both the prompt section and the validator method, so a future tool author understands the contract without leaving the manifest file.

---

## Rollout strategy (Phase 1 → Phase 2)

The strict ordering is **observe → measure → autocorrect**:

1. **Phase 1 (shipped 2026-05-15)** — `PLANNER_SEMANTIC_LEAK_MODE=observe` by default in `.env.example` / `.env.prod.example`. The validator runs, emits logs and metrics, but does not mutate any plan. **No regression possible by construction**.

2. **Telemetry accumulation (1–2 weeks)** — `lia_planner_semantic_leak_detected_total{mode="observe"}` accumulates per model / tool / param. Operators inspect:
   - Leak rate (% of plans with at least one detection) — target reading: > 3% to justify flipping to autocorrect, < 0.5% means the prompt + hint already cover production.
   - False positives — manual sample of logged events to confirm none of them are legitimate literal searches missed by the quote heuristic.
   - Per-model breakdown of `lia_planner_semantic_filter_terms_emitted_total{model, term_count_bucket}` — quantifies which planners spot the patterns and which rely on the validator.

3. **Phase 2 (conditional)** — operator flips `.env` value to `autocorrect`. **No code redeploy**. The autocorrect path is already shipped and tested; it activates by config alone. Continued telemetry on `lia_planner_semantic_leak_autocorrected_total{tool_name, param_name}` shows how many plans the validator actively rescued.

4. **Phase 3 (deferred, optional)** — if specific tools (e.g. `unified_web_search_tool` for keyword-quoted recipes) generate too many false positives in autocorrect, mark them `text_search_mode="hybrid"` rather than relax the heuristic. The opt-out path is already structural.

---

## Consequences

### Positive

- **Generic across connectors**: no Google/Gmail/Notion identifier appears in the principle. Adding a new connector requires zero validator change — only declaring `text_search_mode` if it's not literal.
- **Generic across plan topologies**: the validator runs in `validate_execution_plan`, so single-domain, multi-domain, and future planning strategies all get the check for free.
- **Generic across models**: the structured hint replaces an inference each model used to redo. Weaker models that can't make the abstraction get the answer pre-chewed; stronger models that can still use the hint as a confirmation signal.
- **Zero-regression rollout**: `observe` mode default makes Phase 1 strictly additive. A bug in the detector cannot break production plans.
- **Defense-in-depth**: prompt + hint + validator + tool-descriptor opt-out all reinforce each other. Failure of any single layer doesn't break the principle.
- **Observable**: 3 Prometheus counters give precise telemetry for the rollout decision and ongoing health.

### Negative / trade-offs

- **The prompt section costs ~370 tokens per planner call** — recovered by provider prompt caches in steady state, but cold starts pay it.
- **The `semantic_filter_terms` field puts more output schema load on the query_analyzer LLM** — a weaker analyzer might emit malformed values, mitigated by post-LLM normalization (lower-case, strip).
- **The word-boundary heuristic in the validator is intentionally simple** — `split + strip(".,;:!?()[]")` against a lowercase term set. It can miss morphological variants (`"medical's"` would still match `"medical"` via `'`-strip but `"medicalize"` would not match `"medical"`). Acceptable trade-off: false-positive cost > false-negative cost during rollout.
- **`autocorrect` is not free of risk** — even with the quote heuristic and the `text_search_mode` opt-out, a tool with non-standard literal-match semantics could see a legitimate plan rewritten. The Phase 2 promotion is gated on operator review of the `observe` logs precisely for this reason.

### Open questions (deferred)

- **Should the hint be cleared on `chat_override`?** Currently yes (same hygiene rationale as `skill_name`), but the rationale is weak: a chat turn never reaches the planner anyway. Cleared mostly for downstream consumer cleanliness.
- **Should multi-token semantic phrases be supported?** Currently the validator's word-boundary match is single-token (`"work-related"` won't trigger unless split into `["work", "related"]` by the analyzer). If telemetry shows this gap matters, a phrase-aware matcher can replace the set intersection.
- **Should the prompt section be versioned (`v2`)?** Per ADR-025 the prompt is version-controlled via `PLANNER_PROMPT_VERSION`. Currently shipped as `v1` modified in-place because the change is additive (new section, no rule removal). If a future revision changes the principle, a `v2` bump is the path.

---

## Implementation summary (Phase 1)

**13 files modified, 1 file created.** All listed in `CHANGELOG.md` v1.20.6 entry. **17 unit tests** in `tests/unit/domains/agents/orchestration/test_validator_semantic_leak.py` covering the 10-row regression matrix (generic listing, indexable filter, quoted literal, semantic-search tool exception, target case in both `observe` and `autocorrect`, cardinality × semantic, mixed, multi-step, conservatism without hint, word-boundary true/false positive) plus 3 mode-gating tests and 2 backward-compatibility tests. Adjacent test suites continue to pass: 521 in `tests/unit/domains/agents/orchestration/`, 276 in `tests/unit/domains/agents/registry/`, 60 across planner/query_analyzer.

The four-layer architecture, the rollout strategy, and the test matrix are documented as one block (this ADR) precisely because the layers reinforce each other and cannot be evaluated in isolation.
