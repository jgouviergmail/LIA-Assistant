# EffectLedgerUnavailable - Runbook

**Severity**: critical
**Component**: effects (ADR-263)
**Impact**: Two things at once, both bad. Actions the user had to confirm are **refused** because they cannot be recorded (by design: what the user confirmed is recorded or not done), and actions they never had to confirm are **performed with no trace**.
**SLA Impact**: Direct. Confirmed actions fail for the user, and the register stops being a faithful account.

---

## 1. Alert Definition

**Alert Name**: `EffectLedgerUnavailable`

**Prometheus Expression**:
```promql
(
  sum(rate(lia_effect_ledger_failures_total[5m]))
  + sum(rate(lia_effect_unrecorded_total[5m]))
) > <<<ALERT_CORE_EFFECT_LEDGER_FAILURE_RPS>>>
```

**Firing Duration**: `for: 5m`

**Labels**: `severity: critical`, `component: effects`, `tier: core`

**Why the two terms are summed**: they are the same failure seen from either side of the policy split. A `confirm` effect that cannot be claimed is refused (a failure); a `reversible` one runs anyway and is counted as unrecorded. Watching only one would miss half the incident.

---

## 2. Symptoms

### What Ops See
- Dashboard **28 - Effect ledger**, panels *Échecs du registre* and *Effets NON enregistrés*, both non-zero (they must sit at zero).
- API logs carrying `effect_ledger_claim_failed`, `effect_ledger_close_failed` or `effect_unrecorded`.

### What the user sees
For a third-party MCP tool needing confirmation: *"This action could not be recorded and was therefore not performed."* Everything else keeps working — which is exactly why this needs an alert rather than a support ticket.

---

## 3. Possible Causes

### Cause 1: PostgreSQL unreachable or saturated (High likelihood)
The ledger opens its **own** session per claim (`get_db_context`), so pool exhaustion hits it first.

```bash
docker exec lia-postgres-prod psql -U lia -d lia -c \
  "SELECT count(*), state FROM pg_stat_activity GROUP BY state;"
docker logs lia-api-prod --since 15m 2>&1 | grep -E "effect_ledger_.*_failed" | tail -20
```

Check `DatabaseDown` and `CriticalDatabaseConnections` first: if either is firing, this alert is a symptom, not the cause.

### Cause 2: No run context names a user (Medium)
`lia_effect_unrecorded_total{reason="no_context"}` rising while `claim` failures stay flat means the gate found no `LiaRuntimeContext` — a capability invoked outside a graph run. Every row belongs to someone, so nothing can be written.

```promql
sum by (reason) (increase(lia_effect_unrecorded_total[1h]))
```

### Cause 3: Encryption key rotated without re-encrypting (Low, but total)
`label` and `result_payload` are encrypted. A `FERNET_KEY` change makes every write fail at once.

```bash
docker exec lia-api-prod env | grep -c FERNET_KEY   # must be 1
docker logs lia-api-prod --since 30m 2>&1 | grep -i "invalidtoken\|fernet" | head
```

---

## 4. Resolution Steps

### Immediate — decide whether to keep serving
Nothing needs to be disabled: reads are untouched, and drafts still execute (their gap is counted, not blocking). Only `confirm` tools are refused, and that refusal is the owner's rule, not a bug.

### Fix the database first
```bash
docker ps --filter name=lia-postgres-prod
docker exec lia-postgres-prod pg_isready -U lia
docker restart lia-api-prod    # only after the database answers
```

### Then measure the gap you must explain
Effects performed while the register was down are the ones the journal will never show:

```promql
sum(increase(lia_effect_unrecorded_total[6h]))
```

Say so in the incident note. The register is trusted precisely because its gaps are stated.

---

## 5. Verification

```promql
sum(rate(lia_effect_ledger_failures_total[5m]))   # 0
sum(rate(lia_effect_unrecorded_total[5m]))        # 0
sum(rate(lia_effect_claims_total[5m]))            # back to its usual rate
```

---

## 6. Prevention

- The ledger's own session is deliberate: a claim inside the caller's transaction could be rolled back after the mail had left. Do not "optimise" it into the caller's session.
- Watch `CriticalDatabaseConnections`: the ledger adds two short transactions per mutating call, and none on the read path (measured: zero sessions opened for a read).

---

## 7. Related

- Dashboard: **28 - Effect ledger**
- Alert: `EffectLedgerClaimedOrphans` (the other side of the same question)
- ADR-263 — execution authority chain and effect register
