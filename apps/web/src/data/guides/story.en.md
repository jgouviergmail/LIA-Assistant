# Directing an AI That Codes

> Field report — a complete system, from design to production.

**Version**: 1.9
**Date**: 2026-08-23
**Application**: LIA v1.42.1
**License**: AGPL-3.0 (Open Source)

---

## 1. The essentials

LIA is a complete multi-agent AI assistant — business connectors, voice, memory, user-to-user connections, six languages — designed, built and continuously operated in production, as a personal project.

Nearly all of the code was written by an AI, under human direction: a written engineering rulebook, blocking automated checks, systematic review, recurring audits. The result is measured: **8.3/10** on a technical audit across 24 areas. The repository is open source; the audit's conclusions — strengths and weaknesses alike — are owned and summarized in this document.

| Indicator | Value |
| --- | --- |
| Code written by an AI — directed, framed, controlled | **≈ 100%** |
| Lines of code (excluding tests) — 44 functional domains | **580,000** |
| Automated tests, run on every commit and release | **31,300+** |
| Documented architecture decisions (ADR) | **263** |
| Versions shipped at a steady pace | **246** |
| Languages, parity checked automatically | **6** |
| Technical audit across 24 areas | **8.3/10** |

Conviction from experience: AI-assisted development can be industrialized today. The limiting factor is not the tool — it is the management framework you give it.

## 2. The approach

Generative AI transforms both what teams produce and how they produce it. On both topics, I did not want to base my convictions on market narratives: I chose to face the full reality of an AI system in production — costs, risks, operations, debt — and the reality of AI-assisted development, by practicing them end to end.

The training ground: LIA, a multi-agent conversational AI assistant — mail, calendar, contacts and files across Google, Apple and Microsoft, real-time voice interface, long-term memory, document search, an animated character that embodies it — self-hosted and multilingual.

The constraints were deliberate: alone, outside professional hours, minimal hardware budget, and the AI as the only developer. This project therefore does not measure individual velocity; it measures what demanding direction obtains from a properly framed AI.

*Technical foundation: FastAPI · Next.js/React · LangGraph (agent orchestration) · PostgreSQL · Redis · Docker · Prometheus/Grafana/Loki/Tempo · 7 integrated AI model providers.*

## 3. The method

An AI that codes produces volume; it only produces quality under constraint. Four mechanisms carried this project — none of them is a tool, all four are acts of management:

- **A written rulebook, as for a team.** Architecture rules, conventions, mandated patterns with their canonical example in the code, documented known traps — versioned in the repository, enforceable on every delivery.
- **Blocking automated checks.** Every structural rule is backed by a check that rejects non-compliant commits: strict typing, static analysis, custom detection of recurring bug patterns, six-language parity, a full test battery. The level of rigor depends neither on the vigilance of the moment nor on the AI's goodwill.
- **A review that decides.** Nothing lands without an enforced cycle — impact analysis, proposal, explicit validation, implementation, verification. The AI proposes, the human decides; structural decisions are recorded and indexed so that every "why" outlives its author.
- **Audits that disturb.** At regular intervals, the entire system is re-examined adversarially — findings verified against evidence, false positives eliminated, remediation planned in waves. This is what stops the slow drift that no day-to-day review can detect.

> Speed comes from the AI. Quality comes from the framework. And the framework is management work.

## 4. The trade-offs

Three structural decisions, among the 263 documented:

**Sovereignty & reversibility — no irreversible vendor dependency.** AI models (OpenAI, Anthropic, Google, DeepSeek, Qwen, Perplexity, local models via Ollama) sit behind a single abstraction: any usage can switch provider through configuration, with cost comparison. The same principle applies to business services: Google, Apple and Microsoft are interchangeable per functional category. Hosting is fully controlled; personal data is encrypted and stays on the infrastructure.

**AI economics — cost per request is a design criterion.** Two execution modes coexist: a deterministic, economical pipeline for everyday requests, and an autonomous agent mode for exploratory ones — the measured consumption gap ranges from 1 to 4-8×, for equivalent service on standard cases. Every call is counted per token, valued in euros, aggregated per user and per model, governed by quotas.

**Risk control — no irreversible action without human validation.** Six levels of human control, graded by the sensitivity of the action — from clarification to confirmation of destructive operations. Behavior on interruption is specified and tested: a pending validation survives restarts, with no loss and no double execution.

## 5. Operations

A system flown on instruments:

- **Observability**: twenty-six dashboards — application health, service commitments, AI costs, agent behavior, infrastructure. More than 490 metrics; centralized structured logs with personal-data filtering; end-to-end distributed tracing. Some forty written operating procedures — diagnosis, remediation, restoration. And the assistant reads that telemetry itself: a periodic self-check, an incident memory diagnosed against those very procedures, and answers that route around a known outage.
- **Delivery**: containerized deployment, automated schema migrations, images published for two hardware architectures (amd64/arm64).
- **Costs**: frugal infrastructure by choice — about €150 of hardware, zero licenses, open-source building blocks sized to actual needs.
- **Compliance**: security reviewed endpoint by endpoint; personal data encrypted; account lifecycle aligned with the GDPR.

## 6. The proof

The level claimed in this document comes from a complete technical audit: 24 areas scored, every finding verified in the code and cross-checked to eliminate false positives. The audit applies the project's own method — conducted with AI tooling, in an adversarial posture, every conclusion anchored in cross-checked evidence. Latest assessment: **8.3/10**, with a profile openly acknowledged. The full report — scorecard, method, open findings and the protocol to reproduce it — is public: [full audit report](https://github.com/jgouviergmail/LIA-Assistant/blob/main/docs/audit/README.md).

**Confirmed strengths:**

- Solid data layer: complete referential integrity, migrations without breakage, controlled concurrent access.
- Complete observability and quality tooling, genuinely used day to day.
- Decision traceability and delivery discipline sustained over the entire duration.

**What remains to be done — known, planned:**

- Backups: encryption and off-site copies — the daily automation itself is in production and verified.
- Alerting: recalibrating the historical alert thresholds — the critical core is active and proven end to end, e-mail included.
- Continuing the decomposition of the densest components, now driven by measurement (complexity, coupling) — the backend's main monoliths are done.

The action plan is organized in waves, each with measurable exit criteria. That is how this project reports on itself: not a proclaimed level, a measured one — gaps included.

That requirement carries a consequence the project learned the hard way: **a green test suite does not prove a feature works**. It proves that what was tested behaves as written. The defects that survive the gates are exactly the ones the gates were never asked about — a capability nobody calls, a figure nobody adds up, a guard that recognises a name rather than a mechanism.

Hence a working rule: **nothing is believed until it has run**, against real data and along the path a user takes. A component can be correct and its page empty; a counter can be exact and its question wrong. Every release therefore ends with an adversarial review, conducted cold, whose purpose is not to run the tests but to look for what they do not cover.

What that review produces does not stop at the fix. Every defect found leaves behind a **structural guard** — a start-up check, a continuously verified invariant, a test that fails if the whole class of problem reappears. It is the only kind of progress that outlives the person who wrote it: a fix protects one line, a guard protects the rule.

---

## 7. Convictions

What this experience changes in a management practice:

- **AI-assisted development is deployed as a management system, not as a tool.** Productivity gains are real and significant; they only last if the framework — rulebook, checks, review, audit — is installed before generalization. That is the order in which to introduce it in an organization.
- **The economic governance of AI is decided at usage-design time.** Two architectures delivering the same service can differ by a factor of 4 to 8 in consumption: that choice belongs to technical leadership, upstream — bill control always arrives too late.
- **Between blanket prohibition and blind trust, there is a governable path.** Graded human control can be specified, tested and audited; it is the approach regulatory requirements are converging on, and it is operational today.
- **A leader who practices arbitrates better.** Build or buy, acceptable debt or not, credible vendor promise or not — these decisions gain accuracy when you have worked the material yourself. This project is a way of maintaining that proximity to the field.

*Personal project, carried out outside any professional activity. Figures from the July 2026 technical audit — tests executed, measurements taken on the code, findings cross-checked. Repository: [github.com/jgouviergmail/LIA-Assistant](https://github.com/jgouviergmail/LIA-Assistant).*
