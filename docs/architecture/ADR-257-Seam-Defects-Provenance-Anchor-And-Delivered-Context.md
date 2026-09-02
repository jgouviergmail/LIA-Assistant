# ADR-257 — Five seam defects: provenance through compaction, the turn anchor, honest trace counts, coverage-checking validation, and measured delivered context

- **Status**: Accepted
- **Date**: 2026-09-02
- **Related**: ADR-167 (content trust registry), ADR-086 (compaction v2),
  ADR-248 (progress-earned ReAct budget), ADR-133 (execution trace),
  ADR-184 (publish what you enforce), ADR-244 (model capability catalogue),
  ADR-256 (budget conservation)

## Context

A literature review (arXiv cs.AI/cs.MA/cs.CY, 2026-09-01 listings — 299
papers triaged, 12 retained) was used as a reading grid over the codebase.
Every hypothesis was validated with executable proofs against production code
before any change. Five defects survived counter-verification; each is a
**seam defect**: two subsystems, each correct under its own ADR, composing
into a behaviour neither owns.

1. **Provenance laundering through compaction.** ADR-167 marks third-party
   text on the two LLM surfaces it enumerates (pipeline data block, ReAct
   `ToolMessage`). Compaction is a third surface it never enumerated:
   `_compact_impl_llm` summarises marked `ToolMessage`s under a prompt whose
   nine rules preserve identifiers, decisions and actions — and say nothing
   about provenance — then the node re-emits the result as a **SystemMessage**
   that the ReAct windowing deliberately retains on every later turn. Proven
   end-to-end with a compliant summariser: an email body's demand resurfaced
   as an established fact, unmarked, in the highest-authority channel. The
   truncation fallback laundered too: `_extract_identifiers` harvested the
   attacker's URL and address out of the wrapped span and republished them as
   "Key identifiers preserved". Scope: ReAct mode (the pipeline writes no raw
   ToolMessage into `messages`).

2. **The count cap evicts the turn's own question.** ADR-248 deliberately
   lengthened ReAct turns; `add_messages_with_truncate` keeps the LAST
   `max_messages_history` messages. A turn producing 2 messages per iteration
   evicts its own HumanMessage at iteration `ceil(cap / 2)` — measured at
   exactly 75 with the default 150, invariant across prior history lengths.
   Downstream, `window_messages_for_react` splits at the last HumanMessage;
   with none left it short-circuits entirely (windowing AND legacy-system
   hygiene both lost), and none of the seven `react_system_blocks` carries
   the question. Reachability: the compute budget charges model time only
   (ADR-170/256), so 75 iterations fit within 300 s whenever the mean model
   call stays under 4.0 s — and the code default budget is 90 iterations.

3. **The visible trace dropped its head and understated its count.** The
   per-message trace cap kept the tail only (`slice(-100)`), on the live path
   and on reload — erasing the turn's FIRST actions, precisely where an
   injected instruction acts — and the disclosure showed the CAPPED length as
   the step count. Severity re-measured honestly: per-key deduplication
   (frontend `emittedStepKeysRef`, backend `TraceCapture._seen_keys`) makes
   the cap reachable mainly through detail-labelled steps; the backend
   persistence cap is essentially unreachable (distinct i18n keys ≪ 100) and
   was deliberately left untouched.

4. **The semantic validator could name an omission but was never asked to
   look for one.** `SemanticIssueType.MISSING_STEP` is exposed through the
   structured-output schema; the v1 prompt never names it and 0 of its 9
   decision-tree bullets concern an absence — the published "omission
   blindness" failure mode (judges verify presence, not absence; the remedy
   that measurably works is enumerating the demands first, then checking
   coverage).

5. **Delivered context was unmeasured, and Anthropic never cached the
   history.** Iterations and durations were instrumented; the prompt actually
   delivered per iteration was not (measured: 2.3k tokens at iteration 1,
   112k at iteration 90; cumulative input per 90-iteration turn ≈ 5.1M).
   Prefix caching amortises the cost automatically on Qwen and OpenAI — but
   Anthropic caching is NEVER automatic (provider doc, 2026-09-02): it needs
   block breakpoints or a root `cache_control`, and LIA marked only the
   static system block, while a comment claimed the opposite ("caching is
   automatic ≥ 1024 tokens") and hardcoded an Opus-4-era 4096-token minimum.

## Decision

One lot per seam, each TDD'd, each behind the narrowest possible mechanism:

- **B — provenance survives compaction.** `CompactionResult.contains_external_content`
  is computed on BOTH branches (marked message in `to_compact`, or a
  consolidated prior summary already carrying the banner); the node makes the
  summary inherit `COMPACTION_EXTERNAL_PROVENANCE_BANNER` — placed AFTER
  `COMPACTION_SUMMARY_MARKER`, because four readers recognise the summary via
  `startswith` and a prefix change silently drops the conversation's
  compressed memory. The prompt gains rule 10 and a
  "Third-Party Content (Untrusted)" output section; the fallback notice
  splits identifiers by provenance (`_extract_identifiers_by_provenance`,
  fail-closed on an unclosed wrapper). Taint is computed at write time,
  deterministically — never re-derived from what an LLM chose to echo.

- **A — the turn anchor.** `_ensure_turn_anchor` re-pins the last
  HumanMessage after BOTH truncation branches, right after leading
  SystemMessages; a no-op below the thresholds (byte-identical output,
  pinned by tests at the 76th+ conversational turn). The coupling is named
  once: `react_budget_exceeds_state_window(max_iterations, cap)` —
  `max_iterations >= ceil(cap / 2)`, verified on five cap values — and is
  logged with the re-pin WARNING rather than warned at every boot of an
  exposed-by-default configuration. The four false `(default: N)` comments in
  the env files were corrected, and the example files were aligned on the
  code defaults (90 iterations / 300 s — owner-delegated arbitration
  2026-09-02): the budget is progress-earned (ADR-248) so only productive
  loops reach the ceiling, cost stays bounded by the compute timeout, the
  tool budget (ADR-256) and provider prefix caches, and a 15-iteration cap
  would recreate the very defect ADR-248 fixed.

- **C — honest trace.** `capTraceSteps` (ONE implementation shared by the
  reducer and the hydration path) keeps head (20) + tail (80) and counts the
  omission; the disclosure states the TRUE total and renders a translated
  "omitted" line (×6 locales) — a shown count is a claim: exact or absent.

- **D — measure before you manage.** `react_delivered_context_tokens` and
  `react_context_window_utilization` observed in `react_call_model_node`
  through the reducer's memoized counter (`count_messages_tokens_cached` —
  no re-encoding of unchanged history on the hot path), window resolved via
  the same ADR-244 seam the compaction threshold uses, wrapped in a
  best-effort suppress. Two Grafana panels (dashboard 20, `or vector(0)`,
  `noValue: "0"`) satisfy the metric-coverage ratchet. **No compression
  policy ships with this ADR**: the measurement decides whether one is ever
  needed.

- **E — the validator looks for what is missing.** The prompt gains a
  COVERAGE PASS before the decision tree (applied to v1 in place — prompts
  are not versioned in this codebase, owner decision 2026-09-02) — enumerate the request's demands, check each has a covering
  step — with two false-positive shields (analysis demands belong to the
  response LLM; unservable demands are not missing steps). A `missing_step`
  verdict routes to the SILENT replan (ADR-184: a verdict is not a failure),
  bounded by `planner_max_replans`; pinned by routing tests including the
  exhausted-budget case. The cache-hygiene guard now scans every version
  directory that may exist, so a future variant can never silently lose the
  marker.

- **F — Anthropic caching tells the truth and covers the history.** The
  factory payload patch adds the documented root-level `cache_control`
  (auto-moving breakpoint over the growing message history), withheld if four
  explicit breakpoints already exist (documented 400); the static-system
  breakpoint stays. The false "automatic" comments were corrected and the
  hardcoded 4096 became `ANTHROPIC_CACHE_MIN_TOKENS_TYPICAL` with honest
  per-model wording. Default blast radius: one agent (`mcp_app_react_agent`).

- **G — the personalization probe.** LIA injects seven personalization
  sources into the response prompt and measured none of the three published
  side-effect classes. `scripts/eval/personalization_probe.py` is an
  OPERATOR tool (never CI): fixed EN/FR scenarios, baseline vs profile-block
  A/B, three numbers each with its threshold — deterministic leak detection
  (significant-token evidence, morphology-tolerant), stance-flip rate via an
  extraction pass (never a holistic judge), distinct-3 diversity delta. Its
  pure core is unit-pinned.

## Consequences

- The compaction summary and truncation notice can no longer promote
  third-party text to system authority; cost is a one-line banner and a
  bounded untrusted-identifiers clause.
- A ReAct turn keeps its question to the end at any iteration count; the
  state bound (+1 message at most) and normal conversations are unchanged.
- The user-visible action record keeps the turn's opening acts and never
  understates its own length.
- An incomplete plan is now something the validator is INSTRUCTED to detect;
  worst-case cost of a false positive is `planner_max_replans` silent rounds.
- Anthropic-configured agents stop paying full price for the growing history;
  no behavioural change for other providers.
- New shrink-only surface: none added; the metric-coverage ratchet already
  governs the two new histograms.

## Rejected / deferred

- **Backend trace-capture head+tail**: unreachable in practice through key
  deduplication; complexity not paid for.
- **Boot-time refusal (or warning) on the budget/window coupling**: the
  repo's cross-field precedent refuses to boot, which would break every
  existing 90/150 deployment including the maintainer's; an every-boot
  warning on a default configuration is noise nobody reads. The warning
  fires where the coupling actually bites (the re-pin), with
  `budget_coupling_exposed` separating expected cause from anomaly.
- **A TRACER-style learned retention policy**: requires RL, and the measured
  cost is already amortised by provider prefix caches; Lot D's measurement
  is the prerequisite for ever revisiting.
- **Knowledge-graph agent memory**: measurably worse than the existing flat
  hybrid retrieval at matched budget (arXiv 2608.28978); LIA's existing
  retention scoring and supersession already implement what that literature
  validates.

## Sources

- arXiv 2608.29028 (boundary metadata collapse in handoffs) — lot B
- arXiv 2608.31057 (measure agent working memory) / 2608.29363 (TRACER) — lot D
- arXiv 2608.31016 (LLM judges verify presence, not absence) — lot E
- arXiv 2608.30362 (covert indirect prompt injection) — lots B, C
- arXiv 2608.28833 (PRISK, hidden costs of personalization) — lot G
- Anthropic prompt-caching documentation (read 2026-09-02) — lot F
- Executable proofs: session scratchpad `proofs/f1*, f2*, f3*, f4*, f5*, f6*`
  (measurements quoted above; reproduced by the new unit tests)
