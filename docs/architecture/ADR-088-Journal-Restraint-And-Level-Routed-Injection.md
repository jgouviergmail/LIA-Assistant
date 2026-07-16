# ADR-088: Journal Write Restraint + Level-Routed Operational Injection + ReAct Directive Coherence

## Status

Accepted — 2026-06-02. **Amends (does not supersede) [ADR-079](ADR-079-Stratified-Journal-Consciousness.md)**: it keeps the stratified-consciousness architecture (levels, epistemic status, deferred self-evaluation, portrait diffusion) and refines how levels are *written* and *read*.

## Context

After [ADR-079](ADR-079-Stratified-Journal-Consciousness.md) shipped the stratified journal, real usage surfaced a quality regression: the assistant produced journal entries that were frequently useless or actively harmful, without any clear user signal. Two reproducible failure modes:

1. **Surface over-generalisation** — a single short user message produced a standing directive ("WHEN the user writes briefly → DO answer briefly without detail"), which then stripped detail out of every later answer. Message length is not a request for less content; the inference is a non-sequitur.
2. **Capability hallucination** — after a tool returned empty, the assistant wrote a directive asserting it lacked access to the user's data ("I have no access to the user's personal data"), which then made it refuse to even try on later turns.

Root-cause analysis (reading both write prompts and the read path) found a **systemic production bias amplified by an indiscriminate read path**:

- **Write side, both prompts push production, not grounding.** The extraction prompt (`journal_introspection_prompt.txt`) opened with "most conversations do not warrant entries" but spent ~300 lines pressuring the model to extract signals ("L0 sweep", "0-`learnings` is a red flag", "favor under-produced themes", a distribution target). The consolidation prompt was worse: STEP 5 *mandated* L2 synthesis ("you MUST do ONE of", "red flag: 5+ consolidations producing zero L2 — be more proactive"). The extraction model is a low-reasoning `mini`; it obeyed the loudest, most concrete instructions — all of which pushed volume.
- **No grounding or validity bar.** Nothing required an entry to rest on an explicit user signal, nor that the directive be safe to obey blindly. The `WHEN → DO BECAUSE` format manufactured plausible-but-wrong rules from one occurrence, with a fabricated `BECAUSE`.
- **No capability grounding.** Nothing forbade directives about the assistant's own access/tools, so an empty tool result became an enshrined self-limitation.
- **No level discipline at the read path.** `build_journal_context` (`repository.search_by_relevance` + `get_recent_for_user`) filtered by user/status only — it injected **L0, L1, L2, L3 mixed** into operational prompts under the header "BEHAVIORAL DIRECTIVES". So an ambiguous **L0 raw observation** was presented as a directive to apply, and **L3 facets** were injected raw *and* again via the compiled portrait (redundant, mis-labelled).
- **Cross-mode asymmetry.** In pipeline mode, directives reach the planner (reasoning) and response. In ReAct mode, the reasoning loop received only the L3 portrait brief — never the per-turn L1/L2 directives, which reached only the final `response_node`. A procedural directive ("verify Y before acting") therefore steered the plan in pipeline mode but not the tool-calling reasoning in ReAct.

These compound along an **amplification path**: a weak inference → a mis-grounded L1 → consolidation *forces* it into an L2 synthesis → the L2 feeds a portrait facet → the portrait is diffused to every channel. One bad inference can contaminate all surfaces.

The intent of the feature ([ADR-057](ADR-057-Personal-Journals.md), ADR-079) is the opposite: an *organ of operational meta-cognition* that builds **accurate** understanding over time. The levels were defined (L0 raw, L1 directive, L2 pattern, L3 portrait) but had **no operational meaning at read time** — they were cosmetic except for the portrait.

## Decision

Refine the journal along three coherent pillars. Guiding principle:

> **Keep the discriminators and discovery mechanisms (they improve correctness); remove the quotas and mandates (they force production). Give each level a distinct role at read time: L0 = private feedstock · L1/L2 = behaviour · L3 = portrait.**

### Pillar 1 — Write discipline: grounding over production

- **Extraction prompt rewritten restraint-first** (`journal_introspection_prompt.txt`, ~311 → ~150 lines). Default output is `[]`. An L1 requires BOTH (a) **grounding in an explicit user signal you could quote** (a correction, a stated preference, a behaviour visibly repeated in the conversation) and (b) **being safe to obey blindly** (it makes a future response better, never worse). Generic **hard prohibitions** name the error *classes* — never assert a limit on your own capabilities/access/tools (the toolset evolves; an empty result means "not found this time"), never generalise from a single surface feature, never project a third party's trait onto the user. **L0 is a capped release valve** (at most one per turn, default zero; private, never injected; feeds consolidation). A maintenance carve-out makes explicit that the "write nothing" default governs *creation* only — pruning, confidence demotion, and `evidence_outcome` signalling stay welcome.
- **Consolidation prompt de-pressured** (`journal_consolidation_prompt.txt`). STEP 5 keeps the topic-clustering *scan* but makes L2 synthesis **conditional on genuine convergence** ("zero L2 is the correct outcome when no convergence exists; a forced or spurious L2 is worse than none"). STEP 1 dedup keeps its aggressiveness on true duplicates but adds a guard: *never merge two directives that prescribe different actions*. Self-audit and Section 2 lose the theme-distribution targets and keep only the classification discriminators. L0→L1 promotion now requires **recurrence** (an isolated one-off L0 is not promoted).
- **Analyst persona aligned** (`journal_analyst_persona.txt`): the "thematic diversity" production nudge becomes a neutral discriminator note; the quality gate is hardened and made generic ("write only what is TRUE, GROUNDED, and SAFE to obey blindly; never assert a limit on your own capabilities/access/tools").

### Pillar 2 — Level-routed operational injection

The operational read path now carries **only L1/L2 behavioural directives**. L0 (private feedstock) and L3 (already carried by the compiled portrait) are excluded.

- New domain constant `JOURNAL_OPERATIONAL_INJECTION_EXCLUDE_LEVELS = ["L0", "L3"]`.
- `JournalEntryRepository.search_by_relevance` and `get_recent_for_user` gain an optional `exclude_levels: list[str] | None = None` parameter. **Default `None` preserves the current behaviour** — extraction and consolidation call the repository directly and must keep seeing every level.
- `build_journal_context` (the single operational chokepoint: response, planner, heartbeat, reminder, react) excludes the configured levels **by default**, so all existing call sites are fixed without modification. An explicit `exclude_levels=[]` re-enables all levels.

This makes the levels operationally meaningful at last: an ambiguous L0 can no longer masquerade as a directive, and L3 is no longer double-injected.

### Pillar 3 — ReAct procedural coherence

The ReAct reasoning loop now receives the L1/L2 directives, closing the cross-mode gap.

- `react_setup_node` injects, **once at setup**, a bounded set of L1/L2 directives via `build_journal_context` (its own DB session, query = last user message), as a `SystemMessage`. L0/L3 are excluded by the Pillar-2 default.
- The cap is **by count, not by characters** — `JOURNAL_REACT_CONTEXT_MAX_ENTRIES` (new setting, default 3) injected **in full** (`truncate_to_budget=False`), so a directive is never cut mid-sentence. Size is naturally bounded (`N × max_entry_chars`). Set to 0 to disable (portrait only).
- **Deferred self-evaluation stays anchored to `response_node`** (where `injected_journal_ids` is persisted, in both modes) — it is not duplicated in ReAct.

## Architecture

The two distinct read moments, now disambiguated:

| Read moment | Reader | Levels seen | Mechanism |
|---|---|---|---|
| **Operational injection** | response · planner · heartbeat · reminder · **react** | **L1 + L2** only | `build_journal_context` (excludes L0/L3 by default) |
| **Portrait diffusion** | every flow LIA speaks through | **L3** synthesis | `build_journal_user_model_block` (unchanged) |
| **Maintenance read** | extraction · consolidation | **all levels** | repository called directly (`exclude_levels=None`) |

## Storage changes

**None.** No schema change, no migration. The `level` column from ADR-079 is reused; this ADR only changes how it is read and written.

## Consequences

### Positive

- **Kills the two reported failures at the source**: the grounding bar + generic capability prohibition stop ungrounded and capability-asserting entries; runtime validation confirmed sober output (3/4 conversations wrote nothing; the one entry was an L1 grounded in a quoted user statement).
- **Levels finally mean something operationally**: L0 feedstock and L3 portrait no longer pollute behavioural injection; the amplification path is cut at the read stage even when a weak entry slips through.
- **Cross-mode coherence**: ReAct reasoning is now guided by the same directives as the pipeline planner.
- **No truncation in ReAct**: count-capped, full-entry injection; intuitive to calibrate.
- **Zero migration, minimal blast radius**: the operational exclusion is centralised in one function; extraction/consolidation are untouched by construction (default `None`).

### Negative / Trade-offs

- **Sobriety over richness (deliberate bet)**: fewer directives are written and injected. The portrait (always present) carries the relational dimension; richness accrues over time through consolidation. If the journal proves too thin, the lever is to relax via `confidence` (allow reasoned low-confidence inference), not to re-introduce production pressure.
- **L0 promotion yield is unproven**: an isolated L0 that never recurs ages out unused; its primary value is to absorb the L1 over-generalisation pressure, not necessarily to be promoted. Bounded by the per-turn cap and consolidation GC.
- **Capability guard is prompt-only (by choice)**: no structural output filter was added, to avoid over-engineering and a brittle hardcoded tool list. Mitigated by the generic prohibition plus natural attrition (isolated → not promoted → GC'd). Not airtight; observed in production.
- **Minor double `injection_count`**: a directive may be injected at both `react_setup` and `response_node` in one ReAct turn (+2). Acceptable — it reflects real usage.
- **Behavioural discontinuity for existing users**: L0/L3 raw entries that were being injected stop being injected; `journal_zero_injection_age_days` will shift.

## Alternatives Considered

1. **Structural capability filter** (regex/classifier rejecting capability-denial entries before persistence, mirroring the UUID-hallucination filter): rejected as over-engineering. The generic prohibition + level attrition is sufficient for now; revisit if production shows leakage.
2. **Character budget for ReAct injection**: rejected — a char budget truncates a directive mid-sentence, which is worse than absent. A count cap with full entries is predictable (`N × max_entry_chars`) and intuitive.
3. **Full rewrite of the consolidation prompt** (symmetric to extraction): rejected. Its dedup, reclassification audit, epistemic lifecycle, and portrait steps are sound; only the production mandates needed removal (done as coherent block rewrites of STEP 5 / self-audit / Section 2).
4. **Keep injecting all levels and only fix the prompts**: rejected. The L0-as-directive injection is a read-path bug; a prompt that promises "L0 is never injected" while the code injects it would be internally inconsistent.
5. **Per-iteration directive injection in the ReAct loop**: rejected — too costly (a semantic search per iteration). One bounded injection at setup is enough to guide the loop.

## References

- [ADR-057: Personal Journals](ADR-057-Personal-Journals.md) — original feature
- [ADR-064: Journal Analyst Persona](ADR-064-Journal-Analyst-Persona.md) — analyst persona, directive format, dedup discipline
- [ADR-079: Stratified Journal Consciousness](ADR-079-Stratified-Journal-Consciousness.md) — levels, epistemic status, deferred self-evaluation, portrait diffusion (**amended here**)
- [ADR-070: ReAct Execution Mode](ADR-070-ReAct-Execution-Mode.md) — the ReAct loop this ADR makes journal-coherent
- `docs/technical/JOURNALS.md` — operational reference (updated)
