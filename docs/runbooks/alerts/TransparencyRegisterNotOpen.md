# TransparencyRegisterNotOpen - Runbook

**Severity**: critical
**Component**: effects (ADR-263, lot 4)
**Impact**: The consultation register is **incomplete** for some turns. Nothing is broken from a user's point of view, which is exactly why this is critical: a register that is quietly partial is worse than none, because it is read as if it were whole.
**SLA Impact**: None on latency or availability. The impact is on **trust**: the account journal and every export understate what the assistant consulted.

---

## 1. Alert Definition

**Alert Name**: `TransparencyRegisterNotOpen`

**Prometheus Expression**:
```promql
sum(increase(lia_treatments_uncollected_total[15m])) > 0
```

**Firing Duration**: `for: 5m`

**Labels**: `severity: critical`, `component: effects`, `tier: core`

**No threshold file, deliberately.** The acceptable value is zero, in every environment. A tunable threshold would invite raising it, and "we lose a few consultations" is not a state anyone should be able to configure.

**The summary carries no count.** `increase()` extrapolates to the window edges, so its value is an estimate — and this codebase does not show counts that are not exact (ADR-185). The alert says THAT it happened; the panel and the register itself say how much.

---

## 2. What the counter actually means

`record_treatment` is called by the effect gate on every read-through call. It increments this counter when, and only when:

- a **runtime context exists** — a turn is genuinely running, so there is something to record; and
- **no collector is published** — nobody opened a register to receive it.

Outside a turn (a script, a test, a boot probe) it stays silent: there is nothing to record and therefore no gap.

So a non-zero value has exactly one meaning: **some code path runs the agent graph without publishing the collector.**

---

## 3. Why this alert exists

The collector is published in exactly one place — `AgentService._stream_with_new_services`, beside the token tracker. That is the chat entry point, and every current caller (chat, channels, scheduled actions) goes through it.

The day someone adds a second way to run the graph — a background worker, a new API, a future execution mode — the consultations of those turns would be collected by nobody, the register would be silently partial, and no test would fail: the existing end-to-end guard proves the CHAT path records, not that every path does.

This is the ADR-148 failure mode verbatim: a source failing open dropped the health signals on 46.5 % of heartbeat ticks for a week because no metric existed. A gap that produces no signal is a gap nobody fixes.

---

## 4. Diagnosis

### Step 1 — Which execution mode?

```promql
sum by (execution_mode) (increase(lia_treatments_uncollected_total[1h]))
```

The label names the mode the runtime context declared (`pipeline`, `react`, `subagent`). A mode you do not recognise is itself the answer.

### Step 2 — Find the entry point

```bash
grep -rn "treatment_recorder(" apps/api/src/          # should be exactly ONE call site
grep -rn "graph.astream\|graph.ainvoke" apps/api/src/ # every way the graph runs
```

The log line `treatment_register_not_open` is emitted with the execution mode at WARNING on the same path; correlate it with `run_id` in the surrounding request logs to identify the caller.

### Step 3 — Confirm the loss

```sql
SELECT count(*) FROM agent_treatments WHERE occurred_at > now() - interval '1 hour';
```

Compare with `sum(increase(lia_treatments_total[1h]))`. The register counter only moves on a successful write, so a large gap between what the instance served and what the register holds confirms the scope.

---

## 5. Resolution

**Open a register on the new path.** One line, at the level that owns the turn:

```python
async with tracker, treatment_recorder(run_id=run_id):
    ...
```

The `run_id` is passed explicitly and never rebuilt from a config — rebuilding it one layer above is precisely how lot 3 filed a turn's effects under the thread id and made the surface look empty.

**Do not silence the counter.** It is the only thing standing between "the register is complete" and "the register looks complete".

**Backfill is impossible**, and that is worth saying plainly: a consultation not recorded when it happened cannot be reconstructed afterwards — the gate keeps no other trace. The turns already lost stay lost; fixing the path stops the loss.

---

## 6. Prevention

- The end-to-end guard (`test_treatment_end_to_end`) drives the REAL chat entry point and asserts the register is non-empty. Extend it, rather than copy it, when a second entry point is added.
- `tests/unit/domains/agents/effects/test_treatment_collection.py::TestALostRegisterIsNeverSILENT` pins the three cases: a turn with no register is counted, a call outside a turn is not, a collected turn is not.

---

## 7. Related

- ADR-263 — Execution authority chain and effect register
- `docs/runbooks/alerts/EffectLedgerUnavailable.md` — the same question for the ACTION register
- Dashboard 28 — Effect ledger, panel *Consultations PERDUES (aucun registre ouvert)*
