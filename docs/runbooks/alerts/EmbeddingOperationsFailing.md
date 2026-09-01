# EmbeddingOperationsFailing - Runbook

**Severity**: warning
**Component**: llm
**Impact**: Answers keep flowing and look normal. What is lost is invisible to
the user: a turn's RAG context, its journal context, the memory that should
have been written from it, the indexing that would have made it findable later,
and the router's tool scoring. Two of those are permanent — a memory not
extracted and a message not indexed are not retried later by anything.
**SLA Impact**: No. Nothing fails; the assistant quietly gets less intelligent.

---

## 1. Alert Definition

**Alert Name**: `EmbeddingOperationsFailing`

**Prometheus Expression**:
```promql
(
  sum(increase(embedding_call_outcomes_total{outcome="failed"}[30m]))
  or vector(0)
) >= 3
```

**Firing Duration**: `for: 10m`

**Labels**: `severity: warning`, `component: llm`, `tier: core`

**Why outcomes and not calls.** `embedding_api_calls_total` counts what hit the
provider, retries included — the truth about the provider, and the wrong
denominator here: with retries enabled a single recovered failure is two
attempts, so alerting on calls would fire on incidents that repaired
themselves. This counter collapses an operation into one row, whatever it cost.

**Why `or vector(0)`.** A labelled counter that has never fired exposes no
series at all, and `sum()` over nothing renders "No data" — which an operator
reads as a broken metric rather than a healthy zero.

---

## 2. What Happened Before This Alert Existed

Measured 2026-09-01, on an instance with one to three active users:

| Fact | Value |
|---|---|
| Provider calls since boot | 24 |
| Failures | **11 (46 %)** |
| Cause | `429 RESOURCE_EXHAUSTED`, per-minute quota on the `gemini-embedding` base model |
| Chat turns involved | **0** — every failure came from background schedulers |
| Time it went unnoticed | ~30 minutes, until someone read the logs by hand |

The metric was already on two Grafana dashboards. Nobody was looking at them,
which is the entire difference between visibility and an alert.

**The volume was never the problem.** A steady four calls a minute passed
without a single error. What broke was the *concentration*: interval jobs whose
periods were all multiples of five minutes, all counting from scheduler start,
none carrying jitter — six of them firing inside the same second, each running
an agent, each agent issuing several embeddings.

---

## 3. Diagnosis

Work down this list; the first three answer most cases.

**Is it still happening, or did it clear?**
```promql
sum by (outcome) (increase(embedding_call_outcomes_total[30m]))
```

**Is it the quota, or something else?** The reason is in the retry log line:
```
docker logs lia-api-prod --since 60m | grep retry_attempt | grep embedding
```
`http_429` or `message:quota exceeded` means the quota. `http_500`/`http_503`
means the provider itself. Anything else, read the payload.

**Is it a burst or a sustained rate?** Bursts cluster on the same second:
```
docker logs lia-api-prod --since 60m | grep gemini_embedding_failed \
  | sed -E 's/.*"timestamp": "[^T]+T([0-9:]{5}).*/\1/' | sort | uniq -c
```
A few failures spread over many minutes is a rate problem (raise the quota, or
lower `EMBEDDING_RATE_LIMIT_MAX_CALLS` so the shaper queues more). Several in
one minute is a burst problem (see §4).

**Did something else change?** A new proactive job, a new user, a reindex.
`rag_system_indexation_total` and the scheduler log lines around the burst.

---

## 4. Remediation

**If it is a burst.** Check that interval jobs still carry jitter —
`tests/unit/infrastructure/startup/test_scheduler_jitter.py` fails in CI if one
does not, so a burst with the guard green means a NEW source: a job added with
a written exemption, or work fanning out inside a single job.

**Ask the shaper first — it answers which of the two this is.**

```promql
sum by (outcome) (increase(embedding_shaper_outcomes_total[30m]))
```

- `expired` climbing: the shaper IS holding and calls are going through anyway
  because the wait is bounded. The budget has become too small for the current
  number of users — dial 1 below, then dial 2.
- `unavailable` climbing: Redis is unreachable, so **nothing is being shaped at
  all** and every call goes straight to the provider. Raising the budget would
  change nothing; fix Redis.
- Neither moving, with failures rising: the provider is refusing calls that were
  never concentrated. Go straight to dial 2, and check the provider's status.

**If it is a sustained rate.** Two dials, in this order:
1. `EMBEDDING_RATE_LIMIT_MAX_CALLS` / `EMBEDDING_RATE_LIMIT_WINDOW_SECONDS` —
   lower the ceiling so the shaper queues instead of letting calls fail. Costs
   latency on background work, nothing else.
2. Request a provider quota increase. This is the real fix as users grow; the
   shaper only makes the failure graceful.

**Do not raise `EMBEDDING_RETRY_MAX_ATTEMPTS` as a first move.** The seam sits
on a chat turn's critical path — `user_message_embedding` shares its singleton
with the memory domain — and the budget is guarded by
`TestTheBudgetStaysOffTheCriticalPath` for that reason. More attempts trade a
fast degraded answer for a slow degraded answer.

**Turning the shaper off** (`EMBEDDING_RATE_LIMIT_MAX_CALLS=0`) is safe and
costs no Redis round-trip. It restores the pre-ADR-254 behaviour: calls go
straight to the provider and fail when the quota is hit.

---

## 5. Verification

```promql
sum(increase(embedding_call_outcomes_total{outcome="failed"}[30m])) or vector(0)
```
Back to zero, and staying there across at least one full cycle of the slowest
interval job (60 minutes) — that is the period at which the alignment used to
recur.

---

## 6. Related

- `SystemKnowledgeIndexationFailing` — the same provider, seen from the RAG
  reindex path. Both firing together points at the provider, not at us.
- ADR-254 — why the shaper, the retry and the jitter are three mechanisms with
  three different jobs, and why none of them alone would have been enough.
