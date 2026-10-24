# LIA Alerting Chain — Operations Guide

**Scope**: the live alerting chain reactivated by ADR-119 (2026-07): Prometheus rule evaluation → Alertmanager → email. This is the canonical operational doc; it replaces the former `README_ALERT_MANAGER2.md`, `README_PROMETHEUS_ALERTMANAGER.md` and `README_ALERTING_SMTP.md` (deleted 2026-07, recoverable from git history).

Related docs:
- Thresholds mechanism & legacy-threshold corruption: [PROMETHEUS_THRESHOLDS.md](./PROMETHEUS_THRESHOLDS.md)
- Decision record: [ADR-119](../architecture/ADR-119-Alerting-Reactivation-Minimal-Core.md)
- Per-alert incident procedures: [docs/runbooks/alerts/](../runbooks/alerts/)

---

## Architecture

```
thresholds/{env}.env ──prepare_config.sh──► alerts-core.yml   (the core rules, committed)
                                                 │ rule_files
Prometheus ◄── scrape: api, postgres, redis, node, cadvisor,
    │                  alertmanager, blackbox(-backup/-public),
    │                  and the pipeline itself: loki, alloy, tempo, grafana
    │                  (`up` + a keep-list each — ObservabilityScrapeTargetMissing,
    │                  LogsNotDelivered, dashboard 16)
    │ alerting: alertmanager:9093
    ▼
Alertmanager ──SMTP──► ALERTMANAGER_BACKEND_TEAM_EMAIL
    ▲  └──► read by Grafana (`alertmanager` datasource): alerts and silences
    │       in its Alerting pages — Grafana evaluates no rule of its own
    └─ entrypoint renders config from ALERTMANAGER_* env vars at startup

blackbox-exporter ── probes ──► postgres-backup:8080 (BackupFailed)
                              ► $BLACKBOX_PUBLIC_PROBE_URL (PublicEndpointDown,
                                CertificateExpirySoon — file_sd written at
                                Prometheus startup; empty var = probe disabled)
```

All components run in both compose files. Config lives in:

```
infrastructure/observability/
├── alertmanager/
│   ├── docker-entrypoint.sh                 # renders the config at startup (--render-only: the gate)
│   ├── alertmanager.yml.template            # THE template; optional blocks marked @begin/@end
│   ├── lia-webhook-{route,receiver}.fragment # LIA self-diagnostics webhook, injected when set
│   ├── tests/routing_matrix.yml             # cases of `task test:alertmanager`
│   └── templates/email.tmpl                 # HTML email templates
├── blackbox/blackbox.yml                    # single http_2xx module
└── prometheus/
    ├── prometheus.yml                       # alerting block + scrape jobs
    ├── alerts-core.yml(.template)           # THE loaded rules (ADR-119)
    ├── thresholds/{env}.env                 # ALERT_CORE_* live values
    └── tests/alerts_core_test.yml           # promtool unit tests
```

### Rendering at startup (entrypoint)

| Condition | Rendered config |
|---|---|
| SMTP vars missing | Minimal **log-only** (alerts visible in UI, no notification) |
| SMTP set | The template, minus every block whose channel or team is not configured ← production: email only |

There is ONE template (audit A07): two used to diverge, and the email-only one
had routes no alert could reach. Each optional block sits between
`# @begin <name>` and `# @end <name>` and is removed when what it needs is
missing, so a rendered config never holds an empty Slack URL or PagerDuty key
(Alertmanager refuses to start on either — measured):

| Block | Kept when |
|---|---|
| `slack-critical` / `slack-warning` | `ALERTMANAGER_SLACK_WEBHOOK_CRITICAL` / `_WARNING` is set |
| `pagerduty` | `ALERTMANAGER_PAGERDUTY_ROUTING_KEY` is set |
| `team-ml` | the ML team's address is set and is not the backend's (case ignored) |
| `email-security` / `slack-security` | the security address is not the backend's / the security webhook is not the critical one |
| `team-security` | `email-security` or `slack-security` is kept |

Values reach the config literally — `&`, `|`, `\` and `'` included; a value
holding a line break is refused at startup rather than rendered. The banner
states each channel (`CONFIGURED` / `NOT CONFIGURED`) and each team (`ROUTED` /
`NOT ROUTED`), never an address, a webhook or a key (ADR-317).

## Configuration

All variables live in the root `.env` (dev) / `.env.prod` (production) and are
passed to the containers by docker-compose. Templates: section `[20]` of
`.env.example` / `.env.prod.example`, section `[11]` of `.env.min.prod`.

**Required for email notifications:**

| Variable | Example |
|---|---|
| `ALERTMANAGER_SMTP_SMARTHOST` | `smtp-relay.example.com:587` |
| `ALERTMANAGER_SMTP_FROM` | `alerts@yourdomain.com` |
| `ALERTMANAGER_SMTP_AUTH_USERNAME` / `_PASSWORD` | SMTP credentials |
| `ALERTMANAGER_BACKEND_TEAM_EMAIL` | notification recipient |

**Optional:** `ALERTMANAGER_{SECURITY,ML}_TEAM_EMAIL` (a team is told in addition to the backend, and only on an address of its own), `ALERTMANAGER_SLACK_WEBHOOK_*`, `ALERTMANAGER_PAGERDUTY_ROUTING_KEY` (each adds its channel; one left empty renders nothing), `ALERTMANAGER_HOST_PORT` (default 9094), `BLACKBOX_PUBLIC_PROBE_URL` (public URL probe; leave empty in dev).

**SMTP provider notes:**
- **Gmail**: `smtp.gmail.com:587`, requires an App Password (2FA enabled), ~500 mails/day limit.
- **Brevo / SendGrid / SES**: use the relay host and API-key-based credentials; prefer a dedicated sender identity so DMARC passes.
- TLS is required (`smtp_require_tls: true` in the templates).

## Routing & inhibition

Severity fixes the URGENCY of the backend team's notification; the component
adds an AUDIENCE (owner decision, 2026-10-22). Both severity routes carry
`continue: true`, so a team route still sees the alert, and every loaded alert
is `critical` or `warning` (`test_alerts_core_guard`): a team is told in
addition to the backend, never instead of it.

| Route | Matches | Receiver | Channels | group_wait / repeat |
|---|---|---|---|---|
| severity | `severity=critical` | `critical` | email + Slack critical + PagerDuty | 10s / 30m |
| severity | `severity=warning` | `warning` | email + Slack warning | 1m / 2h |
| team | `component` agents, hitl, hitl_streaming | `ml-team` | email | 1m / 1h |
| team | `component=oauth`, critical | `security-team` | email and/or Slack security | 5s / 30m |

An audience is kept only with an alert that reaches it. No alert, loaded or
dormant, reached the finance route (the dormant budget alerts carry
`component: cost`), so it is gone with `ALERTMANAGER_FINANCE_TEAM_EMAIL`. No
loaded alert reaches the security route either (the dormant OAuth alerts carry
`component: auth`): security being outside the A07 audit, it stays as it was,
declared dormant in `test_alertmanager_template_guard.py` and reported to the
owner (ADR-119 amendment 2026-10-23).

PagerDuty pages from the critical route alone. The LIA webhook route, when
configured, comes first and observes every critical and warning alert
(`continue: true`). Resolved notifications are sent (`send_resolved: true`). Inhibition rules
suppress noise: ServiceDown mutes API error/latency alerts, RedisDown mutes
Redis warnings, PostgreSQLDown mutes connection-pool alerts, and any critical
mutes the same alert's warning.

## Validation & testing

```bash
# 1. Rendering + routing matrix: each case of alertmanager/tests/routing_matrix.yml
#    rendered by the real entrypoint in the production image (no network), then
#    `amtool check-config`, every email template it names rendered, and
#    `amtool config routes test` (audit A07; also in CI)
task test:alertmanager

# 2. Rule syntax + unit tests (thresholds pinned inside descriptions)
docker run --rm --entrypoint promtool \
  -v "$(pwd)/infrastructure/observability/prometheus:/cfg" prom/prometheus:v3.0.0 \
  check config /cfg/prometheus.yml
docker run --rm --entrypoint promtool \
  -v "$(pwd)/infrastructure/observability/prometheus:/cfg" prom/prometheus:v3.0.0 \
  test rules /cfg/tests/alerts_core_test.yml

# 3. Rendered Alertmanager config (inside the running container)
docker exec lia-alertmanager-dev amtool check-config /etc/alertmanager/alertmanager.yml

# 4. Synthetic alert end-to-end (email should arrive)
docker exec lia-alertmanager-dev amtool alert add TestAlert severity=warning \
  --annotation=summary="Manual chain test" --alertmanager.url=http://localhost:9093

# 5. Real end-to-end (proven 2026-07-09, ~3m30 detection→email)
docker stop lia-redis-dev    # RedisDown fires after for:2m → [CRITICAL] email
docker start lia-redis-dev   # resolved email ~2m later
```

## Troubleshooting

| Symptom | Check |
|---|---|
| Container starts in log-only mode | `docker logs lia-alertmanager-*` — banner lists missing SMTP vars |
| SMTP 535 auth failed | Credentials/app password; some relays require the FROM to match the authenticated identity |
| Alert fires but no email | Alertmanager logs for `notify` errors; check spam and **Gmail filters** (alerts may be auto-labeled out of INBOX); verify `repeat_interval` hasn't already fired |
| No alerts at all | Prometheus UI `/alerts` (rules loaded?), `/targets` (alertmanager target up?), `up{job="alertmanager"}` |
| AlertmanagerDown firing | See [AlertmanagerDown runbook](../runbooks/alerts/AlertmanagerDown.md) — this one cannot email you by definition |

## Legacy alert catalog (NOT loaded)

The 2025-11 catalog (60 alerts in `alerts.yml`, 11 in `alert_rules.yml`, plus
`prometheus/alerts/*.yml`) is **not** wired into `rule_files`: its rendered
thresholds are corrupted (percentages above 100 — see
[PROMETHEUS_THRESHOLDS.md](./PROMETHEUS_THRESHOLDS.md)). Recalibrate
group by group before re-enabling; the templates are the source of truth for
their PromQL.

**Second blocker, measured 2026-08-27 — its runbook links go nowhere.** Eight
`runbook_url` annotations in `alerts.yml` point at `https://docs.company.com/...`,
a placeholder domain that has never existed. Re-enabling a group without fixing
them hands the on-call a dead link at the worst possible moment.

The loaded catalog does not have this problem, and not by luck: `alerts-core.yml`
uses a `runbook` annotation holding an **in-repo path**, and
`test_alerts_core_guard::test_alert_links_to_a_runbook_that_exists` fails when
that file is missing. Any group promoted out of the legacy catalog must adopt the
same convention — in-repo path, not external URL — so the guard covers it the day
it starts firing. A recalibrated threshold with a dead runbook is half a control.
