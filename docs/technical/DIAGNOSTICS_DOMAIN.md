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
| `infrastructure/telemetry/{prometheus,loki,alertmanager}.py` | HTTP read clients. **Never raise**: every failure is a typed `unavailable` result; circuit breaker per source; empty URL = source disabled. |
| `domains/diagnostics/query_catalogue.py` | The ONLY producer of PromQL: named queries, bounded params (published in manifests), boot completeness assert. |
| `domains/diagnostics/logql.py` | The ONLY producer of LogQL: closed service enum, closed levels, strict event pattern, range/line hard caps (constants). |
| `domains/diagnostics/checks.py` + `engine.py` | Declarative check registry (Prometheus-backed + in-process probes) → `HealthSnapshotDTO`. Prometheus down ⇒ those checks `unknown`, probes still run; `unknown` caps overall at `degraded`. |
| `domains/diagnostics/models.py` + `repository.py` | `health_snapshots`, `incidents`. One OPEN incident per correlation key via a partial unique index; open-or-touch is a single `ON CONFLICT` upsert (`xmax = 0` detects creation). |
| `domains/diagnostics/incident_sync.py` | Snapshot verdicts → incidents. Critical opens/touches; OK auto-resolves **self_check-sourced only** (the alert's resolved event owns alert-sourced ones); a check may declare the `alertname` it mirrors so both sources share one identity. |
| `domains/diagnostics/webhook_router.py` | `POST /api/v1/internal/diagnostics/alert-webhook` — Bearer shared secret; 404 while the flag is off or the secret unset; firing→open, resolved→resolve; nameless alerts skipped. |
| `domains/diagnostics/notifications.py` | Superuser fan-out (in-app + push + channels; **no email**), cooldown = one atomic `SET NX EX`, fail-OPEN. Strings in `core/i18n_diagnostics.py` (6 languages, backend-canonical `zh-CN`). |
| `domains/diagnostics/diagnosis.py` | Budget-capped diagnostician pump. System prompt **injected by the caller** (F009: no diagnostics→agents import); runbook loader sanitizes `^[A-Za-z0-9]{1,64}$`; UTC-day USD budget via `INCRBYFLOAT`; skipped ⇒ diagnosis stays NULL for retry. |
| `domains/diagnostics/advisor.py` + `degradation_map.py` | Fail-open O(1) view of degraded capabilities (open incidents cached in Redis + this worker's open breakers). Alternatives come from the declared map only. |
| `domains/diagnostics/failure_context.py` | Pure extraction of typed failures from `completed_steps` / ReAct ToolMessages (bounded, code + message head only) + the honesty directive builder (template injected). |
| `domains/diagnostics/service.py` + `router.py` | `build_overview` (ONE implementation, shared by REST and the chat tool) + `/admin/diagnostics/*` under `require_superuser`. |
| `infrastructure/scheduler/diagnostics_self_check.py` | The leader tick: engine → persist → prune → incident sync → notify (post-commit, new incidents only) → diagnosis pump → liveness stamp (success only). |
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
nothing in the snapshot could say **why**. One bounded TCP connect per tick now
does, and it is:

- **configured, never guessed** (`DIAGNOSTICS_EGRESS_PROBE_TARGET`, `host:port`):
  point it at a host the instance already talks to, so the probe discloses
  nothing new — an installation must not acquire a third party from a default;
- **absent when unconfigured**, not `ok` (that would claim a measurement nobody
  took) and not `unknown` (that would cap every default install at `degraded`).
  `InProcessCheck.enabled_setting` expresses this declaratively, and the boot
  assert refuses a gate no `Settings` field backs.

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
  the entrypoint when both URL and secret are set; the composition matrix is
  replayed in CI by `tests/unit/test_alertmanager_webhook_matrix.py`.
- Runbooks are mounted read-only at `/app/docs/runbooks` (dev + prod compose) for
  the diagnosis grounding.
- Subsystem metrics: `diagnostics_checks_total`, `diagnostics_incidents_total`,
  `diagnostics_self_check_duration_seconds`, `diagnostics_llm_cost_usd_total`,
  `diagnostics_catalogue_miss_total` (the free-form-query escalation signal).

## Deliberate exclusions (escalation-gated — spec §3)

Free-form PromQL/LogQL in chat, Tempo trace reads, baseline anomaly detection and
Tier-1 auto-remediation ship **only** once their measured criteria fire. The
registries are the extension seams; empty scaffolding was deliberately not built.
