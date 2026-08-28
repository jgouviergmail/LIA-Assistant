# Directing an AI That Codes

> Field report — a complete system, from design to production.

**Version**: 1.7
**Date**: 2026-08-23
**Application**: LIA v1.34.0
**License**: AGPL-3.0 (Open Source)

---

## 1. The essentials

LIA is a complete multi-agent AI assistant — business connectors, voice, memory, user-to-user connections, six languages — designed, built and continuously operated in production, as a personal project.

Nearly all of the code was written by an AI, under human direction: a written engineering rulebook, blocking automated checks, systematic review, recurring audits. The result is measured: **8.3/10** on a technical audit across 24 areas. The repository is open source; the audit's conclusions — strengths and weaknesses alike — are owned and summarized in this document.

| Indicator | Value |
| --- | --- |
| Code written by an AI — directed, framed, controlled | **≈ 100%** |
| Lines of code (excluding tests) — 44 functional domains | **580,000** |
| Automated tests, run on every commit and release | **27,600+** |
| Documented architecture decisions (ADR) | **246** |
| Versions shipped at a steady pace | **229** |
| Languages, parity checked automatically | **6** |
| Technical audit across 24 areas | **8.3/10** |

Conviction from experience: AI-assisted development can be industrialized today. The limiting factor is not the tool — it is the management framework you give it.

## 2. The approach

Generative AI transforms both what teams produce and how they produce it. On both topics, I did not want to base my convictions on market narratives: I chose to face the full reality of an AI system in production — costs, risks, operations, debt — and the reality of AI-assisted development, by practicing them end to end.

The training ground: LIA, a multi-agent conversational AI assistant — mail, calendar, contacts and files across Google, Apple and Microsoft, real-time voice interface, long-term memory, document search — self-hosted and multilingual.

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

Three structural decisions, among the 246 documented:

**Sovereignty & reversibility — no irreversible vendor dependency.** AI models (OpenAI, Anthropic, Google, DeepSeek, Qwen, Perplexity, local models via Ollama) sit behind a single abstraction: any usage can switch provider through configuration, with cost comparison. The same principle applies to business services: Google, Apple and Microsoft are interchangeable per functional category. Hosting is fully controlled; personal data is encrypted and stays on the infrastructure.

**AI economics — cost per request is a design criterion.** Two execution modes coexist: a deterministic, economical pipeline for everyday requests, and an autonomous agent mode for exploratory ones — the measured consumption gap ranges from 1 to 4-8×, for equivalent service on standard cases. Every call is counted per token, valued in euros, aggregated per user and per model, governed by quotas.

**Risk control — no irreversible action without human validation.** Six levels of human control, graded by the sensitivity of the action — from clarification to confirmation of destructive operations. Behavior on interruption is specified and tested: a pending validation survives restarts, with no loss and no double execution.

## 5. Operations

A system flown on instruments:

- **Observability**: twenty-six dashboards — application health, service commitments, AI costs, agent behavior, infrastructure. More than 480 metrics; centralized structured logs with personal-data filtering; end-to-end distributed tracing. Some forty written operating procedures — diagnosis, remediation, restoration. And since v1.34, the assistant reads that telemetry itself: a periodic self-check, an incident memory diagnosed against those very procedures, and answers that route around a known outage.
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

The proof also has its most instructive episode: three recalibrations of a simple spacing, three "I see no change" — and a delivery chain proven healthy down to the bytes served to the browser. Two plausible false leads (browser cache, service worker) fell one after the other, until the measurement that forgives nothing: in a driven browser, the margin computed to 16 pixels while the rendered gap was 3. The label primitive had stayed `inline`, and an inline element ignores its vertical margins — the defect predated the whole programme. The fix is one word, the arbitration happened on three real screenshots, and the rule became doctrine: measure the rendering before suspecting the delivery.

The habit-learning detector earned its trust the same way: it was executed against real production data before being believed — and it was caught. A daily scheduled action had been writing a "user" message at 07:00 for sixty-six days; the detector claimed the scheduler's own timetable as a human habit. The refutation became a whitelist of human sessions, the fabricated window disappeared, and the honest verdicts fell into place. The rule stands: prove against reality before believing the design.

The 1.29.0 cycle added a third episode, and this one is about the tests themselves. Every protection in the programme had shipped with its own, all green — and all of the same shape: they pinned what the code did on the day it was delivered. A hand-written list does not describe a system; it describes what its author knew about the system. So three guards were rewritten to **recalculate** the protection from the source of truth instead of restating it. They found three faults no existing test could see: speech synthesis billed and never counted against the spend ceiling, a provider sign-in that bypassed the newly mandatory terms acceptance entirely, and eleven connector paths that bound a real credential with no guard at all. Then each guard was deliberately broken, to check that it goes red — because a guard nobody has ever seen fail is just one more promise.

The 1.30.0 cycle documented a lesson of a different kind: a feature can be delivered, encrypted, consented — and useless, because nobody reads it. The last known position had existed for months; only proactive notifications consulted it. On the move, the assistant therefore answered from the home address, with confidence. The diagnosis came from the production logs, the fix reduced three divergent paths to a single cascade — and the exact-counts doctrine extended to position: a dated position announces itself as dated, "based on your last known position at 9:30", never "you are at". The same cycle recalled that a synchronization mechanism is only believed once proven against the real engine: the lock serializing the first boot deadlocked against PostgreSQL's concurrent index creation — measured in the engine's own lock table, fixed as a non-blocking poll, and guarded by a test that forbids the blocking form's return.

Later in the same cycle, the settings page — the very place all of this is steered from — shed its wall of fifty collapsed accordions for a master-detail shell: a permanent rail of sections, a pane, an overview of cards where every description is finally visible before opening anything, and a search that at last covers administration. The redesign was argued on interactive mockups before a line shipped, and it retired a whole class of drift with it: the page now renders from the same tables that power search and deep links, so a section can no longer exist half-way.

The cycle closed on the surface that is supposed to answer for all the others. The capability map had gone on publishing thirteen entries while six capabilities shipped past it, and the settings hub could say what a section WAS but not what it held. Both were fixed from the same aggregate — nineteen capabilities, one request, the same words on both screens — and the fix that mattered was not the content but the assertion added underneath it: from now on the application refuses to start if a new capability has not decided where it belongs on the map. It is the same lesson as every other one here — a convention degrades, a mechanism does not — applied this time to the page whose only job was to stay true.

Cycle 1.30.1 took the logic one step further: it audited the audit. An internal report concluded that the streamed LLM slots counted zero tokens — exact mechanism, plausible conclusion, maximum severity. The counter-review did what the report could not: it asked production. Five hundred and ten calls out of five hundred and ten were counted. The real defect lay elsewhere, and was more insidious: the accounting rested entirely on the generosity of a provider nobody asked — nothing requested it, nothing tested it, nothing watched it. The answer was not a patch but a contract: every provider declares its accounting mode, the application refuses to start without that declaration, and a paid call without a count becomes an alert. The same cycle repaired the dashboard's actions counter, stuck at zero since forever by a vocabulary nobody emitted — history included, reclassified from the archived intentions. Because a displayed count is exact, or it does not exist.

Cycle 1.30.2 applied the same discipline to what nobody ever looks at: the foundations. Upgrading the orchestration ecosystem past five months of fixes could have been a number swap; it was run as an evidence-first operation — every version validated in a throwaway environment before touching the repo, eight and a half thousand tests executed under the target versions, the private integration points simulated offline. And the audit that came with the upgrade found what coverage metrics were hiding: seventeen hundred and fifty lines of a second, never-wired implementation of human-in-the-loop resumption, kept green by fifty tests. Deleted, with its architecture decision on record. A showcase system is judged not only by what it shows — also by what it refuses to keep.

Cycle 1.30.5 started from a three-line user message: "I asked to relay a message, I got a confirmation, nothing was sent." The investigation — timestamped production logs, database, the container's own code, one proof at a time — traced it to a single line: the execution engine was overwriting every tool's verdict with a hardcoded success, and the honesty layer designed precisely to name blockages was being disarmed by the very lie it existed to prevent. The fix is small; the method is the real deliverable: every hypothesis counter-verified before writing a line, every fix preceded by a failing test, and an assistant that now tells the truth all the way into its refusals — with exact numbers, in all six languages.

Cycle 1.30.6 turned the same discipline outward, toward the standard the entire ecosystem speaks. The Model Context Protocol had just published a revision that makes the protocol stateless — and whose own compatibility matrix condemns older clients in front of new-generation servers. The work was run as a compliance investigation before being a migration: the specification read requirement by requirement, every gap demonstrated by simulation before a single line changed, the new SDK exercised against real servers of both generations. LIA now speaks both — the new stateless revision and the legacy handshake — so every server already configured keeps working unchanged while next-generation ones become reachable; the OAuth flow gained the revision's security obligations, each with an explicit tolerance rule for existing registrations. And declining a consent screen is no longer an error page: it is an answer, acknowledged in six languages.

Cycle 1.30.7 completed the movement: after speaking the ecosystem's wire protocol, speak its package format. The Agent Plugins open standard — steered by AWS, Microsoft, OpenAI, Cursor and Vercel — had just given the whole ecosystem one portable way to ship skills and MCP servers together, and the work followed the now-familiar discipline: the normative text read section by section, every integration hypothesis proven against the code by simulation before a line was written, then a client built almost entirely out of layers LIA already trusted — the hardened skill importer, the per-user MCP registry, the quota system. The review found and killed two real bugs before they ever ran, and the whole lifecycle was proven at runtime against the real database, twice. What shipped is quietly radical: a plugin packaged for ChatGPT or VS Code installs into LIA unchanged, reports exactly what it brought — and what it could not bring, with the reason — and leaves without a trace.

Cycle 1.30.11 produced the most unexpected lesson: designing an export can reveal that the system cannot answer its own question. Administering a hundred and twenty-four AI models one dialog at a time had stopped being tenable, and the idea was simple — export the pricing grid into a workbook, fix it offline, import it back. Writing it, though, required answering "what is this model's tariff?". There was no answer: nothing enforced a single active tariff, and two read paths could return different prices for the same model, at the same instant, on the same database. Two billing errors had been running in production for months with nobody able to see them. Putting it back in order produced a rule that outlives this domain: a migration never invents business data. The intuitive rule — keep the most recent row — proved wrong on all four real cases; so the migration merges what is strictly identical and stops, naming the rest, leaving the arbitration to a human. The delivered file holds the same standard: nothing is deleted implicitly, the preview you approve is the one that gets written, and what did not change is not rewritten.

The 1.31.0 cycle moved the proof requirement onto new ground: aesthetics. Giving the assistant a gaze — two cartoon eyes that watch while you type, squint while it thinks, sweep while it searches and react to the tone of each answer — was first an animation project, where half the success lives in fluidity. The discipline did not change for that: the entire behavior fits in a pure engine fed by signals the application already emitted — the chat state machine, the streamed execution steps, the emotional engine — with no extra model call and no new endpoint, every expression driven by decision tables tested with injected clocks and randomness. And when the user panel could not settle on a style, the arbitration was rendered like every other one: on evidence, an interactive board of styles previewed for real. The winner became the default, the others a settings choice — and adding a new one is a registry entry, not a project.

The same standard accompanied the arrival of the native apps: rather than assuming what a WebView can do, a dedicated bench drives the **real application** on an emulator, scene by scene, from the first screen to forgetting a mistyped server. Before its first green run it had already caught three real defects — including an offline screen that never loaded in the only state where it matters — that compilation, CI and every static guard had blessed.

## 7. Convictions

What this experience changes in a management practice:

- **AI-assisted development is deployed as a management system, not as a tool.** Productivity gains are real and significant; they only last if the framework — rulebook, checks, review, audit — is installed before generalization. That is the order in which to introduce it in an organization.
- **The economic governance of AI is decided at usage-design time.** Two architectures delivering the same service can differ by a factor of 4 to 8 in consumption: that choice belongs to technical leadership, upstream — bill control always arrives too late.
- **Between blanket prohibition and blind trust, there is a governable path.** Graded human control can be specified, tested and audited; it is the approach regulatory requirements are converging on, and it is operational today.
- **A leader who practices arbitrates better.** Build or buy, acceptable debt or not, credible vendor promise or not — these decisions gain accuracy when you have worked the material yourself. This project is a way of maintaining that proximity to the field.

*Personal project, carried out outside any professional activity. Figures from the July 2026 technical audit — tests executed, measurements taken on the code, findings cross-checked. Repository: [github.com/jgouviergmail/LIA-Assistant](https://github.com/jgouviergmail/LIA-Assistant).*

Then the assistant learned to show its own work: an Activity page listing everything it does on its own, learned rules you can read and correct, a memory that dates its recollections and archives without erasing, a voice that breathes with its mood. Autonomy grew exactly as the project's philosophy demanded: inside the frame, under the user's gaze.

Then the assistant fit into a pocket without moving out of its home. One app per store, a client for whichever server its user runs: sign-in through the phone's real browser because the embedded one is refused, notifications that either come from the user's own project or pass through a relay built to know nothing, and a bench that drives the real app scene by scene — which found three live defects the compiler had blessed. The sovereignty thesis survived contact with the app stores: the data still has one home.
