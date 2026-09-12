<p align="center">
  <img src="docs/assets/logo.png" alt="LIA — Your life. Your AI. Your rules." width="600" />
</p>

<h1 align="center">LIA</h1>

<p align="center">
  <strong>A self-hosted, multi-agent conversational assistant — LangGraph orchestration, Human-in-the-Loop before every mutation, transparency registers, enterprise observability, six languages.</strong>
</p>

<p align="center">
  <strong>If you find this project valuable, a star on GitHub is the best way to say so. Thank you!</strong>
</p>

<p align="center">
  <a href="https://lia.jeyswork.com/"><img src="https://img.shields.io/badge/🚀_Try_LIA-lia.jeyswork.com-0EA5E9?style=for-the-badge" alt="Try LIA"></a>
  &nbsp;&nbsp;
  <a href="https://github.com/jgouviergmail/LIA-Assistant/stargazers"><img src="https://img.shields.io/github/stars/jgouviergmail/LIA-Assistant?style=for-the-badge&logo=github&label=Star&color=gold" alt="GitHub Stars"></a>
</p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.14-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.14"></a>
  <a href="https://nodejs.org/"><img src="https://img.shields.io/badge/Node.js-24%20LTS-5FA04E?style=flat-square&logo=nodedotjs&logoColor=white" alt="Node.js 24 LTS"></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-0.136.3-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI"></a>
  <a href="https://nextjs.org/"><img src="https://img.shields.io/badge/Next.js-16-000000?style=flat-square&logo=nextdotjs&logoColor=white" alt="Next.js 16"></a>
  <a href="https://langchain-ai.github.io/langgraph/"><img src="https://img.shields.io/badge/LangGraph-1.2.11-FF6F00?style=flat-square" alt="LangGraph"></a>
  <a href="https://python.langchain.com/"><img src="https://img.shields.io/badge/LangChain-1.3.15-4B8BBE?style=flat-square" alt="LangChain"></a>
  <a href="#talk-to-it"><img src="https://img.shields.io/badge/i18n-6%20languages-E040FB?style=flat-square" alt="6 languages"></a>
  <a href="docs/audit/README.md"><img src="https://img.shields.io/badge/360%C2%B0%20audit-8.3%2F10-2E7D5B?style=flat-square" alt="360° technical audit: 8.3/10 on the normalized 24-area grid — full public report"></a>
  <a href="#license"><img src="https://img.shields.io/badge/License-AGPL--3.0-blue?style=flat-square" alt="License"></a>
  <a href="https://deepwiki.com/jgouviergmail/LIA-Assistant"><img src="https://deepwiki.com/badge.svg" alt="Ask DeepWiki"></a>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#administration--monitoring">Admin & Monitoring</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#documentation">Documentation</a> •
  <a href="#contributing">Contributing</a> •
  <a href="CHANGELOG.md">Changelog</a>
</p>

<p align="center">
  <strong>Version 1.44.4</strong> — <strong>An answer you keep is yours.</strong> A bookmark on every answer copies it out of the conversation, with your request and its date; kept answers have their own tab, and a new account starts with the connectors that ask nothing of it — 12 September 2026.
</p>

---

## Table of Contents

- [What is LIA?](#what-is-lia)
- [Try LIA Online](#try-lia-online)
- [Built by an AI, Directed by a Human](#built-by-an-ai-directed-by-a-human)
- [Screenshots](#screenshots)
- [Features](#features)
- [Administration & Monitoring](#administration--monitoring)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Technologies](#technologies)
- [Quality: Tests, CI/CD, Security](#quality-tests-cicd-security)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [Support](#support)
- [License](#license)
- [Acknowledgments](#acknowledgments)

---

## What is LIA?

LIA is a personal assistant you host yourself. It reads your mail, calendar, contacts, tasks and documents through your own Google, Apple or Microsoft account, listens and speaks in six languages, acts on your behalf — never changes anything without asking first — and keeps a record of everything it did, read and decided.

Under the hood: a FastAPI backend orchestrating 20+ specialised agents with LangGraph, a Next.js front end, PostgreSQL + pgvector and Redis, and a multi-provider LLM layer that runs as well on a cloud model as on a local one through Ollama.

```
📅 "Find my meetings for tomorrow and send a reminder to all participants"
📧 "Summarize my unread emails from this week that have attachments"
👥 "Update the companies of my contacts who work at startups"
🔔 "Remind me tomorrow at 9am to call Marie for her birthday"
```

| The usual problem              | What LIA does about it                                                                                                                                                       |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Opaque LLM spend**           | Tokens are accounted per node and per provider; an account quota and an instance-wide daily ceiling both apply; prices live in an admin catalogue; everything exports to CSV |
| **Actions nobody can audit**   | Human-in-the-Loop before any mutation, and three registers — what was done, what was read, what was decided — sealed per account on request                                  |
| **Fragmented integrations**    | One orchestration over 20+ agents, Google / Apple / Microsoft connectors, your own MCP servers, skills, plugins and sub-agents                                                |
| **Operations in the dark**     | Prometheus, Grafana, Loki, Tempo and Langfuse, a vital alert core with runbooks, and a self-diagnosis written in the administrator's language                                 |
| **Vendor lock-in**             | Seven LLM providers with local models as first-class citizens, self-hosted on anything from a Raspberry Pi to a server, AGPL-3.0                                             |

---

## Try LIA Online

LIA is hosted at **https://lia.jeyswork.com/** — no installation required.

The [interactive showroom](https://lia.jeyswork.com/demo) runs six guided synthetic missions, one per differentiating mechanism: orchestration under approval, proactivity, persistent memory, outbound calls, rich replies and in-app configuration. Approve, edit or refuse each prepared change through the real approval UI, and read LIA's closing reply rendered by the production pipeline. Everything is labelled synthetic — no account, model or external service is contacted — and a proof drawer links every visible capability to its exact source.

> **Closed beta** — access is granted at the administrator's discretion. To request an invitation, write to **liamyassistant@gmail.com**.

Self-hosting starts at the [Quick Start](#quick-start) below.

---

## Built by an AI, Directed by a Human

> _"Speed comes from the AI. Quality comes from the framework."_

Nearly **100% of this codebase was written by an AI**, under human direction: a written
engineering rulebook, blocking automated checks, systematic review, adversarial audits.
The result is measured, not proclaimed:

|                           |                                         |                             |                                                                         |
| ------------------------- | --------------------------------------- | --------------------------- | ----------------------------------------------------------------------- |
| **49** functional domains | **660,000** lines of code (excl. tests) | **36,000+** automated tests | **281** ADRs                                                           |
| **257** versions shipped  | **6 languages**, parity enforced in CI  | **553** Prometheus metrics  | [**8.3/10** technical audit, 24 normalized areas](docs/audit/README.md) |

- **The full story** — method, trade-offs, results and what remains to be done, weaknesses included: [lia.jeyswork.com/story](https://lia.jeyswork.com/story)
- **The audit itself** — 24 normalized areas mapped to ISO/IEC 25010:2023, every score backed by executed evidence, open worksites included, with the protocol and the full standalone report: [docs/audit/](docs/audit/README.md)

---

## Screenshots

<p align="center">
  <img src="docs/assets/screenshot-homepage.png" alt="Dashboard — Homepage with usage statistics" width="800" />
  <br /><em>Dashboard — Homepage with quick access, usage statistics, and personalized greeting</em>
</p>

<p align="center">
  <img src="docs/assets/screenshot-chat.png" alt="Chat — Multi-agent conversation with debug panel" width="800" />
  <br /><em>Chat — Multi-agent conversation with real-time debug panel (right sidebar)</em>
</p>

<details>
<summary><strong>More screenshots</strong></summary>

<p align="center">
  <img src="docs/assets/screenshot-chat-debug-panel.png" alt="Chat — Debug panel detail" width="800" />
  <br /><em>Chat — Debug panel: per-message routing, tool calls, token cost and reasoning timeline</em>
</p>

<p align="center">
  <img src="docs/assets/screenshot-chat-interactive-skills.png" alt="Chat — Interactive skill widgets" width="800" />
  <br /><em>Chat — Interactive skill widgets: maps, dashboards, calendars and mini-apps rendered inline</em>
</p>

<p align="center">
  <img src="docs/assets/screenshot-settings-preferences.png" alt="Settings — Preferences (connectors, MCP, themes)" width="800" />
  <br /><em>Settings — Preferences: connectors, MCP servers, language, timezone, and themes</em>
</p>

<p align="center">
  <img src="docs/assets/screenshot-settings-features.png" alt="Settings — Features (memory, interests, notifications)" width="800" />
  <br /><em>Settings — Features: LIA Style, long-term memory, interests, proactive notifications, scheduled actions, sub-agents, channels</em>
</p>

<p align="center">
  <img src="docs/assets/screenshot-settings-features-memory.png" alt="Settings — Long-term memory" width="800" />
  <br /><em>Settings — Long-term memory: pinned facts, automatic extraction, edit / delete / pin per memory</em>
</p>

<p align="center">
  <img src="docs/assets/screenshot-settings-features-psyche.png" alt="Settings — Psyche Engine" width="800" />
  <br /><em>Settings — Psyche Engine: Big Five personality traits modulating the assistant's emotional responsiveness</em>
</p>

<p align="center">
  <img src="docs/assets/screenshot-settings-administration.png" alt="Settings — Administration panel" width="800" />
  <br /><em>Settings — Administration: LLM config, RAG Spaces, users, connectors, pricing, skills, voice, broadcast, debug</em>
</p>

<p align="center">
  <img src="docs/assets/screenshot-settings-administration-oneclick.png" alt="Settings — One-click administration" width="800" />
  <br /><em>Administration — One-click simplicity: every admin action is accessible in a single click, no technical skills required</em>
</p>

<p align="center">
  <img src="docs/assets/screenshot-settings-administration-llm.png" alt="Settings — LLM Configuration with multi-provider support" width="800" />
  <br /><em>Administration — LLM Configuration: 7 providers (OpenAI, Anthropic, Google Gemini, DeepSeek, Qwen, Perplexity, Ollama), per-node model selection</em>
</p>

<p align="center">
  <img src="docs/assets/screenshot-faq.png" alt="FAQ — Searchable help center" width="800" />
  <br /><em>FAQ — Searchable help center with categorized Q&A sections</em>
</p>

</details>

---

## Features

Every capability below is documented in an architecture decision record (ADR) or a technical document — the links lead there.

### Talk to it

- **A chat that streams** — answers arrive over SSE with rich HTML cards, interactive widgets and a per-message cost badge; images and PDFs can be attached (vision analysis, text extraction, strict per-user isolation); long conversations are compacted by an LLM summary that preserves identifiers, and the history scrolls back page by page without limit.
- **Voice, both ways** — push-to-talk or the wake word "OK Guy", detected in the browser by sherpa-onnx so no audio leaves the device for detection; offline Whisper transcription in the user's own language; spoken answers from a catalogue-driven TTS (Edge, free; OpenAI; ElevenLabs) streamed sentence by sentence, first audio in about a second ([VOICE](docs/technical/VOICE.md), [ADR-081](docs/architecture/ADR-081-Voice-TTS-Catalogue-Driven.md), [ADR-082](docs/architecture/ADR-082-Progressive-Sentence-Streaming.md)).
- **An expressive face** — twenty expressions derived from the chat, voice and approval state machines with no extra LLM call; the answer declares its own register and the face plays it; brows, mouth and gaze live in a TypeScript rig with six selectable looks, frozen into static poses under `prefers-reduced-motion` ([ADR-240](docs/architecture/ADR-240-expressive-eyes-widget.md), [ADR-252](docs/architecture/ADR-252-Expressive-Eyes-Animation-Rig.md), [ADR-253](docs/architecture/ADR-253-Per-Turn-Expressivity-Annotation.md), [ADR-264](docs/architecture/ADR-264-Living-Brows-And-Mouth.md)).
- **A psyche of its own** — Big Five traits, a mood space, discrete emotions, a relationship stage and curiosity drives shape word choice and rhythm without ever being announced; a four-chart dashboard, temperament sliders and two reset scopes in Settings ([PSYCHE_ENGINE](docs/technical/PSYCHE_ENGINE.md)).
- **Wherever you are** — six languages end to end (UI, approvals, notifications, Telegram, skills); a bidirectional Telegram channel with OTP linking and localized approval keyboards ([GUIDE_TELEGRAM](docs/guides/GUIDE_TELEGRAM_INTEGRATION.md)); native Android and iOS shells that load *your* server, with native push and the sign-in flow Google permits ([ADR-246](docs/architecture/ADR-246-Native-Push-And-Wake-Relay.md), [GUIDE_MOBILE_ANDROID](docs/guides/GUIDE_MOBILE_ANDROID.md), [GUIDE_MOBILE_IOS](docs/guides/GUIDE_MOBILE_IOS.md)); an offline-capable PWA ([ADR-146](docs/architecture/ADR-146-Offline-PWA.md)).

### Connect your world

- **Mail, calendar, contacts, tasks** — Google (OAuth 2.1 + PKCE), Apple iCloud (IMAP/SMTP, CalDAV, CardDAV) and Microsoft 365 (Graph API, personal and business tenants); one active provider per category, and activating one deactivates its competitor ([OAUTH](docs/technical/OAUTH.md)).
- **Connected from the first day** — the connectors that ask nothing of the person (Wikipedia, page browsing, Google Places, Weather and Environment) are activated when the account is created, unless the administrator switched one off or the instance has no platform key; existing accounts keep their choices ([CONNECTORS_PATTERNS](docs/technical/CONNECTORS_PATTERNS.md)).
- **Documents, places and weather** — Google Drive folders and a Gmail label as knowledge sources, synced incrementally ([ADR-262](docs/architecture/ADR-262-Opt-In-Mail-Label-RAG-Source.md)); Google Maps places, routes and geocoding; weather with change detection; a last-known-position cascade so every feature knows where you are, with the age of the fix stated ([ADR-219](docs/architecture/ADR-219-Derniere-Position-Connue-Generalisee.md)).
- **Home and body** — Philips Hue lighting by voice (rooms, scenes, local bridge or cloud); daily steps and heart-rate batches pushed from an iPhone Shortcut, idempotently, with baselines, variation detection and charts ([ADR-076](docs/architecture/ADR-076-Health-Metrics-Ingestion.md), [ADR-148](docs/architecture/ADR-148-Health-Daily-Rollup.md), [GUIDE_IPHONE_SHORTCUTS_HEALTH](docs/guides/GUIDE_IPHONE_SHORTCUTS_HEALTH.md)).
- **Your own tools (MCP)** — per-user servers with API key, bearer or OAuth 2.1 authentication (dynamic registration, PKCE), HTTPS-only, SSRF-checked, credentials encrypted; conformant to the protocol's current revision on both halves and reading tool declarations to the letter of JSON Schema 2020-12 ([ADR-224](docs/architecture/ADR-224-Conformite-MCP-2026-07-28-SDK-v2.md), [ADR-255](docs/architecture/ADR-255-MCP-Tool-Declaration-Conformance.md)); MCP Apps rendered as sandboxed widgets behind a CSP airlock ([ADR-098](docs/architecture/ADR-098-CSP-Widget-Airlock.md)); an iterative mode where a dedicated agent reads a complex server's docs before calling it ([MCP_INTEGRATION](docs/technical/MCP_INTEGRATION.md)).
- **Skills and plugins** — agentskills.io skills with progressive disclosure, sandboxed scripts and rich outputs (maps, dashboards, calendars, QR codes…), generated from a conversation and installed straight into *My Skills* ([SKILLS_INTEGRATION](docs/technical/SKILLS_INTEGRATION.md)); Agent Plugins v1 packages — skills plus streamable-http MCP servers — installed in one step with an exhaustive per-component report ([ADR-225](docs/architecture/ADR-225-Standard-Agent-Plugins-v1.md)).

### Act, under your control

- **Two execution modes, one toggle** — the *pipeline* (planner → semantic validator → approval gate → parallel orchestrator) is deterministic and 4–8× cheaper in tokens; *ReAct* lets the model reason step by step for exploratory or ambiguous requests; both stream through the same response node ([ADR-070](docs/architecture/ADR-070-ReAct-Execution-Mode.md), [PLANNER](docs/technical/PLANNER.md)).
- **Human-in-the-Loop** — five interrupting approval levels (clarification, draft critique, destructive confirmation, bulk `FOR_EACH` confirmation, modifier review) plus plan approval, currently auto-approved because tool-level approval supersedes it ([HITL](docs/technical/HITL.md), [ADR-106](docs/architecture/ADR-106-HITL-Contract-Coherence.md)).
- **Phone calls on your behalf** — through your own ElevenLabs + Twilio connector, every call confirmed before dialing, a strict mandate that forbids any expense beyond the objective, free/busy visibility only, no recording, and a post-call summary that states every cost ([ADR-127](docs/architecture/ADR-127-Agentic-Telephony.md), [TELEPHONY](docs/technical/TELEPHONY.md)).
- **Documents and images** — CSV, Excel, Word, PowerPoint, PDF, Markdown or text produced by local renderers with each format's native mechanisms (styles, fields, layouts, typed tables, bookmarks); nothing overflows by construction, and a truncated model answer is refused rather than rescued into a shorter file ([ADR-226](docs/architecture/ADR-226-Document-Generation-Agent.md), [ADR-274](docs/architecture/ADR-274-Document-Craft-Renderer-Owned-Model-Semantic.md), [ADR-275](docs/architecture/ADR-275-Truncated-Structured-Output-Is-A-Refusal.md)); image generation and natural-language editing with per-user quality and size preferences ([IMAGE_GENERATION](docs/technical/IMAGE_GENERATION.md)).
- **A browser, a sandbox, delegates** — browser control with progressive screenshot streaming ([ADR-059](docs/architecture/ADR-059-Browser-Control.md)); a short Python script run in the skills sandbox when a step needs real computation, ReAct only ([ADR-249](docs/architecture/ADR-249-Ephemeral-Python-In-The-Existing-Sandbox.md)); persistent read-only sub-agents with their own instructions, skills and budgets ([SUB_AGENTS](docs/technical/SUB_AGENTS.md)).
- **The workboard** — a ticket has a lifecycle, a holder and a result ([ADR-276](docs/architecture/ADR-276-Workboard.md), [WORKBOARD](docs/technical/WORKBOARD.md)):
  - one row per ticket, shared by its owner and its holder, across seven columns with sub-tickets, comments and a history; the holder can be you, a connected peer, or LIA;
  - when LIA holds it, a sweep claims one ticket at a time, runs it in the execution mode the ticket declares, and settles from an explicit result — a quota ceiling or a busy conversation postpones the run, never fails it;
  - a run that needs a decision asks instead of refusing: the ticket lands in « To confirm » carrying the exact card the chat would show, and your comment *is* the answer.

### Anticipate

- **The heartbeat** — LIA takes the initiative when it is worth it: calendar, mail, tasks, weather changes, interests, memories, habits and the workboard are aggregated, a cheap structured decision says whether to speak, at your local time, and a second pass writes it in your voice and language; each source has a switch that says whether it is connected, you set the windows, the daily maximum and the channels, rate every notification, and every pass files what it read in your registers ([HEARTBEAT_AUTONOME](docs/technical/HEARTBEAT_AUTONOME.md), [GUIDE_HEARTBEAT](docs/guides/GUIDE_HEARTBEAT_PROACTIVE_NOTIFICATIONS.md)).
- **Moments served to the minute** — a periodic sweep cannot serve an instant, so a finished meeting or an awaited reply is kept as an anticipated moment, claimed under a lock, revalidated, and served under the full eligibility checker while bypassing only the deferrals; mail watches are answered from the push-driven wake that already holds the Gmail delta ([ADR-281](docs/architecture/ADR-281-Anticipated-Moments-And-Mail-Watches.md), [ADR-261](docs/architecture/ADR-261-Push-Driven-Heartbeat-Wake-And-Incremental-Drive-Sync.md)).
- **Routines and reminders** — one recurrence engine answers "when?" for both, as a product of calendar days and moments ("every three days", "the 2nd Tuesday of the month", "every two hours between 9 and 5"), timezone-aware, with a week view and a run history per tick ([ADR-268](docs/architecture/ADR-268-Generic-Recurrence-And-Reminder-Management.md), [ADR-265](docs/architecture/ADR-265-Routine-Week-Timeline-And-Run-History.md), [SCHEDULED_ACTIONS](docs/technical/SCHEDULED_ACTIONS.md)).
- **Interests and habits, learned with restraint** — an interest is created only on a named ground quoted from your own words, with six exclusion classes and a cap on deletions per run ([ADR-166](docs/architecture/ADR-166-Extraction-Admission-Doctrine.md), [INTERESTS](docs/technical/INTERESTS.md)); habits are learned deterministically from a recurrence ledger, promoted, refreshed or demoted by a nightly job and never on doubt; a status you set on a learned window holds for the heartbeat, its scheduling and the assistant's context alike, a missed routine is offered by name, and one learning switch closes every door ([ADR-214](docs/architecture/ADR-214-Habitudes-Utilisateur-Apprentissage-Deterministe.md)).
- **A daily briefing** — the home page aggregates your sources in parallel with a per-section cache and an LLM synthesis, served by a read-only domain outside the agent graph ([BRIEFING_DOMAIN](docs/technical/BRIEFING_DOMAIN.md)).

### Remember

- **Long-term memory** — facts extracted after each conversation, pinned or edited by hand, injected by relevance with their scores visible in the debug panel ([LONG_TERM_MEMORY](docs/technical/LONG_TERM_MEMORY.md), [MEMORY_RESOLUTION](docs/technical/MEMORY_RESOLUTION.md)).
- **Personal journals** — introspective notebooks the assistant keeps in the first person, stratified from raw observations to a user portrait, with an epistemic status per entry and a deferred self-evaluation at zero added LLM cost ([ADR-079](docs/architecture/ADR-079-Stratified-Journal-Consciousness.md), [JOURNALS](docs/technical/JOURNALS.md)).
- **Knowledge spaces** — personal document bases in 15+ formats with hybrid search (pgvector cosine + BM25), Google Drive folder sync, a Gmail label as a source, and a system space that indexes the product's own FAQ so LIA can explain itself ([GUIDE_RAG_SPACES](docs/guides/GUIDE_RAG_SPACES.md), [ADR-055](docs/architecture/ADR-055-RAG-Spaces-Architecture.md), [ADR-058](docs/architecture/ADR-058-System-RAG-Spaces.md)).
- **Meetings and minutes** — record from the phone or the computer while the chat stays usable, with a capture that survives reloads and lost microphones; a chain of transcription engines walked at processing time; minutes filled from one of thirty built-in templates or your own, reformatted in place or derived into a second set from the same transcript ([ADR-258](docs/architecture/ADR-258-Meeting-Recording-And-Structured-Minutes.md), [ADR-259](docs/architecture/ADR-259-Meeting-Template-Library-And-Reformatting.md), [MEETINGS](docs/technical/MEETINGS.md)).
- **People** — a 360° relationship lens over open loops, calls, messages and memories, with a written debrief per person built lazily when the card opens ([ADR-176](docs/architecture/ADR-176-Personal-CRM-Relations.md), [ADR-193](docs/architecture/ADR-193-Read-Capabilities-And-Merged-Identity.md), [ADR-269](docs/architecture/ADR-269-Relationship-Debrief.md)); connections between users of the same instance, assistant to assistant — relayed messages delivered by the recipient's own assistant, field-level read-only shares, silent blocking ([ADR-180](docs/architecture/ADR-180-Peer-Connections.md), [ADR-182](docs/architecture/ADR-182-Peer-Routing-Awareness-And-Honest-Failure.md)).
- **What LIA produced is yours** — generated images, documents and browser screenshots have their own galleries with search, exact totals and a visible retention deadline; clearing a conversation never clears them ([ADR-279](docs/architecture/ADR-279-Generated-Assets-Gallery.md)).
- **What you keep is yours too** — a bookmark on every answer copies it with the request that produced it and the answer's date, so it outlives the conversation; a Bookmarks tab beside the galleries lists them newest first, with search, an exact total against the account's cap, sharing, a Markdown export and deletion ([ADR-282](docs/architecture/ADR-282-Message-Bookmarks.md), [BOOKMARKS](docs/technical/BOOKMARKS.md)).

### Trust it

- **Three registers, sealed on request** — one row per action (claimed before it happens, closed from an explicit result), one per consultation (which capability read what, when, with what outcome), one per turn; proactive acts and direct reads are recorded too; extractions are complete, never capped; an opt-in per-account hash chain makes the registers tamper-evident while preserving the right to erasure ([ADR-263](docs/architecture/ADR-263-Execution-Authority-Chain-And-Effect-Register.md), [ADR-270](docs/architecture/ADR-270-Spend-Roads-And-Register-Authorship.md), [ADR-273](docs/architecture/ADR-273-Complete-Register-Extractions.md), [AI_ACT_TRACEABILITY](docs/technical/AI_ACT_TRACEABILITY.md)).
- **Spend that answers to two ceilings** — every platform-paid token counts against the account's quota *and* the instance's daily budget; a refusal carries a dedicated code and a `Retry-After`; where each module's spend is recorded is declared and guarded, never inferred ([ADR-216](docs/architecture/ADR-216-Plafond-De-Depense-D-Instance.md), [ADR-272](docs/architecture/ADR-272-Every-Platform-Paid-Token-Answers-To-Both-Ceilings.md), [USAGE_LIMITS](docs/technical/USAGE_LIMITS.md)).
- **Strong authentication** — WebAuthn passkeys, a TOTP second factor with backup codes, step-up re-authentication on sensitive actions, device sessions with per-device revocation, server-side Redis sessions behind HTTP-only cookies ([ADR-143](docs/architecture/ADR-143-Strong-Authentication-Passkeys.md), [ADR-144](docs/architecture/ADR-144-Device-Sessions.md), [AUTHENTICATION](docs/technical/AUTHENTICATION.md)).
- **Your data, by construction** — Fernet-encrypted credentials, PII kept out of logs, a full-account GDPR export ([ADR-145](docs/architecture/ADR-145-Account-Export.md)), external content wrapped with a provenance that survives compaction, skill scripts confined to a throwaway container, automated backups with a tested one-command restore ([ADR-109](docs/architecture/ADR-109-PostgreSQL-Backup-Strategy.md), [SECURITY](docs/technical/SECURITY.md)).
- **Switches, not redeploys** — twenty-five capabilities switch off from the admin panel, each declaring where it is enforced; a switch removes the capability, never the record ([ADR-217](docs/architecture/ADR-217-Capacites-Administrables.md), [ADR-280](docs/architecture/ADR-280-Complete-Capability-Control.md)).

---

## Administration & Monitoring

Operators get complete control and real-time visibility without touching configuration files or the database.

### Admin Dashboard

| Area                          | What you control                                                                                                                                                                                                              |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **LLM configuration**         | The model behind every node and slot, provider parameters, prompt versions, the context window per slot                                                                                                                       |
| **Model catalogue & pricing** | Providers, capability flags, accepted reasoning depths, a provenance badge and prices per model — the source of truth for the LLM factory, with its status against the public registries; image-generation and Google API pricing alongside; live cross-worker invalidation |
| **Platform capabilities**     | Twenty-five switches in six families, each row showing the deployment bound, the operator choice and the state actually enforced                                                                                            |
| **Budgets & limits**          | Per-user token, message and cost quotas with live gauges; the instance daily ceiling in euros, today's spend and what remains                                                                                                 |
| **Knowledge & skills**        | Knowledge spaces and reindexation, the system FAQ space, skills (enable, translate, delete), admin MCP servers and plugins                                                                                                     |
| **People & voice**            | Users, roles, connector health, assistant personalities, the TTS catalogue and voice picker                                                                                                                                   |
| **Platform health**           | Incidents and their diagnoses, each shown with the evidence it was written from                                                                                                                                                |
| **Registers**                 | Readable, technical and Article-12 extractions over one, several or all accounts — masked unless audited                                                                                                                      |
| **Broadcast, debug, demo**    | System-wide notifications, per-user debug verbosity, the public showroom link, CSV consumption exports                                                                                                                        |

### Real-Time Debug Panel

A 24-section panel embedded in the chat, organised into six groups; an empty section shows "N/A" rather than disappearing.

| Group                      | Sections                                                                                                                                                      |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Request Analysis**       | Intent classification, Domain detection, Routing decision, Query transformations                                                                              |
| **Planning & Execution**   | Planner output, Tool selection, Context resolution, Token budget, Execution timeline, ForEach analysis, Execution waves                                       |
| **Intelligent Mechanisms** | Cache hits, pattern learning, semantic expansion, Skills activation                                                                                           |
| **Context Injection**      | Memory injection (scores), RAG injection (scores), Knowledge enrichment (Brave), Journal injection (per-entry scores, budget)                                 |
| **Background Extraction**  | Memory detection (create/update/delete), Journal extraction, Interest profile                                                                                 |
| **LLM & API Pipeline**     | Request lifecycle (timing breakdown per node), LLM Pipeline (chronological reconciliation), LLM call details (model, tokens, latency, cost), Google API calls |

> Built for developers and operators: diagnose, optimise prompts and understand the agent's decisions in real time — no external tool, no log access needed ([DEBUG_PANEL](docs/technical/DEBUG_PANEL.md)).

### Observability

- **Prometheus**: 553 custom metrics (agents, LLM, infrastructure). A metric nobody can see is a metric nobody acts on: every one must be wired to a Grafana panel, a recording rule or an alert, and a shrink-only ratchet fails the build on a newly blind metric.
- **Grafana**: 29 dashboards, including a product-value cockpit · **Loki**: structured JSON logs with PII filtering · **Tempo**: distributed tracing · **Langfuse**: LLM tracing with prompt versions.
- **Probes**: liveness (`GET /health`) split from readiness (`GET /ready`, 503 unless PostgreSQL **and** Redis answer) — [ADR-115](docs/architecture/ADR-115-Liveness-Readiness-Probes.md).
- **Alerting**: a vital core (service, database and Redis down, disk, OOM, 5xx rate, SSE latency, backup failure, public-endpoint and TLS probes, chain self-monitoring) evaluated by Prometheus, emailed by a dedicated Alertmanager, unit-tested with `promtool`, every alert linking its runbook — [ADR-119](docs/architecture/ADR-119-Alerting-Reactivation-Minimal-Core.md).
- **Self-diagnostics**: a leader-elected self-check of the golden signals, one incident per outage whichever observer saw it first, and a budget-capped diagnosis written in each administrator's language from evidence collected at diagnosis time — metrics, a sanitised log excerpt, the running build, the alert's runbook — shown under its verdict in Settings › Platform health ([ADR-247](docs/architecture/ADR-247-Self-Diagnostics-And-Answer-Resilience.md), [ADR-266](docs/architecture/ADR-266-Diagnosis-Evidence-At-Diagnosis-Time-And-Exact-Str-Embedding-Inputs.md)).

---

## Quick Start

### Prerequisites

| Software                      | Version | Required         |
| ----------------------------- | ------- | ---------------- |
| Python                        | 3.14    | Yes              |
| Node.js                       | 24 LTS  | Yes              |
| Docker                        | 24+     | Yes              |
| pnpm                          | 10+     | Yes              |
| [Task](https://taskfile.dev/) | 3+      | Yes (build tool) |

Every command lives in `Taskfile.yml`.

### Express Setup

```bash
# 1. Clone the repository
git clone https://github.com/jgouviergmail/LIA-Assistant.git
cd LIA-Assistant

# 2. Configure environment
cp .env.example .env  # Edit with your API keys

# 3. Full setup (backend + frontend + git hooks)
task setup

# 4. Start all services (API + Web + PostgreSQL + Redis + observability)
task dev
```

<details>
<summary><strong>Manual setup (without Task)</strong></summary>

```bash
# 1. Start the infrastructure
docker compose up -d postgres redis prometheus grafana

# 2. Backend setup
cd apps/api
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install --require-hashes -r requirements.lock.txt  # compiled lockfile (reproducible)
cp ../../.env.example .env  # Configure your API keys

# 3. Database migrations
alembic upgrade head

# 4. Frontend setup
cd ../web
pnpm install

# 5. Start the services
# Terminal 1 - Backend:
cd apps/api && uvicorn src.main:app --reload --port 8000

# Terminal 2 - Frontend:
cd apps/web && pnpm dev
```

</details>

### Self-Hosting in Production

A guided installer lives at the repository root ([ADR-215](docs/architecture/ADR-215-Self-Host-Installer.md)). It asks a short questionnaire (LAN exposure, your own reverse proxy, or managed HTTPS with Caddy), generates a private `.env` and Compose overlay, applies the reference seeds atomically, creates the admin and provider keys over stdin, verifies the installation beyond `/ready` and prints a non-secret report. A complete source checkout builds the images locally; an official release directory uses prebuilt digests only when its adjacent manifest is qualified. Resume an interrupted run with `./install.sh --resume`, change the routing later with `./install.sh --reconfigure`.

**Full guide: [docs/guides/GUIDE_SELF_HOSTING.md](docs/guides/GUIDE_SELF_HOSTING.md)** — what it installs, every setting, and what to do when a step fails. Production targets include the Raspberry Pi (ARM64) through multi-arch Docker images (`linux/amd64,linux/arm64`).

### Development URLs

| Service    | URL                        | Credentials |
| ---------- | -------------------------- | ----------- |
| Frontend   | http://localhost:3000      | —           |
| API Docs   | http://localhost:8000/docs | —           |
| Grafana    | http://localhost:3001      | admin/admin |
| Prometheus | http://localhost:9090      | —           |

### Minimal Configuration (.env)

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/lia
REDIS_URL=redis://localhost:6379/0

# Security (REQUIRED - change in production)
SECRET_KEY=change-me-in-production-use-openssl-rand-base64-32
FERNET_KEY=your-fernet-key-here

# LLM provider API keys are configured in the Admin UI after first login
# (Settings > Administration > LLM Configuration). At least one provider is required.

# Google OAuth (optional)
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...

# Feature flags (optional, disabled by default unless stated)
MCP_ENABLED=false               # Admin MCP servers
MCP_USER_ENABLED=false          # Per-user MCP (requires MCP_ENABLED)
CHANNELS_ENABLED=false          # Multi-channel messaging (Telegram)
HEARTBEAT_ENABLED=false         # Autonomous proactive notifications
SUB_AGENTS_ENABLED=false        # Persistent specialized sub-agents
SKILLS_ENABLED=false            # Skills system (agentskills.io standard)
RAG_SPACES_ENABLED=true         # Knowledge spaces (document upload & retrieval)
FCM_NOTIFICATIONS_ENABLED=false # Firebase push notifications
```

Every optional subsystem is governed by a `{FEATURE}_ENABLED` flag, checked at startup, at route wiring and at node entry; the full list with defaults is in [`.env.example`](.env.example).

---

## Architecture

Three layers: a **Next.js** front end (chat, settings, six languages, SSE streaming, voice) talking over HTTP-only cookies to a **FastAPI** backend, whose **LangGraph** graph orchestrates the agents and tools; **PostgreSQL** (data, checkpoints, pgvector) and **Redis** (cache, sessions, rate limiting, locks) underneath, with Prometheus, Langfuse, Loki and Tempo watching. The backend follows Domain-Driven Design: one bounded context per domain, each with its router, service, repository and schemas.

### Two Execution Modes

Switchable per user from the chat header:

- **Pipeline** (default) — a **Planner** decomposes the request into an execution plan (a small DSL with dependencies, conditions and `FOR_EACH` iteration), a **Semantic Validator** checks its coherence, the **Approval Gate** handles Human-in-the-Loop, and a **Task Orchestrator** runs the tools in parallel waves; Bayesian pattern learning shortens the next similar request. Deterministic, and 4–8× fewer tokens than ReAct.
- **ReAct** (⚡) — the model reasons iteratively, calling tools one by one and adapting to each result. More autonomous, more expensive; ideal for exploratory, research or ambiguous queries. Its iteration budget is extended while the loop keeps producing results, and a turn that stops mid-flight closes its own books.

```mermaid
graph TD
    A[User Message] --> B[Router Node]
    B -->|conversation| C[Response Node]
    B -->|pipeline mode| D[Planner Node]
    B -->|react mode| R1[ReAct Setup]
    D --> E[Semantic Validator]
    E --> F{Approval Gate}
    F -->|approved| G[Task Orchestrator]
    F -->|rejected| C
    G --> H[Domain Agents + Tools]
    H --> G
    G --> C
    R1 --> R2[ReAct Call Model]
    R2 -->|tool_calls| R3[ReAct Execute Tools]
    R2 -->|done| R4[ReAct Finalize]
    R3 --> R2
    R4 --> C
    C --> J[SSE Stream]
```

### Code Structure

```
apps/api/src/
├── core/                 # Settings composed per domain, constants, i18n tables, recurrence engine
├── domains/              # 49 bounded contexts (DDD)
│   ├── agents/           # The LangGraph graph: nodes (router, planner, react ×4, response…), tools, prompts, orchestration
│   ├── connectors/       # Google, Apple and Microsoft clients behind one provider resolver
│   ├── heartbeat/ moments/ scheduled_actions/ reminders/ habits/ interests/ briefing/       # initiative
│   ├── memories/ journals/ rag_spaces/ meetings/ relations/ peers/ workboard/ attachments/  # what LIA keeps
│   ├── auth/ users/ usage_limits/ capabilities/ feature_switches/ diagnostics/              # control
│   └── voice/ skills/ plugins/ user_mcp/ telephony/ document_generation/ image_generation/ …
└── infrastructure/       # Cross-cutting: cache and Redis key families, LLM factory and providers,
                          # MCP client pool, browser pool, rate limiting, scheduler, startup steps, observability
apps/web/src/             # Next.js App Router under app/[lng]/, components, hooks, stores, six locales
apps/mobile/              # Capacitor shells for Android and iOS, loading a self-hosted server
infrastructure/           # Compose stacks, database seeds, observability config, backups, Caddy
scripts/                  # Release, audit, deployment and measurement tooling
docs/                     # Architecture, technical documents, guides, runbooks, ADRs, the public audit
```

### Key Design Patterns

| Pattern                    | What it buys                                                                                                                                                                                                                                                       |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Five-layer tool system** | A generic connector base with OAuth auto-refresh, a meta-decorator composing metrics + rate limiting + context save, domain formatters, a declarative `ToolManifest`, and a catalogue loader — a tool is a few lines, not a file                                    |
| **Domain taxonomy**        | One declarative `DOMAIN_REGISTRY` (agents, result key, related domains, priority, routability) feeds catalogue filtering, semantic expansion and the initiative phase — never a second hand-maintained table                                                        |
| **Data registry**          | Tool results live in an in-memory store decoupled from the message history, so aggressive message windowing never loses a `$steps.X.field` reference                                                                                                               |
| **Semantic validator**     | A dedicated LLM, distinct from the planner, inspects every plan for hallucinated capabilities, ghost dependencies, cardinality and scope errors before anything runs                                                                                                |
| **Adaptive re-planner**    | A rule-based analyser classifies an execution failure and picks a recovery; in *panic mode* the catalogue expands to every tool for one retry                                                                                                                      |
| **Connector abstraction**  | Python protocols and normalisers make Google, Apple and Microsoft interchangeable behind unified domain models; a resolver guarantees one provider per category                                                                                                    |
| **Published bounds**       | Whatever a validator can reject, its producer can read: every enforced limit is published to the planner, and what is mechanically repairable is repaired before validation ([ADR-184](docs/architecture/ADR-184-Published-Bounds-And-Non-Prescriptive-Verdicts.md)) |
| **Exact counts**           | A number shown to a person is exact or it does not exist — aggregates over the whole set, pages of rows, never a count derived from a capped page ([ADR-185](docs/architecture/ADR-185-Exact-CRM-Counts-And-Readable-Relayed-Messages.md))                          |
| **Boot-time completeness** | Every registry keyed by an enum or a domain is asserted complete at startup; the app refuses to boot on a missing entry rather than failing silently later                                                                                                          |
| **Error architecture**     | Tools return `ToolResponse` / `ToolErrorModel` with a closed `ToolErrorCode` taxonomy and a recoverability flag; the API raises through centralised exception helpers, never a raw `HTTPException`                                                                  |

> The long version: [How does LIA work?](https://lia.jeyswork.com/how) (public architecture guide), [ARCHITECTURE.md](docs/ARCHITECTURE.md), [ARCHITECTURE_LANGRAPH.md](docs/ARCHITECTURE_LANGRAPH.md).

---

## Technologies

### Stack

| Layer         | Technology                                                                                                            | Role                                                              |
| ------------- | --------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| Backend       | Python 3.14 · FastAPI 0.136.3 · Pydantic 2.13.4 · SQLAlchemy 2.0.50 · Alembic                                         | REST API, SSE streaming, validation, async ORM, migrations        |
| Orchestration | LangGraph 1.2.11 · LangChain 1.3.15 · `mcp` SDK (Streamable HTTP)                                                     | Multi-agent graph, LLM abstraction, Model Context Protocol        |
| Data          | PostgreSQL 16 + pgvector · Redis 7.4                                                                                  | Data, checkpoints, vector search · cache, sessions, locks         |
| Frontend      | Node.js 24 LTS · Next.js 16.3.4 · React 19.2.7 · TypeScript · TailwindCSS · Radix UI · TanStack Query · react-i18next | App Router UI, accessible primitives, server state, six languages |
| Voice         | sherpa-onnx (wake word, offline Whisper) · Edge TTS · OpenAI · ElevenLabs                                             | In-browser detection and transcription, speech synthesis          |
| Observability | Prometheus · Grafana · Loki · Tempo · Langfuse · structlog                                                             | Metrics, dashboards, logs, traces, LLM tracing                    |
| Delivery      | Docker (multi-arch amd64/arm64) · GitHub Actions · Task                                                               | Images, CI/CD, one build tool for every command                   |

The UI is responsive by design — desktop, tablet and phone — with touch-friendly, mobile-first components.

### Supported LLM Providers

The model catalogue lives in the database, curated from vendored public registries and editable from the admin panel; every row states where its capabilities came from ([ADR-244](docs/architecture/ADR-244-LLM-Catalogue-Truth.md)). Reasoning depth has one stored shape for every provider ([ADR-245](docs/architecture/ADR-245-Reasoning-Unification.md)).

| Provider   | Notes                                                                                             |
| ---------- | ------------------------------------------------------------------------------------------------- |
| OpenAI     | Prompt caching, reasoning models, structured output                                               |
| Anthropic  | Extended thinking                                                                                 |
| Google     | Gemini, multimodal; `gemini-embedding-001` for retrieval                                          |
| DeepSeek   | Cost-effective reasoning with a thinking-mode toggle                                              |
| Qwen       | Thinking, tools and vision through Alibaba Cloud DashScope; regional endpoint via `QWEN_BASE_URL` |
| Perplexity | Web-augmented answers; endpoint via `PERPLEXITY_BASE_URL`                                         |
| Ollama     | Any local model, capabilities discovered from the server, native client; `OLLAMA_BASE_URL`        |

### Local Models as First-Class Models

Any LLM slot can run on a model hosted on your own machine, with no cloud account involved. LIA drives Ollama through its **native API** rather than an OpenAI compatibility layer ([ADR-267](docs/architecture/ADR-267-Ollama-Native-Provider-And-Discovered-Capabilities.md)):

- **Thinking is controlled, not endured** — the configured depth reaches the server as `think`, including switching it off, and the thinking trace comes back separated from the answer.
- **The server declares the capabilities** — tools, vision, thinking and context length are read from the tag listing, so a depth never reaches a model that cannot think and a control a local model would ignore is not offered.
- **The context window belongs to the configured slot** ([ADR-278](docs/architecture/ADR-278-Per-Slot-Context-Window.md)) — a frugal router and a generous responder can share one model with different windows; it is the number LIA *asks* for and the number it *counts* with.

---

## Quality: Tests, CI/CD, Security

### Tests

```bash
task test:backend:unit:fast        # fast unit suite, parallel (what the pre-commit hook runs)
task test:backend:unit:coverage    # the CI command verbatim, including the coverage floor
task test:backend:integration      # requires PostgreSQL + Redis
task test:backend:agents           # LangGraph agent suite
task test:frontend                 # vitest
task test:e2e                      # Playwright + axe journeys (hermetic, mocked API)
```

| Metric                  | Value                                                                                                 |
| ----------------------- | ----------------------------------------------------------------------------------------------------- |
| Backend tests           | 28,443 collected over `tests/` (`pytest --collect-only -q`, 1,669 files, 2026-09-11)                  |
| Frontend tests (vitest) | 8,256 across 645 files, plus hermetic Playwright journeys with axe, dark-mode and zoom checks          |
| Coverage floor          | 72% enforced in CI on the backend — a shrink-only ratchet, never lowered; frontend thresholds per glob |
| Technical audit         | **8.3/10** across 24 normalized areas — [full public report & protocol](docs/audit/README.md)         |

Tests are risk-driven and behavioural: a module never disables itself on a missing provider key, a test double that receives a coroutine owns it, and an unawaited coroutine or a post-summary warning is a failure ([GUIDE_TESTING](docs/guides/GUIDE_TESTING.md)).

### CI/CD

Two layers: a **local pre-commit hook** (fast, on staged files) and a **GitHub Actions pipeline** on every push and PR to `main`. The workflow orchestrates and the Taskfile implements: every CI step is a `task <name>` call, so the pipeline runs literally the command a developer runs, and a guard fails on any inline step.

```
Pre-commit (local)              GitHub Actions CI
===================             ==================
.bak files check                Lint Backend (Ruff + Black + MyPy strict)
Secrets grep                    Lint Frontend (ESLint + TypeScript)
Ruff + Black + MyPy             Fast unit tests + coverage floor
Fast unit tests                 Integration tests (PostgreSQL + Redis)
Critical pattern detection      Agents suite
i18n keys sync                  Code hygiene (i18n, Alembic, lockfiles, patterns, docs)
Alembic migration conflicts     Docker build smoke test
.env.example completeness       Secret scan (Gitleaks)
ESLint + TypeScript check       ──────────────────────
                                Security workflow (weekly)
                                  CodeQL (Python + JS)
                                  Dependency audit (pip-audit + pnpm audit)
                                  Trivy filesystem scan
                                  SBOM generation
```

| Practice                 | Implementation                                                                                                                                                                                                           |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Reproducible builds**  | Universal Python lockfiles (linux/amd64, arm64, Windows), hash-verified installs everywhere, a guard failing manifest edits without lock regeneration ([ADR-112](docs/architecture/ADR-112-Python-Dependency-Locking.md)) |
| **Supply chain**         | Every GitHub Action pinned by commit SHA, `permissions: contents: read`, Dependabot weekly with grouped minor/patch updates, SBOM per release                                                                             |
| **Shrink-only ratchets** | Coverage, file size, cyclomatic complexity, MyPy debt, React hooks, accessibility and metric visibility can only improve — a baseline is lowered after the work, never raised to absorb a regression                     |
| **Documentation gate**   | Every version, count and threshold a document states is recomputed from the code that owns it and a mismatch fails the build; broken links, stale code paths and unreachable documents too                               |
| **Release pipeline**     | A tag builds candidates; a release is promoted only from a qualified, disposable-machine installer run ([ADR-215](docs/architecture/ADR-215-Self-Host-Installer.md)); multi-arch images on ghcr.io                       |

> Full details: [CI/CD documentation](docs/technical/CI_CD.md).

### Security

| Standard         | Status                                                                                                                                                                                                                                                                    |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| GDPR             | PII filtering, data minimisation, full-account export, deletion that scrubs every register with the account                                                                                                                                                               |
| OWASP Top 10     | XSS, SQL injection and CSRF protection; a global Redis-backed rate limit in front of every route; request bodies bounded before they are read, webhooks included                                                                                                          |
| Prompt injection | External content wrapped in safety markers, trust classified by data type rather than by producing tool, and a provenance that survives history compaction — a summary built from third-party text inherits its banner instead of promoting the claim to system authority |
| OAuth 2.1        | Mandatory PKCE, single-use state tokens, issuer validation                                                                                                                                                                                                                |
| Supply chain     | Hash-verified universal lockfiles, pip-audit on the full transitive tree, SBOM per release                                                                                                                                                                                |
| Untrusted code   | Skill scripts execute in a throwaway container — no Docker socket, no network, read-only filesystem, unprivileged uid, all capabilities dropped — and no sandbox means no execution, never a weaker fallback                                                               |

**Reporting a vulnerability** — do not open a GitHub issue. Write to **liamyassistant@gmail.com** with a description, the steps to reproduce and the potential impact; we answer within 48 hours. Policy and supported versions: [SECURITY.md](SECURITY.md).

### Performance

Instrumentation and caching are in place — per-node message windowing, LLM context compaction with a threshold derived from the response model's window, prompt caching on OpenAI and Anthropic, asymmetric Gemini embeddings, parallel execution of independent domains, persistent HTTP pools — all instrumented in production. The perceived response time is dominated by the LLM call cascade (seconds to tens of seconds depending on the request and the hardware); that is the optimisation programme in progress. The [technical audit](docs/audit/README.md) scores performance 7.5/10: no sustained load campaign has been executed yet, and the figures will be published when one has.

---

## Documentation

| Entry point                                   | What it covers                                                                                       |
| --------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| [GETTING_STARTED.md](docs/GETTING_STARTED.md) | Detailed installation guide                                                                          |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md)       | Complete system architecture                                                                         |
| [INDEX.md](docs/INDEX.md)                     | The full documentation map                                                                           |
| [CLAUDE.md](CLAUDE.md)                        | The engineering rulebook the AI works under — its systemic rules, each paid for by a measured defect |

| Domain                 | Documents                                                                                                                                                                                                                                                            |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Agents & LLM**       | [ARCHITECTURE_LANGRAPH](docs/ARCHITECTURE_LANGRAPH.md) • [PLANNER](docs/technical/PLANNER.md) • [SEMANTIC_ROUTER](docs/technical/SEMANTIC_ROUTER.md) • [LLM_PROVIDERS](docs/technical/LLM_PROVIDERS.md)                                                              |
| **HITL & registers**   | [HITL](docs/technical/HITL.md) • [AI_ACT_TRACEABILITY](docs/technical/AI_ACT_TRACEABILITY.md) • [PROVENANCE_AND_CAPABILITIES](docs/technical/PROVENANCE_AND_CAPABILITIES.md)                                                                                         |
| **Voice & meetings**   | [VOICE](docs/technical/VOICE.md) • [VOICE_MODE](docs/technical/VOICE_MODE.md) • [MEETINGS](docs/technical/MEETINGS.md)                                                                                                                                               |
| **Memory & knowledge** | [LONG_TERM_MEMORY](docs/technical/LONG_TERM_MEMORY.md) • [MEMORY_RESOLUTION](docs/technical/MEMORY_RESOLUTION.md) • [JOURNALS](docs/technical/JOURNALS.md) • [GUIDE_RAG_SPACES](docs/guides/GUIDE_RAG_SPACES.md)                                                     |
| **Reach**              | [MCP_INTEGRATION](docs/technical/MCP_INTEGRATION.md) • [SKILLS_INTEGRATION](docs/technical/SKILLS_INTEGRATION.md) • [PLUGINS_INTEGRATION](docs/technical/PLUGINS_INTEGRATION.md) • [BROWSER_CONTROL](docs/technical/BROWSER_CONTROL.md) • [SUB_AGENTS](docs/technical/SUB_AGENTS.md) |
| **Initiative**         | [HEARTBEAT_AUTONOME](docs/technical/HEARTBEAT_AUTONOME.md) • [SCHEDULED_ACTIONS](docs/technical/SCHEDULED_ACTIONS.md) • [WORKBOARD](docs/technical/WORKBOARD.md) • [BRIEFING_DOMAIN](docs/technical/BRIEFING_DOMAIN.md)                                              |
| **Channels & mobile**  | [CHANNELS_INTEGRATION](docs/technical/CHANNELS_INTEGRATION.md) • [GUIDE_TELEGRAM](docs/guides/GUIDE_TELEGRAM_INTEGRATION.md) • [GUIDE_MOBILE_ANDROID](docs/guides/GUIDE_MOBILE_ANDROID.md) • [GUIDE_MOBILE_IOS](docs/guides/GUIDE_MOBILE_IOS.md)                     |
| **Security**           | [SECURITY](docs/technical/SECURITY.md) • [AUTHENTICATION](docs/technical/AUTHENTICATION.md) • [OAUTH](docs/technical/OAUTH.md) • [RATE_LIMITING](docs/technical/RATE_LIMITING.md)                                                                                    |
| **Operations**         | [CI_CD](docs/technical/CI_CD.md) • [OBSERVABILITY_AGENTS](docs/technical/OBSERVABILITY_AGENTS.md) • [METRICS_REFERENCE](docs/technical/METRICS_REFERENCE.md) • [ALERTING](docs/technical/ALERTING.md) • [runbooks](docs/runbooks/)                                    |
| **Costs**              | [LLM_PRICING_MANAGEMENT](docs/technical/LLM_PRICING_MANAGEMENT.md) • [GOOGLE_API_TRACKING](docs/technical/GOOGLE_API_TRACKING.md) • [USAGE_LIMITS](docs/technical/USAGE_LIMITS.md)                                                                                   |

| Guide                                                       | Description                   |
| ----------------------------------------------------------- | ----------------------------- |
| [GUIDE_DEVELOPPEMENT](docs/guides/GUIDE_DEVELOPPEMENT.md)   | Complete development workflow |
| [GUIDE_AGENT_CREATION](docs/guides/GUIDE_AGENT_CREATION.md) | How to create a new agent     |
| [GUIDE_TOOL_CREATION](docs/guides/GUIDE_TOOL_CREATION.md)   | How to create a new tool      |
| [GUIDE_TESTING](docs/guides/GUIDE_TESTING.md)               | Testing strategy              |
| [GUIDE_DEBUGGING](docs/guides/GUIDE_DEBUGGING.md)           | LangGraph and log debugging   |
| [GUIDE_SELF_HOSTING](docs/guides/GUIDE_SELF_HOSTING.md)     | Production self-hosting       |

### Architecture Decision Records

281 ADR files (ADR-001 through ADR-282 — ADR-008 has no separate file) record every major architectural decision with its context, the alternatives and, increasingly, the production measurement that motivated it. Three to start with, and [the full index](docs/architecture/ADR_INDEX.md):

- [ADR-070: ReAct Execution Mode](docs/architecture/ADR-070-ReAct-Execution-Mode.md) — why two execution modes rather than one
- [ADR-263: Execution Authority Chain and Effect Register](docs/architecture/ADR-263-Execution-Authority-Chain-And-Effect-Register.md) — how every act is claimed, closed and recorded
- [ADR-184: Published Bounds and Non-Prescriptive Verdicts](docs/architecture/ADR-184-Published-Bounds-And-Non-Prescriptive-Verdicts.md) — an enforced-but-hidden bound is a trap, not a contract

---

## Contributing

Contributions are welcome — bug fixes, features, documentation, tests, translations in the six supported languages, performance work. Start with the [Contributing Guide](CONTRIBUTING.md).

```bash
git clone https://github.com/YOUR-USERNAME/LIA-Assistant.git && cd LIA-Assistant
git checkout -b feature/my-feature
task setup                          # backend + frontend + git hooks
task test:backend:unit:fast         # develop and test
git commit -m "feat(agents): add weather forecast agent"   # Conventional Commits
git push origin feature/my-feature  # then open a PR
```

- **Python**: Black + Ruff + MyPy strict · **TypeScript**: ESLint + Prettier · **Commits**: [Conventional Commits](https://www.conventionalcommits.org/)
- **Before pushing**: `task ci:fast` runs every CI gate that needs no service; `task pre-commit` is what the git hook runs
- **Rules that are not stylistic**: read the *Systemic Rules* in [CLAUDE.md](CLAUDE.md) — each one closes a bug class measured in production, and a guard enforces most of them

---

## Support

| Channel                                                                          | Usage                  |
| -------------------------------------------------------------------------------- | ---------------------- |
| [GitHub Issues](https://github.com/jgouviergmail/LIA-Assistant/issues)           | Bugs, feature requests |
| [GitHub Discussions](https://github.com/jgouviergmail/LIA-Assistant/discussions) | Questions, ideas       |
| liamyassistant@gmail.com                                                         | General inquiries      |

Also: the [documentation index](docs/INDEX.md), the [practical guides](docs/guides/) and the [operational runbooks](docs/runbooks/).

---

## License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)** — see [LICENSE](LICENSE).

A commercial license is available for organizations that cannot comply with AGPL-3.0 terms: contact liamyassistant@gmail.com.

---

## Acknowledgments

LIA stands on excellent open source work: [Python](https://www.python.org/), [FastAPI](https://fastapi.tiangolo.com/), [LangGraph](https://github.com/langchain-ai/langgraph) and [LangChain](https://python.langchain.com/), [SQLAlchemy](https://www.sqlalchemy.org/), [Pydantic](https://docs.pydantic.dev/), [Alembic](https://alembic.sqlalchemy.org/), [PostgreSQL](https://www.postgresql.org/) with [pgvector](https://github.com/pgvector/pgvector), [Redis](https://redis.io/), [structlog](https://www.structlog.org/), [Edge TTS](https://github.com/rany2/edge-tts), [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx), [Docker](https://www.docker.com/); [Node.js](https://nodejs.org/), [Next.js](https://nextjs.org/), [React](https://react.dev/), [TypeScript](https://www.typescriptlang.org/), [TailwindCSS](https://tailwindcss.com/), [Radix UI](https://www.radix-ui.com/), [TanStack Query](https://tanstack.com/query/), [react-i18next](https://react.i18next.com/); [Prometheus](https://prometheus.io/), [Grafana](https://grafana.com/), [Loki](https://grafana.com/oss/loki/), [Tempo](https://grafana.com/oss/tempo/) and [Langfuse](https://langfuse.com/); and the [Model Context Protocol](https://modelcontextprotocol.io/), [agentskills.io](https://agentskills.io/) and [Agent Plugins](https://agent-plugins.org/) open standards.

---

<p align="center">
  <strong>LIA</strong> — Your life. Your AI. Your rules.
</p>

<p align="center">
  Built with ❤️ using Python, FastAPI, LangGraph, Next.js and Node.js
</p>

<p align="center">
  <a href="#lia">Back to top</a>
</p>
