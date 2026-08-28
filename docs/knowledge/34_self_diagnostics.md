# Self-Diagnostics & Platform Health

## Can LIA monitor itself?
Yes — since v1.34 (ADR-247), LIA reads its own telemetry. A periodic self-check evaluates the platform's golden signals (error rate, latency, LLM failures, disk, memory) plus direct probes of PostgreSQL, Redis and its own loop, and stores health snapshots with exact measured values. This works even while the monitoring stack itself is down: the probes keep running, and the affected checks honestly report "unknown" instead of guessing.

## Where do administrators see the platform's health?
In **Settings > Platform health** (administrators only): the latest self-check with per-check verdicts and exact values, currently firing alerts, degraded capabilities with their suggested fallbacks, and the incident history with stored diagnoses. When a critical incident opens, administrators are also notified in-app and by push — never by e-mail, since the alerting stack already e-mails.

## What is the incident memory?
Every outage becomes exactly ONE incident: alerts delivered by the monitoring stack and critical self-check verdicts converge on the same incident when they describe the same problem. An incident records its evidence (exact values, alert annotations), its lifecycle (open → resolved), and optionally an automatic diagnosis.

## How are incidents diagnosed?
A dedicated, budget-capped LLM step reads the incident's evidence and the operations runbook written for that alert, then stores a diagnosis: what is happening, the probable cause, and recommended actions. Those recommendations are proposals for a human administrator — nothing is ever executed from the model's text, and a daily cost cap (configurable, 0 disables the step) bounds the spend.

## Can I ask LIA to diagnose itself in chat?
Yes, if you are an administrator: ask "diagnose yourself" or request a specific platform metric, recent service logs, or an incident's diagnosis. Four read-only tools answer: current health, a curated metric catalogue (free-form query languages are deliberately not accepted), bounded log excerpts, and the incident list. Non-administrators are refused.

## Does this change anything for regular users?
Yes, one thing: honesty under failure. When a step fails during a request, LIA now explains precisely what succeeded, what failed and why — from typed error codes, never raw logs — and applies a known workaround when one exists (for example switching web-search provider when one is down) instead of failing on a timeout.

## How do I enable it on my own server?
Set `DIAGNOSTICS_ENABLED=true` in your `.env`. It is off by default, and with the flag off the subsystem does not exist at runtime. The telemetry sources (Prometheus, Loki, Alertmanager) are optional individually: an empty URL disables a source, and an install without the observability stack keeps working unchanged. To turn alerts into in-app incidents, also set the webhook secret and URL (`DIAGNOSTICS_WEBHOOK_SECRET`, `ALERTMANAGER_LIA_WEBHOOK_URL`) — the alerting container then notifies LIA on every firing and resolved alert.
