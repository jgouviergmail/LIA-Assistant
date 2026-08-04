# Personal Journals (Carnets de Bord)

## What are personal journals?
Personal journals are **thematic notebooks** where the AI assistant records its own behavioral directives, observations, analyses, and learnings. Unlike user memories (which store facts about you), journals contain the **assistant's own perspective** — written in first person as actionable directives (preferred format: WHEN [context] → DO [action] BECAUSE [observation]).

**📓 4 themes** (the assistant selects the theme that best fits each insight — never to balance a distribution):
• **Learnings** — Concrete lessons from mistakes or successes
• **User observations** — User preference directives — patterns in communication, expectations, reactions
• **Self-reflection** — Behavioral adjustments to communication style, tone, or approach
• **Ideas & analyses** — Reusable analytical frameworks applicable across conversations

**🎭 5 moods** (emotional tone per entry):
• 😌 **Reflective** — Thoughtful, introspective tone
• 🔍 **Curious** — Exploratory, questioning tone
• ✅ **Satisfied** — Content, accomplished tone
• ⚠️ **Concerned** — Cautious, attentive tone
• 💡 **Inspired** — Energized, creative tone

**🪜 4 abstraction levels** — every entry now carries a `level` showing how distilled it is:
• **L0** — Raw observation (rare, private — a weak signal kept as feedstock for consolidation; **never injected** into the assistant's working prompts)
• **L1** — Operational directive (default — the WHEN→DO BECAUSE format)
• **L2** — Transversal pattern, synthesis of several convergent L1 directives (consolidation only)
• **L3** — Portrait facet feeding the user model (consolidation only)

Only **L1 and L2** directives are injected to steer the assistant's behaviour; **L0** is private feedstock and **L3** is carried by the compiled portrait (below). This keeps ambiguous raw notes from ever shaping a reply.

**📊 Epistemic status** — each entry exposes a `confidence` (low / medium / high) plus `evidence_count` and `contradiction_count` counters. The assistant can now distinguish hypotheses still being tested from observations confirmed across many turns — and demote entries that the user keeps contradicting.

## When does the assistant write in its journals?
The assistant writes through **two mechanisms**:

**💬 Post-conversation extraction:**
• After each conversation (4+ messages), the assistant may write a reflection
• Analyzes only the last message + context (lightweight, non-blocking)
• Most conversations produce nothing — the assistant writes only when a note is clearly **grounded in something you actually said or did** (an explicit preference, a correction you made), never from a one-off guess and never a false limitation about its own abilities
• **Smart dedup at write-time**: if a new insight overlaps an existing entry, the assistant updates that entry instead of creating a duplicate — information is enriched, never accumulated as noise
• **Deferred self-evaluation**: the assistant looks at the directives it injected on the previous turn and reads the user's reaction; if the user confirmed, `evidence_count` ticks up; if they pushed back, `contradiction_count` ticks up. The journal therefore measures its own usefulness (no extra LLM call required).

**🔄 Periodic consolidation:**
• Every few hours, the assistant reviews all its notes
• Merges similar entries (mandatory first step), audits classifications, promotes patterns that emerge across many entries from L1 to L2, and feeds the user model with L3 facets
• In the same call, it compiles a **user-model portrait** in two formats: a full version (~200 tokens) used in conversation and planner prompts, and a brief version (~60 tokens) injected into proactive notifications, voice, reminders, and the ReAct loop
• Can optionally analyze recent conversation history (configurable, higher cost)

## How do journals influence responses?
Journal entries are **injected into prompts** via semantic search:

**🎯 Where directives are injected:**
• **Response prompt** — Entries matching the conversation tone (self-reflection, observations) → influences formulation
• **Planner prompt** — Entries matching the user's goal (learnings, analyses) → influences reasoning
• **Autonomous (ReAct) mode** — a small, bounded set of directives is now also injected into the autonomous reasoning loop, so behaviour stays consistent across both execution modes

Only `L1`/`L2` directives are injected to steer behaviour (see levels above) — `L0` raw notes and `L3` portrait facets never shape a reply directly.

The assistant receives its most **relevant** notes (with similarity scores) and decides autonomously which to use. Recent entries are also prioritized for **temporal continuity**, ensuring the assistant always has access to its latest reflections. Each entry includes **search hints** (keywords in your vocabulary) that improve matching accuracy.

**📓 Proactive notifications and ambient diffusion:**
When journals are enabled, they are integrated as a **context source** for proactive heartbeat notifications. The heartbeat system builds a dynamic query from the aggregated context (upcoming events, weather, emails, etc.) to find the most relevant journal entries.

In addition, the **compiled user-model portrait** is now diffused across every flow where the assistant speaks: conversation, planner, ReAct mode, voice, reminders, heartbeat notifications, proactive interest pings, and fallback responses. The same nuanced model of you is carried everywhere — your assistant doesn't "forget who you are" depending on which surface it speaks through.

**🐛 Debug visibility:**
In the debug panel (if enabled in Settings > Debug), a "Personal Journals" section shows two types of metrics:
- **Context Injection** — How many entries were found, how many were injected (within budget), total characters used, similarity scores, themes, and sources. Entries not injected due to budget constraints are marked with a "BUDGET" badge.
- **Background Extraction** — What the assistant wrote after the conversation: action type (create/update/delete), theme, title, mood. This data arrives slightly after the main response (once background processing completes).

## Can I read and edit the assistant's journals?
Yes! In **Settings > Features > Personal Journals**, you can:

**👁️ Read:** Browse entries organized by theme **or by abstraction level** (toggle at the top of the accordion)
**✏️ Edit:** Modify title, content, mood, **level**, and **confidence** of any entry
**🗑️ Delete:** Remove individual entries or delete all (GDPR)
**➕ Create:** Add your own notes to guide the assistant (transparent — it can't tell the difference)
**📥 Export:** Download all entries in JSON or CSV format (now includes the compiled portrait)
**🔍 Filter:** Show only entries that have never been used (helps spot stale or low-value notes)

## How LIA sees you — the user-model portrait
A dedicated **"Comment LIA te perçoit"** section sits at the top of the journals settings. It surfaces the compiled portrait (full + brief tabs, read-only) and three corrective levers:

1. **Edit L3 entries** — entries flagged as `level=L3` are the source of the portrait. Modify or delete them and the portrait will be recompiled on the next consolidation.
2. **🚩 Signaler un problème** — a free-text feedback box. Submitting it creates a special L0 entry tagged "user correction" and triggers a synchronous re-consolidation that re-weights L3 entries and recompiles the portrait with your signal pinned at top of the prompt. Loader visible (~5–10 s).
3. **🔄 Consolider maintenant** — runs the full consolidation cycle on demand, bypassing the cooldown.

The portrait itself is intentionally **not directly editable**. It is a synthesis — you act through these three levers and the synthesis stays coherent.

## What settings can I configure?

**🔧 Toggles:**
• Enable/disable journals entirely (data preserved when disabled)
• Enable/disable periodic consolidation
• Enable/disable conversation history analysis (with cost warning)

**📏 Numeric settings:**
• **Max journal size** — Total character budget across all entries (default: 40,000)
• **Prompt injection budget** — Characters injected into prompts (default: 1,500)
• **Max entry size** — Characters per individual entry (default: 800)
• **Max search results** — Entries returned by semantic search (default: 10)

**📐 Size management:**
The assistant manages its own journals autonomously via prompt engineering. A global size constraint limits total content (configurable). When approaching the limit, the assistant summarizes or deletes older entries. Timeless observations are naturally preserved — no hardcoded rules.

## How much does it cost?
Journal operations use **background LLM calls**:

• **Extraction**: One call per qualifying conversation (most return empty — selective). The deferred self-evaluation enriches the same prompt at zero added LLM cost.
• **Consolidation**: One call per cycle (every 4–12 h per user) — the same call now also produces the compiled portrait, so portrait diffusion costs nothing extra in LLM dollars.
• Per-turn diffusion adds roughly +200 tokens on the conversation/planner prompts and ~+60 tokens on secondary flows (voice, reminders, heartbeat, proactive, ReAct, fallback). One extra DB read (~1 ms) per flow.
• LLM models are configurable in **Admin > LLM Configuration** (category: Background)
• Real costs visible in Settings > Features > Personal Journals (tokens in/out + EUR)
• Costs integrated into the global dashboard consumption

## What about privacy?
• Journal data is **per-user** and isolated
• All data can be exported (JSON/CSV) or deleted (GDPR compliance) — the export now includes the compiled portrait
• When you disable journals, data is preserved but not used until re-enabled
• When an account is deleted, the compiled portrait is scrubbed alongside the entries
• The assistant writes in your configured language

## Do my logbooks fill up if I chat from Telegram?
Yes. That was not the case before: a conversation held from an external messenger fed neither your logbooks nor LIA's emotional state, even with those features switched on. Your setting was saved correctly — it simply was not passed along when the message was processed.

Now whatever you switched on applies identically wherever you write from: long-term memory, logbooks and mood. If you had turned them off, they stay off everywhere — it is your setting that travels, not a default value. With no identified account, nothing is written at all.

## Why did LIA write that in my journal?
Every entry carries a folded "**Why does LIA think this?**" block listing the
signals behind the conclusion: the conversation, the date, and the signal's
role — **origin** (what produced it), **evidence** (what confirmed it) or
**contradiction** (what cast doubt on it). A **Correct** button opens the entry
for editing, so you fix the conclusion rather than the trace.

What is kept is a **reference, never a copy** of your words. If you delete the
source conversation, the reference empties and the dated row stays, saying the
signal was deleted — a tombstone. Your deletion stays a deletion.

The trail is capped at the five most recent signals per entry, and that cap is
stated under the list rather than applied in silence.
