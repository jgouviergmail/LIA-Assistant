# LIA — The AI Assistant That Belongs to You

> **Your Life. Your AI. Your Rules.**

**Version**: 7.0
**Date**: 2026-10-23
**Application**: LIA v4.2.0
**License**: AGPL-3.0 (Open Source)

---

## Table of Contents

1. [Why LIA](#1-why-lia)
2. [What LIA does for you](#2-what-lia-does-for-you)
3. [At home, for your loved ones](#3-at-home-for-your-loved-ones)
4. [Simple to administer](#4-simple-to-administer)
5. [Nothing hidden](#5-nothing-hidden)
6. [An assistant who knows you](#6-an-assistant-who-knows-you)
7. [She acts, you decide](#7-she-acts-you-decide)
8. [Open](#8-open)
9. [What LIA is not, and where she is going](#9-what-lia-is-not-and-where-she-is-going)

---

## 1. Why LIA

ChatGPT, Gemini, Copilot or Claude can already act for you: read your emails, fill your calendar, search the web. But your conversations live on their servers, you cannot see what happens between your question and the answer, and the day you leave, what they know about you stays with them.

LIA takes a different path. This is a personal assistant you install on your server, that you can understand from end to end and that you keep under your control. She is not one more AI model: she puts the models you choose to work and organizes your services, your memory and your rules around them.

The mechanics are explained in [the technical guide](/en/how). How the code was written, by an AI directed and checked by a human, is told in the [field report](/en/story).

## 2. What LIA does for you

You talk to her normally, in writing or by voice. The interface exists in six languages (French, English, German, Spanish, Italian, Chinese) and your dictation is transcribed in your account's language. Some twenty specialized agents share the work: your personal data, the web, creation, the smart home, browsing websites and anticipation.

A switch in the chat chooses how she reasons. **Pipeline** mode, the default, prepares every step, checks them, then runs them in parallel: it is predictable and uses 4 to 8 times fewer tokens. **ReAct** mode moves step by step, more autonomous and more costly, for an open-ended search; when a step needs a real calculation, it writes a few lines of Python and runs them in a locked sandbox, which reaches the web only through a single proxy and without your keys ([privacy](/en/faq#faq-privacy), [the journey of a message](/en/how#pipeline)).

If you choose the **cards** display (the other two modes are plain HTML and Markdown), answers that carry data arrive this way: photos of a place, the weather slot by slot, a route, a preview of a document. A card shows what the source provided, inventing nothing, and replying to an email from its card prepares the request without sending anything.

### Your services

You ask LIA to move your Thursday appointment: she prepares the change and shows it to you before sending it. She reads, searches, summarizes, drafts, sends and forwards your emails (Gmail, Outlook, Apple Mail), reads their attachments, including a photo or a scan, and manages your mailbox drafts, which she sends only after you confirm. She keeps your calendar and your contacts at Google, Microsoft or Apple, your tasks at Google or Microsoft, reads your Drive files and writes there only with your consent, and turns on your Philips Hue lights.

Without configuring anything, you get Wikipedia, web page reading, nearby places with opening hours and reviews, five-day weather with air quality and pollen, and routes on foot, by bike, by car or by public transport ([connectors](/en/faq#faq-connectors)). With your own keys, web search also cross-checks Brave Search and Perplexity, and cites its sources. LIA can also browse a site for you, click, fill in a form.

### Voice

You hold down the microphone, or you say "Dis LIA" to talk hands-free. This wake word is recognized on your device, and nothing leaves before it is heard; for now it exists only in French, in beta. "LIA, stop" cuts her voice. Your dictation is transcribed on your server or by a remote engine, depending on your setting.

**Live mode** opens a real-time voice conversation with your own Gemini Live, GPT-Live or ElevenLabs key. The voice carries the conversation and hands each request to LIA, who handles it like an ordinary message; in Live direct, the voice reads your data without acting. A silence puts the session on standby without billing anything, and you are the one who ends it. An experimental talking avatar can accompany the voice with your own Simli key; as long as its connection stays open, silences are billed too. What runs on your own keys is shown to you, but LIA neither records nor counts it ([voice](/en/faq#faq-voice_mode)).

### Create and keep

LIA creates and edits images with the model the administrator chose, without moving to an option more expensive than your preferences. As an option, she enriches your description, and you find an image again by asking her for it ([images](/en/faq#faq-image_generation)). She produces real files (CSV, Excel, Word, PowerPoint, PDF), built by a local engine and delivered with their expiry date, Excalidraw diagrams, and she reads the photos and PDFs you attach. MCP apps display their forms directly in the chat.

What she produces, you keep, send by email in one click, share with a person connected to your instance when it is an image, or let expire. A kept answer leaves the conversation with your request and its date, and joins a knowledge space where LIA will find it weeks later.

### Taking the initiative

If you allow it, LIA does more than wait. She writes to you when your calendar, the weather, your tasks, your emails or your interests warrant it, and she can start a personal conversation on her own. At the end of a meeting, she asks you how it went. When your mailbox or your calendar changes, she can react within minutes, and "Watch" keeps an eye out for an expected email until it arrives. If rain is forecast for Saturday, she looks at your outdoor activities. She remembers what you really care about, and a topic you turn down does not come back.

You hand her a ticket: she takes it at her own pace and gives you back a result to accept. For a complex task, she delegates to sub-agents working in parallel. Routines and reminders follow rich rhythms (every other Tuesday, the second Tuesday of the month, until a given date), and a week view shows what actually happened ([initiative](/en/how#proactivity)).

### Other people

LIA places a real call on your behalf, to the garage or to a friend, and brings you back a written summary. She first tells you who she is calling and why, and waits for your go-ahead. With someone else, she accepts no commitment in your name, reveals of your calendar only whether you are free, and keeps only a short summary that expires. She can also call you, on a number you have verified, and then nothing is restricted: on the line you have your data and all her functions, with actions still confirmed as in the chat. This mode exists only if the phone provider can reach your instance ([telephony](/en/faq#faq-telephony)).

On the same instance, two connected people see their assistants talk to each other: you approve the exact message, the other assistant passes it on with its own personality, and yours confirms delivery. Each connection opens only the shares you chose, read-only. You find someone only by their exact identity, a block stays silent (the other person gets the same answer as a stranger), and relayed messages are erased after thirty days. The **Relations** page gathers, for each person, the commitments, calls, memories and messages, with a synthesis at the top, without collecting anything new. You are the one who merges two identities, for example "Dad" and a phone number, reversibly and without writing anything into your sources.

Your phone also becomes a meeting recorder. When you stop, LIA transcribes and writes minutes in the format that fits, tells you which one and why, and sends them to the chat, as a PDF and by email, then files them in a "Meetings" space where you will find what was decided. A dropout costs only a few seconds of audio, a recording made elsewhere can be imported, and the transcription can stay entirely on your server.

### And more

A personal radio, started whenever you like, blends your day with sourced news and shows what it spends ([radio](/en/faq#faq-radio)).

Your phone, iPhone or Android, or any system able to send data as JSON can also pass LIA your text messages, your step count and your heart rate, each through a dedicated, revocable token. The text messages join a private, encrypted archive that she reads only with a separate permission, never keeping access codes. The health measurements stay with you, where you erase them whenever you like; their use by the assistant is off by default and, when on, passes her only a factual summary, with no medical diagnosis at all.

The conversation keeps up with your other devices without reloading the page.

## 3. At home, for your loved ones

LIA is a server you install once and share with your family, your friends or your team. Each account has its profile, its language, its connectors, its private documents and its own relationship with the assistant. Memory and journals are kept separate from one account to the next, and an account opens only with the administrator's consent: signing in with Google proves an address, not an approval ([privacy](/en/faq#faq-privacy)). Everyone sees their usage in real time.

A Raspberry Pi 5, a computer costing about 80 euros, is enough for the whole family: LIA runs on one in production day and night, monitoring included. A NAS, a small rented server or a company machine work too. A local AI model can fill any text role, from conversation to background tasks, and that choice is changed role by role, without redeploying.

Your data lives in your server's database. You export it (secrets excluded), back it up or ask for its deletion, and your connected devices can be revoked. Your location is kept only if you choose so, with no history. An email or a web page arrives labeled as material to analyze, not as an order to follow. The server logs keep numbers and codes, not your content, with one exception: the error message of an outside service in an unknown format can still quote a fragment of it. One limit to know: a remote model receives the data it needs for its part of the request.

On the phone, a single app per store serves as a window onto your server. You enter its address once, and on Android its notifications do not go through the publisher; on iOS, a minimal relay wakes the phone with a fixed sentence ([self-hosting](/en/faq#faq-self_hosting)).

**LIA World** gives the instance a shared house and garden. You stroll there with your avatar, you meet the others, you play at an arcade cabinet, you sit at a table where LIA brings you your dashboard. Your home, your documents and your assistant stay private, and a room of the world opens the same functions, with the same rights and confirmations, as the app ([LIA World](/en/faq#faq-world)).

## 4. Simple to administer

A guided installer (`./install.sh`) asks a few questions, in French or English, creates the administrator account without writing any secret in clear text, checks that everything really works, and picks up where it left off if a step fails. Each step is described in a step-by-step guide. The first setup still takes a bit of time and some technical basics. An update follows a written procedure that starts with a backup, because there is no going back once the migrations are applied ([self-hosting](/en/faq#faq-self_hosting)).

After that, everything is set in the web interface, with no terminal or configuration file, on a computer, tablet or phone ([getting started](/en/faq#faq-getting_started)). A full assistant should be as simple to use as a consumer app. Everyone has their own settings space, with a search that understands your language: connect Google or Microsoft in one authorization ([connectors](/en/faq#faq-connectors)), choose LIA's personality (teacher, friend, coach, poet…) and her voices, adjust the appearance, decide what she learns and when she reaches out to you, add your MCP servers, your skills and your knowledge spaces, which can follow a Drive folder or a Gmail label. You also choose your exchange rhythm, frequent or occasional, so that LIA makes the most of the provider's cache.

You can also set LIA up by talking to her: "Switch my answers to cards". A read or a small reversible setting happens right away; a creation, a deletion or a sensitive change keeps its confirmation. A password or a key goes through your browser, not through the chat, and a command bypasses no protection ([privacy](/en/faq#faq-privacy)). Then LIA says what actually happened, including a partial result or a conflict, without claiming to know every internal effect of a tool.

The administrator has their own tab. They open accounts, see what each person uses, set per-person limits (tokens, messages, cost) and a daily budget for the whole instance. They turn each function on or off without redeploying, and turning a function off stops the capability without erasing what exists: without memory, LIA stops learning, but what she knows stays readable. They choose the providers, one model per role and its depth of reasoning, with keys stored encrypted, and keep the price grid, which they can edit in Excel. They also manage the instance's personalities, skills, FAQ and speech synthesis; cloning a voice first requires a consent attestation recorded in the audit log. LIA, for her part, monitors her own health, diagnoses her incidents and alerts the administrator, who can also question their server in natural language from the chat.

Accessibility targets WCAG 2.2 level AA, color does not carry meaning on its own, and automated checks complement manual evaluation without replacing it.

## 5. Nothing hidden

You see which models are called, how many tokens, at what cost, and why a given decision was made. Every message shows its cost in euros, a folded line under each answer unfolds what actually happened, and when one of your MCP servers is slow to get ready, LIA names it instead of keeping you waiting in silence. If the administrator turns it on, a debug panel shows the plan, each tool and each model call live. No subscription hiding the costs: you can put an economical model where it is enough, and LIA optimizes what she consumes on her own. Everything the platform pays for you, a call, a live session or speech synthesis, counts toward your usage, at the price the provider really charges. Your feedback on an answer (👍 or 👎) stays in your database, with no third-party analytics.

LIA does not tell you something is done when her tools refused it, and what a screen states about your data is exact or absent. Every announced protection is backed by a test that fails if it disappears. The full technical audit, weak points included, is public along with its protocol, and the FAQ has a section for every function.

What LIA concludes about you, you correct. Memories, journals and interests can be reread, corrected or deleted, and the correction applies everywhere. LIA keeps a pointer to what led her to a conclusion, not a copy, so a deleted conversation does not come back anywhere. What she thinks she knows about your rhythm can be inspected, paused or deleted in a habits panel, which stays off until you turn it on, and the routines she suggests wait for your approval. A rule drawn from your instructions ("answer more briefly") becomes a memory you can edit.

Finally, LIA keeps three **registers**: what she did for you, what she consulted ("your calendar", without what was searched) and each exchange. What she undertakes on her own has its own tab. An action is recorded before it happens and closed only on a real result. The registers can be read as charts, exported in full and sealed with hashes you verify yourself, and LIA answers from them when you ask her what she has done ([the registers](/en/faq#faq-registers)). With the parameters sent to the models and the register's gaps, that makes five forms of evidence. The European AI Act does not automatically classify a personal assistant among high-risk systems: this evidence is a choice of transparency, not a certification.

## 6. An assistant who knows you

Beyond the facts, LIA builds a psychological understanding of you. Each memory carries an emotional weight and an importance, and you can view, pin, correct or delete everything, or turn off automatic extraction.

The **Psyche Engine** gives her an inner state that evolves with every exchange, where the big assistants keep a fixed personality. The relationship deepens, and her emotions show without being stated: a vocabulary that warms up, sentences that shorten under tension, humor when the exchange is light. You adjust her character traits. She also learns, domain by domain and on an experimental basis, where she is reliable, from evidence and not from her own grade; where evidence is lacking, she checks, asks, or states her limit. Outside the chat, an animated companion stays by your side on the dashboard, where you placed it.

She keeps her own **journals** in the first person, and from these notebooks comes a portrait of you that goes with her wherever she speaks. You read them, edit them, flag an error or start a consolidation; the portrait itself cannot be edited directly, so that it stays coherent. When a painful memory comes up, she switches to protective mode: no jokes, no minimizing. And if you ask her what she can do, she answers from a knowledge base about her own functions ([memory](/en/how#memory)).

## 7. She acts, you decide

Before a sensitive action, LIA submits it to you. What you approve is exactly what will be executed, even after several edits, and the confirmation shows everything that is about to go out. Faced with an action she is not allowed to do alone, she asks you on the ticket; a routine running with nobody in front of the screen refuses the action and says so. A skill's code runs in a disposable container, with no access to your files or your keys, and no network beyond the authorized hosts.

She sticks to what she actually obtained. The answer is based on the tools' real results, information that cannot be found is reported as missing, and a failure is named along with the service at fault. Calculations, durations between two dates and currency conversions go through exact tools.

A question keeps being processed if you close the tab, and the stop button interrupts it within a second. The database is backed up every night and restoring it is actually tested; the off-site copy and the attachments remain for the operator to plan. Full monitoring has been part of the architecture from the start; its metrics contain neither names nor searches, and every building block of the server is pinned by its digest ([privacy](/en/faq#faq-privacy), [observing and measuring](/en/how#observability)).

The operator can hand a few precise decisions to a dedicated engine, such as choosing the format of meeting minutes. When this engine is unsure, the task goes back to the usual processing, permissions stay within LIA, and each use is visible and can be withdrawn.

## 8. Open

LIA works with OpenAI, Anthropic, Google, DeepSeek, Perplexity, Qwen and, for local models, Ollama. You mix them role by role, and if one changes its prices or gets worse, you switch right away ([the models](/en/how#llm)).

She speaks open, public standards rather than an in-house protocol, and her architecture is built to welcome other connectors, channels and providers. Through **MCP**, you plug in external tools without writing code. A plugin in the Agent Plugins format installs and uninstalls cleanly. **Skills** in the agentskills.io format add know-how written in natural language; a generator helps you create them, a skill installs from an https address or the skills.sh library, and it can display a small app in the chat or hand you files. A skill from elsewhere works apart, without touching your connectors, and what you build in this ecosystem follows you. A trusted connection can pass you a skill or a plugin: you receive a disabled copy, without its credentials, and enabling it commits you as if you had created it.

Your accounts connect through OAuth 2.1 without LIA knowing their password, and a passkey signs you in with no password at all. Each release publishes the exact inventory of what it contains and is installed on clean machines before it is published ([security](/en/faq#faq-privacy)). Every architecture decision is written down and filed on [the maps](/en/maps). The code is under AGPL-3.0: you can audit it, modify it, and it must stay open.

You find LIA in the browser, in the mobile app with its push notifications, and on Telegram, where confirmations are made with buttons and where she also answers your voice messages. The same memory follows you everywhere.

## 9. What LIA is not, and where she is going

LIA is not a competitor to the cloud giants. For chatting, a model used in its own app will probably be smoother. She is not an artificial general intelligence, but a practical and relational intelligence, serving one person. Her protections do not on their own guarantee an installation's GDPR compliance, which also depends on how it is run, and the models' diagnostic traces, which are optional, can keep context: they require explicit configuration.

What interests her is the long run. Memory, journals, learning and the Psyche Engine combine so that, month after month, LIA understands you better and better. She exists because an assistant that was truly yours was missing.
