# TransparencyRegisterGrowth - Runbook

**Severity**: warning
**Component**: effects (ADR-263, lot 4)
**Impact**: None yet. This alert is not an incident — it is a **decision becoming due**.
**SLA Impact**: None. Nothing is degraded; a register is simply larger than the size at which its owner chose to be asked about it.

---

## 1. Alert Definition

**Alert Name**: `TransparencyRegisterGrowth`

**Prometheus Expression**:
```promql
max by (table) (lia_ledger_bytes) > <<<ALERT_CORE_LEDGER_BYTES>>>
```

**Firing Duration**: `for: 1h`

**Labels**: `severity: warning`, `component: effects`, `tier: core`

**Why per table**: the two registers grow at completely different rates — `agent_effects` takes one row per **action**, `agent_treatments` one row per **consultation**, and a busy turn consults dozens of capabilities while acting on none. Summing them would let the busy one hide behind the quiet one.

**Where the number comes from**: Prometheus cannot see rows. `lia_ledger_bytes` is a DB-backed gauge (pattern `lifetime_metrics.py`): the API reads `pg_total_relation_size` — the table **and its indexes** — at the periodic sync interval and transports the figure here. Its companion `lia_ledger_rows` is an **estimate** (`pg_class.reltuples`, refreshed by `ANALYZE`) and says so in its help string: a `COUNT(*)` every sync would sequentially scan the largest table in the schema, and the supervision would become the load it watches.

---

## 2. Why no purge job exists

This is a decision, recorded here so nobody re-opens it by accident.

Owner arbitration, 2026-09-04: *keep everything for now and add a purge mechanism later if needed. Everything is deleted when the account is deleted. Have metrics followed in Grafana for supervision and alerting.*

Both registers cascade on `users.id`: an account deletion removes every row it owns, and « Tout oublier » does not — a reset is not an erasure of what the assistant did (ADR-260 draws the same line for Redis key families). So retention is **until the account is deleted**, deliberately, and this alert is the instrument that decides whether that remains reasonable.

Building a purge before a measurement asked for one would have meant choosing a retention window from an intuition. That is what this alert exists to replace.

---

## 3. Symptoms

### What Ops see
- Dashboard **28 - Effect ledger**, panel *Volume des registres*, one series above the threshold.
- The companion panel *Lignes des registres* shows which register is growing and how fast.

### What the user sees
Nothing. The journal and the exports keep working; they simply cover more history.

---

## 4. Diagnosis

### Step 1 — Which register, and how fast?

```promql
lia_ledger_bytes
deriv(lia_ledger_bytes[7d]) * 86400        # bytes per day, per register
```

Roughly 250 bytes per treatment row (three UUIDs, a tool name, four short enumerations, a duration, a timestamp, plus the row header and two indexes). A hundred tool calls a day per user is about 9 MB a year; five hundred is about 45 MB.

### Step 2 — Is it rows, or is it bloat?

```promql
lia_ledger_bytes / clamp_min(lia_ledger_rows, 1)
```

Far above ~250 bytes/row on `agent_treatments` means dead tuples rather than data — a table that has taken many deletes (an account removal cascades) without a `VACUUM`. Check with:

```sql
SELECT relname, n_live_tup, n_dead_tup, last_autovacuum, last_autoanalyze
FROM pg_stat_user_tables
WHERE relname IN ('agent_effects', 'agent_treatments');
```

### Step 3 — Is one account responsible?

```sql
SELECT user_id, count(*) AS rows
FROM agent_treatments
GROUP BY user_id
ORDER BY rows DESC
LIMIT 10;
```

A single account far ahead of the others usually means a scheduled action or a ReAct loop consulting in a cycle. That is a **behaviour** to fix, not a volume to purge — check `lia_effect_claims_total{source="scheduled"}` and the ReAct budget (ADR-256) before touching the data.

---

## 5. Resolution

### If it is bloat (Step 2)

```sql
VACUUM (ANALYZE) agent_treatments;
```

`ANALYZE` also refreshes `reltuples`, so the rows gauge realigns with reality at the next sync. Nothing else to do.

### If it is a runaway producer (Step 3)

Fix the producer. A register that faithfully records a loop is doing its job; the loop is the defect.

### If it is ordinary growth

Then the decision this alert exists for is due. In order of preference:

1. **Raise the threshold** (`ALERT_CORE_LEDGER_BYTES` in `infrastructure/observability/prometheus/thresholds/<env>.env`) if the disk comfortably holds it. Re-render with `prepare_config.sh`. This is the right answer while the figure is small relative to the disk — the registers are the transparency this system promises, and deleting them to save megabytes is a bad trade.
2. **Build the purge**, at which point it is a designed feature and not a reflex: a retention setting, a periodic job on the existing scheduler (with `jitter_seconds_for(...)` — six jobs in one second is a measured failure mode here), and a written decision on what a user is told about what disappeared. A register that silently loses history is worse than one that grows: it can no longer be used as evidence.

**Never** delete rows by hand from `agent_effects`: the ledger's unique `(thread_id, idempotency_key)` is what makes "exactly once" true, and freeing a key lets a replayed approval perform its effect a second time.

---

## 6. Prevention

- Watch `lia_ledger_rows` growth per week rather than the absolute figure; a slope change is the early signal, a threshold crossing is the late one.
- `pg_stat_user_tables.last_autoanalyze` staleness makes the rows gauge drift; if autovacuum is not keeping up on this instance, that is worth fixing on its own account.

---

## 7. Related

- ADR-263 — Execution authority chain and effect register
- `docs/runbooks/alerts/EffectLedgerClaimedOrphans.md`
- `docs/runbooks/alerts/EffectLedgerUnavailable.md`
- Dashboard 28 — Effect ledger
