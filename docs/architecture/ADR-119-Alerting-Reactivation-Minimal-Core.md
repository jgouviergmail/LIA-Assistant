# ADR-119: Alerting Reactivation — Minimal Viable Core over Alertmanager Email

**Status**: ✅ IMPLEMENTED (2026-07-10)
**Author**: Claude Code (Fable 5)
**Related**: `infrastructure/observability/prometheus/alerts-core.yml.template`, `infrastructure/observability/alertmanager/`, [PROMETHEUS_THRESHOLDS.md](../technical/PROMETHEUS_THRESHOLDS.md), [ADR-109 (PostgreSQL backups)](ADR_INDEX.md), `docs/runbooks/alerts/`

## Context

On 2026-01-16, Prometheus alerting was disabled entirely — `alerts.yml` removed
from `rule_files`, the `alerting:` block commented out — **without an ADR**.
The 2026-07 audit found the consequences:

- ~71 maintained alert rules (60 in `alerts.yml`, 11 in `alert_rules.yml`) and
  22 runbooks in `docs/runbooks/alerts/` were dormant. **Nobody was notified of
  any incident**; the only signal was the daily logwatch digest. DORA MTTR was
  unmeasurable.
- Alertmanager ran in development only — and even there as a zombie: Prometheus
  neither loaded alert rules nor targeted it.
- Two divergent Alertmanager config directories existed
  (`apps/api/monitoring/alertmanager/` — the one actually mounted — and an
  orphaned `infrastructure/observability/prometheus/alertmanager/`).
- **The rendered legacy thresholds are corrupted**: the 2025-11 generator
  applied blind multipliers (prod ×1.5, staging ×3, dev ×7.5) to bounded
  percentages. Production `DiskSpaceCritical` fired at **147% disk usage**
  (impossible), CPU/memory at 142.5%, error rate at 30% instead of the
  documented 5%. Re-enabling `alerts.yml` as-is would have produced an
  alerting chain that *looks* alive but can never fire on disk/CPU/memory.
- 22 one-shot migration scripts and archive files cluttered the living config
  directory.

## Decision

1. **Prometheus-evaluated rules + a dedicated Alertmanager (email), not Grafana
   unified alerting.** Alertmanager v0.27 in both compose files
   (prod limits: 128M/0.25 cpu — RPi5-scale like the other sidecars). Grafana
   alerting stays deliberately unused: it would move rule evaluation into a
   tightly-sized Grafana, has no `promtool test rules` equivalent, and would
   make Grafana a silent single point of failure for the whole chain.
2. **Email as the notification channel** (user decision). The pre-existing
   entrypoint renders the config from `ALERTMANAGER_*` env vars and
   auto-selects the email-only template when Slack/PagerDuty are unset; with
   no SMTP configured it degrades to log-only instead of crashing.
3. **A 13-alert core (`alerts-core.yml`) instead of re-enabling the 71 legacy
   rules**: ServiceDown, DatabaseDown, RedisDown, DiskSpaceCritical,
   ContainerMemoryNearLimit, ContainerRestartLoop, HighErrorRate,
   SSELatencyP95High, BackupFailed, PublicEndpointDown, CertificateExpirySoon,
   AlertmanagerDown, ObservabilityScrapeTargetMissing. Every alert annotates
   its runbook (`docs/runbooks/alerts/<Name>.md`). Thresholds are
   `ALERT_CORE_*` variables in `thresholds/{env}.env` (parameterizable = .env,
   project rule), and **descriptions reference the same template variables as
   expressions** so they can never drift apart again.
4. **blackbox-exporter** (64M/0.1 cpu) probes what no existing exporter sees:
   the backup sidecar's healthcheck webhook (`BackupFailed`) and the public
   URL end-to-end through Cloudflare edge → cloudflared tunnel → web
   (`PublicEndpointDown`, `CertificateExpirySoon`). The public target is
   injected at container start from `BLACKBOX_PUBLIC_PROBE_URL` (.env) into a
   file_sd file — the real domain never lands in the open-source repo; empty
   variable = probe disabled (dev default).
5. **Directory consolidation**: Alertmanager config unified under
   `infrastructure/observability/alertmanager/` (infra config does not belong
   to the API app); the orphaned copy deleted; the never-loaded custom alert
   files moved to `infrastructure/observability/prometheus/alerts/`; the 22
   one-shot scripts/archives deleted (recoverable from git history).

## Consequences

- Any core alert firing sends an email within ~1–5 minutes
  (`group_wait` 10s–1m + SMTP); resolution emails confirm recovery.
- The alerting chain is fully versioned and reproducible: rules are rendered
  by `prepare_config.sh`, validated by `promtool check rules` and unit-tested
  by `promtool test rules` (`tests/alerts_core_test.yml`).
- The 71 legacy rules remain available as templates but **must have their
  thresholds recalibrated before any group is re-added to `rule_files`**
  (tracked in README_PROMETHEUS_THRESHOLDS.md).
- Assumed limitation: if Alertmanager itself is down, `AlertmanagerDown` fires
  but cannot email (Alertmanager is the mailer). It is visible in the
  Prometheus UI and the logwatch digest. An external dead-man's-switch
  (e.g. healthchecks.io watchdog) is the documented future hardening.
- The SSE latency threshold (60s p95 TTFT) is set above the measured
  production baseline to detect *degradation*; it must be tightened after the
  latency-optimization work lands.

## Amendment 2026-10-18 — the digest reads what fired; a p95 needs observations

Measured on production for the report covering 2026-10-17. The alerting chain
worked end to end (31 rules healthy, no notification failure, 18 emails and 18
webhook deliveries that day), but the two consumers around it did not say so:

1. **The daily digest read no alert.** Its Docker section described the host
   at 06:25 — container states, `RestartCount`, one `docker stats` sample — so
   a demonstrator API that restarted about 2 050 times under a critical
   `ContainerRestartLoop` for six and a half hours read « Aucun redemarrage.
   Tout est stable. » (the container had been recreated since), and the
   « maximum 61 % » memory figure was one container at 06:25:30. Its tunnel
   section counted log LINES with patterns written for QUIC (two lines per
   failed request, client cancellations as errors, « requests » matching the
   failure lines, a registration pattern with its words in the wrong order).
   The digest now opens on a « Supervision LIA » section read from the systems
   that recorded the window — the alerts Prometheus fired, the chain's own
   health, the alerts active now, the incidents still open, container restarts
   and recreations, memory peaks, probe failures —, each source named when it
   cannot be read (`infrastructure/logwatch/scripts/services/lia-supervision`).
   The tunnel section counts each failed request once, by side, and reads
   traffic and HTTP codes from cloudflared's own counters. It reads the tunnel's
   journal itself (`journalctl --output=short-iso` over the report window,
   `LogFile = none`): fed through a logfile group, it received what logwatch's
   `*ApplyStdDate` makes of an ISO line — a syslog date without a year — so one
   outage of three minutes printed 27 periods, and on a day the journal stayed
   empty the whole section, « Service : failed » included, was absent. A section
   whose source recorded none of the window says « aucune mesure », and the
   share it recorded when it recorded part of it: no sample is never « no
   restart », « every probe answered » or « no alert fired ». The unit tests
   that import these extensionless scripts write no bytecode, the bundle prunes
   any, and `deploy.sh` installs the scripts' regular files only — a
   `__pycache__` left beside them made `cp` exit 1 and stopped the deployment at
   step 4/7. The consequence above (« visible in the Prometheus UI and the
   logwatch digest ») is true only from this amendment on.
2. **`SSELatencyP95High` measured nobody's wait.** Every out-of-turn run
   streamed through the chat code and fed the TTFT histogram; three morning
   routines did so with one or two observations per ten minutes, each above
   90 s, and the alert fired every morning from 2026-09-19 on. Only a turn a
   person waits for is observed now (`streaming/latency_sli.py`, declared per
   run by the out-of-turn funnel), and the rule evaluates only over
   `ALERT_CORE_SSE_TTFT_MIN_OBSERVATIONS` turns: below `1 / (1 - 0.95)`
   observations a histogram's p95 IS its slowest observation. Production's
   chat traffic peaks far below that, so on that instance the alert stays
   silent by construction — the price of a quantile that means what it says.
