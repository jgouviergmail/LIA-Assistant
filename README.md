<p align="center">
  <img src="docs/assets/logo.png" alt="LIA — Your life. Your AI. Your rules." width="600" />
</p>

<h1 align="center">LIA</h1>

<p align="center">
  <strong>Intelligent multi-agent conversational assistant with LangGraph orchestration, Human-in-the-Loop, enterprise-grade observability, and full i18n support (6 languages)</strong>
</p>

<p align="center">
  <strong>If you find my project and work valuable, I would be grateful for a star on GitHub. Thank you !</strong>
</p>

<p align="center">
  <a href="https://lia.jeyswork.com/"><img src="https://img.shields.io/badge/🚀_Try_LIA-lia.jeyswork.com-0EA5E9?style=for-the-badge" alt="Try LIA"></a>
  &nbsp;&nbsp;
  <a href="https://github.com/jgouviergmail/LIA-Assistant/stargazers"><img src="https://img.shields.io/github/stars/jgouviergmail/LIA-Assistant?style=for-the-badge&logo=github&label=Star&color=gold" alt="GitHub Stars"></a>
</p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.12%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+"></a>
  <a href="https://nodejs.org/"><img src="https://img.shields.io/badge/Node.js-24%20LTS-5FA04E?style=flat-square&logo=nodedotjs&logoColor=white" alt="Node.js 24 LTS"></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-0.136.3-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI"></a>
  <a href="https://nextjs.org/"><img src="https://img.shields.io/badge/Next.js-16-000000?style=flat-square&logo=nextdotjs&logoColor=white" alt="Next.js 16"></a>
  <a href="https://langchain-ai.github.io/langgraph/"><img src="https://img.shields.io/badge/LangGraph-1.2.2-FF6F00?style=flat-square" alt="LangGraph"></a>
  <a href="https://python.langchain.com/"><img src="https://img.shields.io/badge/LangChain-1.3.2-4B8BBE?style=flat-square" alt="LangChain"></a>
  <a href="#internationalization-i18n--6-languages"><img src="https://img.shields.io/badge/i18n-6%20languages-E040FB?style=flat-square" alt="6 languages"></a>
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
  <a href="#contributing">Contributing</a>
</p>

<p align="center">
  <strong>Version 1.25.6</strong> — <strong>Interest notifications learn variety — every mechanism validated by measurement first.</strong> Production data showed the repetitiveness was not the draw (already uniform) but pool composition: one perceived subject (AI), fragmented into 9 of 19 interests, captured ~50% of notifications. Three benches on the real prod snapshot settled the design (<strong>ADR-131</strong>): an embedding-cosine "semantic cooldown" was <em>refuted</em> (a false pair outscored a true one; only ≥ 0.95 is reliable), incremental LLM subject labeling was <em>refuted</em> (order-dependent drift, aberrant merges), while <strong>batch labeling measured 98.2% stable</strong> — so the <code>subject</code> label is derived data, recomputed wholesale by a scheduled job (stale scan 30 min + nightly full). A 300-run simulation validated against production picked variant <strong>V5</strong>: subject cooldown then rarity draws at both levels — the dominant family falls to ~33% and starvation drops 0.8 → 0.3 interests/30 days, fail-open at every stage, instant <code>uniform</code> rollback knob. The audit also closed real holes: extraction dedup silently disabled itself when embedding generation failed (how "Anthropic"/"anthropic" both existed — a nightly retro-merge ≥ 0.95 now heals history while repointing the audit trail), renames could collide or keep stale labels, and notifications gained <strong>deterministic source hyperlinks</strong> (markdown in chat, readable text for push/Telegram — zero hallucinated URLs). A long-standing i18n bug died too: proactive titles were keyed <code>zh</code> while <code>User.language</code> is <code>zh-CN</code> — Chinese users had been silently receiving English titles. <strong>Verified:</strong> <strong>10,388 fast unit</strong> tests green, mypy strict clean on 904 files, migration replay-from-zero green, live clustering of 33 real interests in dev Docker, distribution regression executable in CI. — 18 July 2026.

</p>


---

## Table of Contents

- [Why LIA?](#why-lia)
- [Try LIA Online](#try-lia-online)
- [Built by an AI, Directed by a Human](#built-by-an-ai-directed-by-a-human)
- [Screenshots](#screenshots)
- [Features](#features)
- [Administration & Monitoring](#administration--monitoring)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Technologies](#technologies)
- [Documentation](#documentation)
- [Tests](#tests)
- [CI/CD](#cicd)
- [Performance](#performance)
- [Security](#security)
- [Contributing](#contributing)
- [Support](#support)
- [License](#license)
- [Acknowledgments](#acknowledgments)

---

## Why LIA?

**LIA** solves the fundamental problems of today's AI assistants:

| Problem | LIA Solution |
|---------|---------------------|
| **Unpredictable LLM costs** | Real-time token tracking, budget alerts, 93% optimization |
| **Uncontrolled hallucinations** | Human-in-the-Loop (HITL) with 6 approval levels |
| **Fragmented integrations** | Unified multi-domain orchestration (19+ agents + MCP + sub-agents) |
| **Limited observability** | 423 Prometheus metrics, 25 Grafana dashboards, email alerting with runbooks, GeoIP analytics |
| **Inconsistent performance** | Gemini embedding-001 with asymmetric task types, semantic routing with hybrid scoring |

### Primary Use Cases

```
📅 "Find my meetings for tomorrow and send a reminder to all participants"
📧 "Summarize my unread emails from this week that have attachments"
👥 "Update the companies of my contacts who work at startups"
🔔 "Remind me tomorrow at 9am to call Marie for her birthday"
```

---

## Try LIA Online

<p align="center">
  <a href="https://lia.jeyswork.com/"><img src="https://img.shields.io/badge/🚀_Try_LIA-lia.jeyswork.com-0EA5E9?style=for-the-badge" alt="Try LIA"></a>
</p>

LIA is available as a hosted service at **https://lia.jeyswork.com/** — no installation required.

> **Closed beta**: Access is currently limited to a restricted number of users, at the administrator's discretion. To request an invitation, contact **liamyassistant@gmail.com**.

---

## Built by an AI, Directed by a Human

> *"Speed comes from the AI. Quality comes from the framework."*

Nearly **100% of this codebase was written by an AI**, under human direction: a written
engineering rulebook, blocking automated checks, systematic review, adversarial audits.
The result is measured, not proclaimed:

| | | | |
|---|---|---|---|
| **32** functional domains | **420,000** lines of code (excl. tests) | **11,900+** automated tests | **120+** ADRs |
| **153** versions shipped | **6 languages**, parity enforced in CI | **423** Prometheus metrics | [**8.3/10** technical audit, 24 normalized areas](docs/audit/README.md) |

- **The full story** — method, trade-offs, results and what remains to be done, weaknesses included: [lia.jeyswork.com/story](https://lia.jeyswork.com/story)
- **The audit itself** — 24 normalized areas mapped to ISO/IEC 25010:2023, every score backed by executed evidence, 7 open worksites included, with the protocol and the full standalone report: [docs/audit/](docs/audit/README.md)

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

### Multi-Agent Intelligence (LangGraph 1.x)

- **19+ Specialized Agents**: Contacts, Emails, Calendar, Drive, Tasks, Reminders, Places, Routes, Weather, Wikipedia, Perplexity, Brave, Web Search, Web Fetch, Browser Control (with progressive screenshot streaming), Smart Home (Philips Hue), Context, Query + dynamic MCP agents
- **ReAct Execution Mode** ([ADR-070](docs/architecture/ADR-070-ReAct-Execution-Mode.md)): Alternative to the pipeline — the LLM iteratively reasons about tool outputs and decides next steps autonomously. User-toggleable preference, 4-node LangGraph architecture with native HITL support, timeout enforcement, cross-domain initiative via prompt engineering. Supports all tools including MCP and Skills
- **MCP (Model Context Protocol)**: Per-user external tool servers with OAuth 2.1, SSRF protection, structured items parsing, MCP Apps (interactive iframe widgets), **Iterative Mode (ReAct)** for complex servers — a dedicated agent reads docs then calls tools correctly
- **Agent Initiative Phase**: Post-execution cross-domain enrichment — the assistant proactively verifies related information (e.g., weather shows rain → checks calendar for outdoor events). Prompt-driven, read-only, fully configurable
- **Skills (agentskills.io) with Rich Outputs**: Open standard for expert instructions (SKILL.md), model-driven activation, progressive disclosure (L1/L2/L3), sandboxed scripts, marketplace import, auto-translated multi-language descriptions, ZIP download, admin management. **Rich Skill Outputs** (v1.16.8): skills can return interactive HTML frames (iframe srcDoc or external URL) and/or images in addition to text, via a simple JSON contract (`SkillScriptOutput`). Automatic theme & locale sync (theme switch propagates live to frames via `postMessage`), iframe auto-resize, CSP-sandboxed client-side interactivity (`addEventListener`, `crypto.getRandomValues`), bundled `segno` for QR codes. Seven built-in rich skills: `interactive-map`, `weather-dashboard`, `calendar-month`, `qr-code`, `pomodoro-timer`, `unit-converter`, `dice-roller`. **Planner skill guard**: multi-domain deterministic skills are protected from false-positive early clarification requests via domain overlap detection (`_has_potential_skill_match`). **Built-in Skill Generator**: create custom skills in natural language — the assistant guides you through need analysis and archetype selection (the dialogue keeps its context across turns), then validates and **installs the finished skill directly into My Skills**, announced by name and immediately usable. Every import path (chat-generated or manual upload) goes through one hardened pipeline: strict name validation, zip-expansion caps, name-conflict rejection, atomic install with automatic rollback
- **Agentic Telephony** ([ADR-127](docs/architecture/ADR-127-Agentic-Telephony.md)): LIA places real outbound phone calls on your behalf via your own per-user ElevenLabs + Twilio connector (BYO — zero cost on LIA's side). Every call is HITL-confirmed before dialing; the goal-driven voice agent greets the instant the line opens, resolves relative dates against a live temporal anchor, and hangs up when done. Privacy by capability: the call agent can only read free/busy availability — never event titles or contents; no recording, no stored transcript. A **strict mandate boundary** forbids any expense or commitment beyond the objective (offers are captured with their price and deferred to you), and the asynchronous post-call summary must state every cost and flag every open point. Config self-heals: fingerprint-based lazy re-sync of the vendor agent, self-healing one-active-call guard (vendor status probe, deleted-conversation 404 handling), pinned thinking-free agent LLM, telephony-native `ulaw_8000` audio
- **AI Image Generation & Editing**: Generate images from text prompts (gpt-image-1), edit existing images with natural language instructions. Multi-provider factory architecture, per-user quality/size preferences, cost tracking with DB-cached pricing, attachment-based storage with cascade cleanup
- **File Attachments (Images, PDF)**: Upload with client-side compression, configurable LLM vision analysis, PDF text extraction, strict per-user isolation
- **Semantic Routing**: Binary classification with confidence scoring (high >0.85, medium >0.65)
- **Multi-Step Planning**: ExecutionPlan DSL with dependencies and conditions
- **Parallel Execution**: asyncio.gather for independent domains
- **Intelligent Context Compaction**: LLM-based conversation history summarization when token count exceeds dynamic threshold (ratio of response model context window). Preserves identifiers (UUIDs, URLs, emails). `/resume` command for manual trigger. 4 HITL safety conditions prevent compaction during active approval flows
- **Scroll-up History Pagination**: `GET /conversations/me/messages` exposes a keyset cursor (`?before=<created_at>`) with `has_more` / `next_cursor`. The chat UI binds an `IntersectionObserver` on a top sentinel — older pages prepend with id-based dedup, scroll position preserved via a shared `wasPrependRef` that skips the auto-scroll-to-bottom for that cycle. Conversations of any length stay fully reachable; the existing `(conversation_id, created_at DESC)` composite index makes each page an index-only seek. Bounds env-tunable (`CONVERSATION_HISTORY_DEFAULT_LIMIT` / `_MAX_LIMIT`)

### Psyche Engine — Dynamic Emotional Intelligence

- **5-Layer Psychological State**: Big Five personality traits (permanent) → PAD mood space with 14 moods (hours) → 22 discrete emotions with cross-suppression (minutes) → 4-stage relationship progression (weeks) → curiosity/engagement drives (per-session)
- **Show, Don't Tell**: Mood and emotions subtly influence word choice, sentence rhythm, energy level, and relational tone — the assistant never declares "I'm feeling happy"
- **Emotional Avatar**: Mood-responsive emoji with colored ring on each message. Historical avatars persisted per-message for reload consistency
- **Evolution Awareness**: The assistant knows how its mood shifted since the last message, providing narrative continuity
- **4-Chart Dashboard**: Interactive recharts visualization of mood (PAD), emotions, relationship, and drives over time (24h to 90 days)
- **Education Guide**: 7-section interactive documentation explaining every layer, with descriptive tables for 14 moods and 22 emotions
- **Customizable Temperament**: Expressiveness (stoic → highly expressive) and stability (volatile → very stable) sliders. Soft reset (mood only) and full reset (everything) with explicit scope descriptions
- **Global Injection**: Behavioral directives injected via template variables into all user-facing text generation (response, notifications, reminders, voice) within semantic XML blocks (`<InnerState purpose="tone-calibration">`)
- **Safety Guardrail**: Explicit instruction prevents the LLM from projecting its own emotional state onto the user
- **Self-Report**: Zero-cost emotion tracking via hidden `<psyche_eval/>` tag — no additional LLM call

### Voice: Input & Output

**Voice Input (STT)**
- **Push-to-Talk**: Hold microphone button to speak, release to transcribe. Optimized for mobile (anti-long-press CSS, touch gesture handling)
- **Wake Word**: Say "OK Guy" to activate hands-free recording. Sherpa-onnx WASM (Whisper Tiny.en) runs entirely in-browser — no audio sent externally for wake word detection
- **Per-User Language**: STT transcription uses the user's preferred language setting (Whisper Small, 99+ languages, fully offline)
- **Latency Optimized**: Mic stream reuse, WebSocket pre-warming, parallel setup, cached AudioWorklet (~50-100ms wake-to-record)

**Voice Output (TTS)**

| Provider | Models | Cost | Latency (TTFA) | Notes |
|----------|--------|------|---------------|-------|
| Edge TTS (Microsoft Neural) | `edge-tts` | Free | ~250 ms | Multilingual neural voices, free fallback |
| OpenAI TTS | `tts-1` / `tts-1-hd` | $15 / $30 per 1M chars | ~500 ms | 6 stable voices (alloy, echo, fable, onyx, nova, shimmer) |
| ElevenLabs TTS | `eleven_multilingual_v2` | $100 / 1M chars | ~300 ms | High-quality multilingual, Voice Library access |
|              | `eleven_turbo_v2_5` | $50 / 1M chars | ~250 ms | Sweet-spot quality / latency |
|              | `eleven_flash_v2_5` | $50 / 1M chars | ~75 ms | Ultra-low-latency for conversational agents |

- **Catalogue-driven** (ADR-081): provider/model/voice are admin-controlled via Configuration LLM (LLM type `voice_tts`). Voice + tuning live in `provider_config` JSONB. No env vars to maintain across deployments.
- **Sentence streaming** (ADR-082): TTS runs sentence-by-sentence pipelined with the LLM stream. First audio lands in ~1 s on chat mode (was ~5 s).
- **Per-message cost transparency**: `🔊 N chars · €X.XXX` badge on the assistant bubble (paid providers only — Edge stays badge-free as it's $0).
- **Graceful degradation**: missing API key on a paid provider transparently falls back to Edge with a structured warning log.
- **Persistent HTTP pool** on ElevenLabs: keep-alive across sentences saves ~100–300 ms TLS handshake per call.

### FOR_EACH Iteration Pattern

```python
# DSL Syntax
ExecutionStep(
    tool_name="send_email",
    for_each="$steps.get_contacts.contacts",
    for_each_max=10
)
```

- **HITL Thresholds**: Mutations >= 1 trigger mandatory approval
- **Bulk Operations**: Send emails, update contacts, mass deletions

### Smart Services (Token Savings 89%)

| Service | Role | Optimization |
|---------|------|--------------|
| QueryAnalyzerService | Routing decision | LRU Cache |
| SmartPlannerService | ExecutionPlan generation | Pattern Learning |
| SmartCatalogueService | Tool filtering | 96% token reduction |
| PlanPatternLearner | Bayesian learning | Bypass >90% confidence |

### Google Integrations (OAuth 2.1 + PKCE)

- **Gmail**: Search, read, send, reply, trash
- **Contacts**: Fuzzy search, list, details (14+ schemas)
- **Calendar**: Search, create, update events
- **Drive**: Search, file/folder listing
- **Tasks**: Full CRUD with completion

### Apple iCloud Integrations

- **Apple Mail**: Search, read, send, reply, forward, trash (IMAP/SMTP)
- **Apple Calendar**: Search, create, update, delete events (CalDAV)
- **Apple Contacts**: Search, list, create, update, delete (CardDAV)

### Microsoft 365 Integrations (OAuth 2.0 + PKCE)

- **Outlook**: Search, read, send, reply, forward, trash (Graph API)
- **Calendar**: Search, create, update, delete events (calendarView)
- **Contacts**: Search, list, create, update, delete
- **To Do**: Full CRUD with completion (task lists + tasks)
- **Multi-tenant**: Personal accounts (outlook.com) and business accounts (Azure AD) via `tenant=common`

### 3-Way Mutual Exclusivity

- Only one provider per functional category (email, calendar, contacts, tasks)
- 3 supported providers: Google, Apple, Microsoft
- Activating a new provider automatically deactivates the active competitor

### Smart Home — Philips Hue

- **Voice-controlled lighting**: Turn lights on/off, adjust brightness and colors via natural language
- **Room & scene management**: Control entire rooms or activate predefined scenes ("dim the living room", "activate movie mode")
- **Local or cloud connection**: Connect via local bridge IP or Philips Hue cloud API
- **Feature flag**: `PHILIPS_HUE_ENABLED=true` to enable

### Human-in-the-Loop (HITL)

| Type | Trigger | Severity |
|------|---------|----------|
| Plan Approval | Destructive actions | CRITICAL |
| Clarification | Detected ambiguity | WARNING |
| Draft Critique | Email/Event review | INFO |
| Destructive Confirm | Deletion of >= 3 items | CRITICAL |
| FOR_EACH Confirm | Bulk mutations | WARNING |
| Modifier Review | Review and approve AI-suggested modifications to draft content | INFO |

> Note: the plan-approval level is currently auto-approved — tool-level HITL supersedes it
> (see [ADR-106](docs/architecture/ADR-106-HITL-Contract-Coherence.md)); the other five levels
> interrupt execution and wait for the user.

### Enterprise Observability

- **Prometheus**: 423 custom metrics (agents, LLM, infrastructure)
- **Grafana**: 22 production-ready dashboards
- **Langfuse**: LLM-specific tracing with prompt versions
- **Loki**: Structured JSON logs with PII filtering
- **Tempo**: Distributed cross-service tracing
- **Probes**: liveness (`GET /health`, always 200 while the process serves — what Docker healthchecks poll) split from readiness (`GET /ready`, 503 unless PostgreSQL **and** Redis answer) — [ADR-115](./docs/architecture/ADR-115-Liveness-Readiness-Probes.md)
- **Alerting**: a 13-alert vital core (service/DB/Redis down, disk, container OOM, 5xx rate, SSE latency, backup failure, public-endpoint & TLS-certificate probes, chain self-monitoring) evaluated by Prometheus and emailed by a dedicated Alertmanager — unit-tested with `promtool test rules`, every alert linking its runbook — [ADR-119](./docs/architecture/ADR-119-Alerting-Reactivation-Minimal-Core.md)

### Cost Tracking & Billing

| Type | Tracking | Export |
|------|----------|--------|
| **LLM Tokens** | Per node, per provider | Detailed CSV |
| **Google API** | Per endpoint, per user | Detailed CSV |
| **Aggregated** | Per user, per period | CSV summary |

- **Google Maps Platform**: Places, Routes, Geocoding, Static Maps
- **Dynamic Pricing**: Admin UI for full LLM catalogue CRUD — provider, 8 capability flags (max input/output tokens, tools, structured output, strict mode, streaming, vision, reasoning) and pricing per model, all stored in the database. Same surface for image generation models (provider + quality/size/pricing). Cross-worker cache invalidation via Redis Pub/Sub (ADR-063), live cross-sibling refresh in the frontend — no code change, no redeploy
- **ContextVar Pattern**: Implicit tracking without explicit parameter passing
- **Admin CSV Exports**: Token usage, Google API usage, Consumption summary (all users or filtered by user)
- **User CSV Exports** (v1.9.1): Personal consumption export in Settings > Features — users export their own data only (`user_id` forced server-side, IDOR-safe)

### Security & Compliance

- **OAuth 2.1**: PKCE (S256), single-use state token
- **BFF Pattern**: HTTP-only cookies, Redis session with 24h TTL
- **Encryption**: Fernet (credentials), bcrypt (passwords)
- **GDPR**: Automatic PII filtering, pseudonymization, personal data export (Art. 20 data portability)
- **Per-User Usage Limits**: Token, message, and cost quotas (period/global) with 5-layer defense-in-depth enforcement, admin kill switch, real-time dashboard with WebSocket gauges. Feature flag: `USAGE_LIMITS_ENABLED=true`
- **Backups**: Automated daily PostgreSQL dumps (pg_dump sidecar, daily/weekly/monthly rotation, all `.env`-driven) with a tested one-command restore and a verification drill (`task backup:verify`) — ADR-109, runbook in `docs/runbooks/DATABASE_BACKUP_RESTORE.md`

### MCP (Model Context Protocol)

- **Per-user external servers**: Each user connects their own MCP servers (third-party tools)
- **Flexible authentication**: None, API Key, Bearer Token, OAuth 2.1 (DCR + PKCE S256)
- **Enhanced security**: HTTPS-only, SSRF prevention (DNS resolution + IP blocklist), encrypted credentials (Fernet)
- **Structured Items Parsing**: Automatic JSON array detection into individual items with McpResultCard HTML
- **Auto-generated descriptions**: LLM analysis of discovered tools to generate domain descriptions optimized for intelligent routing
- **Per-server rate limiting**: Redis sliding window per server/tool
- **Feature flag**: `MCP_USER_ENABLED=true` to enable per-user

### Multi-Channel Messaging (Telegram)

- **Bidirectional Telegram**: Full chat with LIA via Telegram (text, voice, HITL)
- **OTP Linking**: Secure account-to-Telegram linking via 6-digit OTP code (single-use, 5min TTL, brute-force protection)
- **HITL Inline Keyboards**: Approval/rejection buttons localized in 6 languages directly in Telegram
- **Voice Transcription**: Telegram voice messages to STT (Sherpa Whisper) to text processing
- **Proactive Notifications**: Reminders and interest alerts also sent via Telegram
- **Extensible Architecture**: `BaseChannelSender`/`BaseChannelWebhookHandler` abstraction for future channels (Discord, WhatsApp)
- **Observability**: 12 dedicated Prometheus RED metrics (latency, errors, volumes)
- **Feature flag**: `CHANNELS_ENABLED=true` to enable

### Autonomous Heartbeat — Proactive Notifications

- **LLM-driven proactivity**: LIA takes the initiative to inform you when relevant (weather, calendar, interests)
- **Multi-source aggregation**: Calendar, Weather (with change detection), Tasks, Interests, Memories, Activity — parallel fetch
- **2-phase LLM decision**: Phase 1 (structured output, cost-effective model) decides whether to notify, Phase 2 rewrites with user personality and language
- **Intelligent anti-redundancy**: Recent history + cross-type dedup (heartbeat vs. interests) in the decision prompt
- **User control**: Push notifications (FCM/Telegram) independently toggleable, configurable daily max (1-8), dedicated time windows (independent from interests)
- **Weather change detection**: Rain start/end, temperature drops, wind alerts — truly actionable notifications
- **Feature flag**: `HEARTBEAT_ENABLED=true` to enable

### Scheduled Actions

- **Recurring actions**: Schedule repetitive actions executed automatically (send emails, checks, reminders)
- **Timezone-aware**: Correct timezone handling per user
- **Retry logic**: Automatic retries on failure with back-off
- **Auto-disable**: Automatic deactivation after N consecutive failures
- **Multi-channel integration**: Result notifications via FCM, SSE, and Telegram
- **Feature flag**: `SCHEDULED_ACTIONS_ENABLED=true` to enable

### Sub-Agents (F6)

- **Persistent specialized agents**: Create sub-agents with custom instructions, skills, and LLM configuration
- **Read-only V1**: Sub-agents perform research, analysis, and synthesis — no write operations
- **Template-based creation**: Pre-defined templates (Research Assistant, Writing Assistant, Data Analyst)
- **Invisible to user**: The principal assistant orchestrates sub-agents and presents results naturally
- **Token guard-rails**: Per-execution budget, daily budget, auto-disable after consecutive failures
- **Feature flag**: `SUB_AGENTS_ENABLED=true` to enable (default: false)

### RAG Knowledge Spaces

- **Personal knowledge bases**: Create spaces, upload documents in 15+ formats (PDF, DOCX, PPTX, XLSX, CSV, RTF, HTML, EPUB, and more), automatic chunking and embedding
- **Google Drive folder sync**: Link Google Drive folders to spaces for automatic file vectorization with incremental change detection (new, modified, deleted). Feature flag: `RAG_SPACES_DRIVE_SYNC_ENABLED`
- **Hybrid search**: Semantic similarity (pgvector cosine) + BM25 keyword matching with configurable alpha fusion
- **Response enrichment**: RAG context automatically injected into assistant responses when active spaces exist
- **Full cost transparency**: Embedding costs tracked per document and per query, visible in chat bubbles and dashboard
- **System knowledge spaces**: Built-in FAQ knowledge base (119+ Q/A across 17 sections) indexed from Markdown files (`docs/knowledge/`). `is_app_help_query` detection by QueryAnalyzer, RoutingDecider Rule 0 override, App Identity Prompt injection with lazy loading (zero overhead on normal queries). Auto-indexed at startup with SHA-256 hash-based staleness. Admin UI for reindex and staleness monitoring. [ADR-058](./docs/architecture/ADR-058-System-RAG-Spaces.md)
- **Admin reindexation**: Full reindex when embedding model changes, with Redis mutual exclusion and automatic dimension ALTER. System spaces have independent reindex via admin API
- **Observability**: 17 Prometheus metrics (14 user + 3 system), dedicated Grafana dashboard
- **Feature flags**: `RAG_SPACES_ENABLED=true` (user spaces), `RAG_SPACES_SYSTEM_ENABLED=true` (system FAQ spaces)

### Personal Journals (Carnets de Bord) — Stratified consciousness

- **Introspective notebooks**: The assistant maintains thematic journals (self-reflection, user observations, ideas & analyses, learnings) written in first person, colored by its active personality
- **Four abstraction levels**: Each entry carries a `level` — `L0` raw observation, `L1` operational directive (`WHEN→DO BECAUSE`), `L2` transversal pattern, `L3` portrait facet. L2/L3 are produced exclusively at consolidation through active topic clustering ([ADR-079](./docs/architecture/ADR-079-Stratified-Journal-Consciousness.md))
- **Epistemic status**: `confidence` ∈ {low, medium, high} plus `evidence_count` and `contradiction_count` counters per entry. The journal distinguishes hypotheses still in test from observations validated across many turns
- **Deferred self-evaluation T → T+1**: `MessagesState.injected_journal_ids` carries IDs across turns; the post-conversation extractor sees the previous turn's directives + the current user reaction, signals `evidence_outcome="evidence" | "contradiction"`, and the service atomically increments the counters. **Zero added LLM cost** (same extractor call, enriched prompt). Anti-hallucination layer 4: LLM never writes absolute counter values.
- **Dual trigger**: Post-conversation extraction (fire-and-forget) + periodic consolidation (APScheduler, 4–12 h cooldown)
- **Gemini dual-vector embeddings**: `gemini-embedding-001` (1536d) — one vector on title+content, one on `search_hints` keywords. Search uses `LEAST(dist_content, dist_keyword)` per row to bridge the assistant's introspective vocabulary and the user's vocabulary ([ADR-069](./docs/architecture/ADR-069-Gemini-Embedding-Migration.md))
- **Ambient diffusion of the user-model portrait**: Consolidation produces, in the same LLM call, a `portrait_full` (~200 tokens) for conversation/planner and a `portrait_brief` (~60 tokens) diffused across 6 secondary flows (ReAct setup, interest proactive, reminder notification, voice, heartbeat, fallback sync+async). Standalone builder `build_journal_user_model_block(user_id, format, flow)` mirrors `build_psyche_prompt_block`.
- **Three corrective levers** on the portrait (never directly editable): edit L3 source entries, `POST /journals/portrait/feedback` (free text → L0 `user_correction` + synchronous re-consolidation), `POST /journals/consolidate` (manual, bypasses cooldown).
- **Prompt-driven lifecycle**: The assistant manages its own journals — no hardcoded auto-archival. Mandatory pairwise dedup at consolidation STEP 1, classification audit, active L1→L2 clustering at STEP 5
- **Heartbeat integration**: Journal entries enrich proactive notifications via dynamic second-pass query built from aggregated context. The compiled portrait brief is also injected so the notification voice is aligned with the same user model used by conversation
- **Full user control**: Enable/disable (data preserved), consolidation toggle, conversation history analysis (with cost warning), 4 configurable numeric settings, group-by Theme/Level toggle, filter "show only entries never used", full CRUD in Settings (level + confidence editable)
- **4-layer anti-hallucination**: prompt guidance with ID reference tables, `field_validator` on UUIDs, known-ID filtering in extraction and consolidation, atomic counter increments
- **11 Prometheus metrics**: `journal_entries_total{action,theme,source}`, `journal_evidence_total{outcome}`, `journal_consolidation_promotions_total{from_level,to_level}`, `journal_level_distribution{level}`, `journal_portrait_present_total{flow,format}`, `journal_portrait_age_hours`, `journal_portrait_feedback_total{outcome}`, etc.
- **Debug panel**: Dedicated "Personal Journals" section showing injection metrics AND background extraction results (CREATE/UPDATE/DELETE badges with theme/title/mood, even on partial updates where the LLM omits fields)
- **Cost transparency**: Real token costs tracked via TrackingContext, visible in Settings and dashboard
- **GDPR**: Account deletion scrubs the three portrait columns alongside entries; export endpoint includes the compiled portrait under a `portrait` key
- **Feature flags**: `JOURNALS_ENABLED=false` (system), user-level toggle in Settings > Features. ADRs: [ADR-057](./docs/architecture/ADR-057-Personal-Journals.md) → [ADR-064](./docs/architecture/ADR-064-Journal-Analyst-Persona.md) → [ADR-069](./docs/architecture/ADR-069-Gemini-Embedding-Migration.md) → [ADR-079](./docs/architecture/ADR-079-Stratified-Journal-Consciousness.md)

### Health Metrics — iPhone Shortcuts Batch Ingestion

- **Two token-authenticated endpoints** (`POST /api/v1/ingest/health/steps` and `/api/v1/ingest/health/heart_rate`): an iPhone Shortcut automation pushes daily batches of samples. Each sample carries its own ISO 8601 `date_start` / `date_end` — UTC-normalized server-side and second-truncated to keep uniqueness stable.
- **Polymorphic single-table storage** (`health_samples`): one row per sample with a `kind` discriminator (`heart_rate` | `steps`). Extending to `spo2` / `sleep` / `calories` reduces to a new `kind` value — no new table, no new endpoint.
- **Idempotent UPSERT** (`ON CONFLICT (user_id, kind, date_start, date_end) DO UPDATE`) using PostgreSQL's `RETURNING (xmax = 0)` trick to split insert vs update counts in a single round-trip. Re-sending the same batch is free — last value wins.
- **Flexible body parser**: accepts JSON array, NDJSON, `{"data": [...]}` envelope, and the iOS Shortcuts "Dictionnaire" wrapping (`{"<ndjson_blob>": {}}`) — no contract pressure on the user's Raccourci authoring.
- **Per-user hashed tokens**: SHA-256 digest stored, raw value (`hm_xxx`) returned once at generation, display prefix shown in Settings, individually revocable. Multiple tokens may coexist for rotation.
- **Mixed per-sample validation**: out-of-range / malformed / missing-field / invalid-date samples are individually rejected with their 0-based index + reason, while valid siblings in the same batch persist.
- **Bucketed aggregation** (`hour / day / week / month / year`): heart rate averaged (plus min / max), steps SUM-ed per bucket; gaps kept (`has_data=False`) so the UI displays honest curves.
- **Settings visualization**: four-section panel (ingestion API + tokens, recharts line/bar charts with period average overlays, statistics, deletion by kind or full wipe).
- **GDPR-aware**: deletion by kind (`DELETE ?kind=...`), full erasure (`DELETE /all`), `ON DELETE CASCADE` on the user FK.
- **Observability**: bounded-cardinality Prometheus metrics (`health_samples_upserted_total{kind, operation}`, validation rejections, rate-limit hits, auth failures, token lifecycle, deletions, latency histogram) + Grafana dashboard 21.
- **Guards**: 60 req/h/token sliding-window rate limit (configurable), 1000 samples/batch cap (`413` beyond).
- **Feature flag**: `HEALTH_METRICS_ENABLED=false` (system). [ADR-076](./docs/architecture/ADR-076-Health-Metrics-Ingestion.md) · [Guide iPhone](./docs/guides/GUIDE_IPHONE_SHORTCUTS_HEALTH.md) · [Technical doc](./docs/technical/HEALTH_METRICS.md)

### Health Metrics — Assistant Agent

- **Single `health_agent` with 7 hand-crafted tools**: steps (summary, daily breakdown, baseline delta), heart rate (summary, baseline delta), cross-kind (overview, change detection). One agent ↔ one domain pattern, mirroring `email_agent` / `event_agent`.
- **`time_min` / `time_max` windowed queries**: aggregation tools accept ISO 8601 bounds exactly like `calendar_tools.search_events_tool`. The QueryAnalyzer resolves "this week" / "last month" into concrete date ranges, and the planner splits them across the two parameters.
- **Inlined figures in the LLM message**: all factual data (totals, averages, per-day values) ship in the `UnifiedToolOutput.message` so the Response LLM surfaces them without reaching into `structured_data` (pattern from `weather_tools`).
- **Extensible registry** (`HEALTH_KINDS`): adding sleep / SpO2 / calories = one entry in `kinds.py` — bounds, merge strategy, aggregation method, baseline kind. Service helpers iterate the registry so cross-kind logic stays generic.
- **Baseline & variation detection**: rolling 28-day median with `bootstrap` → `rolling` mode switch after 7 days of data, tunable thresholds (`HEALTH_METRICS_VARIATION_*` env vars).
- **Heartbeat / Memory / Journal integration**: `health_signals` source injected for proactive context; `context_biometric` JSONB persists deltas and trends in memories (never raw values) when emotional weight crosses a threshold.
- **Per-user opt-in**: single `health_metrics_agents_enabled` toggle governs the four integrations (tool access, Heartbeat, memory extraction, journal injection). `PATCH /auth/me/health-metrics-agents-preference`.

### MCP Apps — Interactive Widgets

- **Sandboxed iframes via a CSP airlock** (ADR-098): third-party widgets boot through a same-origin shell (`public/widget-frame.html`) served with its own permissive CSP, so external-CDN widgets (Excalidraw, …) work while the main app keeps a strict policy. Isolation is the iframe `sandbox` (opaque origin, no parent cookies/DOM), not the CSP; the shell is hardened by anti-abuse locks + `frame-ancestors 'self'`
- **JSON-RPC Bridge**: Bidirectional communication between iframe app and chat via PostMessage JSON-RPC 2.0
- **Excalidraw Iterative Builder**: Intent-based diagram generation via dedicated LLM calls (shapes + arrows) with cheat sheet injection for format accuracy. Runs under a dedicated MCP-step timeout family (300 s floor / 600 s ceiling, ADR-100) so complex diagrams are not cut off mid-generation
- **`read_me` convention**: MCP servers exposing a `read_me` tool have their content auto-injected into the planner prompt
- **Auto-generated descriptions**: LLM analysis of discovered tools for domain description optimized for routing
- **App-only tools**: Tools with `visibility: ["app"]` filtered from the LLM catalogue (iframe only)

### Internationalization (i18n) — 6 Languages

LIA is fully translated in **6 languages**: English, French, German, Spanish, Italian, and Chinese.

- **Complete UI coverage**: All interfaces, dialogs, notifications, error messages, FAQ, and landing page
- **HITL localized**: Human-in-the-Loop approval prompts adapted per language
- **Proactive notifications**: Heartbeat and reminders delivered in the user's language
- **Telegram**: Inline keyboards and messages localized
- **Skills**: Auto-translated descriptions in all 6 languages
- **react-i18next**: Namespace-based translations with `locales/{lang}/translation.json`

### Landing Page & Public Showcase

- **Animated hero chat demo**: three rotating scenarios mirroring the real display modes — HITL draft approval, rich HTML weather card + proactive cross-domain initiative, multi-agent Markdown reply — with per-mode title-bar chips
- **Proof band**: verifiable engineering numbers (agents, tools, providers, tests, ADRs, releases, audit score) sourced from the codebase (`LANDING_STATS` documents each origin)
- **Two-mode diagram**: faithful LangGraph topology — router fork, five numbered pipeline steps (human approval highlighted), ReAct reason→act→observe loop, streaming convergence
- **`/story` field report** (6 languages): how LIA is built — method, trade-offs, operations, measured audit profile — on the /why–/how guide pattern
- **SEO & OpenGraph**: dynamically generated OG image, per-locale hreflang, JsonLd (WebSite, Organization, SoftwareApplication, breadcrumbs), `llms.txt` for AI crawlers
- **Public-route guard**: the 401 handler's public-page list is pinned by a filesystem-completeness test — a new public page missing from the list fails CI instead of ejecting anonymous visitors to /login
- **Authenticated redirect**: automatic redirect to dashboard if already logged in

---

## Administration & Monitoring

LIA includes a **full-featured administration interface** — giving operators complete control and real-time visibility over the system without touching configuration files or the database.

### Admin Dashboard

A web-based administration panel covering every operational aspect:

| Section | Capabilities |
|---------|-------------|
| **LLM Configuration** | Model selection per node, provider parameters, temperature/token limits, prompt versions |
| **RAG Knowledge Spaces** | Manage document spaces, embedding configuration, user reindex operations, system knowledge spaces (FAQ staleness, reindex) |
| **Personalities** | Create and manage assistant personalities (tone, language, behavior rules) |
| **User Management** | User accounts, roles, permissions, connector status overview |
| **Connector Management** | Google/Apple/Microsoft OAuth status, token health, per-user provider activation |
| **Skills Management** | Enable/disable skills, edit descriptions, translate in 6 languages, delete |
| **MCP Servers** | Admin-level MCP server configuration, tool discovery, domain descriptions |
| **LLM Pricing** | CRUD for the full LLM catalogue — provider, 8 capability flags (max input/output tokens, tools, structured output, strict mode, streaming, vision, reasoning) and pricing (input/output/cache tokens) per model. Source of truth for the LangChain factory and the agent constraints. Live cross-worker invalidation, no redeploy |
| **Image Generation Pricing** | CRUD for image models — provider, quality, size and pricing. Drives the user preferences dropdowns directly |
| **Google API Pricing** | Per-endpoint pricing configuration for Google Maps Platform services |
| **Voice Settings** | TTS catalogue management (Edge / OpenAI / ElevenLabs) via Configuration LLM (`voice_tts` type), per-provider tuning, voice picker (live ElevenLabs voices) |
| **Broadcasting** | Send system-wide notifications to all users or targeted groups |
| **Debug Settings** | Toggle debug panel visibility, configure diagnostic verbosity per user |
| **Usage Limits** | Per-user token/message/cost quotas (period + global), real-time gauges, manual block/unblock, WebSocket live updates |
| **Consumption Export** | CSV export of token usage, Google API usage, and aggregated consumption per user/period |

### Real-Time Debug Panel

A 24-section debug panel embedded in the chat interface, organized into **6 logical groups** with always-visible sections (empty sections show "N/A" instead of disappearing):

| Group | Sections |
|-------|----------|
| **Request Analysis** | Intent classification, Domain detection, Routing decision, Query transformations |
| **Planning & Execution** | Planner output, Tool selection, Context resolution, Token budget, Execution timeline, ForEach analysis, Execution waves |
| **Intelligent Mechanisms** | Cache hits, pattern learning, semantic expansion, Skills activation |
| **Context Injection** | Memory injection (scores), RAG injection (scores), Knowledge enrichment (Brave), Journal injection (per-entry scores, budget) |
| **Background Extraction** | Memory detection (create/update/delete), Journal extraction, Interest profile |
| **LLM & API Pipeline** | Request lifecycle (timing breakdown per node), LLM Pipeline (chronological reconciliation), LLM call details (model, tokens, latency, cost), Google API calls |

> The debug panel is designed for **developers and operators** to diagnose issues, optimize prompts, and understand the agent's decision-making process in real time — without needing external tools or log access.

---

## Quick Start

### Prerequisites

| Software | Version | Required |
|----------|---------|----------|
| Python | 3.12+ | Yes |
| Node.js | 24 LTS | Yes |
| Docker | 24+ | Yes |
| pnpm | 10+ | Yes |
| [Task](https://taskfile.dev/) | 3+ | Yes (build tool) |

All commands are defined in `Taskfile.yml`. Quick start: `task setup` then `task dev`.

### Express Setup (5 minutes)

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

### Development URLs

| Service | URL | Credentials |
|---------|-----|-------------|
| Frontend | http://localhost:3000 | — |
| API Docs | http://localhost:8000/docs | — |
| Grafana | http://localhost:3001 | admin/admin |
| Prometheus | http://localhost:9090 | — |

### Minimal Configuration (.env)

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/lia
REDIS_URL=redis://localhost:6379/0

# Security (REQUIRED - change in production)
SECRET_KEY=change-me-in-production-use-openssl-rand-base64-32
FERNET_KEY=your-fernet-key-here

# LLM Provider API keys are configured via Admin UI after first login
# (Settings > Administration > LLM Configuration)
# At least one provider (typically OpenAI) is required.

# Google OAuth (optional)
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...

# Feature Flags (optional, disabled by default)
MCP_ENABLED=false              # Admin MCP servers
MCP_USER_ENABLED=false         # Per-user MCP (requires MCP_ENABLED)
CHANNELS_ENABLED=false         # Multi-channel messaging (Telegram)
HEARTBEAT_ENABLED=false        # Autonomous proactive notifications
SCHEDULED_ACTIONS_ENABLED=false # Recurring scheduled actions
SUB_AGENTS_ENABLED=false       # Persistent specialized sub-agents
SKILLS_ENABLED=false           # Skills system (agentskills.io standard)
RAG_SPACES_ENABLED=true        # RAG Knowledge Spaces (document upload & retrieval)
FCM_NOTIFICATIONS_ENABLED=false # Firebase push notifications
```

---

## Architecture

### Overview

Production targets include Raspberry Pi (ARM64) via multi-arch Docker builds (`linux/amd64,linux/arm64`).

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Next.js 16 + React 19)                  │
│    Chat UI • Settings • i18n (6 languages) • SSE Streaming • Voice Mode  │
└─────────────────────────────┬───────────────────────────────────────────┘
                              │ HTTP-only cookies (session_id, 24h TTL)
┌─────────────────────────────┴───────────────────────────────────────────┐
│                     BACKEND (FastAPI + LangGraph 1.x)                    │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                 LangGraph Multi-Agent Orchestration                 │ │
│  │                                                                      │ │
│  │   Router → QueryAnalyzer → Planner → ApprovalGate → Orchestrator   │ │
│  │      ↓                                        ↓                     │ │
│  │   ┌─────────────────────────────────────────────────────────────┐  │ │
│  │   │  Contacts │ Emails │ Calendar │ Drive │ Tasks │ Reminders  │  │ │
│  │   │  Places │ Routes │ Weather │ Wikipedia │ Perplexity      │  │ │
│  │   │  Brave │ Web Search │ Web Fetch │ Browser │ Context │ Query│  │ │
│  │   └─────────────────────────────────────────────────────────────┘  │ │
│  │                              ↓                                      │ │
│  │               MCP Tools (per-user external servers)                │ │
│  │                              ↓                                      │ │
│  │                       Response Node (synthesis)                     │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │  Domain Services: Auth, Users, Connectors, RAG, Voice, Skills...    ││
│  └─────────────────────────────────────────────────────────────────────┘│
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │  Infrastructure: Redis (cache) • PostgreSQL (checkpoints) •         ││
│  │  MCP Client Pool • Prometheus (metrics) • Langfuse (traces)       ││
│  └─────────────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────────────┘
```

### Two Execution Modes

LIA offers two execution strategies, switchable per user via a toggle in the chat header:

**Pipeline mode** (default) — A feat of engineering that delivers the same power as ReAct with **4–8× fewer tokens**:

1. A smart **Planner** decomposes the request into an optimized execution plan (DSL)
2. A **Semantic Validator** checks plan coherence (cardinality, scope, dependencies)
3. An **Approval Gate** handles HITL for mutations
4. A **Task Orchestrator** executes tools in parallel waves via `asyncio.gather()`
5. **Bayesian learning** optimizes planning patterns over time

**ReAct mode** (⚡) — The LLM reasons iteratively, calling tools one by one and adapting to each result. More autonomous but higher token cost. Ideal for exploratory, research, or ambiguous queries.

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

### Code Structure (DDD)

```
apps/api/src/
├── core/                    # Modular configuration (9 modules)
│   ├── config/              # Settings per domain
│   ├── constants.py         # Global constants
│   └── bootstrap.py         # Initialization functions
├── domains/                 # Bounded Contexts (DDD)
│   ├── agents/              # LangGraph nodes, services, tools
│   │   ├── nodes/           # Graph nodes (router, planner, react ×4, response...)
│   │   ├── services/        # Smart services, HITL
│   │   ├── tools/           # Domain-specific tools
│   │   └── orchestration/   # ExecutionPlan, parallel executor
│   ├── auth/                # JWT, sessions, OAuth
│   ├── connectors/          # Google + Apple + Microsoft clients, provider resolver
│   ├── conversations/       # Conversation CRUD & history
│   ├── google_api/          # Google API pricing & usage tracking
│   ├── rag_spaces/          # RAG Knowledge Spaces (upload, embed, retrieve, system FAQ)
│   ├── user_mcp/            # Per-user MCP servers (CRUD, OAuth, domain routing)
│   ├── voice/               # TTS factory, STT, Wake Word
│   ├── skills/              # Skills system (agentskills.io standard)
│   ├── sub_agents/          # Persistent specialized sub-agents (F6)
│   ├── interests/           # Interest Learning System
│   ├── heartbeat/           # Autonomous Heartbeat (Proactive Notifications)
│   ├── channels/            # Multi-channel messaging (Telegram)
│   ├── reminders/           # Reminder & notification scheduling
│   ├── scheduled_actions/   # Recurring scheduled actions
│   ├── journals/            # Personal Journals (introspective notebooks)
│   ├── health_metrics/      # iPhone Shortcuts health ingestion + charts
│   └── users/               # User management
└── infrastructure/          # Cross-cutting concerns
    ├── cache/               # Redis sessions, LLM cache
    ├── llm/                 # Factory, providers, embeddings
    ├── mcp/                 # MCP client pool, auth, security, tool adapters
    ├── browser/             # Playwright session pool, CDP accessibility
    ├── rate_limiting/       # Distributed rate limiter
    └── observability/       # Metrics, logging, tracing
```

### Key Design Patterns

**Tool System (5-layer architecture)** — Tools are built in five composable layers: `ConnectorTool[ClientType]` (generic base with OAuth auto-refresh), `@connector_tool` (meta-decorator composing metrics + rate limiting + context save), Formatters (domain-specific result normalization), `ToolManifest` + Builder (declarative declaration with semantic keywords), and Catalogue Loader (dynamic introspection). Per-tool boilerplate reduced from ~150 to ~8 lines (94% reduction). Category-based rate limits: Read (20/min), Write (5/min), Expensive (2/5 min).

**Domain Taxonomy** — Each domain is a declarative `DomainConfig` (agents, `result_key`, `related_domains`, priority, routability). The `DOMAIN_REGISTRY` is the single source of truth consumed by SmartCatalogue (filtering), semantic expansion (adjacent domains), and the Initiative phase (structural pre-filter).

**Data Registry** — An `InMemoryStore` decouples tool results from message history. Results survive per-node message windowing (5/10/20 turns) via `@auto_save_context`, and cross-step references (`$steps.X.field`) resolve against the registry — this is what makes aggressive windowing viable without losing tool output context.

**Semantic Validator** — Before HITL approval, a dedicated LLM (distinct from the planner) inspects plans against 14 issue types across four categories: Critical (hallucinated capability, ghost dependency), Semantic (cardinality mismatch, scope overflow), Safety (dangerous ambiguity), and FOR_EACH-specific validations.

**Adaptive Re-Planner** — On execution failure, a rule-based analyser classifies the failure pattern and selects a recovery strategy. In **Panic Mode**, the SmartCatalogue expands to all tools for one retry, solving cases where domain filtering was too aggressive.

**Connector Abstraction** — Python protocols enable transparent switching between Google, Apple, and Microsoft providers. Normalizers convert provider-specific responses into unified domain models. The `ProviderResolver` guarantees only one provider per functional category (email, calendar, contacts, tasks).

**Error Architecture** — All tools return `ToolResponse`/`ToolErrorModel` with a `ToolErrorCode` enum (18+ types) and a `recoverability` flag. API-side centralized exception raisers replace raw HTTPException everywhere.

**Feature Flags** — Every optional subsystem is controlled by a `{FEATURE}_ENABLED` flag, checked at startup, route wiring, and node entry (instant short-circuit).

> Full technical details: [How does LIA work?](https://lia.jeyswork.com/how) — 25-section architecture guide

---

## Technologies

### Backend

| Technology | Version | Role |
|------------|---------|------|
| Python | 3.12+ | Primary runtime |
| FastAPI | 0.136.3 | REST API + SSE framework |
| LangGraph | 1.2.4 | Multi-agent orchestration |
| LangChain | 1.3.9 | LLM abstraction + tools |
| SQLAlchemy | 2.0.50 | Async ORM |
| Alembic | 1.18.4 | Database migrations |
| PostgreSQL | 16 + pgvector | Database + vector search |
| Redis | 7.4.0 | Cache, sessions, rate limiting |
| Pydantic | 2.13.4 | Validation + serialization |
| structlog | latest | Structured JSON logging |
| openai | 2.x | LLM provider |
| Edge TTS | 7.2+ | Voice synthesis (free) |
| mcp | 1.9+ | Model Context Protocol SDK (Streamable HTTP) |
| Docker | 24+ | Containerization (multi-arch amd64/arm64) |

### Frontend

| Technology | Version | Role |
|------------|---------|------|
| Node.js | 24 LTS | JavaScript runtime |
| Next.js | 16.2.10 | React framework |
| React | 19.2.7 | UI library |
| TypeScript | 6.0.2 | Type safety |
| TailwindCSS | 4.3.2 | Styling |
| TanStack Query | 5.101 | Server state management |
| react-i18next | 17.0.8 | i18n (6 languages) |
| Radix UI | latest | Accessible UI primitives |

**Responsive Design**: Fully optimized for desktop, tablet, and smartphone. Adaptive layouts, touch-friendly interactions, and mobile-first components ensure a seamless experience on any device.

### Supported LLM Providers

| Provider | Models | Use Case |
|----------|--------|----------|
| OpenAI | GPT-5.4, GPT-5.4-mini, GPT-5.2, GPT-5.1, GPT-5, GPT-5-mini/nano, GPT-4.1, GPT-4.1-mini/nano, GPT-4o, o1, o3-mini | Primary (prompt caching, reasoning) |
| Anthropic | Claude Opus 4.6/4.5, Claude Sonnet 4.6, Claude Haiku 4.5 | Alternative (extended thinking) |
| Google | Gemini 3.1/3/2.5 Pro, Gemini 3/2.5/2.0 Flash | Multimodal |
| DeepSeek | **deepseek-v4-flash, deepseek-v4-pro** (V4 family — thinking-mode toggle, v1.19.1+), deepseek-chat (V3, legacy), deepseek-reasoner (R1, legacy) | Cost-effective reasoning. V4 supports tools + structured output via JSON-mode fallback when thinking is on. |
| Perplexity | sonar-small/large-128k-online | Web-augmented responses. Base URL configurable via `PERPLEXITY_BASE_URL` env var (v1.19.1+). |
| Qwen | qwen3-max, qwen3.5-plus, qwen3.5-flash | Thinking + tools + vision (Alibaba Cloud DashScope). Base URL configurable via `QWEN_BASE_URL` (regional US/CN swap, v1.19.1+). |
| Ollama | Any local model (dynamic discovery) | Zero API cost, self-hosted. Base URL configurable via `OLLAMA_BASE_URL`. |

### Observability

| Technology | Role |
|------------|------|
| Prometheus | 423 metrics |
| Grafana | 25 dashboards |
| Loki | Aggregated logs |
| Tempo | Distributed tracing |
| Langfuse | LLM observability |
| structlog | Structured JSON logs |

---

## Documentation

### Main Documentation

| Document | Description |
|----------|-------------|
| [GETTING_STARTED.md](./docs/GETTING_STARTED.md) | Detailed installation guide |
| [ARCHITECTURE.md](./docs/ARCHITECTURE.md) | Complete system architecture |
| [INDEX.md](./docs/INDEX.md) | Full documentation map (190+ docs) |

### Technical Documentation

| Domain | Documents |
|--------|-----------|
| **Agents & LLM** | [GRAPH_AND_AGENTS_ARCHITECTURE](./docs/technical/GRAPH_AND_AGENTS_ARCHITECTURE.md) • [PLANNER](./docs/technical/PLANNER.md) • [SEMANTIC_ROUTER](./docs/technical/SEMANTIC_ROUTER.md) |
| **HITL** | [HITL](./docs/technical/HITL.md) • [PLAN_HITL_STREAMING_VALIDATION](./docs/technical/PLAN_HITL_STREAMING_VALIDATION.md) |
| **Voice** | [VOICE](./docs/technical/VOICE.md) • [VOICE_MODE](./docs/technical/VOICE_MODE.md) |
| **Memory** | [LONG_TERM_MEMORY](./docs/technical/LONG_TERM_MEMORY.md) • [MEMORY_RESOLUTION](./docs/technical/MEMORY_RESOLUTION.md) |
| **MCP** | [MCP_INTEGRATION](./docs/technical/MCP_INTEGRATION.md) • [GUIDE_MCP_INTEGRATION](./docs/guides/GUIDE_MCP_INTEGRATION.md) |
| **Heartbeat** | [HEARTBEAT_AUTONOME](./docs/technical/HEARTBEAT_AUTONOME.md) • [GUIDE_HEARTBEAT](./docs/guides/GUIDE_HEARTBEAT_PROACTIVE_NOTIFICATIONS.md) |
| **Channels** | [CHANNELS_INTEGRATION](./docs/technical/CHANNELS_INTEGRATION.md) • [GUIDE_TELEGRAM](./docs/guides/GUIDE_TELEGRAM_INTEGRATION.md) |
| **Scheduled Actions** | [SCHEDULED_ACTIONS](./docs/technical/SCHEDULED_ACTIONS.md) • [GUIDE_SCHEDULED_ACTIONS](./docs/guides/GUIDE_SCHEDULED_ACTIONS.md) |
| **Skills** | [SKILLS_INTEGRATION](./docs/technical/SKILLS_INTEGRATION.md) |
| **Sub-Agents** | [SUB_AGENTS](./docs/technical/SUB_AGENTS.md) |
| **RAG Spaces** | [GUIDE_RAG_SPACES](./docs/guides/GUIDE_RAG_SPACES.md) • [ADR-055](./docs/architecture/ADR-055-RAG-Spaces-Architecture.md) • [ADR-058](./docs/architecture/ADR-058-System-RAG-Spaces.md) |
| **Browser Control** | [BROWSER_CONTROL](./docs/technical/BROWSER_CONTROL.md) • [ADR-059](./docs/architecture/ADR-059-Browser-Control.md) |
| **Personal Journals** | [JOURNALS](./docs/technical/JOURNALS.md) • [ADR-057](./docs/architecture/ADR-057-Personal-Journals.md) |
| **LLM Providers** | [LLM_PROVIDERS](./docs/technical/LLM_PROVIDERS.md) |
| **CI/CD** | [CI_CD](./docs/technical/CI_CD.md) |
| **Security** | [SECURITY](./docs/technical/SECURITY.md) • [OAUTH](./docs/technical/OAUTH.md) • [RATE_LIMITING](./docs/technical/RATE_LIMITING.md) |
| **Observability** | [OBSERVABILITY_AGENTS](./docs/technical/OBSERVABILITY_AGENTS.md) • [METRICS_REFERENCE](./docs/technical/METRICS_REFERENCE.md) |
| **Cost Tracking** | [LLM_PRICING_MANAGEMENT](./docs/technical/LLM_PRICING_MANAGEMENT.md) • [GOOGLE_API_TRACKING](./docs/technical/GOOGLE_API_TRACKING.md) |

### Practical Guides

| Guide | Description |
|-------|-------------|
| [GUIDE_DEVELOPPEMENT](./docs/guides/GUIDE_DEVELOPPEMENT.md) | Complete development workflow |
| [GUIDE_AGENT_CREATION](./docs/guides/GUIDE_AGENT_CREATION.md) | How to create a new agent |
| [GUIDE_TOOL_CREATION](./docs/guides/GUIDE_TOOL_CREATION.md) | How to create a new tool |
| [GUIDE_TESTING](./docs/guides/GUIDE_TESTING.md) | Testing strategy (~11,000 tests across 559 files) |
| [GUIDE_DEBUGGING](./docs/guides/GUIDE_DEBUGGING.md) | LangGraph and log debugging |

### Architecture Decision Records (ADR)

100+ ADRs (numbered up to ADR-108) documenting major architectural decisions:

- [ADR-007: Service Layer Pattern for Node Complexity](./docs/architecture/ADR-007-Service-Layer-Pattern-For-Node-Complexity.md)
- [ADR-048: Semantic Tool Router](./docs/architecture/ADR-048-Semantic-Tool-Router.md)
- [ADR-051: Reminder & Notification System](./docs/architecture/ADR-051-Reminder-Notification-System.md)
- [View all ADRs](./docs/architecture/ADR_INDEX.md)

---

## Tests

### Running Tests

```bash
cd apps/api

# Unit tests (parallel: task test:backend:unit:fast, ~4 min)
pytest tests/unit -v

# Integration tests (require PostgreSQL + Redis)
pytest tests/integration -v

# LangGraph agent tests
pytest tests/agents -v

# Full coverage
pytest --cov=src --cov-report=html -v
# Report: htmlcov/index.html
```

### Statistics

| Metric | Value |
|--------|-------|
| Total backend tests | ~11,970 (pytest collected, 670 test files) |
| Backend breakdown | unit fast ~10,150 · agents ~970 · integration ~580 (zero skips) |
| Frontend tests (vitest) | 1,222 (+ 17 hermetic Playwright E2E incl. axe/dark/zoom) |
| Coverage target | 45% backend (ratchet) · frontend thresholds locked per category |
| CI Workflows | 3 (CI, Security, Release) |
| Technical audit | **8.3/10** across 24 normalized areas — [full public report & protocol](docs/audit/README.md) |

---

## CI/CD

LIA uses a two-layer quality gate: a **local pre-commit hook** (fast, on staged files only) and a **GitHub Actions CI pipeline** (comprehensive, on every push/PR to `main`).

### Pipeline Overview

```
Pre-commit (local)              GitHub Actions CI
===================             ==================
.bak files check                Lint Backend (Ruff + Black + MyPy)
Secrets grep                    Lint Frontend (ESLint + TypeScript)
Ruff + Black + MyPy             Fast unit tests + coverage (45%)
Fast unit tests                 Integration tests (PostgreSQL + Redis)
Critical pattern detection      Agents suite
i18n keys sync                  Code Hygiene (i18n, Alembic, lockfiles, patterns)
Alembic migration conflicts     Docker build smoke test
.env.example completeness       Secret scan (Gitleaks)
ESLint + TypeScript check       ──────────────────────
                                Security workflow (weekly)
                                  CodeQL (Python + JS)
                                  Dependency audit (pip-audit + pnpm audit)
                                  Trivy filesystem scan
                                  SBOM generation
```

### Key Practices

| Practice | Implementation |
|----------|---------------|
| **SHA-pinned Actions** | All GitHub Actions pinned by commit SHA (supply-chain security) |
| **Reproducible builds** | Universal Python lockfiles (linux/amd64 + arm64 + Windows), SHA256 hash-verified installs everywhere; CI guard fails manifest edits without lock regeneration ([ADR-112](./docs/architecture/ADR-112-Python-Dependency-Locking.md)) |
| **Least privilege** | `permissions: contents: read` on CI workflow |
| **Branch protection** | PR required (external contributors), 7 status checks, force push forbidden |
| **Dependabot** | Weekly updates for pip, npm, Docker, Actions — minor/patch grouped |
| **Pre-commit / CI alignment** | CI covers everything the pre-commit does (and more) |
| **Coverage threshold** | 45% minimum enforced in CI (ratchet +2 per release) |

### Workflows

| Workflow | Trigger | Jobs |
|----------|---------|------|
| **CI** (`ci.yml`) | Push to `main`, PR | 8 jobs: lint, unit tests, integration tests, code hygiene, docker build, secret scan |
| **Security** (`security.yml`) | PR, weekly schedule, manual | CodeQL, dependency audit, Trivy, SBOM |
| **Release** (`release.yml`) | Tag `v*` | Docker multi-arch build + push (ghcr.io), GitHub Release |

> Full details: [CI/CD Documentation](./docs/technical/CI_CD.md)

---

## Performance

### Key Metrics (P95)

| Metric | Value | SLO |
|--------|-------|-----|
| API Latency | 450ms | < 500ms |
| First SSE event (request acknowledged) | 380ms | < 500ms |
| Router Latency | 800ms | < 2s |
| Planner Latency | 2.5s | < 5s |
| Gemini Embedding | ~100-200ms | < 300ms |
| Token Reduction (Windowing) | 93% | > 80% |
| Context Compaction Savings | ~60% per compaction | — |

> These figures measure the infrastructure. The full perceived response time depends on the
> LLM call cascade (seconds to tens of seconds depending on request complexity and hardware) —
> this is the main optimization programme in progress, measured in production. The
> [July 2026 technical audit](docs/audit/README.md) scores Performance 7.5/10: instrumentation
> and caching are in place, but no sustained load campaign has been executed yet.

### Implemented Optimizations

- **Message Windowing**: 5/10/20 turns depending on node
- **Context Compaction**: LLM summarization of old messages (dynamic threshold from response model context window, configurable via `COMPACTION_*` settings)
- **Prompt Caching**: OpenAI/Anthropic (90% discount)
- **Gemini Embeddings**: gemini-embedding-001 with asymmetric task types (multilingual)
- **Parallel Execution**: asyncio.gather for independent domains
- **Redis O(1)**: Optimized operations (vs O(N) SCAN)
- **Connection Pooling**: httpx persistent connections

---

## Security

### Compliance

| Standard | Status |
|----------|--------|
| GDPR | PII filtering, data minimization |
| OWASP Top 10 | XSS, SQL injection, CSRF protection |
| Prompt Injection | External content wrapping (`<external_content>` safety markers) |
| OAuth 2.1 | Mandatory PKCE |
| Supply chain | Hash-verified universal lockfiles, pip-audit on the full transitive tree, SBOM per release |

### Reporting a Vulnerability

**DO NOT create a GitHub Issue for security vulnerabilities.**

Send an email to **liamyassistant@gmail.com** with:
- Description of the vulnerability
- Steps to reproduce
- Potential impact

We respond within 48 hours.

---

## Contributing

We welcome all contributions! See our [Contributing Guide](./CONTRIBUTING.md) to get started.

### Quick Start for Contributors

```bash
# 1. Fork and clone
git clone https://github.com/YOUR-USERNAME/LIA-Assistant.git
cd LIA-Assistant

# 2. Create a branch
git checkout -b feature/my-feature

# 3. Full setup (backend + frontend + git hooks)
task setup

# 4. Develop and test
task test:backend:unit:fast

# 5. Commit (Conventional Commits)
git commit -m "feat(agents): add weather forecast agent"

# 6. Push and create PR
git push origin feature/my-feature
```

### Types of Contributions

- Bug fixes
- New features
- Documentation
- Tests
- i18n translations (6 supported languages)
- Performance optimizations

### Standards

- **Python**: Black + Ruff + MyPy (strict)
- **TypeScript**: ESLint + Prettier
- **Commits**: [Conventional Commits](https://www.conventionalcommits.org/)
- **Coverage**: >= 45% enforced in CI (ratchet +2 per release, never lowered)
- **Pre-commit hook**: Installed via `task setup` — runs linters + tests on staged files
- **CI**: All PRs must pass 7 status checks before merge (see [CI/CD](#cicd))

---

## Support

### Getting Help

| Channel | Usage |
|---------|-------|
| [GitHub Issues](https://github.com/jgouviergmail/LIA-Assistant/issues) | Bugs, feature requests |
| [GitHub Discussions](https://github.com/jgouviergmail/LIA-Assistant/discussions) | Questions, ideas |
| liamyassistant@gmail.com | General inquiries |

### Resources

- [Full documentation](./docs/INDEX.md)
- [Practical guides](./docs/guides/)
- [Operational runbooks](./docs/runbooks/)

---

## License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.

See [LICENSE](./LICENSE) for details.

A commercial license is also available for organizations that cannot comply with AGPL-3.0 terms. Contact liamyassistant@gmail.com for details.

---

## Acknowledgments

### Open Source Technologies

This project builds on excellent open source technologies:

**Backend & Infrastructure**
- [Python](https://www.python.org/) - Primary runtime
- [FastAPI](https://fastapi.tiangolo.com/) - Modern async web framework
- [LangGraph](https://github.com/langchain-ai/langgraph) - Multi-agent orchestration
- [LangChain](https://python.langchain.com/) - LLM abstraction & tools
- [SQLAlchemy](https://www.sqlalchemy.org/) - Async ORM
- [Pydantic](https://docs.pydantic.dev/) - Data validation & settings
- [Alembic](https://alembic.sqlalchemy.org/) - Database migrations
- [PostgreSQL](https://www.postgresql.org/) + [pgvector](https://github.com/pgvector/pgvector) - Database & vector search
- [Redis](https://redis.io/) - Cache, sessions, rate limiting
- [Google Gemini Embeddings](https://ai.google.dev/gemini-api/docs/embeddings) - gemini-embedding-001 for multilingual semantic search
- [Edge TTS](https://github.com/rany2/edge-tts) - Free neural voice synthesis
- [structlog](https://www.structlog.org/) - Structured JSON logging
- [Docker](https://www.docker.com/) - Containerization & multi-arch builds

**Frontend**
- [Node.js](https://nodejs.org/) - JavaScript runtime
- [Next.js](https://nextjs.org/) - React framework
- [React](https://react.dev/) - UI library
- [TypeScript](https://www.typescriptlang.org/) - Type safety
- [TailwindCSS](https://tailwindcss.com/) - Utility-first styling
- [Radix UI](https://www.radix-ui.com/) - Accessible UI primitives
- [TanStack Query](https://tanstack.com/query/) - Server state management
- [react-i18next](https://react.i18next.com/) - Internationalization (6 languages)

**Observability**
- [Prometheus](https://prometheus.io/) - Metrics & alerting
- [Grafana](https://grafana.com/) - Dashboards & visualization
- [Loki](https://grafana.com/oss/loki/) - Log aggregation
- [Tempo](https://grafana.com/oss/tempo/) - Distributed tracing
- [Langfuse](https://langfuse.com/) - LLM observability & prompt management

### Inspirations

- [OpenAI Assistants API](https://platform.openai.com/docs/assistants/overview)
- [Anthropic Claude](https://www.anthropic.com/)
- [Model Context Protocol](https://modelcontextprotocol.io/)

---

<p align="center">
  <strong>LIA</strong> — Next-Generation Intelligent Conversational Assistant
</p>

<p align="center">
  Built with ❤️ using Python, Node.js, FastAPI, LangGraph, and Next.js
</p>

<p align="center">
  <a href="#lia">Back to top</a>
</p>
