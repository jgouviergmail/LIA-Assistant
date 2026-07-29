# Product Dashboard Program — Grafana 26 "Product Value, Activation & Retention"

**Date:** 2026-07-29 · **Status:** Phase 0 + Phase 1 in progress (decisions signed off)
**Baseline:** HEAD `0ccf5ee3` (v1.26.0). Working tree: 1 untracked file
(`docs/superpowers/specs/2026-07-29-html-enrichi-composants-design.md`) — zero overlap
with this program.
**Source document:** `output/pdf/LIA_Specification_Dashboard_Grafana_Produit_v1.1.pdf`
(user-authored, 21 pages). This file is the **corrected v1.2 working contract**: every
claim below was verified in-code on 2026-07-29 (file:line evidence inline); 12 factual
corrections vs the PDF are listed and are authoritative over it.
Sibling program docs (same format): `2026-07-22-ux-refinements-program.md`,
`2026-07-21-quick-wins-ux-program.md`.

**Architecture (ADR-178):** 100 % native stack — Grafana + Prometheus + PostgreSQL.
No third-party analytics or tracing platform. Langfuse is NOT a dependency of this
dashboard (it only runs in dev; prod compose has no Langfuse service) — nothing is
removed from LIA, the dashboard simply never references it.

---

## How to resume (session protocol)

1. Read memory `project_product_dashboard_program.md`, then this document. The status
   tracker (bottom) says where the program stands.
2. Check the real state: `git log --oneline -5`, `git status`. If HEAD moved past the
   baseline, re-verify the volatile assumptions of the target phase (metric names,
   dashboard count, ADR numbering — ADR-177 was taken by Rich HTML mid-program).
3. Present findings → green light → implement **inline** (user rule: no subagents).
4. Runtime proof happens in the Docker dev containers (`docker restart` before browser
   validation; Grafana dev admin user `adminliagrafana`, password in the container's
   `GF_SECURITY_ADMIN_PASSWORD`).
5. Update the status tracker here + the memory file. **Never commit/push — the user does.**

---

## Signed-off decisions (2026-07-29, user)

| # | Decision | Outcome |
|---|----------|---------|
| 1 | Phasing | 5 phases; Phase 1 (dashboard v0 on existing metrics only) ships first, alone |
| 2 | Raw `product_events` | **Included in v1** (Phase 2 scope, alongside `product_outcomes`) — user override of the "defer" recommendation |
| 3 | `device_class` | Derived from the session's bounded `os_family` (android/ios → mobile, windows/macos/linux → desktop, tablet not distinguished). No new client capture (ADR-144 minimization) |
| 4 | Read-only PG role | Idempotent script + Task target (pattern `db:create-admin`), `GRANT SELECT` on product views/tables only, `statement_timeout` set on the role. Never a password in an alembic migration |
| 5 | Dashboard identity | uid `26-product-value` (documented `<numero>-<slug>` convention), **English** title `26 - Product Value, Activation & Retention` |
| 6 | Raw-outcome retention | 180 days raw (`PRODUCT_OUTCOMES_RETENTION_DAYS`, env-configurable), daily aggregates kept forever; purge runs inside the leader-elected aggregation job |

## Corrections vs PDF v1.1 (authoritative)

1. **uid** `lia-product-value` → `26-product-value`; **title in English** (all 25 existing
   dashboards have English titles, e.g. "25 - Today Briefing").
2. **AUT-13 reclassified** "Existant" → "Nouveau DB": no Prometheus series for
   `consecutive_failures` — DB column only
   (`apps/api/src/domains/scheduled_actions/models.py:197`); only generic
   `background_job_*` series exist.
3. **HITL-14 reclassified** "Existant" → "Nouveau DB": a *median of per-draft edit
   iterations* is not derivable from the global Counter
   `registry_draft_actions_total` (`metrics_agents.py:1257`).
4. **`execution_mode` variable**: values are `pipeline | react` only
   (`apps/api/src/domains/auth/schemas.py:404`); `direct` does not exist and is dropped.
5. **`job` label** on `product_metrics_last_refresh_timestamp_seconds` → renamed
   **`refresh_job`** (`job` is a reserved Prometheus scrape label; it would be mangled
   to `exported_job`).
6. **Datasource provisioning**: `database` must be `$POSTGRES_DB` (env-interpolated),
   never hardcoded `lia`; `GRAFANA_PRODUCT_DB_PASSWORD` must be added to the Grafana
   container environment in BOTH compose files + `.env.example` + `.env.prod.example`
   (+ `.env.min.prod` if needed). Env interpolation on Grafana 11.3 to be re-proven in
   dev at Phase 3 start (5-min check) before relying on it.
7. **`locale` variable**: backend-canonical values (`zh-CN`, not `zh` —
   `apps/api/src/core/constants.py:882`); fed from the datasource, never hardcoded.
8. **Histogram cardinality**: max **2 labels** per new `product_*` histogram.
   `DOMAIN_REGISTRY` has 26 domains (`domain_taxonomy.py:82`), not ~7; the PDF's
   4-label histograms would create up to ~23k series on an RPi5. Fine-grained splits
   (result_type × domain × mode) live in PostgreSQL only.
9. **OUT-21 reclassified** "Dérivé" → "Partiel": `react_agent_duration_seconds` has no
   labels (`metrics_react.py:12`); per-request-type normalization is impossible from
   existing series. v0 compares p95 via `langgraph_stage_duration_seconds{execution_mode}`.
10. **UX-11..17 / DQ-13 ("QA automatisée")**: out of v1 scope — no push mechanism
    exists (no Pushgateway, no QA export pipeline). Revisit only with a specified
    mechanism.
11. **Currency contract**: all `product_*` costs in **EUR**, sourced from DB
    (`message_token_summary.total_cost_eur`, `chat/models.py:123`).
    `conversation_cost_usd` (USD) stays confined to dashboards 05/09; never mixed.
12. **"Vues PostgreSQL"** → daily aggregate **tables** (`product_*_daily`) written by the
    hourly leader-elected job (pattern `user_statistics` + atomic upserts à la
    `create_or_update_token_summary`), plus thin read views for Grafana. No
    `MATERIALIZED VIEW` (locking refresh, foreign to the codebase).

Two verified nuances kept as caveats (not errors): DAU/WAU gauges measure
conversational activity only (`DISTINCT user_id` on `Conversation.updated_at`,
`lifetime_metrics.py:522-535`) — panel descriptions must say so; PERF-11's
pipeline-side timeout counter is unverified (react side exists:
`react_agent_executions_total{status="timeout"}`).

## Additional mandatory wiring (self-audit additions)

- **GDPR / account lifecycle**: `product_outcomes` and `product_events` carry
  `user_id` → register both in `users/user_data_map.py` (`_PURGED_FULL`) and in
  `account_deletion_service`, with tests (same treatment as `scheduled_actions`,
  `user_data_map.py:136`).
- **Channel attribution is NEW instrumentation**: nothing carries a
  web/pwa/voice/scheduler channel on a run today (only the
  `scheduled_action_` session prefix, `constants.py:481`). The Phase 2 design must
  state the provenance of every `channel` value; unknown → `unknown`, never guessed.
- **Emission off the hot path**: outcome writes are async/best-effort, never blocking
  the SSE loop.
- North Star is **never** computed from Prometheus (E1/E2 states are mutable within
  24 h; Counters cannot un-count). NS panels bind to the PostgreSQL datasource only —
  enforced by a structural check in Phase 3.

## Phases

| Phase | Deliverables | Gates |
|-------|--------------|-------|
| 0 — Contract (this doc) | v1.2 corrections, ADR-178 + index, program spec | `task lint:docs` |
| 1 — Dashboard 26 v0 | `26-product-value.json` (42 panels, existing metrics live, future `product_*` names pre-wired rendering N/A, DB-only panels as explicit text placeholders), GRAFANA_DASHBOARDS.md v4.5 | JSON + structural validation, every referenced metric proven to exist, Grafana dev provisioning loads with zero error, dashboards 01-25 untouched |
| 2 — Durable outcomes | `domains/product/` (models `product_outcomes` + `product_events`, repo, service, config module + `PRODUCT_ANALYTICS_ENABLED`, migration + replay-check, model registration ×3), E3 auto + E1 feedback + E2 24 h-job, `metrics_product.py` DB-backed gauges (≤2 labels), hourly leader-elected job (aggregation + 180 d purge), GDPR purge wiring, tests (round-trip, concurrent upsert, timezone, cardinality guard) | `task lint`, `task test:backend:unit:fast`, `task db:migrate:replay-check`, runtime Docker proof |
| 3 — PostgreSQL datasource | `product_*_daily` tables + read views, `grafana_product_reader` (script + task + scoped GRANTs + `statement_timeout`), provisioned datasource (uid `postgres-product-readonly`, env-interpolated), compose + env files, NS/funnel/cohort panels live, `EXPLAIN ANALYZE` on 7/30/90 d | same + live audit dev |
| 4 — Client telemetry (own spec) | landing/demo funnel, web vitals, PWA — ingestion endpoint, rate limiting, privacy | dedicated spec first |
| 5 — Product alerts (≥4 weeks baseline) | `alerts-product.yml` + `rule_files` + compose mounts ×2, ADR-119 hygiene (owner, runbook) | live alert audit |

## Dashboard 26 v0 contract (Phase 1)

Identity: uid `26-product-value`, title `26 - Product Value, Activation & Retention`,
tags `["lia", "product", "value", "growth", "outcomes"]`, schemaVersion 38, refresh
`5m`, time `now-30d`, timezone `browser`, `graphTooltip: 1`, `$datasource` variable
(Prometheus) — conventions of GRAFANA_DASHBOARDS.md §"Ajouter un dashboard".

42 panels / 11 rows (rows 00/01/02/10 visible, 03–09 collapsed). Three panel states:

- **LIVE** (existing series/rules): E3 technical success, negative-feedback rate,
  agentic quality, turns heatmap (`conversation_turns_total` IS a histogram,
  `metrics_business.py:109`), pipeline-vs-react p95, HITL (4), DAU/WAU (caveated),
  connectors (2), proactivity (2), TTFT/streaming, EUR costs (DB-backed gauges).
- **PRE-WIRED** (query on the future `product_*` name from the corrected contract —
  renders N/A via `noValue: "n/a"` until Phase 2/3 ships the series, then lights up
  with no dashboard change): North Star trend, penetration, activation, retention,
  funnel stages, value by domain/result_type, mobile gap, data-quality ratio,
  freshness (`refresh_job` label).
- **TEXT placeholder** (no honest future Prometheus name — DB/client-only): median
  results per user, first-pass rate, cohort heatmaps, inter-step times, routines
  (3 panels), search, QA UX, web vitals. Each states its phase and source.

noValue conventions per GRAFANA_DASHBOARDS.md: `"n/a"` for ratios/future series,
`"0"` for rare-event counters, nothing on core-throughput series. Rare-family
quantiles use `[1h]` windows.

## Phase 4 — client telemetry (arbitrations signed off 2026-07-29)

User decisions: **(a) anonymous pre-signup landing events: YES** — restricted
to a fixed pre-auth event subset, no identifier of any kind stored (no IP, no
fingerprint, `user_id NULL`), counts only; **(b) Web Vitals sampling: 100 %**
(tiny traffic), client-side `NEXT_PUBLIC_WEB_VITALS_SAMPLE_RATE` default 1;
**(c) PWA install tracking: YES** (`pwa_install_prompt` / `pwa_installed`).

Architecture: one bounded ingestion endpoint `POST /api/v1/product/events`
(optional session auth via `get_optional_session`, IP rate-limited, enum-only
event schema — never free text, batch <= 20). Funnel/PWA events land in
`product_events` (user nullable — migration c0d1e2f3a4b5); search + Web
Vitals go to bounded Prometheus families only (`product_search_total`,
`product_web_vital_seconds`, `product_web_vital_ratio` for CLS). Vitals v1 =
LCP + CLS via native PerformanceObserver (no new dependency; INP deferred —
documented). Frontend emitter behind `NEXT_PUBLIC_PRODUCT_TELEMETRY`
(off by default: dev/e2e inert), sendBeacon-first, always fail-silent.

## Implementation notes (learned during phases 1-3)

- `docker restart` never re-reads `.env` — recreate with `up -d <svc>` when a
  flag must reach a container.
- Migrations run IN the api container (`docker compose … exec -T api alembic
  upgrade head`) — the host cannot resolve `postgres`.
- The file-size/CC ratchets bite on touched frozen files: the SSE seam must
  stay a single unconditional call (guard inside `schedule_outcome_recording`)
  and `stream_gates.py` absorbed the extracted pre-stream blocks.
- A JSONB column named `properties` collides with the AST mutation guard via
  a non-ORM homonym (`browser/accessibility.py`) — the column is `payload`.
- Standalone scripts must call `import_domain_models()` before touching any
  mapper (the `create_admin.py` lesson).
- Grafana env interpolation in datasource provisioning PROVEN live on 11.3
  (`database: $POSTGRES_DB` resolved; role query 200; base tables denied).

## Dashboard v2 + prod hardening (2026-07-29, post-release v1.26.2)

Prod audit found three real defects, all fixed:
1. **Grants were never applied in prod** (role created before the views; the
   runbook script could not run — `apps/api/scripts/` was missing from the
   deploy transfer whitelist). Fixed live via direct SQL grants; whitelist now
   copies `apps/api/scripts/` (prepare-prod.ps1).
2. **The rollup starved**: interval-only job + API restarting more often than
   the interval = zero ticks ever (4 boots, 0 runs measured). `next_run_time`
   now pins the FIRST run ~2 min after boot (proven in-process: gauges exposed
   by the server 2 min after recreate).
3. **Stale placeholders**: panels said "Awaiting Phase 3/4" after those phases
   shipped. v2: search + Web Vitals are LIVE Prometheus; first-pass proxy,
   signup->first-value (ACT-03) and routines health are LIVE SQL over three
   NEW views (migration d1e2f3a4b5c6: product_routines_snapshot,
   product_time_to_first_value, product_quality_daily — grants via the
   script, now 7 views); every waiting text states the true current reason
   (pipeline live / telemetry flag off / run-linkage deferred).

## Status tracker

| Item | State |
|------|-------|
| Phase 0 — spec v1.2 + ADR-178 | DONE 2026-07-29 |
| Phase 1 — dashboard 26 v0 (42 panels, validated live in dev Grafana) | DONE 2026-07-29 |
| Phase 2 — durable outcomes (domain, migration a8b9c0d1e2f3, seams, rollup job, GDPR purge, gauges) | DONE 2026-07-29 — all gates green (mypy strict, replay-check, 14 771 unit tests) |
| Phase 3 — PG datasource (views b9c0d1e2f3a4, grafana_product_reader, provisioning, panels 3/27 SQL) | DONE 2026-07-29 — proven live (role denied on base tables) |
| Phase 4 — client telemetry (ingestion endpoint, migration c0d1e2f3a4b5, client metrics, frontend emitter + 4 surfaces) | DONE 2026-07-29 — proven live (anonymous 202, NULL-user row, `pwa_installed` refused anonymously); backend 14 779 + frontend 4 083 tests green, coverage thresholds EXIT=0 |
| Phase 5 — product alerts | PREPARED (`alerts-product.yml`, not mounted) — activate after 4-week baseline |

Phase 4 additional traps: a developer `.env` with
`NEXT_PUBLIC_PRODUCT_TELEMETRY=true` leaks into vitest through the global
Taskfile dotenv — both frontend test tasks now blank it (same class as the
documented `NEXT_PUBLIC_API_URL` leak); `lib/product-telemetry.ts` is a
justified entry in the raw-`fetch` allowlist (beacon semantics — apiClient
auth-eject/error surfaces must never trigger). `demo_completed` is emitted
nowhere yet (the interactive mockup has no unambiguous "end" signal — wire it
when the demo gets a terminal state). INP deferred (LCP + CLS shipped).
