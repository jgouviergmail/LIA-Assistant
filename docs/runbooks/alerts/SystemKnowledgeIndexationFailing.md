# SystemKnowledgeIndexationFailing - Runbook

**Severity**: warning
**Component**: rag
**Impact**: The assistant keeps answering questions about itself, but from the
previously indexed corpus. Anything changed in `docs/knowledge/*.md` since the
last successful indexation is invisible to users. No outage, no empty answers —
the failure path never deletes the corpus it failed to replace.
**SLA Impact**: No.

---

## 1. Alert Definition

**Alert Name**: `SystemKnowledgeIndexationFailing`

**Prometheus Expression**:
```promql
sum by (space_name) (increase(rag_system_indexation_total{status="error"}[6h])) >= 2
```

**Firing Duration**: `for: 15m`

**Labels**: `severity: warning`, `component: rag`, `tier: core`

Why two failures and not one: a single transient rejection is retried in place
(bounded by `RAG_SPACES_SYSTEM_INDEX_EMBED_MAX_ATTEMPTS` and
`RAG_SPACES_SYSTEM_INDEX_EMBED_RETRY_BUDGET_SECONDS`) and, failing that, retried
by the next boot. Two failures in six hours means the cause is not passing.

Why it is in the core tier: this indexation failed on **69 boots across 14 days**
(measured 2026-07-27) without anyone noticing. The only traces were a WARNING
that the startup step swallowed and a `database_session_error` filed under the
database layer for a failure that never touched it.

---

## 2. Symptoms

### What Ops See
- `rag_system_indexation_total{status="error"}` climbing, `status="success"` flat.
- Panel "System indexation" on the Grafana dashboard `18-rag-spaces`.

### Logs
```bash
docker logs lia-api-prod 2>&1 | grep -E 'system_indexer_failed|system_rag_startup_failed'
```

`system_indexer_failed` carries the reason. `system_rag_startup_failed` confirms
the boot was not blocked.

---

## 3. Possible Causes

### Cause 1: Embedding provider quota exhausted (High likelihood)
The historical cause. Look for `RESOURCE_EXHAUSTED` / HTTP 429:
```bash
docker logs lia-api-prod 2>&1 | grep -c RESOURCE_EXHAUSTED
docker logs lia-api-prod 2>&1 | grep 'system_indexer_embed_retry'
```
The quota is per Google Cloud project and is **shared with every other client
using the same API key**, development environments included. Check whether
anything else is embedding against `GOOGLE_GEMINI_API_KEY`.

Two related consumers used to make the boot itself the culprit, both now fixed —
if either regresses, this alert is how you will find out:
- the tool-embeddings cache must live on the `tool_cache_data` volume, otherwise
  every worker re-embeds the whole catalogue on every deploy;
- only one worker may index (`FOR UPDATE SKIP LOCKED` on the space row).

```bash
# Both must be true on a healthy boot.
docker logs lia-api-prod 2>&1 | grep -c semantic_tool_selector_cache_hit   # >= 1
docker logs lia-api-prod 2>&1 | grep -c system_indexer_claim_declined      # workers - 1
```

### Cause 2: Knowledge directory missing from the container (Medium)
```bash
docker exec lia-api-prod ls /app/docs/knowledge | head
docker logs lia-api-prod 2>&1 | grep system_indexer_knowledge_dir_missing
```
`docs/knowledge` is a read-only bind mount declared in `docker-compose.prod.yml`.
A missing mount degrades to this alert instead of an empty corpus.

### Cause 3: Provider credentials rejected (Low)
An HTTP 401/403 is **not** retried — retrying a rejected key only burns the
budget. `system_indexer_failed` names the status.

---

## 4. Resolution

1. Fix the cause above.
2. Re-index without waiting for a deploy — the admin endpoint runs the same code
   path (superuser session required):
   ```
   POST /api/v1/rag-spaces/admin/system-spaces/lia-faq/reindex
   ```
   It is also the "Reindex" button of Settings → Admin → RAG Spaces. A **409**
   means another worker holds the claim: retry once it commits, the indexation
   did not run. Restarting the API works too — the indexation runs on every boot
   and is idempotent.
3. Confirm:
   ```bash
   docker logs lia-api-prod 2>&1 | grep system_rag_startup_indexed
   ```

Nothing needs cleaning up by hand. A corpus that diverges from the parsed files —
in either direction — is detected at the next boot
(`system_indexer_corpus_diverged`) and rebuilt, even when the content hash
matches.

---

## 5. Escalation

None. This alert never warrants waking someone: the previous corpus keeps
serving. Treat it during working hours.
