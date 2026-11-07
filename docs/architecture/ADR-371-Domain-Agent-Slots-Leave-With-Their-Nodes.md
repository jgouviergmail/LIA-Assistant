# ADR-371 — The domain agents' slots leave with the nodes that read them

**Status**: Accepted, 2026-11-06.
**Date**: 2026-11-06

**Completes**:
[ADR-065](ADR-065-Legacy-Domain-Agent-Nodes.md) — the nodes it documented as dead and kept
« for safety » leave, its Option 2, with the slots it called misleading.

**Amends**:
[ADR-244](ADR-244-LLM-Catalogue-Truth.md) — `llm_type_map` keeps the two compiled agents that
exist, and a seed row names a slot that exists, on a model with an active tariff.

## Context

The admin screen « LLM types configuration » listed seventeen « domain agents »: Contacts, Emails,
Calendar, Drive, Tasks, Weather, Wikipedia, Perplexity, Brave, Web Search, Web Fetch, Hue, Places,
Routes, Health Metrics, Telephony and SMS. Each had a builder, a versioned prompt, a graph node and a
slot an administrator could tune. The owner asked whether any of it was still used.

ADR-065 had answered in March and kept the nodes as a theoretical fallback until someone was sure.
That is now measured rather than reasoned. The router only emits `action` and `conversation`, the
legacy `create_orchestration_plan` maps contact and browser intentions alone, `agents_to_call` is
therefore empty, and `task_orchestrator` runs a plan through `parallel_executor`, which calls the
tools directly. ReAct binds the tools itself. Measured on production on 2026-11-06:

- `token_usage_logs`: not one token on any of these nodes across the 109,043 calls recorded since
  2025-12-11;
- Prometheus, seven days: no transition into any `*_agent` node, against 137 transitions across the
  whole graph as a witness that the query reads real data.

Sixteen slots were configuration nobody read: an administrator who tuned « Calendar Agent » changed
nothing. The seventeenth is alive under the same label: `get_llm("email_agent")` writes in
`emails/content_generation.py`, `emails/reply_drafting.py` drafts through it, and `TOOL_LLM_SLOTS`
declares it on four mail tools.

## Decision

1. **The sixteen slots are gone**: `LLM_TYPES_REGISTRY`, `LLM_DEFAULTS`, the `LLMType` Literal, their
   translations in six languages, their builders and prompts, their nodes and edges, and the rows in
   `llm_config_overrides` (migration `b6d21f7e4a90`, which leaves `emails_agent` alone).
2. **`emails_agent` stays**, with its singular alias. It is a writer, not a graph node: its builder
   and prompt leave with the others.
3. **What a name means is unchanged.** `contact_agent`, `event_agent` and their siblings remain the
   `agent=` of the tool manifests and the taxonomy's vocabulary: the catalogue, the capability
   switches, the metrics and the `agent_results` keys read them. Only a *slot* or a *compiled agent*
   of that name is gone.
4. **A compiled agent is one that exists.** `build_query_agent` and `build_browser_agent` stay, with
   `build_generic_agent` and its middleware. `SmsModelBoundary` belongs to that middleware, so its
   proofs stay, on a test agent holding the real SMS tools (`sms_reader_agent.py`).
5. **The SMS tools' budget reads the slots that receive the page**: `response`, and `react_agent`
   before it in ReAct. The retired `sms_agent` slot gave them a budget from a model nobody called.

## Why a fresh install changed too

Reading the seeds for the orphan `web_search_agent` row showed four slots of a fresh install on a
model with no active tariff, counted at zero in every ledger: `vision_analysis` on a retired
Gemini, and the three `discussion_*` stages inheriting a retired Qwen from `heartbeat_decision`.
`llm_config_seed.sql` moves them to the same provider's current model, with the same capabilities;
the native defaults stay, because a default is also what an existing instance falls back on.
`test_pricing_seed_extraction_guard.py` now refuses a fresh slot on an unpriced model and a seed row
for a slot nobody declares.

## Consequences

- The admin screen shows only slots that act on something.
- `create_orchestration_plan` keeps its browser intentions alone. That legacy road, the browser
  node it leads to (the browser tool runs its own loop) and the query agent, which the registry
  knows and nothing ever builds, are the same question for another day: none was on the list.
- A checkpoint survives: the graph reads only the channels it declares, and all 58 threads of the
  dev database read back through the new graph, none waiting on a node that left.
- The constants nothing read any more leave with them: the `NODE_*` of nodes that are gone and the
  `INTENTION_*` nothing routes on.
- A value an administrator saved on a retired slot is deleted by the migration. Nothing is lost:
  nothing ever read it. The downgrade writes nothing back, the former code falling back on its
  defaults.
- `EMAILS_AGENT_PROMPT_VERSION` leaves the templates. A live `.env` still carrying it is harmless:
  `Settings` ignores what it does not declare.
