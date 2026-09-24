# ADR-306 — The Claude request surface is declared once; the prompt cache is shaped, and billed, the way the vendor measures it

**Status**: accepted — 2026-09-23 (the OpenAI half, section 7, the same day)
**Amends**: ADR-087 (the thin `ChatOpenAICached`), ADR-244 (model capability catalogue), ADR-245 (one reasoning intent, one seam), ADR-263 lot 7 (Article-12 inference parameters), ADR-272 (every euro the platform pays is counted), ADR-284 (the `DYNAMIC CONTEXT` convention of the versioned prompts)

## Context

Eight Claude models the Claude API serves were missing from the catalogue:
`claude-fable-5-1`, `claude-fable-5`, `claude-opus-5-5`, `claude-opus-5`,
`claude-sonnet-5`, `claude-opus-4-8`, `claude-opus-4-7` and `claude-sonnet-4-5`. Adding
rows was the small part. Each generation accepts a different request, and every
difference was **measured on the Claude API before it was written down** (2026-09-23,
validation requests at `max_tokens` 0 or 16, about 0.09 USD in all):

| Fact | Where it bites |
|---|---|
| A non-default `temperature` is a 400 (« `temperature` is deprecated for this model ») from Opus 4.7 on; `top_p` next to `temperature` is a 400 from Claude 4.5 on | every slot on a new model |
| A forced `tool_choice` is refused by Fable 5.1 and Opus 5.5 | structured output's forced-tool door |
| Thinking comes in six shapes: none (3.5), a token budget (4.5), adaptive (4.6), adaptive opt-in with `display` (Opus 4.7/4.8), on unless disabled (Opus 5, Sonnet 5), always on — no off switch (Fable 5, Fable 5.1, Opus 5.5) | the reasoning family, the admin ladder |
| A request naming no depth runs at `high` — `medium` on Opus 5.5 — wherever thinking is on by default | the thinking-budget guard |
| Fable 5.1 and Opus 5.5 bind a thinking block to the conversation that produced it: once the history before it changed — the system prompt LIA rebuilds every turn is enough — an account created from 2026-08-31 gets a 400; the `thinking-binding-controls-2026-08-01` beta with `prefix_mismatch_behavior: "drop_block"` drops the block instead | every multi-turn conversation |
| `ChatAnthropic` publishes `output_config` to the callbacks but not its `effort` field | the Article-12 register never saw the depth |

Five defects were found on the way, the last one on OpenAI's side:

1. **The context-window table handed 200K to Opus 4.7 and 4.8** — `claude-opus-4` came
   before the newer names it prefixes — and 200K to the Opus/Sonnet 4.6 pair, whose
   window is 1M.
2. **The prompt cache paid only on half the turns.** Every turn that carries agent
   results has TWO system messages, which langchain merges into a list of blocks; the
   breakpoint sat on the last block — the turn's data. Measured on Sonnet 5 with the
   real `response` prompt: the second call read 0 cached tokens and REWROTE 5,222 at
   1.25x, where a single system block read 5,074 and wrote 88. A rolling breakpoint was
   also written on every single-shot call, whose tail is never read again.
3. **A cache write was billed at the input price.** Claude bills it at 1.25x (the
   5-minute TTL); the ledger priced the written tokens as plain input — 25 % short on
   every write, silently.
4. **Cached tokens were billed twice on four surfaces, every provider.**
   `TokenCaptureHandler` — a ninth copy of the usage arithmetic ADR-272's amendment
   thought it had closed — handed the RAW input (cache reads included) to callers
   that priced `tokens_cache` on top: the heartbeat decision, the open-loop
   extraction, the meeting minutes and the relationship debrief's displayed cost. And
   the relayed peer message was tracked with `model_name=None`: priced at zero.
5. **GPT-5.6 and GPT-6 rewrote their whole prompt on every call.** Those two OpenAI
   generations cache by breakpoint and bill a write at 1.25x; the breakpoint OpenAI
   places by default ends after the turn's data, so a call sharing the static part with
   the previous one read 0 tokens and rewrote 2,873 (gpt-6-luna, the real `response`
   prompt) — and the ledger priced the rewrite as plain input.

## Decision

### (1) One declaration of the Claude request surface

`core/claude_surface.py` holds `CLAUDE_SURFACES`, one row per generation — ordered
prefixes, the thinking shape, the implicit depth, whether sampling and a forced tool
are accepted, whether thinking blocks are bound to their conversation — and
`claude_surface(model)` answers for any name; an undeclared Claude name gets the
strictest answer (no sampling, no forced tool). It imports nothing from `src`. Every
reader asks it rather than a model name: the reasoning rules (`_claude_profile`
derives the family from the row), the adapter's sampling decision
(`anthropic_kwargs.prepare_anthropic_kwargs`, extracted so `adapter.py` stays under
its size cap), the structured-output door, and the admin write path's temperature lock
(`sampling_omitted`). A guard test holds the table against every measured model,
dated snapshot names included.

### (2) Reasoning: a family for the display-era generations

`anthropic_adaptive_display` (ADR-245) renders a level as
`thinking: {type: adaptive, display: summarized|omitted}` plus `effort`, `none` as
`thinking: {type: disabled}` where the generation can switch it off, and
`provider_default` as nothing. `display` follows the intent's `exclude_from_output`.
The ladder is the Models API's (`low…xhigh…max`; no `none` on always-on generations,
so the admin UI never offers an off switch the API refuses), and
`ReasoningProfile.implicit_level` states the depth an empty request runs at — declared
only where the vendor documents it, so no other family changes. The effort travels in
`output_config` (merged with any `output_config` the escape hatch set), which is what
`ChatAnthropic` publishes: `inference_params` reads `output_config.effort` and a
disabled `thinking`, so the Article-12 row now carries the depth.

### (3) What each generation refuses is never sent

No `temperature` on a generation that refuses sampling, whatever the slot says, and
none while thinking is on (the older rule); `top_p` and the penalties never reach a
Claude model. Where a forced tool is refused, structured output takes the auto-tool
door directly — never a forced attempt that fails first. On the binding generations
the request carries the beta header and `block_binding.prefix_mismatch_behavior:
drop_block`, as a safety net for the one case the payload policy cannot see (a history
the state reducer trimmed in the middle of a tool loop).

### (4) The payload is shaped for the cache (`providers/anthropic_payload.py`)

The factory's request-payload hook runs ONE policy, `shape_claude_payload`:

- **The static prefix is marked wherever it is.** The system prompt is split at
  `DYNAMIC CONTEXT` whether it arrives as a string or as a list of blocks; a constant
  block before the prompt joins the cached prefix; a breakpoint a caller placed is
  kept. A prompt without the marker gets no breakpoint (ADR-284's convention).
- **The rolling breakpoint only where it is read**: a request offering more than one
  tool, or carrying a tool result, is a loop and gets the root-level automatic
  breakpoint; a single call does not. At four explicit breakpoints nothing is added
  (automatic plus four is a documented 400).
- **A previous turn's thinking is not replayed.** Thinking blocks of assistant turns
  before the last real user message are removed (the current tool loop keeps its own,
  as the API requires). On the binding generations a replayed block is a 400; on the
  generations that keep previous thinking it is billed as input on every later turn.
- **Only the 5-minute TTL is written** (measured: 89 % of LIA's cache reuse happens
  within five minutes); a test holds every breakpoint the policy writes to
  `{"type": "ephemeral"}`.

### (5) A cache write is billed at its price, on every path

`UsageTokens.cache_write` is the fourth count of the one usage reader: the part of
`prompt` written to the provider's cache. It is read wherever it is reported — the
generic `cache_creation` (what a call WITHOUT tools reports: measured, 5,076 written
tokens and no TTL keys) and the TTL breakdown langchain-anthropic fills when the
response carries one, which a TOOL-BOUND call does (measured: 23,097 under
`ephemeral_5m_input_tokens`, the generic key zeroed) — both shapes reach the ledger,
and nothing counts twice.
The count is neutral; **what a write costs is the tariff's**:
`CachedModelPrice.cache_write_multiplier`, set from the model's provider when the
price index is built — 1.25 for every Anthropic tariff
(`PROMPT_CACHE_WRITE_MULTIPLIER`) and every OpenAI one (section 7), 1.0 elsewhere.
`get_cached_cost_usd_eur`
adds `writes × input × (multiplier − 1)`, the input price being a time slot's where
one applies.

Every door that turns counts into euros takes the writes —
`get_cached_cost_usd_eur`, `record_node_tokens`, `track_proactive_tokens`,
`record_instance_llm_spend`, the metrics cost — and the carriers that hold counts
between a call and its price carry them (`TokenExtractor`, `TokenCaptureHandler`,
`ProactiveTaskResult`, `TokenAccumulator`, the heartbeat's two generators, the
meetings' `SynthesisUsage`, telephony's `SynthUsage`, the reminder's result, the
interest analysis and its Redis round trip, and the display summary `LLMUsage`).
`test_cache_write_reaches_every_price` walks `src/` and refuses a call to a pricing
door that does not pass the writes explicitly — `0` where the priced thing has no
prompt cache (characters, embeddings), where the explicit zero is the decision.

`TokenCaptureHandler` now counts through the one reader (cache reads out of
`tokens_in`), which ends the double billing of cached tokens on its four surfaces;
telephony's own subtraction went with it. The relayed peer message names the model
that answered. The two near-identical interest recorders became one that takes a
`UsageTokens` — the file had grown past its size cap. `calculate_total_cost_from_logs`,
which rebuilt costs from token columns and had no caller, is deleted: a cost rebuilt
from counts can no longer be right, since the write surcharge is not a column.

### (6) The catalogue, the prices, and the guards on the write path

The eight rows reach every instance by the reference seed AND migration
`c3e7a1f5d9b2` (production never replays the seed), provenance `verified`, guarded
equal; each tariff is the pricing page's (cache hits at 0.1x, 0.025x on Fable 5.1,
0.05x on Opus 5.5, stored as the cached price). A guard holds every Claude row's
sampling flags to the surface and its ladder to the family. The context-window table
lists the newer names first. `validate_thinking_token_budget` reads an empty level as
the profile's implicit depth, so a slot on an always-on or default-on generation with a
small `max_tokens` is refused like any heavy one — and the admin toast names that depth
instead of advising an off switch the model does not have. The admin UI documents the
three new families (`anthropic_4_7`, `anthropic_5`, `anthropic_always_on`).

### (7) OpenAI: the writes are priced, the static prefix is marked where the model accepts it

From GPT-5.6 on, OpenAI caches a prompt by breakpoint and bills a write at 1.25x the
input price (a 30-minute TTL, its only value); earlier models cache by automatic prefix
and charge nothing for a write. Measured the same day on the Responses API, two calls
per model sharing the real `response` static prefix:

| Models | Reports a write | Accepts `prompt_cache_breakpoint` |
|---|---|---|
| gpt-6-astra, gpt-6-sol, gpt-6-luna, gpt-5.6-sol, gpt-5.6-terra, gpt-5.6-luna | yes (`cache_write_tokens`) | yes |
| gpt-5.5, gpt-5.4-mini, gpt-5.2, gpt-5.1, gpt-5, gpt-5-mini, gpt-5-nano, o4-mini, o3, gpt-4.1(-mini) | `0` | no — 400 « not supported on this model » |
| gpt-4o-mini (Chat Completions) | no such field | not tried |

- **The price is one line**: `_CACHE_WRITE_MULTIPLIERS` gives OpenAI Anthropic's 1.25.
  The provider-wide rule is exact because a write is reported only where it is billed,
  and it keeps no list of models: a later generation that bills its writes is priced
  the day it is served.
- **The shape** (`providers/openai_payload.py`, applied by `ChatOpenAICached` to every
  request): the static prefix gets an explicit breakpoint, cut at `DYNAMIC CONTEXT` —
  a string content becomes two `input_text` blocks whose concatenation is the original
  text; a marker opening a system message puts it on the one before; no marker, no
  breakpoint. The request stays in **implicit** mode: explicit mode looks up explicit
  breakpoints only, and a tool loop reads its previous iteration through the implicit
  breakpoint and the earlier message endings that mode also looks up.
- **Only the declared families are sent one** (`gpt-6`, `gpt-5.6`, and a name
  continuing either with a dash): the field refuses every call of an earlier model, so
  a family is declared once measured, never read off a version number. A guard holds
  the catalogue's matches equal to the measured list — wider is an outage, narrower a
  model rewriting its whole prompt.
- **The cache key stops at the first marker too.** `compute_prompt_cache_key` hashed
  the pre-marker part of EVERY system message, so a second one without the marker —
  a ReAct turn's context blocks, a response's agent results — was hashed whole and
  changed the key on every turn. From GPT-5.6 on a key is a cache partition: a call
  sharing the previous one's static prefix read 0 tokens under a new key and 2,831
  under the same (gpt-6-luna). The key now covers what the breakpoint covers.
- The price follows what the vendor REPORTS and the shape what the model ACCEPTS, on
  purpose: a model the shape does not know yet is still billed right.
- No new probing surface: the only prefix the breakpoint makes shareable across
  accounts is the static part of a versioned prompt, public text in this repository.

### Measured

On Docker dev (2026-09-23), two calls through LIA's own chain — `get_llm` (payload
shaping), the tracking callback, `TokenExtractor`, `record_node_tokens` and the
pricing cache rebuilt from the dev database — on Sonnet 5 with a fresh static prefix:
the first WROTE 5,076 tokens and was recorded at 0.012884 USD, exactly the vendor's
arithmetic on the provider's raw report (72 × 2 + 5,076 × 2.50 + 5 × 10 per million);
the pre-change ledger would have recorded 0.010346. The second READ the 5,076 tokens
and was recorded at 0.0012092. Migration `c3e7a1f5d9b2` ran on dev: 8 rows, 8 tariffs.

The OpenAI half, through the same chain on gpt-6-luna and gpt-5.6-terra: the first
call WROTE 2,879 tokens and was recorded at 0.000363175 and 0.0072635 USD — the
published arithmetic, cache writes at 0.125 and 2.50 per million; the second READ
2,832 and wrote 47, recorded at 0.000037495 and 0.0007499 USD. Without the
breakpoint every call is a first one (gpt-6-luna: 0 read, 2,873 rewritten). With a
second, marker-less system message in front of the question, the same pair read 0
before the key change and 2,831 after it (the key identical on both calls).

## Stated limits

- **The per-call token columns do not carry the write count**; the cost does. A cost
  recomputed from `token_usage_logs` columns and a tariff is short by the surcharge on
  a call that wrote.
- **Only the 5-minute TTL is priced.** LIA never writes another (guarded); a write an
  operator forced to 1 hour through the `provider_config` escape hatch would be billed
  at 1.25x instead of 2x.
- **On GPT-5.6 and GPT-6 the tail is still written at 1.25x.** The implicit
  breakpoint covers the turn's data, the history and the question on every call, and
  only a call that repeats them reads it back — a tool loop's next iteration does, a
  single call's does not. Explicit mode would bill that tail at 1x, at the price of
  every read a tool loop makes.
- **The cross-turn cache of a ReAct call is bounded by its tool list.** Measured on
  dev (2026-09-23): the tools are 82 % of a turn's first call (70 schemas, ~22K
  tokens), and ADR-293's relevance selection changed the list between every pair of
  consecutive turns observed (Jaccard 0.67). Claude and OpenAI put the tools FIRST in
  the cached prefix, so the second of two turns reads nothing — and moving the
  per-turn context after the history does not change that (0 % in both shapes, real
  calls, 70 real schemas); with an identical list it reads 83 %, 91 % with the
  context moved. DeepSeek renders the system prompt BEFORE the tools: 5 % today,
  26 % with the context moved, 92 % with an identical list as well. Within a turn's
  loop the prefix is stable and read. A stable list is a trade against ADR-293's
  relevance: not decided here.
- The implicit depth is declared for the Claude generations alone; DeepSeek's default
  thinking is not (the validator is unchanged for it).
- Claude 4.7+ tokenizes about 30 % denser than earlier generations: local estimates
  (tiktoken) under-count those models; billing reads the provider's report.
- The retired `claude-3-5-*` rows stay active in the catalogue: deactivating them is
  ADR-244's retirement flow, not this change. The Mythos models are Project Glasswing
  only — absent from the Models API of an ordinary organisation — so not offered,
  though the surface already answers for their names. Fast mode and `inference_geo`
  are not used.

## Rejected

- **Reading only Anthropic's TTL breakdown to find a write.** Written first; the
  runtime probe showed the path LIA runs never carries it, so every write read as
  zero while a unit test agreed with itself.
- **A write price column in the tariff table.** The surcharge is a multiple of the
  input price on every Claude model; a column would be one more number to keep equal
  to its rule.
- **Keeping previous turns' thinking for cache stability.** The system prompt changes
  every turn anyway, and on the binding generations a kept block is a 400.
- **The 1-hour TTL.** Twice the write price, for reuse that happens inside five
  minutes.
- **A write multiplier per OpenAI model.** The first idea; the reporting measurement
  made it unnecessary — a model that does not bill a write reports none — and a list
  would have left the next generation unpriced until somebody remembered it.
- **OpenAI's explicit mode.** It bills a single call's tail at 1x instead of 1.25x,
  but looks up explicit breakpoints only: a tool loop would lose the implicit
  breakpoint and the earlier message endings it reads today.
- **A version rule (« 5.6 and later ») for the breakpoint.** It is OpenAI's own
  wording, but a model it misjudges refuses every call; a declared family costs one
  line once the next generation is measured.
