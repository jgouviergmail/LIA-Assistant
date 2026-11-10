# ADR-374 — JEV keeps what someone reads, declares its thresholds and counts its judgements

**Status**: Accepted, 2026-11-08. Revised the same day on the owner's review: the
e-mail-only gate in front of the initiative evaluator is withdrawn (decisions 2 and 3).
**Date**: 2026-11-08

**Amends**:
[ADR-325](ADR-325-JEV-Bounded-Decisions-With-Hot-Switches-And-Accounted-Fallbacks.md) — the
eight collection previews and the initiative utility gate leave; a threshold is a declared,
bounded setting instead of a constant; every paid judgement is counted durably; the
observers' agreement is measured, and observation still never suppresses an extraction.
[ADR-062](ADR-062-Agent-Initiative-Phase.md) — the JEV gate in front of the post-execution
initiative evaluator leaves; the evaluator runs on every eligible tool turn, as before.

## Context

On 2026-11-06 the owner saw many JEV decisions end below their thresholds, for little visible
use, and asked for the thresholds to become adjustable and for statistics to judge them by.
Measured that day on production (read only), on dev, and by paid replays on a proof account
(0.040 € for 468 JEV calls, fictional data only):

- **The threshold is rarely the lever.** Five causes explain the silent decisions: a limiting
  floor (calendar classification, the initiative gate); an all-or-nothing composition (radio,
  HITL exclusion); an eligibility gate upstream (consultations); no consumer at all (the eight
  collection previews, the four observers); and a confidence that measures concentration, so
  that its meaning depends on the number of options (0.99 over two options lets only
  p = 1.00 through).
- **Nothing could be judged from outside.** Twelve thresholds lived as constants in seven
  modules; no confidence outlived the one-hour diagnostic trace; `jev_decisions_total`
  counts a batch rather than a judgement, mixes `disabled` with decisions, and production
  keeps one week of Prometheus.
- **The collection previews have no reader.** Their only surface, the « first results »
  panel, was hidden on 2026-10-04 (ADR-325 amendment). The web reducer still wrote
  `resultPreviews`; no component read it. Their measured quality (no wrong verdict over 122
  items at 0.94) does not matter when nothing shows them.
- **The initiative's JEV gate decided nothing.** `initiative_utility` answered 0.67 to 0.77
  where the evaluator acts and 0.41 to 0.81 elsewhere, and production never saw it answer
  « nothing useful ». Behind it, the evaluator itself had nearly stopped producing
  anything — seven days: 89 evaluations, no action, a follow-up chip on 1 answer in 104, for
  8.24 € over thirty days and up to 2.9 s per tool turn — since its prompt was rewritten on
  2026-09-15 to act only on an operational friction (ADR-062 amendment of 2026-11-08).
  Replayed with that prompt on twelve faithful fictional states, it acted on the four that
  carried an urgent e-mail or an invitation awaiting an answer and refused every calendar
  list.
- **The observers are the best pre-extraction filter, and they are off.** Replayed on the
  repository's independent extraction battery, the shipped observer judged no positive turn
  « empty » at 0.50 or more, and set aside at 0.90 every empty interest turn (14 of 14) and 8
  of 11 empty memory turns. Nothing compares its verdict with what the extractor then
  proposed: the agreement is unmeasured.

## Decision

1. **The eight collection previews leave** (`filter_email`, `filter_event`, `filter_task`,
   `filter_file`, `filter_reminder`, `filter_ticket`, `filter_mcp`, `filter_document`): their
   modules, questions, switches and slots, the `result_preview` stream event, the reducer
   field and the debug coverage. A migration deletes their `system_settings` and
   `llm_config_overrides` rows before the code that no longer knows them boots: an unknown
   key of a `native_enum=False` column read without a filter raises `LookupError`.
2. **The initiative's JEV gate leaves; the evaluator runs as before.** `initiative_utility`
   leaves with its question, switch and slot, and the evaluator sees every eligible tool
   turn. The e-mail classification learns whether a message expects a reply, shown as a
   badge and read by the response. Withdrawn on review the same day: an e-mail-only gate
   that called the evaluator only after an urgent, critical or reply-expecting e-mail. The
   same call produces the read-only enrichment (the weather on a route, the journey to an
   appointment), the suggestion, the follow-up chips and their motivation, so the gate
   would have taken all of them from every other turn.
3. **No exit criterion for the initiative node here.** The criterion written with the
   e-mail gate left with it; ADR-062 governs the node.
4. **Qualified usages that are off stay.** The meeting template, the radio verifier, both
   consultations, HITL exclusions and refusals, personal references and the four observers
   keep their record of 2026-10-26; the owner switches them on. The guarded parameter values
   stay: that guard can only add a refusal.
5. **A threshold is a declared setting.** `domains/llm_config/jev_gates.py` declares every
   gate: its question keys, what its score is (a choice's confidence, a classification's
   bounded concentration, a Noul's margin), its shipped default, its bounds, its scope (each
   answer, or all of them) and which choices can conclude through it — an abstention
   concludes nothing at any threshold. The values live in `system_settings`, one JSON key per
   usage holding only the values that differ from their default, read in the same query as
   the switches, frozen in the operation's snapshot and carried by `DecisionAttempt`; every
   consumer decides through `gate_passes`, never a constant. One predicate,
   `threshold_refusal`, judges a value for the screen's write (a 422) and for a stored row's
   read: a value that is not finite, finer than the hundredth, out of its bounds or naming
   an unknown gate falls back to the default, logged. Comparisons are exact (`Decimal`): `p >= 1 - margin` in floating point
   refused p = 0.82 against a 0.18 margin. The administrator moves a gate within its bounds on
   the « JEV integrations » screen, which says « outside the qualified record » as soon as a
   value differs from its default, and the classification policy fingerprint hashes the
   EFFECTIVE thresholds, so a label published under another threshold is never served. No
   default changes here: lowering the e-mail priority floor from 0.80 to 0.50 wins one e-mail
   in 134 on the committed corpora; it is adjustable, not moved.
6. **Every paid judgement is counted durably.** The runtime records, after each successful
   paid attempt, every answer a gate judges in a daily histogram at the hundredth,
   independent of the threshold (`jev_gates.judgement_bucket`): a confidence at
   `floor(score × 100)` read on its decimal, a margin's judgement at its distance to a
   certain answer, `ceil(min(p, 1 − p) × 100)` — the only bucketing under which « concludes
   at this threshold » is exact for both kinds, a Noul's probability having no bounded
   precision (an exhaustive test holds it against `passes` at every threshold the screen
   offers). Each consumer's outcome goes through one door, `count_jev_outcome`
   (`jev_statistics_sink.py`), the only writer of `jev_decisions_total` (AST guard); a
   `disabled` outcome reaches the counter only. Each worker aggregates in memory and its own
   flusher writes a sorted, chunked, atomic UPSERT every `JEV_STATISTICS_FLUSH_INTERVAL`
   seconds (30), and once more at shutdown within `JEV_STATISTICS_FINAL_FLUSH_TIMEOUT`: a
   killed worker loses at most one interval of counts, never a partial row (measured on
   PostgreSQL, eight writers: unsorted, 27 deadlocks in 320 statements; sorted, 150,022
   acknowledged and 150,022 stored; the integration test keeps eight concurrent writers
   exact). A flush whose statements fail keeps its batch for the next one; a flush whose
   commit fails drops it, its outcome unknown, rather than count it twice. Volume, cost and
   the median latency are read from `token_usage_logs` in one aggregate grouped by slot. The
   screen shows, per usage, the outcomes and, per gate, the share the slider's position
   concludes — recomputed from the buckets as it moves — and the distribution in ten bands.
7. **The observers' agreement is measured, not acted on.** Each observation also records its
   verdict, its confidence bucket and whether the extractor proposed anything, as the
   extractor's own parse reported it (`set_proposals`): an output it could not read counts as
   proposing, and an extractor that stopped before parsing files no agreement. Skipping an
   extractor stays forbidden (ADR-325 §3) until an amendment reads, for that extractor, no
   confident « empty » contradicted by a proposal over at least 200 observations across four
   weeks.
8. **Three corrections.** The extraction selectivity battery imports what exists and renders
   the four messages the extractors read; the two classification usages get their help text
   in six languages; a JEV call waits as long as its slot says (`timeout_seconds`), and the
   5 s ceiling the code laid over the database is gone.

## Consequences

- The chat stream loses an event no screen used, and the response node two background tasks
  per search turn. A tab opened before the deployment ignores an event it still knows.
- The initiative evaluator keeps its cost on every eligible tool turn (about 8 € a month and
  up to 2.9 s before the answer, measured): it is what the enrichment, the suggestion and
  the follow-up chips are paid with.
- An administrator can lower or raise a threshold and see its effect on the real
  distribution, with the qualified record named whenever the screen leaves it. A threshold
  moved outside its record is a decision the screen states, not a silent drift.
- A diagnostic trace written by an earlier version is skipped on reading, never a failure of
  the whole panel.
- A deployment that rolls back keeps working: the downgrades write no retired switch back
  (the former code reads a missing switch as off and a missing slot as its defaults), delete
  the threshold rows the former code cannot read, and drop the statistics tables.
- The statistics tables hold registry codes and counts, no user column: nothing to purge
  with an account or to export, and no purge ships (their growth is bounded by keys per day).

## Implementation (2026-11-08)

Decisions 1, 2, 5, 6, 7 and 8 are implemented
([the plan](../superpowers/plans/2026-11-06-jev-rationalisation.md), lots A to F). The
e-mail classification's « expects a reply » (decision 2) is its third question, a
Noul decided at the `reply_expected` margin (0.30) and published only beside an accepted
legitimate category, spam and phishing being always « no reply »; requalified on the
three corpora by one paid replay (36 calls, 0.0093 €) with no wrong accepted label on any
dimension ([EMAIL_EVENT_CLASSIFICATION.md](../technical/EMAIL_EVENT_CLASSIFICATION.md)).
The e-mail-only initiative gate was implemented, then withdrawn on review the same day
before any commit. Decision 7's skipping (lot G) waits for its measured condition.

## Alternatives considered

- **Keep the initiative JEV gate with another question.** It could not discriminate on the
  states where the evaluator acts, and the evaluator's refusals follow rules a utility
  question does not see.
- **Call the evaluator only after an e-mail that calls for a follow-up** (adopted, then
  withdrawn on review). The 89 empty evaluations measured an evaluator its 2026-09-15
  prompt had already narrowed, not a useless node; the gate would have taken the weather on
  a route, the journey to an appointment, the suggestion and the chips from every other
  turn.
- **Give the previews a surface.** The owner hid the only one; a second surface is a product
  decision nobody asked for.
- **Prometheus as the statistics store.** One week of retention in production, `increase` is
  not an integer, and a histogram per gate multiplies the series; a daily aggregate table
  answers « what happened this month » exactly.
- **Lower the thresholds now.** Measured, the floors are not what silences most decisions,
  and every default change would need a paid requalification; the screen makes the change
  possible once the real distribution argues for it.
