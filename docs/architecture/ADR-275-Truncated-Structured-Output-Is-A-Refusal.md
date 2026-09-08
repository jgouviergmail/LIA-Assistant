# ADR-275 — A truncated structured output is a refusal, never a rescue

**Status:** Accepted — 2026-09-08
**Amends:** ADR-220 (shared JSON recovery), ADR-226 (document generation — "an
overflow fails honestly"), ADR-258 (a permanent meeting failure is not
requeued), ADR-272 (every spend site answers to both ceilings)

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
