# LIA — The AI Assistant That Belongs to You

> **Your Life. Your AI. Your Rules.**

**Version**: 4.8
**Date**: 2026-08-17
**Application**: LIA v1.30.8
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

Since v1.29.0 that first phase is itself guided: `./install.sh` at the repository root asks a short questionnaire in your language — how you want to reach the instance, which provider keys you hold — then builds the images from the source you cloned, applies the reference data in a single transaction, creates your administrator account without ever putting a secret on the command line, and finally verifies that the installation genuinely works rather than merely answering. If a step fails, resuming picks up exactly where it stopped.

### 2.2. What each user can configure

Every user has their own settings space, organized in two tabs. A search field saves you from walking through them: type the name of a setting — or a word close to it in your own language — and LIA opens the right section, whichever tab it lives in.

**Personal preferences:**

- **Personal connectors**: plug in your Google, Microsoft or Apple accounts in a few clicks via OAuth — email, calendar, contacts, tasks, Google Drive. Or connect Apple via IMAP/CalDAV/CardDAV. API keys for external services (weather, search)
- **Personality**: choose from available personalities (professor, friend, philosopher, coach, poet...) — each influences LIA's tone, style and emotional behavior
- **Voice**: configure voice mode — wake word detection, sensitivity, silence threshold, automatic response playback
- **Notifications**: manage push notifications and registered devices
- **Channels**: link Telegram for chatting and receiving notifications on mobile
- **Image generation**: enable and configure AI image creation
- **Personal MCP servers**: connect your own MCP servers to extend LIA's capabilities
- **Appearance**: language, timezone, theme (5 palettes, dark/light mode), font (9 choices), response display format (HTML cards, HTML, Markdown)
- **My dashboard**: hide or reorder the 9 briefing cards — a hidden card is not even fetched anymore
- **Debug**: access the debug panel to inspect each exchange (if enabled by administrator)

**Advanced features:**

- **Psyche Engine**: adjust personality traits (Big Five) that modulate your assistant's emotional responsiveness
- **Memory**: view, edit, pin or delete LIA's memories — enable or disable automatic fact extraction
- **Personal journals**: configure introspection extraction after each conversation and periodic consolidation review
- **Interests**: define your favorite topics, configure notification frequency, time slots and sources (Perplexity, Brave, Wikipedia, AI reflection)
- **Proactive notifications**: set frequency, time window and context sources (calendar, weather, tasks, emails, interests, memories, journals)
- **Scheduled actions**: create recurring automations executed by the assistant
- **Skills**: enable/disable expert competencies in a gallery with previews, create your own personal Skills, or install one from an https URL (server-validated)
- **Knowledge Spaces**: upload your documents (PDF, Word, Excel, PowerPoint, EPUB, HTML and 15+ formats) or sync a Google Drive folder — automatic indexing with hybrid search
- **Consumption export**: download your LLM and API consumption data in CSV

### 2.3. What the administrator controls

The administrator accesses a third tab dedicated to instance management:

**Users and access:**

- **User management**: create, activate/deactivate accounts, view connected services and enabled features per user
- **Usage limits**: set per-user quotas (LLM tokens, API calls, image generations) with real-time monitoring and automatic blocking
- **Broadcast messages**: send important messages to all users or a selection, with optional expiration date
- **Global consumption export**: export all-users consumption in CSV
- **Instance daily budget**: cap what the WHOLE instance may spend in a day, in euros — not just what each account consumes. The panel shows today's spend, the run count, the ceiling that actually applies and what remains; the operator value may only tighten the deployment bound, never widen it. When the budget is exhausted, users are told the deployment is paused and given the exact time it resets, not a false message about their personal quota
- **Platform capabilities**: turn ten capabilities on or off instantly, with no redeploy — dictation, speech synthesis, images, uploads, document spaces, web search, browsing, skills, MCP, telephony. A disabled capability also disappears from the catalogue offered to the planner, so LIA stops proposing what the routes would refuse; each row shows what the deployment allows, what you chose, and what is actually enforced

**AI and connectors:**

- **LLM configuration**: configure provider API keys (OpenAI, Anthropic, Google, DeepSeek, Qwen, Perplexity, Ollama), assign a model per role in the pipeline, manage reasoning levels — keys stored encrypted. The dialog only exposes the parameters the chosen model actually accepts (per-model DB matrix for temperature, top_p, frequency_penalty, presence_penalty and reasoning widget shape), preventing entry of any value the API would reject
- **Connector activation/deactivation**: enable or disable integrations globally (Google OAuth, Apple, Microsoft 365, Hue, weather, Wikipedia, Perplexity, Brave Search). Deactivation revokes active connections and notifies users
- **Pricing**: manage pricing per LLM model (cost per million tokens), per Google Maps API (Places, Routes, Geocoding), and per image generation — with price history. When adding a new reasoning model, a "copy shape from such existing model" selector lets the operator inherit the reasoning widget and its values without manual entry; Custom mode remains available for atypical models. Text-model tariffs can also vary by UTC time of day (peak/off-peak windows, DeepSeek-style): each call is then valued at the tariff of its exact moment, and usage statistics match the provider's real invoice

**Content and extensions:**

- **Personalities**: create, edit, translate and delete personalities available to all users — set the default personality
- **System Skills**: manage instance-wide expert competencies — import/export, enable/disable, translate
- **System Knowledge Spaces**: manage the FAQ knowledge base, monitor indexing status and model migrations
- **Global voice**: configure the default TTS provider, model, and voice for all users (Edge free, OpenAI, or ElevenLabs), with per-provider tuning (speed, stability, audio format)
- **System debug**: logging and diagnostic configuration

### 2.4. An assistant, not a technical project

LIA's goal is not to turn you into a system administrator. It's to give you the power of a full AI assistant **with the simplicity of a consumer application**. The interface is installable as a native app on desktop, tablet and smartphone (PWA), and everything is designed to be accessible without technical skills in daily use.

---

## 3. What LIA can do

LIA acts concretely in your digital life through 20+ specialized agents covering all everyday needs: managing your personal data (emails, calendar, contacts, tasks, files), accessing external information (web search, weather, places, routing), creating content (images, diagrams, documents), controlling your smart home, autonomous web browsing, and proactively anticipating your needs.

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
- **Position on the move**: when your live position is unavailable (a mobile app left dormant), LIA uses your last remembered position — if you enabled it — rather than your home address, and always states that position's age instead of presenting it as current

### 3.4. Voice

LIA offers a complete voice mode:

- **Push-to-Talk**: hold the microphone button to speak, optimized for mobile
- **"OK Guy" wake word**: hands-free detection running **entirely in your browser** via Sherpa-onnx WASM — no audio is transmitted until the wake word is detected
- **Voice synthesis**: three admin-configurable providers — Edge TTS (free), OpenAI TTS (`tts-1` / `tts-1-hd`), or ElevenLabs (`eleven_multilingual_v2`, `eleven_turbo_v2_5`, `eleven_flash_v2_5`)
- **Telegram voice messages**: send audio messages, LIA transcribes and responds

### 3.5. Creation and media

- **Image generation**: create images from text descriptions, edit existing photos
- **Document generation**: ask for a CSV, an Excel sheet, a Word report, a PowerPoint or a PDF — a dedicated writer model produces the content in your language, a local renderer builds the real file, and it arrives as a downloadable card with an explicit expiry date
- **Excalidraw diagrams**: generate diagrams and schemas directly in conversation
- **Attachments**: attach photos and PDFs — LIA analyzes visual content and extracts text from documents
- **MCP Apps**: interactive widgets directly in chat (forms, visualizations, mini-applications)

### 3.6. Proactivity and initiative

LIA doesn't just respond — it anticipates:

- **Proactive notifications**: LIA cross-references your context sources (calendar, weather, tasks, emails, interests) and notifies you when something is genuinely useful — with a built-in anti-spam system (daily quota, time window, cooldown)
- **Conversational initiative**: during an exchange, LIA proactively checks related information — if weather forecasts rain on Saturday, it checks your calendar to flag potential outdoor activities
- **Interests**: LIA keeps what you actually care about, not what you asked once — asking a question is a task, not a taste, and it takes a stated passion, a practice, real prior knowledge or genuine digging for a subject to count. Themes rotate (never the same subject twice in a row), every notification includes clickable links to its sources, and a subject you refuse does not come back: the block is compared against every new subject, including under another name
- **Sub-agents**: for complex tasks, LIA delegates to ephemeral specialized agents working in parallel

### 3.7. Autonomous web browsing

A browsing agent (Playwright/Chromium headless) can navigate websites, click, fill forms, extract data from dynamic pages — from a simple natural language instruction. A simplified extraction mode converts any URL into usable text.

### 3.8. Server administration (DevOps)

By installing Claude CLI (Claude Code) directly on the server, administrators can diagnose their infrastructure in natural language from LIA's chat: check Docker logs, verify container health, monitor disk space, analyze errors. This feature is restricted to administrator accounts.

### 3.9. Personal health data

LIA welcomes your heart-rate and step-count measurements from **any source** — the documented, simplest path is an iPhone Shortcuts automation pushing Apple Health, but any system capable of signing an HTTP call (Android automation, personal scripts, compatible IoT) can feed the ingestion API. The protocol accepts **batches** rather than a continuous push: each sample carries its own measurement interval, and the server deduplicates naturally on those intervals — re-sending the same data multiple times is harmless. When two sensors (Apple Watch + iPhone, for example) cover the same period, LIA merges them automatically: maximum for steps (each sensor captures a complementary slice of movement), rounded average for heart rate.

The data stays inside your LIA instance — no third-party service has access — and is visualized in a dedicated Settings section, as a line chart (HR) and bar chart (steps), with a period selector (hour, day, week, month, year) and a dashed line for the period average.

Ingestion is authenticated by a **dedicated token** (starting with `hm_…`) that you generate from the app and can revoke at any time. The token only authorizes health-data ingestion — never the rest of your account. You can generate several (one per device) and manage them independently.

An **"Assistant" toggle** (off by default, *opt-in*) lets you, if you wish, authorize the assistant to read these measurements and answer factual questions ("How many steps this week?", "My average heart rate today?", "Am I walking less than usual?"), enrich proactive notifications that combine health + weather + calendar, and attach a non-raw biometric context (deltas, trends) to its memories and internal journals. A single switch governs these four integrations. Never diagnostic — only factual figures, with a baseline that qualifies itself honestly ("based on only N days" while history is under 7 days).

Three management actions give you full control: delete all heart-rate samples, delete all step samples, or wipe everything. No raw physiological value is ever kept in server logs — GDPR compliance is built in by design.

### 3.10. Calling on your behalf

LIA can pick up the phone for you. Ask it to "call the garage to check if the car is ready" or "call Marie and ask if she's free Tuesday evening", and LIA places a real outbound call, holds the conversation toward your goal, and brings back a written summary — with a one-tap follow-up when there's something to do next (booking the slot it just agreed, for instance).

You are always in the loop: before dialing, LIA tells you exactly **who** it will call and **why**, and waits for your go-ahead. And that control doesn't stop during the call: the assistant operates under a strict mandate — if the person offers an extra, an option or any unplanned commitment (even a small one), it never accepts on your behalf; it notes the offer and its price, announces a call-back, and the summary hands you every cost and every open point so you decide. The summary lands in the chat asynchronously, so you can keep doing other things while the call happens.

And it stays private by construction. During a call LIA can only tell whether you're free or busy at a given time — never the titles, guests or places on your calendar. Nothing is recorded, the conversation is never stored, and only a short summary is kept before it expires. Phone calls run through your own ElevenLabs connector, billed on your account, and the feature is there only if your administrator turned it on.

### 3.11. Talking to your people, assistant to assistant

On the same instance, two users can connect — and their assistants talk to each other. You say “ask Marie if she is free on Tuesday”, you approve the exact wording, and it is Marie’s assistant that delivers the message, in her assistant’s own personality, naming you; yours confirms delivery back to you. Each connection can also open chosen, read-only shares: your calendar availability, your task titles — nothing more, nothing by default.

Protecting people comes before the feature: discovery is opt-in and exact-identity only — a full name or an address, never a fragment, blocking is silent (the other side never learns of it), and an unknown person, a decline or a block all receive exactly the same answer — probing who exists is impossible. Every access to a share is re-checked at the moment of the read and journaled, and relayed message content is erased after thirty days, leaving only the trace of the exchange.
### 3.12. What ties you to someone, gathered

The **Relations** page brings together, person by person, what LIA already tracks: the commitments open between you, the calls placed, the memories that mention them, the messages your assistants passed on. Nothing new is collected — it is a lens over what already exists.

You can also just ask, without opening the page: "when did I last call Marie?", "what do I owe her?". The answer comes from the same computation as the card, so the assistant and the page cannot tell you two different things — and the total stated is exact, never the length of what happens to fit on screen.

What remains is what no system can guess. LIA groups what is written the same, accents and capitals aside; it cannot know that a number jotted down one day and a name are the same person, or that "Dad" is anyone in particular. That is a judgement, and it is yours: you say it once, from the card, and it is **reversible** — the merge is shown with its own undo, and nothing is rewritten in your sources. A display grouping never changes who a message is addressed to, either.


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
- **An instance-wide ceiling**, on top of the per-user ones: N accounts × their quota is unbounded spend, so a daily euro ceiling bounds the deployment itself. It is first come, first served — and where a per-user limit fails open, an unknown instance spend fails closed

### 4.3. Your family AI

Imagine: a Raspberry Pi in your living room, and the whole family enjoying an intelligent AI assistant — each with their own personalized experience, memories, conversation style, and an assistant that develops its own emotional relationship with them. All under your control, without a cloud subscription, without data leaving for a third party.

---

## 5. Sovereign and frugal

### 5.1. Your data stays with you

When you use ChatGPT, your conversations live on OpenAI's servers. With Gemini, at Google's. With Copilot, at Microsoft's.

With LIA, **everything stays in your PostgreSQL**: conversations, memory, psychological profile, documents, preferences. You can export, back up, migrate or delete all your data at any time — including a one-click complete export from the settings: readable Markdown, structured JSON and your files, with secret material unexportable by construction. And every device connected to your account is visible and revocable in one click. GDPR is not a constraint — it's a natural consequence of the architecture. Sensitive data is encrypted, sessions are isolated, and automatic personally identifiable information (PII) filtering is built in. Your position follows the same doctrine: remembering the last position is an explicit choice, encrypted like everything else, never historized — each update overwrites the previous one — and erased the moment you switch the option off.

The protection covers what comes **in**, too. Every day LIA reads text you did not write: an email body, an invitation description authored by its organiser, a web page, a place listing. Anyone can slip an instruction meant for the assistant inside them. Every piece of data now carries its provenance, and what comes from outside arrives labelled as **material to analyse, never as an order to follow** — with manipulation attempts spotted and named, across the six languages. Your content is never rewritten for that: an email stays what its author wrote. Rewriting would give the illusion of a guarantee that the next bypass would deny; naming what we see is more honest, and more useful.

### 5.2. Even a Raspberry Pi is enough

LIA runs in production on a **Raspberry Pi 5** — a single-board computer costing around $80. 20+ specialized agents, a full observability stack, a psychological memory system, all on a tiny ARM server. Multi-architecture Docker images (amd64/arm64) enable deployment on any hardware: Synology NAS, VPS for a few dollars a month, enterprise server, or Kubernetes cluster.

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

The same transparency applies to actions: under every response, a collapsed “⚙ N steps · X s” line unfolds what actually happened — routing, tools called, duration — and that trace is stored with the message: it survives reloads, on every device. Every response can also be rated with a discreet 👍/👎, remembered and fed back into the assistant's learning — never used to regenerate the answer on your behalf.

### 6.4. Trust through evidence

Transparency is not a technical gimmick. It changes your relationship with your assistant: you **understand** its decisions, you **control** your costs, you **detect** problems. You trust because you can verify — not because you're asked to believe.

---

This transparency extends to the system's own quality. The complete technical audit — scores, method, strengths and what remains to be improved — is published in the repository, with the protocol to rerun it and the commands to verify the measurements: [full audit report](https://github.com/jgouviergmail/LIA-Assistant/blob/main/docs/audit/README.md). You are not asked to trust the figures on this site; you can check them.

The same honesty applies to usefulness itself: LIA measures whether it actually helps — an outcome only counts once you validated it, explicitly or by leaving an action uncorrected — and that measurement lives in the same local database as your data, with no third-party analytics platform involved, ever.

And it applies to confirmations: LIA never announces as done what its own tools refused. Each tool's verdict — success or refusal, with its cause — crosses the system unchanged, all the way to the answer. If a message is too long to leave, you do not get an "it's sent": you get the exact length, the limit, and an offer to shorten it.

The same principle applies to the protections themselves. Security that is announced but unverifiable is treated as absent: every control is backed by a test that fails if the control disappears, and when a fix is written the old behaviour is restored long enough to confirm the test catches it. A test that cannot fail proves nothing.

Nor does a test that never runs — and that is the least comfortable discovery this project has made. Ten test files had switched themselves off whenever a provider key was missing, and nothing reported it any more: a skipped test counts as green, coverage measures lines reached rather than assertions executed, and a review sees a test file and concludes the surface is protected. Two hundred and nineteen tests had never run once; switching them back on surfaced four genuine defects — among them a voice that split every number in two, and a reminder lost for good when the usage budget ran out in the wrong minute. The absence of a red signal is not proof of health: sometimes it is only the absence of measurement. A continuous-integration guard now refuses to let a test module go quiet.

The same principle applies to what is **advertised**. A panel showed a "hybrid search" switch for memory; the matching engine had not existed for several versions, and the switch commanded nothing. The dead code and the display were removed together, and the real behaviour written in their place. A capability advertised but absent is not a documentation imprecision: it is a promise made to a user who has no way of checking it. Showing a setting that controls nothing is worse than showing nothing.

### 6.5. Why LIA thinks that

An assistant that remembers things ends up asserting them. “You prefer morning meetings”, “this topic interests you”: useful conclusions, but unverifiable as long as you cannot trace back to what produced them.

Under every memory, every journal entry and every interest, LIA therefore shows the signals that led it there: the conversation, the date, and the signal's role — what gave rise to the conclusion, what confirmed it, what cast doubt on it. A button lets you correct the conclusion at its source.

What is kept is a **reference, never a copy**. Your text stays where you wrote it, and if you delete the conversation it comes back nowhere: the reference empties, the row stays dated, and LIA simply says the signal was deleted. A deletion must remain a deletion — otherwise what you erase on one side would be served back to you on the other.

The same principle applies to an interest's weight: it explains itself instead of scoring itself. The originating signal, the last mention, the calculation itself — enough to redo the arithmetic. Turning that uncertainty into a score would invite a competition nobody asked for, while teaching nothing more.

### 6.6. Legible without effort

Transparency does not stop at what the system shows: it also covers how it shows it. A screen where everything carries the same weight asks the reader to do the sorting, and there is no reason that work should fall to them.

An urgent alert therefore does not look like an ordinary one — and that is not only a matter of colour. Two neighbouring hues merge on a screen, all the more so on a phone, in bright sunlight, or for someone who tells them apart poorly. What separates the levels here is **density**: a solid ground against a light tint, a difference that holds even in black and white.

The same principle applies throughout: a count wears the colour of the other counts, an action button has the same shape from one screen to the next, a sent message is not told apart from a received one by a single small arrow. None of this adds information — all of it saves time on what is already there.

And colour never carries meaning on its own: every label keeps its word. An interface that only works in colour does not work for everyone.

### 6.4. Even what LIA learns about you is inspectable

The same transparency covers habit learning: what LIA believes about your rhythm and your recurring requests sits in a dedicated panel — a 24-hour heat map, your active-day percentage, a progress bar toward the first claims, and for every habit the real days it was observed plus the exact thresholds the detector applied. When there is no stable habit, the panel says so instead of inventing one. Pause, permanent block, total deletion, instant retroactive recompute — and the whole feature is off until you turn it on.

## 7. Emotional depth

### 7.1. Beyond factual memory

Major assistants remember your preferences and personal facts. That's useful, but flat. LIA goes further with a structured **psychological and emotional understanding**.

Each memory carries an emotional weight (-10 to +10), an importance score, a usage nuance, and a psychological category. This isn't a simple database — it's a profile that understands what moves you, what motivates you, what hurts you.

Those memories still have to arrive. A memory is only worth what it actually captures, and silence is its worst failure mode: nothing signals a memory that was never formed. So LIA counts each of its memorisation decisions — kept, skipped, disabled — so that the gap between what it should retain and what it does retain is visible rather than assumed. What you entrust to it while asking for an action counts as much as a confidence, what you write from a messenger counts as much as from the browser, and what the system says to itself never counts at all.

### 7.2. The Psyche Engine: a living personality

This is LIA's deepest differentiator. ChatGPT, Gemini, Claude — all have a fixed personality. Every message is an emotional blank slate. LIA is different.

The **Psyche Engine** gives LIA a dynamic psychological state that evolves with every exchange:

- **14 moods** that fluctuate with the conversation's tone (serene, curious, melancholic, playful...)
- **22 emotions** that trigger and fade in response to your words
- **A relationship** that deepens message after message
- **Personality traits** (Big Five) inherited from the chosen personality
- **Motivations** that influence the assistant's proactivity

You're not talking to a tool — you're interacting with an entity whose vocabulary warms up when touched, whose sentences shorten under tension, whose humor emerges when the exchange is light. And it never says so — it **shows** it.

This inner life has a face: the mood emoji animates on the current reply, the colored ring pulses when the mood shifts, and the milestones of your relationship are celebrated with a discreet wink.

And this presence follows you: outside the chat, a floating companion keeps LIA at your side across the whole dashboard — at rest, at work, or carrying a notification.

### 7.3. Personal journals

LIA keeps its own reflections in **stratified personal journals**: self-reflection, observations about the user, ideas, learnings. These notes, written in the first person and colored by the active personality, organically influence future responses.

The journal is organized along **four levels of depth** — from raw observation (a weak signal noted to see if it confirms) up to portrait facet (a stable trait that says something about who you are), through operational directives and transversal patterns. Each entry carries an **epistemic status**: hypothesis in test, observation confirmed, or directive validated by the evidence accumulated over conversations.

Beyond writing, the journal **measures itself**. At every turn, LIA looks at the directives it applied on the previous turn and reads your reaction on the current turn: if you confirmed, the evidence counter rises; if you pushed back, the contradiction counter rises. Over time, false hypotheses get demoted silently, good intuitions get promoted, transversal patterns emerge through active clustering.

From this stratification emerges a **compiled user-model portrait**: your voice, your rhythm, your contexts, your contradictions, your blind spots. It travels with LIA wherever it speaks — conversation, voice, reminders, proactive notifications, ReAct, fallback — so the assistant doesn't "forget who you are" depending on the surface it's using.

This is a form of artificial introspection — the assistant reflecting on its interactions, measuring its own usefulness, and developing a nuanced understanding of you. You retain full control: reading by theme or by level, editing, signaling a problem on the portrait, triggering a consolidation on demand. The portrait itself is never directly edited — it's a synthesis voice, corrected through indirect levers to preserve its coherence.

### 7.4. Emotional safety

When a memory with a strong negative emotional charge is activated, LIA automatically switches to protective mode: never joke, never minimize, never trivialize. The assistant adapts its behavior to the emotional reality of the person — not a one-size-fits-all treatment.

### 7.5. Self-knowledge

LIA has a built-in knowledge base about its own capabilities, allowing it to answer questions about what it can do, how it works, and what its limitations are.

---

## 8. Production reliability

### 8.1. The real challenge of agentic AI

The vast majority of agentic AI projects never reach production. Uncontrolled costs, non-deterministic behavior, missing audit trails, failing agent coordination. LIA has solved these problems — and runs in production 24/7 on a Raspberry Pi. And your data survives incidents: the database is backed up automatically every night, and the restore procedure is not theoretical — it is tested.

A feature nobody can find does not exist. That is why the interface's reachability is treated like server uptime: measured, not assumed. Every header control is compared against the browser viewport, width by width and **in all six languages** — German and Italian carry the longest labels and break first. And what the mobile layout is allowed to drop is written down, with its reason: an action never disappears without a substitute taking its place.

A feature that fails silently does not exist either. A generation cut off just before the end, an import blocked by a directory that became unwritable, a connection that dies announcing nothing: three unrelated causes, one symptom — nothing happens. That is the worst possible signal, because it points at no one. Every defect of that kind is therefore closed with a guard we first made fail on purpose: break what it protects, check that it goes red, and only then keep it.

There is something more insidious than a guard nobody ever made fail: a guard that watches the wrong signal. Three of the interface's headers declared themselves pinned while scrolling, and not one of them was — on every screen, since the very beginning. Nothing had caught it, because no check ever measured a position *during* a scroll: they all observed a page at rest, precisely the state in which the defect does not exist. Fixing the cause was therefore only half the work; the missing measurement had to be added, and the old setting restored afterwards to confirm that it really did go red.

Trickier still than a guard aimed at the wrong signal: a defect that only shows up half the time. The same request failed, then went through thirty minutes later with not one line changed — just enough to conclude "it was transient" and close the case. The cause sat in an invisible detail: tools are chosen against an English rewording produced by a model, regenerated on every turn. A different verb, a reading tool drops out, and the assistant ends up having to reply to a message it cannot read. The temptation was to tune that randomness — one more keyword, a threshold nudged. We preferred a guarantee that never looks at it: before planning, the system checks that everything it requires is actually within reach. When an answer depends on a dice roll, fixing it rarely means improving the dice.

A displayed count is a claim: it is exact, or it does not exist. The dashboard long showed “0 successful actions” — not because nothing succeeded, but because the internal classification compared against a word nobody emitted. And token accounting was right — but by the provider's politeness, not by contract: nothing requested it, nothing tested it, nothing watched it. Both repairs share one shape: the vocabulary is locked on both sides by a contract test, the accounting request is declared per provider and verified at startup, and a paid call completing without a count fires an alert. Exactness is not a state — it is a watch.

### 8.2. A professional observability stack

LIA ships with production-grade observability:

| Tool | Role |
| --- | --- |
| **Prometheus** | System and business metrics |
| **Grafana** | Real-time monitoring dashboards |
| **Tempo** | End-to-end distributed tracing |
| **Loki** | Structured log aggregation |
| **Langfuse** | Specialized LLM call tracing |
| **Alertmanager** | Email alerts on vital signals, linked runbooks |

Every request is traced end-to-end, every LLM call is measured, every error is contextualized. This isn't monitoring bolted on as an afterthought — it's a **foundational architectural decision** documented across the project's Architecture Decision Records.

### 8.3. An anti-hallucination pipeline

The response system features a three-layer anti-hallucination mechanism: data formatting with explicit boundaries, directives enforcing exclusive use of verified data, and explicit edge case handling. The LLM is constrained to synthesize only what comes from actual tool results.

### 8.4. Human-in-the-Loop with 6 levels

LIA doesn't refuse sensitive actions — it **submits** them to you with the appropriate level of detail: plan approval, clarification, draft critique, destructive confirmation, batch operation confirmation, modification review. Each approval feeds the learning system — the system accelerates over time. And the promise is kept to the letter: what you approve — after one, two or ten edits — is **exactly** what gets executed, never a version silently re-generated behind the scenes.

### 8.5. Your answers don't need you

Send a question, close the tab, walk away. Generation continues on the server, and the answer is waiting in the conversation — or resumes live, exactly where it left off, if you come back while it is still being written. Nothing to do, nothing to configure: continuity is the default behavior. And when you are the one changing your mind, a stop button interrupts generation within a second — what was already written stays on screen, honestly marked as interrupted. A reliable assistant isn't just one that answers correctly: it's one that finishes what it starts.

### 8.6. Nothing runs behind your back

An assistant that can act is an assistant that can act *wrongly*. Two rules make that acceptable.

First, **nothing touches your server without you saying yes** — and the confirmation shows everything that will be sent, including the instructions LIA wrote for itself. A summary you cannot fully read is not a confirmation, it is a formality. The permission is checked again the moment the action starts, not only when you asked for it.

Second, **what does run, runs in a sealed box**. A skill's code executes in a container created for that single run and destroyed straight after: no network, no access to your files, no keys, no way to reach the machine underneath. If that box cannot be built, the script simply does not run — no silent fallback to a weaker mode. You install a skill for what it produces, not for the trust you must extend to its author.

---

The same demand applies to what LIA **asserts**. An answer must rest on data actually retrieved, never on the memory of an earlier phrasing; and when a piece of information was never obtained, calling it missing beats reconstructing something plausible. This is a design constraint rather than a matter of style: recently retrieved entities are explicitly re-injected into the response context, and inventing an entity attribute is forbidden at the prompt level. A plausible factual error costs more than an "I don't know".

Visual consistency answers to the same standard. An action has the same shape everywhere or nowhere; a colour code the pointer must reveal is not a code, it is a secret; grey is reserved for what is inactive — a live state carries its colour. These rules are not tastes: each one is written down, tooled and guarded by a test, because the effort of reading belongs to the system, not to the person using it.

## 9. Radical openness

### 9.1. Zero lock-in

ChatGPT ties you to OpenAI. Gemini to Google. Copilot to Microsoft.

LIA connects you to **7 AI providers simultaneously**: OpenAI, Anthropic, Google, DeepSeek, Perplexity, Qwen, and Ollama (local models). You can mix: OpenAI for planning, Anthropic for response, DeepSeek for background tasks — all configurable from the admin interface, in one click.

If a provider changes its pricing or degrades its service, you switch instantly. No dependency, no trap.

### 9.2. Open standards

| Standard | Usage in LIA |
| --- | --- |
| **MCP** (Model Context Protocol) | Per-user external tool connections |
| **agentskills.io** | Injectable skills with progressive disclosure |
| **Agent Plugins** (open standard) | Portable plugins bundling skills + MCP servers, one-step install |
| **OAuth 2.1 + PKCE** | Authentication for all connectors |
| **OpenTelemetry** | Standardized observability |
| **AGPL-3.0** | Complete, auditable, modifiable source code |

### 9.3. Extensibility

Each user can connect their own MCP servers, extending LIA's capabilities far beyond built-in tools. The client speaks both generations of the protocol — the new stateless revision and the legacy handshake, chosen automatically per server — so openness never costs compatibility. Skills (agentskills.io standard) allow injecting expert instructions in natural language — with a built-in Skill generator that creates them through a guided dialogue and installs them directly into your skills, ready to use. Since v1.16.8, a Skill can also return an **interactive HTML frame** (map, dashboard, calendar, converter...) or an **image** (QR code, chart) right inside the chat, sandboxed under a strict CSP, with theme and locale automatically kept in sync.

Since v1.30.8, this openness has a package format: LIA speaks the **Agent Plugins** open standard (agent-plugins.org), the portable plugin format steered by AWS, Microsoft, OpenAI, Cursor and Vercel and adopted by ChatGPT, Codex, Cursor, GitHub Copilot, Kiro and VS Code. A plugin bundling skills and MCP servers installs into LIA in one step — from a zip or an https link — with a full per-component report of what was installed, skipped (and why) or removed, and uninstalls just as cleanly, everything it brought leaving with it. Interoperability is a conviction here, not a feature: what you build or adopt anywhere in the ecosystem is yours to bring.


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

How LIA is built — an AI writing the code, a human directing, reviewing and auditing — is told in detail in our [field report](/en/story).

**Your Life. Your AI. Your Rules.**
