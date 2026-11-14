# RagSourceRecoveryLoop - Runbook

**Severity**: Warning
**Component**: RAG spaces (linked Drive folders and Gmail labels)
**Impact**: A linked source is synchronised in full again and again. Nothing is lost, but each pass re-reads the whole folder or label from the provider, competes with the person's own tools for the connector's rate limit, and keeps the source locked while it runs
**SLA Impact**: No — indexing still converges; the cost is provider calls and delay

---

## 📊 Alert Definition

**Alert Name**: `RagSourceRecoveryLoop` (core tier, `alerts-core.yml` — ADR-119)

**Prometheus Expression**:
```promql
sum by (job_type) (
  increase(rag_jobs_recovered_total{job_type=~"sync|mail_sync", outcome="requeued"}[6h])
) >= 5
```

`for: 30m`. `job_type="sync"` is a Drive folder, `mail_sync` a Gmail label.

A source being synchronised holds a lease (`sync_status = 'syncing'`,
`lease_expires_at`, renewed by a heartbeat). The reaper
(`domains/rag_spaces/reapers.py`, every `RAG_JOB_REAPER_INTERVAL_SECONDS`) re-drives a
source whose lease expired while it was still `syncing`: that is how a sync interrupted
by a crash or a deployment completes. One recovery is therefore normal. Five in six
hours is a lease nobody returns.

Documents (`job_type="document"`) are left out on purpose: their retries are bounded by
`RAG_JOB_MAX_ATTEMPTS`, and a burst of failed embeddings legitimately requeues many at
once.

**Why this alert exists**: from 2026-09-04 to 2026-11-10 every Gmail push left its label
sources `syncing`. The push pass took the lease with one SQL statement, then released it
through an object loaded BEFORE the lease: the release only wrote the columns that
differed from that stale state, so the status and the lease stayed. Five minutes later
the reaper logged « recovered from stuck sync lease (worker crash) » and replayed a full
label sync. Measured in production: 236 recoveries and 127,585 thread reads in 24
hours. Nothing was red.

**Labels**:
- `severity`: warning
- `component`: rag
- `tier`: core
- `job_type`: `sync` or `mail_sync`

---

## 🔍 Symptoms

- API logs: `rag_mail_sync_jobs_recovered` or `rag_sync_jobs_recovered` every few
  minutes, `rag_mail_sync_complete` in step.
- `rate_limit_exceeded_retrying` from the connector client, and
  `rag_mail_sync_thread_error` carrying `RateLimitError`.
- `rag_mail_push_index_total{outcome="locked"}` grows: pushes find the source busy.

---

## 🎯 Diagnosis

```sql
-- Read-only. A healthy source is 'completed' with no lease between two syncs.
SELECT left(id::text, 8) AS source, sync_status, attempts,
       lease_expires_at, heartbeat_at, last_sync_at
FROM rag_mail_sources ORDER BY created_at;   -- rag_drive_sources for a folder
```

Sample it every 30 seconds for ten minutes:

| What the row shows | Meaning |
|---|---|
| `syncing`, `attempts = 1`, the lease NOT renewed, `last_sync_at` just written | A pass finished and did not return its lease — a release that does not land |
| `syncing`, the lease renewed every minute, for a long time | One sync that is genuinely long (a large folder or label), not a loop |
| `syncing`, `attempts` climbing to `RAG_JOB_MAX_ATTEMPTS`, then `error` | The sync crashes each time; read `rag_mail_sync_fatal` / `rag_sync_dead_lettered` |

```promql
# How often, and which kind
sum by (job_type) (increase(rag_jobs_recovered_total{outcome="requeued"}[1h]))
# What each pass re-reads (skipped = read and found unchanged)
sum by (result) (increase(rag_mail_sync_threads_total[1h]))
```

---

## 🛠️ Resolution

1. **A release that does not land** is a code defect: whoever takes the lease by SQL must
   read the row again before releasing it through the ORM
   (`mail_sync._serve_source` does; `drive_push._apply` loads the source after the lease).
   `tests/integration/domains/rag_spaces/test_mail_push_lock_release.py` holds the push
   path on real PostgreSQL.
2. **A sync that crashes each time** dead-letters to `error` by itself after
   `RAG_JOB_MAX_ATTEMPTS`; the person re-links or re-syncs from the space's page once the
   cause in the logs is fixed.

---

## 📚 Related

- [EmbeddingOperationsFailing](./EmbeddingOperationsFailing.md) — the embedding side of an indexing burst
- [PushWakeSweepStalled](./PushWakeSweepStalled.md) — the sweep that serves Gmail pushes
- [ADR-262](../../architecture/ADR-262-Opt-In-Mail-Label-RAG-Source.md) — the label source
