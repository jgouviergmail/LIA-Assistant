# ADR-263 — Execution authority chain and effect register

**Date**: 2026-09-04
**Status**: Accepted
**Context**: LIA could already decide well and act well. What it could not do
was let anyone check, afterwards, *what it actually did* — without taking the
executor's word for it. Three measurements made that concrete on 2026-09-03:
thirteen native tools that modify, delete or communicate ran with **no
confirmation gate in either execution mode**, and nothing said whether that was
a decision or an omission; a confirmed draft could be **executed twice** (the
response node executed at one point and cleaned up at another, and the router
never purged the key); and the sub-agent, documented read-only, was enforced by
a **hand-written list of 17 names** that four mutating tools were not on. Each
of those is a different symptom of the same absence: nothing in the system
stated *what a capability owes the user before it acts*, and nothing recorded
*what it then did*.

## Decision

### 1. A capability DECLARES what it owes the user

`mutation_policy` on every native tool manifest, six values:
`read | draft | confirm | reversible | artefact | sandboxed`. The last three
carry a written reason. `assert_mutation_policy_completeness` refuses the boot
on an omission (ADR-085 idiom).

Two rules, both paid for by a measurement:

- **Only the `search` category is exempt** from declaring. `readonly` is the
  *fallback* of `infer_tool_category`, and that is where the dangerous tools
  sit — `claude_server_task_tool`, `run_python_tool`,
  `delegate_to_sub_agent_tool` are all declared read-only deliberately. Exempting
  "read-only" would have exempted exactly them.
- **`permissions.hitl_required` answers a different question.** It says whether
  ReAct pauses, which a tool may earn for its COST rather than its EFFECT
  (`delegate_to_sub_agent_tool` opens a read-only research loop and changes
  nothing). Deriving the policy from that flag would have made it unusable.

A third-party MCP tool never declares: its policy is **derived** from the
server's own annotations and is never looser than they are.

### 2. An effect is CLAIMED before it happens and CLOSED from its result

`agent_effects`: one row per effect, `(thread_id, idempotency_key)` unique. The
claim commits in **its own transaction** — an email is not transactional, and a
claim rolled back after the mail left is the dual-write hole this exists to
close. A terminal status is written only from an **explicit** result; absence of
an exception is not proof of delivery. The tool result is kept **encrypted** so
a resume can be served instead of re-executed, and the label is stored as
`{i18n_key, values}` so the register reads in the reader's language rather than
the writer's.

### 3. The gate is installed on the CAPABILITY, not asked of its callers

`gated()` wraps the coroutine at REGISTRATION; `gated_executor()` wraps each
draft executor. A gate a caller must remember to invoke is a gate that will be
forgotten: three call sites reach a tool today through two different APIs.
`assert_effect_gate_completeness` checks the property at boot, and earned its
keep the day it was written by finding a second registration path through which
114 of 122 tools entered the registry ungated.

The MCP adapters gate **themselves**, inside `_arun`: their `coroutine` is a
read-only property (assigning to it broke every registration), and they are
reached through three doors — `.coroutine(...)`, `ainvoke` → `_arun`, and
`_MCPReActWrapper._inner._arun(...)`. A gate on one door is not a gate.

### 4. An unconfirmed effect ASKS instead of failing

The pipeline confirms nothing before execution, so a `confirm` tool refused
there would be a capability lost, not safety gained. The gate hands the call
back as a **draft** (`DraftType.TOOL_CALL`) — the one shape both execution
modes already confirm — so the card, the queueing, the batch handling and the
resume all come for free. An **unattended** run (a scheduled action) is refused
instead: a draft nobody can confirm is a promise nobody keeps.

### 5. What the register does NOT cover

The register records what a **capability** did in a turn: a tool call, or a
confirmed draft executing. It is not a log of every database write. Measured
2026-09-04, the only writes to the outside world outside that scope are the
push relay and the security e-mails of `auth` — infrastructure, not actions
taken on the user's behalf. Saying so here is part of the contract: a register
that over-promises is worse than one with stated limits.

### 6. The proof is READ, never inferred

Everything downstream reads the register rather than reconstructing it: the
"Actions performed" block under a bubble, the debug panel section, the user's
action journal, the account export, the admin surfaces. One reader
(`readable_label`) shapes a row for all of them, so they cannot describe the
same effect differently. Nothing writes: correcting a row is a reviewed
database operation, because an executor able to edit its own record defeats the
point of keeping one.

### 7. Two registers, two audiences

- **Readable** — the user's own record. Leaves with the account export,
  rendered in the reader's language, and dies with the account (CASCADE).
  Across accounts an administrator sees it **masked**; every unmasking writes
  an `AdminAuditLog` entry.
- **Technical** — pseudonymised BY CONSTRUCTION for analysis: an explicit
  column ALLOWLIST (a column added tomorrow is absent until someone decides
  otherwise), identifiers replaced by HMAC handles keyed by the instance
  secret, and the two content columns never exported at all. A guard fails the
  build if any model column is neither exported nor explicitly forbidden.

### 8. Two registers, because they count different things (lot 4)

The register above answers *what did the assistant DO*. The question a person
actually asks first is *what did it LOOK AT* — and the gate already saw every
one of those calls, since a read is exactly what it lets pass through.

Owner arbitration, 2026-09-04: **two distinct lists, never one list with a
filter**. `agent_effects` takes one row per ACTION, `agent_treatments` one row
per CONSULTATION; a busy turn consults dozens of capabilities and acts on none,
so merging them would drown the four lines that matter under four hundred that
do not, and would let a reader add two totals that count different things.

Four properties make the second register affordable and honest:

- **Observing stays free.** An action is CLAIMED before it happens, in its own
  committed transaction, because an effect not recorded beforehand can never be
  proven afterwards. A consultation is merely OBSERVED: the turn's parent
  publishes a **live list**, the gate appends to it, and ONE batch is written at
  the end. The measured property that makes the gate acceptable on the hot path
  — 0.64 µs and zero database session on a read — survives intact.
- **The collector is a LIST, not a `ContextVar.set()`.** A `set` made inside a
  child task does not propagate to its parent, so a collector built that way
  would work in ReAct (sequential awaits) and silently lose the pipeline
  (`asyncio.gather`) — a register that lies by omission, on one execution mode
  only. Proven on a real compiled `StateGraph`, with a fan-out node and a
  sequential node, plus a failing turn and a cancelled one.
- **A turn that stops mid-flight closes its books.** The recorder is an
  `async with` beside the token tracker, so `__aexit__` runs on the normal path,
  on an exception and on a cancellation. The flush is shielded, for a narrower
  reason than the obvious one: measured, a SINGLE cancellation still writes;
  a cancellation **re-delivered during cleanup** (a container stopping — the
  ordinary case on a Raspberry Pi) loses the write without a shield.
- **A consultation records the capability, never the call.** No label, no
  arguments, no result — « searched Marie's emails » would reveal a search
  nobody asked to have recorded, where « sent an email to Marie » records an act
  the user requested. Which is also why an administrator's readable extraction
  masks the ACTION register and does not mask this one: there is nothing to
  mask, and pretending otherwise would cost an operator information for no
  privacy gained.

**The wording is the DOMAIN, not the tool.** Measured before deciding: the ⚙
trace's `execution.steps` covers 81 of the 119 registered tools, in a progress
style (« Activating Hue scene... »), leaving 38 showing a raw technical name and
costing six new strings for every tool ever added. `DOMAIN_REGISTRY` is already
the single source of truth for the vocabulary — 31 nouns cover everything,
forever, and the tool name is shown beside them, so the technical half is
present without being the half a person reads first. A boot guard
(`assert_treatment_domain_completeness`) refuses to start on a capability no
reader could name.

**Retention is measured, not guessed.** Owner arbitration: keep everything, delete
it with the account (CASCADE, as for the actions), and build a purge only if a
measurement asks for one. So no purge job ships; the growth is instrumented
instead — `lia_ledger_rows` (an ESTIMATE from `pg_class.reltuples`, because a
`COUNT(*)` every sync would scan the largest table in the schema) and
`lia_ledger_bytes` (`pg_total_relation_size`, indexes included), two panels, one
threshold alert per table and a runbook that says explicitly that the purge is
not built and how to decide to build it. Roughly 250 bytes a row: ~9 MB a year
at a hundred calls a day, ~45 MB at five hundred.

### 9. Four extractions, one engine (lot 4)

The registers exist to be taken out of the application, so the four extractions
the programme owes are served by ONE renderer per format, driven by a
`RegisterSpec` — two implementations would drift, and a register whose exports
disagree with each other is evidence of nothing.

| Who | What | Where |
|---|---|---|
| a user | their own register, readable | `GET /effects/export?register=…&format=markdown\|csv` |
| a user | both registers, in the account archive | `account_export` (one markdown file each) |
| an administrator | one, several or ALL accounts over a period, readable | `GET /admin/effects/export/readable` (masked; unmasking is audited) |
| an administrator | the same scope, technical | `GET /admin/effects/export` (JSON Lines, pseudonymised) |

Three properties the documents must have, each one a way an export could have
been quietly wrong: the **reader's clock** (an action stamped 23:40 UTC happened
the next day in Auckland, so day headers are cut in the reader's own display
timezone), the **reader's language** (resolved at export time from the stored
key), and a **published cap** (`X-Register-Truncated`, so a register cut at the
ceiling says so instead of looking complete). A CSV cell that would be read as a
formula is neutralised with a leading apostrophe rather than dropped: an export
carries what was recorded, not a cleaned-up version of it.

### 10. What using it found (lot 4, second pass)

The register went into the owner's hands and answered a question nobody had
asked it: *"I asked for my three latest emails and it shows five email
consultations."* It was right — measured on the dev instance, one ReAct turn
made five model calls, each followed by one `get_emails_tool` call, over eight
seconds, with five different durations. **That is the register working**: a
loop's real cost had been invisible until something recorded it.

Five defects came out of that first contact, and each is a rule rather than a
patch:

- **A gauge that contradicts itself is a false statement.** `lia_ledger_rows`
  read 0 while `lia_ledger_bytes` read 73 728, because `pg_class.reltuples` is
  `-1` until the first `ANALYZE`. An estimate is acceptable; an estimate that
  reads ZERO on a table holding rows is not an approximation. A non-positive
  estimate is now replaced by an exact `COUNT(*)` — self-balancing, since a
  table large enough for the scan to cost anything has long since been
  analysed.
- **The register had no counter at all.** Dashboard 28 could say what the two
  tables cost on disk and nothing about what the assistant looks at.
  `lia_treatments_total{domain, outcome, execution_mode}` is counted from what
  was **persisted**, never from what was collected — a failed flush leaves it
  untouched and raises `lia_effect_ledger_failures_total{operation=
  "treatments_flush"}` instead. Four panels, including consultations by
  execution mode, which is where the "five for three" question is answered.
- **The technical export served one register out of two.** It is now
  spec-driven: one renderer, two column contracts, and the PII guard applied to
  BOTH — a guard covering only the original would have left the newcomer's
  columns unclassified.
- **The technical export's header named the accounts in clear.** A file whose
  whole promise is "pseudonymised by construction" listed, on its first line,
  exactly the accounts it covered. Identifiers among the stated filters are now
  pseudonymised with the same key as the rows. The same header also described
  the ACTION columns whatever the file held; it describes its own register now.
- **A filter a register cannot honour is REPORTED, never dropped.** The
  consultation register has no status, policy or approval; a request naming one
  comes back in `filters.ignored_filters`, so an unfiltered file never reads as
  a filtered one.

Two UI decisions came from the same contact. Consecutive identical
consultations FOLD into one line carrying `×N` and the summed duration — five
identical rows is a log, one row saying five is a register — and the fold never
crosses a day, an outcome or a capability, so nothing hides inside it while the
exact server-side total above the list stays untouched. And both journals cut
their rows into **day sections** with real headings, so the outline is
navigable rather than an undifferentiated run.

Finally, the administrator's extraction — readable and technical, one account,
several or all, over a period — got the screen it never had
(`AdminRegistersSection`). It existed as an API from the first day and nothing
in the interface reached it, which is the same as absent for everyone but a
curl user.

### 11. Two neighbours the register's scrutiny uncovered

Neither belongs to the ledger; both were found while answering "did lot 4
regress the calendar?" — verified factually: it did not (`git status` clean on
those files, last change v1.31.1, and this lot's only calendar edits are
additive `mutation_policy` declarations). Recorded here because they were fixed
in the same pass.

**`find_availability_tool` read the wrong calendar.** Both its paths asked for
`primary` unconditionally — the freeBusy fast path by omitting `calendar_ids`,
the projection fallback by passing `calendar_id="primary"` literally. A user
whose agenda lives in a named calendar was therefore reported FREE while
booked: the 2026-07-30 defect `owner_defaults.py` documents, closed there for a
PEER's calendar and never wired for the account's own. It now resolves the
owner's default, degrading to `primary` — deliberately unlike the WRITE paths,
because creating an event in the wrong calendar is a mistake in the world while
reading availability from `primary` is a fallback the resolver already states.

Every other calendar reader already resolved it (`get_events_tool`,
`search_events_tool`, `get_event_details_tool`, the briefing fetcher), and the
whole TASKS family does too (`_resolve_default_task_list` on every tool that
touches a list). This was the last reader that did not.

**Four `*DirectTool` classes were dead, and passively dangerous.**
`CreateEventDirectTool`, `CreateTaskDirectTool`, `UpdateTaskDirectTool` and
`DeleteTaskDirectTool` (206 lines) each called their client WITHOUT a calendar
or task-list id — so anyone wiring one back would have reintroduced the very
defect above. Their comments claimed "for HITL callback" and "for draft
execution", which the code contradicts: those callbacks are `execute_*_draft`,
which resolve the owner's default and never touched these classes.

Deleted after five independent proofs, not after reading the code twice:

| Proof | Result |
|---|---|
| instantiations in the whole source (`ClassName()`) | 0 |
| references outside their own definition and `__all__`, repo-wide | 0 |
| test references | 0 |
| what the registry collector registers | `isinstance(attr, BaseTool)` — INSTANCES, never classes |
| tools registered by the running instance, before and after | **128 → 128** |

The last row is the one that settles it: removing them changed nothing at
runtime, which is what "dead" means. Ruff then found two imports only they
used, and the size ratchet lowered two caps (1202→1152, 1045→941 SLOC) — a
deletion that shrinks a frozen file is exactly what the ratchet is for.

### 12. A register nobody can verify is a register you must believe (lot 5)

The two registers are complete and readable. Neither property survives the
question a regulator, an auditor or a suspicious user eventually asks: *how do I
know these rows were not edited afterwards?* Until lot 5, the honest answer was
"you don't" — the application could rewrite any row, and nothing would say so.

**Each account gets its own hash chain.** `ledger_chain` holds one row per
notarised stage: the digest of an explicit column allowlist, bound to the
previous entry's hash. Altering a register row breaks its entry's digest;
altering the entry breaks every entry after it; deleting either leaves a gap the
sequence exposes.

Four decisions, each paid for by a measurement rather than a preference.

**Per ACCOUNT, not per instance.** This is the decision the whole design turns
on. A global chain and the right to erasure are incompatible: deleting an
account would punch a permanent, unfixable hole in a chain everyone else's proof
depends on. Per account, deleting an account removes a COMPLETE chain (FK
`ON DELETE CASCADE`) and leaves nobody else's proof weaker. Inalterability and
erasure stop being a trade-off.

**Asynchronous, and the window is published.** Sealing inside the write path
costs 6,0 ms per row against 0,21 ms for the write itself — ×28 on the user's
critical path, for a property nobody reads in that moment. A background notary
pays the same cost out of band. The price is a window: a row created at T is
sealed at T+δ, and a rewrite inside δ leaves no trace. That is stated rather
than hidden — δ is a setting, it is measured
(`lia_ledger_chain_lag_seconds`), it is alerted (`LedgerNotaryStalled`), and
every surface names how many rows are not sealed yet instead of letting
"verified" imply "all of it".

**Two stages for an action, one for a consultation.** A ledger row is MUTATED:
`claim` inserts it and `close` updates it. One digest taken at claim time would
turn every legitimate close into a tampering alarm. `EFFECT_CLAIMED` covers only
columns that never change; `EFFECT_SETTLED` covers the outcome. A consultation
is written once, so one stage covers all of it. An integration test pins that a
normal lifecycle verifies clean — without it, the whole mechanism would be a
false-positive generator, and an audit device whose alarms are routinely
dismissed is worse than none.

**Found by the pending set, not by a join.** Measured on 50 000 rows: joining
against the chain costs 9,93 ms per tick and grows with the register;
`WHERE notarised_at IS NULL` on a partial index costs 0,64 ms and grows with the
PENDING set alone. And unlike a timestamp watermark, a NULL marker has no
late-commit blind spot — simulated: a row whose transaction committed after the
notary passed was picked up on the next tick, with nothing left behind. A false
negative is exactly the failure an audit device must not have.

**What it does NOT prove, said plainly.** The chain proves that rows have not
changed since they were sealed. It does not prove they were TRUE when written —
nothing can — and it does not cover the window. An operator with database
credentials who rewrites a row *and* its entry *and* every entry after it
produces a chain that verifies; the defence against that is the head fingerprint
the user is shown and invited to note down, which no rewrite can reproduce.
Saying this in the ADR rather than only in the code is the point: a proof
oversold is a proof that fails in front of the person it was built for.

**Nothing repairs a chain.** There is deliberately no endpoint, task or script
that re-notarises a broken chain — such a tool would serve an attacker exactly
as well as an operator. A break stays visible to every later walk, and the
notary keeps sealing new activity rather than refusing to protect what comes
next.

### 13. The turn itself, pointed at rather than copied (lot 6)

Both registers file their rows under a ``run_id``, and until lot 6 that
identifier pointed at nothing. `agent_decisions` is what it means: one row per
TURN — who asked, through which route, in which mode, ending how, with a
pointer to the message that asked and the message that answered.

**It points; it never copies.** ``conversation_messages`` is already the user's
own data, purged with the account. Copying a request into the register would be
a second copy of the very words the register exists to make accountable, and a
second place to leak them. Both references are ``ON DELETE SET NULL``, so
deleting a conversation leaves a dated TOMBSTONE — the turn happened, its text
is gone — never a resurrection and never a cascade that would erase the fact
along with the words (the ADR-201 doctrine, applied again).

**A HITL resumption is the SAME turn.** ``run_id`` is reused across an
interrupt, so the write is an upsert that MERGES: the earliest start, the latest
end, an ACCUMULATED duration — twenty minutes of a human deciding is not twenty
minutes of a turn running — and a ``segments`` counter. Overwriting in silence
would make an interrupted turn indistinguishable from a straight one, which is
precisely the fact an audit wants. The arithmetic is server-side
(``GREATEST``/``LEAST``/``+``), never SELECT-then-write: a lost update here
would silently understate a turn.

**The verdict is DERIVED, never asked for.** The outcome starts at
``interrupted`` and only an explicit success writes ``answered``; the context
manager reads the exception to decide between ``failed`` and ``interrupted``,
and an explicit success is never downgraded by a stream that broke during
teardown after the answer was delivered. Asking callers to declare it is how
that property rots — there is always one more exit path someone forgets.

**Three registers, and they still never add up.** One row per ACTION, one per
CONSULTATION, one per TURN. The decision register gets no user-facing tab, on
purpose: it carries no content, and a person already reads their turns as a
conversation. Where it is genuinely useful — a technical reader, an Article-12
extraction — it is offered, and the administrator's screen shows it only under
the technical format rather than everywhere with two dead renderings.

### 14. The parameters of the inference, read from what was SENT (lot 7)

Article 12 asks with what settings an answer was produced. LIA held three
different answers, and the analysis that opened this lot was mostly about
finding out which one is true:

1. ``llm_config_overrides`` — the CONFIGURATION. Mutable and unversioned:
   reading it tomorrow does not say what ran yesterday.
2. the ``LLMAgentConfig`` resolved in ``get_llm()`` — what LIA DECIDED. ADR-245
   may coerce a reasoning level afterwards, so it is not always what was sent.
3. ``invocation_params``, which LangChain hands every callback — what was
   actually SENT.

**Only the third is the parameters of the inference**, and it needed no new
plumbing: the tracking callback already receives it beside the metadata it
reads for ``llm_type``. No new table either — ``token_usage_logs`` was already
the per-call record, keyed by the same ``run_id`` as the registers, already
carrying the model, the slot, the latency and the outcome. A fourth register
would have duplicated it.

Two rules came from probing the real adapters rather than the documentation.
**The output cap has three spellings** (``max_completion_tokens``,
``max_tokens``, ``max_output_tokens``) and reasoning has three shapes; storing
the provider's own would give one concept three names and compare with nothing,
so the columns speak ONE vocabulary and reasoning speaks ADR-245's. And
**capture is an allowlist, never a dump**: no adapter leaks a credential in its
invocation parameters today, nothing guarantees the next one will not, and a
register is the last place a key should end up. A ``params_digest`` over every
allowlisted parameter keeps « was anything else set? » answerable when the
readable columns cannot say.

One honesty note the contract cannot express: unlike the three registers,
``token_usage_logs`` is ``BILLING_RETAINED`` and therefore OUTLIVES the account
it describes. It holds no content and no name — but it is not purged with the
rest, and the traceability document says so rather than letting a reader assume.

### 15. Situations that mean the record is incomplete (lot 8)

Inventory first: of everything Article 12 calls a « situation presenting a
risk », only FOUR left no durable trace. Refusals, orphaned claims, failed LLM
calls and failed turns were already recorded by lots 1, 4, 6 and ADR-244.

The four gaps split into two natures, and merging them would have been the same
mistake as one register for actions and consultations:

- **The turn stopped before it finished** is a fact OF THE TURN. It became a
  ``stop_reason`` column on ``agent_decisions``, read from ``react_exit_reason``
  — the one predicate that decides the stop (ADR-248 invariant 2) — never
  recomputed. The outcome stays ``interrupted``; this says why. Two columns,
  two facts, and the user's own archive reads it in their language.
- **The record itself is incomplete** cannot be written into the register that
  is failing. ``agent_integrity_events`` holds four bounded kinds: an effect
  performed with no ledger row, a turn whose consultations nobody collected, a
  chain break, a notary pass rolled back.

Each of those four already had a metric and an alert. **A counter cannot say
WHICH accounts and WHICH turns are affected**, and that is precisely the
question a user and a regulator ask — which is what earns the table rather than
a fifth counter. Every row is written at the point that already increments the
metric: one detection, two destinations, never a second detector (pinned by a
guard that reads the source). And observing never breaks the observed: every
write swallows its own failure, because an integrity note able to fail a turn
would be a worse defect than the one it records.

### 16. The reader gets the machine-readable form too (owner ask, 2026-09-05)

The account holder had two formats of their own register — markdown to read,
CSV to count. They now have a third, JSON Lines, and it is the **same contract
the administrator's export obeys**: an allowlist of columns, no content,
identifiers pseudonymised.

Reusing it rather than inventing a user variant is the decision. It makes the
file safe to **hand on** — the readable export already carries the reader's own
wording, so what this adds is a record of the same events that reveals nothing
when attached to a bug report, a complaint or a portability request — and it
takes no new privacy decision, where a second contract for the same rows would
be a second place for a column to slip from « forbidden » to « exported ».

Two properties the shape enforces. The route has **no account parameter at
all**, so there is no way to ask for someone else's register by mistake: a
filter one could forget is a filter someone eventually forgets. And the format
is an **entry in a table**, not a branch — the module said so before this lot
existed, and a guard now pins that every offered format has a renderer.

What the file holds decides whether it is safe to send, and one word cannot say
that, so each format carries a description associated **programmatically**
(`aria-describedby`), not only as a tooltip a screen reader and a finger both
miss.

### 17. One extraction, five records that never add up (lot 9)

A composition, not new machinery: the specs, the pseudonymisation, the row
builder and the JSONL renderer all existed. The file is JSON Lines with a
``lia_record`` discriminator per line over the five records — turns, effects,
consultations, LLM calls, gaps.

The discriminator is namespaced because the plain one was **silently
overwritten** on the first render against real rows: the integrity register has
a business column called ``kind``. A key belonging to the FILE must be immune to
every source column name, including a sixth record's, and a guard now pins it.

The ceiling applies **per source and is stated per source**: a file complete in
four records of five is not a complete file, and a reader must answer « is this
the whole period? » from the header alone. The sources are read from the
registry rather than listed, so a sixth record joins the extraction without
anyone remembering it.

### 18. A cap without an order is a lie about the period (owner report, 2026-09-05)

The owner read a technical export from the dev instance and reported that the
models named in it were not the ones the instance runs. Their diagnosis — « you
must have taken the code defaults » — was wrong, and the truth was worse: the
figures were real, they simply came from the **wrong end of the register**.

The five reads carried a `LIMIT` and no `ORDER BY`. PostgreSQL then returns
whatever it reaches first, which for an append-only table is the OLDEST rows.
So a 5000-row cap on a register holding more than that produced a file covering
2026-01-31 → 2026-03-05 and naming eight models the instance had long since
stopped configuring, while the header truthfully said « capped ». Nothing was
fabricated and nothing was verifiable: a reader checking their recent activity
found none of it.

The rule this leaves: **a capped read states which end it kept.** All five reads
now go through one helper (`infrastructure/database/export_window.py`), which
orders newest-first, takes the cap, and reverses — so the file reads
chronologically while holding the most recent window. Verified against the dev
register: 2026-07-22 → 2026-09-04, with the four models `llm_config_overrides`
actually names.

It sits in `infrastructure/database/` rather than beside the registers because
the chat domain reads it too, and putting it in `domains/agents/` closed an
import cycle between two domains — a local import would have hidden the edge
rather than removed it.

The corollary the owner stated themselves and the design already honoured: a
model change must remain **visible**. Every LLM row stores the model it actually
used, so the history keeps what was current at the time; nothing resolves a
model name at read time, which would rewrite the past every time a slot is
reconfigured.

### 19. The same records, seen as figures (owner ask, 2026-09-05)

The registers answer « what exactly happened »; a shape answers « what has been
happening ». Both are needed and neither replaces the other, so the charts are a
**third tab** beside the two journals rather than decoration bolted onto them.

Four decisions carry the ADR's doctrine into the drawing:

- **One component, two audiences.** A reader looking at their own records and an
  operator looking at one, several or every account see the same cards from the
  same computation. Two renderings would be two places for a figure to be right
  on one screen and wrong on the other.
- **Nothing is counted on the client.** Every series arrives aggregated. A
  client that downloaded rows to count them would fetch the very content the
  registers exist to keep in one place, and would disagree with the export.
- **The exact total sits beside the bars** (ADR-185). The server folds a long
  tail into `other`; without the total a reader could not check that the bars
  add up, and a chart nobody can check is decoration.
- **Labels come from bounded vocabularies.** A consultation shows its DOMAIN
  (31 nouns), a graph step collapses `sub-agent: <title>` and
  `MCP Iterative: <server>` to one word — those two carry user-authored text and
  third-party server names, which must never reach a chart legend, a metric
  label or an operator's screen.

An empty series says it is empty; the integrity card gets its own sentence,
because there empty is the good news.

### 20. What a cold adversarial review found, after green gates (2026-09-05)

Every gate was green when this review started. Four defects survived them, and
each says something about what a gate cannot see.

**A confirmed draft could report a success nobody had.** When the claim was
lost to a row that kept no result — a first attempt that FAILED, or a winner
still in flight — the executor gate returned an empty dict. The caller reports
`success=True` for ANY dict that comes back, so the user was told their email
had left. The tool wrapper answered the same situation honestly because its
return value is read by a MODEL; the executor's is read by the CALLER, and the
two contracts had drifted apart. It now raises `EffectAlreadyClaimed`, wordless
so the caller resolves the sentence from the locale, and the ticket carries the
row's STATUS so « already performed » and « a previous attempt failed » are two
different answers rather than one.

**The widest read in the application had no authorisation.**
`/admin/effects/export/article12` — five records, every account — carried a
docstring saying « must be a superuser » and never checked. Its three
neighbours did check, which is exactly why nobody noticed: the guard lives in
the body, so nothing structural refuses a handler that forgets it.

**Two admin routes were dead, and their guard was fictitious.**
`require_superuser` is an imperative helper `(current_user, action=…)`. Wired as
`Depends`, FastAPI reads `current_user` as a required QUERY parameter: the route
answers 422 to every well-formed request and authorises nothing. The
administrator's charts and the cross-account chain verification had never
worked. The owner reported the symptom (« Les figures n'ont pas pu être
calculées ») from the dev instance.

**A register write abandoned under cancellation had no strong reference.**
`asyncio` holds tasks weakly, and the abandonment path returns while the write
is still running; the module's own background registry now holds it, which is
what `safe_fire_and_forget` exists for two hundred lines above.

Three guards close the class rather than the instances: no admin route without
a real check (an AST search for a CALL, because the route that shipped
unguarded contained the guard's NAME in its docstring), no use of the imperative
helper as a dependency, and no required query parameter an endpoint never
declared — the general shape of any helper-as-dependency mistake.

The last one is the lesson: **a guard that matches a name validates a name.**
The property test written earlier in the same review passed on both dead routes,
because it found `require_superuser` in their dependency list without asking
whether that dependency could work.

### 21. A figure says what it is, or it says nothing (2026-09-05)

Two of the ten series do not draw plain counts, and each wore a badge that
could not be checked against its bars. The tokens chart STACKS prompt and
completion on one bar while its total counted prompt tokens only — shorter than
the bars beside it. The latency chart draws MEANS, and its badge summed them:
a sum of averages is not a quantity, and the folded « other » bar was taller
than any value it stood for.

A series now declares its KIND — `count`, `stacked`, `average` — and the badge
is derived from it rather than passed by the caller, so a chart added tomorrow
cannot label it wrongly. The averages are computed from a SUM and its
OBSERVATIONS rather than from `avg()` per group, because that is the only shape
that can be folded and totalled: the overall figure and the folded bar are both
weighted.

The same pass closed a leak: `consultation_latency_by_tool` grouped on the raw
`tool_name`, so a third-party MCP server's own tool names reached the axis —
and, on the administrator's cross-account screen, listed the servers one account
had installed. It collapses to one word now, the rule `treatment_domain` has
lived by since ADR-255.

## Consequences

**What changes for a user (lot 5).** Above the two tabs, a card states how much
of their journals is sealed and up to when — and offers a verification they
trigger themselves, because a claim of integrity made before anyone checked is
the thing this mechanism replaces. A clean verdict shows the head fingerprint,
which is the one check a person can perform alone, later, against a copy they
kept. Their account archive carries the same attestation.

**What changes for a user.** A confirmation card can now appear in pipeline
mode for a third-party MCP tool whose server asks for one. Under the answer,
what the turn actually did is stated — including a failure. `/dashboard/actions`
carries the two registers as two tabs — *Actions* and *Consultations* — each
with its own filter and its own export, in three formats (readable, CSV,
technical). A third tab, *Vue d'ensemble*, draws the same five records as
figures (`GET /effects/statistics`); the tile that leads there is named
*Registres*, because the surface stopped being a journal of actions alone.

**What changes for an operator (lot 5).** Dashboard 28 gains a *Scellement des
journaux* section; two alerts (`LedgerChainBroken`, `LedgerNotaryStalled`) and
their runbooks; and `/admin/effects/chain/verify` verifies one, several or every
account, broken chains first. The subsystem is OFF by default
(`LEDGER_CHAIN_ENABLED=false`) — the registers are complete without it.

**What changes for an operator.** Dashboard 28 answers "is the gate healthy?",
with two core alerts (stale `CLAIMED` rows; the ledger failing to record) and
their runbooks. Six counters and one DB-backed gauge, all with bounded labels —
never `tool_name`, whose value set belongs to third-party servers. The
administrator's registers section carries the same figures over one, several or
every account (`GET /admin/effects/statistics`) — the same component and the
same computation as the reader's, so the two screens cannot disagree.

**What the register costs.** Measured: **0.64 µs** and **zero database
sessions** on a read — the path most calls take short-circuits before any
bookkeeping. A mutation pays two short transactions.

**What was deliberately NOT done.**

- No plan-level approval was built on: `approval_gate_node` is a pass-through
  and tool-level HITL supersedes it.
- The `tool_confirmation` HITL interaction was NOT removed. It looked dead from
  the pipeline (nothing sets `pending_tool_confirmation`), but `react_nodes`
  raises an `interrupt()` carrying that very type for every mutation — it is
  ReAct's confirmation card. Only the two pipeline state keys are unreachable,
  and a test already pins that the new `tool_call` draft does not go there.
- The technical export is capped and synchronous rather than a background job:
  the cap travels in the file's header and the period filter makes chunking
  exact, which a second job subsystem would not improve.

## Guards this decision leaves behind

| Guard | Refuses |
|---|---|
| `assert_mutation_policy_completeness` | a manifest that declares no policy, or contradicts itself |
| `assert_effect_gate_completeness` | a registered capability, or a draft executor, that bypasses the gate |
| `assert_effect_label_completeness` | a capability that can act but cannot say what it did |
| `test_registered_tool_declaration_guard` | a registered tool with no manifest and no written exemption |
| `test_effect_metric_label_bounds` | an unbounded Prometheus label on an effect metric |
| `test_technical_export` | a model column neither exported nor explicitly forbidden |
| `test_metric_coverage_ratchet_guard` | an effect metric no dashboard, rule or alert reads |
| `assert_treatment_domain_completeness` | a capability the consultation register could only show as a tool name |
| `test_treatment_collection_graph` | a collector that loses a turn's consultations on a real compiled graph |
| `test_treatment_end_to_end` | a register that stays EMPTY after a turn driven from the real entry point |
| `test_chain_spec` | a column of a covered model that is neither digested nor excluded on purpose |
| `test_chain_digest` | an encoding change that would silently invalidate every past chain (frozen vectors) |
| `test_chain_notary_db` | a rewritten row, a deleted row, a rewritten entry or a deleted entry going undetected |
| `test_scheduler_jitter` | a notary pass registered without jitter (ADR-254) |
| `test_chain_claim_immutability` | an `UPDATE` on a column the CLAIM digest covers — it would break every chain on rows nobody touched |
| `assert_decision_wording_completeness` | a turn outcome an archive could only print as a stored code |
| `test_decision_recording` | a turn that died reading as one that answered |
| `test_decision_notes_are_inside_the_turn` | a `note_*` called after the row is written — every turn would read `interrupted` |
| `test_inference_params` | a credential kept, or one concept stored under three provider spellings |
| `test_integrity_events` | a metric that fires without recording which account it concerns |
| `test_article12_export` | a source column shadowing the file's own discriminator |
| `TestEverySpecIsREACHABLE` | an export contract the route refuses, or a route value nothing describes |
| `test_user_technical_export` | a reader's own technical file carrying content, or a route that could read someone else's register |

Three of those refuse the BOOT. That is deliberate: `init_agent_registry` used
to catch its own guards' `RuntimeError` and merely log it, so three ADR-085
guards left the instance running with an empty catalogue. Completeness failures
now raise `StartupCompletenessError` and are re-raised by the step. And the
draft executors are registered **before** the asserts run: they register lazily,
so at assert time the registry held zero entries and the executor half of two
guards passed on anything — an assert that cannot fail is a promise nobody
checks.
