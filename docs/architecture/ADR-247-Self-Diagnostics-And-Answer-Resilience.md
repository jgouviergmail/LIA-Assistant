# ADR-247: an assistant that can read its own telemetry

**Status**: Accepted (2026-08-28)
**Deciders**: LIA core team (arbitrations by the project owner, 2026-08-27)
**Technical story**: self-diagnostics programme. Spec: `docs/superpowers/specs/2026-08-27-self-diagnostics-design.md`; domain doc: [DIAGNOSTICS_DOMAIN](../technical/DIAGNOSTICS_DOMAIN.md).

## Context

LIA emits enterprise-grade observability — hundreds of Prometheus metrics, structlog
JSON logs shipped to Loki, a 14-alert core (ADR-119) with per-alert runbooks — and
read **none of it**. There was no Prometheus or Loki client anywhere in the backend:
the assistant was fully instrumented and fully blind to itself. Invisible failures
(a dead background job, the documented `/health`-green-but-LangGraph-dead class)
reached no one until a human opened Grafana; a firing alert reached email but never
LIA nor an administrator inside the product; and a run that failed mid-request could
not use the platform's own knowledge of what was broken to answer honestly or route
around the outage.

## Decision

One bounded context, `domains/diagnostics/`, plus a telemetry read layer
(`infrastructure/telemetry/`) and thin hooks into existing seams — everything behind
`DIAGNOSTICS_ENABLED` (default **false**: flag off, the subsystem does not exist at
runtime). Seven pillars:

1. **Telemetry access that never raises.** Async clients for Prometheus, Loki and
   Alertmanager: short timeouts, the existing circuit breaker per source, and every
   failure mode collapsed into a typed `unavailable` result. An empty base URL
   disables a source, so an install without the observability stack is unchanged.
2. **No free-form query language, ever.** A named-query catalogue (boot-asserted,
   ADR-085 pattern) is the only producer of PromQL — parameters are typed, bounded
   and **published** in the tool manifests (ADR-184 doctrine); a constrained builder
   is the only producer of LogQL (closed service enum, closed level set, strict
   event pattern, range and line caps as constants). This is what protects Loki —
   which has an OOM history on the Pi — and closes query injection structurally.
3. **A deterministic self-check loop.** A leader-elected job evaluates a declarative
   check registry (golden signals from Prometheus + in-process probes that keep
   working when Prometheus is down) into persisted snapshots with exact measured
   values. `unknown` caps the overall verdict at `degraded`: blind is not healthy,
   and blindness is not an outage.
4. **An incident memory with one identity per outage.** Alertmanager deliveries
   (a new Bearer-authenticated webhook, injected into the Alertmanager config from
   committed fragments and matrix-tested) and critical self-check verdicts converge
   on ONE open incident per correlation key — a partial unique index makes the
   open-or-touch upsert atomic under webhook-vs-leader concurrency. Admins are
   notified in-app/push (never email — Alertmanager already emails), behind an
   atomic `SET NX EX` cooldown that fails OPEN.
5. **Runbook-grounded, budget-capped LLM diagnosis.** A pull-based pump on the same
   leader tick diagnoses open incidents with a dedicated `diagnostician` LLM slot;
   evidence and runbook are quoted data, spend is metered per UTC day through one
   `INCRBYFLOAT` and a cap of 0 disables the step. A skipped incident keeps a NULL
   diagnosis so a later tick retries; no automated action ever derives from LLM text.
6. **Admin-only surfaces.** Four read-only chat tools (admin check at call time —
   the DevOps-tool pattern, via a shared gate extracted from it), a superuser REST
   surface, a "Platform health" settings section (i18n ×6), all exact-count honest.
7. **Answer resilience on the request path.** A fail-open advisor turns open
   incidents + this worker's open breakers into a degradations block injected into
   planner/ReAct context **only when non-empty** (zero tokens on a healthy
   platform); typed failure extraction over what the run already carries
   (`completed_steps`, ReAct ToolMessages — deliberately **no new state key**)
   feeds an honesty directive into response synthesis. ADR-182/184 hold: the
   user-facing explanation derives from typed classifications only.

## Consequences

- The domain graph stays acyclic: diagnostics never imports agents. Prompt
  templates are **injected by callers** (the response-node adapter and the
  scheduler job load them), which the F009 cycle ratchet enforces.
- `health_snapshots` and `incidents` are GLOBAL tables (no user data; excluded
  from GDPR export and account purge — classified in `user_data_map`).
- The diagnosis budget is an estimate from real usage via the pricing cache; it is
  deliberately outside per-user token tracking (there is no user to attribute
  system diagnosis to).
- Deferred behind measured escalation criteria (spec §3): free-form PromQL/LogQL
  for admins, Tempo reads, baseline anomaly detection, Tier-1 auto-remediation.
  The extension seams (registries) exist; the code deliberately does not.
