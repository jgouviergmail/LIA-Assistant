# ADR-390 — The automatic mode chooses the engine per request

**Status**: Accepted, 2026-11-15. The gap the first replay left (E07) is closed by a fourth judged property, qualified on a held-out set in a second round (§ Qualification).
**Date**: 2026-11-15

**Builds on**:
[ADR-070](ADR-070-ReAct-Execution-Mode.md) — the two engines, the pipeline's plan and the ReAct loop;
[ADR-325](ADR-325-JEV-Bounded-Decisions-With-Hot-Switches-And-Accounted-Fallbacks.md) — native decisions, one usage per integration, a fallback
that never claims more than it knows;
[ADR-263](ADR-263-Execution-Authority-Chain-And-Effect-Register.md) — the decision register;
[ADR-276](ADR-276-Workboard.md) and [ADR-268](ADR-268-Generic-Recurrence-And-Reminder-Management.md) — a ticket and a routine
choose their own mode;
[ADR-389](ADR-389-Telegram-Reads-And-Answers-Like-The-Chat.md) — Telegram answers like the chat.

## Context

A person chose between two engines in the chat header: the pipeline (one plan, validated, then run —
four to eight times fewer tokens) and the ReAct loop (a model that reasons and calls tools step by step).
Choosing well needs to know, for each request, whether one plan can finish it — knowledge the person
does not have and should not need. The owner asked for a third choice, « auto », ordered by three goals:
**the answer's quality and completeness first, then latency, then tokens**, with two arbitrations taken
before any code (2026-11-15):

- **A** — an open-ended request goes to the loop;
- **B** — an instance without a decision provider runs « auto » as the loop;

and, for its surfaces, Telegram follows the person's mode, tickets and routines offer « auto », and an
automatic answer says which engine produced it, in a small badge that holds on a phone.

## Decision

1. **Two vocabularies, never confused.** A MODE is what is chosen (`pipeline`, `react`, `auto`:
   `ExecutionMode`, `EXECUTION_MODE_CHOICES`); an ENGINE is what ran (`pipeline`, `react`:
   `EXECUTION_ENGINES`). Only an engine reaches the registers, the tools, the sandbox gates and the metric
   labels, through ONE door, `executed_mode_of(context)` (AST guard
   `test_execution_mode_door_guard.py`). The turn's engine lives in a holder on the frozen runtime context
   (`TurnEngine`): settled ONCE, first writer wins — the router for a new turn, the context builder for a
   resumed one, so a confirmation resumes in the engine its turn started in even after the person changed
   the preference. The graph's recursion bound is the loop's whenever the loop may run
   (`recursion_limit_for`).

2. **The rule is pure and ordered** (`services/engine_resolution.resolve_engine`): a chosen engine is
   obeyed; the loop switched off on the instance sends every turn to the pipeline (`loop_disabled`);
   otherwise « auto » sends to the loop any shape the router's analysis reads that one plan cannot finish
   — an act (`act`), something to do for each item (`item_wise`), a skill (`skill`), a reference to what
   an earlier turn showed (`reference`), a calculation over another domain's results (`calculation`). Only
   then is the request's shape judged, and **the pipeline plans the turn only when all four properties
   are JUDGED ABSENT**: a figure to work out from fetched data (`computed`), results to check against each
   other (`cross_check`), open-ended work (`open_ended`), someone or something only an item's written text
   names (`named_in_text` — a plan's `$steps` reference passes a FIELD, never a name read in a
   description). A property present, a judgement undecided or no judgement at all (`no_decision`) goes to
   the loop. Thirteen bounded reasons, one `EngineReason`; « judged absent » has one door,
   `property_absent`, read by the verdict and by the qualification bench.

3. **The judgement is a native JEV usage** (`execution_mode`, slot `jev_execution_mode`, switch
   `JEV_EXECUTION_MODE_ENABLED`): four yes/no questions in ONE call (`jev_execution_mode_*_question.txt`),
   the request as its only state, each answer passed only beyond a margin (`GateKind.MARGIN`; computed
   0.20, cross-check 0.50, open-ended 0.50, named in a text 0.48, administrable). The router starts it BESIDE its analysis and
   awaits it only when the analysis decided nothing; otherwise it cancels it, awaiting the cancellation
   for a bounded grace (`EXECUTION_MODE_JUDGEMENT_CANCEL_GRACE_SECONDS`). It never raises: every failure
   is `no_decision`, and the loop. Its spend is the turn's, under both ceilings
   ([ADR-272](ADR-272-Every-Platform-Paid-Token-Answers-To-Both-Ceilings.md)).

4. **What « auto » does here is said, not guessed** (`llm_config/execution_mode_readiness.auto_resolution`):
   `decided` when the usage is requested and configured, `always_react` otherwise (arbitration B),
   `always_pipeline` when the loop is off. `GET /auth/me/execution-mode-preference` publishes it, and the
   header menu says it under « auto » before the person chooses, read again each time the menu opens.

5. **Every surface speaks the same three choices**: the chat header's menu (three described choices, the
   chosen one checked, focus kept during a save), the ticket and routine field, the channel requests
   (`ChannelAgentRequest.user_execution_mode`, required — a channel cannot forget it). The frontend's
   vocabulary (`lib/execution-mode.ts`) is held to the API's by `test_execution_mode_frontend_sync.py`.

6. **An automatic answer names its engine.** `execution_engine` is written on the archived answer and the
   `done` chunk alike (`with_execution_engine`, read from the turn's record), only for a turn asked as
   « auto »; one reader, `executionEngineOf`, draws a small themed badge after the time and a bar
   (« 18:06 | ReAct ») — the word and, for a screen reader and on hover, the sentence. Its word is centred
   on the time's and the line is no taller than without it (measured in Chromium at 390 and 1280 px, held
   by `execution-mode-auto.spec.ts`). On a 320 px phone a long date and the badge do not fit on one line:
   the bar and the badge carry the line's one break opportunity and drop under the date whole.

7. **The register and the metrics say how each turn chose.** `agent_decisions.requested_mode` and
   `resolution_reason` (migration `aec0910ecebe`; a resumed segment keeps the first segment's values,
   `COALESCE`), the technical export and the debug panel read them;
   `execution_mode_resolutions_total{requested, engine, reason}` feeds a collapsed row of the agents
   dashboard. A downgrade maps « auto » back to each table's default (accounts: pipeline; tickets and
   routines: the loop) and removes the usage's rows.

## Qualification

Lot 0, before any code: a held-out corpus written before measuring
(`scripts/agents/execution_mode_corpus.py`: calibration, validation, adversarial and end-to-end cases in
six languages), simulated providers on the proof account, the decision rule and its acceptance criterion
declared in the corpus beforehand, thresholds chosen on calibration, the verdict read on validation, two
draws per case.

- **Classification is clean.** The judgement takes 165 ms (median; p90 196 ms) beside an analysis of
  2.8 s, so it adds no latency. On validation, 51 of 56 requests one plan can finish went to the pipeline,
  and one request that needed the loop went to the pipeline on one draw of two (V18, a German cross-check
  judged just under its margin). Four cases changed engine between draws; none on the adversarial set.
- **The first end-to-end run put « auto » between the two engines on every axis**: completeness pipeline
  0.656, loop 0.753, auto 0.673; first token (median) 7.5 s, 13.7 s, 8.9 s; mean cost €0.0029, €0.0043,
  €0.0037; 20 turns of 48 planned in the pipeline.
- **The declared criterion — never below the loop's completeness — was not met**, and the gap was not the
  router's: three requests the rule rightly judged plannable (E02, E07, E14) failed IN THE PIPELINE for
  reasons no request text shows (« open tickets » mapped to one status; a name held in a ticket's free
  text, never chained; tasks and events from connectors in error offered instead of reminders). The loop
  was worse than the pipeline on two internal briefs (E17, E19).

The judgement alone is re-measured from the repository (`task agents:execution-mode:measure`: the
production door and verdict, the instance's margins, the proof account, the usage measured even when
switched off — a qualification precedes activation). On 2026-11-15, two draws of the 96 cases
(192 calls, €0.007): no case labelled with a judged property was judged plannable on any split, the
acts were left to the analysis as designed, the validation lane held 53 draws of 64, and the corpus's
declared acceptance passed.

The owner chose to fix the three pipeline causes, then replay the end-to-end set:

- **E02**: `list_tickets_tool` takes `open_only` (every column but done); a named column still wins.
- **E14**: the `reminder` domain says what a reminder holds — what to do and WHEN — and the questions it
  answers (« when must I… », « what did I plan for… »).
- **E07**, first link: a ticket query matches every word in the title or the description
  (`board_queries.search_words`, `mentions_word`), no longer one contiguous fragment of the title.

Replay, 2026-11-15, same corpus, same two draws, 96 turns, €0.37: completeness pipeline 0.744, loop
0.767, **auto 0.771**; first token (median) 7.3 s, 12.7 s, 9.0 s; mean cost €0.0029, €0.0043, €0.0038;
20 turns of 48 planned in the pipeline. E02 now scores 1.00 in the pipeline on both draws; on E14
« auto » scores 0.50 and 1.00 where the loop scores 0.00 and 0.50. The loop stays below the pipeline on
one internal brief (E17: 0.00 against 0.60 on both draws), and « auto » follows the loop there
(arbitration A).

**E07 remained below the loop on both draws** (pipeline 0.00 and 0.50, loop 1.00). The ticket was found,
but the person it names lives only in its description, and a plan's `$steps` reference passes a FIELD:
the planner guessed `assignee`, which no ticket tool produces, and the step died at execution — where
[ADR-194](ADR-194-Reference-Truth-Is-A-CI-Guard.md) keeps that check, a runtime path validator having
measured 63 false refusals out of 112 real paths. No plan can carry a value that only prose holds. The
owner chose a fourth judged property over a pipeline step that would read a value out of a text with a
model call: this shape goes to the loop.

**The fourth property was qualified like the first three, in two rounds** (corpus docstring; €0.04).
Its cases and acceptance were written before any measurement: a new shape `T` (a lookup about someone or
something only an earlier result's text names), hard negatives where what is left unsaid is a field (a
sender, an appointment's place, a deadline, an organiser) or is named, zero leak allowed. The first round
failed its validation: V32 (« who am I supposed to meet », from a reminder) scored 0.08 and 0.11, read as
a meeting's attendees. Those cases were seen, so they joined calibration; the wording now states what
each KIND of item records (a reminder only its time; a person a message's text names is never recorded),
and its margin stayed at 0.48. The second round, on a held-out set written for it: no leak (labelled
≥ 0.78), the hard negatives judged absent on 10 of 12 draws (one sender, 0.62-0.67, sent to the loop),
the adversarial cases held (≥ 0.87). The first round's lane criterion had counted draws the computed and
open-ended questions took (a phone number and a travel time read as figures to work out); the second
counts the property's own judgement.

**Re-read end to end with the property** (the turns already ran in both engines; only the choice moves):
E07 goes to the loop on both draws (1.00 where the pipeline scored 0.00 and 0.50). A real « auto » turn on
the proof account, through the production router, filed `requested_mode = auto`, `execution_mode =
react`, `resolution_reason = named_in_text`, and answered with the person and what is known of them.

**The keyword oracle overrated the pipeline.** Read by a person, three answers it counted complete were
not: E06 (the pipeline read tasks, not the reminder, and could not give the day — its five-day forecast
named the right words), E08 (« no reminder that day », then the reminder that day), E14 on one draw.
Re-graded fact by fact on the shapes where words can mislead (S, M, D, T, R): completeness pipeline
0.685, loop 0.767, **auto 0.774** — still not below the loop, but by a hair, and E06 stays below it on
one draw. Two pipeline defects remain, measured and not fixed here: the reminder/task confusion (E06
on every pipeline draw, E14 on one) and a negation the response writes against its own data (E08).

**The two pipeline defects, worked on (owner's go, 2026-11-15).** No fix routes by a word, a tool or a
domain: each publishes a fact the model reads, or orders by a relevance the router already computed.

- **An oracle that reads** (`scripts/agents/execution_mode_oracle.py`): a judge, the instance's response
  slot at temperature 0, says fact by fact whether the answer STATES it while answering; a denial, a
  doubt, a suggestion or a self-contradiction is 0, and an unreadable verdict is reported, never guessed.
  Against the hand grades of the replay above: 120 facts of 120. It is not infallible: two near-identical
  E06 answers (« I cannot find the day; here is the forecast for the coming days ») were graded 0.67 and
  0.00, so every cell whose grade moved between replays is re-read by hand.
- **E08, the negation: fixed.** `list_reminders_tool(on_day=…)` lets a plan chain the deadline it read
  into the reminder filter ([ADR-268](ADR-268-Generic-Recurrence-And-Reminder-Management.md) amendment of
  2026-11-15); nothing is left for the response to compare: 1.00 on every draw since.
- **E05, a regression that fix caused: closed.** « The next three days » became one call per day, today
  and the two following, and the reminder three days ahead was never read (1.00 → 0.75 on both draws);
  the parameter now says ONE day, left out for a span: 1.00 on both draws, and the weekly review (E17)
  and the count of the next reminders (E11) stopped reading today's reminders alone.
- **E14: fixed** by saying which source no connector serves: the turn's copy of a category tool that
  nothing of the account serves carries `connected: false` into the planner's catalogue, and the prompt
  says what it means ([ADR-184](ADR-184-Published-Bounds-And-Non-Prescriptive-Verdicts.md) amendment of
  2026-11-15):
  1.00 on every draw since.
- **E06: improved, not fixed.** Read on the planner's own prompt, captured during a pipeline turn: the
  reminder domain was seated by its write tool and its reader fell under the ten-tool cap; the catalogue
  now seats each domain by relevance ([ADR-293](ADR-293-React-Tools-Bound-By-Relevance.md) amendment).
  With the reader offered, the planner reads it in about one draw in four where the analyzer names the
  domain (3 of 11, from none of 4 before), and the analyzer names it in 11 draws of 16. Two planner
  wordings were measured and withdrawn: a sentence saying every source able to hold an unlocated value is
  needed (an A/B of eight draws per arm: reminders read 2 of 7 with it, 1 of 4 without), and a rewording
  of the `connected: false` sentence, which changed nothing. The loop fails E06 too, differently: it reads
  the reminder and answers that the tasks could not be read.

Replay of the final code, 2026-11-15 (the pipeline replayed, €0.14; the loop's 48 turns of the replay
just before, which no withdrawn wording reached), judge-read and hand-audited: completeness pipeline
0.772, loop 0.713, **auto 0.770**, never below the loop on any shape; first token (median) 6.9 s,
11.8 s, 9.7 s; mean cost €0.0028, €0.0045, €0.0038; 15 turns of 47 planned in the pipeline. On the 43
cells every replay of the day read, before the defects lot → now: pipeline 0.722 → 0.785, loop
0.725 → 0.709, auto 0.756 → 0.771. Part of the pipeline's gain is the planner's own draw, not this lot:
« tomorrow's weather » planned as `days: 1` with no date reads today (E20, E21 on one replay of three).

**The loop answered from the tasks it could not read — fixed (owner's go, 2026-11-16).** Traced on E06:
the loop found the day and wrote it; the requested-result coverage withheld its answer (the result sat in
the domain the analyzer guessed, whose only tool failed), and the response, told to synthesise from the
tool results, received none ([ADR-336](ADR-336-Requested-Outcomes-Checked-Against-Canonical-Observations.md)
amendment of 2026-11-16, `react_handover`). The replays' other findings were fixed in the same lot: a
read FOR_EACH over five tickets asked a bulk confirmation decided on its cap (E13; now decided again on
the measured count, `still_requiring_approval`); a selection tag closed under a garbled name was shown to
the person ([ADR-253](ADR-253-Per-Turn-Expressivity-Annotation.md) amendment); the planner's multi-domain
section was prose in a `.py` ([ADR-284](ADR-284-Prompt-States-What-The-Code-Enforces.md) amendment). Two
clarified wordings of the judge did worse than the qualified one (118 and 116 facts of 120): it stays.

Replay, 2026-11-16 (96 turns, €0.37), judge-read and hand-audited. It ran across midnight, so the three
cases whose facts assume the seeding day (E04, E09, E20) are set aside: on the 38 cells every replay
read, pipeline 0.708, loop **0.816**, auto 0.789 (end of the previous lot: 0.744, 0.671, 0.741). The
loop's gain is E06, E14 and E17, 1.00 on both draws where they scored 0.00. On all 48 cells, auto 0.778
against the loop's 0.764; first token (median) 7.0 s, 12.8 s, 9.5 s; mean cost €0.0028, €0.0045,
€0.0042; 16 turns of 48 planned in the pipeline. **On the 38 comparable cells « auto » now falls below
the loop**, by one cell: E06 d0, which the judgement sends to the pipeline, where the reminder is still
missed half the time, while the loop now reads it.

## Consequences

- A person no longer needs to know the engines to be answered well; the badge shows what « auto » chose,
  and the debug panel why.
- Every « auto » turn costs one short decision call; a turn the analysis decides cancels it unread.
- The pipeline's own defects now decide part of « auto »'s quality: a fix to the pipeline improves both,
  as the open-ticket filter and the reminder domain did.

### Amendment, 2026-11-16: the final chunk outlives the recording scope

The archived answer is built inside `decision_recorder`; the SSE `done` chunk is
built after it closes, so its costs include the final accounting. Reading the
ambient turn there lost the engine on every live automatic answer, although its
archive kept it. A background history merge preserves a live bubble, so it did
not recover the badge; reloading the history did.

`with_done_enrichments` now requires the turn's owned `TurnDecision`, passed to
the same `automatic_turn_engine` predicate the archive reads. No engine is
inferred and no recording scope is prolonged. The real streaming-generator
regression covers both engines, explicit modes and conversation turns, with an
active and an inactive synthetic Telegram binding; the browser's producer never
reads that binding. Separate tests cross the actual scope exit and keep the other
delivered extras intact.

A resumed turn also keeps the choice it began with if the person changes their
preference while answering a confirmation. Once the checkpoint authorizes the
resume, `restore_resumed_choice` reads the existing decision row on a short
session and verifies its run, account and conversation identity. It restores
`requested_mode` and `resolution_reason`; only the checkpoint settles the engine.
A missing, unreadable or inconsistent row leaves the original choice unknown
and shows no automatic badge. A new turn performs no such read, and no second
copy of the choice is added to graph state.

## Left, and said

- The judgement reads the request alone, never the conversation: a follow-up whose shape lives in an
  earlier turn is judged by its words.
- A routine or a ticket run in « auto » resolves exactly like a chat turn; no corpus measured them apart.
- A Telegram turn shows no badge: the channel has no meta line.
- The first end-to-end figures were graded by matching words; from the defects lot on, a judge reads
  every answer and a person re-reads every cell whose grade moved. The keyword figures stand as published.
- E06 stays a pipeline weakness: the analyzer does not always name the reminder domain for « what day
  must I… », and when it does the planner reads the reminders in about one draw in four. « auto » sends
  E06 to the pipeline while the loop now answers it (1.00 on both draws): there « auto » falls below the
  loop. Sending such requests to the loop is a judgement margin, the owner's call.
- The coverage (ADR-336) still labels a requested result failed when the analyzer's GUESSED source
  fails; the response now has the turn's reads, but telling a named source from a guessed one would
  change the analyzer's contract.
- A span still reaches the reminder tool as one day on about one pipeline draw in ten (E11, `on_day`
  read as « the third day »), down from five draws in six before its description said ONE day.
- One pipeline turn of about two hundred ended on « dictionary changed size during iteration » inside
  the planner node, after its model call (E09, 2026-11-16); six re-runs did not reproduce it, and the
  bench keeps no traceback.
- The pipeline asks a bulk confirmation before reading five tickets one by one (E13); the bench answers
  no question, so those turns are unread, and « auto » sends E13 to the loop.

## References

- Code: `core/execution_mode.py`, `domains/agents/services/engine_resolution.py`,
  `domains/agents/services/analysis/jev_execution_mode.py`, `domains/agents/nodes/router_node_v3.py`,
  `domains/llm_config/execution_mode_readiness.py`, `domains/auth/execution_mode_router.py`,
  `apps/web/src/components/execution-mode-menu.tsx`, `apps/web/src/components/chat/ExecutionEngineMark.tsx`.
- Measurement: `scripts/agents/execution_mode_corpus.py`, `scripts/agents/measure_execution_mode.py`
  (`task agents:execution-mode:measure`), `scripts/agents/execution_mode_oracle.py` (the end-to-end
  judge).
