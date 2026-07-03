# ADR-097: Concurrency, GDPR Purge & Skill Sandbox from the Wave-4 Audit

**Status**: ✅ IMPLEMENTED (2026-07-04)
**Author**: Claude Code (Fable 5)
**Related**: [ADR-093](ADR-093-Security-Hardening-Proxy-XSS.md) (proxy/XSS hardening), [ADR-094](ADR-094-Remove-Dead-Per-Node-Windowing-Helpers.md) (wave-1), [ADR-095](ADR-095-Systemic-Guards-Wave2-Audit.md) (wave-2 systemic guards), [ADR-096](ADR-096-Performance-Boundary-Hardening-Wave3-Audit.md) (wave-3 boundaries), [ADR-085](ADR_INDEX.md) (boot-time asserts), [BRIEFING_DOMAIN.md](../technical/BRIEFING_DOMAIN.md) (session-per-fetcher pattern)

## Context

Wave 4 targets the audit's **most insidious** class: defects that surface only
under **concurrency** or in **account-lifecycle** scenarios — invisible to unit
tests and to static analysis, visible only to a reader tracing runtime
behaviour. Each correction touches a *shared* path (planner, aggregators,
message middleware, agent wrapper, skill sandbox), so the reinforced protocol
required, on top of the standard red-first loop, a **concurrency or integration
test reproducing the defect before the fix**. "No reproduction = no fix."

The six items:

1. **A5a — shared `AsyncSession` under `asyncio.gather`.** SQLAlchemy forbids
   concurrent operations on one session. `HealthMetricsService.compute_overview`
   gathered one summary per health kind on the service's shared session;
   `heartbeat.ContextAggregator.aggregate` gathered 10 fetchers, 8 of them on
   `self._db` — and `return_exceptions=True` converted the resulting
   `InvalidRequestError`s into silent `failed_sources`, so each heartbeat lost
   context sources non-deterministically.
2. **A5b — GDPR purge gaps.** `AccountDeletionService` purged 20+ tables but not
   `health_samples` / `health_metric_tokens`; the user row is soft-deleted so FK
   CASCADE never fires → physiological data (the most sensitive GDPR category)
   survived deletion, and a deleted user's iPhone kept ingesting
   (`ingest _authenticate` only checked `revoked_at`).
   `last_known_location_encrypted` was not scrubbed either.
3. **B6 — per-request state on singletons (cross-user leak).**
   `SmartPlannerService` (a singleton) stored `journal_context` on `self` and
   read it back via `getattr` after await points → user B's private journal
   could land in user A's planner prompt. `ConnectorTool.runtime` (singleton
   tool instances) leaked timezone/language between users; `SmartCatalogueService._metrics`
   leaked filtering metrics across concurrent requests.
4. **N-179b — orphan tool messages.** `MessageHistoryMiddleware` selected the
   "last 5 ToolMessages" and trimmed by tokens *per message*, detaching a
   ToolMessage from the AIMessage carrying its `tool_call`s → OpenAI/Anthropic
   400 ("must be a response to a preceding message with 'tool_calls'").
5. **N-183 — frozen datetime + quadratic token counting.**
   `build_generic_agent` rendered `{current_datetime}` once at BUILD time while
   agents are cached for the process lifetime (stale "now" after uptime); the
   agent wrapper re-recorded the `usage_metadata` of *every* AIMessage in the
   returned full-state on *every* invocation (quadratic token accounting +
   inflated Prometheus tool counters).
6. **A1/A2 — skill sandbox vs the Docker socket.** `run_skill_script` is open to
   every user and `SkillScriptExecutor` ran scripts as **root** with the
   `/var/run/docker.sock` mount visible → a script could control every container
   on the host. There was no CPU/RAM/NPROC/FSIZE ceiling either.

## Decision

### A5a — one session per gathered fetcher (imitate `briefing/`)

`compute_overview` is now a **sequential loop** (two indexed queries gain
nothing from parallelism); `ContextAggregator` gives **each gathered fetcher its
own `get_db_context()` session** via a `_with_fresh_session` helper, exactly the
pattern `briefing/fetchers.py` documents as CRITICAL. `self._db` survives only
for the sequential journal second-pass. **Reproduction** (real Postgres, a
pooled engine so a fresh session's connection-provisioning genuinely races):
before, `test_heartbeat_aggregator_loses_no_source_to_session_concurrency`
lost 7 sources and `compute_overview` raised `InvalidRequestError`; after, 0
lost sources.

### A5b — purge health + scrub location + defense-in-depth auth

`health_samples` and `health_metric_tokens` join Group 2 of the purge (deleting
the tokens also cuts off any device still pushing samples);
`last_known_location_encrypted` / `_updated_at` are scrubbed in
`_mark_user_deleted` alongside `home_location`. As **defense in depth**,
`get_active_token_by_hash` now joins `User` and requires `is_active AND NOT
deleted` — a token of a deactivated/deleted owner no longer authenticates even
if some future flow forgets to revoke it. **Reproduction**: after account
deletion, 0 health/location rows remain and an ingestion write is refused (401);
7 integration tests.

### B6 — thread per-request state, not instance state

`journal_context` is now an **explicit parameter** end-to-end (the planner, both
LLM strategies, all three bypass strategies, `_build_prompt`), and the
`_current_journal_context` attribute is gone. `ConnectorTool.runtime` became a
**task-local ContextVar** exposed through a property (bound/reset by `execute()`
in a `finally`); the mixin no longer shadows it. `SmartCatalogueService._metrics`
became a **ContextVar** (same approach as the already-migrated `panic_mode_used`).
**Reproduction**: two interleaved `plan()`/`execute()` calls (a gate parks user A
on an await while user B completes) proved the leak, then proved isolation.

### N-179b — atomic tool-call units

`before_model` now groups non-system messages into **atomic units** — an
AIMessage with `tool_calls` plus its ToolMessages — and both the recency
selection and the token trim operate on whole units. A final
`enforce_tool_message_pairing` net (new, in `message_filters.py`) guarantees the
provider contract in **both** directions (orphan tool result *and* unanswered
tool call) even for already-corrupted histories. **Reproduction**: a
45-combination sweep of `(keep_last_n × max_tokens)` asserts a provider-valid
sequence for every pressure.

### N-183 — per-invocation datetime + index-diff counting

A new `DynamicDatetimeMiddleware` re-renders `{current_datetime}` on **every**
model call via `wrap_model_call` (the placeholder stays in the cached prompt).
The agent wrapper records the index of the incoming messages and only accounts
**messages posterior to entry** (`result.messages[input_count:]`) — linear token
accounting again. **Opportunistic fix**: `ContextEditingMiddleware` fell back to
a **dict-based edit** (the removed `TruncateToolResult` API) whose objects have
no `.apply()` method — crashing *every* model call of *every* built agent
(masked by the retry middleware into "Model call failed after 4 attempts"). Now
uses the real `ClearToolUsesEdit` (settings-driven trigger/keep).

### A1/A2 — privilege drop (not mount-namespace mask)

The audit proposed masking the socket by mount namespace; **this is impossible**
in the container (no `CAP_SYS_ADMIN` — `unshare -rm` returns EPERM). We chose the
strictly-better **privilege drop**: when the API runs as root,
`SkillScriptExecutor` drops each skill subprocess to an unprivileged uid
(`setgroups([gid])` → `setgid` → `setuid`, groups cleared **first** so the
retained `docker`/`root` group cannot keep socket access) via `preexec_fn`. The
root-owned `srw-rw---- root root` socket then becomes unreachable — and
`RLIMIT_NPROC` (bypassed for uid 0) becomes effective. The same `preexec_fn`
applies **RLIMIT_AS/NPROC/FSIZE/CPU**, bounding fork bombs / memory / disk / CPU.
The temp cwd is chmod-777 so dropped scripts still write output. **DevOps is
untouched**: the admin Claude CLI runs on a separate code path, still as root,
still with socket access. **Reproduction** (in-container, running as root): a
non-dropped script opens the socket and lists containers; a dropped script is
denied both. Plus rlimit tests (CPU spin killed, memory/fsize capped, fork storm
contained; NPROC test skipped under uid 0 with a documented rationale — it
covers the non-root hardening target).

**Deviation recorded (per protocol).** We did **not** remove `group_add: docker`
+ the socket mount from the API compose service, nor add a filtering
socket-proxy. The privilege drop already denies skill scripts the socket at the
process level with **zero DevOps-regression risk and no deploy**; the compose
rewiring is deploy-gated (the socket-proxy DevOps path cannot be runtime-validated
without a prod deploy) and is recorded as a recommended defense-in-depth
follow-up, not applied blind.

### Opportunistic systemic fix — mypy platform alignment

The POSIX-only sandbox (`resource`, `os.setuid/setgroups`) exposed the recurring
host/Docker mypy divergence (Dev Container Pitfall #2). `pyproject.toml` now sets
`platform = "linux"` for mypy — type-checking against the deployment target, so
the host pre-commit hook and the Linux CI runner resolve POSIX APIs identically.
Verified: 0 errors across all 865 source files.

## Consequences

- **New `.env` keys** (all opt-outable / tunable, defaults preserve behaviour):
  `SKILLS_SCRIPT_MAX_MEMORY_MB`, `SKILLS_SCRIPT_MAX_PROCESSES`,
  `SKILLS_SCRIPT_MAX_FILE_SIZE_MB`, `SKILLS_SCRIPT_MAX_CPU_SECONDS`,
  `SKILLS_SCRIPT_DROP_PRIVILEGES`, `SKILLS_SCRIPT_UNPRIVILEGED_UID/GID`,
  `CONTEXT_EDIT_CLEAR_TRIGGER_TOKENS`, `CONTEXT_EDIT_CLEAR_KEEP_TOOL_RESULTS`
  (the last two replace the dead `CONTEXT_EDIT_MAX_TOOL_RESULT_TOKENS`).
- **No DB schema change, no migration.**
- **New guards**: session-per-fetcher (heartbeat), GDPR health purge + owner-state
  auth, ContextVar isolation for planner/runtime/metrics, atomic tool-call units,
  per-invocation datetime middleware, index-diff token accounting, rlimit +
  privilege-drop skill sandbox. All red-first, reproduced before fix.
- **Test infrastructure repaired** (unblocks the whole integration suite): a
  loop-bound Redis singleton crashed later tests with "Event loop is closed"
  (autouse reset added); `.env.test` now pins `SESSION_COOKIE_SECURE=false` (the
  httpx test client never resends a `Secure` cookie → session endpoints 401'd);
  five pre-existing rotted unit tests fixed (stale constant/model assertions,
  a raw-DBAPI-exception 500 in `/health`, a cookie-secure default).

Completes waves 1–3 ([ADR-094](ADR-094-Remove-Dead-Per-Node-Windowing-Helpers.md),
[ADR-095](ADR-095-Systemic-Guards-Wave2-Audit.md),
[ADR-096](ADR-096-Performance-Boundary-Hardening-Wave3-Audit.md)) on the
concurrency & lifecycle axis the earlier waves deferred.
