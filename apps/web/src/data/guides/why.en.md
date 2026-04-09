# LIA — The AI Assistant That Belongs to You

> **Your Life. Your AI. Your Rules.**

**Version**: 3.0
**Date**: 2026-04-08
**Application**: LIA v1.14.5
**License**: AGPL-3.0 (Open Source)

---

## Table of Contents

1. [The context](#1-the-context)
2. [Simple administration](#2-simple-administration)
3. [What LIA can do](#3-what-lia-can-do)
4. [A server for your loved ones](#4-a-server-for-your-loved-ones)
5. [Sovereign and frugal](#5-sovereign-and-frugal)
6. [Radical transparency](#6-radical-transparency)
7. [Emotional depth](#7-emotional-depth)
8. [Production reliability](#8-production-reliability)
9. [Radical openness](#9-radical-openness)
10. [Vision](#10-vision)

---

## 1. The context

The era of agentic AI assistants has arrived. ChatGPT, Gemini, Copilot, Claude — each offers an agent capable of acting in your digital life: sending emails, managing your calendar, browsing the web, controlling your devices.

These assistants are remarkable. But they share a common model: your data lives on their servers, the intelligence is a black box, and when you leave, everything stays behind.

LIA takes a different path. Not a head-on competitor to the giants — a **personal AI assistant that you host, that you understand, and that you control**. LIA orchestrates the best AI models on the market, acts in your digital life, and does so with fundamental qualities that set it apart.

---

## 2. Simple administration

### 2.1. A guided deployment, then zero friction

Self-hosting has a bad reputation. LIA doesn't pretend to eliminate every technical step: the initial setup — configuring API keys, setting up OAuth connectors, choosing your infrastructure — takes some time and basic skills. But every step is **documented in detail** in a step-by-step deployment guide.

Once this installation phase is complete, **day-to-day management is handled entirely through an intuitive web interface**. No more terminal, no more configuration files.

### 2.2. What each user can configure

Every user has their own settings space, organized in two tabs:

**Personal preferences:**

- **Personal connectors**: plug in your Google, Microsoft or Apple accounts in a few clicks via OAuth — email, calendar, contacts, tasks, Google Drive. Or connect Apple via IMAP/CalDAV/CardDAV. API keys for external services (weather, search)
- **Personality**: choose from available personalities (professor, friend, philosopher, coach, poet...) — each influences LIA's tone, style and emotional behavior
- **Voice**: configure voice mode — wake word detection, sensitivity, silence threshold, automatic response playback
- **Notifications**: manage push notifications and registered devices
- **Channels**: link Telegram for chatting and receiving notifications on mobile
- **Image generation**: enable and configure AI image creation
- **Personal MCP servers**: connect your own MCP servers to extend LIA's capabilities
- **Appearance**: language, timezone, theme (5 palettes, dark/light mode), font (9 choices), response display format (HTML cards, HTML, Markdown)
- **Debug**: access the debug panel to inspect each exchange (if enabled by administrator)

**Advanced features:**

- **Psyche Engine**: adjust personality traits (Big Five) that modulate your assistant's emotional responsiveness
- **Memory**: view, edit, pin or delete LIA's memories — enable or disable automatic fact extraction
- **Personal journals**: configure introspection extraction after each conversation and periodic consolidation review
- **Interests**: define your favorite topics, configure notification frequency, time slots and sources (Wikipedia, Perplexity, AI reflection)
- **Proactive notifications**: set frequency, time window and context sources (calendar, weather, tasks, emails, interests, memories, journals)
- **Scheduled actions**: create recurring automations executed by the assistant
- **Skills**: enable/disable expert competencies, create your own personal Skills
- **Knowledge Spaces**: upload your documents (PDF, Word, Excel, PowerPoint, EPUB, HTML and 15+ formats) or sync a Google Drive folder — automatic indexing with hybrid search
- **Consumption export**: download your LLM and API consumption data in CSV

### 2.3. What the administrator controls

The administrator accesses a third tab dedicated to instance management:

**Users and access:**

- **User management**: create, activate/deactivate accounts, view connected services and enabled features per user
- **Usage limits**: set per-user quotas (LLM tokens, API calls, image generations) with real-time monitoring and automatic blocking
- **Broadcast messages**: send important messages to all users or a selection, with optional expiration date
- **Global consumption export**: export all-users consumption in CSV

**AI and connectors:**

- **LLM configuration**: configure provider API keys (OpenAI, Anthropic, Google, DeepSeek, Qwen, Perplexity, Ollama), assign a model per role in the pipeline, manage reasoning levels — keys stored encrypted
- **Connector activation/deactivation**: enable or disable integrations globally (Google OAuth, Apple, Microsoft 365, Hue, weather, Wikipedia, Perplexity, Brave Search). Deactivation revokes active connections and notifies users
- **Pricing**: manage pricing per LLM model (cost per million tokens), per Google Maps API (Places, Routes, Geocoding), and per image generation — with price history

**Content and extensions:**

- **Personalities**: create, edit, translate and delete personalities available to all users — set the default personality
- **System Skills**: manage instance-wide expert competencies — import/export, enable/disable, translate
- **System Knowledge Spaces**: manage the FAQ knowledge base, monitor indexing status and model migrations
- **Global voice**: configure the default TTS mode (standard or HD) for all users
- **System debug**: logging and diagnostic configuration

### 2.4. An assistant, not a technical project

LIA's goal is not to turn you into a system administrator. It's to give you the power of a full AI assistant **with the simplicity of a consumer application**. The interface is installable as a native app on desktop, tablet and smartphone (PWA), and everything is designed to be accessible without technical skills in daily use.

---

## 3. What LIA can do

LIA acts concretely in your digital life through 19+ specialized agents covering all everyday needs: managing your personal data (emails, calendar, contacts, tasks, files), accessing external information (web search, weather, places, routing), creating content (images, diagrams), controlling your smart home, autonomous web browsing, and proactively anticipating your needs.

You choose how LIA reasons, via a simple toggle (⚡) in the chat header:

- **Pipeline mode** (default) — A genuine feat of engineering: LIA plans all steps upfront, validates them semantically, then executes tools in parallel. Result: the same power as an autonomous agent, but with 4 to 8 times fewer tokens consumed. This is the most economical and predictable mode.
- **ReAct mode** (⚡) — The assistant reasons step by step: it calls a tool, analyzes the result, then decides what to do next. More autonomous, more adaptable, but more costly in tokens. Ideal for exploratory research or complex questions where the added value justifies the cost.

### 3.1. Natural conversation

Talk to LIA as you would to a human assistant — no commands to memorize, no syntax to follow. LIA understands and responds in 99+ languages, with an interface available in 6 languages (French, English, German, Spanish, Italian, Chinese). Responses are rendered as interactive HTML visual cards, direct HTML, or Markdown based on your preferences.

### 3.2. Personal connected services

- **Email**: read, search, compose, send, reply, forward — via Gmail, Outlook or Apple Mail
- **Calendar**: view, create, modify, delete events — via Google Calendar, Outlook Calendar or Apple Calendar
- **Contacts**: search, create, modify contacts — via Google Contacts, Outlook Contacts or Apple Contacts
- **Tasks**: manage your task lists — via Google Tasks or Microsoft To Do
- **Files**: access Google Drive to search and read your documents
- **Smart Home**: control your Philips Hue lighting — on/off, brightness, colors, scenes, room management

### 3.3. Web intelligence and environment

- **Web search**: multi-source search (Brave Search, Perplexity, Wikipedia) for comprehensive, sourced answers
- **Weather**: current conditions and 5-day forecasts, with change detection (rain start/end, temperature drops, wind alerts)
- **Places and businesses**: nearby location search with details, hours, reviews
- **Routing**: multi-modal route calculation (car, walking, cycling, transit) with automatic geolocation

### 3.4. Voice

LIA offers a complete voice mode:

- **Push-to-Talk**: hold the microphone button to speak, optimized for mobile
- **"OK Guy" wake word**: hands-free detection running **entirely in your browser** via Sherpa-onnx WASM — no audio is transmitted until the wake word is detected
- **Voice synthesis**: standard mode (Edge TTS, free) or HD (OpenAI TTS / Gemini TTS)
- **Telegram voice messages**: send audio messages, LIA transcribes and responds

### 3.5. Creation and media

- **Image generation**: create images from text descriptions, edit existing photos
- **Excalidraw diagrams**: generate diagrams and schemas directly in conversation
- **Attachments**: attach photos and PDFs — LIA analyzes visual content and extracts text from documents
- **MCP Apps**: interactive widgets directly in chat (forms, visualizations, mini-applications)

### 3.6. Proactivity and initiative

LIA doesn't just respond — it anticipates:

- **Proactive notifications**: LIA cross-references your context sources (calendar, weather, tasks, emails, interests) and notifies you when something is genuinely useful — with a built-in anti-spam system (daily quota, time window, cooldown)
- **Conversational initiative**: during an exchange, LIA proactively checks related information — if weather forecasts rain on Saturday, it checks your calendar to flag potential outdoor activities
- **Interests**: LIA progressively detects topics you're passionate about and can send you relevant content
- **Sub-agents**: for complex tasks, LIA delegates to ephemeral specialized agents working in parallel

### 3.7. Autonomous web browsing

A browsing agent (Playwright/Chromium headless) can navigate websites, click, fill forms, extract data from dynamic pages — from a simple natural language instruction. A simplified extraction mode converts any URL into usable text.

### 3.8. Server administration (DevOps)

By installing Claude CLI (Claude Code) directly on the server, administrators can diagnose their infrastructure in natural language from LIA's chat: check Docker logs, verify container health, monitor disk space, analyze errors. This feature is restricted to administrator accounts.

---

## 4. A server for your loved ones

### 4.1. LIA is a shared web server

Unlike personal cloud assistants (one account = one user), LIA is designed as a **centralized server** that you deploy once and share with your family, friends, or team.

Each user gets their own account with:

- Their profile, preferences, language
- **Their own assistant personality** with its own mood, emotions and unique relationship — thanks to the Psyche Engine, each user interacts with an assistant that develops a distinct emotional bond
- Their memory, recollections, personal journals — fully isolated
- Their own connectors (Google, Microsoft, Apple)
- Their private knowledge spaces

### 4.2. Per-user usage management

The administrator maintains control over consumption:

- **Usage limits** configurable per user: message count, tokens, maximum cost — per day, week, month, or as a global cumulative cap
- **Visual quotas**: each user sees their consumption in real time with clear gauges
- **Connector activation/deactivation**: the administrator enables or disables integrations (Google, Microsoft, Hue...) at the instance level

### 4.3. Your family AI

Imagine: a Raspberry Pi in your living room, and the whole family enjoying an intelligent AI assistant — each with their own personalized experience, memories, conversation style, and an assistant that develops its own emotional relationship with them. All under your control, without a cloud subscription, without data leaving for a third party.

---

## 5. Sovereign and frugal

### 5.1. Your data stays with you

When you use ChatGPT, your conversations live on OpenAI's servers. With Gemini, at Google's. With Copilot, at Microsoft's.

With LIA, **everything stays in your PostgreSQL**: conversations, memory, psychological profile, documents, preferences. You can export, back up, migrate or delete all your data at any time. GDPR is not a constraint — it's a natural consequence of the architecture. Sensitive data is encrypted, sessions are isolated, and automatic personally identifiable information (PII) filtering is built in.

### 5.2. Even a Raspberry Pi is enough

LIA runs in production on a **Raspberry Pi 5** — a single-board computer costing around $80. 19+ specialized agents, a full observability stack, a psychological memory system, all on a tiny ARM server. Multi-architecture Docker images (amd64/arm64) enable deployment on any hardware: Synology NAS, VPS for a few dollars a month, enterprise server, or Kubernetes cluster.

Digital sovereignty is no longer an enterprise privilege — it's a right accessible to everyone.

### 5.3. Optimized for frugality

LIA doesn't just run on modest hardware — it **actively optimizes** its AI resource consumption:

- **Catalog filtering**: only the tools relevant to your query are presented to the LLM, drastically reducing token consumption
- **Pattern learning**: validated plans are memorized and reused without calling the LLM again
- **Message Windowing**: each component sees only the strictly necessary context
- **Prompt caching**: leveraging native provider caching to limit recurring costs

These combined optimizations enable a significant reduction in token consumption compared to ReAct mode.

---

## 6. Radical transparency

### 6.1. No black box

When a cloud assistant executes a task, you see the result. But how many AI calls? Which models? How many tokens? What cost? Why that decision? You have no idea.

LIA takes the opposite approach — **everything is visible, everything is auditable**.

### 6.2. The built-in debug panel

Right in the chat interface, a debug panel exposes in real time each conversation with details on intent analysis (message classification and confidence score), execution pipeline (generated plan, tool calls with inputs/outputs), LLM pipeline (every AI call with model, duration, tokens and cost), injected context (memories, RAG documents, journals) and the complete request lifecycle.

### 6.3. Cost tracking to the penny

Each message shows its cost in tokens and currency. Users can export their consumption. Administrators get real-time dashboards with per-user gauges and configurable quotas.

You're not paying a subscription that hides the real costs. You see exactly what each interaction costs, and you can optimize: economical model for routing, more powerful for the response.

### 6.4. Trust through evidence

Transparency is not a technical gimmick. It changes your relationship with your assistant: you **understand** its decisions, you **control** your costs, you **detect** problems. You trust because you can verify — not because you're asked to believe.

---

## 7. Emotional depth

### 7.1. Beyond factual memory

Major assistants remember your preferences and personal facts. That's useful, but flat. LIA goes further with a structured **psychological and emotional understanding**.

Each memory carries an emotional weight (-10 to +10), an importance score, a usage nuance, and a psychological category. This isn't a simple database — it's a profile that understands what moves you, what motivates you, what hurts you.

### 7.2. The Psyche Engine: a living personality

This is LIA's deepest differentiator. ChatGPT, Gemini, Claude — all have a fixed personality. Every message is an emotional blank slate. LIA is different.

The **Psyche Engine** gives LIA a dynamic psychological state that evolves with every exchange:

- **14 moods** that fluctuate with the conversation's tone (serene, curious, melancholic, playful...)
- **22 emotions** that trigger and fade in response to your words
- **A relationship** that deepens message after message
- **Personality traits** (Big Five) inherited from the chosen personality
- **Motivations** that influence the assistant's proactivity

You're not talking to a tool — you're interacting with an entity whose vocabulary warms up when touched, whose sentences shorten under tension, whose humor emerges when the exchange is light. And it never says so — it **shows** it.

### 7.3. Personal journals

LIA keeps its own reflections in **personal journals**: self-reflection, observations about the user, ideas, learnings. These notes, written in the first person and colored by the active personality, organically influence future responses.

This is a form of artificial introspection — the assistant reflecting on its interactions and developing its own perspectives. The user retains full control: reading, editing, deleting.

### 7.4. Emotional safety

When a memory with a strong negative emotional charge is activated, LIA automatically switches to protective mode: never joke, never minimize, never trivialize. The assistant adapts its behavior to the emotional reality of the person — not a one-size-fits-all treatment.

### 7.5. Self-knowledge

LIA has a built-in knowledge base about its own capabilities, allowing it to answer questions about what it can do, how it works, and what its limitations are.

---

## 8. Production reliability

### 8.1. The real challenge of agentic AI

The vast majority of agentic AI projects never reach production. Uncontrolled costs, non-deterministic behavior, missing audit trails, failing agent coordination. LIA has solved these problems — and runs in production 24/7 on a Raspberry Pi.

### 8.2. A professional observability stack

LIA ships with production-grade observability:

| Tool | Role |
| --- | --- |
| **Prometheus** | System and business metrics |
| **Grafana** | Real-time monitoring dashboards |
| **Tempo** | End-to-end distributed tracing |
| **Loki** | Structured log aggregation |
| **Langfuse** | Specialized LLM call tracing |

Every request is traced end-to-end, every LLM call is measured, every error is contextualized. This isn't monitoring bolted on as an afterthought — it's a **foundational architectural decision** documented across the project's Architecture Decision Records.

### 8.3. An anti-hallucination pipeline

The response system features a three-layer anti-hallucination mechanism: data formatting with explicit boundaries, directives enforcing exclusive use of verified data, and explicit edge case handling. The LLM is constrained to synthesize only what comes from actual tool results.

### 8.4. Human-in-the-Loop with 6 levels

LIA doesn't refuse sensitive actions — it **submits** them to you with the appropriate level of detail: plan approval, clarification, draft critique, destructive confirmation, batch operation confirmation, modification review. Each approval feeds the learning system — the system accelerates over time.

---

## 9. Radical openness

### 9.1. Zero lock-in

ChatGPT ties you to OpenAI. Gemini to Google. Copilot to Microsoft.

LIA connects you to **8 AI providers simultaneously**: OpenAI, Anthropic, Google, DeepSeek, Perplexity, Qwen, and Ollama (local models). You can mix: OpenAI for planning, Anthropic for response, DeepSeek for background tasks — all configurable from the admin interface, in one click.

If a provider changes its pricing or degrades its service, you switch instantly. No dependency, no trap.

### 9.2. Open standards

| Standard | Usage in LIA |
| --- | --- |
| **MCP** (Model Context Protocol) | Per-user external tool connections |
| **agentskills.io** | Injectable skills with progressive disclosure |
| **OAuth 2.1 + PKCE** | Authentication for all connectors |
| **OpenTelemetry** | Standardized observability |
| **AGPL-3.0** | Complete, auditable, modifiable source code |

### 9.3. Extensibility

Each user can connect their own MCP servers, extending LIA's capabilities far beyond built-in tools. Skills (agentskills.io standard) allow injecting expert instructions in natural language — with a built-in Skill generator to create them easily.

LIA's architecture is designed to facilitate adding new connectors, channels, agents and AI providers. The code is structured with clear abstractions and dedicated development guides (agent creation guide, tool creation guide) that make extension accessible to any developer.

### 9.4. Multi-channel

The responsive web interface is complemented by a native Telegram integration (conversation, transcribed voice messages, inline approval buttons, proactive notifications) and Firebase push notifications. Your memory, journals, and preferences follow you from one channel to another.

---

## 10. Vision

### 10.1. Intelligence that grows with you

The combination of psychological memory + introspective journals + Bayesian learning + Psyche Engine creates a form of emergent intelligence: over the months, LIA develops an increasingly nuanced understanding of who you are. This isn't artificial general intelligence — it's **practical, relational, and emotional intelligence**, in service of a specific person.

### 10.2. What LIA does not claim to be

LIA is not a competitor to cloud giants and does not claim to rival their research budgets. As a pure conversational chatbot, the models used through their native interfaces will likely be more fluid. But LIA isn't a chatbot — it's an **intelligent orchestration system** that uses these models as components, under your full control.

### 10.3. Why LIA exists

LIA exists because the world lacks an AI assistant that is truly **yours**. Simple to administer day-to-day. Shareable with your loved ones, each with their own emotional relationship. Hosted on your server. Transparent about every decision and every cost. Capable of an emotional depth that commercial assistants don't offer. Reliable in production. And open — open on providers, standards, and code.

**Your Life. Your AI. Your Rules.**
