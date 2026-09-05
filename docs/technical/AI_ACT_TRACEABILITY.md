# Traceability: what LIA records, and what it can prove

> **Status**: the ADR-263 programme is complete — lots 5 to 9 (the
> tamper-evident chain, the decision register, the inference parameters, the
> integrity register and the unified extraction) are all in place.
> This document states what exists today; a line it does not contain is a line
> LIA does not currently produce.
>
> **Related**: [ADR-263](../architecture/ADR-263-Execution-Authority-Chain-And-Effect-Register.md),
> [ADR-260](../architecture/ADR-260-Redis-Key-Families-Scope-And-Reset-Purge.md),
> runbooks [LedgerChainBroken](../runbooks/alerts/LedgerChainBroken.md) and
> [LedgerNotaryStalled](../runbooks/alerts/LedgerNotaryStalled.md).

---

## 1. Why this document exists

LIA is a self-hosted assistant that acts on a person's own accounts. It sends
mail, moves calendar events, edits documents, reads correspondence. Two
questions follow from that, and they are not the same question:

1. **What did it do, and what did it read?** — answered by the two transparency
   registers (`agent_effects`, `agent_treatments`), since ADR-263 lots 1 to 4.
2. **How do I know those records were not edited afterwards?** — answered, in
   part, by the chain described here.

The distinction matters because the first question has a complete answer and the
second has a *bounded* one. Overstating the second is the failure mode this
whole programme was built to avoid, so the boundaries are stated before the
capabilities.

---

## 2. What LIA is, under the AI Act

LIA is not a high-risk system under Annex III: it is a general personal
assistant, self-hosted by the person it serves, deciding nothing about
employment, credit, education, law enforcement or essential services. Article 12
(record-keeping) is therefore **not legally binding on it**.

It is implemented anyway, and the reason is not compliance theatre. An assistant
that acts on someone's accounts owes that person an account of its actions
whatever the regulation says — and the discipline Article 12 imposes (automatic
recording, over the lifetime, of what the system did and on what basis) is
exactly the discipline that makes an assistant trustworthy.

Two consequences follow. LIA claims **conformance with the shape** of Article 12,
never a legal status it does not have. And where a lot is not built, this
document says so rather than describing an intention as a capability.

---

## 3. What is recorded today

| Recorded | Where | Since |
|---|---|---|
| Every external effect: what capability, under whose authority, with what declared policy, its outcome, its provider reference | `agent_effects` | lot 1 |
| Every capability consulted to answer: which capability, which domain, how long, whether it answered | `agent_treatments` | lot 4 |
| The sealing of both, per account | `ledger_chain` | lot 5 |
| Every TURN: who asked, through which route, in which mode, ending how — and why it stopped short — with POINTERS to the request and the answer | `agent_decisions` | lots 6, 8 |
| Every LLM CALL: model, provider, and the sampling and reasoning parameters actually SENT | `token_usage_logs` | lot 7 |
| Every GAP in the record itself: an effect with no row, consultations nobody collected, a chain break, a notary pass rolled back | `agent_integrity_events` | lot 8 |

Three properties hold across all of them:

- **Automatic.** Nothing is recorded because a caller remembered to. The gate is
  installed on the capability at registration (ADR-263 §3), and a capability
  that bypasses it fails a boot-time completeness assert.
- **Over the lifetime.** No purge job ships. Retention runs to account deletion,
  and the growth is instrumented (`lia_ledger_rows`, `lia_ledger_bytes`) so the
  day a purge becomes necessary is a measured day rather than a guess.
- **The user's own.** Both registers leave with the account archive and die with
  the account.

### What is deliberately NOT recorded

A consultation records the **capability**, never the request. "Consulted your
e-mails" is a record; "searched your e-mails for *Marie*" would be a second
copy of the very data the register exists to make accountable. The same rule
governs the chain (digests and identifiers, never content) and the decision
register (a route, a count, timings and two pointers).

The pointers are the deliberate answer to "the input data of the request": the
words stay in the one place that already holds them and is already purged with
the account. A copy here would double both the storage and the exposure, and
would let the register outlive a deletion the user asked for.

---

## 4. What the chain proves

Each account has its own chain. Each entry carries the SHA-256 digest of an
explicit column allowlist of one register row, bound to the previous entry's
hash. Verification walks the chain and, in deep mode, re-digests every row it
covers.

| Alteration | Detected | How |
|---|---|---|
| A register row rewritten | ✅ | its digest no longer matches (`payload`) |
| A register row deleted | ✅ | its digest cannot be recomputed (`payload`) |
| A chain entry rewritten | ✅ | its own hash no longer matches (`entry_hash`) |
| A chain entry deleted | ✅ | the sequence has a gap (`sequence`) — and this one is noticed **continuously**, by the notary itself, for the price of one index-only scan |
| The chain re-rooted at a later point | ✅ | the first entry must carry no predecessor, and only the first (`sequence` / `prev_hash`) |

Anyone can check: a user through *Registres → Vérifier l'intégrité*, an
administrator through `/admin/effects/chain/verify` over one, several or every
account.

---

## 5. What the chain does NOT prove

Four limits, each of them real. They are stated here because a proof oversold is
a proof that fails in front of the person it was built for.

**It does not prove a row was true when written.** The chain proves that a row
has not changed since it was sealed. Whether the application recorded the truth
in the first place is a different property, held up by the gate's own guards and
tests — not by cryptography.

**It does not cover the window.** Sealing is asynchronous, on a measurement:
6,0 ms per row synchronously against 0,21 ms for the write itself, ×28 on the
user's critical path. A row created at T is sealed at T+δ, and a rewrite inside δ
leaves no trace. δ is published (`lia_ledger_chain_lag_seconds`), alerted
(`LedgerNotaryStalled`), and every surface names how many rows are unsealed
rather than letting « verified » imply « all of it ».

**It does not stop a complete rewrite by someone with database credentials.**
An operator able to rewrite a row, its entry, and every entry after it produces a
chain that verifies. The defence is external: the head fingerprint shown to the
user after a clean verification and carried in their account archive. Comparing
a fingerprint noted last month against the chain today detects exactly that
attack — and it works because the copy lives outside the system being checked.

**It does not survive account deletion, and that is the design.** Deleting an
account removes its complete chain. A global chain would keep an unfixable hole
at every erasure; per account, inalterability and the right to erasure coexist
instead of trading off.

---

## 5 bis. One record does NOT die with the account

The three registers, the chain and the integrity events are purged when an
account is deleted. **`token_usage_logs` is not**: it is classified
`BILLING_RETAINED`, kept for dispute resolution, and lot 7 added the inference
parameters to it rather than duplicating it into a fourth register.

Stated here rather than left to be discovered. The row holds no name, no
content and no request — a model, a provider, sampling values, a digest — and
its account reference was already retained before lot 7. But a reader entitled
to know what survives an erasure must not have to infer it from a data map.

---

## 6. Article 12 mapped to what exists

| Article 12 expects | LIA today | Lot |
|---|---|---|
| Automatic recording of events over the lifetime | Both registers, gate-enforced, no purge | 1, 4 |
| Recording of the period of each use | `claimed_at` / `closed_at`, `occurred_at` | 1, 4 |
| Identification of the natural persons involved in verification | The HITL confirmation is recorded as the effect's `approval_kind` / `approval_ref` | 1 |
| The reference database or input data used | Consultations name the capability and its domain | 4 |
| Integrity of the records themselves | Per-account hash chain, user- and admin-verifiable | 5 |
| The input data of the request | Pointed at, never copied: `request_message_id` / `response_message_id`, `SET NULL` so a deleted conversation leaves a tombstone | 6 |
| The parameters of the inference | Read from what was SENT (`invocation_params`), normalised to one vocabulary, plus a digest of everything else allowlisted | 7 |
| Situations presenting a risk, and their handling | Refusals and failures were already recorded (lots 1, 4, 6); the four remaining gaps are `stop_reason` and `agent_integrity_events` | 8 |
| A single machine-readable extraction | `/admin/effects/export/article12` for an operator, `/effects/export/article12` for the account holder — five records, one file, one `lia_record` per line | 9 |

---

## 6 bis. Reading an extraction, and reading a chart

**Every extraction is capped, and the cap keeps the MOST RECENT window.** The
ceiling exists because production runs on a Raspberry Pi 5 — a five-record,
5000-row extraction peaked at 33,9 MB and 939 ms, against 6,6 MB and 201 ms at
1000. Two properties make that ceiling honest rather than misleading:

- it is stated **per source**, in the file's header, because a file complete in
  four records of five is not a complete file;
- it keeps the **newest** rows. Ordering was missing once, and PostgreSQL then
  returned the oldest ones: an export read on 2026-09-05 covered
  January to March and named models the instance no longer configured. Nothing
  was fabricated and nothing was checkable. A capped read now says which end it
  kept (`infrastructure/database/export_window.py`, one helper for all five).

**A model change stays visible.** Every LLM row stores the model actually used,
so the record keeps what was current at the time. Nothing resolves a model name
at read time — that would silently rewrite the past on every reconfiguration.

**The unified extraction is the account holder's too.** The operator's route
names accounts; the reader's declares **no account parameter at all**, so its
scope is the session rather than a default a query string could override — the
same shape as `/effects/statistics` and `/effects/export`. Both call one
composition and one set of reads (`technical_reads.py`, extracted from the
admin router the day the second surface appeared): a sixth record joins both
files at once, and neither audience can end up seeing a record the other does
not.

It is also the same CONTRACT, not a reader's variant — same columns, same
exclusions, same pseudonymisation, the caller's own identifier included. That
is what makes the file safe to attach to a portability request or a complaint
without editing it first, and it takes no new privacy decision: a second
contract for the same rows would be a second place for a column to slip from
« forbidden » to « exported ».

**The charts are the same records, aggregated server-side.** Nothing is counted
in the browser: a client that downloaded rows to count them would fetch the
content the registers exist to keep in one place, and would disagree with the
export. Each series carries the **exact total** of the whole filtered set beside
its bars, including whatever the top-N folded into `other`, so a reader can check
that they add up. Labels come from bounded vocabularies — a consultation reads as
its domain, and a graph step collapses `sub-agent: <title>` and
`MCP Iterative: <server>` to one word, because those two carry user-authored text
and third-party server names.

---

## 7. Operating it

The subsystem is **off by default** (`LEDGER_CHAIN_ENABLED=false`), like every
ADR-260/261/262 addition: the registers are complete and readable without it,
and an instance must be able to run the transparency it already has without also
running a notary.

```bash
LEDGER_CHAIN_ENABLED=true
LEDGER_CHAIN_INTERVAL_SECONDS=60      # also the width of the unsealed window
LEDGER_CHAIN_ACCOUNTS_PER_PASS=50
LEDGER_CHAIN_ROWS_PER_ACCOUNT=500     # measured: 500 rows seal in 41 ms
LEDGER_CHAIN_VERIFY_PAGE=1000
```

Turning it on seals retroactively: every existing register row is pending, so the
first passes chain the whole history. That is honest but weaker than it looks — a
retroactively sealed row attests to its state at chain opening, not at creation.
The genesis entry of every chain therefore records how many rows predated it, so
a reader can tell the two apart rather than assume.

**What to watch**: `lia_ledger_chain_breaks_total` (any value above zero is a
security event — runbook `LedgerChainBroken`) and `lia_ledger_chain_lag_seconds`
(the window — runbook `LedgerNotaryStalled`). Dashboard 28, section *Scellement
des journaux*.

---

## 8. Where the code is

| Concern | Module |
|---|---|
| Canonical encoding and digest (frozen test vectors) | `domains/agents/effects/chain_digest.py` |
| What each stage covers, column by column | `domains/agents/effects/chain_spec.py` |
| The link, and the walk that decides a chain holds (pure) | `domains/agents/effects/chain_link.py` |
| Pending sets, appends, markers | `domains/agents/effects/chain_repository.py` |
| One notary pass | `domains/agents/effects/notary.py` |
| Verification against the database | `domains/agents/effects/chain_verify.py` |
| The two endpoints | `domains/agents/effects/chain_router.py` |
| The reader's own export, three formats | `domains/agents/effects/export_router.py` |
| The turn's live record and its verdict | `domains/agents/effects/decisions.py` |
| Writing one row per turn, exactly once | `domains/agents/effects/decision_recorder.py` |
| The upsert that merges a resumed turn | `domains/agents/effects/decision_repository.py` |
| The scheduled pass | `infrastructure/startup/scheduler_ledger.py` |
| The capped window, newest kept, shared by five reads | `infrastructure/database/export_window.py` |
| The parameters actually sent to a model | `infrastructure/llm/inference_params.py` |
| Gaps in the record itself | `domains/agents/effects/integrity.py` |
| The five records as one file | `domains/agents/effects/article12_export.py` |
| Reading the five registers, shared by both surfaces | `domains/agents/effects/technical_reads.py` |
| The series, aggregated in SQL | `domains/agents/effects/statistics.py` |
| The user's card | `apps/web/src/components/effects/ChainSealCard.tsx` |
| The administrator's sweep | `apps/web/src/components/settings/AdminChainVerification.tsx` |
| The charts, one component for both audiences | `apps/web/src/components/effects/RegisterCharts.tsx` |
