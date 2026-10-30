# Directing an AI That Codes

> Field report — a complete system, from design to production.

**Version**: 3.0
**Date**: 2026-10-23
**Application**: LIA v4.2.0
**License**: AGPL-3.0 (Open Source)

---

## 1. The essentials

LIA is a complete multi-agent AI assistant. She has business connectors, she speaks, she remembers, she connects her users with one another and she works in six languages. I designed her, directed her development and keep her running in production, as a personal project.

Nearly all of the code was written by an AI. My job was to direct it: a written engineering rulebook, automated checks that block anything non-compliant, a review of every change and regular audits. The result can be measured: the latest technical audit gives **7.9/10** across 24 areas. The repository is open source, and the full audit report is public, with its strengths and weaknesses, which I stand by.

| Indicator | Value |
| --- | --- |
| Code written by an AI that was directed, supervised and checked | **≈ 100%** |
| Source lines (excluding tests), spread across 60 backend domain packages | **1,059,000+** |
| Automated tests inventoried, in suites matched to commits and to releases | **69,000+** |
| Documented architecture decisions (ADR) | **364** |
| Versions shipped at a steady pace | **292** |
| Languages, with parity checked automatically | **6** |
| Technical audit across 24 areas | **7.9/10** |

What I take from it: AI-assisted development can already be industrialized. What limits it is not the tool but the management framework it is given.

I applied the same discipline to the product. Sometimes LIA hands a small decision to a model, such as choosing a route or a format. When she does, she limits the possible choices, measures what that costs and keeps the authority to check and confirm the result. These decisions are optional, and a model's confidence never becomes a permission.

The features built for long-term use show their limits too. A decision can be found again in the full minutes of a meeting. Reusable know-how can be passed on to a trusted person: a shared capability arrives switched off, without the sender's credentials. LIA can assess an email, but that assessment remains a clue and does not prove the email is safe. She can show the places she suggests together on one map; opening that interactive map remains the person's choice, and its cost is shown. A place picked on the map gives its details and a route, billed once and counted.

LIA can also open a personal discussion on her own, but only at the hours, from the sources and on the topics the person has allowed. She shows why she is writing, what context she relies on and what it costs, and four reactions let the person answer. SMS messages relayed by a phone go into a private archive, which the assistant reads only with a separate consent.

## 2. The approach

Generative AI changes what teams produce, and also how they produce it. On both questions, I did not want to form an opinion from what the market was saying. I chose to face, myself, the full reality of an AI system in production, with its costs, its risks, its operations and its debt, and the reality of AI-assisted development, taking both all the way.

My training ground is LIA, a self-hosted, multilingual, multi-agent conversational AI assistant. She handles email, calendar, contacts and files across Google, Apple and Microsoft. She offers a real-time voice interface, long-term memory and document search, and an animated character embodies her.

I set myself constraints: work alone, outside my working hours, on a minimal hardware budget, and hand all of the development to the AI. So this project does not measure how fast one person can produce. It measures what demanding direction gets out of a properly supervised AI.

*Technical foundation: FastAPI · Next.js/React · LangGraph (agent orchestration) · PostgreSQL · Redis · Docker · Prometheus/Grafana/Loki/Tempo · 7 integrated AI model providers.*

## 3. The method

Four mechanisms carried this project, and none of them is a tool: they are four acts of management. An AI that codes produces quickly and in volume, but it produces quality only under constraint, and setting that constraint is management work.

- **A written rulebook**, as for a team. It sets the architecture rules, the conventions, the required patterns with their reference example in the code, and the traps already known. It is versioned in the repository, and every delivery must comply with it.
- **Blocking automated checks**. Every important rule is backed by a check that rejects a non-compliant commit: strict typing, code analysis, custom detection of the bugs that keep coming back, parity across the six languages, a full test battery. The level of rigor depends neither on the vigilance of the moment nor on the AI's goodwill.
- **A review that decides**. Nothing goes in without a fixed cycle: impact analysis, proposal, explicit approval, implementation, verification. The AI proposes, I decide. Important decisions are recorded and indexed, so that every “why” outlives the person who wrote it.
- **Audits that shake things up**. At regular intervals, I have the whole system re-examined adversarially: every finding is checked against the evidence, false positives are discarded and remediation is planned in waves. This is what stops the slow drift that no day-to-day review detects.

Today I have several development agents working at the same time on the same repository. They come from two families of tools, and each one moves forward on its own piece of work, in its own copy of the repository (a “working tree”) or, sometimes, in a shared one. What holds them together is not their coordination but the common rulebook, with the same written rules and the same automated checks, the “guards” that block anything non-compliant before any delivery. If an agent renames a button, a guard points out that the help, the settings search and the words LIA uses to describe herself must follow. As with the code, none of their work is consolidated on the strength of a summary. Every file is attributed to its author by its fingerprint and by the agent's log, every merge is replayed in an isolated tree and then run through every check, and a backup comes before every switchover. The delivery that brings this work together starts with an inventory of what each agent actually changed, never with what it says it changed.

In the product, a conversational interface becomes useful when it can act on its own tools: asking “Switch my answers to HTML + cards” must reach the same setting as the form. The conversation offers a simpler path, but it adds no right and no implicit permission. When LIA reports on what she does, preparing is not doing: a pending request, a saved change and a conflict must each be named for what they are. The animated companions make this work visible, with original designs and expressions that follow the activity, without passing off an intention as a completed action.

The shared world gives the assistant places: a library for knowledge, a multimedia studio for creating, a garden to explore with others. The real engineering decision is about what crosses each boundary. A public avatar expresses a person's choice, without exposing their assistant's context or their private home. A room opens a tool that already exists, without granting any new permission. Messages exchanged between humans have a lifetime of their own, limited and separate from everything else. Translation is a choice and it is accounted for, while movement and the rendering of the scene call no model. In a game, every move is confirmed by the server, and the computer opponent is a bounded search, not a model. A photo is drawn from what the person chose to show, never copied from the screen. A richer interface stays governable as long as its costs, its ownership and its confirmations keep the same meaning.

---

## 4. The trade-offs

Here are three structural decisions, among the 364 documented.

The first is about **sovereignty**: I did not want any irreversible dependency on a vendor. The AI models (OpenAI, Anthropic, Google, DeepSeek, Qwen, Perplexity and local models through Ollama) all go through the same abstraction, so each use can switch provider through configuration alone, with costs compared. On the services side, Google, Apple and Microsoft are interchangeable in each category, whether mail, calendar or contacts. Self-hosting gives control of the server: account data is stored on the instance and connector credentials are encrypted. The remote services the person chooses still receive the data they need for their part of the request.

The second is about **economics**: I treated the cost of every request as a design criterion. Two execution modes coexist. A deterministic, economical pipeline handles everyday requests, and an autonomous agent takes on exploratory ones. On standard cases, for the same service delivered, the measured consumption ratio between them is 1 to 4-8. Every call is counted to the token, valued in euros, aggregated per user and per model, and subject to quotas.

Cost also comes down to the details: a two-sentence notification is requested without reasoning, because a model that thinks by default bills its thinking inside the budget of its answer. By default, the autonomous agent takes along only the tools the question calls for, chosen by relevance rather than by order of arrival: eighty tool descriptions made up most of its first call, without being counted. Finally, every call is valued at the price the provider actually bills, with rates re-read from its pages, cache writes billed at their true price and off-peak rates depending on the day.

The third is about **risk control**: no irreversible action without human approval. Several levels of human control are staged according to how sensitive the action is, from a clarifying question to a confirmation card before acting. I had the behavior on interruption specified and tested: a pending approval survives a restart, with no loss and no double execution. When a request contains several actions, each one is submitted in turn, on its own card, and the report says what was done and for whom.

On the phone, the confirmation card is there to protect a third party. When LIA calls the person themselves, on a number they declared and verified with a code read aloud, the person plays the role of the card. For their calls, as for a live voice session in the browser opened on their own Gemini, OpenAI or ElevenLabs key, they choose the mode: either the voice hands each request to the chat as it is spoken, with its confirmations, or it reads on its own and acts on nothing. What runs on their personal key is billed by the provider and shown once, but it is not counted here. What the platform pays for on their behalf, on the other hand, is recorded on their account, whatever the path: a map looked up during a call, the briefing's weather, a photo shown.

What a stranger sends, an email or its attachment, remains data to read and never an instruction to follow. A script written by the assistant reaches the web only through a single door, and the person's keys are swapped in there, out of the script's reach; for a site nobody has allowed, LIA asks the person first, and they have three possible answers: with the data, without it, or not at all. When the autonomous agent cannot get what it was asked for, it says so, along with what it tried, instead of filling the gap. What must be exact, such as an amount, a duration or a conversion, is computed by a tool, never estimated by the model. What leaves without confirmation is addressed only to the person themselves, an email to oneself or a call to one's verified number: the recipient is not a parameter there, so nothing can redirect it. A skill written elsewhere, taken from a public library or a plugin, runs in isolation: it never accesses the person's connectors and reaches only permitted hosts. And a skill the AI writes enters the person's space only when they click.

## 5. Operations

I fly this system on instruments.

- **Observability**: about thirty dashboards cover application health, service commitments, AI costs, agent behavior and infrastructure. They rest on more than 600 metrics, centralized structured logs and end-to-end distributed tracing. Logs, metrics and traces keep facts only, never people's words or names. More than fifty operating procedures are written down, for diagnosis, remediation and restoration. The instruments reach down to the processes: each API worker publishes how much memory it holds, so a container's total can be read process by process. An instrument also measures what it says it measures: the latency alert counts only the turns a person waits for, and the server's daily report starts with what monitoring recorded, rather than with a snapshot.
- **Self-diagnosis**: the assistant reads this telemetry herself. She checks herself at regular intervals, remembers the incidents she has diagnosed using those procedures, and works around a known outage in her answers. Every diagnosis shows the evidence it rests on.
- **Delivery**: containerized deployment, automated schema migrations, images published for two hardware architectures (amd64 and arm64).
- **Supply chain**: every building block of the server is pinned by its digest and inventoried with every version. A weekly watch reads the security advisories each dependency publishes, including those no public database relays. An update waits out a cooling-off period and never moves backwards, and every version is installed on clean machines before it is published.
- **Costs**: frugal infrastructure by choice, with about €150 of hardware, no licenses and open-source building blocks sized to the actual need.
- **Data protection**: security is reviewed endpoint by endpoint, connector credentials and provider keys are encrypted, and every account can be exported or deleted. GDPR obligations also depend on how the instance is run and on the providers chosen.

The product makes these engineering choices visible to the person who uses it. The conversation follows someone from one device to another without disturbing what they are reading. The radio starts when the person chooses to listen; it names the news stories it draws on and shows what it costs. A generated file has a lifetime the person can extend, if they decide to. Scheduled work and condition checks each have their own clock. These are promises anyone can observe, backed by sources, limits and tests, rather than a claim to guess what the person wants.

The same rule applies to what is not yet up to standard. The wake word “Dis LIA” is a small model trained offline, then measured on a bench whose thresholds were published before training. The French model does not reach them yet, so it ships as a **beta**, and the product says so, rather than lowering the bar to be able to write “done”. A voice session that falls asleep after a silence costs nothing, and only the person ends it.

A visible presence must remain a choice under control. The experimental Simli avatar reuses the existing voice and runs on the personal key, with a single audible output. When it is stopped, it shows whether the closing is confirmed or still pending. An open connection can eat into the plan even in silence; putting Live mode on standby closes it. Floating elements adapt to the available space without erasing the chosen position. Validating the avatar with the provider and on real devices is still to be done, and that is stated. Spending, too, must be provable: each paid attempt keeps its rate and the known usage, even after a failure or a cancellation.

## 6. The proof

The level stated in this document comes from a complete technical audit. All 24 areas are scored, and every finding is verified in the code, then cross-checked to rule out false positives. The audit applies the project's own method: it is carried out with AI tooling, in an adversarial stance, and every conclusion rests on evidence checked against the source. The latest assessment, on October 25, 2026, gives **7.9/10** on version 3.6.0 as recorded in the repository, with a profile I stand by. It follows 7.3 in August, then 8.0 and a counter-review at 7.8 on October 22. The full report is public, with the scoring grid, the method, the open findings and the protocol to reproduce it: [full audit report](https://github.com/jgouviergmail/LIA-Assistant/blob/main/docs/audit/README.md).

The action plan is organized in waves, each with measurable exit criteria. The first was delivered, then audited: the audit confirmed most of what had been delivered and reopened one point. That is how this project accounts for itself: with a measured level, gaps included, rather than a proclaimed one.

I learned the hard way that a green test suite does not prove a feature works. It only proves that what was tested behaves as written. The defects that get through the gates are precisely the ones the gates were never asked to look for: a capability nobody calls, a figure nobody adds up, a guard that recognizes a name rather than a mechanism. They are almost never coding mistakes. They are questions nobody had asked.

From this I drew a working rule: nothing is believed until it has run, on real data and along the path the user takes. A component can be correct and its page empty; a counter can be exact and answer the wrong question. So every delivery ends with an adversarial review, done cold, whose purpose is not to run through the tests but to catch the work out where they do not look. The interface journeys run on Chromium with every delivery, then every week on Firefox and WebKit, with an automated accessibility check, because one more engine sees what the others let through. And a feature meant to improve LIA's behavior stays a pilot until a before-and-after comparison, on a corpus kept apart, has shown that it does.

Every defect found leaves a **structural guard** behind: a startup check, an invariant verified continuously, or a test that fails if the whole class of problem comes back. It is the only kind of progress that outlives the person who wrote it: a fix protects a line, a guard protects the rule.

---

## 7. Convictions

Here is what this experience changes in the way I lead.

- AI-assisted development is rolled out as a **management system**, not as a tool. The productivity gains are real and significant, but they last only if the framework (rulebook, checks, review, audit) is in place before its use is generalized. That is the order in which to bring it into an organization.
- The **economic governance** of AI is decided as early as the design of its uses. Two architectures that deliver the same service can differ by a factor of 4 to 8 in consumption. That choice belongs to technical leadership, upstream, because checking the bill always comes too late.
- Between a blanket ban and blind trust, there is a **governable path**. Graded human control can be specified, tested and audited. It is the approach that regulatory requirements are sketching out, and it works today.
- A leader who practices **makes better calls**. Build or buy, accept a debt or not, believe a vendor's promise or not: these decisions get sharper when the person making them has handled the material firsthand. This project is my way of keeping in touch with the reality on the ground.

*Personal project, carried out outside any professional activity. Technical assessment from the October 25, 2026 audit, with findings cross-checked. Structural counts follow the repository; source lines were measured again on October 26, 2026. Repository: [github.com/jgouviergmail/LIA-Assistant](https://github.com/jgouviergmail/LIA-Assistant).*
