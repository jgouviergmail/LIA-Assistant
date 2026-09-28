# ADR-275 — A truncated structured output is a refusal, never a rescue

**Status:** Accepted — 2026-09-08; amended 2026-09-27 (the ReAct loop)
**Amends:** ADR-220 (shared JSON recovery), ADR-226 (document generation — "an
overflow fails honestly"), ADR-258 (a permanent meeting failure is not
requeued), ADR-272 (every spend site answers to both ceilings); the amendment
also amends ADR-248 (the ReAct invariants) and ADR-263 lot 8 (the stop reason)

---

## Context

`json_recovery.extract_json_payload` closes an open JSON structure
mechanically — it was written for fences, prose and trailing commas — and
`_rescue_structured_from_text` then validates what is left. Nothing read
`finish_reason`.

**Measured 2026-09-08** by cutting a valid document payload at 100 positions:
**12 report cuts and 14 deck cuts validated as SHORTER documents**. A report
missing its last three sections was rendered, stored, and announced *"generated
successfully"* — the exact opposite of what ADR-226 states ("an overflow fails
honestly rather than shipping a silently truncated file"). And when the repair
did NOT validate, `get_structured_output_with_retry` replayed the same prompt
three times: a truncation is deterministic, so each retry bought the identical
refusal at full price.

Every structured caller was exposed, not only documents: meeting minutes, the
relationship debrief, the planner, the semantic validator.

The defect had **three doors**, and only two were in the design:

| Door | Providers | How the cut answer survived |
|---|---|---|
| `_buffered_invoke` (native) | OpenAI, Anthropic, DeepSeek, Google | `include_raw` bundle → `rescue_tool_call` → `_rescue_structured_from_text` |
| `_structured_via_auto_tool` | OpenAI reasoning, thinking Claude | a cut answer read as a "miss", then a second full call |
| `_get_json_mode_fallback` | **Ollama, Perplexity** | **found during review**: `json_recovery` is called deliberately here, its own comment naming truncation as a case it "handles" — the shortened object came back with no parsing error at all |

A second finding on the same door: `resolve_owner` reads
`config["metadata"]["user_id"]`, and LangGraph never puts it there (probed:
only `thread_id` is merged into the run metadata). The document service knew
the account and did not pass it, so at that door only the INSTANCE ceiling was
asked — enforcement held solely because the turn entrance asks the per-account
one. `test_every_spend_site_is_bounded` accepts
`get_structured_output_with_retry` by NAME ("carrying the owner"); this call
carried nothing.

## Decision

1. **One predicate reads the provider's own verdict**
   (`infrastructure/llm/output_truncation.py::is_output_truncated`): OpenAI
   chat `finish_reason=length`, Responses `status=incomplete` +
   `incomplete_details.reason=max_output_tokens`, Anthropic
   `stop_reason=max_tokens`, Ollama `done_reason=length`, Google
   `finish_reason=MAX_TOKENS`. Each shape was read in the installed adapter and
   is pinned by a fixture. Doubt never invents a refusal: no metadata, no
   verdict.

2. **It runs at all THREE doors, before any rescue**, and raises
   `StructuredOutputTruncatedError(StructuredOutputError)`.

3. **A complete answer is never refused.** The verdict is consulted only once
   no complete answer exists: a payload the provider parsed without any repair
   (native `parsed`, a validating tool call, a bare `json.loads`) is
   syntactically closed, so the budget stopped the stream *after* the object
   ended and nothing was lost. Refusing it would cost a valid document and a
   second bill. Both directions are pinned: a cut answer is refused, a whole
   one carrying the same `finish_reason=length` is kept.

4. **Nothing retries it.** `get_structured_output_with_retry` re-raises it
   without a second attempt, and the two application-level replays found in the
   blast radius are closed the same way:
   - `semantic_validator` retried once (it exists for a residual EMPTY-answer
     rate, which a second attempt squares — it cannot complete what a budget
     cut) and now falls open at once;
   - `meetings/processing` marked every `StructuredOutputError` as
     `transient=True`, so a cut minutes synthesis was re-driven by the reaper
     until the attempt budget ran out, each attempt paid. A truncation is
     PERMANENT: new code `synthesis_too_long`, `transient=False`, six locales —
     the same doctrine as the permanent transcription codes (ADR-258).

5. **The refusal is actionable.** The document tool names the budget: *"The
   document exceeded the output budget of the document_generation slot (N
   tokens). No document was produced. Ask for a shorter document, or split it
   into several documents."* No card, no phantom success.

6. **The document service passes `user_id` to the structured door.** The
   guard's blind spot — a "bounded caller" accepted by name — is recorded here;
   tightening `test_every_spend_site_is_bounded` to require the `user_id=`
   keyword is a follow-up audit, because other `TURN` modules may legitimately
   rely on the turn entrance.

## Consequences

- Every structured caller now fails honestly where it used to receive a
  silently shortened object, or pay for three identical retries. Watched
  through the `structured_output_truncated` log event: no new Prometheus
  metric, because a metric no panel reads is a metric nobody acts on
  (ADR-148), and the existing structured-failure counters already fire.
- ADR-226's honesty sentence is true for the first time.
- **Stated limit**: the streaming reasoning path holds no raw message, so it
  cannot consult the verdict. It cannot silently shorten either — a cut tool
  call fails to parse, which sends it to the buffered fallback, where the
  verdict IS read.
- A meeting cut at the budget now dead-letters immediately with a message the
  person can act on, instead of retrying to the same end.

## Alternatives rejected

1. **Detect truncation from the text** (unbalanced braces, a trailing comma):
   that is exactly what `json_recovery` does, and it cannot tell a cut object
   from a deliberately short one. The provider knows; we ask it.
2. **Refuse on the verdict alone, whatever came back**: simpler, and it throws
   away complete documents whose object closed on the last allowed token —
   a false positive paid twice.
3. **Retry with a smaller ask** (fewer sections, a shorter budget): inventing a
   different request the caller never made, and hiding a budget problem the
   operator should see in the slot configuration.
4. **A dedicated Prometheus counter**: the metric-coverage ratchet would demand
   a panel for a rare event the existing failure counters and the log already
   carry.

---

## Amendment 2026-09-27 — the ReAct loop: a cut output never enters the thread

### Context

The decision above covered the three STRUCTURED doors. The ReAct loop reads
free text through `stream_reasoning_events` and nothing there read the
verdict: `react_call_model_node` wrote every reply to `messages`, and
`react_finalize_node` published the last one as the answer.

**Measured on production, 2026-09-25 → 26.** The third model call of a relayed
phone call (ADR-301) ran to its output budget: **20 000 tokens, 71 822
characters, no tool call**. The loop served it, and the thread kept it — ONE
thread per account, shared by the chat, the voice relays and every routine. The
model then copied it into later calls: the relayed live session three minutes
later, then **seven routines out of seven** the next morning, each stopping
after one iteration with no tool run and no e-mail sent (an evening chat turn in
between, and the eighth routine at 07:00, answered normally). Two
different instructions came back with **exactly 73 193 characters**: verbatim
recopy. Each copy of ~20 000 tokens pushed the rest of the history out of the
reducer's token window (141 → 28 messages). `token_usage_logs.status`,
`agent_decisions.outcome` and `scheduled_action_runs.outcome` all said
*success*; the owner reset the conversation by hand, after which every run was
normal. Since 2026-09-05 (the capture of inference parameters) exactly nine
production calls reached their output cap: these nine, all in that thread. What
made the model degenerate the first time is not knowable — the reset purged the
thread, Langfuse is off, and logs carry no content by design (ADR-317) — which
is precisely why the system must contain it rather than hope it never recurs.

### Decision

1. **A reply the provider cut is neither an answer nor a plan, and it never
   reaches `messages`** (`nodes/react_output_guard.py::model_call_update`,
   the ONLY writer of a model call's update). Its text stops wherever the
   budget fell; its tool calls may be the unfinished half of a plan — running
   part of it would act on a decision the model never completed. The
   call still advances the iteration and charges its seconds: it ran, and it
   was billed.
2. **It ends the loop through the ONE stop predicate.** The guard writes
   `react_output_truncated` (declared in `MessagesState`, reset by
   `react_turn_reset()` — the guard test refuses one without the other), and
   `react_exit_reason` returns `output_truncated`, first: when the cut call
   also exhausted a budget, the cut is what explains an answer with nothing in
   it. The router finalizes on it (logged once, where the output was refused —
   never as a time budget), the decision register records it as the turn's
   `stop_reason` (ADR-263 lot 8), and `STOP_REASON_WORDING` says it in six
   languages (the boot guard reads the predicate's returns).
3. **The finalize node explains with the same predicate**
   (`react_budget.loop_cut_reason`, its only reader of the stop condition):
   an empty final message and `truncation.reason = output_truncated`, so the
   response node synthesises from the tool results that DID come back under
   the existing `react_truncation_directive` — ADR-248 invariant 1's path. A
   recovery pass whose call was cut hands its draft back (ADR-310: a complete
   answer is never traded for nothing). A final answer given ON the last
   allowed iteration stays a finished answer.
4. **Nothing retries it.** Same doctrine as point 4 above, and a second reason
   specific to the loop: a turn that already acted (a sent e-mail, a created
   event) would act twice.
5. **It is counted and shown**: `react_output_truncated_total` on dashboard 20
   (« Model Outputs Cut at the Budget », expected 0), the `output_truncated`
   verdict on the turn's panel, and one `react_output_truncated` warning with
   facts only (output and reasoning tokens, characters, call counts). Unlike
   the structured doors — whose refusal raises an error the existing counters
   already count — the loop's cut left no failure ANYWHERE; that invisibility
   is what let it run for twelve hours.

### Measured before trusting the design

The loop judges the AGGREGATE of a stream, not a buffered reply. Pinned by
`tests/unit/infrastructure/llm/test_output_truncation_streamed.py`: through the
production OpenAI-compatible client on a fake SSE transport, the aggregate
carries `finish_reason=length` (and not on `stop`); a verdict an adapter puts in
`generation_info` (Gemini `finish_reason`, Ollama `done_reason`) is merged into
the message metadata by langchain-core; Anthropic writes `stop_reason` on its final
chunk — only while `stream_usage` is on, which the adapters keep for accounting
(ADR-220): switching it off would blind this guard too. A library upgrade that
loses either path fails the build instead of blinding the guard. The incident itself is replayed on the real nodes,
router and reducer (`test_react_output_truncation.py`): the next turn's model
is never shown the cut text.

### Alternatives rejected

1. **Keep the message but mark it**: every later call would still be shown the
   text the model copied — the contagion channel is the persistence itself.
2. **Retry the call**: a loop that already acted would act again, and a cut
   provoked by the history repeats with the same history.
3. **Detect a cap from the token count** (`completion_tokens ≥ max_tokens`):
   a second, derived reading of what the provider states outright — the
   predicate above is the one reading.
4. **An alert**: no ReAct metric carries one; the answer now states the
   interruption to the person, the panel shows the rate, and the register
   keeps the reason.
