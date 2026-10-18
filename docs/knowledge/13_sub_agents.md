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

It works on one task, briefly and within bounds:
• LIA gives it a **role** — a specialist of the field — and a **task** written for your question, with the information from your request it needs already included
• it researches with a narrow set of **read-only** tools — by default web search and page reading, not your e-mails, calendar or contacts. Your administrator chooses the list, a tool that would change anything is never allowed, and a sub-agent cannot start another one
• it separates what it observed from what it deduces, dates its figures, links its sources, and says plainly when a piece of information is missing rather than inventing it
• if it runs out of steps, its last pass writes up what it found instead of searching further

LIA then hands you that analysis **as written**, keeping its sections and sources — sometimes even in the language the analysis was written in.

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
