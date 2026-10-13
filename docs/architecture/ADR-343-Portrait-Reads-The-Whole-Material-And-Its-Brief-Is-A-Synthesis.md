# ADR-343 — The portrait reads the whole material, and its brief is a synthesis

- **Status**: Accepted
- **Date**: 2026-10-12
- **Amends**: ADR-292 (four sources under five caps; the budgets « stated,
  not a clamp »), ADR-079 (the brief as « core essence in 2-3 dense
  sentences »), ADR-284 (a prompt states what the code enforces), ADR-269 (a
  dated synthesis is kept, never replaced by nothing), ADR-184 (what is
  mechanically repairable is repaired), and the portrait pipeline that shipped
  with commit 499c4cecc (v3.0.0) without an ADR of its own — proven claims,
  a semantic review, a hard clamp before the review, a brief carved out of the
  full, a wipe on every journal change
- **Scope**: `domains/shared/portrait_sources.py` (the seam, nine keys), one
  `portrait_source.py` per source domain, `domains/journals/portrait_sources.py`
  (the assembler), `source_state.py`, `consolidation_output.py`,
  `consolidation_settlement.py`, `lifecycle.py`, `removal_commands.py`,
  `portrait_read.py`, `portrait_builder.py`, the consolidation prompt (the
  review prompt and `portrait_review.py` are deleted by § 6), the journals
  settings, the settings card and its six locales,
  `scripts/journals/measure_portrait.py`

## Context

The portrait went from a free synthesis to a pipeline of proofs in v3.0.0, and
nobody measured what the person received. Measured on 2026-10-12, production
and dev, before anything was decided:

| Fact | Owner's account, production | Dev, three accounts |
|---|---|---|
| Claims proposed → cut by the budget before review → rejected → published | 6 → 1 → 2 → 3 | 3→1, 6→5, 2→2 |
| Published full | 736 characters, 140 of 300 tokens | 122 / 459 / 389 characters |
| Published brief | ONE claim of the full, 257 characters | one or two claims everywhere |
| Sources the prompt received | memories 38 of 81 (2 clamped into ineligibility), interests 15, habits 1, debriefs 0 of 3 (all three clamped into ineligibility) | — |
| Sources the published claims cited | journal entries only | journal entries only |

Three mechanisms produced it. The brief was packed from the full's own
paragraphs under 70 proxy tokens, and a paragraph weighs about fifty, so one
fitted — the prompt promised « a synthesis, not a chopped full text », which the
code could not produce. Five caps bounded the sources (40 memories, 30
interests, 10 debriefs, a 200-character clamp per item that made every clamped
item INELIGIBLE as a proof, 12 000 characters in all), and the prompt's rule
said only journal rules could support a claim, so the four sources were read and
never cited. And every journal change set the four portrait columns to NULL:
between an extraction and the next consolidation (a 5-hour scheduler, a 6-hour
cooldown) no surface had a portrait at all — the owner's « it does not show the
profile any more » of that morning.

The owner's directives: the portrait is fed from ALL the material LIA keeps,
never a limited or truncated selection; the brief is a real summary; the
synthesis is complete; and nothing ships before a measured simulation.

## Decision

1. **Every record about the person is a portrait source, read WHOLE.** The seam
   keeps its closed vocabulary, grown from four keys to nine in the prompt's
   order: `memories`, `interests`, `habits`, `relation_debriefs`, `open_loops`,
   `workboard`, `routines`, `reminders`, `bookmarks` — each with a
   `portrait_source.py` of its own (reader, gates read at call time, exact total,
   never raises, a `FreshnessProbe`), each line one whole item. Not a source,
   and why: the psyche state (LIA's own inner state, numbers the prompt forbids
   restating), the meeting minutes (third parties' words), the peer connections
   (a roster of names). The conversation slice stays the person's option.

2. **One physical bound replaces five caps, and a cut is stated.** The item
   caps, the per-item clamp and the character cap are deleted. The sources may
   take `JOURNAL_CONSOLIDATION_SOURCES_WINDOW_FRACTION` (0.5) of the
   consolidation slot's effective context window (ADR-278's door); sections keep
   their order; when the material exceeds the share, the LAST sections lose items
   from their END at item boundaries, and the provenance states `used` of
   `total` with `reason: over_budget` (ADR-286's rule) — a section whose header
   alone does not fit stays `used` with `used: 0`, never « could not be read »,
   and the settings card names the cut sources on a line of their own. One
   length per item line, `PORTRAIT_ITEM_MAX_CHARS` (the seam's), is a CUT, counted
   as `cut_items`, never a drop; a kept answer's excerpt stops at
   `BOOKMARK_EXCERPT_MAX_CHARS` with the bound stated in its header and NO marker
   in the line (review 2026-10-12: the catalogue admits whole lines only, so a
   marked excerpt was invisible to the model). On the measured deployments (a
   1 000 000-token window) the share is never reached.

3. **The brief is written as its own claims.** `PortraitClaim.placement` is
   `full` or `brief`; the prompt asks for two or three short brief sentences,
   each a claim with its own supports, condensing what the full claims establish;
   `grounded_portraits` publishes each format from its own claims. The brief is
   no longer a prefix of the full.

4. **The portrait is an ANALYSIS of the person, under the v1.45 contract, on nine
   sources** (amended 2026-10-12 b, after the owner's reading of the measured
   output). The v3.0.0 commit `499c4cecc` (2026-10-11, ADR-335 to 338 — none of
   which names the portrait) had replaced the v1.45 instruction « a faceted
   synthesis of the living person » by « describe only what the cited evidence
   supports, preserve each passage's scope »: under those rules the only safe
   sentence restates one item, and the measured output was the material
   paraphrased, one paragraph per source, enumerations included. STEP 7 is the
   v1.45 contract again, extended to the nine sources: a READING of the person
   across the sources on seven facets (`posture`, `focus`, `context`, `rhythm`,
   `tension`, `interaction`, `uncertainty`), never an inventory — no list of
   items, no paragraph per source, a fact only as the ground of a reading, a
   pattern named from the set rather than its items, one isolated item grounding
   no trait. Measured (2026-10-12 c), the model named a pattern and then listed
   what grounded it — the protected slots, the tickets, the open loops — so STEP 7
   says NAME THE PATTERN AND STOP (amendment 2026-10-13): the items are the
   claim's `supports`, shown apart; one example at most; a final reread rewrites
   a sentence that walks through slots, tasks or commitments; `rhythm` names the
   KINDS of time defended, never the slots; and the contrastive example is
   unrelated to the measurement persona, so it cannot be copied into the
   measured output. The brief is the core essence in two or three sentences. A
   reading cites EVERY item it rests on (`PORTRAIT_CLAIM_SUPPORTS_MAX` — a cap of
   eight had forced one-item paraphrases). The budgets
   (`JOURNAL_PORTRAIT_FULL_MAX_TOKENS`, `JOURNAL_PORTRAIT_BRIEF_MAX_TOKENS`) are
   targets the prompt states;
   the publication keeps every admitted reading whole (owner rule: the synthesis
   is complete). Policy `analytical_reading_v5`: every stored portrait is
   recompiled once.

5. **A claim is repaired or dropped, never fatal to the batch.** A provisional
   claim filed under another facet than `uncertainty` is REPAIRED (the facet is
   metadata). A claim whose reference the snapshot cannot resolve — an unknown
   or ambiguous id, a passage that is not the whole current rule, a duplicate,
   an entry this batch changes — is DROPPED and logged
   (`journal_portrait_claims_dropped`, codes only; `admit_portrait_claims`).
   Measured: with the old rule, three candidate consolidations of three were
   refused whole for one such claim, three paid generations for nothing. The
   maintenance actions follow the same rule since the amendment of 2026-10-13:
   measured, ONE action had voided a whole paid run, portrait included, in 3
   runs of 11 on the measurement persona — twice a synthesis on immature rules,
   once supports cited by their portrait id. An abstraction its supports cannot
   carry is REPAIRED (`repair_maintenance`: a new entry is created at L1, an
   update keeps the entry's level, a rewrite of a validated L2/L3 keeps its
   words — the level is evidence the code decides, as `_confidence` already
   lowers a confidence), counted (`journal_maintenance_abstractions_repaired`);
   an action the parser cannot read or the snapshot refuses is DROPPED alone,
   with every action naming the same entry (`_parse_actions`,
   `admit_maintenance`, `journal_maintenance_actions_dropped`, codes or fixed
   reasons only); an answer of actions alone, every one refused, is still
   `invalid_output`. Steps 3 and 5 and the transactional rules of the prompt
   publish all of it, and Step 5 says which identifier a support is — an
   entry's `id`, never a `portrait_item_id`, the confusion measured. A failure
   WHILE writing still rolls the whole transaction back (no case observed:
   isolating each write is not built), and a snapshot that moved during the
   call is still `stale`. A batch whose EVERY claim was dropped compiled nothing —
   the words stay, nothing is stamped, the pass is `no_op` when it applied
   nothing — and so does a batch whose only surviving claims are `brief`: a
   brief alone would replace a good full with nothing (review 2026-10-12 b).
   The same review found that a claim-LEVEL fault — a 41st support, a figure in
   a sentence, an unknown facet, a text past its bound — voided the whole paid
   run through the payload's schema: the claims are now read one by one
   (`_parse_claims`), a duplicate support is folded and the tail past
   `PORTRAIT_CLAIM_SUPPORTS_MAX` cut (repairs), an unreadable claim is rejected
   alone with its codes (`rejected_claims`), and both caps are published to the
   model (`{portrait_claims_max}`, `{portrait_supports_max}` — ADR-184). Only an
   action that actually CHANGED its entry bars the claims citing it (a
   zero-effect update is no change), and a paragraph whose own proofs resolve
   is never dropped as the twin of an earlier one whose proofs did not.

6. **No model reviews the readings; what refuses invention is structural.** The
   v3.0.0 semantic review (a second paid call judging `supported`,
   `scope_preserved`, `uncertainty_preserved`, `synthesized` per claim, with a
   receipt bound to the publication) is REMOVED, with its prompt, its receipt,
   its ceiling and its tests. Measured on the analytical contract, 2026-10-12 b,
   on the proof account (deepseek-flash, 0.128 €): the generation wrote
   readings — 0 paragraph restating an item, 0 enumeration, 2 to 2.3 kinds of
   record per reading, against 3 enumerations and one source per paragraph for
   the descriptive baseline — and the reviewer rejected 1 of 9, 3 of 10, 3 of 10
   as « unsupported », after two successive recalibrations of its criterion, the
   second telling it in so many words to refuse only an invented FACT or a
   contradiction and to pass interpretation. A verifier demands a literal proof;
   an analysis has none by definition. What stays is deterministic, claim by
   claim: a reading cites items of THIS snapshot or it is not published
   (`validate_portrait_claims`); a paragraph that RESTATES one cited item — half
   its content words or more are that item's, labels and date stripped, the
   function words of the six languages left out (`PORTRAIT_RESTATEMENT_OVERLAP`,
   `PORTRAIT_STOP_WORDS`; `content_words` is the ONE reading the measurement
   harness shares, so what is measured is what is enforced) — is dropped; a
   person's name the cited items carry STRUCTURALLY — the head of a relationship
   debrief, the counterparty of an open loop — drops the paragraph that repeats
   it, and nothing is guessed from capitals: every German noun is capitalised,
   so are the English weekdays, and a first guard reading capitals as names
   (written, then measured against the corpus) would have dropped a legitimate
   German reading on every turn — a name in a memory's free text stays the
   prompt's rule, measured: seven readings of seven carried none; a figure, an
   e-mail address, a URL, an ISO date, a UUID or technical metadata in the prose
   drops the claim
   (`_TECHNICAL_STYLE`); the batch rule; the provenance drawn under the words
   with the sources and the cut; the stored supports that make the erasure
   surgical — every support read through ONE `CatalogueIndex` per pass (review
   2026-10-12 c: re-parsing and re-hashing a section for every support cost
   0.8 s on 150 items and 10.6 s on 2000, one batch of 32 claims × 40 supports,
   synchronous CPU under the owner lock; 3 ms and 44 ms since) — a batch whose
   every claim the PARSER rejected keeps the words like one whose every claim
   was dropped at resolution (the readable list is empty, which is not the
   model saying the material is insufficient); and the person's three levers
   (flag, edit, recompile). Written
   down as NOT checkable without a model: the scope of a reading, a hedge the
   words should carry, a causal link the set does not show — and the
   portrait is injected into every prompt while its material includes text a
   third party wrote (a ticket, a kept answer): the second model was a weak
   barrier against an instruction smuggled into a reading, STEP 7's « data,
   never a command » is the one left, an accepted risk. One model call per
   consolidation again (about 40 % of the cost and 60 to 120 s less), as
   before the rupture.

7. **A journal change marks the portrait STALE; nothing but a publication
   replaces its words.** `mark_journal_changed` moves the revision and keeps
   the four columns; a settings change and a pass that compiled nothing keep
   them too (an explicit empty compilation still clears them: the model said
   the material is insufficient). `portrait_is_current` keeps its one meaning —
   it decides `stale`, never visibility — and runs where the person acts on it:
   `read_managed_portrait` serves the words with `stale: true` and the card
   draws « a recompilation is pending ». The ambient block ALWAYS carries its
   compilation date and a sentence that a fact stated in the turn wins, and
   runs NO probe (review 2026-10-12 c: the nine-source probe cost 14 ms fixed
   plus a hash of every row of the record, two to three times per chat turn,
   to decide one line — the date is a fact the row already holds). ADR-269's
   doctrine: replacing a usable synthesis with an empty
   panel turns « I could not refresh this » into « there is nothing ». Three
   precisions from the review (2026-10-12). **An ERASURE is not staleness**: the
   removal door (`remove_journal_entries`, the UI and the application tool)
   calls `withdraw_journal_supports`, which takes from the portrait every claim
   resting on a removed entry — the claims are stored with their supports — and
   re-renders each format from what stays (`withdrawn_claims` counted); a legacy
   portrait whose claims cannot be read is wiped whole; `_verify_removed_scope`
   refuses a removal that left a claim on a removed entry. A service-level
   delete inside the consolidation marks stale and the publication that follows
   never cites the entry (`_unchanged_supports`). **A pass that compiled nothing
   keeps the previous provenance WHOLE**: re-stamping the new revision on old
   words read them as current. **Switching journals off stores the words and
   serves nothing** (`journals_enabled` gates every reader); withdrawing the
   conversation-history consent keeps them — every claim rests on records the
   account still holds, never on the slice.

8. **The prompt states what the code does.** One `{portrait_sources}`
   placeholder renders every section in the declared order; STEP 7 names the
   nine sources as evidence on a par with the journal rules, asks for one
   reading per facet the material supports (seven facets, most important
   first) and the brief as its own sentences; the budgets and both caps are
   stated from their constants; the server's own refusals are stated as they
   are enforced, and no verifier is promised. Omitting `portrait_claims` keeps
   the current portrait; an EMPTY list clears it, and the prompt says so. The
   policy version moves to `analytical_reading_v5`, so every stored portrait
   is recompiled once at its next eligible pass.

9. **A repeating reminder is its schedule, never its next instant.** The
   reminders reader renders the instant of a one-off reminder and the recurrence
   of a repeating one, and its probe hashes `content`, `recurrence` and `status`
   — `trigger_at` moves at every firing, and hashed it reopened a paid
   consolidation after each (review 2026-10-12). The habit profile's payload and
   the debriefs' daily expiry predate this lot and are left as they were.

10. **Measured before it is trusted.** `task journals:portrait:measure` seeds
   an INVENTED persona (`scripts/journals/portrait_corpus.json`) into the proof
   account on dev, runs the real `consolidate_journals_for_user` and reads what
   it published; the report of 2026-10-12 is
   `docs/superpowers/plans/2026-10-12-portrait-whole-material-simulation.md`.

## Alternatives rejected

- **Raising the five caps** — a larger page is still a page, and the 200-character
  clamp would still make a long memory ineligible as a proof.
- **A second model call to write the brief from the approved full claims** — one
  more paid call per consolidation for what the generation can do in the same
  call, with the same verification.
- **Keeping the budgets as clamps and raising them** — any clamp drops a verified
  facet whole; the owner's rule is that the synthesis is complete.
- **Keeping the semantic review as a gate and recalibrating its criterion** —
  tried twice on 2026-10-12 b (grounded synthesis, then « refuse invention and
  contradiction only »): 70 to 80 % of grounded analytical readings still
  rejected; a reviewer that must find a literal proof shrinks every portrait
  back to its sources, which is the defect the lot set out to remove.
- **Keeping the review as a logged diagnostic that gates nothing** — a paid
  call whose verdict nothing applies; dead code with a bill.
- **Hiding a stale portrait** (the v3.0.0 behaviour) — measured on production,
  the portrait was absent for hours after every conversation; a dated synthesis
  beats none, and the gate still says it is dated.

## Consequences

- Five new `portrait_source.py` modules (open loops, workboard, scheduled
  actions, reminders, bookmarks) and five scaffold blocks in
  `journal_portrait_source_lines.txt`; `SourceBudget`, `ITEMS_BOUNDED_BY_SOURCE`
  and the memories' selection query are gone (`clamp_item` stays for the
  radio); `flat_item` collapses newlines and cuts nothing.
- Settings: `JOURNAL_CONSOLIDATION_MEMORIES_MAX`, `…_INTERESTS_MAX`,
  `…_DEBRIEFS_MAX`, `…_SOURCE_ITEM_MAX_CHARS` and `…_SOURCES_MAX_CHARS` are
  deleted; `JOURNAL_CONSOLIDATION_SOURCES_WINDOW_FRACTION` (0.5) is added;
  `JOURNAL_PORTRAIT_FULL_MAX_TOKENS` moves from 300 to 400;
  `NEXT_PUBLIC_JOURNAL_CONSOLIDATION_TIMEOUT_MS` moves from 240 000 to 330 000
  (the server bound is 300 s; measured 199 s on production when the
  consolidation still made two model calls with reasoning — kept with the
  margin, the single call still reasons over a 40 000-character prompt).
- `JournalPortraitResponse.stale`; the settings card draws the stale line, nine
  provenance sources and the sources the window cut, in six languages, and
  starts on the format the portrait has; the frontend marks the portrait stale
  after a write instead of blanking it; the provenance carries `cut_items`,
  `omitted_claims` and `withdrawn_claims` (a `portrait_review` receipt an older
  row still carries is dropped at the boundary); the application tool
  publishes `brief`, `compiled_at` and `stale` and no longer
  describes a wipe; a flow asking for the brief is served the full when no brief
  claim was published (the frame budget still decides); the harness restores
  every account column it overwrites and deletes under the proof account's id.
- Measured on dev, HISTORICAL — the first lot, under the descriptive contract
  and the semantic review both since removed (deepseek-flash, the proof account,
  the invented persona): every record read whole (62 memories, 20 interests, 2
  habits, 3 debriefs, 5 open loops, 4 tickets, 3 routines, 3 reminders, 3 kept
  answers); 15 claims proposed, 13 approved, 2 rejected; the full portrait four to six paragraphs
  under the former 300-token clamp, every approved paragraph now; the brief one
  or two dense sentences; sources cited: journal, memories, open loops,
  workboard. Baseline on the same material: 9 proposed, 4 published, journal
  only. Total spend of the simulation: 0.265 €.
- Measured again on 2026-10-12 b, on the analytical contract (five runs,
  0.128 €): what the generation published read as analysis — e.g. the tension
  between a wish to delegate and the habit of rereading every message, the
  tempo of support against the slowness of a workshop — and the brief as a rule
  of interaction; the harness now carries three deterministic oracles
  (`restatement_ratio` on the stored canonical quotes, `enumerations`,
  `mean_source_kinds` / `multi_source_share`), restores every account column
  it overwrote, removes the entries the runs' own maintenance created, and
  refuses a second seed over a live state. One run was lost to a dev scheduler
  sweep writing on the account mid-run (`stale`), one to the maintenance
  contract (`invalid_output`). The restatement figure of that evening was read
  on the journal-backed supports alone (the oracle looked the other supports up
  by an id the stored claims never carry — review 2026-10-12 b); the
  item-agnostic reading of the same texts (every paragraph against every seeded
  item: 0.00-0.03 overlap against 0.05-0.09 for the baseline, 0 enumeration
  against 3) is what the conclusion rests on. The deterministic guards were
  then confronted, at no cost, with the seven readings those runs published,
  each against every seeded item (review 2026-10-12 c): none restates one
  (maximal overlap 0.18, far under `PORTRAIT_RESTATEMENT_OVERLAP`), none carries
  a figure, and
  none carries a name — and the same confrontation found the first name guard
  wrong by construction, since every German noun is capitalised, which is why
  the guard became structural (§ 6).
- Measured once more on 2026-10-12 c, on the GUARDED chain the review left (no
  reviewer, the deterministic guards, the per-claim parse; three runs on a fresh
  seed, 0.049 €): the first run was lost whole to ONE maintenance action — a
  higher-level synthesis without enough mature supports, `invalid_output`, the
  all-or-nothing contract below; the two others published ten readings each,
  and the guards dropped none of the twenty (no false positive), with no
  paragraph restating one item, every facet present and a brief written as its
  own claims. Two residuals, stated: the full portrait ran at 1.6 to 2 times
  its target and the brief at 0.9 to 1.6 times its own (`JOURNAL_PORTRAIT_*_MAX_TOKENS`,
  targets, never a clamp); and in six readings of ten a sentence lists three
  grounds or more — the rhythm, focus and context paragraphs open on a reading
  (« defended windows », « a phase of tidying and closing ») and then list what
  grounds it (the protected slots, the tickets, the open loops), which the
  one-item restatement guard does not see by design, while posture, tension
  and uncertainty read as analysis and the brief as a synthesis.
- Measured on 2026-10-13, after the two maintenance remedies (§ 5) and the two
  prompt levers (§ 4): six runs, 0.109 €, every one published — 10 to 12
  readings, none dropped, no paid pass lost, where one action had voided 3 runs
  of 11 before. The listed grounds receded without vanishing: sentences of three
  commas or more were 6 and 6 readings of ten before any lever, 4, 6 and 6 after
  the first, 3, 2 and 5 after the second, and the `listed_grounds` oracle (one
  sentence naming three cited items) read 0.2, 0 and 0.2, then 0.1, 0.08 and 0.
  `rhythm` names the KINDS of time defended in two runs of three and still walks
  through dated slots in the third; `focus` states a direction after three
  summarised activities. The measurement had first to stop waking the dev
  workers: at every earlier seed the workboard runner executed the persona's
  « todo » ticket — a paid agent turn on the dev slots nobody budgeted, about
  0.11 € in five seeds — and its moves made two consolidations `stale`; a
  reminder due an hour later fired, the interest sweep notified, and fifteen
  projected kept answers stayed orphaned after the teardown. The seed is now
  inert (verified: four minutes, nothing moves, nothing billed) and the teardown
  removes a kept answer through its own door.
- Left open, in writing: the
  corpus states no gender and the model alternates « il » and « elle », which
  a real account's prompt does not settle either; `portrait_is_current` runs
  one aggregate per source — nine since this ADR, over every row, where ADR-292
  ran four with the memories bounded by their page — and it ran at every ambient
  portrait read until review 2026-10-12 c measured it (14 ms fixed plus a hash
  of every row of the record, two to three reads per chat turn) and moved it to
  the journals page alone, the ambient block carrying its date instead (§ 7); a
  cached verdict keyed on the revision stays the next lever for the page if a
  measurement on a large account shows it; the deploy's `.env.encrypted` copies
  are regenerated from `.env` by `deploy-prod.ps1` at the next deployment; a
  failure while WRITING the maintenance still rolls the whole pass back (0 of
  62 production consolidations over 30 days failed at all, read-only
  2026-10-12 c — isolating each write waits for a case); and `rhythm` still walks
  through dated slots in one run of three after two prompt levers — a third
  lever is measured before it is trusted, never assumed.
