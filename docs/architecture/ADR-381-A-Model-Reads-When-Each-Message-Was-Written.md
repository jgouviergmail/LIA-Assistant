# ADR-381 — A model reads when each message was written

**Status**: Accepted, 2026-11-13.
**Amended**: 2026-11-13 — the four background extractions read the person's time (see the
amendment at the end).
**Date**: 2026-11-13

**Relates to**:
[ADR-309](ADR-309-One-Prompt-Layout-For-Every-Cache-Mechanism.md) — a history read back across
turns keeps its bytes, so the question is stamped while it is asked;
[ADR-380](ADR-380-A-Persons-Time-Travels-With-Its-Zone.md) — a stamp is an instant written in the
person's zone, never a wall time guessed into one;
[ADR-284](ADR-284-Prompt-States-What-The-Code-Enforces.md) — every reader is told what a stamp is,
once, and only where it reads one;
[ADR-323](ADR-323-Declared-Language-Complete-Tables-English-For-The-Model.md) — what only a model reads is technical English.

## Context

A model reading LIA's conversation was told the present (`<TemporalContext>`, the ReAct
`<Context>`, the analyzer's `Date/Time`) and nothing about when an earlier message was written.
A thread resumed days later therefore read as if everything had just been said: « I have the
dentist tomorrow at 10 », written on a Tuesday, was still ahead on the Friday, and « is it still
ahead of me? » was answered yes.

Measured before any code (`apps/api/scripts/agents/measure_message_timestamps.py`,
`task agents:timestamps:measure`): eleven scenarios in a zone away from UTC — seven whose answer
depends on when an earlier message was written, four controls whose answer does not — three model
families, three repetitions. On the seven time-bound questions:

| Family | No stamp | Earlier messages stamped | Every message of the person stamped, one system sentence |
|---|---|---|---|
| DeepSeek | 3/21 | 19/21 | 20/21 |
| OpenAI | 5/21 – 7/21 | 11/21 | 14/21 |
| Anthropic | 3/21 | 19/21 | 16/21 |

The controls stayed stable or improved on every family, and no answer copied the bracketed form.
The two runs cost 0.054 EUR together. The last column is the form adopted: it is the only one a
cross-turn cache can read back (Decision 3), and it is the one that measured best on average.

## Decision

1. **The person's message carries the instant it was written.** It is set once, when its turn
   begins (`agents/services/orchestration/person_message.person_message`, at the three places the
   turn start creates one: a new message, a resumed confirmation, an edited message), under
   `WRITTEN_AT_KEY = "original_created_at"` — the key a message restored from the archive already
   carried, so a restored notification or earlier turn reads its own moment. LIA's answers carry
   none: they follow the person's message at once. A value without an offset is a wall time, not
   an instant, and is never guessed into one (ADR-380).

2. **One door renders it** (`infrastructure/llm/message_view.py`): `with_written_at` for a list of
   model-bound messages (a text content is prefixed, a content of blocks gets a first text block),
   `written_prefix` for a reader that flattens messages to text. Both write the same technical
   English stamp, `[Tue 10 Nov 2026, 09:12]`, in the person's display zone
   (`core/time_utils.resolve_zone`), whatever the process locale and whenever it is read.

3. **The question is stamped while it is asked.** The frequent rhythm's cache reads a turn back
   through its question (ADR-309): a question stamped only once it is earlier would change its
   bytes between two turns and miss that cache. The stamp depends on nothing but the message and
   the zone, so every call of a turn sends the same bytes.

4. **Every model that reads the conversation reads the stamps**: the response node (its
   conversation, and the text history a dialogue skill's runner is handed), the ReAct loop (the
   earlier turns and the current one), the query analyzer (each turn's text keeps its whole budget,
   `QUERY_ANALYZER_HISTORY_TURN_MAX_CHARS`, the stamp written before it), the compaction summarizer
   (its prompt already turns a relative date into an absolute one when the conversation states the
   reference date: the stamp is that date, so a summary keeps the dates of the messages it
   replaces), and the owner's phone call and Live direct session (their recent exchanges, stamped
   in the person's words like the agenda and reminders lines beside them).

5. **Each reader is told, once, what a stamp is**: « A message may start with the date and time it
   was written, in brackets. » ReAct and the response read it in their static part, at no cache
   cost; ReAct resolves a relative expression against the moment it was said. The analyzer and the
   compaction read it beside their history, a dialogue skill's runner with its history and only
   then (`skill_runner_lines.txt`). Guard: `tests/unit/domains/agents/prompts/test_message_stamp_explained.py`.

## What this decision leaves, and says so

- **The four background extractions** (memories, interests, open loops, journal) read the
  exchange that just happened without stamps. Their prompts state the present in UTC — two of them
  without saying so. Stamping them in the person's zone would contradict their own clock; stamping
  them in UTC would entrench it. Moving their anchor to the person's zone decides the meaning of an
  hour, which the owner's 2026-11-12 directive asks to PROPOSE first (ADR-380, « the readers »);
  their stamps belong to that change. *Done the same day, on the owner's go: see the amendment.*
- **The planner, the semantic validator and the initiative** read the current question, whose
  moment is the present they are told, and the analyzer's resolution — never the history.

## Consequences

- About ten tokens per stamped message; the static parts of the ReAct and response prompts changed
  once, so their cached prefixes are written again once after deployment.
- The analyzer's per-turn cut is one constant applied once, by the projection; the second cut its
  renderer applied (and the dead 500-character one) are gone.
- The script-skill runner's task wording left the code for `skill_runner_lines.txt` (ADR-284).
- `CompactionService.compact` and `_fetch_recent_exchanges` take the zone as a required argument:
  a caller cannot forget it and summarise or read aloud an undated history.

## References

- `apps/api/src/infrastructure/llm/message_view.py` — `WRITTEN_AT_KEY`, `written_at`,
  `stamped_now`, `with_written_at`, `written_prefix`
- `apps/api/src/domains/agents/services/orchestration/person_message.py`
- `apps/api/src/domains/agents/nodes/react_history.py`, `response_node.py`,
  `response_skill_runner.py`, `compaction_node.py`
- `apps/api/src/domains/agents/services/analysis/query_context.py`,
  `services/compaction_service.py`
- `apps/api/src/domains/telephony/self_call_context.py`
- `apps/api/scripts/agents/measure_message_timestamps.py` — the measurement, replayable

## Amendment 2026-11-13 — the four extractions read the person's time

On the owner's go, the four background extractions (memories, interests, open loops,
journal) moved to the person's clock, all four in one change:

1. **One present, written like a stamp.** `message_view.present_label(zone, now)` renders the
   present in the person's zone with the zone named (`Fri 13 Nov 2026, 11:30
   (America/Los_Angeles)`); the memory, interest and open-loop prompts read it in place of the
   UTC value two of them gave without saying so. The journal's introspection states no present
   and still states none.
2. **The exchange stamped.** Each extraction's formatter writes `written_prefix` before a
   message that carries its instant, in the same zone; each prompt says what a stamp is (the
   sentence `test_message_stamp_explained.py` holds the four to) and resolves a relative date
   against the moment it was written.
3. **The zone is the turn's.** `post_response_extractions` hands each extraction the state's
   `user_timezone`, a voice session's learning its session's zone, the debug panel the state's;
   the parameter is required, so a launcher that forgets it is refused instead of silently
   writing UTC (`test_extractions_receive_the_persons_zone.py`).
4. **A deadline without an offset is the person's.** Told the present in the person's zone, a
   model that writes `2026-11-15T09:00:00` means nine o'clock there: `_parse_due_hint` reads it
   in that zone, where it used to read it in UTC and move the person's « 9 h » by their offset.
   An explicit offset is the model's own instant and is kept.

Proven in a zone away from UTC (Auckland, UTC+13 in November:
`test_extractions_read_the_persons_time.py`), and once on the development stack with a real
model: « d'ici mardi 18 h », said in Paris on Friday 13 November, was stored as Tuesday 17
November 18:00 in Paris (17:00 UTC). Not measured as a rate: the change removes a contradiction
between two clocks rather than tuning an instruction, and the stamps are the ones the lot 17
measurement adopted.
