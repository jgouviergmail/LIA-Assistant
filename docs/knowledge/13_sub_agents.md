# Sub-Agents

## What are sub-agents?
Sub-agents are **specialized ephemeral experts** that the principal LIA assistant can delegate a task to. When your request would benefit from a domain expert perspective (deep analysis, market study, technical audit, structured comparison), the assistant can spin up one or more sub-agents that run in parallel and produce a focused expert-grade output.

Sub-agents are **invisible**: you only talk to the principal assistant, which orchestrates the delegation and presents the expert output to you naturally.

**💡 Tip:** you can ask LIA explicitly to use a specialist, for example: *"Answer me as a senior analyst, use a specialized sub-agent"*.

## When does LIA use sub-agents?
LIA decides to delegate when:

• Your request benefits from a **specialist's perspective** (e.g., senior analyst on market trends, expert reviewer on a contract)
• A topic requires **deep, structured analysis** rather than a short factual answer
• Multiple **independent expert viewpoints** are useful in parallel (e.g., a finance expert + a regulatory expert on the same question)

Simple factual questions are always handled directly — experts are only mobilised when they add real value.

**You stay in control:** before launching an expert, LIA asks for your confirmation. If you decline, the assistant automatically switches to a standard plan without sub-agents.

## What does a sub-agent actually do?
A sub-agent runs a focused, time-bounded loop:

• It receives a **persona** (e.g., "senior analyst with 10+ years in AI markets") and a **task statement** written by the principal assistant for your specific question.
• It has access to a **narrow set of read-only research tools** (web search and web-page fetching by default) — not to your personal data tools (emails, calendar, contacts, files). The principal assistant already inlines the data the sub-agent needs.
• It **calibrates its output** to the nature of your request: a "detailed market analysis" yields a structured multi-section report with cited sources ; a "summary" yields a tight condensation ; a "comparison" yields parallel sections per item.
• It **cites its sources** (URLs) for every numerical claim and distinguishes facts from inferences.
• It **never invents data** — if a piece of information is missing and cannot be researched, the sub-agent says so plainly.

The principal assistant then **restitutes the sub-agent's analysis verbatim** to you, preserving its sections, sources and expert voice — without rewriting it in the assistant's own conversational tone.

## Can I disable sub-agents?
Sub-agent activation is **managed at the application level** by your administrator (via a global configuration flag); it is not a per-user setting in your account.

In practice, **you stay in control on each delegation**: before launching the experts, LIA asks for your confirmation. If you decline, the assistant automatically switches to a standard plan without sub-agents — you can keep refusing on a per-question basis.

If you would prefer to **never** see sub-agent delegations, ask your administrator to disable the feature globally.

## Do sub-agents cost more tokens?
Yes — each sub-agent runs its own LLM calls (a few rounds of research tool use plus a final synthesis). A single sub-agent typically costs **2–4× more tokens** than answering the same question directly without an expert; a plan that delegates to multiple parallel experts costs proportionally more.

**🛡️ Built-in guard-rails:**
• Dedicated **timeout budget** per delegation (configurable by the administrator)
• Bounded number of **research rounds** per sub-agent (configurable; default leaves room for ~3–4 tool rounds + synthesis)
• **Inline instruction cap** — the principal can't shovel megabytes of raw data into the delegation
• All sub-agent costs are **tracked and visible** in your usage statistics (tokens used, duration, cost)
