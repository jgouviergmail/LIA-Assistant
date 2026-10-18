# Self-Diagnostics & Platform Health

## Can LIA watch over its own health?

Yes, once the operator has turned **self-diagnostics** on — it is off by default, and the guided installer asks.

**🩺 What it checks, on a regular cycle:**
• the server's error rate and response time
• how often the AI models and the embedding service fail
• disk and memory use
• the database, the cache and its own check loop
• services temporarily set aside after repeated failures
• whether the server can still reach the outside, when the operator names a target

Every verdict keeps its exact measured value. If the monitoring stack is down, the checks that depend on it say **Unknown** instead of guessing, while the direct ones keep running.

Administrators read it all in **Settings › Administration › Platform health**: the latest check, the alerts firing, the degraded capabilities with their suggested fallback, and the incident history.

## What is an incident, and how is it diagnosed?

**📒 One problem, one incident:**
Critical self-check results and, when the instance runs a monitoring stack, its alerts converge on a single incident when they describe the same problem. It keeps its evidence and its lifecycle, from open to resolved. An incident born of an alert closes when the alert resolves; if that news gets lost on the way, LIA sees that the monitoring stack no longer reports the alert and closes the incident after a delay the operator sets (an hour by default) without news, recording it in the incident's history. When a critical one opens, administrators are notified in the app, on their devices and on the external channels they linked — never by e-mail, which the alerting stack already sends.

**🔬 The diagnosis:**
A dedicated model, with its own role in LLM Configuration, reads the evidence and the operations runbook written for that alert, then writes what is happening, the probable cause and recommended actions. Those are proposals for a person: nothing is ever executed from them. A daily budget the operator sets bounds the spend and is checked before every call; at zero, no diagnosis is written.

**🌍 Its language:**
It is written in the languages the instance's administrators read. If yours is not among them, you still see it, with a note saying which language it is in.

## What does the platform diagnostician read before it diagnoses an incident?

In **Settings › Administration › Platform health**, each incident's diagnosis is written from the incident itself — the check, its measured value and thresholds — and from an evidence pack gathered at the moment of the diagnosis:
• **Breakdown metrics** over the incident's window — which outcome, status or refusal reason moved, and by how much
• **A bounded log excerpt** — recent error lines counted by event, personal data removed
• **The running build** and how long it has been up, so a recent deployment is visible
• **The operations runbook** written for that alert

**Each source stands on its own:** one that cannot be reached is named as unavailable in the diagnosis, never read as "nothing happened". If no runbook is installed with the API, the panel says so.

Under every diagnosis, **What the diagnostician read** shows exactly that pack, so you can check the text against its evidence.

## Can I ask LIA to diagnose itself in the chat?

Yes, if you are an administrator and self-diagnostics is on. For example:
• *Diagnose yourself*
• *Are there any open incidents?*
• *Show me the API's recent errors*

LIA answers with four read-only lookups: the current health, a curated list of platform measurements (no free-form query language), bounded excerpts of the service logs, and the incident list. It changes nothing, and the number of lookups over a period is limited.

For anyone else, LIA declines: platform health is an administrator's view.

## Does self-diagnostics change anything for regular users?

One thing, quietly. When a service is known to be down — a web-search provider, a weather provider, the browser — LIA is told before it plans, so it can go around the outage instead of discovering it through a timeout. Where a real alternative exists, such as the other web-search provider, it is suggested; whether you can use it still depends on your connectors and on what the instance offers.

What does not depend on self-diagnostics: when a step fails, LIA always tells you which one, what it answered and what succeeded anyway — on every instance.

## How do I enable it on my own server?

Answer yes to the self-diagnostics question of the guided installer, or set `DIAGNOSTICS_ENABLED=true` in your `.env`. It is off by default, and with the flag off the subsystem does not exist at runtime.

The telemetry sources (Prometheus, Loki, Alertmanager) are optional individually: an empty URL disables a source, and an install without the observability stack keeps working, with the direct checks only. To turn alerts into incidents, the alerting container needs LIA's webhook (`DIAGNOSTICS_WEBHOOK_SECRET`, `ALERTMANAGER_LIA_WEBHOOK_URL`); when you choose both the monitoring stack and self-diagnostics in the installer, it wires the webhook for you.

## What happens when the embedding provider refuses a call?

Embeddings are what store a conversation in memory, index a message and retrieve a document's context, so a refused call is not left silent. Three mechanisms cover it, each with its own role:
• background jobs start at staggered times rather than all in the same second, so their calls do not arrive as one burst
• a short-window shaper smooths what remains; it is never a gate — its wait is bounded, and a caller that waited its share proceeds anyway
• a bounded retry covers transient provider errors only

All three are configurable, and `EMBEDDING_RATE_LIMIT_MAX_CALLS=0` disables the shaper entirely. The embedding failure rate is one of the self-checks above.

## Is every metric LIA produces actually visible somewhere?

Yes, and it is checked automatically when LIA is built rather than assumed: every metric defined in the code must be read by a dashboard panel, a recording rule or an alert. The few that are not yet are listed explicitly, and that list can only get shorter — a newly blind metric fails the build. A metric nobody can see is a metric nobody acts on.
