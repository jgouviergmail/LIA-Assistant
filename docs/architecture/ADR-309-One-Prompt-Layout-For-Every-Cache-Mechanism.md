# ADR-309 — One prompt layout for every cache mechanism: stable before volatile, one boundary, no write nobody reads

**Status**: accepted — 2026-09-23 (owner rule: every provider and model is configurable, so no decision reasons on one of them; aim at the best AVERAGE over usages and model choices)
**Revised**: 2026-09-24, after the owner's test turns — the response sends its conversation once and keeps its sections' order (4), the history blocks are the loop's alone (6), the journal extraction gains the boundary (2)
**Amends**: ADR-306 (the explicit request mode, a second payload adapter), ADR-308 (the loop's history dropped by blocks under the same flag), ADR-284 (the response's conversation sent once, its two scaffolds in a lines file), ADR-064 (the analyst persona's place in the extraction prompt), ADR-147 (the grounding block's own budget)

## Context

ADR-308 made a ReAct turn's loop reuse the previous turn's prefix. The rest of the
turn did not move, and measured on the owner's six test turns of 2026-09-23 it
costs about the same whatever the loop's model: 0.005 to 0.006 USD per turn —
6 % of a turn whose loop runs on an expensive model, 58 % of one whose loop runs
on a cheap one. Five causes, each measured:

1. **The response prompt's dynamic tail changes on every turn.** On a provider
   that caches prefixes by itself, the response read back exactly its static
   part — 24.5 % of 12,020 tokens, the 2,824 static ones. And it carried the
   conversation TWICE: as a `<History>` text in the system prompt, each message
   cut at 500 characters, and as the conversation's own messages, whole.
2. **A single call sends its whole prompt as ONE user message.** The ADR-306
   payload shapers mark instruction roles only, so the static part of an
   extraction, of the query analyzer or of the initiative was never marked. On
   gpt-6-luna every extraction read 0 % of its prompt and wrote ALL of it at
   1.25x — to the cent: the journal extraction billed 0.005001 USD for 37,293
   tokens, exactly 37,293 × 1.25 × 0.10 USD/M plus its output.
3. **A request no tool loop can continue still wrote its tail.** GPT-5.6/6's
   implicit breakpoint writes everything up to the last message at 1.25x; with no
   tool bound no later call extends that prompt (the query analyzer's 24,140
   unread tokens: billed at exactly 1.25x).
4. **The history window slides by one turn on every turn** (ReAct loop: 5 turns;
   response: 10), so its first message changes every time and nothing reads the
   history again once a thread is longer than its window.
5. **Two providers were not translated at all.** Qwen 3.5 and 3.6 (Plus and
   Flash) have NO implicit cache in any DashScope region — only an explicit one
   (`cache_control`, written at 125 %, read at 10 %, five minutes). And every
   Gemini node of production read 0.0 % for months: LIA reads the cache
   correctly (12,262 tokens read through LIA's own client, 4,056 recorded in
   production in May on gemini-3.5-flash), but gemini-3.7-flash read nothing
   below a request size far above its documented 4,096-token minimum — no read
   up to 10.3K tokens over four request shapes and eleven attempts (3 to 15 s
   apart, divergent and extending tails alike), ~12.3K read at 17.8K — while
   production's Gemini prompts averaged 0.4K to 5.4K.

## Decision

**One rule for every call of a turn: stable before volatile, and no cache write
nobody reads. Each provider adapter translates the one boundary into its own
mechanism; a model without a cache pays exactly what it paid.**

1. **The boundary has one reading**: `core/prompt_layout.split_at_marker` — the
   static part runs to the end of the `DYNAMIC_CONTEXT_MARKER` line. The ADR-308
   turn layout reads it too.
2. **A single call sends its static part as the system message**
   (`single_call_messages`): the query analyzer, the initiative, the memory,
   interest and journal extractions — held by an AST guard that reads the CALL
   (`tests/unit/core/test_single_call_sites_guard.py`). The HITL classifier
   already sends a system message. The journal extraction had no marker — the
   turn's data sat between its rules and its analyst persona: the rules, the final
   check, the output format and the persona (placed by `{analyst_persona}`, which
   the renderer refuses to find missing) now come first, 2,545 tokens; the turn's
   data follows the marker, closed by a one-line reminder of the check and the
   output. The model now reads the language's name, and the size warnings are the
   consolidation's own lines (ADR-284).
3. **A request no tool loop can continue writes its declared breakpoints only**:
   GPT-5.6/6 requests with no tool bound go in explicit mode
   (`prompt_cache_options.mode = explicit`); a tool-bound request keeps the
   implicit breakpoint a loop reads through (ADR-306).
4. **The response sends its conversation once**, as the conversation's own
   messages, whole. The `<History>` text is gone: it repeated the same window cut
   at 500 characters per message, dropped the compaction summary, and escaped the
   plan-rejection filter the messages go through. The dynamic sections keep their
   attention order: each changes on every turn (the « psychological profile » is
   a memory retrieval for the current query), so no order reads more from a cache
   — the response's cache is its static part. The two sentences the node wrote in
   Python (the current-turn data prefix, the language reminder) are in
   `response_prompt_lines.txt` (ADR-284); the prefix, which precedes the
   conversation, no longer calls it « above ».
5. **The initiative's tool catalogue and interests open its dynamic part** — after
   the marker, where the static-part hygiene guard wants per-turn content.
6. **Under `REACT_CROSS_TURN_CACHE_ENABLED`, the ReAct loop's history is dropped
   by blocks** (`REACT_CROSS_TURN_HISTORY_BLOCK_FRACTION`, 0.5): it keeps between N
   and N + block − 1 turns, so each turn's history extends the previous one. One
   implementation: `get_windowed_messages(block_size=…)`. The response node keeps
   sliding: its conversation follows the turn's own context, which no cache reads,
   so blocks would only add tokens there.
7. **Qwen's explicit cache is marked** (`providers/qwen_chat.py`,
   `ChatQwenCached`) on the DECLARED families without an implicit cache (3.5 and
   3.6, Plus and Flash): the static system prefix — tools included, DashScope
   counts them there — and, inside a tool loop, a rolling marker on the last
   message. DashScope reports the write as `cache_creation_input_tokens`, which
   langchain does not map: the client copies it to the standard field, so the one
   usage reader bills it, at the provider's 1.25 multiplier. A model WITH an
   implicit cache keeps it: explicit only beats implicit from four reads per five
   minutes. qwen3.6-flash's cached rate is corrected at its source to the explicit
   hit (10 %) — it had shipped the implicit 20 % the same day, unreleased.

## Consequences

- **Measured through the real chain on dev** (2026-09-23): qwen3.6-plus wrote
  5,191 tokens then read 5,191; qwen3.5-flash 5,198 then 5,198 — both read nothing
  before; gpt-6-luna in explicit mode wrote 2,721 tokens — the static prefix
  alone, not its 2,869-token prompt — then read 2,721 and wrote nothing.
- **Measured on the owner's turns** (2026-09-23, four ReAct and three pipeline
  turns, flag on, no error): from their second call the single calls on
  gpt-6-luna read 53-55 % (query analyzer), 40-52 % (memory) and 73 % (interests)
  with no write surcharge left; the ReAct loop on deepseek-flash read 94-95 %
  after its first call; the response read 22-31 % — its static part, which is
  what revised 4 — and the journal 0 %, which revised 2.
- 1 to 5 add no token anywhere, and 4 removes some: up to a window of messages,
  500 characters each, on every response call. 6 trades about a fifth more loop
  history, on average, for a history read again two turns out of three; a model
  without a cache pays that fifth.
- The response prompt keeps its order; what changed is that the conversation
  reaches the model once, whole, and that the plan-rejection filter covers all of
  it.
- **Not measured**: Anthropic (no credit for this work — unit tests only). A
  response whose conversation precedes the turn's context (ADR-308's move applied
  to the response node) would make its history readable again; not done — it
  changes where the model reads the turn's data, and needs its own measurement.

## Rejected

- **A stable initiative catalogue of every eligible tool under the flag**:
  measured 39 tools and 6,043 tokens against 10-20 tools and 1,501-3,872 tokens
  today, and it would reopen the executed domains the node excludes on purpose;
  with 5 the catalogue is already read again when a turn's domains repeat.
- **Gemini's explicit `cachedContents`**: an hourly-billed resource per prefix,
  for prompts below the size its implicit cache serves.
- **Marking the Qwen models that have an implicit cache**: see 7.
- **The response's sections reordered stable-first, and its history dropped by
  blocks** (written, then reverted after the owner's turns): the « profile » is
  retrieved per query and the history was also in the message array, so nothing
  in the tail stayed the same from one turn to the next.
- **A per-model tuning or a measurement campaign per provider**: the owner's rule.

## References

- `apps/api/src/core/prompt_layout.py`, `apps/api/src/infrastructure/llm/providers/openai_payload.py`,
  `apps/api/src/infrastructure/llm/providers/qwen_chat.py`,
  `apps/api/src/domains/agents/utils/message_windowing.py`,
  `apps/api/src/domains/agents/prompts/v1/response_context_sections.txt`,
  `apps/api/src/domains/agents/prompts/v1/response_prompt_lines.txt`,
  `apps/api/src/domains/agents/prompts/v1/journal_introspection_prompt.txt`,
  `apps/api/src/domains/journals/prompt_builders.py`
- [ADR-306](ADR-306-Claude-Request-Surface-And-Billed-Prompt-Cache.md), [ADR-308](ADR-308-ReAct-Cross-Turn-Prompt-Cache.md), [ADR-284](ADR-284-Prompt-States-What-The-Code-Enforces.md), [ADR-064](ADR-064-Journal-Analyst-Persona.md), [ADR-147](ADR-147-Recent-Entities-Grounding.md)
