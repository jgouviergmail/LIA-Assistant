# Personal Journals (Carnets de Bord)

## What are personal journals?
Personal journals are **thematic notebooks** where the AI assistant records its own reflections, observations, analyses, and learnings. Unlike user memories (which store facts about you), journals contain the **assistant's own perspective** — written in first person, colored by its active personality.

**📓 4 themes:**
• **Self-reflection** — Thoughts about its own behavior, style, and growth
• **User observations** — Patterns in your communication, preferences (complementary to memories)
• **Ideas & analyses** — Creative ideas, analytical frameworks, hypotheses
• **Learnings** — Lessons from interactions, mistakes, successes

**🎭 5 moods** (emotional tone per entry):
• 😌 **Reflective** — Thoughtful, introspective tone
• 🔍 **Curious** — Exploratory, questioning tone
• ✅ **Satisfied** — Content, accomplished tone
• ⚠️ **Concerned** — Cautious, attentive tone
• 💡 **Inspired** — Energized, creative tone

## When does the assistant write in its journals?
The assistant writes through **two mechanisms**:

**💬 Post-conversation extraction:**
• After each conversation (4+ messages), the assistant may write a reflection
• Analyzes only the last message + context (lightweight, non-blocking)
• Most conversations produce nothing — the assistant is selective

**🔄 Periodic consolidation:**
• Every few hours, the assistant reviews all its notes
• Merges similar entries, summarizes verbose ones, removes obsolete observations
• Can optionally analyze recent conversation history (configurable, higher cost)

## How do journals influence responses?
Journal entries are **injected into prompts** via semantic search:

**🎯 Two distinct injections:**
• **Response prompt** — Entries matching the conversation tone (self-reflection, observations) → influences formulation
• **Planner prompt** — Entries matching the user's goal (learnings, analyses) → influences reasoning

The assistant receives its most **relevant** notes (with similarity scores) and decides autonomously which to use. Recent entries are also prioritized for **temporal continuity**, ensuring the assistant always has access to its latest reflections. Each entry includes **search hints** (keywords in your vocabulary) that improve matching accuracy.

**📓 Proactive notifications:**
When journals are enabled, they are also integrated as a **context source** for proactive heartbeat notifications. The heartbeat system builds a dynamic query from the aggregated context (upcoming events, weather, emails, etc.) to find the most relevant journal entries, allowing the assistant to personalize notification tone and content based on its own observations.

**🐛 Debug visibility:**
In the debug panel (if enabled in Settings > Debug), a "Personal Journals" section shows two types of metrics:
- **Context Injection** — How many entries were found, how many were injected (within budget), total characters used, similarity scores, themes, and sources. Entries not injected due to budget constraints are marked with a "BUDGET" badge.
- **Background Extraction** — What the assistant wrote after the conversation: action type (create/update/delete), theme, title, mood. This data arrives slightly after the main response (once background processing completes).

## Can I read and edit the assistant's journals?
Yes! In **Settings > Features > Personal Journals**, you can:

**👁️ Read:** Browse entries organized by theme in accordion sections
**✏️ Edit:** Modify title, content, or mood of any entry
**🗑️ Delete:** Remove individual entries or delete all (GDPR)
**➕ Create:** Add your own notes to guide the assistant (transparent — it can't tell the difference)
**📥 Export:** Download all entries in JSON or CSV format

## What settings can I configure?

**🔧 Toggles:**
• Enable/disable journals entirely (data preserved when disabled)
• Enable/disable periodic consolidation
• Enable/disable conversation history analysis (with cost warning)

**📏 Numeric settings:**
• **Max journal size** — Total character budget across all entries (default: 40,000)
• **Prompt injection budget** — Characters injected into prompts (default: 1,500)
• **Max entry size** — Characters per individual entry (default: 2,000)
• **Max search results** — Entries returned by semantic search (default: 10)

**📐 Size management:**
The assistant manages its own journals autonomously via prompt engineering. A global size constraint limits total content (configurable). When approaching the limit, the assistant summarizes or deletes older entries. Timeless observations are naturally preserved — no hardcoded rules.

## How much does it cost?
Journal operations use **background LLM calls**:

• **Extraction**: One call per qualifying conversation (most return empty — selective)
• **Consolidation**: One call per consolidation cycle (every 4-12h per user)
• LLM models are configurable in **Admin > LLM Configuration** (category: Background)
• Real costs visible in Settings > Features > Personal Journals (tokens in/out + EUR)
• Costs integrated into the global dashboard consumption

## What about privacy?
• Journal data is **per-user** and isolated
• All data can be exported (JSON/CSV) or deleted (GDPR compliance)
• When you disable journals, data is preserved but not used until re-enabled
• The assistant writes in your configured language
