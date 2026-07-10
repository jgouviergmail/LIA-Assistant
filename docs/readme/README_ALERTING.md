# LIA Alerting Chain — Operations Guide

**Scope**: the live alerting chain reactivated by ADR-119 (2026-07): Prometheus rule evaluation → Alertmanager → email. This is the canonical operational doc; it replaces the former `README_ALERT_MANAGER2.md`, `README_PROMETHEUS_ALERTMANAGER.md` and `README_ALERTING_SMTP.md` (deleted 2026-07, recoverable from git history).

Related docs:
- Thresholds mechanism & legacy-threshold corruption: [README_PROMETHEUS_THRESHOLDS.md](README_PROMETHEUS_THRESHOLDS.md)
- Decision record: [ADR-119](../architecture/ADR-119-Alerting-Reactivation-Minimal-Core.md)
- Per-alert incident procedures: [docs/runbooks/alerts/](../runbooks/alerts/)

---

## Architecture

```
thresholds/{env}.env ──prepare_config.sh──► alerts-core.yml   (13 rules, committed)
                                                 │ rule_files
Prometheus ◄── scrape: api, postgres, redis, node, cadvisor,
    │                  alertmanager, blackbox(-backup/-public)
    │ alerting: alertmanager:9093
    ▼
Alertmanager ──SMTP──► ALERTMANAGER_BACKEND_TEAM_EMAIL
    ▲
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
│   ├── docker-entrypoint.sh                 # env-var substitution at startup
│   ├── alertmanager.yml.template            # full multi-channel template
│   ├── alertmanager-email-only.yml.template # selected when Slack/PagerDuty unset
│   ├── validate_config.py                   # offline template validation
│   └── templates/email.tmpl                 # HTML email templates
├── blackbox/blackbox.yml                    # single http_2xx module
└── prometheus/
    ├── prometheus.yml                       # alerting block + scrape jobs
    ├── alerts-core.yml(.template)           # THE loaded rules (ADR-119)
    ├── thresholds/{env}.env                 # ALERT_CORE_* live values
    └── tests/alerts_core_test.yml           # promtool unit tests (17 cases)
```

### Startup mode selection (entrypoint)

| Condition | Rendered config |
|---|---|
| SMTP vars missing | Minimal **log-only** (alerts visible in UI, no notification) |
| SMTP set, Slack/PagerDuty empty | **Email-only** template ← production mode |
| SMTP + any webhook set | Full multi-channel template |

The selected mode is printed in the container logs at startup (`Mode: Email only`).

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

**Optional:** `ALERTMANAGER_{FINANCE,SECURITY,ML}_TEAM_EMAIL` (default to backend email), `ALERTMANAGER_SLACK_WEBHOOK_*`, `ALERTMANAGER_PAGERDUTY_ROUTING_KEY` (setting any switches to the multi-channel template), `ALERTMANAGER_HOST_PORT` (default 9094), `BLACKBOX_PUBLIC_PROBE_URL` (public URL probe; leave empty in dev).

**SMTP provider notes:**
- **Gmail**: `smtp.gmail.com:587`, requires an App Password (2FA enabled), ~500 mails/day limit.
- **Brevo / SendGrid / SES**: use the relay host and API-key-based credentials; prefer a dedicated sender identity so DMARC passes.
- TLS is required (`smtp_require_tls: true` in the templates).

## Routing & inhibition (email-only mode)

| Severity | group_wait | repeat_interval | Subject |
|---|---|---|---|
| critical | 10s | 30m | `[CRITICAL] LIA: <alertname>` |
| warning | 1m | 2h | `[WARNING] LIA: <alertname>` |
| llm budget (critical) | 5s | 15m | `[BUDGET] ...` |

Resolved notifications are sent (`send_resolved: true`). Inhibition rules
suppress noise: ServiceDown mutes API error/latency alerts, RedisDown mutes
Redis warnings, PostgreSQLDown mutes connection-pool alerts, and any critical
mutes the same alert's warning.

## Validation & testing

```bash
# 1. Offline template validation (no containers needed)
python infrastructure/observability/alertmanager/validate_config.py

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
[README_PROMETHEUS_THRESHOLDS.md](README_PROMETHEUS_THRESHOLDS.md)). Recalibrate
group by group before re-enabling; the templates are the source of truth for
their PromQL.
