# Self-Diagnostics & Answer Resilience — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline execution was
> chosen by the owner; no subagents). Steps use checkbox (`- [ ]`) syntax for tracking.
> **Repo override:** no git actions — every "commit" step of the standard template is replaced by
> a gate checkpoint (`task lint` / targeted pytest); the owner commits.

**Goal:** Give LIA read access to its own telemetry (Prometheus, Loki, Alertmanager), a
deterministic self-check loop with incident memory and grounded LLM diagnosis, admin-only
surfaces (chat tools, REST, settings UI, proactive notifications), and platform-state-aware
answer resilience on the request path.

**Architecture:** New bounded context `apps/api/src/domains/diagnostics/` (briefing pattern — no
LangGraph) + `apps/api/src/infrastructure/telemetry/` clients + thin hooks into existing seams
(planner/ReAct context, response node, catalogue loader, scheduler, Alertmanager template).
Everything behind `DIAGNOSTICS_ENABLED` (default false).

**Tech Stack:** FastAPI, SQLAlchemy 2 async, httpx 0.28 (MockTransport in tests), APScheduler
(leader-elected), Redis, LangGraph state hooks, Next.js 16 + react-i18next (admin UI).

**Spec:** `docs/superpowers/specs/2026-08-27-self-diagnostics-design.md` (argues every decision;
read it first — arbitrations §9, escalation gates §3, verified evidence §4).

## Global Constraints

- Python 3.14, MyPy strict, Black 100, Ruff; every new file < 600 logical SLOC.
- All datetimes `datetime.now(UTC)`; JSONB written by new-dict reassignment only.
- No inline user-visible strings (backend i18n mechanisms; 6 locales frontend, strict parity).
- Tools: `@track_tool_metrics` + settings-driven `@rate_limit`; errors via `ToolErrorModel`.
- Reading telemetry never raises on a caller's path; every enforced bound is published.
- No LLM tokens on the happy path; LLM only on incident open, budget-capped.
- Tests unconditional (no env-key skips); markers such that every test runs in ≥1 CI job.
- Structured logs via structlog; no PII at INFO; counts shown are exact or absent.
- Feature flag OFF ⇒ zero behavioural change anywhere (routers, tools, jobs, webhook absent).
- Gate per lot: `task lint` + `task test:backend:unit:fast` (+ `task test:frontend` for lot 6);
  `task ci:fast` at programme end. Runtime proofs per lot (blocked items batched while the
  Docker Desktop D: file-sharing fix is pending, then executed).

## Delivery order

Lot 0 → 1 → 3 (chat tools) → 2 (incidents+webhook) → 4 (answer resilience) → 5 (diagnosis) →
6 (admin UI + notifications) → docs/ratchets close-out. Tier-1 auto-remediation (spec lot 7) is
**not implemented** (ships empty by spec; an empty registry with no consumer would be dead code —
it waits for the §3 escalation criterion).

---

### Task 0.1 — Settings + constants

**Files:**
- Create: `apps/api/src/core/config/diagnostics.py` (`DiagnosticsSettings`)
- Modify: `apps/api/src/core/config/__init__.py` (MRO), `apps/api/src/core/constants.py`,
  `.env.example`, `.env.prod.example`
- Test: `apps/api/tests/unit/core/config/test_diagnostics_settings.py`

**Interfaces (produces):** `settings.diagnostics_enabled: bool=False`;
`diagnostics_prometheus_url/loki_url/alertmanager_url: str` (defaults `http://prometheus:9090`,
`http://loki:3100`, `http://alertmanager:9093`; empty = source disabled);
`diagnostics_http_timeout_seconds: float=5.0`; `diagnostics_self_check_interval_seconds: int=300`;
`diagnostics_snapshot_retention_days: int=30`; `diagnostics_loki_default_lines: int=200`;
`diagnostics_notification_cooldown_seconds: int=3600`;
`diagnostics_diagnosis_daily_cost_cap_usd: float`; `diagnostics_failure_context_max_entries:
int=10`; `diagnostics_advisor_cache_ttl_seconds: int=30`; per-check thresholds (named
`diagnostics_check_<id>_warn/_crit`); rate-limit pair for tools. Hard caps as constants:
`DIAGNOSTICS_LOKI_MAX_LINES=500`, `DIAGNOSTICS_LOKI_MAX_RANGE_HOURS=24`,
`SCHEDULER_JOB_ID_DIAGNOSTICS_SELF_CHECK`, `DIAGNOSTICS_AGENT_NAME="diagnostics_agent"`,
`REDIS_KEY_DIAGNOSTICS_*` prefixes.

Steps: failing tests (defaults, env override, flag false by default) → implement → gate.

### Task 0.2 — Telemetry clients

**Files:**
- Create: `apps/api/src/infrastructure/telemetry/__init__.py`, `models.py`, `prometheus.py`,
  `loki.py`, `alertmanager.py`
- Test: `apps/api/tests/unit/infrastructure/telemetry/test_prometheus_client.py`,
  `test_loki_client.py`, `test_alertmanager_client.py`

**Interfaces (produces):** Pydantic result models with `status: Literal["ok","unavailable"]`
(never raises): `PromSample(metric: dict[str,str], value: float, ts: datetime)`,
`PromResult(status, samples, error)`, `LokiLine(ts, container, level, payload: dict|None, raw)`,
`LokiResult(status, lines, error)`, `ActiveAlert(fingerprint, name, severity, component,
starts_at, summary, description, runbook)`, `AlertsResult(status, alerts, error)`.
`PrometheusClient(base_url, timeout).instant_query(promql) -> PromResult`;
`LokiClient(...).query_range(logql, start, end, limit) -> LokiResult`;
`AlertmanagerClient(...).active_alerts() -> AlertsResult`. Each guarded by
`get_circuit_breaker("telemetry_<source>")`; per-call `async with httpx.AsyncClient(...)`
(ownership rule: low QPS, no shared client lifecycle). Empty base_url ⇒ immediate
`unavailable("disabled")`.

Test matrix per client (httpx `MockTransport`): 200 nominal parse; 500; timeout
(`httpx.TimeoutException`); malformed JSON; circuit-open short-circuit; disabled URL. Assert **no
exception escapes** in any case.

### Task 0.3 — Named-query catalogue + LogQL builder

**Files:**
- Create: `apps/api/src/domains/diagnostics/__init__.py`, `query_catalogue.py`, `logql.py`
- Test: `apps/api/tests/unit/domains/diagnostics/test_query_catalogue.py`, `test_logql.py`

**Interfaces (produces):** `NamedQuery(key, title, promql_template, params, unit)` with typed
bounded params; `QUERY_CATALOGUE: dict[str, NamedQuery]` (~10 entries: api error rate & p95 from
the existing HTTP metrics, `llm_api_errors_total` by kind, `background_job_errors_total`,
`up{job=...}`, node disk/memory, `circuit_breaker_state`); `render_query(key, **params) -> str`
(out-of-bounds params **clamped** — ADR-184 repair doctrine; unknown key raises `KeyError` to the
caller-side, callers translate); `assert_query_catalogue_completeness()` (placeholders ⊆ declared
params; params bounded; every **LIA-owned** metric name in templates exists in the live
prometheus_client REGISTRY — exporter-owned names live in an allowlist with a written reason).
`build_logql(service: DiagService, level, event, start, end, limit) -> str` — `DiagService`
closed enum mapped to the compose `service` label (env-independent); `event` validated
`^[a-z0-9_.]{1,64}$`; range clamped to 24 h; limit clamped to 500; **no free-text filter**.

### Task 0.4 — Boot assert wiring + runtime proof

**Files:**
- Modify: `apps/api/src/infrastructure/startup/registries.py` (call the catalogue assert next to
  the existing `assert_registry_completeness` call, guarded by the flag),
  `apps/api/src/infrastructure/startup/__init__.py` if exports demand it.
- Test: extend `test_query_catalogue.py` (assert runs at import of startup step with flag on).

Runtime proof (needs D: fix): from `lia-api-dev`, one instant query + one bounded Loki query via
a throwaway `python -c` — record latency; calibrate defaults if measured cost demands it.

### Task 1.1 — Snapshot model + migration + repository

**Files:**
- Create: `apps/api/src/domains/diagnostics/models.py` (`HealthSnapshot`: UUIDMixin,
  `taken_at: Mapped[datetime]`, `overall: Mapped[str]`, `results: Mapped[dict]` JSONB,
  TimestampMixin), `repository.py` (`DiagnosticsRepository(BaseRepository)`), alembic revision
- Modify: `alembic/env.py`, `src/infrastructure/database/registry.py`,
  `src/infrastructure/startup/registries.py::import_domain_models`
- Test: `apps/api/tests/unit/domains/diagnostics/test_repository.py`; migration covered by
  `task db:migrate:replay-check`

**Interfaces (produces):** `save_snapshot(dto) -> HealthSnapshot`;
`latest_snapshot() -> HealthSnapshot|None`; `snapshots_since(dt) -> list`; `prune_snapshots(days)
-> int`.

### Task 1.2 — Check registry + engine

**Files:**
- Create: `apps/api/src/domains/diagnostics/checks.py` (registry + verdict types),
  `engine.py` (`run_self_check() -> HealthSnapshotDTO`)
- Test: `test_checks.py` (registry completeness: unique ids, alertname unique-or-None, every
  `query_key` exists in catalogue, thresholds read from settings — test computes from `settings`,
  never literals), `test_engine.py`

**Interfaces (produces):** `CheckStatus` str-enum `ok|degraded|critical|unknown`;
`CheckResult(check_id, status, value, detail, alertname)`; `HealthSnapshotDTO(taken_at, overall,
results: list[CheckResult])` with `to_results_jsonb()`; `CHECK_REGISTRY: dict[str,
CheckDefinition]` — Prometheus-backed checks (declarative: query_key, params, warn/crit
comparators) + in-process checks (db ping via `get_db_context`, redis ping, circuit-breaker
states, scheduler-tick freshness from Redis). Prometheus unreachable ⇒ those checks `unknown`,
in-process still evaluated; overall = worst(critical > degraded > unknown-capped-at-degraded >
ok).

### Task 1.3 — Scheduler job + subsystem metrics

**Files:**
- Create: `apps/api/src/infrastructure/scheduler/diagnostics_self_check.py`,
  `apps/api/src/infrastructure/observability/metrics_diagnostics.py`
- Modify: `apps/api/src/infrastructure/startup/schedulers.py::init_scheduler` (flag-guarded,
  job id constant, `replace_existing=True`, before `leader_elector.start()`)
- Test: `apps/api/tests/unit/infrastructure/scheduler/test_diagnostics_self_check.py`

Job body: run engine → persist snapshot → prune retention → write scheduler-tick freshness key →
(lot 2 extends: incident open/resolve; lot 5 extends: diagnosis pump). Metrics:
`diagnostics_checks_total{check_id,status}`, `diagnostics_self_check_duration_seconds`,
`diagnostics_incidents_total{source,severity}` (used from lot 2),
`diagnostics_llm_cost_usd_total`, `diagnostics_catalogue_miss_total`.

### Task 3.1 — Shared admin gate (factorisation) + chat tools

**Files:**
- Create: `apps/api/src/domains/agents/tools/admin_gate.py` (extract devops'
  `_check_user_is_admin` → `user_is_superuser(user_id) -> bool`), `diagnostics_tools.py`
- Modify: `apps/api/src/domains/agents/tools/devops_tools.py` (consume the shared gate; behaviour
  identical), conditional import wiring in `agents/tools/__init__.py` (imitate devops)
- Test: `test_admin_gate.py`, `test_diagnostics_tools.py`; devops tool tests still green

**Interfaces (produces):** 4 read-only tools returning `UnifiedToolOutput` (devops shape):
`platform_health_tool()`, `platform_metrics_tool(query_key, window_minutes=15)`,
`platform_logs_tool(service, level="error", event="", minutes=60, limit=<settings default>)`,
`platform_incidents_tool(incident_id="")`. Non-admin ⇒ `UnifiedToolOutput.failure(...,
error_code="FORBIDDEN")` (devops wording). Truncation always states the exact dropped count.

### Task 3.2 — Agent manifest + catalogue registration

**Files:**
- Create: `apps/api/src/domains/agents/diagnostics/catalogue_manifests.py` (mirror the devops
  module layout; bounds **published** in every parameter manifest)
- Modify: `agent_manifest_definitions.py` (`DIAGNOSTICS_AGENT_MANIFEST`),
  `registry/catalogue_loader.py` (flag-gated block, devops pattern)
- Test: `apps/api/tests/unit/domains/agents/registry/` — extend the loader test with flag on/off;
  tool-registry smoke test must pass with flag on.

### Task 2.1 — Incident model + atomic repository

**Files:**
- Modify: `domains/diagnostics/models.py` (+`Incident`), `repository.py`; alembic revision with
  **partial unique index** `uq_incidents_open_correlation` on `(correlation_key) WHERE
  status='open'`
- Test: `test_repository.py` (open-or-touch upsert via `pg_insert ... on_conflict_do_update`
  targeting the partial index; unit with mocked session shape + `@pytest.mark.integration`
  two-actor concurrency against real PG), replay-check

**Interfaces (produces):** `Incident(correlation_key, source: "alert"|"self_check", alertname,
fingerprint, severity, status: "open"|"resolved", title, evidence: JSONB, diagnosis: JSONB|None,
action_log: JSONB, opened_at, last_seen_at, resolved_at, notified_at)`;
`open_or_touch_incident(...) -> tuple[Incident, bool_created]`; `resolve_incident(correlation_key,
source_filter=None)`; `list_incidents(status, page) -> tuple[list[Incident], int_exact]`;
`incidents_needing_diagnosis(limit)`.

### Task 2.2 — Alertmanager webhook endpoint

**Files:**
- Create: `apps/api/src/domains/diagnostics/webhook_router.py`, `schemas.py` (webhook payload +
  admin DTOs)
- Modify: `src/api/v1/routes.py` (flag-gated include)
- Test: `test_webhook_router.py` — 404 flag-off/secret-unset; 403 wrong secret
  (`secrets.compare_digest`); firing→open idempotent by fingerprint; resolved→resolve; malformed
  payload 422; no PII logged.

### Task 2.3 — Self-check ⇄ incidents + admin notification

**Files:**
- Create: `apps/api/src/domains/diagnostics/notifications.py`,
  `apps/api/src/core/i18n_diagnostics.py` (6-language data module)
- Modify: `diagnostics_self_check.py` job (open incidents on critical results, auto-resolve
  self_check-sourced ones on ok; correlation via declared alertname else check_id)
- Test: `test_notifications.py` (superusers-only fan-out via the existing proactive dispatcher
  path, cooldown honoured via `notified_at` + Redis NX, i18n keys exist ×6),
  `test_engine_incidents.py` (one outage ⇒ one incident even when alert + self-check overlap)

### Task 2.4 — Alertmanager template + matrix + compose

**Files:**
- Modify: `infrastructure/observability/alertmanager/alertmanager.yml.template` (+ entrypoint) —
  first child route `continue: true` → receiver `lia-api-webhook` (`webhook_configs`), injected
  only when `ALERTMANAGER_LIA_WEBHOOK_URL` + secret are set (imitate how optional Slack blocks
  are handled today — read `docker-entrypoint.sh` first and copy its optionality mechanism);
  `validate_config.py` matrix extended with the webhook dimension; `docker-compose.dev.yml` /
  `docker-compose.prod.yml`: `docs/runbooks:/app/docs/runbooks:ro` mount (used in lot 5) and the
  webhook env plumbing; `.env.example` / `.env.prod.example`.
- Test: the existing alertmanager validation harness (wherever CI runs it) + runtime proof:
  synthetic alert (`amtool` or curl to Alertmanager API) lands as an incident — **both** target
  schemes proven (prod HTTP `http://api:8000`, dev HTTPS self-signed + `insecure_skip_verify`).

### Task 4.1 — Degradation advisor + mapping registry

**Files:**
- Create: `apps/api/src/domains/diagnostics/advisor.py`, `degradation_map.py`
- Test: `test_advisor.py` (fail-open on any failure → `[]` + debug log; Redis-cached DB part TTL
  from settings; live local breaker merge; mapping boot assert: capability keys are real
  catalogue/tool capabilities, alternatives never invented)

**Interfaces (produces):** `CapabilityDegradation(capability, status, reason, alternative)`;
`async get_active_degradations() -> list[CapabilityDegradation]`; `format_degradations_block(...)
-> str` (empty string when list empty — zero tokens on healthy platform).

### Task 4.2 — Failure-context state key + capture

**Files:**
- Modify: `domains/agents/models.py` (`MessagesState` + declared key `runtime_failures:
  list[dict]`), task orchestrator + ReAct execute-tools error paths (append typed entries:
  `{tool, error_code, capability, ts}` capped at settings max), planner/LLM failure paths
  (`failure_kind` entries)
- Test: `test_runtime_failures_state.py` — key declared (survives checkpoint round-trip test over
  all serialized fields), append bounded, entries are plain JSON dicts.

### Task 4.3 — Plan-time avoidance + response synthesis upgrade + playbooks

**Files:**
- Create: `domains/diagnostics/playbooks.py` (ToolErrorCode/failure_kind → guidance key registry,
  boot-asserted members)
- Modify: planner context builder & ReAct setup (inject `format_degradations_block` only when
  non-empty), `response_node.py` (failures block: what succeeded / what failed typed-why /
  workaround taken-or-available; falls back to today's wording when flag off or advisor empty)
- Test: `test_playbooks.py`, `test_response_failure_synthesis.py` (honesty: no invented claims,
  "blocked" only when nothing executed — ADR-184 guard preserved), planner/react context tests
  (block absent on healthy platform).

### Task 5.1 — Diagnostician LLM slot + prompt

**Files:**
- Modify: `domains/llm_config/constants.py` (`LLM_DEFAULTS["diagnostician"]`), LLM types registry
  (same wiring as `evaluator` — copy its registration sites), `prompt_loader.py` `PromptName`
- Create: `domains/agents/prompts/v1/diagnostician_prompt.txt` (evidence quoted as data; tunables
  as placeholders from settings)
- Test: slot resolvable via `get_llm`-path used by evaluator; prompt loads; placeholders resolve
  from settings (no numerals in prose).

### Task 5.2 — Diagnosis pump (budgeted, resumable)

**Files:**
- Create: `domains/diagnostics/diagnosis.py`
- Modify: `diagnostics_self_check.py` (pump: `incidents_needing_diagnosis` → evidence pack →
  structured output → store; pull-model on the leader job, crash-resumable, never on webhook path)
- Test: `test_diagnosis.py` — budget cap (Redis INCRBYFLOAT UTC-day key) ⇒ `deferred`; runbook
  loader sanitizes alertname `^[A-Za-z0-9]+$` + size cap (path traversal test); evidence pack
  bounded (lines from settings default within the 500 cap); structured output via
  `get_structured_output_with_retry` mocked; cost recorded through the proactive tracking path
  and `diagnostics_llm_cost_usd_total`.

### Task 6.1 — Admin REST

**Files:**
- Create: `domains/diagnostics/router.py`, `service.py` (briefing pattern: split endpoints,
  per-section Redis cache short TTL)
- Modify: `routes.py` (flag-gated)
- Test: `test_admin_router.py` — non-superuser 403 (`require_superuser`), overview/incidents
  (paginated, exact totals), snapshot history, cache behaviour.

**Interfaces (produces):** `GET /admin/diagnostics/overview` (snapshot summary + open incidents +
degradations), `/incidents?status=&page=`, `/incidents/{id}`, `/snapshots?hours=`.

### Task 6.2 — Admin UI (settings section) + i18n + front tests

**Files:**
- Create: `apps/web/src/hooks/useDiagnostics.ts` (useApiQuery), settings section components under
  the ADR-227 master-detail structure (`PlatformHealthSection` + incident detail), tests beside
  them; locale keys in all 6 `apps/web/locales/*/translation.json`
- Modify: settings navigation (superuser-only visibility — same mechanism as existing admin
  sections), optional `NEXT_PUBLIC_GRAFANA_URL` deep links (hidden when unset)
- Skills: invoke `lia-design` + `frontend-design` before building; `lia-i18n` before locale
  edits. Tests: vitest components (status cards, incident list/detail, empty/loading/error
  states, keyboard/aria per repo a11y bar), hook tests, i18n parity via the pre-commit gate.

### Task 6.3 — Programme close-out

- Docs: ADR (next free number), `docs/technical/DIAGNOSTICS_DOMAIN.md`, `docs/INDEX.md`,
  `ADR_INDEX.md`, ARCHITECTURE touch-ups, GETTING_STARTED env vars; then `task
  release:sync-counts` (ADR count surfaces are derived — never hand-edited) and `task lint:docs`
  (+ `lint:docs:preview` for freshly added files).
- Fix in passing (verified stale): `Dockerfile.prod` line 264 comment "API HTTPS" → HTTP.
- Ratchets: measure backend/front coverage; raise floors keeping ≥2 pts margin
  (GUIDE_TESTING.md doctrine); `task ratchet:update` for file-size caps if files shrank.
- Full gates: `task lint`, `task test:backend:unit:coverage`, `task test:frontend:coverage`,
  `task ci:fast`, `task db:migrate:replay-check`, `task test:markers`.
- Runtime proof batch (needs D: fix): §7 spec simulations — kill Redis/Prometheus/Loki one at a
  time; synthetic alert end-to-end; chat tools as admin and as non-admin; advisor fail-open.

## Self-review notes

- Spec coverage: §5 pillars 1-7 → tasks 0.2-0.4 (P1), 1.1-1.3 (P2), 2.1-2.4 (P3), 5.1-5.2 (P4),
  Tier policy (P5) = no lot-7 code + Tier-2 recommended_actions in 5.2, 3.x+6.x (P6), 4.1-4.3
  (P7). §6 security embedded in 2.2/3.1/5.2 tests. §7 verification embedded per task + 6.3.
- Type consistency: result models named once in 0.2 and consumed by 1.2/3.1; `CheckStatus`
  defined 1.2, consumed 2.3/6.1; advisor types defined 4.1, consumed 4.3/6.1.
- No placeholder steps: each task names exact files, signatures, test cases and gates.
