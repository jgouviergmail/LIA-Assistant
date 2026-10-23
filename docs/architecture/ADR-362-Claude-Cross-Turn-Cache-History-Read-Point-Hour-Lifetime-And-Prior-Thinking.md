# ADR-362 — Claude's prompt cache across turns: a read point at the history's end, the hour where the next turn comes, and earlier thinking for the model that wrote it

**Status**: accepted — 2026-10-22 (owner request after an audit of LIA's Claude caching
against the vendor's practices — « la solution la plus optimale tout en maîtrisant
correctement » — then « GO » with a measurement envelope of 1 USD; 0.146444 USD spent)
**Amends**: ADR-306 (payload rule 2, the rolling breakpoint alone; rule 3, no earlier
thinking replayed; the five-minute lifetime only; the per-call columns without the write
count), ADR-308 and ADR-311 (a fourth effect of frequent exchanges), ADR-309 (the history
blocks are read back on Claude only from a read point at their end)

## Context

Everything below was measured on the Claude API on 2026-10-22 (`task llm:cache:probe`,
32 requests on Haiku 5.5 and Sonnet 5, every prefix opened on a fresh nonce so that no
earlier entry could answer for a later request), or read on production, read-only, the
same day.

1. **The next turn re-wrote the history it had just paid to write.** Claude writes a
   cache entry only AT a breakpoint, and a later request finds an entry only by walking
   back from its own breakpoints. Inside a tool loop ADR-306's policy placed two: the
   static prefix, and the rolling one at the end of the request — the question and its
   context, which the next turn never sends again. The next turn found the static
   prefix and nothing after it, and wrote the whole history again at 1.25x. Two turns
   of LIA's own frequent layout (H4): without a read point at the history's end, the
   second turn read 3,981 tokens and wrote 1,685 (Haiku 5.5; 4,049 and 1,685 on
   Sonnet 5); with one, it read 5,230 and wrote 439 (5,298 and 439).
2. **The cross-turn reuse is minutes away, not seconds.** ADR-306 kept the five-minute
   lifetime because 89 % of the cached tokens were re-read within five minutes — a
   figure dominated by tool loops, which re-read in seconds. Between two ReAct turns of
   a person, production says otherwise: over 60 days on two accounts (869 gaps), 49 to
   59 % of the next turns came within five minutes and 77 to 78 % within the hour
   (ADR-308 had measured 391 gaps: 57 % and 78 %). Of the next turns that came within
   the hour, 24 to 37 % found their five-minute entry expired.
3. **The lifetime is not part of the cache key, and a request mixing lifetimes is
   billed span by span.** An entry written for the hour was read by a five-minute
   request, and the reverse, on both generations (H1). A request whose first breakpoint
   asked for the hour and whose second asked for five minutes wrote 4,716 tokens for the
   hour and 2,553 for five minutes (H3, Haiku 5.5; 4,713 and 2,550 on Sonnet 5). The
   order is the API's rule: a longer-lived entry may not follow a shorter one.
4. **A streamed response says which writes were for the hour at its START only.**
   `message_start` carries `cache_creation.ephemeral_1h_input_tokens` and
   `ephemeral_5m_input_tokens`; `message_delta`, where langchain-anthropic reads a
   stream's usage, carries the write total alone (H2 — `MessageDeltaUsage` has no
   breakdown in anthropic 0.122.0). Billed from what the client read, every hour-long
   write of a streamed call — the ReAct loop streams — would have been priced at the
   five-minute rate.
5. **ADR-306 removed every earlier turn's thinking, from every model.** The reason
   holds for the generations that BIND a thinking block to the conversation that
   produced it (`ClaudeSurface.binds_thinking_to_conversation`): LIA rebuilds the system
   prompt every turn, so such a block is refused (a 400) or, under `drop_block`, dropped
   with every block after it — the current loop's included. But the generations that
   keep a previous turn's thinking without binding it (from Opus 4.5 and Sonnet 4.6 on)
   read it as the vendor's default context, and LIA was removing it from the model that
   wrote it. Measured on Sonnet 5 in LIA's history shape, two assistant messages per
   ReAct turn (H5): accepted, billed as input — 107 tokens for one short reasoning, 157
   for two.

## Decision

1. **The history's end is a read point.** In a tool loop, the last cacheable block
   before the current turn's question carries a breakpoint (`mark_history_end`), when
   the rolling one still fits beside it under the four-breakpoint ceiling. It costs no
   extra write — the rolling breakpoint writes that span anyway — and the next turn
   reads its whole history back. The messages it covers are always sent in one shape
   (text as a block list), so the bytes the next turn resends are the bytes this turn
   wrote.
2. **The cross-turn read points live the hour where the next turn comes.** The static
   prefix and the history end are written for Claude's extended lifetime (a write
   billed 2x the input price instead of 1.25x) when the turn runs in frequent exchanges
   (ADR-311), a person waits for it (`latency_sli.a_person_is_waiting`: a routine, a
   ticket or a relay is not followed minutes later) and `PROMPT_CACHE_EXTENDED_TTL_ENABLED`
   holds (default true). The rolling breakpoint keeps five minutes: the next iteration
   re-reads it in seconds. Beside a breakpoint a caller placed itself, nothing the
   policy adds lives the hour — it cannot order a point it did not place, and the API
   refuses an hour after five minutes. The hour pays whenever
   (2 − r)·p₆₀ − (1.25 − r)·p₅ > 0.75, r being the read price as a share of the input
   price and p₅, p₆₀ the shares of next turns within five minutes and within the hour;
   at the measured gaps it saves 8 to 10 % of the cross-turn prefix on the account whose
   turns follow fastest and 23 to 26 % on the other (reads at a tenth and at a twentieth
   of the input price).
3. **The lifetime is declared by the caller, around ONE call.**
   `infrastructure/llm/prompt_cache_horizon` is an ambient scope, like the
   person-waiting declaration: it ends with its `with` block, a gathered call runs in
   its own context copy, and a background task started later sees nothing. The ReAct
   model call is its one writer (guarded in `test_cache_write_reaches_every_price`):
   a scope that narrow leaves every other call at the default — the turn's router and
   response, the background work the turn starts — and the doors that price that call
   are the turn's, which the same guard holds to the extended writes.
4. **An hour-long write is billed at its price, wherever it is reported.**
   `UsageTokens.cache_write_extended` is the part of the writes made for the hour —
   read from a complete response's breakdown, or from the stream's start, which the
   stream hook (`providers/anthropic_hooks`) copies into its chunk under keys the client
   never writes. The reader takes the larger of the two sources, so a client that later
   reports the breakdown itself is never counted twice, and a start that names no
   breakdown is counted and logged (`llm_cache_write_breakdown_missing_total`, expected
   0, alert `LLMCacheWriteLifetimeUnreported` with its self-diagnosis evidence recipe).
   The tariff says what it costs:
   `CachedModelPrice.cache_write_extended_multiplier` (2.0 on every Anthropic tariff,
   the short rate elsewhere), through every pricing door. The
   per-call record carries both counts (`token_usage_logs.cache_write_tokens` and
   `cache_write_extended_tokens`, nullable so that a row written before this change
   reads « unknown »; migration `6b7fe9493921`), the Article-12 technical extraction
   exports them, and the writes are counted by lifetime (`llm_cache_write_tokens_total`,
   dashboard 05).
5. **An earlier turn's thinking goes back to the model that wrote it, and only where it
   can.** Decided on LangChain's messages, before the client formats them — where a
   message still says which model wrote it, and before the client drops an emptied
   assistant message (`providers/anthropic_thinking`, wired by the request hook). Kept
   when the receiver keeps prior thinking without binding it
   (`ClaudeSurface.preserves_prior_turn_thinking`, a column of the one surface table)
   and wrote the block (a dated snapshot is its alias). Removed otherwise, under a named
   reason: the receiver binds it (`receiver_binds`), the API would strip it and lose the
   messages cache after it (`receiver_strips`), the table does not declare the receiver
   yet (`receiver_undeclared`), the block is another model's (`other_model`) or of
   unknown origin (`unknown_origin`), or `PRIOR_TURN_THINKING_REPLAY_ENABLED` is false
   (`disabled`). The current turn is never touched: a tool loop replays the thinking of
   the call it continues. Every decision is counted
   (`llm_prior_turn_thinking_blocks_total{model, decision, reason}`, dashboard 05).

## Measured on real turns (2026-10-22)

Real ReAct turns of a proof account on dev, through the whole graph (router, loop,
response), in frequent exchanges — every tool bound, a prefix of about 146,000 tokens —
the react_agent slot on Claude, driven by a harness in its own process inside the dev API
container; shown is the first ReAct call of each turn, as `token_usage_logs` recorded it:

| Scenario | Turn | Read | Written (for the hour) | Cost of that call |
|---|---|---|---|---|
| five minutes only (Haiku 5.5) | T1 | 0 | 146,241 | 0.01831 USD |
| | T2, 60 s later | 144,376 | 2,066 | 0.00173 USD |
| | T3, 400 s after T2 | 0 | 146,698 | 0.01857 USD |
| the hour (Haiku 5.5) | T1 | 0 | 146,241 (144,376) | 0.02914 USD |
| | T3, seven minutes after T1 | 144,376 | 2,133 (367) | 0.00212 USD |
| the hour (Sonnet 5) | T1 | 0 | 146,307 (144,444) | 0.58299 USD |
| | T2, 60 s later | 144,444 | 1,972 (198) | 0.03469 USD |

After a pause the five-minute entries were gone and the whole prefix was written again;
the hour's were read back: 89 % less on that call. The router's and the response's static
prefixes (6,485 and 5,785 tokens) were re-written after the pause in both scenarios — the
limit stated below, at a twentieth of the loop's.

Three facts only real turns showed:

- **The loop's calls were invisible to every Prometheus LLM metric.** The ReAct node never
  handed its model call the per-node metrics handler every other node attaches
  (`enrich_config_with_node_metadata`): twelve calls reached the ledger and none reached
  `llm_tokens_consumed_total`, `llm_cost_total` or `llm_cache_write_tokens_total` — the one
  call written for the hour, invisible to its own counter. The node attaches it now;
  measured again, its calls are counted, once.
- **A change of thinking parameters rewrites the whole prefix.** Moving the Sonnet 5 slot
  from `low`, omitted thinking, to `medium`, summarized, missed the hour-long entry written
  minutes before with the same tools and system: 146,355 tokens written again. A slot's
  reasoning change costs one full prefix write.
- **With the dev slot's own reasoning (`low`, `exclude_from_output`), no thinking block
  appeared**, not even in the current loop; the earlier turns reached the request as text,
  so the thinking rule decided nothing. With `medium`, summarized, the loop carries
  `thinking` then `tool_use`. A second real turn replaying it was not run: the envelope was
  spent first (stated below).

Spent on the whole measurement, the probe included: 1.526 USD.

## Consequences

- A frequent turn reads its history back from the cache instead of re-writing it, and
  within the hour so does the turn after a pause.
- The hour costs 0.75x the input price more per written token than five minutes. It is
  paid when the static prefix is written — a read refreshes the entry, so turns that
  keep coming within the hour never pay it again — and once per turn for that turn's own
  exchange (387 of the 439 tokens the measured second turn wrote).
- On a generation that keeps it, the model reads its own earlier reasoning again, as the
  vendor intends: billed as input, and read back from the cache with the history in
  frequent exchanges.
- Two operator switches, both on by default; the person's rhythm decides first. Off,
  `PROMPT_CACHE_EXTENDED_TTL_ENABLED` keeps every breakpoint at five minutes and
  `PRIOR_TURN_THINKING_REPLAY_ENABLED` removes every earlier turn's thinking — ADR-306's
  behaviour.
- `token_usage_logs`, the one record that outlives an account (`BILLING_RETAINED`),
  gains two token counts and nothing else.

## Stated limits

- **Measured on two generations** (Haiku 5.5 and Sonnet 5). The lifetime and span rules
  are the vendor's for every Claude model; the history read point relies on the API's
  20-block lookback, which one turn's exchange stays far inside.
- **An earlier turn's thinking was not seen replayed on a real turn.** The probe proved the
  API accepts it in LIA's history shape; the policy is tested on the real client; on
  real turns the dev configuration produced no thinking to replay. A second real turn
  with visible thinking is the measurement that remains.
- **Another model's thinking was billed too.** Sent to a different generation, the same
  history cost 224 input tokens against 113 without the block (H5): whether a model
  reads another's thinking cannot be observed from the outside, so LIA does not send it.
- **An entry lives an hour at the provider instead of five minutes.** It holds what LIA
  sends anyway; Anthropic's caches are isolated per organization.
- **The horizon is provider-neutral; only Claude's policy reads it.** Qwen's
  explicit-only families (ADR-309) have the same shape — a static marker, a rolling one,
  five minutes — and so, in principle, the same re-write on the next turn; but DashScope
  documents neither a lookback nor a second lifetime, so a history marker there is a
  measurement first, then a lot.
- **Only the loop's calls ask for the hour.** The turn's other cross-turn read points —
  the static prefixes of the router and of the response, re-sent every turn as well —
  keep five minutes, and so does every pipeline turn: the exchange rhythm is a ReAct
  choice (ADR-311). The response's static prefix measured 5,074 tokens (ADR-306),
  where the loop's carries the schema of every bound tool (ADR-308); their stability
  from one turn to the next was not measured, so the same inequality decides them
  after a measurement, not before.
- **The gap distribution is two accounts'.** The inequality above decides; the switch is
  the operator's.

## Rejected

- **The hour on every breakpoint.** The rolling tail is re-read by the next iteration
  within seconds, or never: 2x for nothing.
- **The hour for every frequent turn, waited for or not.** A routine's next run is a day
  away, not minutes.
- **Keeping ADR-306's removal everywhere.** It took the model's own context away from the
  generations that read it, to protect the ones that bind it — which the surface table
  tells apart.
- **Keeping earlier thinking for every receiver.** A binding generation refuses it or,
  under `drop_block`, drops the current loop's blocks with it.
- **Deciding the thinking on the formatted request.** The client drops an emptied
  assistant message, so a formatted message cannot be matched back to the LangChain
  message that says who wrote it.
- **Reading the stream's end only, or waiting for the client to carry the breakdown.**
  The first bills every streamed hour at five minutes; the second has no date. The
  hook's keys are private and the reader takes the larger source, so the day the client
  reports it, nothing changes.

## Implementation references

- `apps/api/src/infrastructure/llm/providers/anthropic_payload.py` —
  `shape_claude_payload`, `mark_history_end`.
- `apps/api/src/infrastructure/llm/providers/anthropic_hooks.py` — the request and
  stream hooks, installed by the factory on every Claude client.
- `apps/api/src/infrastructure/llm/providers/anthropic_thinking.py` —
  `replay_prior_turn_thinking`.
- `apps/api/src/domains/agents/nodes/react_nodes.py` — the extended horizon around the
  model call, and the per-node metrics handler it now carries.
- `apps/api/src/infrastructure/llm/prompt_cache_horizon.py`;
  `apps/api/src/domains/agents/nodes/react_turn_layout.py` — `extended_cache_horizon`.
- `apps/api/src/core/claude_surface.py` — `preserves_prior_turn_thinking`.
- `apps/api/src/infrastructure/llm/usage_metadata.py` — `cache_write_extended`;
  `apps/api/src/infrastructure/cache/pricing_cache.py` —
  `cache_write_extended_multiplier`.
- `apps/api/alembic/versions/2026_10_22_1400-6b7fe9493921_token_logs_cache_writes.py`.
- `infrastructure/observability/prometheus/alerts-core.yml.template` —
  `LLMCacheWriteLifetimeUnreported`; runbook
  `docs/runbooks/alerts/LLMCacheWriteLifetimeUnreported.md`.
- `apps/api/scripts/llm/claude_cache_probe.py` — `task llm:cache:probe`, a paid
  measurement, never a gate.
- Tests: `apps/api/tests/unit/infrastructure/llm/providers/test_anthropic_payload.py`,
  `test_anthropic_hooks.py`, `test_anthropic_thinking.py`;
  `apps/api/tests/unit/domains/agents/nodes/test_react_cross_turn_claude_prefix.py`;
  `apps/api/tests/unit/domains/chat/test_extended_cache_writes_ledger.py`;
  `apps/api/tests/integration/domains/chat/test_token_log_cache_writes_db.py`.
