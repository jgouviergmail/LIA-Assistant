# Self-Diagnostics & Platform Health

## Can LIA monitor itself?
Yes — since v1.34 (ADR-247), LIA reads its own telemetry. A periodic self-check evaluates the platform's golden signals (error rate, latency, LLM failures, disk, memory) plus direct probes of PostgreSQL, Redis, its own loop and — when an administrator configures a target — the platform's outbound connectivity, and stores health snapshots with exact measured values, each with the unit the server declares. This works even while the monitoring stack itself is down: the probes keep running, and the affected checks honestly report "unknown" instead of guessing.

## Where do administrators see the platform's health?
In **Settings > Platform health** (administrators only): the latest self-check with per-check verdicts and exact values, currently firing alerts, degraded capabilities with their suggested fallbacks, and the incident history with stored diagnoses. When a critical incident opens, administrators are also notified in-app and by push — never by e-mail, since the alerting stack already e-mails.

## What is the incident memory?
Every outage becomes exactly ONE incident: alerts delivered by the monitoring stack and critical self-check verdicts converge on the same incident when they describe the same problem. An incident records its evidence (exact values, alert annotations), its lifecycle (open → resolved), and optionally an automatic diagnosis.

## How are incidents diagnosed?
A dedicated, budget-capped LLM step reads the incident's evidence and the operations runbook written for that alert, then stores a diagnosis: what is happening, the probable cause, and recommended actions. Those recommendations are proposals for a human administrator — nothing is ever executed from the model's text, and a daily cost cap (configurable, 0 disables the step) bounds the spend; the cap is checked before every call, not once per incident.

The evidence handed over carries the measured value together with the unit, the verdict and the two alert thresholds it was compared against. Before v1.38.3 it carried a number and nothing else, and the diagnoses said so — "insufficient evidence to determine the exact cause" was an accurate answer, because a value with no threshold beside it cannot be judged: 46 is an incident for one check and unremarkable for another.

## What language is a diagnosis written in?
The language of each administrator who reads it. A diagnosis is produced by a scheduler tick that has no reader to ask, so it is written at that moment in the languages the instance's administrators actually read — with a single administrator, the normal case for a self-hosted instance, that is exactly one model call in the right language. A reader whose language was not among them still sees the diagnosis rather than a blank panel, and the interface says which language it is in.

## What happens when the embedding provider refuses a call?
Embeddings are what store a conversation in memory, index a message and retrieve a document context, and until v1.38.3 a refusal was silent: the answer arrived normally, merely less well informed. Three mechanisms now cover it, with three distinct roles. Background jobs start at staggered times instead of together, because interval jobs whose periods share a divisor align forever — measured in production, six of them fired inside the same second every hour, which is what produced 11 failures out of 24 calls in an hour with one to three active users. A short-window shaper covers growth in usage; it is never a gate, its wait is bounded, and a caller that waited its share proceeds anyway. And a bounded retry covers what is left, on transient provider errors only. All three are configurable, and setting `EMBEDDING_RATE_LIMIT_MAX_CALLS=0` disables the shaper entirely without costing a Redis round-trip.

## Can I ask LIA to diagnose itself in chat?
Yes, if you are an administrator: ask "diagnose yourself" or request a specific platform metric, recent service logs, or an incident's diagnosis. Four read-only tools answer: current health, a curated metric catalogue (free-form query languages are deliberately not accepted), bounded log excerpts, and the incident list. Non-administrators are refused.

## Does this change anything for regular users?
Yes, one thing: honesty under failure. When a step fails during a request, LIA now explains precisely what succeeded, what failed and why — from typed error codes, never raw logs — and applies a known workaround when one exists (for example switching web-search provider when one is down) instead of failing on a timeout.

## How do I enable it on my own server?
Set `DIAGNOSTICS_ENABLED=true` in your `.env`. It is off by default, and with the flag off the subsystem does not exist at runtime. The telemetry sources (Prometheus, Loki, Alertmanager) are optional individually: an empty URL disables a source, and an install without the observability stack keeps working unchanged. To turn alerts into in-app incidents, also set the webhook secret and URL (`DIAGNOSTICS_WEBHOOK_SECRET`, `ALERTMANAGER_LIA_WEBHOOK_URL`) — the alerting container then notifies LIA on every firing and resolved alert.

## Is every metric LIA produces actually visible somewhere?
Yes, and that is checked automatically rather than assumed. A metric no dashboard, recording rule or alert refers to is a metric nobody can act on — which is not hypothetical: a context source failing silently once dropped the heartbeat's health signals on 46.5 % of ticks for a week, with no metric to notice it. Since v1.38.0 a build-time check compares every metric defined in the code against every dashboard panel, rule and alert expression. The metrics that reach nothing are listed explicitly, and that list can only get shorter: a newly blind metric fails the build, and a metric that becomes visible must leave the list. At the time of writing, 507 metrics are defined and 57 of them reach nothing — and that list can only get shorter.
