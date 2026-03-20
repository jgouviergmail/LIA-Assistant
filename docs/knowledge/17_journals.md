# Personal Journals (Carnets de Bord)

## What are personal journals?
Personal journals are **thematic notebooks** where the AI assistant records its own reflections, observations, analyses, and learnings. Unlike user memories (which store facts about you), journals contain the **assistant's own perspective** — written in first person, colored by its active personality.

**📓 4 themes:**
• **Self-reflection** — Thoughts about its own behavior, style, and growth
• **User observations** — Patterns in your communication, preferences (complementary to memories)
• **Ideas & analyses** — Creative ideas, analytical frameworks, hypotheses
• **Learnings** — Lessons from interactions, mistakes, successes

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

The assistant receives its most **relevant** notes (with similarity scores) and decides autonomously which to use.

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

## How is the journal size managed?
The assistant manages its own journals **autonomously** via prompt engineering:

• A global size constraint limits total content (configurable by user)
• When approaching the limit, the assistant summarizes or deletes older entries
• Timeless observations (names, deep patterns, fundamental learnings) are naturally preserved
• No hardcoded rules — the assistant decides what to keep based on importance

## How much does it cost?
Journal operations use **background LLM calls**:

• **Extraction**: One call per qualifying conversation (most return empty — selective)
• **Consolidation**: One call per consolidation cycle (every 4-12h per user)
• LLM models are configurable in **Admin > LLM Configuration** (category: Background)
• Real costs visible in Settings > Features > Personal Journals (tokens in/out + EUR)
• Costs integrated into the global dashboard consumption

## Do journals affect proactive notifications?
Yes! When journals are enabled, they are integrated as a **context source** for proactive heartbeat notifications:

• Journal entries appear as a toggleable source badge in heartbeat settings (green when active, grayed when disabled)
• The heartbeat system builds a **dynamic query** from the aggregated context (upcoming events, weather, emails, etc.) to find the most relevant journal entries
• This allows the assistant to **personalize notification tone and content** based on its own observations and reflections about the user
• Entries below a minimum relevance score are automatically filtered out

## Can I see journal injection details?
Yes, in the **debug panel** (if enabled in Settings > Debug):

• A "Personal Journals" section shows injection metrics for each conversation
• You can see how many entries were found, how many were injected (within budget), total characters used
• Each entry shows its similarity score, theme, source, and date
• Entries that were found but not injected due to budget constraints are marked with a "BUDGET" badge

## What about privacy?
• Journal data is **per-user** and isolated
• All data can be exported (JSON/CSV) or deleted (GDPR compliance)
• When you disable journals, data is preserved but not used until re-enabled
• The assistant writes in your configured language
