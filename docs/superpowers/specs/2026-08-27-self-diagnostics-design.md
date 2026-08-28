# Self-Diagnostics & Answer Resilience — Design Spec

- **Date**: 2026-08-27
- **Status**: Draft — pending owner review (design approved in session; arbitrations settled)
- **ADR**: to be written as the next ADR number at implementation time (ADR-247 if none lands before)
- **Scope**: new bounded context `domains/diagnostics/` + `infrastructure/telemetry/` + request-path
  resilience hooks + admin surfaces

## 1. Problem

LIA emits enterprise-grade observability (500+ Prometheus metrics, structlog JSON logs shipped to
Loki by Promtail, Tempo traces, a 14-alert core with 33 in-repo runbooks, optional Langfuse) but
**reads none of it**: there is no Prometheus/Loki/Alertmanager client anywhere in `apps/api/src`
(verified by exhaustive grep). The assistant is fully instrumented and fully blind to itself.

Consequences today:

- Invisible errors (background job failures, silently degraded subsystems, the documented
  `/health`-green-but-LangGraph-dead class from `infrastructure/claude-cli/CLAUDE.server.md`) reach
  no one until a human opens Grafana.
- A firing alert reaches email/Slack (when configured) but never LIA itself, and never an
  administrator *inside the product*.
- When a run fails mid-request, the platform's own knowledge of "what is currently broken" cannot
  inform the answer: LIA retries blindly instead of routing around a known outage, and cannot
  explain the failure accurately.

## 2. Goals

1. **Self-awareness**: LIA continuously checks its own golden signals and knows, at any time, which
   of its capabilities are healthy, degraded, or down.
2. **Self-diagnosis**: on incident, LIA assembles evidence (metrics, bounded log excerpts, the
   alert's runbook) and produces a grounded diagnosis with recommended actions.
3. **Answer resilience** (owner requirement, 2026-08-27): as far as possible, LIA always delivers a
   relevant answer, even when something fails mid-run — by understanding the error, correcting it,
   or choosing an acceptable, honestly-stated workaround.
4. **Admin-only visibility**: everything this subsystem produces is invisible to non-admin users and
   available to `is_superuser` users (in chat, in the settings UI, and proactively on critical
   incidents) to help them consolidate the platform.
5. **Graduated autonomy**: observe → diagnose → propose (HITL) → act, with automation only behind
   measured trust and per-action kill switches.

## 3. Non-goals (v1) — escalation-gated extensions

Each excluded item has a **measured escalation criterion**; the architecture keeps the extension
seams (registries) so they plug in without rework.

| Deferred item | Escalation criterion (measured, not felt) |
|---|---|
| Free-form PromQL/LogQL for admins in chat | ≥ 5 real diagnoses in 30 days where the curated catalogue was insufficient (`diagnostics_catalogue_miss_total`; default threshold, settings-driven) |
| Tempo trace reading | Recurring incidents whose stored diagnosis concludes "cause not determinable without a trace" |
| Baseline/z-score anomaly detection | Documented false negatives: incidents the fixed thresholds missed (visible in incident memory) |
| Tier-1+ auto-remediation breadth | Diagnosis accuracy measured over incident memory ≥ threshold (owner arbitration) over a probing period |
| Grafana HTTP API integration | Never planned: Grafana stays the human console; LIA reads the datasources directly. Admin UI deep-links to dashboards. |

## 4. Verified current state (evidence)

All claims below were verified against the working tree on 2026-08-27.

- **Topology**: single Docker network `lia-network` in dev and prod compose; the API container can
  reach `http://prometheus:9090`, `http://loki:3100`, `http://alertmanager:9093` by service name
  (`docker-compose.prod.yml` services + `networks:`; Grafana already queries those exact URLs from
  another container — `infrastructure/observability/grafana/provisioning/datasources/datasources.yml`).
- **Loki** holds logs of every container of the compose project, full JSON payload queryable at read
  time (`{container="lia-api-prod"} | json | event="..."`); only `level` is a label. Loki OOM'd 4×/week
  on the Pi before label-cardinality was purged (`promtail-config.yml` measured commentary +
  `test_promtail_label_cardinality_guard.py`). **Every query this feature issues must be bounded.**
- **Alerting**: 14-alert core (ADR-119) with per-alert `runbook` annotations; 33 runbooks under
  `docs/runbooks/alerts/`. Alertmanager template has email/Slack/PagerDuty receivers only — **no
  webhook to the API**. Receiver combinations are matrix-validated
  (`infrastructure/observability/alertmanager/validate_config.py`).
- **Admin model**: `User.is_superuser`; `require_superuser` helper
  (`core/security/authorization.py`). Admin-gated diagnostic tooling precedent: the DevOps agent
  (`devops_tools.py`) — feature flag `devops_enabled`, catalogue registration gated on the flag,
  admin check at call time **and re-check at draft execution**, unconditional FN-1 draft
  confirmation, `@track_tool_metrics` + `@rate_limit`.
- **In-process signals** already available without Prometheus: LLM failure taxonomy
  (`error_taxonomy.py`, closed set, shared metric label + `token_usage_logs.failure_kind` column),
  `ToolErrorCode` taxonomy, circuit breakers with state gauges
  (`infrastructure/resilience/circuit_breaker.py`), background-job error counters.
- **Request-path resilience today**: same-model retries only (`ModelRetryMiddleware`,
  `ToolRetryMiddleware` in `infrastructure/llm/middleware_config.py`), structured-output retry
  (`structured_output.py::get_structured_output_with_retry`), response-node graceful degradation
  (`partial_error` status, localized fallback messages, raw exceptions never exposed), honesty
  doctrine (ADR-182/184: no invented diagnosis; "blocked" claims require that nothing executed).
  **No model failover and no platform-state-aware routing exist in code** (the ADR-244 model policy
  is a written spec, zero code).
- **Runtime patterns to imitate**: briefing domain (read-only aggregation: `asyncio.gather` with one
  `AsyncSession` per fetcher, per-section Redis cache, split endpoints); `system_settings` typed
  registry (boot completeness assert, reading never raises); APScheduler jobs behind leader election
  (4 uvicorn workers in prod); proactive `NotificationDispatcher` (in-app archive + FCM push +
  Telegram); daily operator report precedent (`demo_daily_report.py`).
- **Deployment constraints**: production is a Raspberry Pi 5 (30 s scrape interval, 15 d/10 GB
  retention); only `docs/knowledge/` is mounted into the API image today — **runbooks are not**
  (compose change required); `httpx==0.28.1` is a runtime dependency.

## 5. Architecture

Seven pillars. A new bounded context `domains/diagnostics/` (no LangGraph — briefing pattern), a new
infrastructure package `infrastructure/telemetry/`, and thin hooks into existing seams.

### Pillar 1 — Telemetry access layer (`infrastructure/telemetry/`)

Async `httpx` clients: `PrometheusClient` (instant + range queries), `LokiClient` (bounded LogQL),
`AlertmanagerClient` (active alerts). Doctrine:

- **Reading never raises** on the caller's path: short timeouts, reuse `get_circuit_breaker` per
  target, unreachable source → typed `SourceUnavailable` result, never an exception.
- Base URLs in a new `core/config/diagnostics.py` settings module (`DiagnosticsSettings`), defaults =
  compose service names; empty string disables that source (self-hosted installs without the
  observability stack keep working unchanged). Feature flag `DIAGNOSTICS_ENABLED` (default `false`).
- **No free-form query language ever reaches a datasource.** Two constrained surfaces:
  - a **named-query catalogue**: parametrized PromQL declared once in a registry with a boot-time
    completeness assert (ADR-085 pattern); parameters are typed and bounded (window ≤ 24 h, step
    floor), bounds **published** in the tool manifests (ADR-184: an enforced bound is a published
    bound);
  - a **LogQL builder**: container (closed enum), level, event name, time range (cap: 24 h), line
    limit (cap: 500). This is what protects Loki on the Pi and closes query injection.

### Pillar 2 — Self-check engine (deterministic; zero LLM tokens)

A registry of deterministic checks (boot completeness assert) executed by a leader-only scheduled
job (default every 5 min, settings-driven): golden signals from Prometheus (error rate, p95 latency,
LLM failure rate by kind, background job errors, disk/memory, dependency `up`) **plus in-process
signals** (circuit-breaker states, scheduler liveness, `/ready` semantics) so the engine still
works — and can say "my own observability tier is down" — when Prometheus is unreachable (this exact
scenario was live in dev during design). Output: a persisted `HealthSnapshot` (verdict per check:
`ok | degraded | critical | unknown`, exact measured values — a shown count is exact or absent).
Thresholds come from settings (never hardcoded in checks), initially aligned with the ADR-119 core
alert thresholds.

### Pillar 3 — Incident memory + Alertmanager webhook

- New tables: `health_snapshots`, `incidents` (open/resolved lifecycle, source: `alert |
  self_check`, alert fingerprint for idempotency, severity, evidence JSONB, diagnosis fields, action
  audit JSONB, UTC timestamps). JSONB writes follow the new-dict reassignment rule.
- New Alertmanager receiver: `webhook_configs` → `POST /internal/diagnostics/alert-webhook` on the
  API, authenticated by a shared secret header (settings; endpoint 404s when the flag is off or the
  secret is unset). Idempotent by fingerprint; resolve events close incidents. The receiver enters
  the existing Alertmanager validation matrix and the entrypoint env plumbing.
- **Webhook target scheme differs by environment (verified 2026-08-27)**: the prod API serves plain
  HTTP on 8000 (`Dockerfile.prod` CMD has no `--ssl-*` flags; the "API HTTPS" comment at line 264 is
  stale — fix it in passing), while the dev API serves HTTPS with a self-signed certificate. The
  receiver URL is therefore environment-templated (`http://api:8000/...` in prod;
  `https://api:8000/...` + `http_config.tls_config.insecure_skip_verify: true` in dev). Lot 2 must
  prove delivery end-to-end in BOTH environments.
- Incidents opened equally by self-check `critical` verdicts (source `self_check`), so the loop does
  not depend on Alertmanager being configured.
- **Cross-source correlation**: a check in the self-check registry may declare the `alertname` it
  mirrors (e.g. redis check ↔ `RedisDown`). Both sources then converge on ONE logical incident via
  the correlation key instead of opening a duplicate — one outage, one incident, one notification.
  A check with no declared alertname correlates only with itself.
- **Notification cooldown** per correlation key (settings-driven): a flapping alert re-opens the
  incident but must not re-push admins on every transition.

### Pillar 4 — Grounded LLM diagnosis (budgeted; incident-triggered only)

On incident open (async, never on the webhook request path): assemble a **bounded** evidence pack —
related named-query results, error-level log lines from the LogQL builder (default 200, within the
builder's 500-line cap, settings-driven), the alert's runbook
(`docs/runbooks/alerts/<alertname>.md`; requires a read-only mount of `docs/runbooks` into the API
container — compose change), current snapshot — then one LLM call producing `diagnosis`,
`probable_cause`, `recommended_actions`, stored on the incident.

- New LLM slot `diagnostician` in `LLM_DEFAULTS` (imitates `evaluator`): cheap model, bounded
  `max_tokens`, admin-overridable via the existing LLM config UI.
- Prompt is a versioned file under `prompts/v1/`, loaded via `load_prompt()`; tunable numbers arrive
  as placeholders from settings, never in prose.
- **Token discipline**: one diagnosis per incident fingerprint; cooldown on alert flapping; daily
  token/cost cap (settings + counter metric + admin kill-switch in `system_settings`); cap exhausted
  → incident still recorded with deterministic evidence, diagnosis marked `deferred`. Costs are
  tracked through the standard tracking path and count within the instance daily budget.
- **Prompt-injection stance**: log excerpts are quoted data, never instructions; diagnosis text is
  only ever shown to admins; **no automated action may be derived from LLM output** — actions (any
  tier) key off typed check verdicts only.

### Pillar 5 — Graduated autonomy

- **Tier 0 (exists)**: circuit breakers, retry middlewares, reasoning/model coercions.
- **Tier 1 (deferred to the final optional lot)**: safe, reversible remediations declared in a
  registry — preconditions, cooldown, per-action `system_settings` kill switch, audit entry on the
  incident, and **post-action effect verification** (absence of exception is not proof). Ships empty
  until the escalation criterion in §3 is met.
- **Tier 2 (v1)**: everything else is *proposed, never executed* — recommended actions surface in
  the admin UI/chat; server-touching actions route through the existing DevOps agent draft flow,
  whose unconditional confirmation stays the doctrine.

### Pillar 6 — Admin surfaces (invisible to non-admins)

- **API**: `GET /admin/diagnostics/{overview,incidents,incidents/{id},snapshot}` — all under
  `require_superuser`, read-only, briefing-style (split endpoints, per-section Redis cache with
  short TTLs), router included behind the feature flag.
- **Chat**: a `diagnostics_agent` catalogue manifest (registered only when the flag is on — devops
  pattern) with four read-only tools, each `@track_tool_metrics` + settings-driven `@rate_limit`,
  each performing the `is_superuser` check at call time (devops `_check_user_is_admin` pattern):
  `platform_health_tool` (latest snapshot + active alerts), `platform_metrics_tool` (named query +
  bounded params), `platform_logs_tool` (LogQL builder params), `platform_incidents_tool`
  (list/detail incl. stored diagnosis). Non-admin callers get the same `FORBIDDEN` failure the
  DevOps tool returns. This is the "LIA, diagnose yourself" experience in both pipeline and ReAct.
- **Settings UI**: "Platform health" admin section (master-detail, ADR-227 pattern): current status,
  incident list with diagnosis and action audit, health timeline, deep links to Grafana dashboards.
  Full i18n (6 locales, strict key parity).
- **Proactive admin notification**: on `critical` incident open, notify all superusers via the
  existing `NotificationDispatcher` (in-app + push + bound channels). **No email** (owner
  arbitration: Alertmanager already emails; duplicating would be noise).
- **Self-observation**: the subsystem exports its own metrics (`diagnostics_checks_total`,
  `diagnostics_incidents_total`, `diagnostics_llm_cost_usd_total`,
  `diagnostics_catalogue_miss_total`, action counters). No PII at INFO anywhere in the subsystem.

### Pillar 7 — Answer resilience on the request path (owner requirement)

Goal: a failing dependency mid-run should still yield a relevant, honest answer — corrected when
possible, worked around when not, accurately explained always. Zero added LLM tokens and no new
blocking I/O on the happy path.

1. **Degradation advisor** (`domains/diagnostics/advisor.py`): `get_active_degradations()` — a
   ~O(1) read (Redis-cached, short TTL, fail-open) merging open incidents, circuit-breaker states,
   and the latest snapshot verdicts into a small typed structure: *capability → status + suggested
   alternative* (e.g. `web_search: degraded (brave circuit open) → alternative: perplexity`;
   `llm_provider:openai: down → alternative per model policy`). Alternatives come from a declared
   mapping (registry with boot assert), never invented. If the advisor itself fails or the flag is
   off, callers behave exactly as today (fail-open by construction).
2. **Plan-time avoidance**: planner context and ReAct setup inject the current degradations (a
   compact, published block — same mechanism as other catalogue constraints) so plans route around
   known-down capabilities *before* burning a failing call, instead of discovering the outage by
   timeout. The block is injected **only when non-empty**: a healthy platform adds zero prompt
   tokens. Suggested alternatives are platform-level; whether the alternative is available to *this
   user* (connector configured, capability enabled) stays the existing catalogue's authority — the
   advisor never overrides per-user availability.
3. **Failure-context enrichment**: when a tool call or LLM call fails during a run, the typed error
   (`ToolErrorCode` / `failure_kind`) plus the advisor's matching entry are recorded under a new,
   **declared** `MessagesState` key (undeclared keys are silently dropped — known trap). The
   response node then synthesizes: what succeeded, what failed and *why* (typed, not guessed),
   which workaround was taken or is available, and what the user can do — replacing today's generic
   fallback wording. ADR-182/184 honesty holds: no invented diagnosis, no "blocked" claim unless
   nothing executed; a mid-run *user-facing* explanation derives from typed classifications only,
   never from raw log text.
4. **Recovery playbooks (deterministic)**: a small mapping from error class to recovery behaviour,
   applied where retries already live (middleware/tool layers): `rate_limit` → honor backoff, defer
   or switch alternative; `authentication` (connector) → stop retrying, tell the user which
   connector to reconnect; `timeout` on non-essential enrichment → skip and state it; provider
   `api_error`/`model_not_found` → model failover **delegated to the ADR-244 model policy when it
   lands** (this spec does not re-derive its thresholds; until then the entry is "retry per
   middleware, then degrade honestly").

Edge cases: advisor unavailable → today's behaviour; stale incidents → TTL + resolve lifecycle;
circuit-breaker states are per-worker in-memory and that is *correct* here — the breaker that
matters is the one of the worker serving this run (incidents/snapshots stay shared via DB/Redis);
the failure-context state key is bounded (last N typed entries per run, N from settings) so
checkpoints cannot bloat; SSE latency budget for the advisor call ≈ single Redis GET, enforced by
timeout.

## 6. Security & privacy

- All read surfaces: `require_superuser` (routes) or in-tool admin check (chat tools; re-check at
  execution for anything draft-based). Feature flag off → routers, tools, scheduler jobs, webhook
  all absent. The public demonstrator never enables the flag.
- Webhook: shared-secret header, constant-time compare, 404 when unconfigured; no user data crosses
  it (alert labels/annotations only).
- Logs surfaced to admins: bounded excerpts, admin-only rendering; INFO-level logs carry no PII by
  standing policy; excerpts are treated as untrusted data in any LLM prompt.
- New auth-free internal route obeys the route-shape security review (it is not an auth route; it
  must not match `…/auth/<provider>/<login|callback>`).
- No secrets in diagnostics output: evidence packs carry metric names/values, event names, error
  codes — never env values, tokens, or connection strings.

## 7. Testing & verification strategy

- **Unit (unconditional, mocked)**: httpx `MockTransport` for the three clients (timeout, 5xx,
  malformed JSON, circuit-open paths); LogQL builder bound enforcement (range/limit caps, enum
  container); named-query registry completeness assert; check engine verdicts on synthetic inputs
  (ok/degraded/critical/unknown, Prometheus-down fallback to in-process signals); webhook
  idempotency by fingerprint + secret rejection; advisor fail-open; response-node synthesis with
  failure context (typed wording, no raw exception leakage); state round-trip test for every new
  `MessagesState` key (serialization pair rule). No test may skip on a missing env key (ADR-155
  guard applies).
- **Integration (marked)**: incidents/snapshots persistence transitions (open→resolve, concurrent
  webhook + self-check on the same fingerprint), migration `db:migrate:replay-check`.
- **Config matrix**: Alertmanager template with/without the new webhook receiver via the existing
  `validate_config.py` matrix.
- **Runtime proofs (per standing feedback, each lot ends with one)**: lot 0 proves live
  reachability and one bounded Loki query **from inside the dev API container**, and measures query
  latency to calibrate default bounds; blocked-at-design-time by the Docker Desktop D:-mount trap —
  first task once fixed.
- **Simulations before "done"**: kill Redis/Prometheus/Loki one at a time in dev and verify the
  subsystem degrades as designed (no exception on any request path, snapshot says `unknown` for
  affected checks, advisor fail-open); fire a synthetic alert through Alertmanager to the webhook;
  open a synthetic incident and verify admin notification fan-out and the chat tools.
- All standard gates per lot: `task lint`, `task test:backend:unit:fast`, `task ci:fast` before any
  handoff; frontend lots add `task test:frontend` (+ coverage thresholds).

## 8. Delivery plan (lots)

| Lot | Content | Depends on |
|---|---|---|
| 0 | ADR + `DiagnosticsSettings` + telemetry clients + named-query catalogue + LogQL builder + **runtime proofs & bound calibration** | D: mount fixed |
| 1 | Self-check registry + engine + `health_snapshots` + leader job + subsystem metrics | 0 |
| 2 | `incidents` model + lifecycle + Alertmanager webhook receiver (+ config matrix) | 1 |
| 3 | Admin chat agent + 4 read-only tools | 1 (richer once 2 and 5 land) |
| 4 | Request-path answer resilience: advisor + plan-time avoidance + failure-context enrichment + response synthesis upgrade + deterministic playbooks | 2 |
| 5 | Grounded LLM diagnosis (slot, prompt, runbook mount, budget caps) | 2 |
| 6 | Admin settings UI + proactive superuser notifications (i18n ×6) | 2 |
| 7 (opt.) | Tier-1 safe auto-remediation registry behind kill switches | 5 + §3 criterion |

Recommended order: **0 → 1 → 3 → 2 → 4 → 5 → 6 → (7)** — early chat value after three lots, then
incident memory, then the owner-priority answer-resilience pillar, then diagnosis and UI. Every lot
is independently shippable behind the flag; no existing path changes except: the Alertmanager
receiver (matrix-validated), two read-only mounts, declared `MessagesState` keys, and the
response-node synthesis upgrade (behind the flag, falling back to today's wording).

## 9. Settled arbitrations (owner, 2026-08-27)

1. Scope = full programme (B), sequenced so the chat-tools value (A) lands early; C items gated by
   the §3 escalation criteria.
2. Tier-1 auto-remediation deferred to the optional final lot; "observe, diagnose, propose" first.
3. Curated named queries + constrained LogQL builder only; free-form query languages are
   escalation-gated.
4. Critical-incident admin notification: in-app + push (+ bound channels); no email duplication.
5. Answer resilience on the request path is a first-class goal (Pillar 7, lot 4).
