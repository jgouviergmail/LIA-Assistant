# LedgerNotaryStalled - Runbook

**Severity**: warning
**Component**: effects (ADR-263, lot 5)
**Impact**: The transparency registers are still **complete and readable**. What is suspended is the ability to **prove** they were not altered since the notary last ran.
**SLA Impact**: None. No user-facing behaviour changes.

---

## 1. Alert Definition

**Alert Name**: `LedgerNotaryStalled`

**Prometheus Expression**:
```promql
max(lia_ledger_chain_lag_seconds) > <<<ALERT_CORE_LEDGER_CHAIN_LAG_SECONDS>>>
```

**Firing Duration**: `for: 10m`

**Thresholds**: `production.env` 300 s, `staging.env` 600 s, `development.env` 900 s.

**It watches the WINDOW, not the backlog.** `lia_ledger_chain_pending` counts rows; this gauge measures the age of the oldest one. A busy instance can hold thousands of pending rows and be perfectly healthy — its notary is simply working through slices. An instance with three pending rows from two hours ago is not.

---

## 2. What the gauge actually means

Notarising is asynchronous, on a measurement: sealing inside the write path costs 6,0 ms per row against 0,21 ms for the write itself — ×28 on the user's critical path, for a property nobody reads in that moment. The price of moving it out of band is a window: a row created at T is sealed at T+δ, and a rewrite inside δ leaves no trace.

`lia_ledger_chain_lag_seconds` **is** δ, measured rather than assumed. Publishing it is what keeps the design's one concession a stated cost instead of a hidden one.

At the default 60 s period, a healthy instance sits between 0 and ~120 s.

---

## 3. Diagnosis

### Step 1 — Is the notary running at all?

```promql
sum(rate(lia_ledger_chain_entries_total[10m]))
```

Flat zero while `lia_ledger_chain_pending` is non-zero means the job is not executing. Flat zero with `pending` at zero means there is simply nothing to do — the gauge would read 0 and this alert would not be firing.

### Step 2 — Is the flag on?

```bash
docker compose exec api python -c "from src.core.config import settings; print(settings.ledger_chain_enabled, settings.ledger_chain_interval_seconds)"
```

`LEDGER_CHAIN_ENABLED=false` is a legitimate configuration; the sealing subsystem is OFF by default. In that case the gauge is not published at all and this alert cannot fire — if it is firing, the flag is on.

### Step 3 — Is this instance the leader?

The notary runs under leader election, like every write-side scheduled job. Check the elector's own logs (`scheduler_leader_*`) and confirm exactly one instance holds leadership. Two symptoms point here:

- no instance is leader → nothing runs;
- the leader has the job **unregistered** because it booted with the flag off and the flag was turned on afterwards → restart it. `register_ledger_jobs` reads the flag at boot.

### Step 4 — Is it failing every pass?

```promql
sum(increase(lia_ledger_chain_pass_failures_total[1h]))
```

A steady rate here means passes are being rolled back. The most common cause is two notaries running at once — one of them loses the `UNIQUE (user_id, seq)` race on every account. That is survivable but wasteful, and it means leader election is not doing its job.

```bash
grep -rn "ledger_notary_pass_failed\|ledger_notary_account_failed" /var/log/…
```

### Step 5 — Is one account starving the pass?

```sql
SELECT user_id, count(*) FROM agent_treatments WHERE notarised_at IS NULL
GROUP BY user_id ORDER BY 2 DESC LIMIT 10;
```

A pass serves at most `LEDGER_CHAIN_ACCOUNTS_PER_PASS` accounts and `LEDGER_CHAIN_ROWS_PER_ACCOUNT` rows each. An account with a very large backlog is worked through over several ticks by design — but if the instance-wide arrival rate exceeds `accounts × rows / interval`, the backlog never drains.

---

## 4. Resolution

**If the job is not running**: restart the leader, or turn the flag on and restart so `register_ledger_jobs` registers it.

**If the backlog is structural** (step 5), raise the ceilings rather than the interval:

```bash
LEDGER_CHAIN_ROWS_PER_ACCOUNT=2000
LEDGER_CHAIN_ACCOUNTS_PER_PASS=200
```

Measured: 500 rows chain in 41 ms, so a larger slice stays comfortably inside a 60 s tick. Shortening the interval instead multiplies the per-pass fixed cost without moving more rows.

**Do not lower the alert threshold to silence it.** The threshold states how wide a blind window the deployment accepts; raising it is a decision about what the registers can prove, not a tuning knob.

**Nothing is lost while this fires.** The rows stay pending, the marker (not a watermark) decides what is pending, and the next successful pass seals everything that accumulated — including rows whose transaction committed after an earlier pass had already read the clock.

---

## 5. Prevention

- `tests/unit/domains/agents/effects/test_chain_notary.py::TestTheJobIsInertUntilItIsTurnedOn` pins the flag guard, the jitter, `max_instances=1` and the initial delay.
- `tests/integration/…/test_chain_notary_db.py::TestAPassIsIdempotentAndCatchesUp` pins that a late-committed row is picked up rather than skipped.
- The job carries `jitter` (ADR-254): periodic jobs sharing a divisor otherwise align on the same second for the life of the process.

---

## 6. Related

- ADR-263 — Execution authority chain and effect register
- `docs/technical/AI_ACT_TRACEABILITY.md` — the window, stated
- `docs/runbooks/alerts/LedgerChainBroken.md` — the other half: the chain not holding
- Dashboard 28 — Effect ledger, panel *Fenêtre de non-traçabilité*
