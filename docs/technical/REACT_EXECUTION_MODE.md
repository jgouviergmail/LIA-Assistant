# ReAct Execution Mode

| Version | Date | ADR |
|---------|------|-----|
| 1.0 | 2026-04-09 | [ADR-070](../architecture/ADR-070-ReAct-Execution-Mode.md) |
| 1.1 | 2026-07-28 | [ADR-169](../architecture/ADR-169-React-System-Blocks-Are-State.md), [ADR-170](../architecture/ADR-170-React-Compute-Budget-And-Loop-Guard.md) |
| 1.2 | 2026-08-29 | [ADR-248](../architecture/ADR-248-React-Memory-Parity-And-Progress-Earned-Budget.md), [ADR-249](../architecture/ADR-249-Ephemeral-Python-In-The-Existing-Sandbox.md) |
| 1.3 | 2026-09-18 | [ADR-298](../architecture/ADR-298-Sandbox-Egress-Toolbox.md) |
| 1.4 | 2026-09-23 | [ADR-308](../architecture/ADR-308-ReAct-Cross-Turn-Prompt-Cache.md) |
| 1.5 | 2026-09-24 | [ADR-310](../architecture/ADR-310-ReAct-Turn-Judged-On-Its-Result.md) |
| 1.6 | 2026-09-24 | [ADR-311](../architecture/ADR-311-Exchange-Rhythm-Is-The-Persons-Choice.md), [ADR-309](../architecture/ADR-309-One-Prompt-Layout-For-Every-Cache-Mechanism.md) amendment |

## Table of Contents

1. [Overview](#overview)
2. [Pipeline vs ReAct](#pipeline-vs-react)
3. [Architecture](#architecture)
4. [Graph Wiring](#graph-wiring)
5. [Nodes](#nodes)
6. [Tool System](#tool-system)
7. [HITL in ReAct](#hitl-in-react)
8. [Response Synthesis](#response-synthesis)
9. [Initiative enrichment on the nominal path](#initiative-enrichment-on-the-nominal-path-adr-070--adr-062)
10. [Turn isolation & data-precision guidance](#turn-isolation--data-precision-guidance-2026-07)
11. [Token Tracking](#token-tracking)
12. [Skills Integration](#skills-integration)
13. [Sandboxed Python](#sandboxed-python-adr-249)
14. [Configuration](#configuration)
15. [Streaming Step Visibility](#streaming-step-visibility-v1162)
16. [Key Files](#key-files)

---

## Overview

ReAct (Reasoning + Acting, Yao et al. 2022) is an alternative execution mode to the pipeline. Instead of planning all steps upfront then executing them, the LLM iteratively reasons about each tool result and decides the next action autonomously.

The user toggles between modes via a frontend toggle (Zap icon). The preference is persisted in the `users.execution_mode` column (`"pipeline"` or `"react"`).

## Pipeline vs ReAct

| Aspect | Pipeline | ReAct |
|--------|----------|-------|
| **Flow** | Router → Planner → Orchestrator → Agents → Response | Router → ReAct Loop → Response |
| **Planning** | Upfront (ExecutionPlan DSL) | None — LLM decides step by step |
| **Adaptability** | Rigid — follows plan | Adaptive — pivots on tool results |
| **Tool selection** | Planner selects by domain | LLM chooses from all available tools |
| **Token cost** | Lower (1 planner + 1 response LLM call) | Higher (1 LLM call per iteration) |
| **Best for** | Well-structured requests, multi-domain | Exploratory, research, ambiguous queries |
| **HITL** | Plan-level approval + draft confirmation | Tool-level interrupt + draft confirmation (shared flow) |
| **Initiative** | Dedicated `initiative_node` (post-execution LLM evaluation) | Same `initiative_node` on the nominal path when `INITIATIVE_REACT_ENABLED` (ADR-070 amendment 2026-05-21), in addition to the in-loop CROSS-CHECK step |

## Architecture

Custom ReAct loop as **5 nodes in the parent LangGraph graph** (not a `create_react_agent` subgraph — avoided due to LangGraph bugs with dynamic tool interrupts, GitHub #5863/#4796):

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                           ReAct Execution Loop                                   │
│                                                                                  │
│ router ──(react)──► react_setup ──► react_call_model ◄───────────────────┬────┐  │
│                                            │                             │    │  │
│                   ┌────────────────────────┼───────────────────┐         │    │  │
│        tool_calls │         none declared  │     gap declared  │         │    │  │
│                   ▼                        ▼      a pass left  ▼         │    │  │
│          react_execute_tools        react_finalize      react_recovery ──┘    │  │
│                   │                        │           (draft removed,        │  │
│           draft? ─┤                        │            pass recorded)        │  │
│      no (loop) ───┼────────────────────────┼──────────────────────────────────┘  │
│            yes    │                        │                                     │
│                   ▼                        │                                     │
│    hitl_dispatch ─► initiative             │                                     │
│    (draft_critique)      │                 │                                     │
│                          ▼                 ▼                                     │
│                         response_node ──► [END]                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

Each node benefits from the parent graph's PostgreSQL checkpointer, so `interrupt()` works natively in `react_execute_tools` (and in the shared `hitl_dispatch` node reached for draft confirmation) — see [HITL in ReAct](#hitl-in-react).

## Graph Wiring

```python
# graph.py — ReAct edges
graph.add_edge(NODE_REACT_SETUP, NODE_REACT_CALL_MODEL)
graph.add_conditional_edges(
    NODE_REACT_CALL_MODEL,
    route_from_react_call_model,  # → execute_tools, finalize, or recovery (ADR-310)
    {
        NODE_REACT_EXECUTE_TOOLS: NODE_REACT_EXECUTE_TOOLS,
        NODE_REACT_FINALIZE: NODE_REACT_FINALIZE,
        NODE_REACT_RECOVERY: NODE_REACT_RECOVERY,
    },
)
graph.add_edge(NODE_REACT_RECOVERY, NODE_REACT_CALL_MODEL)
graph.add_conditional_edges(
    NODE_REACT_EXECUTE_TOOLS,
    route_from_react_execute_tools,
    {
        NODE_REACT_CALL_MODEL: NODE_REACT_CALL_MODEL,  # Loop back (no draft)
        NODE_DRAFT_CRITIQUE: NODE_DRAFT_CRITIQUE,  # Draft → shared HITL dispatch
    },
)
graph.add_conditional_edges(
    NODE_REACT_FINALIZE,
    route_from_react_finalize,  # optionally via the initiative (INITIATIVE_REACT_ENABLED)
    {NODE_INITIATIVE: NODE_INITIATIVE, NODE_RESPONSE: NODE_RESPONSE},
)
```

Routing from router: when `execution_mode == "react"` and the router classifies the query as actionable, it routes to `NODE_REACT_SETUP` instead of `NODE_PLANNER`.

## Nodes

### react_setup

Prepares tools, system prompt, and context for the ReAct loop:
- Binds the tools the turn needs via `ReactToolSelector` (filtered by active connectors, composed by relevance — ADR-293, see « Tool System » below)
- Builds system prompt from `react_agent_prompt.txt`
- Injects the **same memory context as the pipeline** (ADR-248), built by
  `src/domains/agents/nodes/react_context.py`: memory profile block, resolved references,
  psychological portrait, journal excerpts, active skills — and the degraded-capability
  advisor. Before ADR-248 the two modes read different subsets, so a directive the user had
  stored took effect in one mode and silently did nothing in the other. `react_context.py`
  and the pipeline builder now consume the same services; a parity test pins the block set.
  Since 2026-09-17 (ADR-248 amendment, ADR-291) the loop also receives the person's
  **knowledge spaces** — the same `<UserDocuments>` block as the response node, read from
  the prefetched bundle without consuming it — and `search_user_documents_tool` survives
  the tool cap whatever the detected domains (`CAP_SURVIVORS` in the selector).
- Injects active skills catalogue (L1, filtered by `active_skills_ctx`)
- Sets `react_start_time` (kept for observability; the deadline itself runs on compute — see below)
- Stores tool names and HITL map in state (JSON-serializable)
- **Publishes the turn's system blocks to `react_system_blocks`, not to `messages`** (ADR-169)

> **Why the blocks are state and not messages.** `get_windowed_messages(include_system=True)`
> hoists every `SystemMessage` to the front with no window limit, so appending them to the
> history meant every past copy was re-sent on every call: `react_agent_prompt.txt` is
> **840 tokens**, so 3 turns cost 2 520 tokens of duplicated prompt *per LLM call of every
> iteration*, the provider prefix cache could never hit (the prefix grew each turn), and
> Anthropic rejected the sequence from the second turn — a `SystemMessage` cannot sit in
> the middle of a history. The blocks now live in their own state key and are recomposed
> leading at each call. The state schema is **1.4**; the 1.3 → 1.4 migration is additive
> and idempotent.

### react_call_model

Calls the ReAct LLM with bound tools:
- Recreates LLM and tool bindings each iteration (~1-2ms)
- Recomposes `react_system_blocks` as leading `SystemMessage`s (stable prefix)
- Applies message windowing (preserves current turn, windows history; legacy `SystemMessage`s
  in the history are dropped, except the compaction summary)
- Accumulates the node's own wall time into `react_elapsed_seconds` (the compute budget)
- Returns AIMessage with or without `tool_calls`

### react_execute_tools

Executes tools from the last AIMessage:
- HITL: tools flagged `hitl_required` trigger `interrupt()` for pre-execution approval; draft-preparing mutation tools (`requires_confirmation`) instead hand off to the shared draft-confirmation flow (see [HITL in ReAct](#hitl-in-react))
- Idempotence: on re-execution after interrupt resume, already-resolved tool calls are skipped
- **No-progress guard** (ADR-170): after the idempotence skip, each executed call is digested and counted
- ToolRuntime injection via `_build_tool_runtime()` (same pattern as pipeline)
- **Per-tool timeout** (ADR-256): every call is wrapped in the `compute_step_timeout` policy —
  the same per-family bounds the pipeline applies, read from a second caller rather than a
  second copy. An overrun becomes a recoverable `ToolMessage`, never an exception that kills
  the node and discards the results that did come back
- Accumulates the time spent inside tools into `react_tool_seconds` (ADR-256)
- Registry items accumulated across iterations via `current_turn_registry` merge

### The two time budgets (ADR-170, ADR-256)

A turn has **two** time budgets, counted apart, and one predicate reads both.

| Key | What it counts | Setting | Charged by |
|-----|----------------|---------|------------|
| `react_elapsed_seconds` | The model's own REASONING | `react_agent_timeout_seconds` | `react_call_model` |
| `react_tool_seconds` | Time spent INSIDE tools | `react_tool_budget_seconds` | `react_execute_tools` |

They are separate because a delegating tool opens its own LLM loop behind a single `tool_call`:
20 iterations for a sub-agent (ADR-083), 50 for an iterative MCP task or a browser run. Before
ADR-256 that work charged **nothing anywhere** — `react_elapsed_seconds` was written by one node
out of four, and it is the node that only thinks — so a turn whose model reasoned 10 s while its
tools ran for three hours returned `react_exit_reason() is None`. Measured upper bound for one
turn, on the real constants: **~30 h**.

Summing the two was measured and rejected: one delegation at its pipeline bound (300 s) equals
100 % of the reasoning budget, so turns that complete today would start being cut. The reasoning
threshold is therefore unchanged, and `react_exit_reason` gained a third answer, `tool_budget`,
named apart — reporting delegated time as `compute_budget` would tell the user the model thought
too long when in fact a sub-agent did.

Both exclude the wall clock a user spends on a HITL approval, for the structural reason below.

**Both restart at zero on every turn, from ONE declaration** — `react_turn_reset()` in
`utils/react_budget.py`, spread by `router_node_v3` at turn start and by `create_initial_state`.
Every accumulator of the loop (`react_iteration`, both time counters, `react_productive_iterations`,
`react_call_digests`) is charged as `previous + spent` and restored by the checkpoint, so one the
router does not reset is a debt that runs for the life of the thread. Measured on production
(2026-09-11, ADR-256 amendment): `react_tool_seconds` was missing from the router's hand-maintained
list, one conversation accumulated 913.8 s over six days, and every later ReAct turn of that thread
stopped at iteration 1 with its tool calls abandoned — no error, three identical « ko ». A routine
(one thread per action) and a ticket (one thread per ticket) reach the same wall, slower.
`test_react_turn_reset_guard.py` reads by AST every `state.get("react_…")` of the stop predicate and
of the routing edge, and refuses a key the declaration does not name; `react_max_iterations_effective`
is the one exemption, because its start value is COMPUTED by `react_setup_node` from the domain span.

`react_agent_timeout_seconds` is compared against **compute time**, not wall
clock. The reason is structural: `interrupt()` raises, so the node never returns, no state
update is persisted and no timestamp is refreshed; the resume re-enters the interrupted node,
and the router — where the reset lived — does not replay. Verified on a real LangGraph graph:
*router re-ran on resume?* **no**, *start_time refreshed?* **no**, **2.01 s of wall clock for
0.0102 s of compute**. The consequence was concrete: any approval taking longer than the budget
cut the resumed turn at the next routing decision, leaving the last `AIMessage` carrying tool
calls and no content, so the answer was re-synthesised by a second LLM call and the multi-step
work was lost.

`react_tool_executions_before_interrupt_total` and the `uncharged_wall_seconds` field keep the
gap between wall clock and compute **visible** rather than merely unbilled.

The no-progress guard tracks up to 64 call digests per turn:

| Setting | Default | Effect |
|---------|---------|--------|
| `REACT_REPEATED_CALL_BLOCK_THRESHOLD` | 4 | Nth identical call is refused; the model is told to change approach |
| `REACT_REPEATED_CALL_TERMINAL_THRESHOLD` | 5 | Nth identical call ends the turn |

The digest is an HMAC keyed on the application secret, so it survives an HITL resume on another
worker, and **only the digest and a counter are stored** — neither the tool name nor its
arguments reach the PostgreSQL checkpoint. A validator refuses a terminal threshold at or below
the block threshold.

### Progress-earned iterations (ADR-248)

The iteration ceiling is not a flat constant. `react_iteration_budget()` starts from the
domain span the router detected (ADR-238's adaptive budget, shared with the pipeline), and
`REACT_PROGRESS_EXTENSION_ENABLED` (default `true`) lets the loop buy extra iterations —
but **only against productive ones**. `_is_productive_result()` is the predicate: a tool
result that carries data extends the budget, a refusal, an empty result or an error does
not. The extension is capped by `REACT_PROGRESS_EXTENSION_MAX_ITERATIONS`.

The rule exists because the two failure modes are opposite and both were live: a fixed low
ceiling cut multi-step work that was going *well*, and a fixed high ceiling let a loop that
was going nowhere burn fifteen calls before saying so. Every exit is now named —
`react_exit_reason()` records `completed`, `budget_exhausted`, `no_progress` or `timeout` —
and the reason travels to the response node, so the answer can state what happened instead
of inventing a diagnosis.

### react_recovery (ADR-310)

The loop used to end the moment the model called no tool, so a fact it could not get ended the
turn as a stated gap however many sources it still had (measured 2026-09-23: a forecast served
for the wrong day, answered « I could not get it » after 4 iterations of the 70 its budget
allowed, a web search never tried). A turn is now judged on its result
([ADR-310](../architecture/ADR-310-ReAct-Turn-Judged-On-Its-Result.md)):

- **The protocol.** Every fact the loop set out to obtain — what the person asked for, and
  each cross-check it started — ends obtained or declared, never dropped in silence. The final
  message closes with an `<unresolved>` block, one line per such fact still missing after the
  ladder, with the rungs tried, and carries no block when nothing is missing. A detail nobody
  asked for and nobody looked up is not a gap, nor is a fact obtained from another source: it
  carries that source (`Source: … (fallback)`). `declared_unresolved` reads every block — from
  the LAST opening before each closing, because a model that names the tag in its reasoning
  opens nothing — case-insensitively, and ignores an empty one, the `...` placeholder or a lone
  « none » in six languages.
- **One predicate.** `should_recover` (`nodes/react_recovery.py`) is true when the last message
  is a final answer that declares a gap, fewer passes were taken than `REACT_RECOVERY_PASSES_MAX`
  (`0` switches the pass off), and `react_exit_reason` — which it CALLS — lets the loop go on.
  The router reads it in its « no tool calls » branch.
- **The node calls no model.** It removes the draft from the thread at once (`RemoveMessage`) —
  so every exit of the loop, the draft hand-off to the HITL dispatch included, leaves one answer
  — and appends `{anchor_id, draft, unresolved}` to `react_recovery_passes` (reset by
  `react_turn_reset()`, guarded).
- **What the model is shown is transient.** `with_recovery_directives` puts, on every later call
  of the turn, the draft and a directive (`react_recovery_directive.txt`) right after the
  draft's place — after the system messages glued to it, so the turn's context stays after its
  question (ADR-308). Neither is written to `messages`: no later turn reads the directive as
  something the person said, the roles alternate on every provider, and the prefix before the
  anchor stays the same for the provider's cache. Passes sharing an anchor are shown together,
  in the order they were taken. The final message after a pass REPLACES the draft, so the
  directive asks for it complete — every finding restated, updated.
- **The outcome.** `react_finalize` merges `react_agent_result["recovery"]` (`passes`,
  `outcome`: `resolved`, `partial`, `still_unresolved`, `cut`) and counts it once per turn that
  took a pass (`react_recovery_turns_total{outcome}`, dashboard 20); the debug panel's ReAct
  section draws it as « Recovery ». A pass that ends with no usable answer — an empty reply, or
  a budget that stops it with calls pending — hands the last draft back as the final message,
  since the draft left the thread at the pass. A fact still unresolved reaches the response node
  inside the final message, which says it is missing, with what was tried — never an estimate.

The doctrine behind the protocol lives in the prompt's static part: a result counts only if it
answers what was asked — a wrong day, place or entity, or a list the tool says it cut, is an
obstacle exactly like an error — and every obstacle climbs the RECOVERY LADDER: the loop's own
call corrected, then another source (a sibling tool, then, for public facts, the web search or
page fetch tools of the turn's list), then the declaration, never repeating a call that already
failed with the same arguments. The sandbox rung lives in the `<Computation>` block, rendered
only when `run_python_tool` is bound (ADR-284). Relative dates are resolved to ISO 8601 against
the `<Context>` date and timezone before any tool parameter; the pipeline planner and the
initiative carry the same line.

`task react:recovery:measure` runs seven obstacles and a clean control through the loop's own
functions on real models, with deterministic stub tools, and compares a doctrine with its predecessor
(`--baseline-prompt FILE`); the figures are in ADR-310.

### react_finalize

Collects iteration count and prepares metadata for the response node:
- Records Prometheus metrics (iterations, duration, executions)
- Sets `react_agent_result` for the response node passthrough
- **Refuses to hand over mid-thought content** (ADR-248): when the loop ends on an
  `AIMessage` that carries tool calls and no usable text, the turn does not ship the
  model's last "let me look into your emails…" as the answer. That sentence was the
  measured production defect: an announcement, then silence, because a budget exhaustion
  had ended the turn on a message that was never meant to be final.
- After a recovery pass, merges `react_agent_result["recovery"]` (`passes`, `outcome`) and
  counts it once (ADR-310, see [react_recovery](#react_recovery-adr-310)).

## Tool System

The ReAct agent binds tools **by relevance** ([ADR-293](../architecture/ADR-293-React-Tools-Bound-By-Relevance.md)), never by registration order:
- Filtered by active connectors (`get_request_tool_manifests()`), then composed by `ReactToolSelector.select` from the turn's **global ranking** — every available manifest ordered by the router's semantic scorer from the ONE query embedding it already pays for (`router_tool_scoring.score_tools_for_turn`, `tool_selection_result["global_ranking"]`, user MCP tools ranked through their per-request vectors): the detected domains' tools first (all of them), then every OTHER family's `CATALOGUE_DOMAIN_COVERAGE_TOP_N` best-ranked tools (the planner catalogue's own coverage constant, so a family the router did not name stays reachable), then the first `REACT_TOOL_SEMANTIC_TOP_K` of the ranking; the rest is dropped by relevance (`react_tool_selector_relevance`, names at debug). No tool name is written anywhere in this rule. An iterative user MCP server's individual tools rank through their per-request vectors (they have no manifest of their own) and its delegation door (`_task`) is kept beside the family's coverage, ranked as the best tool behind it; an actionable turn with no detected domain is ranked all the same. A **binding unit** (`ToolManifest.binding_unit` — the four skills tools declare `SKILLS_BINDING_UNIT`) is bound whole or not at all: it ranks as its best member, holds one coverage seat, rides the tail whole and the cap never cuts inside it (ADR-293 amendment 2026-09-20 — measured: the ranking bound `activate_skill_tool` and dropped `run_skill_script`, so the loop activated a skill it could not run).
- Without a ranking, or with `REACT_TOOL_SEMANTIC_TOP_K=0`, every available tool is bound in registration order — the behaviour before ADR-293.
- Capped by `REACT_AGENT_MAX_TOOLS` (default: 100) as the safety net — measured on the **resolved** tool count, after iterative expansion, by a stable sort on tiers: the detected domains' tools, then one coverage per family, then the rest; every dropped tool is named in a `react_tool_selector_capped` warning. A blind positional truncation here used to silently drop e.g. calendar tools on a calendar query once user-MCP expansion pushed the count over the cap (2026-07-08 incident: hallucinated appointments); and before ADR-293 the same tools fell off on every turn of any account with more tools than the cap, whatever the question.
- Measured: `react_tools_bound` (after selection and cap) against `react_tools_resolved`, and `react_bound_tool_tokens` — the schema tokens every model call of the turn carries, which the delivered-context histogram never counted (dashboard 20). `task react:selection:measure -- --turns turns.json` replays an operator's own turns against the policy.
- Wrapped in `ReactToolWrapper` for string conversion + registry collection
- HITL map built from the in-hand tool manifests (`permissions.hitl_required`)

Tools are NOT stored in state (non-serializable). Tool names and HITL map are stored instead, and tools are rebuilt in each node that needs them.

### Cross-turn prompt cache (ADR-308, ADR-311)

« Frequent exchanges » make a turn's prompt prefix the previous turn's, so the provider's prompt cache is read across turns ([ADR-308](../architecture/ADR-308-ReAct-Cross-Turn-Prompt-Cache.md)). It is the PERSON's choice, in Settings › Usage preferences ([ADR-311](../architecture/ADR-311-Exchange-Rhythm-Is-The-Persons-Choice.md)); `REACT_CROSS_TURN_CACHE_ENABLED` (off by default) is only the rhythm of an account that never chose. For « occasional exchanges », nothing above changes. For frequent ones, three things change together:

- **Every available tool is bound, in registration order** — `ReactToolSelector.select` ignores the ranking and `REACT_TOOL_SEMANTIC_TOP_K`, so the tools are the same bytes on every turn. When they cannot all be bound the turn keeps the relevance selection and the fallback is counted by reason (`react_cross_turn_cache_fallback_total`, dashboard 20): `cap` when the account holds more tools than `REACT_AGENT_MAX_TOOLS` (bound 400 — set it to the account's whole catalogue; 400 tools weigh about 140K tokens of schemas, a load for a model with a 1M window), `window` when the schemas exceed `REACT_CROSS_TURN_CACHE_MAX_WINDOW_FRACTION` of the `react_agent` slot's window.
- **The turn's context follows the question** (`nodes/react_turn_layout.py`, called by `react_call_model_node`). The leading system message is the static prompt ending on its `DYNAMIC CONTEXT` line — where the payload shapers cut their breakpoint and the OpenAI cache key stops (ADR-306) — and the context (that line, the prompt's dynamic part, then every context block) comes right after the question, before the loop's own messages. Its shape is declared per provider in `CONTEXT_PLACEMENT`, checked at boot: a system message after the question for OpenAI, DeepSeek and Qwen; the context appended to the question's own message, as text, for Anthropic (a system message that is not first is refused), Gemini (its client folds a later system message back into the system instruction), Ollama and Perplexity. Nothing of it reaches the checkpoint.
- **The history drops by blocks**, anchored on the turn counter (below, ADR-309).

Measured on real turns (2026-09-23), weighted by production's gaps between ReAct turns: −18 % per turn on Claude Sonnet 5, −34 % on gpt-5.6-luna, −42 % on deepseek-flash, −18 % on qwen3.7-plus; +18 % on qwen3.5-plus, which has no prompt cache at all on the Frankfurt endpoint. Binding every tool WITHOUT moving the context cost 44 % more on DeepSeek, whose cached prefix puts the system prompt before the tools — which is why the rhythm does both, and why the history blocks below travel with them: measured, the context after the question pays only when the tools before it stay the same, and the blocks only when the history is read again (ADR-311).

The person decides whether their turns run this way (ADR-311, Settings › Usage preferences): « frequent exchanges » bind every tool, place the context after the question and drop the history by blocks; « occasional exchanges » keep the relevance selection. The rhythm is read once per turn — the router publishes it into the turn's state (`exchange_rhythm`), the setup and every call read the state (`react_turn_layout.frequent_exchanges`) — and `REACT_CROSS_TURN_CACHE_ENABLED` is the default of an account that never chose. For frequent exchanges, the loop's history drops its oldest turns by BLOCKS ([ADR-309](../architecture/ADR-309-One-Prompt-Layout-For-Every-Cache-Mechanism.md)): it keeps between N and N + block − 1 turns, the block being `REACT_CROSS_TURN_HISTORY_BLOCK_FRACTION` of the window, so each turn's history extends the previous one and a provider reads it again. How many is a function of the conversation's turn counter (`current_turn_id`) alone, taken from the END, and a turn is kept whole from its question (`get_block_windowed_messages`): the messages reducer trims the thread's head on every tool result of a long turn, and blocks aligned on the thread's length moved in the middle of a turn — measured on the first production morning, three calls of one routine run re-billed after the tools (amended 2026-09-24). When the reducer has trimmed into the block, the loop keeps the window proper: it holds within the turn, and slides by one turn from one turn to the next, as before ADR-309. For frequent exchanges, `message_windowing_complete` states `turns_wanted`, `turns_available` and `turns_kept`, so that case can be read in the logs. A history shorter than the window is kept whole. The compaction summary is read first wherever compaction appended it, so the head trim that takes it moves the view once. For occasional exchanges the loop slides one turn at a time as before. The response node always slides: it receives the conversation once, as its messages, after the turn's own context (the query, the date, the results), which no cache reads — blocks there would only add tokens.

### Tool results (ADR-286)

What a tool returns reaches the model through `ReactToolWrapper._process_result` → `compose_tool_message`: the tool's `message`, then a `Data:` block, then — only when something was left out — a budget note. The block is a **per-item projection** (`render_data_block`): the heaviest list of dicts in `structured_data` (or the registry payloads grouped by type) is paged at item boundaries under a **token** budget, `min(REACT_TOOL_RESULT_MAX_TOKENS, window × REACT_TOOL_RESULT_WINDOW_FRACTION)` where the window is the `react_agent` slot's own (ADR-278). An admitted item is complete and the block stays valid JSON; scalars (`count`, `query`…) travel whole, `<key>_shown` says how many items made it, at least one item always does. The note (`tool_result_budget_note`) goes **after** the `</external_content>` tag — it is ours, never third-party text — and names the count shown, the total, the budget and the way to the rest; every cut increments `react_tool_result_truncated_total{tool_name}` (dashboard 20, "Tool Result Budget Cuts").

Measured before (2026-09-15): the block was a JSON dump cut at 8 000 **characters**, spent on the first Gmail message's SMTP headers and base64 body (85-98 % of a `format=full` item, tokenised at 1.45 characters per token) — the model read no subject, id or date of any e-mail, ran eleven iterations and answered wrong. The raw provider tree now never leaves `build_emails_output`.

### Reading a mail attachment (ADR-296)

`get_emails` lists a message's attachments and stops there; `get_email_attachment_tool` ([ADR-296](../architecture/ADR-296-Mail-Attachments-Read-By-Text-Or-Vision.md)) reads ONE of them, in both execution modes. The account's own mail client downloads it (`download_attachment`, one shape on Gmail, Graph and IMAP), the bytes decide the route (`agents/emails/attachment_content.py`): a document's text goes through the knowledge spaces' extractor and is served in PARTS under `EMAILS_BODY_PART_TOKENS` like a body (ADR-287); an image, or a PDF without a text layer, is rendered to a bounded set of pages (`EMAIL_ATTACHMENT_VISION_MAX_PAGES`, `EMAIL_ATTACHMENT_IMAGE_MAX_EDGE`) and read by the `vision_analysis` slot — the turn's spend, `skipped_quota` under a ceiling, a truncated answer a refusal. The text reaches the model wrapped as **external content** on both paths. A Gmail attachment handle can expire between two reads of a message (measured on a real mailbox): the tool resolves a stale handle by the file name, then by uniqueness, else answers `DISAMBIGUATION_REQUIRED` with the current handles — the manifest tells the model to prefer the file name. The size bound (`EMAIL_ATTACHMENT_MAX_MB`) is published and stated in the refusal; every reading is counted (`email_attachment_reads_total{route,outcome}`, dashboard 10).

### Tool resolution (shared with the pipeline)

Both `ReactToolSelector` (binding) and `_rebuild_wrapped_tools` (execution) resolve a tool *name* to its instance through the shared `src/domains/agents/tools/tool_resolution.py` — the single source of truth used by the pipeline executor too. Resolution order: global `tool_registry` (native + admin MCP) → hallucinated-suffix strip → per-request `user_mcp_tools_ctx` (exact then fuzzy). Without this fallback the ReAct loop, which consulted only the global registry, silently dropped **user** MCP tools (whose instances live only in the ContextVar) — see ADR-070 amendment 2026-06-02.

### Iterative user MCP expansion

A user MCP server configured `iterative_mode=true` exposes a single opaque `mcp_user_{id}_task` manifest to the planner (it delegates to a ReAct sub-agent — ADR-062). Since the ReAct loop is *itself* iterative, that indirection only hides the descriptive individual tools, so the LLM falls back to generic web search. `ReactToolSelector._expand_iterative_user_mcp` therefore replaces the task manifest with the server's individual tools (read from the ContextVar), letting the model pick them by description. **Exception:** MCP App servers (a tool with `app_resource_uri`) keep the task tool, because they need the dedicated MCP-app prompt and the more capable `mcp_app_react_agent` model. Gated by `REACT_MCP_EXPAND_ITERATIVE_ENABLED` (default `true`); when `false`, the task tool is kept (instant rollback) and still resolves correctly via the shared resolver. The pipeline keeps the task-tool path unchanged.

> Optional MCP parameters left unset are materialised as `None` by the args schema; both MCP adapters drop `None`-valued arguments (`drop_none_values`) before the server call, so strictly-typed (e.g. Go-based) servers don't reject them as `null`.

## HITL in ReAct

ReAct has two HITL paths, both reusing existing infrastructure (no ReAct-specific HITL machinery):

1. **Pre-execution confirmation** — tools flagged `hitl_required` in their manifest (genuinely **non-draft** mutations only: `delegate_to_sub_agent_tool` and user MCP mutation tools) raise a **shared `tool_confirmation` interrupt** from `react_execute_tools` ([ADR-106](../architecture/ADR-106-HITL-Contract-Coherence.md)): the same `action_requests`-typed payload the pipeline uses, rendered by `ToolConfirmationInteraction` and persisted in Redis, then resumed through `_parse_approval_decision` → `{"action": "confirm"|"cancel"}`. The gate executes **only on an explicit confirm** (safe default: any non-approval declines). On resume, LangGraph replays the node; the idempotence pattern skips tool calls that already have a `ToolMessage` in state (matched by `tool_call_id`). *(The legacy bare `react_tool_approval` value carried no `action_requests`, so it never rendered — a silent hang, fixed by ADR-106. Draft-based delete/cancel tools are `hitl_required=False` and go through path 2 below; the `hitl_required` set is locked by `test_hitl_required_consistency.py`.)*

2. **Draft confirmation** — draft-preparing mutation tools (`create_event_tool`, `send_email_tool`, `update_*`, `delete_*`, …) return `requires_confirmation=True` and prepare a **draft** instead of executing. `react_execute_tools` extracts the draft and sets `pending_draft_critique`; `route_from_react_execute_tools` then routes to `hitl_dispatch` (the shared `draft_critique` node) → `initiative` → `response_node` — exactly the path pipeline mode uses. The user confirms/edits/cancels, then `response_node` executes the confirmed draft via `execute_draft_if_confirmed` and synthesizes the real result. Because confirmation happens in a node **downstream** of `react_execute_tools`, resume re-enters `hitl_dispatch` only — the draft tool is never re-run (no duplicate drafts). Completion metrics are still emitted on this short-circuited path (`react_agent_executions_total{status="draft"}`).

> Tools that execute directly without a draft (e.g. `create_reminder_tool`) are not draft-gated and behave identically in both modes.

## Response Synthesis

The ReAct loop never streams its own tokens to the user. `react_finalize` stores the loop's final answer in `react_agent_result.final_message`, and `response_node` delivers it — preserving all post-processing (personality, display mode, voice, registry cards, memory/journal extraction). Four invariants keep that hand-off clean:

1. **Authoritative answer** — `response_node` injects the final answer as `agent_results[…]["data"]["react_synthesis"]`. `_format_status_messages()` (in `formatters/agent_results.py`) surfaces it verbatim as the authoritative current-turn data the response LLM reformulates. Writer and reader use the same `FIELD_REACT_SYNTHESIS` constant, so the contract cannot drift (a missing/renamed key previously dropped the answer into a `"Statut inconnu"` status message, forcing the response LLM to reconstruct one).

2. **No reasoning leak** — `react_setup` injects the `react_agent_prompt` (with its PLAN/ACT/OBSERVE/CROSS-CHECK `<Workflow>` and tool-calling role) as `SystemMessage`s that accumulate in `state["messages"]`. `filter_for_llm_context()` (in `utils/message_filters.py`) **excludes every internal-scaffolding `SystemMessage`** from the response LLM's conversational context, allowlisting only the compaction summary (matched via `COMPACTION_SUMMARY_MARKER`, the message that carries compacted history). Without this, the response LLM mimics the agent's reasoning structure (`PLAN … OBSERVATION … CROSS-CHECK …`) or impersonates its role instead of answering.

3. **What the turn DID is the model's own act** (ADR-263 §23) — the response LLM never sees a tool result, so the pipeline's per-tool confirmation (« Image generated successfully and will be displayed automatically ») has no ReAct counterpart. `build_performed_actions_block` (`services/performed_actions_directive.py`, the sibling of the failures directive) reads the run's SUCCEEDED effects from the register (minus those whose manifest declares `REASON_INTERNAL_CONTEXT` — a skill activated is plumbing, not an answer), and `_build_response_chain` states them in their own system block (`response_directive_performed_actions.txt`) between the directives and the data: done with the model's own tools, an image or document among them already displayed. Never as data lines beside the answer — measured, a bare « Image générée : … » there read as somebody else's caption (a denial the person saw) or as a second image (3 answers out of 100); the directive: 0 out of 100 for both, including a caption-only answer.

4. **Single, de-duplicated stream** — LangGraph `stream_mode="messages"` emits **both** the response LLM's token deltas (`AIMessageChunk`) and the complete post-processed `AIMessage` the node returns to the `messages` channel. `StreamingService._process_messages_chunk()` streams the deltas only and skips the complete message once deltas have been seen (with a non-streaming fallback that emits it when no delta occurred), so the reply is never shown twice. The canonical post-processed content (HTML cards, psyche-tag cleanup) is still delivered by the `content_replacement` chunk after the stream loop.

## Initiative enrichment on the nominal path (ADR-070 / ADR-062)

When `INITIATIVE_ENABLED` **and** `INITIATIVE_REACT_ENABLED` are set, the nominal ReAct path routes `react_finalize → initiative → response` instead of `react_finalize → response`. The conditional edge `route_from_react_finalize` (in `nodes/routing.py`) gates this; the **draft** path (`react_execute_tools → draft_critique → initiative`) is wired independently and is never gated by the flag, so default-off (the default) is byte-identical to the pre-amendment behaviour.

The existing pipeline `initiative_node` is reused almost as-is — its pre-filter reads `query_intelligence.domains`, its execution summary reads `current_turn_registry`, and the per-request tool manifests are all already populated in ReAct. Two ReAct-specific adaptations live outside the node:

- `route_from_initiative` short-circuits to `response` in ReAct (`execution_mode == "react"`): there is no orchestrator loop to re-evaluate against, so exactly one enrichment pass runs.
- `response_node` **merges** the ReAct answer (`{turn}:react_agent`) with any Initiative entry (`{turn}:initiative`) via `_merge_react_synthesis_result` (idempotent on the react key) instead of the previous `if not agent_results` gate, which would otherwise have dropped the answer once Initiative wrote its results first. A ReAct-only `<ProactiveFindings>` prompt directive invites the response LLM to weave the proactive findings (already present via `data_for_filtering`) into the reply; the suggestion uses the existing `<InitiativeSuggestion>` injection.

One node-level fix made this work in ReAct: `_format_execution_summary` now normalizes registry items in both `dict` form (pipeline, after a checkpoint round-trip) and live Pydantic `RegistryItem` form (ReAct, built in-memory by `react_execute_tools`). It previously skipped the latter, so the summary collapsed to `"No execution results."` and the Initiative LLM declined to act.

## Turn isolation & data-precision guidance (2026-07)

Two field bugs fixed on the ReAct path (see [ADR-090](../architecture/ADR-090-Semantic-Layer-Governance.md) §4 for the second):

1. **Cross-turn `current_turn_registry` leak** — nothing purged the per-turn registry at the start of a ReAct turn, so the value restored from the previous turn's checkpoint seeded `react_execute_tools`' intra-turn accumulation, and the response node re-displayed last turn's data (e.g. the previous "4 upcoming events" answer inside a route reply — through BOTH the synthesis text and the SSE data cards). Fixes:
   - `react_setup_node` returns `current_turn_registry: {}` — per-turn purge, mirroring the pipeline where `task_orchestrator` overwrites it ("no merge for display", 2025-12-31 bugfix that had never been ported to ReAct). HITL draft resumes re-enter AFTER setup, so mid-turn items are never dropped; the cross-turn `registry` (merge reducer) is untouched for context resolution.
   - The response node's ReAct passthrough no longer falls back to the cross-turn `registry` when `current_turn_registry` is empty — that fallback tagged EVERY historical item as a registry_update of the current turn, bypassing `_filter_registry_by_current_turn`. A tool-less ReAct turn now legitimately yields no data cards (REFERENCE turns keep their dedicated `resolved_context` path).

2. **Approximate values instead of exact lookups** — the ReAct system prompt now carries a generic PRECISION rule ("memory context tells you WHO, tools give exact values — retrieve the exact value with the lookup tool BEFORE calling the consumer tool") and a `<CrossDomainDataTypes>` section fed by `generate_semantic_dependencies_for_prompt()` (the same ontology ∪ manifests links the pipeline planner receives), so e.g. a route destination is fetched from the contact's exact address rather than a city name recalled from memory.

## Token Tracking

Token tracking works for all providers through the `TokenTrackingCallback`:
- The `node_breakdown` in tracking summary aggregates tokens by node name (sum across iterations)
- For OpenAI models using the Responses API with tools, the call is redirected to Chat Completions which provides `usage_metadata` on the response

Safety limits:
- **Max iterations**: `REACT_AGENT_MAX_ITERATIONS` (default: 15)
- **Hard timeout**: `REACT_AGENT_TIMEOUT_SECONDS` (default: 120s), checked in routing function

## Skills Integration

Skills are available to the ReAct agent through the same mechanism as the pipeline:
- The filtered L1 skills catalogue is injected as a `SystemMessage` in `react_setup`
- The 4 skill tools (`activate_skill_tool`, `run_skill_script`, `read_skill_resource`, `import_user_skill` — ADR-118) are in the tool catalogue and available to the ReAct agent
- Active skill filtering uses `active_skills_ctx` (same per-request context as pipeline)

## Sandboxed Python (ADR-249)

The ReAct agent can write a short Python script and run it, to answer questions a language
model answers *plausibly* rather than correctly: arithmetic over many rows, joins by key,
timezone-aware durations, deduplication.

**No new sandbox was built.** `run_python_tool`
(`src/domains/agents/tools/python_sandbox_tools.py`) calls
`SkillExecutor.execute_source()`, which shares `_run_source_in_container()` with the rich
skills path — one implementation, therefore one set of isolation flags: throwaway container,
no Docker socket, `--network none`, read-only rootfs, uid 65534, all capabilities dropped
(SEC-001). The **legacy in-process sandbox mode is refused** for model-written code: it only
isolates when the API runs as root, an acceptable trade-off for a skill a user installed
deliberately, not for code a model wrote after reading an e-mail. Fail closed, never a
fallback.

**ReAct only, enforced twice.** The manifest
(`src/domains/agents/python_sandbox/catalogue_manifests.py`) declares
`execution_modes=frozenset({EXECUTION_MODE_REACT})` and **every** reader of the catalogue
applies `manifests_for_mode`, so the planner never sees the tool: a planner that saw it
would schedule a step execution then refuses — a dead end invented for the user. The tool
then re-reads `execution_mode` from the typed runtime context (ADR-231) at call time. One
enforcement would have been a trap; two are a contract.

**Everything enforced is published** (ADR-184): the manifest and the `<Computation>` block
state the four jobs (calculate, diagnose, fill a gap, transform), the absence of database and
writable filesystem beyond `/tmp`, the library list rendered from ONE table
(`python_sandbox/libraries.py` — every distribution pinned directly in `requirements.txt`,
imported by the CI on the lockfile and by `task sandbox:libraries:check` inside the built
image), every bound from the setting that enforces it — and say explicitly when *not* to use
the tool.

**The turn's data travels on stdin**, never copied into the source: copying would pay for
those tokens twice and truncate exactly the large cases that justify the feature. The
per-turn run budget lives in **graph state**, seeded into a ContextVar at the start of each
node execution and drained back at the end — a `ContextVar.set()` inside one asyncio task is
invisible to a sibling task, and a graph executor may run each node in its own (measured:
same task 42, separate tasks 0).

**Output is untrusted, code is auditable.** Results carry
`structured_data={"content_trust": "untrusted", ...}` exactly like an e-mail body; the
source and its stated purpose are surfaced to **administrators only**, in the debug panel's
ReAct section — for THIS turn: `react_scripts` joined `react_turn_reset()` (the thread is the
conversation, and the list used to grow for its whole life). Hiding the code would buy no
security — the model wrote it, it is already in context — and would cost all verifiability.

### Network runs (ADR-298)

A run that declares `hosts` joins the `lia-sandbox` internal Docker network, whose only routed
member is the iron-proxy sibling container: HTTPS only, through the proxy, to the declared
hosts — a raw socket, a DNS query, an undeclared host or a private address has nowhere to go.
Every declared host has one of four statuses (`egress/hosts.py`): `connector` (a host of the
person's own active API-key connectors, derived from the client classes), `operator`
(`PYTHON_SANDBOX_EGRESS_HOSTS`), `grant` (what the person allowed before) or `unknown`.

- **A credential never enters the container.** The script reads a per-run token from
  `os.environ["LIA_KEY_<CONNECTOR>"]` and puts it in the carrier the client class declares
  (header or query parameter); the proxy swaps it for the person's real key on that host
  alone. The ruleset is rendered from a Redis registry of live runs (`egress/registry.py`,
  `egress/publisher.py`) and reloaded through the management API before the container
  starts; a reload the proxy refuses is a run that never starts (fail closed, counted as
  `proxy_unavailable`). Measured on dev: `task sandbox:egress:probe`.
- **An unknown host is asked, with three answers** — allow with the turn's data, allow
  without it (stdin then carries no items), refuse — through a `SANDBOX_EGRESS` card
  (`egress/draft.py`). The question is settled IN the loop (`nodes/react_egress_question.py`):
  the node raises the interrupt like a mutation tool's confirmation, and on resume re-invokes
  the SAME call with the answer bound to it (`tool_path.approved_for_call`), so the model goes
  on with its plan — a dispatched draft would have answered from the run's result and dropped
  every later step (measured 2026-09-18). A question costs none of the turn's runs. The answer
  becomes a grant (`sandbox_egress_grants`); past `PYTHON_SANDBOX_MAX_GRANTS_PER_USER` it holds
  for its run alone. The person reviews and revokes grants from *Settings › Sandbox network*.
- **The prompt offers what the account may reach** (`react_prompt.network_available`): the
  network section of `<Computation>` is rendered only when the egress capability is on, and
  lists the reachable hosts with their token variable and carrier. Measured 2026-09-18: told
  « `LIA_KEY_X` in the header », the model sent the variable's NAME as the value; the line now
  spells `os.environ[...]` and the next turn reached Brave with the swapped key.
- **A network run is an action** claimed before the container starts and closed from the
  result (`effects/in_turn_effects.py`, capability `python_sandbox_network`); a run without
  hosts stays pass-through, as ADR-249 made it.

## Configuration

```env
# .env
REACT_AGENT_ENABLED=true              # Feature flag
REACT_AGENT_MAX_ITERATIONS=15         # Max ReAct loop iterations
REACT_AGENT_TIMEOUT_SECONDS=120       # Hard timeout for entire execution
REACT_AGENT_MAX_TOOLS=100             # Safety-net cap on bound tools (resolved count, post-expansion)
REACT_TOOL_SEMANTIC_TOP_K=40          # Semantic slice of the global ranking bound beside domains + family coverage (0 = every tool, cap alone) — ADR-293
REACT_CROSS_TURN_CACHE_ENABLED=false  # Exchange rhythm of an account that never chose (true = frequent: every tool, context after the question, history blocks) — ADR-308, ADR-311
REACT_CROSS_TURN_CACHE_MAX_WINDOW_FRACTION=0.5  # Beyond this share of the slot's window, a turn keeps the relevance selection
REACT_CROSS_TURN_HISTORY_BLOCK_FRACTION=0.5  # For frequent exchanges, the ReAct loop's history drops by blocks of this share of its window — ADR-309
REACT_AGENT_HISTORY_WINDOW_TURNS=5    # Conversation history window
REACT_RECOVERY_PASSES_MAX=1           # Recovery passes a declared gap buys per turn (0-3, 0 = off) — ADR-310
REACT_MCP_EXPAND_ITERATIVE_ENABLED=true  # Expand iterative USER MCP servers into individual tools (false = keep task tool; MCP App servers always keep it)
INITIATIVE_REACT_ENABLED=false        # Run the Initiative phase on the ReAct nominal path (ADR-070; pipeline uses INITIATIVE_ENABLED)

# Progress-earned budget (ADR-248)
REACT_PROGRESS_EXTENSION_ENABLED=true       # Productive iterations buy more iterations
REACT_PROGRESS_EXTENSION_MAX_ITERATIONS=10  # Ceiling on what progress can buy

# Sandboxed Python (ADR-249) — requires the container skills sandbox
PYTHON_SANDBOX_TOOL_ENABLED=true      # Off means the tool does not exist at runtime
PYTHON_SANDBOX_MAX_RUNS_PER_TURN=5    # Bounds a repair loop (1-20): an attempt, corrections, a verification
PYTHON_SANDBOX_RATE_LIMIT_CALLS=20    # Per user, per window
PYTHON_SANDBOX_RATE_LIMIT_WINDOW=300  # Window, seconds

# Network runs (ADR-298) — need the `egress` service of the compose file
PYTHON_SANDBOX_EGRESS_ENABLED=false   # Deployment ceiling; the capability switch is read at the act
PYTHON_SANDBOX_EGRESS_ASK_ENABLED=true  # Ask the person about an unknown host (false = refuse it)
PYTHON_SANDBOX_EGRESS_HOSTS=[]        # Operator allowlist, JSON list of exact lowercase hostnames
PYTHON_SANDBOX_MAX_HOSTS_PER_RUN=5    # Published on the manifest (ADR-184)
PYTHON_SANDBOX_MAX_GRANTS_PER_USER=50 # Past it an approval holds for its run alone
PYTHON_SANDBOX_NETWORK_TIMEOUT_SECONDS=60  # A network run's whole budget
```

LLM type: `react_agent` — configurable in admin LLM config panel.
Default: the `react_agent` entry of `LLM_DEFAULTS` (`apps/api/src/domains/llm_config/constants.py`); a deployment's own configuration lives in `llm_config_overrides`.

## Streaming Step Visibility (v1.16.2)

During ReAct execution, the frontend displays accumulated execution steps in real time:

1. **Node-level steps**: Each ReAct node transition (`react_setup` → `react_call_model` → `react_execute_tools` → `react_finalize`) emits an `execution_step` SSE event via the "updates" stream mode.

2. **Per-tool steps**: When `react_call_model` produces an AIMessage with `tool_calls`, the streaming service inspects the state delta and emits individual `execution_step` events for each tool (e.g., "Retrieving contacts...", "Retrieving events..."), using the tool catalogue's `DisplayMetadata` for emoji and i18n_key.

3. **Reasoning detail**: The AIMessage content (reasoning text) from `react_call_model` is extracted, cleaned of markdown formatting, truncated to 120 characters, and included as a `detail` field in the node-level execution_step event.

4. **Frontend accumulation**: Steps are accumulated in a multi-line progress message (not replaced). All steps remain visible until the first response token arrives. Deduplication by `i18n_key` prevents duplicates.

## Key Files

| File | Purpose |
|------|---------|
| `src/domains/agents/nodes/react_nodes.py` | 4 node functions, iteration budget, exit reasons |
| `src/domains/agents/nodes/react_context.py` | Memory/context blocks, at pipeline parity (ADR-248) |
| `src/domains/agents/nodes/react_recovery.py` | The recovery protocol: the declaration's reader, the predicate, the node, the transient directive, the outcome (ADR-310) |
| `src/domains/agents/tools/python_sandbox_tools.py` | `run_python_tool` + per-turn run budget (ADR-249) |
| `src/domains/agents/python_sandbox/catalogue_manifests.py` | Manifest: ReAct-only, published bounds |
| `src/domains/agents/tools/react_tool_wrapper.py` | Tool wrapper: per-item projection under a token budget, stated cut, registry collection (ADR-286) |
| `src/domains/agents/services/react_tool_selector.py` | Tool selection by relevance: detected domains, family coverage, semantic slice, stable-sort cap (ADR-293) |
| `src/domains/agents/services/performed_actions_directive.py` | The turn's succeeded acts, from the register, stated to the response model as its own (ADR-263 §23) |
| `src/domains/agents/prompts/v1/react_agent_prompt.txt` | System prompt |
| `src/domains/agents/prompts/v1/react_recovery_directive.txt` | What a recovery pass tells the model (ADR-310) |
| `src/domains/agents/nodes/routing.py` | `route_from_react_call_model()` |
| `src/domains/agents/graph.py` | Graph wiring (edges + conditional) |
| `src/domains/agents/models.py` | State fields (react_*, schema 1.2) |
| `src/domains/agents/utils/execution_metadata.py` | Debug panel display metadata |
| `docs/architecture/ADR-070-ReAct-Execution-Mode.md` | Architecture decision record |
| `docs/architecture/ADR-248-React-Memory-Parity-And-Progress-Earned-Budget.md` | Memory parity, truncation honesty, earned budget |
| `docs/architecture/ADR-249-Ephemeral-Python-In-The-Existing-Sandbox.md` | Sandboxed scripts |
| `docs/architecture/ADR-310-ReAct-Turn-Judged-On-Its-Result.md` | The recovery pass, the ladder, absolute dates |
