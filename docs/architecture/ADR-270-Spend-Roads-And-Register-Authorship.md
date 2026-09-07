# ADR-270 — Spend roads, cost bearers, and the authorship of a register row

**Status:** Accepted — 2026-09-07
**Amends:** ADR-263 (execution authority chain and effect register), ADR-248 (one
predicate, never two copies), ADR-085 (a registry gets a completeness assert)

---

## Context

Two questions were asked of the codebase, and neither had an answer that could
be read anywhere:

1. **Is every euro LIA spends counted, and counted against the right person?**
2. **Does the register say what LIA did when nobody asked it to?**

Answering them by reading files produced **nine wrong conclusions in a single
session**, in both directions. The reason is structural rather than accidental:
accounting in this codebase is **ambient**. A node inside a turn spends through
a `TrackingContext` an ancestor published, so the node's own file mentions no
tracker at all. Grepping for the tracker therefore yields false positives (a
tracked module that names nothing) and false negatives (an untracked module
that names a helper it never reaches).

Production was the only reliable oracle. Joining `token_usage_logs` to the
registers by `run_id` on 2026-09-07 drew a clean line:

| | |
|---|---|
| Conversational surfaces recorded | **24/24, 22/22, 10/10, 8/8, 7/7, 6/6** |
| Out-of-turn runs recorded | **0 of 228** over fourteen days |
| Personality translations recorded anywhere | **0 of 84** (2025-12-11 → 2026-02-05) |
| Instance daily spend, measured | 0,42 €/day, worst day 2,82 € |
| Self-diagnosis allowance no ceiling could see | **1,00 USD/day** |

The 84 translations are the sharpest case: they ran while the ledger was
demonstrably working, recording 5 976 rows across 17 other surfaces over the
same window. Nothing was broken. Nothing had ever been told where that spend
should go.

## Decision

### 1. A spend site declares its road

`infrastructure/llm/spend_roads.py` names every module that calls `get_llm` and
the ledger its euros reach: `TURN` (ambient tracker), `ACCOUNTED` (its own
accounting, out of turn), `CALLER` (a named accountant, which must itself reach
a door), `INSTANCE` (no owner; the deployment's daily ledger only).

The guard refuses an omission, a stale entry, an `instance` road without a
written reason, a `caller` road without a named accountant, and — read by AST,
never by substring — a road whose module does not actually call what it claims.
It caught **six of the author's own forty-six classifications**, a 13 % error
rate consistent with the rest of the session.

### 2. A euro nobody owns still reaches a ledger

`domains/usage_limits/instance_spend.py` records account-less spend to
`InstanceDailyBudget` and to nothing else, and asks that ceiling for permission
first. `token_usage_logs.user_id` is `NOT NULL`, so this had to be a separate
path rather than an extension of the existing one. Wired to self-diagnosis,
personality translation, skill-description translation, broadcast translation
and the evaluation harness.

**Amended 2026-09-07 (consolidation pass).** That sentence overstated the code,
and the guard beside it could not tell: it checked that an instance module
RECORDS, never that it ASKS. Four of the five called
`is_instance_spend_blocked`; the evaluation harness did not, so it would have
spent past an exhausted ceiling and dutifully written down that it did.
`INSTANCE_GATE_EXEMPT` now holds the one argued exception — an evaluator must
produce a measurement or fail, and a fabricated score an operator reads as real
is worse than the spend it saves — and a guard refuses a silent one. Verified
by removing the exemption: it reds on exactly the expected module.

### 3. Who pays is declared, and the quota's arithmetic must match it

`domains/usage_limits/cost_bearers.py` states, for each billable family, whose
credential the provider bills and why. The guard reads the enforced sum out of
`_build_user_stats_columns` by AST and checks **both directions**: no
instance-paid family escapes the ceiling, and no user-paid family is charged to
an account that already paid its own provider. Verified before declaring:
`provider_api_keys` has no `user_id`, and `get_api_key_credentials` is
per-account.

### 4. The register gains a fourth authorship — and it is narrow

`EffectSource.PROACTIVE` was excluded originally on the argument that *"the
heartbeat runs no tool"*. That is true of the EFFECT register and false of the
two that came after it: a briefing runs no tool either, yet it reads a person's
mail every morning at their expense. The enum was never reopened when the
consultation and decision registers arrived.

**The authorship is declared by each call site, never defaulted.**
`track_proactive_tokens` is named for the plumbing, not for the initiative, and
conflating the two was a defect caught before shipping: **nothing schedules the
briefing** — it is reached only from `GET /briefing/*` and from chat suggestions
— so filing every caller as `proactive` would have credited LIA with page loads
it never chose to make. A reminder is the person's own deferred instruction:
`scheduled`. Only a runner sweep is `proactive`.

The derivation itself was **four copies** of `"scheduled" if automated else
"user"`; it is now one predicate (`effects/source.py`), extracted before the
third value was added rather than after.

### 5. Every surface that opens the person's sources says so — and that is a REGISTRY, not a list of fixes

`record_treatment` is called from exactly one place — the tool gate — so a
capability that is not a tool records nothing. The briefing has nine direct
fetchers. Its consultations were absent **by construction**.

`_section` is the single chokepoint, and it already distinguishes the three
cases that matter: **a cache hit is not a consultation** (Redis answered, the
mailbox was never opened), **a hidden section is not one either** (the person
switched it off), and a live fetch is a real read. Only the third is recorded,
which is also what keeps the register readable on a page reached at every home
load.

Two more surfaces were found the same way, each by a person noticing an
absence rather than by a test — which is why the third instalment is an
instrument rather than a third fix:

- **the relationship debrief** (seven sources). Reported from production: a
  debrief was generated and its author could not find it. What they found at
  the top of the list was a briefing card read from seconds later, and they
  reasonably concluded it had been filed under the wrong name. It had been
  filed under **no** name. The recording lives in the debrief's own path and
  not in `build_overview_evidence`, which the 360° tool shares — that tool
  already gets its row from the gate, and recording there would double it.
- **the heartbeat sweep** (sixteen sources), **824 runs over thirty days, not
  one row**. The case where the gap matters most: a conversation can be
  re-read; a sweep that opened someone's mail at four in the morning leaves
  them nothing to consult. Recorded at the aggregator's single chokepoint,
  with the collector published by the proactive runner — one insertion covering
  every task it drives.

`domains/agents/effects/user_data_readers.py` then closes the class:
**every** out-of-turn surface declares either the module that records its
consultations, or a written reason it opens nothing. The guard walks a
COMPLETE, enumerable list — the `task_type` of every funnel call site plus the
`task_type` every `ProactiveTask` declares — so a fourteenth surface cannot be
added without answering the question.

**The register is offered, never fetched.** `agents` imports `relations`
(ADR-269), so a domain reaching back into `agents/effects` closes a cycle — and
the coupling ratchet counts LOCAL imports too, so hiding it inside a function
would only make the edge harder to see. The dependency is inverted
(`domains/shared/consultation_sink`): the register installs a sink and a
collector factory at import, and any domain records through the seam. Its
contract is NAMED rather than `**Any`, because a seam that accepted anything
would let a caller misspell a field and write a row with a missing column —
exactly the silence this registry exists to end.

### 6. One guard, two doors

`invoke_with_instrumentation` carried the usage check; `get_structured_output_with_retry`
did not even accept a `user_id`. The debrief, the telephony synthesis and the
self-diagnosis all spend through the second door. `infrastructure/llm/usage_guard.py`
holds the one implementation, `LLM_CHOKEPOINTS` names every door, and a
structural test refuses a third door that does not call it.

Two refusals the guard must **not** make: a call with no owner is never blocked
(its bound is the instance ledger), and `"system"` is not an account.

### 7. A fourth tab, which is a reading and not a register

ADR-263 forbids merging the two registers because an action and a consultation
are different objects. An initiative is neither: it is an **origin**, and it
holds both kinds. So the interface stacks the two registers filtered to
`initiative`, and the two first tabs read `mine` — everything the person set in
motion, **including the routines they wrote** — so no existing row moves out of
the list where its owner has always found it.

`mine` is defined by **exclusion**, so a fifth authorship added tomorrow lands
in the person's own list: visible and possibly misfiled, never invisible.

### 8. Amendment (2026-09-07): three fixes are not a method

Sections 5 to 7 were written surface by surface, as each absence was noticed,
and that is how they came to disagree. Measured one day later — the same
instrument, turned on its own author's work:

| | |
|---|---|
| Copies of the 31 capability names | **3** (one per surface, plus a hand-typed one in the register) |
| Tables written to bridge that gap, read by nobody | **2** (`HEARTBEAT_DOMAIN_OVERRIDES`, `DEBRIEF_DOMAIN_OVERRIDES`) |
| Direct-read capabilities checked by the boot guard | **0 of 31** |
| Surfaces guarding their capabilities against orphans | **1 of 3** |
| Surfaces wrapping their recording loop | **1 of 3** |
| Authorship literals typed at a call site, validated by nothing | **3** |
| Extracted modules shipped with no test at all | **2** |

`domains/shared/consultation_surfaces.py` is the answer, and it is a
DECLARATION rather than a fourth fix: a surface names its key, its prefix, its
authorship and its section-to-domain table, and every reader takes it from
there — each surface for its own names, `TREATMENT_DOMAIN_OVERRIDES` by
MERGING it rather than transcribing it, `assert_treatment_domain_completeness`
for the boot check, `record_surface_consultations` for the writing, and one
test file for all of them.

Four properties follow that no per-surface fix gave:

- **The authorship is a property of the surface, not a literal.** Nobody
  schedules a briefing; nobody asks for a sweep. Typed at a call site,
  `"proactve"` would have written rows the origin filter drops in silence.
- **The seam has ONE caller.** A surface recording by hand escapes the
  declaration, so its capability is checked by no boot guard, its domain by no
  wording test, and its authorship by nothing at all. A guard refuses any other
  caller of the seam.
- **The boot check is STRICTER for a declared capability than for a tool.**
  `UNKNOWN_DOMAIN` is itself a translatable key, so it passes the tool rule —
  deliberately: a third-party name we cannot read must show « Unknown » rather
  than a technical string. We WROTE the thirty-one, so `unknown` there is a
  declaration error. Without that distinction the extension would have
  protected nothing, which is how it was written first.
- **Two tests that became true BY CONSTRUCTION were replaced, not kept.** Once
  the register merges the declaration, « the two tables agree » cannot fail. A
  green-by-absence oracle reads as protection and is none. What replaced them is
  falsifiable: a collision between the tool half and the surface half, and a
  prefix `treatment_domain` answers before it ever reads the table.

A cold adversarial review of that consolidation then caught the trap it had
walked into. The action register carried its OWN `toneFor` — a per-screen tone
map, the exact thing `lib/status-tone.ts` exists to end — where « Effectuée »
rendered in the theme colour instead of as a success and « En cours » in grey
instead of as in-flight. The first factorisation gave the two registers ONE
tone function and thereby centralised the WRONG answer. Both now read
`lifecycleTone`, and the register's own three words joined the shared table:
`claimed` is in-flight, `refused` is NEUTRAL on the habits precedent (a refusal
is a decision, not an incident), and `abandoned` is a warning — the record is
incomplete, which is not the same fact as a call that ran and failed. **A
factorisation is only worth what the implementation it keeps is worth**: before
merging N copies, check whether one of them was already the codebase's answer.

The same review found the display homogeneity still incomplete: an action
always stated its status, a successful consultation stated none — and since the
row's glyph is `aria-hidden`, a successful read had no accessible statement of
outcome at all.

The same pass closed what the coverage numbers had been showing all along. The
two modules extracted to satisfy the size ratchet
(`heartbeat/second_pass_query.py`, `user_mcp/description_generation.py`) had
**no test whatsoever** — an extraction moves code from a covered module to an
uncovered one while changing nothing — and the proactive runner's SUCCESS path,
where the accounting, the decision row and the consultation collector all live,
was exercised by no test at all: every existing one stopped at a skip or a
failure.

## Consequences

- **A defect the audit closed on the way**: reminder notifications wrote only
  the per-run aggregate — no `token_usage_logs` row, no `user_statistics`
  increment, no instance ledger entry. They consulted the quota before spending
  and never fed it.
- **Eight copies of one arithmetic became one.** Reading `usage_metadata` was
  written eight times, and the copies disagreed: only one read Anthropic's
  `cache_read_input_tokens`, and only that one clamped the subtraction at zero.
  The other seven billed cached prompts at full price on every Anthropic model
  and could compute a negative token count. `infrastructure/llm/usage_metadata.py`
  is now the single implementation, and `model_name_of` replaced seven readings
  of the model name with three different fallbacks.
- **No migration.** `Enum(native_enum=False)` leaves `create_constraint` at its
  SQLAlchemy 2.x default of `False`: measured in production, the three register
  tables carry **no check constraint at all**, and the columns store enum
  VALUES. The test that pins the vocabulary is the only thing standing between
  the enum and the data — and its docstring, which claimed a check constraint
  existed, was corrected.
- **What this does not fix**: no numeric ceiling is configured on this
  deployment — 165 limit rows, none with a cost or token bound, and no instance
  budget. The accounting is now complete and the ceiling can see everything;
  arming it is a decision for the operator.
