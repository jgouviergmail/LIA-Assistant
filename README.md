<p align="center">
  <img src="docs/assets/logo.png" alt="LIA — Your life. Your AI. Your rules." width="600" />
</p>

<h1 align="center">LIA</h1>

<p align="center">
  <strong>Your day. LIA keeps up. You decide.</strong><br />
  A personal assistant that brings your context together, helps you follow through, and prepares actions for review.<br />
  <strong>Designed in France · Open source · Self-hostable · Six-language interface</strong>
</p>

<p align="center">
  <strong>Prepare a conversation. Listen to your day. Keep track of your commitments.</strong>
</p>

<p align="center">
  <a href="https://lia.jeyswork.com/"><img src="https://img.shields.io/badge/🚀_Explore_LIA-lia.jeyswork.com-0EA5E9?style=for-the-badge" alt="Explore LIA"></a>
  &nbsp;&nbsp;
  <a href="https://github.com/jgouviergmail/LIA-Assistant/stargazers"><img src="https://img.shields.io/github/stars/jgouviergmail/LIA-Assistant?style=for-the-badge&logo=github&label=Star&color=gold" alt="GitHub Stars"></a>
</p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.14-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.14"></a>
  <a href="https://nodejs.org/"><img src="https://img.shields.io/badge/Node.js-24%20LTS-5FA04E?style=flat-square&logo=nodedotjs&logoColor=white" alt="Node.js 24 LTS"></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-0.141.1-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI"></a>
  <a href="https://nextjs.org/"><img src="https://img.shields.io/badge/Next.js-16-000000?style=flat-square&logo=nextdotjs&logoColor=white" alt="Next.js 16"></a>
  <a href="https://langchain-ai.github.io/langgraph/"><img src="https://img.shields.io/badge/LangGraph-1.2.14-FF6F00?style=flat-square" alt="LangGraph"></a>
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
  <strong>Version 3.2.0</strong> — <strong>A FAQ for every feature, voices that react.</strong> Ten new FAQ sections bring it to 491 questions in six languages, the radio's voices chuckle, laugh or sigh where a programme converses, the tools a switched-off capability names leave both execution modes, and <code>./install.sh --reconfigure</code> changes a running installation without reinstalling it — 18 October 2026.
</p>

---

## Table of Contents

- [What is LIA?](#what-is-lia)
- [Try LIA Online](#try-lia-online)
- [Product presentation](#product-presentation)
- [Screenshots](#screenshots)
- [Features](#features)
- [Administration & Monitoring](#administration--monitoring)
- [Built by an AI, Directed by a Human](#built-by-an-ai-directed-by-a-human)
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

LIA is an open-source personal AI assistant in a web application you can host yourself. It connects the information you make available — emails, calendar, documents, preferences and commitments — to help you prepare conversations, organize your day and follow through.

Its strength is the continuity between those activities. Memory, knowledge spaces, meeting records and **Relations**, its personal relationship view, make relevant context available for the next supported request. A preference you correct, a document you keep or a commitment you record can become useful again. Each feature contributes through its own sources, permissions and settings.

LIA also helps between conversations: a daily briefing, a personal **Radio**, reminders, routines and proactive suggestions. You choose the sources and enabled features, and the time windows and channels for proactive help. Chat, rich cards, voice and Live sessions keep this assistance accessible in the same application.

You can inspect sources, correct remembered information and review prepared drafts. Actions covered by approval flows ask for your decision before execution. Registers expose recorded consultations, action attempts and outcomes; usage and budgets are visible to users and operators.

### Start with something that would help you

| Your situation                | Ask LIA, or use its dedicated view                                                                                                                                                                          |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A discussion to prepare**   | “Prepare my catch-up with Claire using the project brief, our recent emails and the last meeting notes. Highlight anything that conflicts.”                                                                 |
| **A promise to follow up**    | Open **Relations** to review recent exchanges, the debrief and open commitments before contacting someone.                                                                                                  |
| **A message to get right**    | “Draft an email to the supplier asking which delivery date they can commit to. Show me the draft before sending it.”                                                                                        |
| **A meeting to keep useful**  | Record it, review and correct the minutes, then export a PDF. Successfully indexed minutes can be retrieved in a later conversation.                                                                        |
| **A day to listen to**        | Choose personal and news sources in **Radio**, then listen with the programme, transcript and articles beside you.                                                                                          |
| **People to coordinate with** | “Find a time for dinner with Sam tomorrow evening using the availability shared with me. Show the invitation before sending it.” This uses an accepted connection and its permissions on the same instance. |

These examples use the services and permissions enabled on your instance. Generated conclusions and documents remain yours to review.

### What LIA brings together

| What matters in daily use                  | What LIA provides                                                                                                                                                               |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Relevant context, ready to reuse**       | Memory, knowledge, meeting records, saved answers and Relations support relevant requests from their authorized sources. You can inspect and correct what is kept.              |
| **Help when you ask and between requests** | Conversation, daily briefing and personal Radio, alongside reminders, scheduled work, conditional routines and proactive suggestions with their own source and timing controls. |
| **A clear next step**                      | Rich results, reviewable drafts, downloadable documents and compatible skills or MCP apps present information and controls in the appropriate form.                             |
| **A choice of how to work**                | Pipeline builds and validates a plan before execution; ReAct explores iteratively from tool results. Chat and Live voice use documented provider and mode capabilities.         |
| **One installation for several people**    | Separate accounts have their own connectors, memory and preferences. Accepted connections choose what to share and can exchange messages through their assistants.              |
| **A system you can inspect and operate**   | Open code, a documented architecture, registers, model configuration, account and instance budgets, administration, Grafana dashboards and alert rules.                         |

Cloud models and compatible local models served through native Ollama can be configured for supported processing roles. Model capabilities, host resources and enabled external services determine the available features and where information is processed. Hosting and provider services may incur costs.

### A foundation for an internal company assistant

Preparing meetings, retrieving business knowledge and following commitments can also help colleagues. LIA's multi-user web application, connectors, MCP, APIs and observability provide a foundation to customize and integrate into your organization.

Define the deployment's identity, permissions, business sources, usage rules, integrations and hosting. The [architecture](#architecture), [documentation](#documentation) and [self-hosting guide](docs/guides/GUIDE_DEPLOYMENT.md) help scope that work.

---

## Try LIA Online

[Explore LIA and its real interface](https://lia.jeyswork.com/) or try the [public demonstration](https://lia.jeyswork.com/demo).

The public demonstration uses fictional scenarios. When the guided showroom is enabled, it illustrates requests, context, results and approval controls using the application's rendering components, without contacting a real model, account or external service. Source links let you inspect the mechanisms behind that showroom; a live demonstrator is offered when the instance publishes one.

> **Closed beta** — account access and activation are granted at the administrator's discretion. To request an invitation, write to **liamyassistant@gmail.com**.

To run your own LIA, start with [Quick Start](#quick-start) or the [production installation guide](docs/GETTING_STARTED.md).

---

## Product presentation

[![Watch the complete LIA product presentation](docs/assets/lia-presentation.png)](https://github.com/jgouviergmail/LIA-Assistant/releases/download/v3.0.0/lia-presentation-v3.0.0.mp4)

[Watch or download the complete film](https://github.com/jgouviergmail/LIA-Assistant/releases/download/v3.0.0/lia-presentation-v3.0.0.mp4).
The French presentation follows concrete uses, contextual native avatars,
display modes, reminders, Relations, planned actions, administration and the
installable mobile web application. Interfaces follow the product's UI with
fictional demonstration data. The landing's blue **Presentation** button opens
the full film with sound and controls in an exclusive fullscreen player.

The [editable construction](tools/lia-motion/README.md),
[production and update procedure](docs/technical/MOTION_DESIGN.md) and
[decision record](docs/architecture/ADR-341-Editable-Motion-Production-And-Exclusive-Presentation.md)
preserve the scenario, native-view sources, feature focuses and soundtrack
provenance for future product updates. Release assets include a
[checked editable source archive](https://github.com/jgouviergmail/LIA-Assistant/releases/download/v3.0.0/lia-motion-sources-v3.0.0.zip).
The video is a product demonstration, not a recorded provider session.

## Screenshots

Explore the real application interface in English and light mode, filled with fictional demonstration data. The geographic maps and walking route use [real Google Maps imagery and geographic data](apps/web/e2e/fixtures/maps/provenance.json), prepared separately and served locally with attribution. The browser captures exercise the actual pages, controls and widgets without model inference, provider calls, connected accounts or external actions. Radio uses a local silent audio fixture. The interactive budget is a custom skill example produced by an executed [Python fixture generator](apps/web/e2e/capture/render_trip_budget.py); its estimates are illustrative and no booking is made.

Open any image at full resolution. The [home capture manifest](apps/web/public/screenshots/manifest.json), [workflow manifest](apps/web/public/screenshots/proof/manifest.json) and [extended application manifest](apps/web/public/screenshots/proof/extended-manifest.json) record the images and their provenance. Reproduce the campaigns with the [public capture workflow](apps/web/e2e/README.md#public-screenshots), [workflow runner](apps/web/e2e/capture/run-landing-proof.mjs) and [extended capture runner](apps/web/e2e/capture/run-extended-screenshots.mjs).

<p align="center">
  <a href="docs/assets/screenshot-homepage.png"><img src="docs/assets/screenshot-homepage.png" alt="Personal home dashboard — daily briefing, agenda, mail, tasks and reminders" width="1000" /></a>
  <br /><em>Your personal hub — the day’s priorities, appointments and useful context in one place.</em>
</p>

<p align="center">
  <a href="apps/web/public/screenshots/proof/dossier.png"><img src="apps/web/public/screenshots/proof/dossier.png" alt="Chat — project sources, conflicting dates and practical next steps" width="1000" /></a>
  <br /><em>Prepare a decision with the relevant documents, emails and meeting notes in view.</em>
</p>

<p align="center">
  <a href="apps/web/public/screenshots/proof/relations.png"><img src="apps/web/public/screenshots/proof/relations.png" alt="Relations — person overview, debrief, open commitments and recent exchanges" width="1000" /></a>
  <br /><em>Pick up a conversation with useful context and commitments beside you.</em>
</p>

<p align="center">
  <a href="apps/web/public/screenshots/proof/radio.png"><img src="apps/web/public/screenshots/proof/radio.png" alt="Personal Radio — programme, transcript, upcoming segments and source articles" width="1000" /></a>
  <br /><em>Follow a personal programme with its transcript and inspectable sources.</em>
</p>

<details>
<summary><strong>Places, maps and routes in rich conversations</strong></summary>

<p align="center">
  <a href="apps/web/public/screenshots/proof/places.png"><img src="apps/web/public/screenshots/proof/places.png" alt="Google Places — complete place card with opening hours and practical details" width="1000" /></a>
  <br /><em>Inspect a complete place card with opening hours, rating, price range, address and accessibility details.</em>
</p>

<p align="center">
  <a href="apps/web/public/screenshots/proof/maps.png"><img src="apps/web/public/screenshots/proof/maps.png" alt="Google Maps — location card with geographic map, coordinates and address" width="1000" /></a>
  <br /><em>Inspect a location with its geographic map, coordinates and address in the conversation.</em>
</p>

<p align="center">
  <a href="apps/web/public/screenshots/proof/routes.png"><img src="apps/web/public/screenshots/proof/routes.png" alt="Walking route — geographic map, distance and travel time" width="1000" /></a>
  <br /><em>Read a walking itinerary with its map, distance and travel time in view.</em>
</p>

</details>

<details>
<summary><strong>Memory, avatars, personal portrait and emotional context</strong></summary>

<p align="center">
  <a href="apps/web/public/screenshots/proof/memory-library.png"><img src="apps/web/public/screenshots/proof/memory-library.png" alt="Memory library — remembered facts, preferences, categories and management controls" width="1000" /></a>
  <br /><em>Find what LIA remembers and manage the facts and preferences you keep.</em>
</p>

<p align="center">
  <a href="apps/web/public/screenshots/proof/memory.png"><img src="apps/web/public/screenshots/proof/memory.png" alt="Memory — editing a stored preference" width="1000" /></a>
  <br /><em>Correct a remembered preference through the actual edit form.</em>
</p>

<p align="center">
  <a href="apps/web/public/screenshots/proof/portrait.png"><img src="apps/web/public/screenshots/proof/portrait.png" alt="Personal portrait — accumulated context and profile sections" width="1000" /></a>
  <br /><em>Review the portrait that brings your personal context together.</em>
</p>

<p align="center">
  <a href="apps/web/public/screenshots/proof/avatar-picker.png"><img src="apps/web/public/screenshots/proof/avatar-picker.png" alt="Avatar picker — companion previews and appearance selection gallery" width="1000" /></a>
  <br /><em>Preview the companion styles and choose LIA’s appearance in the actual avatar gallery.</em>
</p>

<p align="center">
  <a href="apps/web/public/screenshots/proof/psyche.png"><img src="apps/web/public/screenshots/proof/psyche.png" alt="Psyche Engine — personality traits, emotional state and responsiveness" width="1000" /></a>
  <br /><em>Inspect the personality and emotional settings that shape LIA’s responses.</em>
</p>

<p align="center">
  <a href="apps/web/public/screenshots/proof/psyche-evolution.png"><img src="apps/web/public/screenshots/proof/psyche-evolution.png" alt="Emotional evolution — state timeline and associated events" width="1000" /></a>
  <br /><em>Follow emotional state changes and the events associated with them.</em>
</p>

<p align="center">
  <a href="apps/web/public/screenshots/proof/journal.png"><img src="apps/web/public/screenshots/proof/journal.png" alt="Personal journal — saved reflections and their context" width="1000" /></a>
  <br /><em>Revisit the reflections and context kept in your personal journal.</em>
</p>

</details>

<details>
<summary><strong>Routines, schedules and project work</strong></summary>

<p align="center">
  <a href="apps/web/public/screenshots/proof/routine-studio.png"><img src="apps/web/public/screenshots/proof/routine-studio.png" alt="Routine studio — workflow instructions, recurrence and execution settings" width="1000" /></a>
  <br /><em>Prepare a recurring workflow with its instructions, timing and execution settings.</em>
</p>

<p align="center">
  <a href="apps/web/public/screenshots/proof/routine-week.png"><img src="apps/web/public/screenshots/proof/routine-week.png" alt="Routine calendar — scheduled workflows across the week" width="1000" /></a>
  <br /><em>See the week’s routines and their upcoming runs together.</em>
</p>

<p align="center">
  <a href="apps/web/public/screenshots/proof/workboard.png"><img src="apps/web/public/screenshots/proof/workboard.png" alt="Workboard — projects and work organized by stage" width="1000" /></a>
  <br /><em>Follow projects and tasks across their working stages.</em>
</p>

<p align="center">
  <a href="apps/web/public/screenshots/proof/workboard-dossier.png"><img src="apps/web/public/screenshots/proof/workboard-dossier.png" alt="Project dossier — tasks, working context and follow-ups" width="1000" /></a>
  <br /><em>Keep a project’s tasks, context and next steps together.</em>
</p>

</details>

<details>
<summary><strong>Knowledge spaces, meetings and reusable reports</strong></summary>

<p align="center">
  <a href="apps/web/public/screenshots/proof/knowledge-library.png"><img src="apps/web/public/screenshots/proof/knowledge-library.png" alt="Knowledge library — spaces and indexed document collections" width="1000" /></a>
  <br /><em>Find the knowledge spaces that hold your documents and reference material.</em>
</p>

<p align="center">
  <a href="apps/web/public/screenshots/proof/knowledge.png"><img src="apps/web/public/screenshots/proof/knowledge.png" alt="Knowledge space — documents, Drive folders and mail sources" width="1000" /></a>
  <br /><em>Inspect indexed documents and manage the sources attached to a space.</em>
</p>

<p align="center">
  <a href="apps/web/public/screenshots/proof/meetings-list.png"><img src="apps/web/public/screenshots/proof/meetings-list.png" alt="Meetings list — recordings and reports with their processing states" width="1000" /></a>
  <br /><em>Find your meetings and follow the processing state of each recording or report.</em>
</p>

<p align="center">
  <a href="apps/web/public/screenshots/proof/meetings.png"><img src="apps/web/public/screenshots/proof/meetings.png" alt="Detailed meeting report — participants, summary, decisions and assigned action items" width="1000" /></a>
  <br /><em>Inspect the detailed meeting report: participants, summary, decisions and assigned actions, with editing and export controls.</em>
</p>

<p align="center">
  <a href="apps/web/public/screenshots/proof/meeting-transcript.png"><img src="apps/web/public/screenshots/proof/meeting-transcript.png" alt="Meeting transcript — recorded conversation and report controls" width="1000" /></a>
  <br /><em>Read the conversation behind the meeting report.</em>
</p>

<p align="center">
  <a href="apps/web/public/screenshots/proof/meeting-templates.png"><img src="apps/web/public/screenshots/proof/meeting-templates.png" alt="Meeting templates — available report structures and formats" width="1000" /></a>
  <br /><em>Choose the structure used to turn a recording into a useful report.</em>
</p>

</details>

<details>
<summary><strong>Actions to approve, connected services and interactive skills</strong></summary>

<p align="center">
  <a href="apps/web/public/screenshots/proof/approval.png"><img src="apps/web/public/screenshots/proof/approval.png" alt="Approval — prepared message and confirm, modify and cancel controls" width="1000" /></a>
  <br /><em>Review a prepared action through the application’s approval controls.</em>
</p>

<p align="center">
  <a href="apps/web/public/screenshots/proof/connections.png"><img src="apps/web/public/screenshots/proof/connections.png" alt="Connections — linked services and access management" width="1000" /></a>
  <br /><em>Manage connected services and inspect the access available to LIA.</em>
</p>

<p align="center">
  <a href="apps/web/public/screenshots/proof/skills-library.png"><img src="apps/web/public/screenshots/proof/skills-library.png" alt="Skills library — available skills and activation controls" width="1000" /></a>
  <br /><em>Browse the skills you can use and manage their activation.</em>
</p>

<p align="center">
  <a href="apps/web/public/screenshots/proof/skill.png"><img src="apps/web/public/screenshots/proof/skill.png" alt="Weekend Budget Studio — interactive custom skill with a category breakdown and editable trip controls" width="1000" /></a>
  <br /><em>A custom skill example inside the conversation — adjust travellers, nights and budget to explore an illustrative spending breakdown.</em>
</p>

</details>

<details>
<summary><strong>Models, consumption and account budgets</strong></summary>

<p align="center">
  <a href="apps/web/public/screenshots/proof/model-routing.png"><img src="apps/web/public/screenshots/proof/model-routing.png" alt="Model routing — provider and model selection for each operation" width="1000" /></a>
  <br /><em>Choose the providers and models used by each operation.</em>
</p>

<p align="center">
  <a href="apps/web/public/screenshots/proof/consumption.png"><img src="apps/web/public/screenshots/proof/consumption.png" alt="Consumption — usage figures, costs and operation details" width="1000" /></a>
  <br /><em>Inspect usage and costs with the operations that produced them.</em>
</p>

<p align="center">
  <a href="apps/web/public/screenshots/proof/administration.png"><img src="apps/web/public/screenshots/proof/administration.png" alt="Administration — account quotas and instance spending ceiling" width="1000" /></a>
  <br /><em>Set account limits and the instance ceiling with visible usage gauges.</em>
</p>

</details>

The [Administration & Monitoring](#administration--monitoring) section below includes the three Grafana views supplied by the project.

---

## Features

Every capability below is documented in an architecture decision record (ADR) or a technical document — the links lead there.

| Explore                                            | What you'll find                                                       |
| -------------------------------------------------- | ---------------------------------------------------------------------- |
| [Talk to it](#talk-to-it)                          | Chat, voice, live sessions, radio and a companion that feels present   |
| [Connect your world](#connect-your-world)          | Your accounts, documents, home, health, tools and skills               |
| [Act, under your control](#act-under-your-control) | Orchestration, approvals, calls, creation, browser work and tickets    |
| [Anticipate](#anticipate)                          | Timely suggestions, routines, reminders and a daily briefing           |
| [Remember](#remember)                              | Memory, journals, knowledge, meetings, people and saved work           |
| [Trust it](#trust-it)                              | Records, spending limits, authentication, data protection and controls |

### Talk to it

#### A chat that streams

- Answers arrive over SSE with rich HTML cards, interactive widgets and a per-message cost badge.
- A data card shows everything the source supplied and never invents a missing value — an e-mail's body, every organisation of a contact, conference join points, subtasks, a place's photos (full-screen gallery), reviews and opening hours, a route's alternatives, weather slots, generated-document previews — the detail behind native disclosures; opening one calls nothing. The model reads a versioned semantic view of the answer, never the card's HTML ([ADR-332](docs/architecture/ADR-332-Deterministic-Cards-Received-Facts-And-Message-Owned-Actions.md), [HTML_CARDS](docs/technical/HTML_CARDS.md)).
- Reply, forward, move an e-mail to the trash or adjust a reminder from its card: the request is prepared in the composer, and the server re-checks the original message, source and account grant. E-mail deletion still passes through approval before changing its original mailbox. A route opens as an interactive Google map whose estimated cost is announced first and every construction counted ([ADR-332](docs/architecture/ADR-332-Deterministic-Cards-Received-Facts-And-Message-Owned-Actions.md)).
- MCP cards name the server's public origin and the called method above an accessible response disclosure; opening it reveals the received result without another call. Weather icons follow the provider's condition codes and day/night information, across current, daily and hourly forecasts.
- In the rich HTML mode every data-bearing answer is a composed page — a lead sentence, one section per facet in the component that fits it, a closing callout — laid out on conversational turns too unless a voice is reading them ([ADR-177](docs/architecture/ADR-177-Rich-HTML-Response-Components.md)).
- Images and PDFs can be attached (vision analysis, text extraction, strict per-user isolation).
- Long conversations are compacted by an LLM summary that preserves identifiers, the history scrolls back page by page without limit, and each answer is shared — to the device's sheet, or to a connection through an ordinary confirmed message — or downloaded as a dated Markdown file in one click. A formatted answer keeps its headings, lists, tables, links and code in that file, its cards summed up as a heading and a few bullets; copying stays plain text ([ADR-177](docs/architecture/ADR-177-Rich-HTML-Response-Components.md)).
- The text size is a per-account preference from 14 to 20 px: only the text scales, panels, spacing and icons keep their dimensions.

#### One conversation across devices and channels

- Once a message is committed, the open chat learns of it and merges the new history without replacing older pages, moving the reader or interrupting an action. Other tabs, calls, routines and external channels become visible without a reload.
- A reconnected tab catches up after an interruption ([ADR-320](docs/architecture/ADR-320-The-Chat-Follows-The-Server-Without-A-Reload.md)).

#### Voice, both ways

- Push-to-talk, or the wake word "Dis LIA" — a small trained model run by ONNX Runtime in a browser worker, every file checked against its SHA-256, so no audio leaves the device for detection. "Stop" cuts LIA's voice while it reads an answer. French only for now, in beta; the other interface languages keep tap-to-speak ([ADR-329](docs/architecture/ADR-329-Live-Standby-And-Multilingual-Wake-Word.md), [WAKE_WORD_TRAINING](docs/technical/WAKE_WORD_TRAINING.md)).
- Offline Whisper transcription in the user's own language, or the remote engine the administrator configured (ElevenLabs Scribe, OpenAI or Fish Audio), named before anyone opts in.
- Spoken answers from a catalogue-driven TTS (Edge, free; OpenAI; ElevenLabs; Gemini; Fish Audio), streamed sentence by sentence. Playback can begin before the complete answer is available; startup latency depends on the model, provider and connection ([VOICE](docs/technical/VOICE.md), [ADR-081](docs/architecture/ADR-081-Voice-TTS-Catalogue-Driven.md), [ADR-082](docs/architecture/ADR-082-Progressive-Sentence-Streaming.md)).
- Every heard sentence is billed once, by the engine that spoke it; ElevenLabs synthesis and every Fish Audio request share an administrator-set allowance per vendor account across API workers and speech surfaces; the browser plays queued audio in sequence, even when synthesis completes out of order.
- On the engines that perform them, LIA's spoken comments carry a few expressive cues (a sigh, a laugh, a whisper) in each engine's own syntax, while text it reads aloud never turns a bracket into a cue. Each cue is chosen from what it means: it colours the news, never how LIA's own act went — a confirmation, a failure or a search that found nothing is said plainly. Administrators manage the instance's Fish Audio voices: clone one under a consent attestation filed in the audit log, design one from a description, rename or delete ([ADR-345](docs/architecture/ADR-345-Fish-Audio-Served-Whole-One-Door-One-Allowance-Cues-Each-Engine-Reads.md)).
- Each person picks LIA's male and female voice among the voices of the engine that speaks in the chat, kept per provider so a change of model keeps them; every voice picker — LIA's, the radio's, the administrator's slots — can be narrowed to the person's language and the multilingual voices, never hiding a voice already chosen ([ADR-345](docs/architecture/ADR-345-Fish-Audio-Served-Whole-One-Door-One-Allowance-Cues-Each-Engine-Reads.md)).

#### A personal speaking avatar, experimental

- Connect your own Simli account, choose a face and explicitly authorize its use. The operator must first enable the optional capability; it is off by default.
- A floating window with three sizes follows existing voice comments and Live conversations, with touch/pointer dragging and keyboard movement. The avatar and local player share one audible destination.
- The window keeps its explicit stop control even when the chat encounters an error, and reports confirmed or pending closure. Mobile keyboard, rotation and zoom adjustments preserve the chosen placement.
- The connection stays open while the voice mode is active; silence can consume your personal Simli credits. Live standby closes it, and waking opens a new connection. Radio is outside this integration.
- Provider lip motion, long silence, renewal and physical Android/iOS audio remain subject to qualification ([SPEAKING_AVATAR](docs/technical/SPEAKING_AVATAR.md), [proposed ADR-334](docs/architecture/ADR-334-Personal-Speaking-Avatar-And-One-Audible-Output.md)).

#### Live, voice to voice

- A real-time session on a live model the person connects with their own key (Gemini Live over a WebSocket, GPT-Live over WebRTC, or an ElevenLabs agent whose voice stays on its portal).
- The Live provider connection carries audio directly between the browser and provider. With the optional avatar enabled, LIA's spoken output also passes through the API-controlled Simli relay; its provider token stays encrypted server-side.
- In supported Live configurations, the voice model can delegate a data request or action to the chat engine. The delegated turn uses the graph’s approvals, registers and quotas and appears in the thread. Concurrent speech, interruption and delegation behavior depend on the provider, model and mode.
- A provider declares its wire and the seam never branches on its name.
- A direct session holds the read-only tools itself and acts on nothing.
- A silence puts the session on standby instead of ending it: the provider connection closes and nothing is billed until the phrase or a tap wakes it into a new connection; only the person ends a session ([ADR-329](docs/architecture/ADR-329-Live-Standby-And-Multilingual-Wake-Word.md)).
- The provider's own usage is folded into an indicative meter and shown, never recorded — the vendor's bill read once at the end where it has one ([ADR-299](docs/architecture/ADR-299-Live-Voice-Mode-Two-Intelligences-One-Seam.md), [ADR-300](docs/architecture/ADR-300-A-Second-Live-Provider-One-Seam-Two-Wires.md), [LIVE_MODE](docs/technical/LIVE_MODE.md)).

#### A personal radio, on demand

- A deterministic programme grid blends the listener's day with news from identified sources, over the station's own instrumental music, lowered under every voice.
- Models write and voice the segments, while verification decides what may air. The listener chooses subjects, sources, voices and verification, sees sources and live cost, and ends the session with a timer. Production runs only while someone listens.
- An administrator controls the capability and the guided self-host installer asks before enabling it ([ADR-324](docs/architecture/ADR-324-A-Personal-Radio-A-Grid-Decides-Models-Only-Write.md), [RADIO](docs/technical/RADIO.md)).
- The radio settings group programme, sources, verification, voices and spending so a listener can see what will be used before starting.
- Debates and discussions are voiced in takes on the engines that voice several speakers — never more voices per take than the engine accepts —, each commentator with the voice the listener chose, never one shared with LIA, the anchor or another commentator. Where a programme converses, a chuckle, a laugh or a sigh may open a turn; the news is never read with one. The second-model verification is off unless the listener chooses it, because every check is billed ([ADR-324](docs/architecture/ADR-324-A-Personal-Radio-A-Grid-Decides-Models-Only-Write.md)).
- Editorial selection excludes advertisements, sponsorships and purchase pitches while retaining genuine news, scientific reporting, invoices, reservations and appointments. Raw PCM and µ-law speech are wrapped with their actual format before mixing.

#### An expressive companion

The complete native catalogue uses original designs and contextual expressions.
Reviewed offline artwork supplies bounded body relief, while the shared rig
owns head pose, eyes, brows and mouth. Reduced motion and unavailable graphics
retain their native fallback. See the [volume guide](docs/technical/NATIVE_AVATAR_VOLUME.md)
for projection and performance limits.

- Psyche temperament, actual tool execution and the delivered answer's tone share one animation rig, including the shaded Smiley. Eyes lead a head with depth and weight.
- Continuous mouth/brow contours, quiet thought and varied resting scenes keep transitions natural. Speech follows actual audio, and a prepared draft never earns an accomplished-action gesture. Fresh cached weather and the account clock add discreet ambience without a provider or LLM call.
- You place the companion — a drag, the arrow keys, or a fold into its restore dot — and on a phone nothing else moves it.
- Reduced motion keeps static contextual poses ([ADR-240](docs/architecture/ADR-240-expressive-eyes-widget.md), [ADR-252](docs/architecture/ADR-252-Expressive-Eyes-Animation-Rig.md), [ADR-253](docs/architecture/ADR-253-Per-Turn-Expressivity-Annotation.md), [ADR-264](docs/architecture/ADR-264-Living-Brows-And-Mouth.md), [ADR-294](docs/architecture/ADR-294-A-Face-That-Never-Plays-The-Same-Twice.md)).

#### A psyche of its own

- Big Five traits, a mood space, discrete emotions, a relationship stage and curiosity drives shape word choice and rhythm without ever being announced.
- Settings › LIA's psyche draws it — emotion rings around the mood, a pleasure × arousal plane, the Big Five pentagon, relationship and drive meters, an evolution chart on a true time axis — beside the temperament sliders and two reset scopes ([PSYCHE_ENGINE](docs/technical/PSYCHE_ENGINE.md)).
- An experience per domain learned from evidence, never from its own grade: what an answer verifiably established and the usefulness you expressed (👍/👎) are kept apart, and an index needs several recent observations. Where evidence is thin, LIA checks a point, asks one question or names its limit — a pilot, no gain claimed before a held-out comparison ([ADR-348](docs/architecture/ADR-348-Efficacy-Learned-From-Evidence-Results-And-Usefulness-Kept-Apart.md)).

#### Wherever you are

- Six languages end to end (UI, approvals, notifications, Telegram, skills).
- A bidirectional Telegram channel with OTP linking and localized approval keyboards ([GUIDE_TELEGRAM](docs/guides/GUIDE_TELEGRAM_INTEGRATION.md)).
- Native Android and iOS shells that load _your_ server, with native push and the sign-in flow Google permits ([ADR-246](docs/architecture/ADR-246-Native-Push-And-Wake-Relay.md), [GUIDE_MOBILE_ANDROID](docs/guides/GUIDE_MOBILE_ANDROID.md), [GUIDE_MOBILE_IOS](docs/guides/GUIDE_MOBILE_IOS.md)).
- An offline-capable PWA ([ADR-146](docs/architecture/ADR-146-Offline-PWA.md)).

### Connect your world

#### Mail, calendar, contacts, tasks

- Google (OAuth 2.1 + PKCE), Apple iCloud (IMAP/SMTP, CalDAV, CardDAV) and Microsoft 365 (Graph API, personal and business tenants).
- One active provider per category; activating one deactivates its competitor.
- Google and Microsoft each offer one consent to connect or reconnect several services on the same verified account, and the connection alert offers it as soon as two services of one provider have expired. Each service can still be disconnected separately ([ADR-302](docs/architecture/ADR-302-OAuth-Grant-Par-Compte-Et-Consentement-Groupe.md), [OAUTH](docs/technical/OAUTH.md)).

#### E-mail, read whole and clean

- The three providers speak one vocabulary at the client boundary: a text body, never HTML, with quoted history and signature removed, measured on real payloads.
- The assistant chooses how much to read from the question: headers to list, a body paginated by paragraph to read, or a digest per message to reason over many. A small model computes each digest once; it is cached thirty days and counted in your usage. If digest generation fails or is truncated, the original body remains available ([ADR-287](docs/architecture/ADR-287-Email-Content-First-Detail-Levels-Digests-And-Neutral-Message.md), [EMAIL_FORMATTER](docs/technical/EMAIL_FORMATTER.md)).
- An attachment is read too — its text when it has one, the vision slot for a picture or a scan — bounded, paginated and treated as what a stranger sent ([ADR-296](docs/architecture/ADR-296-Mail-Attachments-Read-By-Text-Or-Vision.md)).
- Your mailbox drafts — Gmail, Outlook, iCloud — are saved, listed, edited and trashed from the conversation without a confirmation, since nothing reaches anyone; sending one asks once, on a card that shows the draft as the mailbox holds it, and a draft edited elsewhere since is not sent ([ADR-344](docs/architecture/ADR-344-Mailbox-Drafts-Kept-Freely-Sent-After-One-Confirmation.md)).

#### Connected from the first day

- The connectors that ask nothing of the person (Wikipedia, page browsing, Google Places, Weather and Environment) belong to the instance: no per-account row and no entry in « My connectors », always on unless the administrator switches one off for everyone or the instance has no platform key.
- For the weather, a person's own OpenWeatherMap key takes precedence over the instance's default ([ADR-307](docs/architecture/ADR-307-Keyless-Connectors-Belong-To-The-Instance.md), [CONNECTORS_PATTERNS](docs/technical/CONNECTORS_PATTERNS.md)).

#### Documents, places and weather

- Google Drive folders, sub-folders included, and a Gmail label as knowledge sources, synced incrementally, with the exact number of files stated before a large sync starts ([ADR-262](docs/architecture/ADR-262-Opt-In-Mail-Label-RAG-Source.md), [ADR-297](docs/architecture/ADR-297-Drive-Folder-Is-A-Tree-And-The-Count-Is-Exact.md)).
- Google Maps places, routes and geocoding.
- Weather with change detection.
- A last-known-position cascade so every feature knows where you are, with the age of the fix stated ([ADR-219](docs/architecture/ADR-219-Derniere-Position-Connue-Generalisee.md)).

#### Home and body

- Philips Hue lighting by voice (rooms, scenes, local bridge or cloud).
- Daily steps and heart-rate batches pushed from an iPhone Shortcut, idempotently, with baselines, variation detection and charts ([ADR-076](docs/architecture/ADR-076-Health-Metrics-Ingestion.md), [ADR-148](docs/architecture/ADR-148-Health-Daily-Rollup.md), [GUIDE_IPHONE_SHORTCUTS_HEALTH](docs/guides/GUIDE_IPHONE_SHORTCUTS_HEALTH.md)).

#### Your own tools (MCP)

- Per-user servers with API key, bearer or OAuth 2.1 authentication (dynamic registration, PKCE), HTTPS-only, SSRF-checked, credentials encrypted.
- Conformant to the protocol's current revision on both halves and reading tool declarations to the letter of JSON Schema 2020-12 ([ADR-224](docs/architecture/ADR-224-Conformite-MCP-2026-07-28-SDK-v2.md), [ADR-255](docs/architecture/ADR-255-MCP-Tool-Declaration-Conformance.md)).
- MCP Apps rendered as sandboxed widgets behind a CSP airlock ([ADR-098](docs/architecture/ADR-098-CSP-Widget-Airlock.md)).
- An iterative mode where a dedicated agent reads a complex server's docs before calling it ([MCP_INTEGRATION](docs/technical/MCP_INTEGRATION.md)).
- A provider's cooldown is shared across workers for that person's server, so another concurrent request cannot restart a wait the service already imposed.

#### Skills and plugins

- Agentskills.io skills with progressive disclosure, sandboxed scripts and rich outputs (maps, dashboards, calendars, QR codes…), written from a conversation and proposed on a card the person installs in one click ([SKILLS_INTEGRATION](docs/technical/SKILLS_INTEGRATION.md)).
- A public skill library: search skills.sh, read a skill's every file, source, exact version and published audits before installing it at the commit that was read, and update it when its folder moves; a skill from the library, an address or a plugin is third-party — run in an isolated runner, never near a connector, its answer drawn without images or HTML ([ADR-327](docs/architecture/ADR-327-Skill-Library-And-Third-Party-Skills.md)).
- Skills that run their own commands — Python, Node, shell — in a throwaway copy of their folder, from a dedicated sandbox image with no Docker client and no application code; what they write comes back as generated files, and a command reaches only the hosts it declares, through the egress proxy.
- Agent Plugins v1 packages — skills plus streamable-http MCP servers — installed in one step with an exhaustive per-component report ([ADR-225](docs/architecture/ADR-225-Standard-Agent-Plugins-v1.md)).

### Act, under your control

#### Manage LIA through conversation

Ask LIA to inspect or change supported preferences and application objects:
reminders, routines, memories, skills and other declared capabilities. Reads and
minor reversible settings follow their own authorization policy; creations,
deletions and sensitive operations present a reviewable confirmation. File,
private-input and connector authorization steps continue through their native
browser flows. Commands remain account-scoped, expiring and checked against
current authority; administrator capabilities stay reserved to administrators.
The [application commands guide](docs/technical/APPLICATION_COMMANDS.md) describes
the supported surfaces and secure continuation contract.

#### Two execution modes, one toggle

- The _pipeline_ builds and validates a plan, applies the required approval gates and executes tools in dependency-aware waves.
- _ReAct_ adapts its next steps to tool results for exploratory or ambiguous requests. Token use and latency depend on the task and configured models.
- Both stream through the same response node ([ADR-070](docs/architecture/ADR-070-ReAct-Execution-Mode.md), [PLANNER](docs/technical/PLANNER.md)).
- A ReAct tool result is projected item by item under a token budget derived from the slot's own window, never cut mid-item, the cut stated to the model and counted ([ADR-286](docs/architecture/ADR-286-Tool-Result-Projected-Per-Item-Under-A-Token-Budget.md)).
- In the pipeline too, what a read step found beyond the cards — durations, connections, a next page — reaches the answer through the same projection, and a tool's declared failure is never returned as a success; a for-each with failed items keeps its successes ([ADR-347](docs/architecture/ADR-347-Read-Tool-Data-Reaches-The-Pipeline-Answer-A-Declared-Failure-Is-Never-A-Success.md)).
- The loop binds its tools by relevance — the detected domains' tools, the best-ranked doors of every other family, the top of the turn's global ranking, a large catalogue such as the settings reached through its own domain — so no family falls off a blind cap and the schemas stop being most of the prompt, and it reads the same knowledge spaces the pipeline reads ([ADR-293](docs/architecture/ADR-293-React-Tools-Bound-By-Relevance.md)).
- A ReAct turn is judged on its result: every fact the loop set out to obtain ends obtained or declared with the rungs tried. A declared gap buys one bounded recovery pass through a node that calls no model ([ADR-310](docs/architecture/ADR-310-ReAct-Turn-Judged-On-Its-Result.md)).
- Requested outcomes are checked against canonical structured observations, including the value, operation, account and completeness expected. A draft, opaque result or delegated announcement does not prove completion. Independent eligible reads return checkpointed segments; exact fresh reads may be reused within the same turn, with mutation invalidation and bounded budgets ([ADR-336](docs/architecture/ADR-336-Requested-Outcomes-Checked-Against-Canonical-Observations.md), [ADR-337](docs/architecture/ADR-337-Checkpointed-ReAct-Read-Segments-And-Turn-Local-Reuse.md)).
- Each person picks an exchange rhythm. Frequent binds every tool, moves the turn's context after the question and drops the history by blocks anchored on the turn counter, so the provider's prompt cache is read from one turn to the next. Occasional keeps the relevance selection at a steady cost ([ADR-308](docs/architecture/ADR-308-ReAct-Cross-Turn-Prompt-Cache.md), [ADR-311](docs/architecture/ADR-311-Exchange-Rhythm-Is-The-Persons-Choice.md)).

#### Human-in-the-Loop

- Five interrupting approval levels (clarification, draft critique, destructive confirmation, bulk `FOR_EACH` confirmation, modifier review) plus plan approval, currently auto-approved because tool-level approval supersedes it ([HITL](docs/technical/HITL.md), [ADR-106](docs/architecture/ADR-106-HITL-Contract-Coherence.md)).
- Several independent drafts in one turn are reviewed one per question, with their position stated and nothing executed before the last answer, while a lot you pre-approved as a list keeps its grouped confirmation ([ADR-288](docs/architecture/ADR-288-Independent-Drafts-Reviewed-One-At-A-Time.md)).
- A draft and its report are described once and drawn per surface — a `lia-card` in the chat, Markdown on a ticket or an external channel — the report naming to whom and what ([ADR-289](docs/architecture/ADR-289-Draft-Surfaces-Drawn-From-One-Description.md)).
- An e-mail to yourself needs no confirmation, because its recipient is not a parameter — the address your mailbox's provider states, or your verified one through LIA's relay — so a routine can send you its result ([ADR-314](docs/architecture/ADR-314-An-E-Mail-To-Oneself-Needs-No-Confirmation.md)).

#### Phone calls on your behalf — and to you

- Through your own ElevenLabs + Twilio connector, calls to third parties require confirmation before dialing. You review the recipient, number and objective; instructions bound the mandate, calendar access exposes free/busy information, and the call is not recorded. The post-call summary and available usage information remain reviewable ([ADR-127](docs/architecture/ADR-127-Agentic-Telephony.md), [TELEPHONY](docs/technical/TELEPHONY.md)).
- **The phone as a channel:** LIA calls _you_ on a number you declared and verified by a spoken code, with no confirmation card, the chat's own context and your configured personality on the line.
- The voice agent reads everything the chat reads through the same read-only tools (mails, calendar, tasks, contacts, files, places, weather, memory — one switch per domain, yours) and acts on nothing.
- What you say comes back as your own message, with drafts to confirm in the chat, ten relay verdicts and one bill per call for what LIA spent ([ADR-290](docs/architecture/ADR-290-Phone-As-A-Channel-Owner-Calls.md)).
- Since ADR-301 a voice session has a **mode**, and the policy follows it whatever the line. In _Live_ (the default), each request is a chat turn of yours handled while you speak; a question LIA asks is the answer, and the next request resumes the run that asked. In _Live direct_, the voice reads and the words are relayed at the end. Phone and browser share one closing; the effective mode is derived and published, and the browser's direct session is relayed like a call ([ADR-301](docs/architecture/ADR-301-Voice-Sessions-One-Policy-Per-Mode.md)).

#### Documents and images

- CSV, Excel, Word, PowerPoint, PDF, Markdown or text produced by local renderers with each format's native mechanisms (styles, fields, layouts, typed tables, bookmarks).
- Format-specific renderers manage layout, and truncated structured model output is rejected instead of silently producing an incomplete file ([ADR-226](docs/architecture/ADR-226-Document-Generation-Agent.md), [ADR-274](docs/architecture/ADR-274-Document-Craft-Renderer-Owned-Model-Semantic.md), [ADR-275](docs/architecture/ADR-275-Truncated-Structured-Output-Is-A-Refusal.md)).
- Image generation and natural-language editing on OpenAI GPT Image or Qwen Image 3.0 — a model family declares its offer, so nothing the configured model cannot serve is priced, offered or selected, the person's preference is resolved to that offer and every image arrives in the chosen format ([ADR-305](docs/architecture/ADR-305-Image-Model-Declares-Its-Offer.md), [IMAGE_GENERATION](docs/technical/IMAGE_GENERATION.md)).
- On request, a new image's description is rewritten following the provider's own advice — a quoted text kept word for word, the original sent whenever in doubt, an edit never rewritten ([ADR-315](docs/architecture/ADR-315-Image-Prompt-Enhancement.md)).

#### Keep and send what LIA made

- Generated images, documents and screenshots can be kept without a deadline within published account limits, or released to a fresh normal deadline.
- Their chat cards reflect the current state ([ADR-319](docs/architecture/ADR-319-A-Generated-File-Can-Be-Kept.md)).
- A file or answer can be sent by e-mail with a subject and optional note: chosen recipients through a connected mailbox, or the account's verified address through LIA's relay, under the selected provider's displayed size limit; typing a recipient suggests the person's contacts by name or phone number and inserts their address ([ADR-321](docs/architecture/ADR-321-A-File-Or-An-Answer-Sent-By-E-Mail.md)).

#### A browser, a sandbox, delegates

- Browser control with progressive screenshot streaming ([ADR-059](docs/architecture/ADR-059-Browser-Control.md)).
- A short Python script run in the skills sandbox when a step needs real computation, ReAct only ([ADR-249](docs/architecture/ADR-249-Ephemeral-Python-In-The-Existing-Sandbox.md)) — and, when the person allows it, reaching the web through one egress proxy that swaps per-run tokens for the person's own connector keys, an unknown host asked with three answers and settled inside the loop ([ADR-298](docs/architecture/ADR-298-Sandbox-Egress-Toolbox.md)).
- Persistent read-only sub-agents with their own instructions, skills and budgets; at their step limit they still write their deliverable from what they found, and a failure says how far it got ([SUB_AGENTS](docs/technical/SUB_AGENTS.md), [ADR-083](docs/architecture/ADR-083-Sub-Agent-Delegation-React.md)).

#### The workboard

A ticket has a lifecycle, a holder and a result ([ADR-276](docs/architecture/ADR-276-Workboard.md), [WORKBOARD](docs/technical/WORKBOARD.md)):

- One row per ticket, shared by its owner and its holder, across seven columns with sub-tickets, comments and a history; the holder can be you, a connected peer, or LIA.
- When LIA holds it, a sweep claims one ticket at a time, runs it in the execution mode the ticket declares, and settles from an explicit result — a quota ceiling or a busy conversation postpones the run, never fails it.
- A run that needs a decision asks instead of refusing: the ticket lands in « To confirm » carrying the exact card the chat would show, and your comment _is_ the answer.

### Anticipate

#### The heartbeat

- LIA takes the initiative when it is worth it: calendar, mail, tasks, weather changes, interests, memories, habits and the workboard are aggregated, a cheap structured decision says whether to speak, at your local time, and a second pass writes it in your voice and language.
- Each source has a switch that says whether it is connected, you set the window and the channels — there is no daily quota: every pass of the window reaches the decision, bounded by the cooldowns ([ADR-328](docs/architecture/ADR-328-Heartbeat-Without-A-Daily-Quota.md)) —, rate every notification, and every pass files what it read in your registers ([HEARTBEAT_AUTONOME](docs/technical/HEARTBEAT_AUTONOME.md), [GUIDE_HEARTBEAT](docs/guides/GUIDE_HEARTBEAT_PROACTIVE_NOTIFICATIONS.md)).

#### Moments served to the minute

- A periodic sweep cannot serve an instant, so a finished meeting or an awaited reply is kept as an anticipated moment, claimed under a lock, revalidated, and served under the full eligibility checker while bypassing only the deferrals.
- Mail watches are answered from the push-driven wake that already holds the Gmail delta ([ADR-281](docs/architecture/ADR-281-Anticipated-Moments-And-Mail-Watches.md), [ADR-261](docs/architecture/ADR-261-Push-Driven-Heartbeat-Wake-And-Incremental-Drive-Sync.md)).

#### Routines and reminders

- A scheduled routine or reminder uses the timezone-aware recurrence engine ("every three days", "the 2nd Tuesday of the month").
- A condition routine has no schedule: it is checked at the system's cadence for its source and records a run only when it fires. A weather condition always reads Google Weather and fires only on a change due within the next hours, above a published precipitation threshold, the run told the hour, the day and the source.
- The studio offers one mode at a time, with a week view of actual runs ([ADR-268](docs/architecture/ADR-268-Generic-Recurrence-And-Reminder-Management.md), [ADR-322](docs/architecture/ADR-322-One-Clock-Per-Routine.md), [ADR-265](docs/architecture/ADR-265-Routine-Week-Timeline-And-Run-History.md), [SCHEDULED_ACTIONS](docs/technical/SCHEDULED_ACTIONS.md)).

#### Interests and habits, learned with restraint

- An interest is created only on a named ground quoted from your own words, with six exclusion classes and a cap on deletions per run ([ADR-166](docs/architecture/ADR-166-Extraction-Admission-Doctrine.md), [INTERESTS](docs/technical/INTERESTS.md)).
- Habits are learned deterministically from a recurrence ledger, promoted, refreshed or demoted by a nightly job and never on doubt.
- A status you set on a learned window holds for the heartbeat, its scheduling and the assistant's context alike, a missed routine is offered by name, and one learning switch closes every door ([ADR-214](docs/architecture/ADR-214-Habitudes-Utilisateur-Apprentissage-Deterministe.md)).

#### A daily briefing

The home page opens on the date and LIA's living face, then aggregates your sources in parallel with a per-section cache and an LLM synthesis — an agenda on a timeline, an illustrated weather, a Workboard card with exact counts of what waits on you, what LIA holds, what your connections hold and what is overdue — served by a read-only domain outside the agent graph ([BRIEFING_DOMAIN](docs/technical/BRIEFING_DOMAIN.md)). Meetings and calls read as timelines by day and part of day, and a list that cannot load says so instead of looking empty.

### Remember

#### Long-term memory

- Facts are extracted after each conversation, pinned or edited by hand, and injected by relevance with their scores visible in the debug panel ([LONG_TERM_MEMORY](docs/technical/LONG_TERM_MEMORY.md), [MEMORY_RESOLUTION](docs/technical/MEMORY_RESOLUTION.md)).
- Newly learned standing instructions are pinned automatically. You can edit, unpin or delete them; automatic maintenance respects their protection.
- The planner, the ReAct loop and the phone look them up on purpose through one lookup door that answers what was asked, never just the latest memories ([ADR-313](docs/architecture/ADR-313-Long-Term-Memory-As-An-Active-Lookup.md)).

#### Personal journals

- Introspective notebooks the assistant keeps in the first person, stratified from raw observations to a user portrait, with an epistemic status per entry and a deferred self-evaluation at zero added LLM cost.
- The portrait is an analysis of the person, not an inventory, read from everything LIA keeps — memories, interests, learned habits, relationship debriefs, open loops, Workboard tickets, routines, reminders and kept answers — each read whole under its own gates; its brief is a summary of its own, a journal change marks it stale rather than erasing it, and it shows which sources it used ([ADR-079](docs/architecture/ADR-079-Stratified-Journal-Consciousness.md), [ADR-292](docs/architecture/ADR-292-Portrait-Reads-Four-Sources.md), [ADR-343](docs/architecture/ADR-343-Portrait-Reads-The-Whole-Material-And-Its-Brief-Is-A-Synthesis.md), [JOURNALS](docs/technical/JOURNALS.md)).
- A read tool searches them on demand — directives, patterns and facets, never raw observations ([ADR-318](docs/architecture/ADR-318-Assistant-Tools-Exact-Answers-And-Own-Records.md)).

#### Knowledge spaces

- Personal document bases in 15+ formats with hybrid search (pgvector cosine + BM25), Google Drive folder sync, a Gmail label as a source, and a system space that indexes the product's own help corpus so LIA can explain itself — drawn from the in-app FAQ, whose 491 questions cover every feature a person can use, in six languages.
- A document that cannot be indexed says why in your language — a scanned PDF without a text layer names its remedy.
- Any indexed document, paused space or not, attaches to a chat message as a copy from the composer's « + » ([ADR-295](docs/architecture/ADR-295-Knowledge-Documents-As-Message-Attachments.md), [GUIDE_RAG_SPACES](docs/guides/GUIDE_RAG_SPACES.md), [ADR-055](docs/architecture/ADR-055-RAG-Spaces-Architecture.md), [ADR-058](docs/architecture/ADR-058-System-RAG-Spaces.md)).

#### Meetings and minutes

- Record from the phone or the computer while the chat stays usable, with a capture that survives reloads and lost microphones.
- A chain of transcription engines walked at processing time.
- Minutes filled from one of thirty built-in templates or your own, reformatted in place or derived into a second set from the same transcript ([ADR-258](docs/architecture/ADR-258-Meeting-Recording-And-Structured-Minutes.md), [ADR-259](docs/architecture/ADR-259-Meeting-Template-Library-And-Reformatting.md), [MEETINGS](docs/technical/MEETINGS.md)).

#### People

- A 360° relationship lens over open loops, calls, messages and memories, with a written debrief per person built lazily when the card opens ([ADR-176](docs/architecture/ADR-176-Personal-CRM-Relations.md), [ADR-193](docs/architecture/ADR-193-Read-Capabilities-And-Merged-Identity.md), [ADR-269](docs/architecture/ADR-269-Relationship-Debrief.md)).
- Connections between users of the same instance, assistant to assistant — relayed messages delivered by the recipient's own assistant, field-level read-only shares, silent blocking ([ADR-180](docs/architecture/ADR-180-Peer-Connections.md), [ADR-182](docs/architecture/ADR-182-Peer-Routing-Awareness-And-Honest-Failure.md)).
- A generated image shared with a connection as a copy, in one click and one transaction, its comment quoted literally in their chat ([ADR-316](docs/architecture/ADR-316-Sharing-A-Generated-Image-With-A-Connection.md)).

#### What LIA produced is yours

- Generated images, documents and browser screenshots have their own galleries with search, exact totals and a visible retention deadline.
- Clearing a conversation never clears them ([ADR-279](docs/architecture/ADR-279-Generated-Assets-Gallery.md)).
- LIA finds them again when asked and shows them as the chat's own cards ([ADR-318](docs/architecture/ADR-318-Assistant-Tools-Exact-Answers-And-Own-Records.md)).

#### What you keep is yours too

- A bookmark on every answer copies it with the request that produced it and the answer's date, so it outlives the conversation.
- A Bookmarks tab beside the galleries lists them newest first, with search, an exact total against the account's cap, sharing, a Markdown export and deletion.
- Every kept answer is also indexed in a knowledge space of your own, so LIA cites it weeks later when a question concerns it, and the card shows the indexing state and two named costs — what the answer cost to produce and what indexing it cost, as billed ([ADR-282](docs/architecture/ADR-282-Message-Bookmarks.md), [ADR-291](docs/architecture/ADR-291-Kept-Answers-Knowledge-Space.md), [BOOKMARKS](docs/technical/BOOKMARKS.md)).

### Trust it

#### Three registers, sealed on request

- One row per action (claimed before it happens, closed from an explicit result), one per consultation (which capability read what, when, with what outcome), one per turn.
- Proactive acts and direct reads are recorded too.
- Extractions are complete, never capped.
- An opt-in per-account hash chain makes the registers tamper-evident while preserving the right to erasure, and LIA answers « what did you do? » from them with exact totals ([ADR-263](docs/architecture/ADR-263-Execution-Authority-Chain-And-Effect-Register.md), [ADR-270](docs/architecture/ADR-270-Spend-Roads-And-Register-Authorship.md), [ADR-273](docs/architecture/ADR-273-Complete-Register-Extractions.md), [ADR-318](docs/architecture/ADR-318-Assistant-Tools-Exact-Answers-And-Own-Records.md), [AI_ACT_TRACEABILITY](docs/technical/AI_ACT_TRACEABILITY.md)).

#### Spend that answers to two ceilings

- Every platform-paid token counts against the account's quota _and_ the instance's daily budget.
- A refusal carries a dedicated code and a `Retry-After`.
- Where each module's spend is recorded is declared and guarded, never inferred.
- The rule covers more than model tokens: every euro the platform pays for a person — a Maps lookup during a call, the briefing's weather, a photo shown, a voice synthesis — reaches their ledger whatever the path. One persistence predicate covers every family the tracker holds, and a counter fails closed into an alert ([ADR-216](docs/architecture/ADR-216-Plafond-De-Depense-D-Instance.md), [ADR-272](docs/architecture/ADR-272-Every-Platform-Paid-Token-Answers-To-Both-Ceilings.md), [USAGE_LIMITS](docs/technical/USAGE_LIMITS.md)).
- Spend uses the price the provider bills: tariffs read from the vendors' pages, a prompt-cache write billed at its price, a pricing window that names its days, a Maps call filed at the SKU its request triggers, and every tariff writer reaching every worker ([ADR-306](docs/architecture/ADR-306-Claude-Request-Surface-And-Billed-Prompt-Cache.md), [LLM_PRICING_MANAGEMENT](docs/technical/LLM_PRICING_MANAGEMENT.md)).
- Every reported model attempt keeps the tariff and exchange rate captured when it started. Paid failures, retries and background work reach the same ledger, including work that finishes after a cancelled conversation; missing usage is not invented ([TOKEN_TRACKING_AND_COUNTING](docs/technical/TOKEN_TRACKING_AND_COUNTING.md)).

#### Strong authentication

- WebAuthn passkeys, a TOTP second factor with backup codes, step-up re-authentication on sensitive actions, device sessions with per-device revocation, server-side Redis sessions behind HTTP-only cookies ([ADR-143](docs/architecture/ADR-143-Strong-Authentication-Passkeys.md), [ADR-144](docs/architecture/ADR-144-Device-Sessions.md), [AUTHENTICATION](docs/technical/AUTHENTICATION.md)).
- A federated sign-in proves an address, never a right — it can neither activate nor unblock an account ([ADR-002](docs/architecture/ADR-002-BFF-Pattern-Authentication.md)) — and every « who is calling? » reads one resolver ([ADR-213](docs/architecture/ADR-213-L-Identite-De-L-Appelant-Vient-D-Un-En-Tete-Qu-Il-Ne-Peut-Pas-Ecrire.md)).

#### Your data, by construction

- Credentials are encrypted with Fernet. Logs keep facts, never the words of the people they concern; the guard checks the value rather than the field name ([ADR-317](docs/architecture/ADR-317-A-Log-Line-Carries-Facts-Never-The-Words.md)).
- A full-account GDPR export is available ([ADR-145](docs/architecture/ADR-145-Account-Export.md)). External content keeps its provenance through compaction, and its envelope holds in every spelling ([ADR-167](docs/architecture/ADR-167-Content-Trust-Registry.md)); mail servers present a verified certificate before any login.
- Skill scripts run in a throwaway container. Automated backups have a tested one-command restore ([ADR-109](docs/architecture/ADR-109-PostgreSQL-Backup-Strategy.md), [SECURITY](docs/technical/SECURITY.md)).

#### Exact where it must be

Arithmetic, dates and currencies use tools in both execution modes, never a model's estimate:

- Calculations are parsed and evaluated in exact decimal, with rounding stated.
- Durations are counted between absolute instants across a clock change.
- Currency conversion uses the European Central Bank reference rate with its date ([ADR-318](docs/architecture/ADR-318-Assistant-Tools-Exact-Answers-And-Own-Records.md)).

#### Failures made visible

- One status vocabulary whose every member is produced and read, one success predicate for the register, the metrics and the ReAct loop, a structural failure marker on the ReAct message, and an honesty directive that names the tool that failed and the exact total, so the response has the recorded failure evidence instead of an unexplained gap ([ADR-303](docs/architecture/ADR-303-Tool-Failure-Restitution.md)).
- Every act is filed under its own turn and stated to the response as the assistant's own ([ADR-263](docs/architecture/ADR-263-Execution-Authority-Chain-And-Effect-Register.md)).
- No database transaction stays open while a provider answers ([ADR-304](docs/architecture/ADR-304-No-Transaction-Across-A-Network-Call.md)).
- A routine never asks a question nobody can see and never repeats an action after a timeout; an e-mail is sent once, and a provider's rate limit is waited out rather than reported as an outage ([ADR-276](docs/architecture/ADR-276-Workboard.md)).

#### Switches, not redeploys

- Every capability switches off from the admin panel, each declaring where it is enforced.
- The tools a switched-off capability names leave both execution modes at once: the switches are applied to the turn's catalogue once, and the Pipeline planner, the ReAct loop, a delegated sub-agent and a skill's ready-made plan all read that same catalogue; the Workboard, LIA connections, MCP servers and Skills switches name no tools and close their pages alone ([ADR-280](docs/architecture/ADR-280-Complete-Capability-Control.md)).
- A switch removes the capability, never the record ([ADR-217](docs/architecture/ADR-217-Capacites-Administrables.md), [ADR-280](docs/architecture/ADR-280-Complete-Capability-Control.md)).

---

## Administration & Monitoring

The admin interface brings deployed capabilities, accounts, model configuration, budgets and diagnostics into one place. The observability stack adds metrics, logs, traces and alerts. Deployment settings still define which services and capabilities are available.

### Admin Dashboard

| Area                          | What you control                                                                                                                                                                                                                                                                                                                                                           |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **LLM configuration**         | The model behind every node and slot, provider parameters, prompt versions, the context window per slot                                                                                                                                                                                                                                                                    |
| **Bounded JEV decisions**     | An independent opt-in switch for each native decision, a general switch, dedicated model and price settings, and diagnostic traces of duration, fallback and spend; uncertain results return to the established path ([ADR-325](docs/architecture/ADR-325-JEV-Bounded-Decisions-With-Hot-Switches-And-Accounted-Fallbacks.md), [guide](docs/technical/JEV_INTEGRATION.md)) |
| **Model catalogue & pricing** | Providers, capability flags, accepted reasoning depths, a provenance badge and prices per model — the source of truth for the LLM factory, with its status against the public registries; image-generation and Google API pricing alongside; live cross-worker invalidation                                                                                                |
| **Platform capabilities**     | One switch per capability, grouped in families, each row showing the deployment bound, the operator choice and the state actually enforced                                                                                                                                                                                                                                 |
| **Budgets & limits**          | Per-user token, message and cost quotas with live gauges; the instance daily ceiling in euros, today's spend and what remains                                                                                                                                                                                                                                              |
| **Knowledge & skills**        | Knowledge spaces and reindexation, the system FAQ space, skills (enable, translate, delete), admin MCP servers and plugins                                                                                                                                                                                                                                                 |
| **People & voice**            | Users with every per-account switch as a sortable column, roles, connector health, assistant personalities, the TTS catalogue and voice picker                                                                                                                                                                                                                             |
| **Platform health**           | Incidents and their diagnoses, each shown with the evidence it was written from                                                                                                                                                                                                                                                                                            |
| **Registers**                 | Readable, technical and Article-12 extractions over one, several or all accounts — masked unless audited                                                                                                                                                                                                                                                                   |
| **Broadcast, debug, demo**    | Announcements to everyone or to chosen accounts, each stored with its recipients and listed with its audience; per-user debug verbosity, the public showroom link, CSV consumption exports                                                                                                                                                                                 |

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

- **Prometheus**: 621 custom metrics (agents, LLM, infrastructure), labelled by route template — a name or a search in an address never becomes a series. A metric nobody can see is a metric nobody acts on: every one must be wired to a Grafana panel, a recording rule or an alert, and a shrink-only ratchet fails the build on a newly blind metric.
- **Grafana**: 31 dashboards, including product-value and radio cockpits · **Loki**: structured JSON logs that keep facts, never people's words, shipped by Grafana Alloy ([ADR-317](docs/architecture/ADR-317-A-Log-Line-Carries-Facts-Never-The-Words.md)) · **Tempo**: distributed tracing, spans named by the route template · **Langfuse**: LLM tracing with prompt versions. The whole stack runs on supported versions, pinned by digest.
- **Linked signals, a pipeline that watches itself**: a log line opens its trace, a trace its logs and metrics, a latency point its exemplar; Loki, Alloy, Tempo and Grafana are scraped on closed keep-lists and `LogsNotDelivered` fires when lines go missing; every dashboard opens on seven days (logs and traces on four hours) behind one shared menu — [ADR-333](docs/architecture/ADR-333-Linked-Signals-And-A-Pipeline-That-Watches-Itself.md).
- **Probes**: liveness (`GET /health`) split from readiness (`GET /ready`, 503 unless PostgreSQL **and** Redis answer) — [ADR-115](docs/architecture/ADR-115-Liveness-Readiness-Probes.md).
- **Alerting**: a vital core (service, database and Redis down, disk, OOM, 5xx rate, SSE latency, backup failure, public-endpoint and TLS probes, chain self-monitoring) evaluated by Prometheus, emailed by a dedicated Alertmanager, unit-tested with `promtool`, every alert linking its runbook. The latency alert observes only turns a person waits for, and only over enough of them for a p95 to mean something; the operator's daily report opens on the alerts that fired, the incidents still open and the container restarts, each source named when it cannot be read — [ADR-119](docs/architecture/ADR-119-Alerting-Reactivation-Minimal-Core.md).
- **Per-process memory**: every API worker publishes what it holds (`lia_worker_memory_bytes`, one series per live worker), drawn on the infrastructure dashboard and watched by an alert that names the process; what a process loads is declared, measured on the target host and bounded where it multiplies — the supervisor never imports the application, heavy libraries load where they are used, and the speech engine keeps one resident model per worker ([ADR-283](docs/architecture/ADR-283-Worker-Memory-Anatomy.md)).
- **Self-diagnostics**: a leader-elected self-check of the golden signals, one incident per outage whichever observer saw it first, and a budget-capped diagnosis written in each administrator's language from evidence collected at diagnosis time — metrics, a sanitised log excerpt, the running build, the alert's runbook — shown under its verdict in Settings › Platform health; an alert incident whose resolution never arrived is reconciled from Alertmanager and closed ([ADR-247](docs/architecture/ADR-247-Self-Diagnostics-And-Answer-Resilience.md), [ADR-266](docs/architecture/ADR-266-Diagnosis-Evidence-At-Diagnosis-Time-And-Exact-Str-Embedding-Inputs.md)).

---

### See the instance from the operator's side

These three Grafana screenshots were supplied by the project owner and reproduced unchanged. Their figures show the supplied dashboard state; the [Grafana manifest](apps/web/public/screenshots/proof/grafana-manifest.json) records their origin and dimensions.

<p align="center">
  <a href="apps/web/public/screenshots/proof/grafana-overview.png"><img src="apps/web/public/screenshots/proof/grafana-overview.png" alt="Grafana — Host CPU, memory, disk, network and container resources" width="1200" /></a>
  <br /><em>Grafana — infrastructure and host/container resources.</em>
</p>

<p align="center">
  <a href="apps/web/public/screenshots/proof/grafana-costs.png"><img src="apps/web/public/screenshots/proof/grafana-costs.png" alt="Grafana — LLM token consumption, cost breakdowns and cache ratio" width="1200" /></a>
  <br /><em>Grafana — LLM tokens, costs and cache.</em>
</p>

<p align="center">
  <a href="apps/web/public/screenshots/proof/grafana-activity.png"><img src="apps/web/public/screenshots/proof/grafana-activity.png" alt="Grafana — Request origins and rates, account activity, tool usage and router intents" width="1200" /></a>
  <br /><em>Grafana — request origins and rates, account activity, tool usage and router intents.</em>
</p>

---

## Built by an AI, Directed by a Human

> _"Speed comes from the AI. Quality comes from the framework."_

Nearly **100% of this codebase was written by an AI**, under human direction: a written
engineering rulebook, blocking automated checks, systematic review, adversarial audits.
The result is measured, not proclaimed:

|                           |                                         |                                         |                                                                         |
| ------------------------- | --------------------------------------- | --------------------------------------- | ----------------------------------------------------------------------- |
| **55** functional domains | **963,000+** source lines (excl. tests) | **63,000+** inventoried automated tests | **347** ADRs                                                            |
| **283** versions shipped  | **6 languages**, parity enforced in CI  | **621** Prometheus metrics              | [**8.3/10** technical audit, 24 normalized areas](docs/audit/README.md) |

Source-line figure: 963,005 physical lines in Python, TypeScript, JavaScript and CSS under `apps/api/src` and `apps/web/src`, excluding test directories and `*.test.*`/`*.spec.*` files (measured 2026-10-18). Test inventory combines backend collection and the frontend suite; release qualification executes the repository's required gates. The published technical audit does not score security.

- **The full story** — method, trade-offs, results and what remains to be done, weaknesses included: [lia.jeyswork.com/story](https://lia.jeyswork.com/story)
- **The audit itself** — 24 normalized areas mapped to ISO/IEC 25010:2023, every score backed by executed evidence, open worksites included, with the protocol and the full standalone report: [docs/audit/](docs/audit/README.md)

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

A guided installer lives at the repository root ([ADR-215](docs/architecture/ADR-215-Self-Host-Installer.md)). It asks a short questionnaire (LAN exposure, your own reverse proxy, or managed HTTPS with Caddy), generates a private `.env` and Compose overlay, applies the reference seeds atomically, creates the admin and provider keys over stdin, verifies the installation beyond `/ready` and prints a non-secret report. The experimental speaking avatar is an optional choice, disabled by default; each person then connects their own Simli account. A complete source checkout builds the images locally; an official release directory uses prebuilt digests only when its adjacent manifest is qualified. The Google Gemini key is an optional question — memory recall, searches by meaning and image analysis wait for it — and the final report names every capability left waiting for a key. Resume an interrupted run with `./install.sh --resume`; change a running installation with `./install.sh --reconfigure`, which shows the answers in force (Enter keeps them) and every setting they would rewrite before anything changes, replaces each file atomically after a private backup, recreates the containers without rebuilding and puts the previous files and stack back if the new one does not come back ready. The shipped `.env` profiles size the connection pools against the database's memory floor as well as its ceiling, and a guard reads both profiles with the Compose file so the sizing cannot drift ([ADR-283](docs/architecture/ADR-283-Worker-Memory-Anatomy.md)).

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

- **Pipeline** (default) — a **Planner** decomposes the request into an execution plan (a small DSL with dependencies, conditions and `FOR_EACH` iteration), a **Semantic Validator** checks its coherence, tool-level approval flows review the actions that require confirmation, and a **Task Orchestrator** runs the tools in parallel waves; Bayesian pattern learning shortens the next similar request. Planning and validation precede execution; token use depends on the task and selected models.
- **ReAct** (⚡) — the model reasons iteratively, calling tools one by one and adapting to each result. Suited to exploratory, research or ambiguous queries; cost and latency depend on the work and selected models. Its iteration budget is extended while the loop keeps producing results, a turn that stops mid-flight closes its own books, the tools it binds are chosen by relevance to the question rather than cut by a cap — or all of them, when the person chose frequent exchanges so the provider's cache reads each turn back from the previous one — and a turn is judged on its result: a gap it declares buys a bounded recovery pass.

```mermaid
graph TD
    A[User Message] --> CP[Compaction]
    CP --> B[Router Node]
    B -->|conversation| C[Response Node]
    B -->|pipeline mode| D[Planner Node]
    B -->|react mode| R1[ReAct Setup]
    D -->|empty plan| C
    D --> E[Semantic Validator]
    E -->|ambiguous| CL[Clarification]
    CL --> E
    E -->|replan| D
    E --> F{Approval Gate}
    F --> G[Task Orchestrator]
    G --> H[Domain Agents + Tools]
    G -->|drafts| HD[HITL Dispatch]
    G -->|bulk action| FE[FOR_EACH Confirm]
    FE -->|approved| G
    H --> I[Initiative]
    HD --> I
    I --> C
    R1 --> R2[ReAct Call Model]
    R2 -->|tool_calls| R3[ReAct Execute Tools]
    R3 --> R2
    R3 -->|draft| HD
    R2 -->|declared gap| R5[ReAct Recovery]
    R5 --> R2
    R2 -->|done| R4[ReAct Finalize]
    R4 --> I
    C --> J[SSE Stream]
```

### Code Structure

```
apps/api/src/
├── core/                 # Settings composed per domain, constants, i18n tables, recurrence engine
├── domains/              # Bounded contexts (DDD); shared helpers stay separate
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

| Pattern                    | What it buys                                                                                                                                                                                                                                                         |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Five-layer tool system** | A generic connector base with OAuth auto-refresh, a meta-decorator composing metrics + rate limiting + context save, domain formatters, a declarative `ToolManifest`, and a catalogue loader — a tool is a few lines, not a file                                     |
| **Domain taxonomy**        | One declarative `DOMAIN_REGISTRY` (agents, result key, related domains, priority, routability) feeds catalogue filtering, semantic expansion and the initiative phase — never a second hand-maintained table                                                         |
| **Data registry**          | Tool results live in an in-memory store decoupled from the message history, so aggressive message windowing never loses a `$steps.X.field` reference                                                                                                                 |
| **Semantic validator**     | A dedicated LLM, distinct from the planner, inspects every plan for hallucinated capabilities, ghost dependencies, cardinality and scope errors before anything runs                                                                                                 |
| **Re-plan before running** | Validator issues go back to the planner a bounded number of times, and _panic mode_ retries planning once over a wider catalogue; once a plan has run, a failed step is stated in the answer, never replayed                                                         |
| **Connector abstraction**  | Python protocols and normalisers make Google, Apple and Microsoft interchangeable behind unified domain models; a resolver guarantees one provider per category                                                                                                      |
| **Published bounds**       | Whatever a validator can reject, its producer can read: every enforced limit is published to the planner, and what is mechanically repairable is repaired before validation ([ADR-184](docs/architecture/ADR-184-Published-Bounds-And-Non-Prescriptive-Verdicts.md)) |
| **Exact counts**           | A number shown to a person is exact or it does not exist — aggregates over the whole set, pages of rows, never a count derived from a capped page ([ADR-185](docs/architecture/ADR-185-Exact-CRM-Counts-And-Readable-Relayed-Messages.md))                           |
| **Boot-time completeness** | Every registry keyed by an enum or a domain is asserted complete at startup; the app refuses to boot on a missing entry rather than failing silently later                                                                                                           |
| **Error architecture**     | Tools return `ToolResponse` / `ToolErrorModel` with a closed `ToolErrorCode` taxonomy and a recoverability flag; the API raises through centralised exception helpers, never a raw `HTTPException`                                                                   |

> The long version: [How does LIA work?](https://lia.jeyswork.com/how) (public architecture guide), [ARCHITECTURE.md](docs/ARCHITECTURE.md), [ARCHITECTURE_LANGRAPH.md](docs/ARCHITECTURE_LANGRAPH.md), and the [living maps](docs/maps/README.md) — the functional map, the technical map and the history of every decision, also published in six languages on the [public site](https://lia.jeyswork.com/maps).

---

## Technologies

### Stack

| Layer         | Technology                                                                                                            | Role                                                              |
| ------------- | --------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| Backend       | Python 3.14 · FastAPI 0.141.1 · Pydantic 2.13.4 · SQLAlchemy 2.0.54 · Alembic                                         | REST API, SSE streaming, validation, async ORM, migrations        |
| Orchestration | LangGraph 1.2.14 · LangChain 1.3.15 · `mcp` SDK (Streamable HTTP)                                                     | Multi-agent graph, LLM abstraction, Model Context Protocol        |
| Data          | PostgreSQL 16 + pgvector · Redis 7.4                                                                                  | Data, checkpoints, vector search · cache, sessions, locks         |
| Frontend      | Node.js 24 LTS · Next.js 16.4.1 · React 19.3.0 · TypeScript · TailwindCSS · Radix UI · TanStack Query · react-i18next | App Router UI, accessible primitives, server state, six languages |
| Voice         | ONNX Runtime Web (wake word) · sherpa-onnx (offline Whisper) · Edge TTS · OpenAI · ElevenLabs · Gemini · Fish Audio   | In-browser detection, server transcription, speech synthesis      |
| Observability | Prometheus · Grafana · Loki · Tempo · Langfuse · structlog                                                            | Metrics, dashboards, logs, traces, LLM tracing                    |
| Delivery      | Docker (multi-arch amd64/arm64) · GitHub Actions · Task                                                               | Images, CI/CD, one build tool for every command                   |

The UI is responsive by design — desktop, tablet and phone — with touch-friendly, mobile-first components.

### Supported LLM Providers

The model catalogue lives in the database, curated from vendored public registries and editable from the admin panel; every row states where its capabilities came from, and a slot's output budget is held to the cap a vouched row declares, flagged on the configuration screen when it exceeds it ([ADR-244](docs/architecture/ADR-244-LLM-Catalogue-Truth.md)). Reasoning depth has one stored shape for every provider ([ADR-245](docs/architecture/ADR-245-Reasoning-Unification.md)); a model family is declared once, and a caller that needs two sentences asks for no reasoning rather than a small budget — a reasoning model bills its thinking inside `max_tokens` ([ADR-285](docs/architecture/ADR-285-Short-Answer-Without-Reasoning-And-One-Family-Declaration.md)). What a prompt says is what the code enforces, and nothing else: every placeholder has a producer, every published bound is the applied bound, prose never lives in a `.py` ([ADR-284](docs/architecture/ADR-284-Prompt-States-What-The-Code-Enforces.md)). Every prompt follows one layout — stable before volatile, one boundary each provider adapter translates into its own cache mechanism, no cache write nobody reads — and what each model generation accepts is measured on its API and declared once ([ADR-309](docs/architecture/ADR-309-One-Prompt-Layout-For-Every-Cache-Mechanism.md), [ADR-306](docs/architecture/ADR-306-Claude-Request-Surface-And-Billed-Prompt-Cache.md)).

| Provider   | Notes                                                                                                                                                              |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| OpenAI     | Prompt caching, reasoning models, structured output                                                                                                                |
| Anthropic  | Extended and adaptive thinking; request surface declared per generation, prompt cache shaped and its writes billed                                                 |
| Google     | Gemini, multimodal; `gemini-embedding-001` for retrieval                                                                                                           |
| DeepSeek   | Cost-effective reasoning with a thinking-mode toggle (`deepseek-flash`, `deepseek-v4-pro`); tariff by UTC window                                                   |
| Qwen       | Thinking, tools and vision through Alibaba Cloud DashScope; explicit prompt cache where the family needs it; Qwen Image 3.0; regional endpoint via `QWEN_BASE_URL` |
| Perplexity | Web-augmented answers; endpoint via `PERPLEXITY_BASE_URL`                                                                                                          |
| Ollama     | Compatible local models, capabilities discovered from the server, native client; `OLLAMA_BASE_URL`                                                                 |

### Local Models as First-Class Models

Compatible chat models hosted on your own machine can serve processing slots whose required capabilities they meet. Image generation, embeddings, Live and native decision providers have their own supported paths. Local inference depends on the chosen model and host resources. LIA drives Ollama through its **native API** rather than an OpenAI compatibility layer ([ADR-267](docs/architecture/ADR-267-Ollama-Native-Provider-And-Discovered-Capabilities.md)):

- **Thinking is controlled, not endured** — the configured depth reaches the server as `think`, including switching it off, and the thinking trace comes back separated from the answer.
- **The server declares the capabilities** — tools, vision, thinking and context length are read from the tag listing, so a depth never reaches a model that cannot think and a control a local model would ignore is not offered.
- **The context window belongs to the configured slot** ([ADR-278](docs/architecture/ADR-278-Per-Slot-Context-Window.md)) — a frugal router and a generous responder can share one model with different windows; it is the number LIA _asks_ for and the number it _counts_ with.

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

| Metric                  | Value                                                                                                                                                |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| Backend tests           | 50,397 collected over `tests/`, across 3,292 files (`pytest --collect-only -q --no-cov`, 2026-10-18)                                                 |
| Frontend tests (vitest) | 13,177 passing across 1,066 files (`task test:frontend:coverage`, 2026-10-18), plus hermetic Playwright journeys with axe, dark-mode and zoom checks |
| Coverage floor          | 78% enforced in CI on the backend — a shrink-only ratchet, never lowered; frontend thresholds per glob                                               |
| Technical audit         | **8.3/10** across 24 normalized areas — [full public report & protocol](docs/audit/README.md)                                                        |

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
Pre-push: secret scan           Security workflow (weekly)
                                  CodeQL (Python, JS/TS, Actions)
                                  Dependency audit (pip-audit + pnpm audit)
                                  Trivy filesystem scan
                                  SBOM generation
                                Dependency watch (weekly, ADR-331)
                                E2E + a11y matrix: Chromium · Firefox · WebKit (weekly)
```

| Practice                 | Implementation                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Reproducible builds**  | Universal Python lockfiles (linux/amd64, arm64, Windows), hash-verified installs everywhere, a guard failing manifest edits without lock regeneration ([ADR-112](docs/architecture/ADR-112-Python-Dependency-Locking.md))                                                                                                                                                                                                                             |
| **Supply chain**         | Every GitHub Action pinned by commit SHA and every production build input by version and digest, `permissions: contents: read`; a weekly watch of the advisories each dependency publishes, a refresh under a cooling-off period that never moves backwards, Dependabot on the same cooldowns ([ADR-331](docs/architecture/ADR-331-Dependency-Watch-And-A-Refresh-That-Never-Goes-Back.md)); the CI's secret scan before every push; SBOM per release |
| **Shrink-only ratchets** | Coverage, file size, cyclomatic complexity, MyPy debt, React hooks, accessibility and metric visibility can only improve — a baseline is lowered after the work, never raised to absorb a regression                                                                                                                                                                                                                                                  |
| **Documentation gate**   | Every version, count and threshold a document states is recomputed from the code that owns it and a mismatch fails the build; broken links, stale code paths and unreachable documents too                                                                                                                                                                                                                                                            |
| **Release pipeline**     | A tag builds candidates; a release is promoted only from a qualified, disposable-machine installer run ([ADR-215](docs/architecture/ADR-215-Self-Host-Installer.md)); multi-arch images on ghcr.io                                                                                                                                                                                                                                                    |

> Full details: [CI/CD documentation](docs/technical/CI_CD.md).

### Security

| Reference                                                                              | Concrete measure                                                                                                                                                                                                                                                                                                                                                                                                                          |
| -------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [GDPR / RGPD](https://eur-lex.europa.eu/eli/reg/2016/679)                              | PII filtering, data minimisation, full-account export and account deletion that also removes linked OAuth grants and transparency records ([privacy guide](docs/knowledge/15_privacy.md))                                                                                                                                                                                                                                                 |
| [EU AI Act](https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai) | The interface identifies LIA as AI; approval before mutation and separate records of actions, reads and decisions support transparency and traceability. Applicable duties still depend on the deployment and use case ([traceability boundaries](docs/technical/AI_ACT_TRACEABILITY.md))                                                                                                                                                 |
| OWASP Top 10                                                                           | XSS, SQL injection and CSRF safeguards; a global Redis-backed rate limit before routes; request bodies bounded before they are read, webhooks included                                                                                                                                                                                                                                                                                    |
| Prompt injection                                                                       | External content wrapped in safety markers, trust classified by data type rather than by producing tool, and a provenance that survives history compaction — a summary built from third-party text inherits its banner instead of promoting the claim to system authority                                                                                                                                                                 |
| SSRF & hostile text                                                                    | Every fetched URL is validated, then fetched on the very address the check resolved, one redirect hop at a time; text flatteners run in linear time on hostile input, held by growth and equivalence tests ([ADR-326](docs/architecture/ADR-326-Linear-Flatteners-And-Pinned-Fetches.md))                                                                                                                                                 |
| OAuth / PKCE                                                                           | PKCE S256, single-use state and issuer/identity checks; grouped Google/Microsoft consent shares grants only within the verified provider account ([ADR-302](docs/architecture/ADR-302-OAuth-Grant-Par-Compte-Et-Consentement-Groupe.md)); linking a federated identity never changes an account's status ([ADR-002](docs/architecture/ADR-002-BFF-Pattern-Authentication.md))                                                             |
| [MCP](https://modelcontextprotocol.io/) / plugins                                      | Model Context Protocol servers and apps, agentskills.io skills and Agent Plugins v1 packages use documented open interfaces, with separately reviewed trust and sandbox boundaries ([MCP](docs/technical/MCP_INTEGRATION.md), [plugins](docs/technical/PLUGINS_INTEGRATION.md))                                                                                                                                                           |
| Supply chain                                                                           | Hash-verified universal lockfiles and every build input pinned by digest, pip-audit on the full transitive tree, a weekly watch of each dependency's own advisories and end-of-life dates, a refresh that never moves a version backwards ([ADR-331](docs/architecture/ADR-331-Dependency-Watch-And-A-Refresh-That-Never-Goes-Back.md)), a CycloneDX SBOM per release                                                                     |
| Untrusted code                                                                         | Skill scripts execute in a throwaway container — no Docker socket, no network, read-only filesystem, unprivileged uid, all capabilities dropped — and no sandbox means no execution, never a weaker fallback; a script the assistant writes, or a skill's command that names its hosts, reaches the web only through one egress proxy holding the keys and the allowlist ([ADR-298](docs/architecture/ADR-298-Sandbox-Egress-Toolbox.md)) |

These references describe implemented controls, not a GDPR/AI Act legal opinion, OWASP or ISO certification, or a security-audit score. The [public 8.3/10 audit](docs/audit/README.md) measures 24 technical-quality areas against an ISO/IEC 25010:2023-inspired grid and explicitly excludes security.

**Reporting a vulnerability** — do not open a GitHub issue. Write to **liamyassistant@gmail.com** with a description, the steps to reproduce and the potential impact; we answer within 48 hours. Policy and supported versions: [SECURITY.md](SECURITY.md).

### Performance

Instrumentation and caching are in place — per-node message windowing, LLM context compaction with a threshold derived from the response model's window, prompt caching shaped for every provider mechanism (breakpoints, explicit markers, implicit prefixes) with an optional cross-turn cache for ReAct, asymmetric Gemini embeddings, parallel execution of independent domains, persistent HTTP pools — all instrumented in production. The perceived response time is dominated by the LLM call cascade (seconds to tens of seconds depending on the request and the hardware); that is the optimisation programme in progress. The [technical audit](docs/audit/README.md) scores performance 7.5/10: no sustained load campaign has been executed yet, and the figures will be published when one has.

---

## Documentation

| Entry point                                   | What it covers                                                                                                                                                                                                             |
| --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [GETTING_STARTED.md](docs/GETTING_STARTED.md) | Detailed installation guide                                                                                                                                                                                                |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md)       | Complete system architecture                                                                                                                                                                                               |
| [INDEX.md](docs/INDEX.md)                     | The full documentation map                                                                                                                                                                                                 |
| [Living maps](docs/maps/README.md)            | A functional map, a technical map and the illustrated history of every decision — interactive pages on the public site (`/maps`, six languages) and offline French documents, from one set of data checked on every commit |
| [CLAUDE.md](CLAUDE.md)                        | The engineering rulebook the AI works under — its systemic rules, each paid for by a measured defect                                                                                                                       |

| Domain                 | Documents                                                                                                                                                                                                                                                                            |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Agents & LLM**       | [ARCHITECTURE_LANGRAPH](docs/ARCHITECTURE_LANGRAPH.md) • [PLANNER](docs/technical/PLANNER.md) • [SEMANTIC_ROUTER](docs/technical/SEMANTIC_ROUTER.md) • [LLM_PROVIDERS](docs/technical/LLM_PROVIDERS.md)                                                                              |
| **HITL & registers**   | [HITL](docs/technical/HITL.md) • [AI_ACT_TRACEABILITY](docs/technical/AI_ACT_TRACEABILITY.md) • [PROVENANCE_AND_CAPABILITIES](docs/technical/PROVENANCE_AND_CAPABILITIES.md)                                                                                                         |
| **Voice & meetings**   | [VOICE](docs/technical/VOICE.md) • [VOICE_MODE](docs/technical/VOICE_MODE.md) • [MEETINGS](docs/technical/MEETINGS.md)                                                                                                                                                               |
| **Memory & knowledge** | [LONG_TERM_MEMORY](docs/technical/LONG_TERM_MEMORY.md) • [MEMORY_RESOLUTION](docs/technical/MEMORY_RESOLUTION.md) • [JOURNALS](docs/technical/JOURNALS.md) • [GUIDE_RAG_SPACES](docs/guides/GUIDE_RAG_SPACES.md)                                                                     |
| **Reach**              | [MCP_INTEGRATION](docs/technical/MCP_INTEGRATION.md) • [SKILLS_INTEGRATION](docs/technical/SKILLS_INTEGRATION.md) • [PLUGINS_INTEGRATION](docs/technical/PLUGINS_INTEGRATION.md) • [BROWSER_CONTROL](docs/technical/BROWSER_CONTROL.md) • [SUB_AGENTS](docs/technical/SUB_AGENTS.md) |
| **Initiative**         | [HEARTBEAT_AUTONOME](docs/technical/HEARTBEAT_AUTONOME.md) • [SCHEDULED_ACTIONS](docs/technical/SCHEDULED_ACTIONS.md) • [WORKBOARD](docs/technical/WORKBOARD.md) • [BRIEFING_DOMAIN](docs/technical/BRIEFING_DOMAIN.md)                                                              |
| **Channels & mobile**  | [CHANNELS_INTEGRATION](docs/technical/CHANNELS_INTEGRATION.md) • [GUIDE_TELEGRAM](docs/guides/GUIDE_TELEGRAM_INTEGRATION.md) • [GUIDE_MOBILE_ANDROID](docs/guides/GUIDE_MOBILE_ANDROID.md) • [GUIDE_MOBILE_IOS](docs/guides/GUIDE_MOBILE_IOS.md)                                     |
| **Security**           | [SECURITY](docs/technical/SECURITY.md) • [AUTHENTICATION](docs/technical/AUTHENTICATION.md) • [OAUTH](docs/technical/OAUTH.md) • [RATE_LIMITING](docs/technical/RATE_LIMITING.md)                                                                                                    |
| **Operations**         | [CI_CD](docs/technical/CI_CD.md) • [OBSERVABILITY_AGENTS](docs/technical/OBSERVABILITY_AGENTS.md) • [METRICS_REFERENCE](docs/technical/METRICS_REFERENCE.md) • [ALERTING](docs/technical/ALERTING.md) • [runbooks](docs/runbooks/)                                                   |
| **Costs**              | [LLM_PRICING_MANAGEMENT](docs/technical/LLM_PRICING_MANAGEMENT.md) • [GOOGLE_API_TRACKING](docs/technical/GOOGLE_API_TRACKING.md) • [USAGE_LIMITS](docs/technical/USAGE_LIMITS.md)                                                                                                   |

| Guide                                                       | Description                   |
| ----------------------------------------------------------- | ----------------------------- |
| [GUIDE_DEVELOPPEMENT](docs/guides/GUIDE_DEVELOPPEMENT.md)   | Complete development workflow |
| [GUIDE_AGENT_CREATION](docs/guides/GUIDE_AGENT_CREATION.md) | How to create a new agent     |
| [GUIDE_TOOL_CREATION](docs/guides/GUIDE_TOOL_CREATION.md)   | How to create a new tool      |
| [GUIDE_TESTING](docs/guides/GUIDE_TESTING.md)               | Testing strategy              |
| [GUIDE_DEBUGGING](docs/guides/GUIDE_DEBUGGING.md)           | LangGraph and log debugging   |
| [GUIDE_SELF_HOSTING](docs/guides/GUIDE_SELF_HOSTING.md)     | Production self-hosting       |

### Architecture Decision Records

347 ADR files (ADR-001 through ADR-348 — ADR-008 has no separate file) record every major architectural decision with its context, the alternatives and, increasingly, the production measurement that motivated it. Three to start with, and [the full index](docs/architecture/ADR_INDEX.md):

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
- **Rules that are not stylistic**: read the _Systemic Rules_ in [CLAUDE.md](CLAUDE.md) — each one closes a bug class measured in production, and a guard enforces most of them

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

Copyright (c) 2024-2026 LIA Contributors.

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
