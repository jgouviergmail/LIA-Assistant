# ADR-308 — One flag makes a ReAct turn's prefix the previous turn's: every tool, and the turn's context after the question

**Status**: accepted — 2026-09-23 (owner arbitration: one flag, off by default, one behaviour for every model)
**Amended**: 2026-09-24 by [ADR-311](ADR-311-Exchange-Rhythm-Is-The-Persons-Choice.md) — the choice is the PERSON's (Settings › Usage preferences: frequent or occasional exchanges), read once per turn; the flag becomes the default of an account that never chose, and the context after the question travels with every tool, as measured here
**Amends**: ADR-293 (the relevance selection stays the default and becomes the fallback), ADR-169 (the turn's system blocks lead the payload — unless the flag moves the context), ADR-306 (the static-prefix breakpoint and the prompt cache key this relies on)

## Context

A ReAct call sends `[tools][system][history][question][loop]`. Measured in production
on 2026-09-23 (DeepSeek, the main account): the first call of a turn carries about
40K tokens — 28K of them the schemas of the ~82 tools the relevance selection bound
out of 212 — and reads **4.9 %** of them from the provider's cache, where the later
calls of the same turn read 87.7 %. Nothing crosses from one turn to the next, for
three reasons, each measured:

1. **The tool list changes every turn.** The relevance selection (ADR-293) binds what
   the question needs: two consecutive turns share about two thirds of their tools
   (Jaccard 0.67), and Anthropic and OpenAI put the tools FIRST in the prefix they
   cache — a changed list is a cold turn.
2. **The system prompt ends with the turn's own data.** The date, the domains' type
   links, the memories, the knowledge, the skills follow `DYNAMIC CONTEXT`; DeepSeek's
   cached prefix starts with the system prompt and puts the tools AFTER it, so even an
   identical tool list is never read again there.
3. **The history window slides by one turn on every turn** (five turns kept): in a
   long-lived thread the history is never a reusable prefix. That is not a lever.

A benchmark measured what binding every tool would buy (2026-09-23, 396 real turns on
the providers' APIs, 14.80 USD): the real selector and the real prompt, a sliding
five-turn window, the same synthetic tool results for every arm, turns run warm
(inside every cache lifetime) and cold (a fresh prefix per turn), then weighted by the
production gaps between consecutive ReAct turns (391 pairs over 60 days: 57 % within 5
minutes, 74 % within 30, 78 % within an hour, 99 % within a day). Cost per turn, a
114-tool account:

| Model (cache lifetime) | Today (relevance) | Every tool, context in place | Every tool + context after the question | Profitable above this warm share |
|---|---|---|---|---|
| Claude Sonnet 5 (5 min) | 0.124 USD | −18 % | −18 % | 41 % |
| gpt-5.6-luna (30 min) | 0.0060 USD | −37 % | −34 % | 40 % |
| deepseek-flash (hours) | 0.0049 USD | **+44 %** | **−42 %** (−66 % if the cache lives a day) | 40 % |
| qwen3.7-plus (implicit cache) | 0.0141 USD | −25 % | −18 % | 29 % |
| qwen3.5-plus (no prompt cache) | 0.0072 USD | +18 % | — | never |

With 199 tools (the native catalogue plus the real MCP servers of production's main
account): Claude −7.5 % (break-even 52 %), GPT-5.6 −30 %, DeepSeek +65 % with the
context in place and −41 % with it moved (−71 % at a day's lifetime). The first tool
chosen was right 12/12 for Claude in every arm and 11-12/12 for GPT-5.6 and DeepSeek —
no measurable degradation on a sanity check of twelve questions, which is not an
evaluation; Qwen without reasoning degraded (qwen3.5-plus 9/12 → 5/12). A turn took
0.5 to 1 s longer, 4.5 s with GPT-5.6 and 199 tools. And no provider refuses more than
128 tools: 215 bound tools were accepted by DeepSeek, Qwen, OpenAI (Responses API),
Anthropic and Gemini.

## Decision

1. **`REACT_CROSS_TURN_CACHE_ENABLED`, off by default.** Off, nothing changes. On,
   `ReactToolSelector.select` binds every available tool in registration order — the
   router's ranking and `REACT_TOOL_SEMANTIC_TOP_K` are ignored — and
   `react_call_model_node` places the turn's context after the question. One behaviour
   for every model (owner arbitration): the gain is positive on every measured model
   that has a prompt cache, and a model without one pays more — the flag is the
   operator's.
2. **The leading system message is the static prompt, ending on its marker line** —
   where the Anthropic and OpenAI payload shapers cut their breakpoint and where the
   OpenAI cache key stops (ADR-306). The turn's context — the marker line, the prompt's
   dynamic part, then every context block in its order — comes right after the
   question and before the loop's own messages, so every iteration of the turn keeps
   the same prefix (`nodes/react_turn_layout.py`).
3. **« After the question » has one shape per provider, declared once**
   (`CONTEXT_PLACEMENT`, checked at boot against `ProviderType`): a system message right
   after the question for OpenAI, DeepSeek and Qwen, the shape measured on their APIs;
   the context appended to the question's own message, as text, for Anthropic (a system message
   that is not first is refused), Gemini (`langchain-google-genai` merges a later
   system message back into the system instruction — the data would never move),
   Ollama (a mid-conversation system role is left to each model's template) and
   Perplexity (the system first, the roles alternating). An unknown provider gets the
   question tail, which every client accepts.
4. **When every tool cannot be bound, the turn keeps the relevance selection**, and the
   fallback is counted by reason (`react_cross_turn_cache_fallback_total`, dashboard 20):
   `cap` — the account holds more tools than `REACT_AGENT_MAX_TOOLS`, whose bound rose
   from 200 to 400: production's main account already holds 212 tools, and the owner
   asked for room as MCP servers are added (a catalogue that size, about 140K tokens
   of schemas, is meant for a model with a 1M window); `window` — the schemas exceed
   `REACT_CROSS_TURN_CACHE_MAX_WINDOW_FRACTION` of the slot's own window (0.5 by
   default: a 32K local window cannot hold the 36K tokens of the native catalogue,
   a 1M window holds 400 tools with room to spare). The context placement still
   follows the flag.
5. **Nothing reaches the checkpoint.** The layout is composed at call time from
   `react_system_blocks` and the windowed history; a question the context closes is a
   copy.

## Consequences

- **Measured through the real chain on dev** (2026-09-23, six ReAct turns, 141 tools
  bound on every turn, 45 059 tokens of schemas, no fallback): the first call of a
  turn following another read **94.6-95.3 %** of its prompt from the cache on
  deepseek-flash (0.0006 USD, against 0.0060 on average for a first call over the
  previous fourteen days) and **86.6-87.2 %** on gpt-6-sol — the 34 035 tokens of
  tools and static prompt — at 0.020 USD, against 0.049 for the first calls of three
  gpt-6-sol turns under the relevance selection the same morning, each read at 0 %
  though 30 s apart. The cold first turn paid the catalogue: 0.0071 USD on DeepSeek,
  0.098 on gpt-6-sol, 37 954 tokens written at 1.25x — exactly what the next call
  read. The first call got faster on DeepSeek (1.5 s against 2.6 s on average) and
  slower on gpt-6-sol (4.7 s against 4.0 s; later calls 7.1 s against 4.1 s, on five
  calls).
- **Production** (DeepSeek, main account): with the flag and `REACT_AGENT_MAX_TOOLS`
  covering its 212 tools, about −41 % per ReAct turn, up to −71 % if DeepSeek's cache
  outlives the gaps. The loop spent about 2.85 USD over the week of 2026-09-14: at
  today's volume the stake is one to two dollars a week.
- **A cold turn costs more**: once the cache has expired, a turn writes the whole
  catalogue (Claude with 199 tools: 0.33 USD against 0.20 today). The measured gaps
  keep the average positive; an account whose turns are hours apart pays more.
- **A model without a prompt cache pays more under the flag**, and full price on every
  iteration without it. Every slot is configurable, so the flag is judged on its average
  over the cache mechanisms, never on one model; measured on Qwen 3.5 and 3.6 on the
  Frankfurt endpoint (no cached token on two identical requests; the vendor's
  implicit-cache list agrees). Explicit cache markers, where a provider offers them,
  would be a separate lever, useful to the relevance selection as well.
- **Not measured**: Gemini, Ollama, Perplexity and the OpenAI models before GPT-5.6
  under the flag, and whether a provider accepts more than the 215 bound tools
  measured. On Anthropic the benchmark measured the context after the question
  as a separate text block, before the development account's credit ran out; the
  shipped form appends it to the question's text (a list of parts would have hidden
  it from the delivered-context metric, which counts text content only), and it is
  proved by the client's own formatter and the payload shaper in unit tests — no
  Anthropic call can prove it.

## Rejected

- **A per-model `auto` mode** binding every tool only where it was measured profitable:
  the owner chose one flag with one behaviour.
- **Moving the context only where the system precedes the tools** (DeepSeek): same
  arbitration; the move was measured neutral on Claude and slightly worse on GPT-5.6
  (−34 % instead of −37 %).
- **Binding past the cap, or cutting the catalogue in registration order**: the first
  ignores the operator's bound, the second is ADR-293's defect — the same families
  dropped on every turn.
- **A second leading system message after the static one**: Anthropic merges leading
  system messages into one system prompt and DeepSeek's prefix puts them before the
  tools; the data would still precede the tools there.
- **The 1-hour Anthropic TTL**: rejected by ADR-306 — twice the write price for a reuse
  that happens within five minutes.

## References

- `apps/api/src/domains/agents/nodes/react_turn_layout.py` — the placement table, the composition
- `apps/api/src/domains/agents/services/react_tool_selector.py` — `_every_tool`, `every_tool_token_budget`
- `apps/api/tests/unit/domains/agents/nodes/test_react_turn_layout.py`,
  `apps/api/tests/unit/domains/agents/services/test_react_tool_selector_every_tool.py`,
  `apps/api/tests/unit/domains/agents/nodes/test_react_cross_turn_cache_wiring.py`
- [ADR-169](ADR-169-React-System-Blocks-Are-State.md), [ADR-293](ADR-293-React-Tools-Bound-By-Relevance.md), [ADR-306](ADR-306-Claude-Request-Surface-And-Billed-Prompt-Cache.md)
