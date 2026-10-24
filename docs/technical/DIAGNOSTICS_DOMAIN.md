# Diagnostics domain — self-diagnostics & answer resilience

> ADR: [ADR-247](../architecture/ADR-247-Self-Diagnostics-And-Answer-Resilience.md) ·
> Spec: `docs/superpowers/specs/2026-08-27-self-diagnostics-design.md` ·
> Feature flag: `DIAGNOSTICS_ENABLED` (default false — flag off, nothing below exists at runtime).

LIA reads its **own** telemetry: Prometheus, Loki and Alertmanager (the compose
services on `lia-network`), a deterministic self-check loop, an incident memory
with runbook-grounded LLM diagnoses, admin-only surfaces, and a request-path
advisor so a known outage shapes the answer instead of a timeout.

## Module map

| Module | Responsibility |
|---|---|
| `infrastructure/telemetry/{prometheus,loki,alertmanager}.py` | HTTP read clients. **Never raise** on a transport, status or payload fault: each is a typed `unavailable` result; circuit breaker per source; empty URL = source disabled. A malformed URL is one of those faults too: `httpx.InvalidURL` is no `httpx.HTTPError`, so the shared helper (`_base.py`) names it apart (`invalid_url`) — before, a mistyped port escaped it and ended the whole self-check tick. `AlertmanagerClient.status` reads when the running instance started (`/api/v2/status` → `uptime`, nothing else of that payload — it also carries the configuration and its credentials). |
| `domains/diagnostics/query_catalogue.py` | The ONLY producer of PromQL: named queries, bounded params (published in manifests), boot completeness assert. |
| `domains/diagnostics/logql.py` | The ONLY producer of LogQL: closed service enum, closed levels, strict event pattern, range/line hard caps (constants). |
| `domains/diagnostics/checks.py` + `engine.py` | Declarative check registry (Prometheus-backed + in-process probes) → `HealthSnapshotDTO`. Prometheus down ⇒ those checks `unknown`, probes still run; `unknown` caps overall at `degraded`. `evidence_for` builds the pack an incident carries: the value **with** its unit, its verdict and the two thresholds it was compared against — a number with no threshold beside it cannot be judged, and the diagnoses said exactly that. Deliberately no log excerpt: that is the chat tool's job, and a scheduler tick must not start depending on Loki. |
| `domains/diagnostics/models.py` + `repository.py` | `health_snapshots`, `incidents`. One OPEN incident per correlation key via a partial unique index; open-or-touch is a single `ON CONFLICT` upsert (`xmax = 0` detects creation) whose conflict target repeats the index predicate LITERALLY (`INCIDENT_OPEN_SQL`): bound as a parameter, PostgreSQL cannot infer the arbiter index once a reused prepared statement is planned generically, and the touch failed intermittently. |
| `domains/diagnostics/incident_sync.py` | Snapshot verdicts → incidents. Critical opens/touches; OK auto-resolves **self_check-sourced only** (the alert's resolved event owns alert-sourced ones); a check may declare the `alertname` it mirrors so both sources share one identity. **A lost « resolved » delivery is reconciled from the same authority** (`reconcile_alert_incidents`, 2026-10-18 — one incident had stayed open 28 days): an alert-sourced incident Alertmanager no longer holds as firing (silenced and inhibited alerts count as firing) AND not re-delivered for `DIAGNOSTICS_INCIDENT_SILENCE_CLOSE_SECONDS` is closed in one statement with an `auto_resolved` audit entry; Alertmanager unreadable closes nothing, and neither does one that started less than `ALERTMANAGER_WARMUP_SECONDS` ago: it keeps its alerts in memory, so until Prometheus re-sends what is firing its listing is empty — and a silenced alert, which no webhook re-delivers, would have had its incident closed with nothing to reopen it. The start instant is read after the listing, so a restart between the two reads defers the pass too. The default silence is held to at least twice the webhook route's `repeat_interval` and the warm-up to several Prometheus re-send periods by `test_incident_reconciliation.py`, and the statement is proven on PostgreSQL (`tests/integration/domains/diagnostics/`). |
| `domains/diagnostics/webhook_router.py` | `POST /api/v1/internal/diagnostics/alert-webhook` — Bearer shared secret; 404 while the flag is off or the secret unset; firing→open, resolved→resolve; nameless alerts skipped. An opened incident is committed BEFORE its notification, like the self-check's: the incident is the record and the notification a best-effort notice, and a COMMIT on a transaction a failed notification aborted rolls back in silence. |
| `domains/diagnostics/notifications.py` | Superuser fan-out (in-app + push + channels; **no email**), cooldown = one atomic `SET NX EX`, fail-OPEN. An admin counts as notified only when a durable channel reached them (archive, push or external channel — an SSE event alone does not count, audit AC-003), and `notified_at` follows that count. Each admin is notified on a session of its own: an archive failing in the database aborts the transaction it ran on, and shared it was every later admin's and the caller's (25P02 measured on PostgreSQL). Strings in `core/i18n_diagnostics.py` (6 languages, backend-canonical `zh-CN`). |
| `domains/diagnostics/diagnosis.py` | Budget-capped diagnostician pump. System prompt **injected by the caller** (F009: no diagnostics→agents import), with `{language}` left UNRESOLVED — the pump renders it once per admin language, resolved lazily from `distinct_admin_languages()` and only once a diagnosis is actually going to be produced. Runbook loader sanitizes `^[A-Za-z0-9]{1,64}$`; UTC-day USD budget via `INCRBYFLOAT`, checked before **every** call (one incident now costs one call per language); skipped ⇒ diagnosis stays NULL for retry. Stored shape keeps the first language FLAT plus `by_language`, so every existing reader finds the keys where they were; `diagnosis_for_language` resolves for the reader and never lets `by_language` leave the server. Both sides go through `normalize_language`. **No session is held across a wait** (ADR-304): the pump opens a short session of its own for the admin languages and one per stored diagnosis (`session_factory`, `get_db_context` by default) — it used to run on the tick's session, in the transaction the pending-incidents read opened, across Prometheus, Loki and every model call of the batch. |
| `domains/diagnostics/evidence_recipes.py` | ADR-266. One `EvidenceRecipe` per CORRELATION key (the alertname a check mirrors, else its check id): the catalogue queries and the Loki events worth reading for that incident, a window, and a written reason when a recipe fetches nothing. Boot assert: every check key has a recipe, every query exists, no silent empty recipe; CI adds every alert `prometheus.yml` loads and every event name emitted in `src/`. |
| `domains/diagnostics/context_collector.py` | ADR-266. Fetches the pack **at diagnosis time**, once per incident, after the budget gate: breakdown series per query, a Loki excerpt filtered client-side on the recipe's events/levels, counted by `(event, level, head)` then sampled, every field allowlisted + capped + PII-sanitised, plus the runtime block (`core/process_info.py`: version, commit, uptime). **Fail-open by source** — Prometheus, Loki or the collector itself failing costs a diagnosis its section, never the diagnosis. Bounds live in `DIAGNOSTICS_CONTEXT_*` constants. |
| `domains/diagnostics/advisor.py` + `degradation_map.py` | Fail-open O(1) view of degraded capabilities (open incidents cached in Redis + this worker's open breakers). Alternatives come from the declared map only. |
| `domains/diagnostics/failure_context.py` | Pure extraction of typed failures from `completed_steps` / ReAct ToolMessages (bounded, code + message head only) + the honesty directive builder (template injected). |
| `domains/diagnostics/service.py` + `router.py` | `build_overview` (ONE implementation, shared by REST and the chat tool) + `/admin/diagnostics/*` under `require_superuser`. |
| `infrastructure/scheduler/diagnostics_self_check.py` | The leader tick: engine → Alertmanager's firing alerts, then its start (both read before the session opens, ADR-304; any failure there — a malformed URL included — is an unreadable Alertmanager, never a lost tick) → persist → prune → incident sync → reconciliation of lost resolutions → notify (post-commit, new incidents only) → pending-incident read → session closed → diagnosis pump → liveness stamp (success only). |
| `agents/tools/diagnostics_tools.py` | 4 read-only chat tools, admin-gated at call time via `agents/tools/admin_gate.py` (shared with DevOps). Registered in the catalogue only when the flag is on. |
| `agents/services/runtime_failure_directive.py` | Response-node adapter: loads the versioned directive and delegates to `failure_context` (keeps agents→diagnostics one-way). |

## Request-path hooks (pillar 7)

- `smart_planner_service` and `react_setup_node` inject
  `format_degradations_block(...)` **only when non-empty** — zero prompt tokens on
  a healthy platform, fail-open by construction.
- `response_node` appends the honesty block built by
  `build_runtime_failures_block(state)`: what succeeded, what failed and *why*
  (typed codes only, ADR-182/184 — never raw logs, never invented diagnosis).

## Naming the cause, not only the consequence

Every check declares its **unit** (`KNOWN_UNITS`, closed set) and the API
publishes it next to the value: a client that infers the unit from the check id
eventually infers wrong — the millisecond egress probe would have rendered as a
percentage (ADR-184 doctrine).

`platform_egress` is the check the **2026-08-28 outage** asked for. The host
stopped forwarding IP (`net.ipv4.ip_forward` reset to 0 by an automatic package
upgrade re-applying a contradictory `sysctl.d` drop-in); every container lost
outbound routing while `/health` stayed green, DNS kept resolving and the host
itself reached the internet. LIA detected the *consequence* within six minutes —
`LLMAPIFailureRateHigh`, 100 % LLM failures, two open circuit breakers — but
nothing in the snapshot could say **why**. One probe per tick now does — a name
resolution then a TCP connect, no TLS, no request — and it is:

- **configured, never guessed** (`DIAGNOSTICS_EGRESS_PROBE_TARGET`, `host:port`):
  point it at a host the instance already talks to, so the probe discloses
  nothing new — an installation must not acquire a third party from a default;
- **absent when unconfigured**, not `ok` (that would claim a measurement nobody
  took) and not `unknown` (that would cap every default install at `degraded`).
  `InProcessCheck.enabled_setting` expresses this declaratively, and the boot
  assert refuses a gate no `Settings` field backs;
- **explicit about the step that failed** ([ADR-361](../architecture/ADR-361-Egress-Probe-Names-The-Failing-Step-And-Confirms-A-Cut.md)):
  the resolution goes through the loop's resolver, the one every outbound call
  uses, and a failure reads `name resolution timed out`, `name resolution
  failed (<class>)`, `connect timed out (name resolution took N ms)` — never the
  exception's message. In production, Docker's embedded resolver waits 4 s before
  failing over to its next DNS server, so a resolution and a connect measured as
  one used to read « unreachable » for a connection never attempted;
- **confirmed before it is critical**: up to `DIAGNOSTICS_EGRESS_PROBE_ATTEMPTS`
  attempts per tick, one per `DIAGNOSTICS_EGRESS_PROBE_TIMEOUT_SECONDS` slot (a
  fast failure waits out its slot). Every attempt failing is `critical`; a
  success after a failed attempt, or slower than
  `DIAGNOSTICS_EGRESS_PROBE_SLOW_SECONDS`, is `degraded` — on the health page
  with both phase durations, never paged. With a target configured, a slow
  threshold not below the timeout is refused at boot: no success could reach it.

`assert_probe_coverage` closes the matching hole on the other side: an
in-process check with no probe used to raise `KeyError` mid-tick — no snapshot,
no verdict, one scheduler error nobody reads.

## Operations

- Env: see `.env.example` §86 (`DIAGNOSTICS_*`, `ALERTMANAGER_LIA_WEBHOOK_URL`).
  The webhook target scheme differs by environment (prod API is plain HTTP on
  8000; dev is HTTPS self-signed — the receiver fragment carries
  `insecure_skip_verify` for that case).
- Alertmanager: the route/receiver are **committed fragments**
  (`infrastructure/observability/alertmanager/lia-webhook-*.fragment`) injected by
  the entrypoint when both URL and secret are set; the composition matrix (with and
  without SMTP, with and without the webhook) is replayed in CI by
  `task test:alertmanager`, which renders each case of
  `infrastructure/observability/alertmanager/tests/routing_matrix.yml` through the
  real entrypoint in the image production pins and checks it with amtool.
- Runbooks are mounted read-only at `/app/docs/runbooks` (dev + prod compose) for
  the diagnosis grounding — and **staged by `prepare-prod.ps1`** since ADR-266:
  until then the production mount was an empty directory Docker had created,
  and every stored diagnosis carried `had_runbook=false`. The overview publishes
  `runbooks_available`, the admin panel states a zero, and the boot validation
  logs `diagnostics_runbooks_missing` (a warning, never a refusal).
- Subsystem metrics, all wired in the "Self-Diagnostics" row of dashboard 16:
  `diagnostics_checks_total`, `diagnostics_incidents_total`,
  `diagnostics_self_check_duration_seconds`, `diagnostics_llm_cost_usd_total`,
  `diagnostics_catalogue_miss_total` (the free-form-query escalation signal),
  `diagnostics_context_sources_total` (evidence sources read per diagnosis, by
  status — a rising `unavailable` is a diagnostician reasoning half-blind).
- A diagnosis stores the pack it was written from (`diagnosis.context`) and the
  admin panel renders it under the text ("What the diagnostician read"): a
  blind source is stated with its reason, never drawn as a zero.

## Deliberate exclusions (escalation-gated — spec §3)

Free-form PromQL/LogQL in chat, Tempo trace reads, baseline anomaly detection and
Tier-1 auto-remediation ship **only** once their measured criteria fire. The
registries are the extension seams; empty scaffolding was deliberately not built.
