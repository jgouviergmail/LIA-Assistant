# EffectLedgerClaimedOrphans - Runbook

**Severity**: warning
**Component**: effects (ADR-263)
**Impact**: One or more actions were claimed but never accounted for. The register cannot say whether the effect actually happened — and the register is what makes the executor's word unnecessary.
**SLA Impact**: No direct user-facing outage. The user's "Journal des actions" is incomplete for those entries.

---

## 1. Alert Definition

**Alert Name**: `EffectLedgerClaimedOrphans`

**Prometheus Expression**:
```promql
max(lia_effect_claimed_orphans) > <<<ALERT_CORE_EFFECT_CLAIMED_ORPHANS>>>
```

**Firing Duration**: `for: 15m`

**Labels**: `severity: warning`, `component: effects`, `tier: core`

**Where the number comes from**: Prometheus cannot see database rows. `lia_effect_claimed_orphans` is a DB-backed gauge (pattern `lifetime_metrics.py`): the API counts, at a settings-driven interval, the `agent_effects` rows still in `CLAIMED` past the staleness threshold, and merely transports the figure here.

---

## 2. Symptoms

### What Ops See
- Dashboard **28 - Effect ledger**, panel *Effets restés CLAIMED*, non-zero.
- On the same dashboard, *Effets dans le temps*: the "réclamés" line runs above "aboutis" + "échoués".

### What the user sees
Nothing directly. A confirmed action may have been performed while its entry stays open in the journal.

---

## 3. Possible Causes

### Cause 1: The API was killed mid-turn (High likelihood)
A claim is committed in its own transaction *before* the effect, on purpose — a rollback after the mail left is the very hole the ledger closes. If the process dies between the claim and the close, the row stays `CLAIMED`.

```bash
docker logs lia-api-prod --since 1h 2>&1 | grep -E "effect_ledger_(claim|close)_failed|SIGTERM|Killed"
```

### Cause 2: A tool hangs past every timeout (Medium)
The claim is committed, the provider never answers, the node is cancelled without the close running.

```bash
docker exec lia-postgres-prod psql -U lia -d lia -c "
  SELECT tool_name, mutation_policy, source, claimed_at, now() - claimed_at AS age
  FROM agent_effects WHERE status = 'claimed' ORDER BY claimed_at LIMIT 20;"
```

### Cause 3: The close path itself is failing (Low, but check)
If `lia_effect_ledger_failures_total{operation="close"}` is also rising, the effects DID finish — the ledger simply could not write their ending. That is `EffectLedgerUnavailable` territory.

```promql
sum by (operation) (increase(lia_effect_ledger_failures_total[1h]))
```

---

## 4. Resolution Steps

### Immediate — establish what actually happened
For each orphan, the row names the tool and the authority. Decide from the PROVIDER, never from the row: check the mailbox, the calendar, the third-party service.

```bash
docker exec lia-postgres-prod psql -U lia -d lia -c "
  SELECT id, tool_name, source, execution_mode, claimed_at
  FROM agent_effects WHERE status = 'claimed' AND claimed_at < now() - interval '15 minutes';"
```

### Then — close the books honestly
There is deliberately **no endpoint that writes the ledger**. Correcting a row is a reviewed database operation, and the honest state for "we cannot tell" is `abandoned`, not `succeeded`:

```sql
UPDATE agent_effects
SET status = 'abandoned', error_code = 'orphan_swept', closed_at = now()
WHERE status = 'claimed' AND claimed_at < now() - interval '1 hour';
```

### If the count keeps growing
The cause is not historical: something is killing turns. Check container restarts (`ContainerRestartLoop`), memory (`ContainerMemoryNearLimit`) and the provider timeouts before sweeping again.

---

## 5. Verification

```promql
max(lia_effect_claimed_orphans)          # back to the threshold or below
sum(rate(lia_effect_claims_total[5m]))   # still tracking outcomes
```

The alert resolves on the next gauge refresh, not immediately after the SQL.

---

## 6. Prevention

- A claim is committed before the effect **by design**; the orphan is the price of never losing an effect silently. The lever is turn stability, not the ledger.
- `run_python_tool` and long browser tasks are the usual suspects: their compute timeout must stay below the node timeout, or the close never runs.

---

## 7. Related

- Dashboard: **28 - Effect ledger**
- Alert: `EffectLedgerUnavailable` (the other side of the same question)
- ADR-263 — execution authority chain and effect register
