# Model output health — measured before any detector

> Three failures a model call can have that no gate in LIA watches today, each measured on
> production (read only) before deciding whether a detector is worth its code. Measured
> 2026-11-13; re-measure with the tasks below before revisiting a decision.

## Summary

| Question | Measured | Decision |
|---|---|---|
| Does an answer loop (the same line, sentence or tail again and again)? | 0 real loops in 349 assistant answers over 30 days | No detector now |
| Does a model stream stall without closing? | 2 timeouts in 2 881 model calls over 7 days; no answer stream error | No detector now; the gap between answer tokens is observed since 2026-11-13 (`sse_token_gap_seconds`), read it before writing one |
| Does counting a compiled agent's history cost a call? | 0.7 to 10.7 ms per model call within budget | No memo now |

## 1. Repeated output

`apps/api/scripts/agents/measure_repeated_output.py` (`task agents:repetition:measure`)
reads every assistant message of the last `--days` in a read-only session and applies three
rule detectors: three identical lines in a row, a 30-character window repeated four times in
the last 800 characters, a sentence of 30 characters or more said four times. Style and script
blocks are removed first, so a card's CSS is not read as text. A flagged message shows only
the SHAPE of what repeats (letters as `a`, digits as `9`), never a word.

**Measured on production, 30 days**: 349 assistant answers, 14 flagged — all of them dated
lists of cards whose date line repeats by design (the shape shows it). No real loop.
ADR-170 already stops a repeated TOOL call; repeated words are not a failure LIA has.

**Revisit when** a flag's shape is not a list's: then a stop on the stream, not a rewrite.

## 2. A stalled stream

`apps/api/scripts/agents/measure_model_call_tail.py` (`task agents:model-tail:measure`) asks
Prometheus, read only: model calls and their errors by kind, the calls longer than 30 and 60
seconds by node, the answer streams, the longest of them and their errors, the external
timeouts.

**Measured on production, 7 days**: 2 881 model calls, 2 timeouts (0.07 %); 97.3 % answered
within 30 seconds and 99.4 % within 60; 17 calls past 60 seconds (14 in the ReAct loop, 2
interactive pages, 1 journal consolidation — long work, not stalls); 66 answer streams, none
in error, one longer than 120 seconds. Every slot's timeout already bounds a call
(ADR-221 amendment 2026-11-05).

**The next measure, now observed (2026-11-13)**: `sse_token_gap_seconds`, the gap between
two answer tokens of a stream a person waits for. One clock per stream
(`TokenGapClock` in `apps/api/src/domains/agents/services/streaming/latency_sli.py`, the
door that already keeps routines out of the latency SLIs) reads every chunk at the stream's
single per-chunk hook (`StreamingService._track_and_observe`): the first token has no gap,
any other chunk between two tokens is part of the gap. A stall reads as a long gap, a long
answer as many short ones. Dashboard 07, row « SSE Streaming »: the p50 and p99 of the gap,
and the gaps longer than 10 seconds per hour; the bench above reads the count and the gaps
longer than 10 and 30 seconds over its window. Proven on the development stack the same
day: one answer of 48 tokens fed 47 gaps, 46 of them under 50 ms. Still not a detector: one
is worth writing only if these show stalls the slot timeouts do not end — read a week of
production first.

## 3. Counting a compiled agent's history

`MessageHistoryMiddleware` (the browser and query agents) counts the tokens of the whole
history before every model call, with nothing remembered from the previous one.
`apps/api/scripts/agents/measure_history_token_counting.py`
(`task agents:history-tokens:measure`) times the real middleware on browser-shaped histories
(page snapshots of 4 000 to 40 000 characters, 5 to 30 tool rounds) and counts what it
encodes, beside what a per-message memo would encode.

**Measured**: within the production budget, 0.7 to 10.7 ms per model call (up to 612 KB
encoded where a memo would encode 4 to 40 KB). Over the budget, the trim loop recounts the
whole history after each dropped unit: 30 to 80 ms (up to about 5 MB encoded), only on the
calls that trim.

**Decision**: no memo — milliseconds beside a model call of seconds. If the trim path ever
matters, the cheap fix is to subtract each dropped unit's count instead of recounting.

## Running them

```bash
task agents:repetition:measure      # read only; production through the read-only harness
task agents:model-tail:measure      # Prometheus, read only
task agents:history-tokens:measure  # local, no model, no database
```
