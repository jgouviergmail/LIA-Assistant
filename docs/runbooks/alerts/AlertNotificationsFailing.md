# AlertNotificationsFailing - Runbook

**Severity**: Warning
**Component**: Observability (Alertmanager delivery)
**Impact**: Alerts are evaluated and nobody is told on the failing channel. Until it is fixed, a critical alert reaches only the other channels, the in-app incident and the daily report
**SLA Impact**: Indirect — the next outage would be noticed late

---

## 📊 Alert Definition

**Alert Name**: `AlertNotificationsFailing` (core tier, `alerts-core.yml` — ADR-119)

**Prometheus Expression**:
```promql
sum by (integration) (
  increase(alertmanager_notifications_failed_total{integration=~"email|slack|pagerduty"}[15m])
) > 0
```

`for: 5m`. One series per human channel.

**The self-diagnostics webhook is left out on purpose.** Its target is the API
(`ALERTMANAGER_LIA_WEBHOOK_URL`), so it fails whenever the API is the thing that is down
and says nothing about a human channel. On 2026-11-09 it failed 22 times, every time
with `no such host` or `connection refused`, during the 53 minutes of `ServiceDown`;
the e-mail left normally. The daily report says so beside the count.

**This alert cannot travel on the channel it reports as broken.** With e-mail as the
only human channel, an e-mail failure reaches the in-app incident and the daily report,
nothing in real time. A second channel is one value in `.env.prod`
(`ALERTMANAGER_SLACK_WEBHOOK_CRITICAL` or `ALERTMANAGER_PAGERDUTY_ROUTING_KEY`): the
Alertmanager template already renders both.

**Labels**:
- `severity`: warning
- `component`: observability
- `tier`: core
- `integration`: `email`, `slack` or `pagerduty`

---

## 🎯 Diagnosis

```promql
# Which channel, and how Alertmanager classifies the failure
sum by (integration, reason) (increase(alertmanager_notifications_failed_total[1h]))
# Is anything delivered at all
sum by (integration) (increase(alertmanager_notifications_total[1h]))
```

```bash
# The error itself (mask URLs and tokens before copying a line anywhere)
docker logs lia-alertmanager-prod 2>&1 | grep -E 'level=(error|warn)' | tail -20
# What the container was rendered with (names and states only, never values)
docker logs lia-alertmanager-prod 2>&1 | grep -E 'CONFIGURED|NOT ROUTED|SMTP'
```

| `reason` | Usual cause |
|---|---|
| `authError` / `clientError` | The SMTP relay or the webhook refuses the credentials: a rotated password, a revoked webhook |
| `rateLimited` | The provider's sending quota |
| `serverError` | The provider is down |
| `other` | DNS or TCP: the containers have lost their outbound route (`cat /proc/sys/net/ipv4/ip_forward` must read 1 on a Docker host) |

---

## 🛠️ Resolution

1. Fix the credential or the address in `.env.prod`, then redeploy: Alertmanager reads
   its environment at start.
2. A provider outage resolves by itself; Alertmanager retries each notification, and a
   resolved alert is sent when the channel returns.
3. Check the proof, not the configuration: the delivered counter moves again.

---

## 📚 Related

- [AlertmanagerDown](./AlertmanagerDown.md) — Alertmanager itself unreachable
- [ADR-119](../../architecture/ADR-119-Alerting-Reactivation-Minimal-Core.md) — the alerting core
