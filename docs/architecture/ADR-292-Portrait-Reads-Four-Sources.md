# ADR-292 — The user portrait reads four sources, and says which

- **Status**: Accepted
- **Date**: 2026-09-17
- **Amends**: ADR-079 (the stratified journal — its diagram claimed the
  consolidation reads memories and interests; it never did), ADR-088 (the
  level-routed injection stays as it is), ADR-184 (a tunable number a prompt
  states is a number the settings own), ADR-269 (a synthesis says what it was
  built from), ADR-280 (a switch is read at the act), ADR-270 (a seam is
  claimed by the boot, never by an import side effect alone)
- **Scope**: `domains/shared/portrait_sources.py` (the seam), one
  `portrait_source.py` per source domain, `domains/journals/portrait_sources.py`
  (the assembler), the consolidation prompt's INPUTS and STEP 7,
  `users.journal_portrait_sources`, the eligibility query, the portrait's API
  and settings card

## Context

The compiled portrait — full in the response and planner flows, brief in the
eleven others — is where LIA carries « who this person is » wherever it
speaks. It was compiled from the journal entries, an optional slice of the
conversation, seven days of usage patterns and, when opted in, health
signals. Meanwhile LIA kept four other records of the same person and read
none of them there: the long-term memories, the interests, the learned habits
and the relationship debriefs. The ADR-079 diagram said the journal « reads
Memory + Interests » and `JournalPortraitResponse`'s docstring said the
portrait was « derived from … memories, interests » — a documented behaviour
the code did not have, which CLAUDE.md classes as a bug.

The owner asked on 2026-09-16 that the portrait be « augmented » with those
four records, and accepted in the design conversation that they enter as
MATERIAL for a synthesis, never as a fact list; that the portrait persist and
show its provenance; that a change in any source make the account eligible
for a consolidation again; and that the portrait's budgets become settings.

## Decision

1. **The sources are OFFERED to `journals` through a seam; `journals`
   imports nobody.** `interests/proactive_task.py` and
   `relations/debrief/llm.py` already import `journals` for the ambient
   portrait block, so `journals` importing them back would close a runtime
   cycle the coupling ratchet refuses — and the ratchet counts local imports
   too. `domains/shared/portrait_sources.py` holds a registry keyed on a
   closed vocabulary (`memories`, `interests`, `habits`, `relation_debriefs`,
   in the prompt's order); each source installs its reader and its
   freshness probe from a `portrait_source.py` module of its own; the boot
   IMPORTS the four and INSTALLS explicitly (an already-imported module wires
   nothing — the ticket-release precedent), then refuses an incomplete
   registry with `StartupCompletenessError`. ONE mechanism for the four, on
   purpose: two of them could have been imported directly, and two shapes for
   one question is how a fifth source would drift.

2. **A reader answers with a STATUS, an exact total and a bounded page,
   and never raises.** `used` (rendered), `empty` (nothing to say),
   `disabled` (a gate refused) or `unavailable` (the read failed — a blind
   source is NAMED, never read as empty). Every reader reads its three gates
   AT CALL TIME: the deployment ceiling, the operator switch
   (`is_capability_enabled`), and the person's own preference where one
   exists (`memory_enabled`, `habits_enabled`, `relation_debrief_enabled`;
   the interests' preference governs their notifications, not the record).
   Memories come pinned then most important, ordered over the WHOLE set in
   SQL beside an exact count, each with the emotional label the memory
   injection uses (moved to `memories/emotional_state.py`, its rightful
   owner) and an ISO date; interests strongest first over the whole set by
   their signal balance; habits through `load_consumable_profile`, so a
   paused or blocked window never colours the portrait either (ADR-214 c),
   plus the ACTIVE recurring requests with shape, hour and usual intent —
   never a date; debriefs READY and under the published injection age,
   against the reader's LOCAL day, headline and standing clamped, the date
   kept so the model treats the line as DATED.

3. **The assembler reads ONE source at a time under budgets the settings
   own, and drops a section WHOLE when the global cap would be broken.**
   `journal_consolidation_{memories,interests,debriefs}_max` bound the
   items, `journal_consolidation_source_item_max_chars` clamps each line,
   `journal_consolidation_sources_max_chars` caps the four together — a cut
   mid-item would hand the model half a memory, so the section is reported
   `unavailable` instead. Four short reads in sequence: a `gather` would hold
   four sessions open for nothing. Every answer is counted
   (`journal_portrait_sources_total{source,status}`, dashboard 23).

4. **The prompt states what the code enforces, and nothing else**
   (ADR-284). The four sections are placeholders of the INPUTS, each rendered
   only when it exists — an empty heading would claim « there is nothing
   here » about something the model was never given. STEP 7 names them as
   MATERIAL, keeps the synthesis doctrine of ADR-079 and adds four RULES:
   never re-list raw facts, never reproduce a memory, an interest line or a
   debrief sentence verbatim, never mention that the sources exist, and « a
   source absent from SECTION 1 is UNKNOWN to you, not empty ». A
   relationship may become a FACET (its role and stakes for the person),
   never a dated fact about somebody else — those stay in the dated,
   name-conditioned debrief injection of ADR-269. The portrait's budgets,
   « ~150-220 » and « ~50-70 tokens » written in prose since ADR-079, are
   now `{portrait_full_tokens}` / `{portrait_brief_tokens}` read from
   `JOURNAL_PORTRAIT_FULL_MAX_TOKENS` (300) and `…_BRIEF_MAX_TOKENS` (70);
   the pure renderer takes them as arguments so the measurement harness can
   render any candidate. The two scaffolds still written inline in the
   service (usage patterns, health) moved to the same lines file
   (`journal_portrait_source_lines.txt`, one parser), unchanged to the byte.

5. **The portrait persists its provenance, and only WITH its words.**
   `users.journal_portrait_sources` (JSONB, versioned) holds the entries'
   count and, per source, `status / used / total`; it is written in the same
   UPDATE as the portrait, so a run whose model returned no portrait leaves
   both untouched (ADR-269's rule on `usage`). The API reads it through one
   lenient door (`provenance_of`): a shape this version cannot read is
   `None`, never a crash. The settings card draws one line — « Compiled from
   12 journal entries, 34 memories and 8 interests » — from the payload's
   numbers, joined with the locale's own list grammar; a switched-off source
   is absent; a source that could not be read is named on a second line.

6. **Freshness reopens the account.** The scheduler's eligibility query
   now OUTER-joins the entries and adds one `EXISTS` per installed
   freshness probe (`memories.updated_at`, `user_interests.updated_at`,
   `user_habits.updated_at`, `relation_debriefs.generated_at`), read on
   `Base.metadata` by table NAME so `journals` still imports no source domain.
   An account with no entry but a fresh memory compiles a portrait; a
   never-consolidated account with a memory does too. No churn loop: the
   stamp is written after the run and a run writes none of the four tables.
   A process that never booted (a script, a narrow test) builds the
   journal-only predicate — never MORE eligible than before, the safe side.

## Alternatives rejected

- **Four direct imports from `journals`** — a cycle for two of them, two
  shapes if mixed.
- **Passing the sections from the scheduler** — the router's synchronous
  consolidation and lever 2 would have needed them too.
- **A second model call to summarise the sources first** — cost, and the
  consolidation model reads bounded material directly.
- **Cutting a section mid-item to fit the cap** — half a memory is a wrong
  memory.

## Consequences

- New modules: the seam, four `portrait_source.py`, the assembler; one
  column on `users` (migration `e6f1b3c5a7d9`); seven settings in section
  `[65]` of the application `.env` files; `MemoryRepository.list_for_portrait`,
  `InterestRepository.count_active_for_user` / `list_active_by_signals`.
- The consolidation prompt carries four more placeholders and a rewritten
  STEP 7; the harness passes the budgets explicitly; the placeholder guard
  credits the four readers as renderers of the lines file (`RENDERED_BY`).
- Measured on Docker dev, 2026-09-17, one real consolidation on the
  configured `journal_consolidation` slot with three memories, two
  interests, a rhythm with two windows and one recurring request, one READY
  debrief and one entry: the four sections rendered with exact totals, the
  account selected by the scheduler's own query, the portrait written in the
  person's language synthesising the phase (the negotiation the debrief
  described), the rhythm, the interests and the relationship as a facet —
  no verbatim line, no mention of the sources — provenance `used ×4`
  persisted and read back, 4 028 tokens in / 2 092 out / 0,0016 € in
  `journal_last_cost_*` and in the ledger. And a limit worth knowing: the
  model overshoots a stated budget by about a third (386 tokens for
  « about 300, never more », 83 for 70) — the setting is what the prompt
  states, not a clamp the code applies.
- Not done, and said: no recompilation triggered by a bookmark (LIA's own
  words are not a portrait source); no change to which flows inject the
  portrait nor to the full/brief choice per flow; no hard clamp on the
  portrait's length.
