# LedgerChainBroken - Runbook

**Severity**: critical
**Component**: effects (ADR-263, lot 5)
**Impact**: A transparency register was altered **outside the application**. Either a row in `agent_effects` / `agent_treatments` was rewritten or deleted, or an entry of `ledger_chain` was. Nothing is degraded from a user's point of view — which is precisely why this is critical.
**SLA Impact**: None on latency or availability. This is a **security** signal, not a performance one.

---

## 1. Alert Definition

**Alert Name**: `LedgerChainBroken`

**Prometheus Expression**:
```promql
sum(increase(lia_ledger_chain_breaks_total[15m])) > 0
```

**Firing Duration**: `for: 0m` — the first observation is the incident.

**Labels**: `severity: critical`, `component: effects`, `tier: core`

**No threshold file, deliberately.** The acceptable value is zero, in every environment. A tunable threshold would invite raising it after the first false alarm, and "a few unexplained alterations" is not a state anyone should be able to configure.

**The summary carries no count.** `increase()` extrapolates to the window edges, so its value is an estimate, and this codebase does not show counts that are not exact (ADR-185). The alert says THAT it happened; `/admin/effects/chain/verify` says where.

---

## 2. What the counter actually means

The chain notarises each register row: the digest of an explicit column allowlist, bound to the previous entry's hash. `lia_ledger_chain_breaks_total` is incremented by exactly two paths, and its `reason` label says which:

| `reason` | What was found | Who found it |
|---|---|---|
| `sequence` | An entry is missing, duplicated or out of order — or the chain does not start at 1 | the notary's per-pass contiguity check, **and** any walk |
| `prev_hash` | An entry points at a predecessor it does not follow | a walk |
| `entry_hash` | An entry's own hash does not match its content — it was rewritten | a walk |
| `payload` | The covered **register row** no longer matches the digest taken of it, or was deleted | a **deep** walk only |

`sequence` is the only one that fires without anybody asking: the notary compares the head position with the entry count on every pass, for the price of one index-only scan. The other three need a walk, which happens when a user opens their own verification or an administrator runs a sweep.

---

## 3. What it does NOT mean

- **It is not an application bug by default.** Every legitimate write path leaves the chain verifying: a claim and its close produce two entries, and an integration test pins that a normal lifecycle verifies clean. If the application could break its own chain, that test would be red.
- **It is not about the last minute.** Notarising is asynchronous. A row created inside the current window (`lia_ledger_chain_lag_seconds`) is not sealed yet, so altering it produces no break at all. This alert is about what WAS sealed.
- **A `payload` break does not say what changed**, only that something did. The chain holds digests, never content — by design.

---

## 4. Diagnosis

### Step 1 — Which reason, and how many

```promql
sum by (reason) (increase(lia_ledger_chain_breaks_total[24h]))
```

`sequence` alone points at deleted chain entries. `payload` points at the registers themselves.

### Step 2 — Which accounts

```bash
curl -s -b "$COOKIE" "$API/api/v1/admin/effects/chain/verify?deep=true" | jq '.[] | select(.ok == false)'
```

Broken chains come back first. Each row carries `broken_at_seq` and `reason`.

### Step 3 — What sits at that position

```sql
SELECT seq, kind, subject_id, occurred_at
FROM ledger_chain
WHERE user_id = '<uuid>' AND seq BETWEEN <n> - 2 AND <n> + 2
ORDER BY seq;
```

`kind` says which stage was covered, `subject_id` the register row. For a `payload` break, read that row and compare its columns with `chain_spec.py`'s allowlist for that stage — those are the only columns the digest covered.

### Step 4 — Who could have written it

```bash
grep -rn "ledger_chain_gap_detected" /var/log/…      # the notary's own finding
```

Then the database's own trail: connection logs, recent `pg_stat_activity`, and any migration or maintenance script run in the window between the entry's `occurred_at` and now.

---

## 5. Resolution

**Treat it as a security event until proven otherwise.** The application has no code path that alters a notarised row, so a break means something outside it did: a manual `UPDATE`, a restore from an inconsistent backup, a migration that rewrote data, or an intrusion.

**Do not "repair" the chain.** There is deliberately no endpoint, task or script that re-notarises a broken chain, and adding one would hand an attacker the same tool. A chain that can be repaired proves nothing.

The two legitimate outcomes:

1. **The alteration is explained** (a reviewed migration, a documented restore). Record it: the ADR, the runbook of the operation, and the affected accounts. The chain stays broken at that position and every later walk keeps reporting it — that is correct, and it is the honest record of what happened.
2. **The alteration is not explained.** Escalate. The registers can no longer be presented as complete for those accounts, and any regulatory statement built on them must say so.

**A restore is not a repair.** Restoring the registers from a backup taken before the alteration restores rows whose digests will match again — but only if the chain is restored from the same point. Restoring one and not the other manufactures a break.

---

## 6. Prevention

- Nothing in the application writes to `ledger_chain` except the notary, and nothing updates a notarised register row. Keep it that way: a new writer on `agent_effects` must only ever INSERT, or close a row that has not been notarised yet.
- Database credentials that can `UPDATE` the two registers should be operator credentials, not application ones.
- `tests/integration/domains/agents/effects/test_chain_notary_db.py` pins that a rewritten row, a deleted row, a rewritten entry and a deleted entry are each detected, and at which position.

---

## 7. Related

- ADR-263 — Execution authority chain and effect register
- `docs/technical/AI_ACT_TRACEABILITY.md` — what the chain proves, and what it does not
- `docs/runbooks/alerts/LedgerNotaryStalled.md` — the other half: the chain not advancing
- Dashboard 28 — Effect ledger, section *Scellement des journaux*
