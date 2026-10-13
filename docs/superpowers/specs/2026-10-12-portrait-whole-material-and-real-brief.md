# The portrait reads the whole material, and its brief is a synthesis

- **Date**: 2026-10-12
- **Status**: design, awaiting the owner's validation of the measured simulation
- **Amends**: the portrait pipeline shipped by commit 499c4cecc (v3.0.0) without an
  ADR of its own; ADR-292 (four sources, budgets as settings); ADR-079 (the brief
  as « core essence in 2-3 dense sentences »); ADR-284 (a prompt states what the
  code enforces); ADR-269 (a dated synthesis is kept, never replaced by nothing)

## What was measured before anything was decided

Measured on production (read-only) and on dev, 2026-10-12:

| Fact | Production (owner's account) | Dev (three accounts) |
|---|---|---|
| Claims proposed → admitted → approved → published | 6 → 5 → 3 → 3 | 3→1, 6→5, 2→2 |
| Published full portrait | 736 chars, ~140 tokens of a 300-token budget | 122 / 459 / 389 chars |
| Published brief | ONE claim, 257 chars | one or two claims everywhere |
| Sources handed to the prompt | memories 38 of 81 (2 omitted as incomplete), interests 15, habits 1, debriefs 0 of 3 (3 omitted as incomplete) | — |
| Sources cited by the published claims | journal entries only | — |
| Proxy tokenizer on French | 5.4 characters per token (70 tokens ≈ 375 chars) | — |
| Consolidation | two model calls, 199 s, 0.023 € | — |

Before commit 499c4cecc the model wrote `portrait_full` (about 300 tokens, no clamp,
overshoot about a third — ADR-292) and `portrait_brief` as its own 2-3 sentence
synthesis. The commit replaced them with `portrait_claims` proven by exact passages,
reviewed by a second model call, packed WHOLE under the budgets BEFORE the review,
the brief being a subset of the full claims under 70 tokens; and every journal
change WIPES the stored words until the next consolidation (scheduler every 5 h,
cooldown 6 h).

## The owner's three directives (2026-10-12)

1. The portrait is fed from ALL the available material about the person, never a
   limited or truncated selection. There are many records: the memories, the
   journal entries, and the others LIA keeps.
2. The brief is a REAL summary: a synthesis, not the first sentence of the full.
3. Test, simulate and validate before any definitive implementation.

## Decisions

### D1 — Every record about the person is a portrait source, read WHOLE

The seam `domains/shared/portrait_sources.py` keeps its closed vocabulary, grown
from four keys to nine, in the prompt's order:

| Key | Record | What a line carries | Why it is portrait material |
|---|---|---|---|
| `memories` | long-term memories | category, emotional label, content, date | facts the person stated |
| `interests` | learned interests | topic, category, subject, weight, last mention | what occupies them |
| `habits` | learned rhythm and recurring requests | windows, recurring shape and hour | when and how they come |
| `relation_debriefs` | relationship debriefs | person, date, headline, where things stand | who matters and the stakes |
| `open_loops` | unfinished threads | subject, counterparty, direction, due hint | what they owe and are owed |
| `workboard` | tickets they own or hold | title, description, status, priority, due | what they delegate and track |
| `routines` | scheduled actions | title, instruction, recurrence or condition | what they automate, their rhythm |
| `reminders` | pending reminders | content, trigger instant, recurrence | what they do not want to forget |
| `bookmarks` | kept answers | the request, a bounded excerpt of the answer, date | what they found worth keeping |

Not a source, and why: the psyche state (it is LIA's own inner state and the
relationship as LIA feels it, numbers the prompt forbids restating); the meeting
minutes (third parties' words, written for a document, not about the person); the
peer connections (a roster of names, which the prompt forbids restating). The
conversation slice stays the person's option (`journal_consolidation_with_history`).

The per-source item caps (`JOURNAL_CONSOLIDATION_MEMORIES_MAX`, `…_INTERESTS_MAX`,
`…_DEBRIEFS_MAX`), the per-item clamp (`…_SOURCE_ITEM_MAX_CHARS`, 200 characters,
which made every clamped item INELIGIBLE as a proof — the owner's three debriefs
were all omitted that way) and the global character cap
(`…_SOURCES_MAX_CHARS`, 12 000) are deleted. ONE bound replaces them, physical and
stated: the sources may take `JOURNAL_CONSOLIDATION_SOURCES_WINDOW_FRACTION`
(default 0.5) of the consolidation slot's effective context window (ADR-278's door,
`get_effective_context_window_for_slot`). Items are rendered whole (a single item is
bounded by `PORTRAIT_SUPPORT_QUOTE_MAX_CHARS`, 5 000, already the proof bound);
sections keep the declared order; when the material physically exceeds the share,
the LAST sections lose items from their END, at item boundaries, and the provenance
states `used` of `total` with `reason: over_budget` (ADR-286's rule: a cut is
stated, never silent). On the measured deployments (a 1 000 000-token window) the
share is never reached.

Each reader keeps the contract of ADR-292: three gates read at call time, a
status (`used | empty | disabled | unavailable`), an exact total, never raises; a
`FreshnessProbe` so a change in the record reopens the consolidation and the gate.
The memories' `selection_query` goes: with no cap, the selection is the whole set,
which the row identity already covers.

### D2 — The brief is written as its own claims

`PortraitClaim.in_brief: bool` becomes `placement: Literal["full", "brief"]`
(default `full`). The prompt asks for the brief as 2-3 SHORT sentences, each a
claim of its own with `placement: "brief"` and its own supports (it may cite the
items the full claims cite — it condenses them), the whole brief fitting
`{portrait_brief_tokens}`. The full claims are paragraphs. `grounded_portraits`
packs the full from the `full` claims and the brief from the `brief` claims; the
brief is no longer a subset of the full, so the prompt's promise (« a synthesis, not
a chopped full text ») is what the code produces (ADR-284). The review judges a
brief claim like any other (its conditions must survive alone).

### D3 — Review first, pack after; the budget bounds the publication

`prepare_portrait_review` admits EVERY structurally valid claim (proofs resolved,
no budget), bounded only by the review input ceiling it already enforces.
`reviewed_portrait` keeps the approved subset, and only THEN `grounded_portraits`
packs it under the budgets, in the model's order (the prompt asks for importance
order). The receipt binds the reviewed candidate and the approved subset exactly as
today. The prompt asks for every supported facet the material carries (eight to
twelve claims when the material allows), tells the model a verifier may drop some
and that the publication keeps, in order, those that fit.

The full budget default stays `JOURNAL_PORTRAIT_FULL_MAX_TOKENS` = 300 until the
simulation measures whether the approved material is cut by it; the simulation
reports the approved set's size against 300 and 400, and the owner decides.

### D4 — A journal change marks the portrait STALE, it never wipes it

`mark_journal_changed(invalidate_portrait=True)` stops clearing the four columns.
A portrait whose evidence moved is SERVED with its date and a `stale: true` flag:
`read_managed_portrait` returns it (the card draws « Compiled {when} — a
recompilation is pending »), the ambient block injects it with its compiled date
and the sentence that it may be dated. ADR-269's doctrine: replacing a usable
synthesis with an empty panel turns « I could not refresh this » into « there is
nothing ». The gate `portrait_is_current` keeps its one meaning — it decides
`stale`, never visibility — and `consolidation_needed` is unchanged.

The frontend's `invalidatePortrait()` (which blanked the card before every refetch)
goes: the refetch decides. `NEXT_PUBLIC_JOURNAL_CONSOLIDATION_TIMEOUT_MS` rises
from 240 000 to 330 000 (the server bound is 300 s and the consolidation now makes
two model calls with reasoning: 199 s measured).

### D5 — The policy version moves, every stored portrait is recompiled once

`JOURNAL_PORTRAIT_POLICY_VERSION` → `grounded_narrative_v4`: `source_state` carries
it, so every stored portrait reads `stale` and the scheduler recompiles each
account once at its next eligible tick.

### D7 — A claim is repaired or dropped, never fatal to the batch; the review judges grounded synthesis

Measured on the first candidate run (2026-10-12): three consolidations of three were refused
`invalid_output` for ONE claim filed under another facet than `uncertainty` while citing a
provisional rule — three paid generations for nothing. The facet is metadata: it is REPAIRED to
`uncertainty` (ADR-184) and the review's `uncertainty_preserved` judges the words. A claim whose
reference the snapshot cannot resolve (unknown or ambiguous id, a passage that is not the
whole current rule, a duplicate, an entry this batch changes) is DROPPED and counted
(`journal_portrait_claims_dropped`, codes only), never fatal: the review cannot judge it, and the
maintenance actions keep their own all-or-nothing contract.

Measured on the second candidate run: with the review written for strict ENTAILMENT, 14 claims
proposed per run, 7 to 12 rejected on `supported` and `scope_preserved`, the brief dead in two
runs of three. A portrait IS a synthesis, which entailment refuses by construction. The review
now judges GROUNDED synthesis: an assertion is supported when a linked passage states it or when
several linked passages read together show it; it fails when it contradicts a passage or when no
passage and no group of passages shows it; the guards against invention from one fact stay
(a job title alone, one example, sentiment labels and weights); `scope_preserved` keeps the
conditions and the domain the linked passages carry and accepts a class whose cases are each
shown by a linked passage. Measured: 2 rejected of 15 per run, the brief a real synthesis.

### D6 — Measured before it is trusted

`task journals:portrait:measure` (`apps/api/scripts/journals/measure_portrait.py`,
the `react:selection:measure` shape) seeds a SYNTHETIC persona (`portrait_corpus.json`
beside the script: French, invented, nothing of anyone's) into the proof account on
dev, runs the real `consolidate_journals_for_user(manual=True)` N times, reads what
the run wrote (claims proposed, admitted, approved, published; characters and proxy
tokens of full and brief; sources cited; review rejections; cost and duration from
the run's own token rows) and removes everything it seeded. The baseline is
measured on the code BEFORE the change, the candidate after, on the same corpus
and the same slot (`deepseek-flash` on dev, never Anthropic). Budget announced:
at most 0.50 € for the whole simulation.

## What the owner validates before the definitive implementation

The measured report: the proof account's two portraits (full and brief) under
the candidate, the counts above, the cost per run, and the full-budget question
(D3). Then the definitive surfaces: the ADR, the living maps in six languages,
JOURNALS.md, the settings examples, the six locales, the adversarial review.
