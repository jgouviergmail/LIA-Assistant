# ReAct result-oriented recovery — design

**Date:** 2026-09-24
**Status:** approved by the owner (2026-09-24), refined while planning — the protocol's module,
the draft removed at the pass and shown again transiently, one state key, the metric's name and
outcomes — and after the bench and the runtime proof: the protocol is anchored on what the
loop set out to obtain, the final message after a pass is complete, a block runs from its last
opening (section 1); the bench runs eight scenarios against the doctrine it replaces
(section 6). Plan: `docs/superpowers/plans/2026-09-24-react-result-oriented-recovery.md`.
**Scope:** a recovery pass the ReAct loop enforces, the ReAct doctrine that feeds it, absolute
dates in the three prompts that write tool parameters, the weather tool's date contract, and a
paid validation bench (at most 2 USD, no Anthropic call).

## Problem, measured on dev (2026-09-23, 22:58 UTC = 00:58 in Europe/Paris)

The person asked: « je veux aller chez mon frère demain en voiture, comment faire pour arriver à
19h pour l'apéro ? ». The ReAct loop found the contact, computed the route (arrival
2026-09-25 19:00, suggested departure 13:49), then called the weather forecast with
`date: "demain"` and answered « Je n'ai pas pu récupérer la prévision du 25/09 — le service m'a
renvoyé les données du 24 ». It stopped by itself after 4 iterations out of the 70 its budget
allowed. Four causes, each read in the logs or the code:

1. **The tool answered another question and said nothing.** `_calculate_target_date`
   (`tools/weather_tools.py`) understands English words only (`today`, `tomorrow`, …), on the
   assumption that the semantic pivot translated the query — which is not true in ReAct, where
   the model reads the person's own words. Any unknown reference falls back to « today, not a
   specific date »: `forecast_date_calculation {"date_ref": "demain", "target_date":
   "2026-09-24", "offset": 0}`. The manifest invites exactly that value: « Accepts: temporal
   reference ('today', 'tomorrow') ». Counter-proof, the next turn (22:59): with
   `date: "2026-09-25"` the tool served the right day.
2. **The recovery rules miss this case.** The ReAct prompt recovers on an ERROR (« If an API
   returns an error… retry ») or an EMPTY result (query relaxation). A successful result that
   answers another question (a wrong date, place or entity) is neither.
3. **The prompt tells the loop to give up on enrichments.** The weather was a cross-check the
   agent added itself (« route… and check weather when it affects the trip »), and the prompt
   says « If an optional cross-domain call fails… proceed immediately… Never stall the primary
   intent for secondary enrichment » and forbids cross-checks on cross-checks.
4. **No fallback ladder and no end-of-turn check.** Nothing names another source for the same
   fact (web search, page fetch) or says when the sandbox helps, and nothing in the loop looks at
   the answer before the turn ends: the loop finishes as soon as the model calls no tool
   (`route_from_react_call_model`). Persistence rests entirely on how the configured model reads
   the prompt — which the owner's rule (every slot is configurable, models are interchangeable)
   makes the wrong place to rest it.

The same defect misled a second consumer: the initiative checked the agenda of 2026-09-24
(its synthesis quotes « météo du 24/09 ») while the route targeted the 25th.

Relative dates have a house doctrine, written as a prompt directive in six prompts (query
analyzer, telephony, memory extraction, meeting synthesis, health agent, compaction). The ReAct
prompt does not carry it, and its exemplar teaches the opposite
(`calendar_get_events(date="tomorrow")`). The pipeline planner and the initiative prompts carry
the current date but no resolution rule. `core/time_utils.parse_datetime` reads ISO values and
the weather tool already uses it; no multilingual reader of « demain » exists, and none is
wanted.

## Goal and success criteria

Owner's words: a result-oriented ReAct agent that, when it meets an obstacle on the way to its
goal — answering with reliable data — uses every tool it has (a corrected retry, web search, a
script in the sandbox), a bounded number of times and never insisting uselessly; relative dates
become absolute dates.

- **Stable**: the same obstacle produces the same persistence whatever the configured model — a
  mechanism in the loop, not only a sentence in a prompt.
- **Reliable**: a fact obtained from a fallback source is stated with its source; a fact still
  missing is said to be missing, with what was tried, never estimated (ADR-303 unchanged).
- **Bounded**: every attempt stays under budgets the code already enforces; a turn with no
  obstacle costs nothing more.

## Decisions taken in chat

| Question | Decision |
|---|---|
| Sandbox network during a recovery | Any host; an unknown host ALWAYS raises the existing permission question (ADR-298), and the answer waits for the person. |
| A fact from a fallback source | Given with its source (site or tool); no second lookup. |
| Activation | On by default; `REACT_RECOVERY_PASSES_MAX` bounds the pass, `0` switches it off. The date directive and the weather contract are fixes, shipped unconditionally. |
| Approach | A — doctrine plus a recovery pass the loop enforces (B and C rejected below). |
| Validation | A paid bench of at most 2 USD, no Anthropic call. |

## Design

### 1. The recovery pass (loop mechanism)

**Protocol.** Every fact the loop set out to obtain — what the person asked for, and each
cross-check it started — ends obtained or declared, never dropped in silence. The loop's final
message ends with an `<unresolved>` block, one line per such fact still missing after the
ladder, with the rungs tried; no block when nothing is missing. A detail nobody asked for and
nobody looked up is not unresolved, nor is a fact obtained from another source: it carries that
source. Two wordings were measured and replaced: « one line per fact the answer needs » made
two model families of three declare wind and rain on the clean control turn (a pass each that
could change nothing); « a fact your answer cannot do without » let 4 replays of the incident
in 9 drop the wrong-day forecast without a word. A block runs from the LAST opening before its
closing: on the runtime proof the model named the tag in its reasoning first. Reading it is case-insensitive; an empty block or a lone « none » declares nothing. The
response node already reads a model-declared tag the same way (`<relevant_ids>`).

**One predicate.** `should_recover(state)` lives in `nodes/react_recovery.py` with the rest
of the protocol and CALLS `react_exit_reason` — the one stop predicate is reused, never
copied. It is true when the last message is an `AIMessage` without `tool_calls`, with an id,
whose text declares at least one unresolved fact, AND fewer passes were taken than
`settings.react_recovery_passes_max`, AND `react_exit_reason(state)` is `None`. `route_from_react_call_model` reads it in its « no tool calls » branch: true →
`NODE_REACT_RECOVERY`, false → `NODE_REACT_FINALIZE` as today. `react_finalize_node` reads the
same parser to report the outcome. No second copy of the arithmetic.

**The node.** `react_recovery` (`nodes/react_recovery.py`, `NODE_REACT_RECOVERY` in
`agents/constants.py`) calls no model. It removes the draft from the thread at once
(`RemoveMessage(id=draft.id)`, the mechanism the compaction node already uses; the reducer
`add_messages_with_truncate` supports it) and appends one record to `react_recovery_passes`:
`{"anchor_id": <id of the draft's predecessor>, "draft": <its full text>, "unresolved":
[<declared facts>]}`. It logs `react_recovery_pass_started` (counts and ids only, no fact text
at INFO) and routes back to `react_call_model` (`graph.add_edge(NODE_REACT_RECOVERY,
NODE_REACT_CALL_MODEL)`). Removing the draft AT the pass, not at finalize, keeps the thread
clean on every exit of the loop — including the draft hand-off to the HITL dispatch, which
never reaches `react_finalize`.

**What the model is shown is transient.** `react_call_model_node` composes its messages as
today, then inserts, after each record's anchor (and after the system messages glued to it —
the turn's context under ADR-308 stays right after its question), the draft again as an
`AIMessage` followed by a `HumanMessage` rendered from `react_recovery_directive.txt` with the
declared facts. Neither is written to `state["messages"]`: the thread, the checkpoint and later
turns never see them, so no later turn reads the directive as something the person said. The
roles keep alternating on every provider — a draft right after the question never produces two
human messages in a row. The prefix before the anchor is unchanged, so the provider's cache
still reads it (ADR-308/309). A HITL interrupt during the pass (the sandbox permission
question) resumes into `react_call_model`, which composes the same messages again from the
checkpointed records.

**Finalize.** When a pass happened, `react_finalize_node` adds `react_agent_result["recovery"]
= {"passes": n, "outcome": ...}` for the debug panel and counts the outcome. A pass that ends
with no usable answer (an empty reply, a budget cut with calls pending) hands the last draft back
as the final message and is never counted `resolved` (final review, 2026-09-24). A fact still
unresolved reaches the response node inside the final message, which says it (section 2).

**State.** One key, `react_recovery_passes: list[dict[str, Any]]` (its length is the number of
passes), declared in `MessagesState` and reset by `react_turn_reset()`. `should_recover` joins
`_DECIDERS` in `test_react_turn_reset_guard.py`, so the guard requires the key in the reset.

**Bounds.** Without a declared gap, no extra call. A pass costs at least one model call plus
the tools its ladder uses. It is never taken once an existing budget is reached (iterations,
compute time, tool time), and inside it the existing brakes still hold: the fourth identical call
is refused (ADR-256), the sandbox runs at most `PYTHON_SANDBOX_MAX_RUNS_PER_TURN` scripts.

**Observability.** `react_recovery_turns_total{outcome}` in `metrics_react.py` — one increment
per turn that took at least one pass — `outcome` in `resolved` (the final message declares
nothing), `partial` (fewer facts than first declared), `still_unresolved`, `cut` (a budget ended
the loop during the pass); a refinement of the two outcomes presented in chat. One panel on `20-react-browser.json` (`sum by (outcome) (rate(...)) or
vector(0)`, `noValue` 0), so the metric-coverage ratchet stays green.

### 2. The doctrine (`react_agent_prompt.txt`, static part, English, generic examples)

- **Verify** (OBSERVE step): a result counts only if it answers what was asked — the right
  entity, date or period, place, and complete (a list the tool says it cut, a partial answer
  do not count). A result that answers another question is an obstacle, exactly like an error.
- **Obstacles** replace line 18: every fact the answer will state, cross-checks included, goes
  through the recovery ladder when it is missing, wrong or unverifiable; results already obtained
  are kept meanwhile.
- **Cross-check depth** (line 21) keeps its limit and adds: recovering a cross-check already
  started is not a new cross-check.
- **Decide** (line 24): a fact still missing after the ladder is declared in `<unresolved>`, then
  the turn ends.
- **Recovery ladder**, replacing ZERO-RESULT HANDLING, SELF-CORRECTION & RECOVERY and « Do NOT
  call the same tool with identical arguments twice »:
  1. your own call — correct the parameters (absolute dates, exact values, a wider window, a
     relaxed query) and call again; an error payload says what to fix;
  2. another source — a sibling tool of the domain, then, for public facts, the web search or
     page fetch tools of this turn's list; the fact is marked with the source used;
  3. conclude — list the fact in `<unresolved>` with the rungs tried.

  Never repeat a call that already failed with the same arguments; stop climbing when no rung
  left can bring new information. No attempt count is written: the code enforces none per fact,
  and a prompt states only what the code enforces (ADR-284).
- **A script is promised only where it can run** (ADR-284): the sandbox rung is added to the
  `<Computation>` block, rendered only when `run_python_tool` is bound — its « FILL A GAP » job
  gains « including a fact the recovery ladder could not obtain from your tools »; the network
  block (rendered only under a network offer) already carries the unknown-host rule.
- **Absolute dates**: every relative date or time expression, in any language, is resolved
  against Date and Timezone in `<Context>` into ISO 8601 before it goes into a tool parameter; an
  ambiguous one (« tomorrow » just after midnight) is decided and logged as an assumption. The
  exemplar passes ISO values.
- **Final message**: a fact obtained outside the tool dedicated to its domain carries
  `Source: <site or tool> (fallback)`; the `<unresolved>` block closes the message.

**`react_recovery_directive.txt`** (technical English, one placeholder `{unresolved}`, rendered in
`nodes/react_recovery.py`, added to `PromptName`): the facts the answer above declared
unresolved; apply the ladder to each, rungs not yet tried first; then write the final message
again, COMPLETE — it replaces the draft, so it restates every finding, updated — keeping in
`<unresolved>` only what is still missing among the facts set out for. Measured: told to
« conclude again », a model wrote about its gaps alone and the list its draft held was lost.

**Response prompt** (`response_system_prompt_base.txt`, `<DataAuthority>`, static part, one line
each): a fact marked as coming from a fallback source is stated with that source, in a few words;
a fact listed as unresolved is said to be missing, with what was tried, never estimated. The
response's cached prefix changes once, at deployment.

### 3. Absolute dates

- **Prompts**: the house directive — one line in the static part — in the ReAct prompt (above),
  `initiative_prompt.txt` and `smart_planner_prompt.txt`: every relative date or time expression,
  in any language, is resolved against the current date and timezone of the context into ISO 8601
  before a tool parameter is written.
- **Weather tool contract** (`weather/catalogue_manifests.py::_DATE_PARAM`, shared by the daily
  and hourly forecasts): « an ISO date (YYYY-MM-DD) or ISO datetime — for a calendar event, its
  `start_datetime`; resolve relative expressions yourself from the current date ». The manifest no
  longer promises a « temporal reference ».
- **No silent fallback**: `_calculate_target_date` no longer maps an unreadable reference to
  today. The tool returns a structured failure with `ToolErrorCode.INVALID_INPUT` (propagated by
  `format_registry_response`, which today writes one generic code for every failure) and a
  technical English message naming the value, the accepted format and the person's current date,
  e.g. `date 'demain' is not readable: pass an ISO date (YYYY-MM-DD); today is 2026-09-24
  (Europe/Paris)`. In ReAct the failure carries the ADR-303 structural marker and rung 1 fires;
  in the pipeline the runtime failures directive states it.
- **Lenient reading kept, not published**: the English words (`today`, `tomorrow`, `in N days`,
  `this week`) and localized absolute dates (« jeudi 9 avril 2026 »), so the pipeline planner does
  not regress. No multilingual reader of relative words: a second authority on languages, where
  the model holds both the date and the language.
- **Inventory**: the weather tools were the only ones to fall back in silence (calendar: ISO
  bounds; reminders: a structured format that raises; health: ISO bounds; telephony: absolute
  dates required by its own prompt).

### 4. Settings

`REACT_RECOVERY_PASSES_MAX_DEFAULT = 1` in `core/constants.py`;
`react_recovery_passes_max: int = Field(default=REACT_RECOVERY_PASSES_MAX_DEFAULT, ge=0, le=3)`
in `core/config/agents.py`; the
variable with its comment in `.env.example`, `.env.prod.example`, `.env`, `.env.prod` and the four
demonstrator files (CRLF preserved where the file has it). No other new setting.

### 5. Tests (TDD)

- Parser: block present, absent, empty, « none », case, several lines; a block written inside
  `<thought>` still counts — the declaration matters, not where the model put it.
- `should_recover` truth table; the router's new branch.
- Node: the draft removed and recorded with its predecessor as anchor; the draft and the
  directive shown after the anchor, never in `state["messages"]`, roles alternating, the turn's
  context kept after its question; composed again after an interrupt; `react_agent_result.recovery`.
- Graph scenario with a scripted fake chat model: a draft declaring a gap → the directive → a
  tool call → a final answer; one pass, one answer left in the thread.
- Weather: an unreadable reference refused with its message and code; English words and
  localized absolute dates still read; the manifest text.
- Existing guards: reset guard (new decider), placeholders produced, `PromptName` sync, prompt
  cache hygiene, metric-coverage ratchet with the new panel, file-size and complexity ratchets.

### 6. Validation bench (paid, at most 2 USD, no Anthropic call)

`task react:recovery:measure` (a script in `scripts/`, the `react:selection:measure` shape):
eight scenarios through the loop's own functions with stubbed tools — a wrong day served; an
error then a success once corrected; an empty result a relaxation resolves; the dedicated tool
unavailable and the fact found by web search; a truncated list; every source failing (the gap
declared, the pass bounded); the 2026-09-23 turn itself (a trip whose weather is a cross-check,
today's forecast served first); a control turn with no obstacle — each run under the current
doctrine and under the one it replaces (`--baseline-prompt`), everything else equal. Three configured
model families with distinct cache mechanisms, chosen from the dev catalogue at run time and
announced with the estimate before the run; three repetitions each. Each scenario binds only its
relevant tools (the dedicated tool, its siblings, web search, page fetch, a stubbed sandbox) to
hold the cost. Measured per scenario and family: fact obtained, gap honestly declared, useless
insistence (a repeated failing call), extra calls and cost; the control turn must show no extra
call. Run once the implementation is green, never before.

### 7. Documentation

ADR-310 (« a ReAct turn is judged on its result »), amending ADR-248, ADR-303, ADR-298,
ADR-284 and ADR-184; its French entry in `ADR_INDEX.md`; `task release:sync-counts`; CLAUDE.md —
the « five ReAct invariants » become six — then `task docs:sync-agents`;
`docs/technical/REACT_EXECUTION_MODE.md`; `docs/ARCHITECTURE_LANGRAPH.md` (the new node in the
loop's diagram); `docs/guides/GUIDE_TOOL_CREATION.md` (« a tool never replaces a value it cannot
read »).

## Rejected

- **B, doctrine only**: the prompt already had a recovery rule and it did not fire; persistence
  would stay whatever each configured model makes of it.
- **C, an independent verifier**: the strongest detection, but one more model call on every
  ReAct turn (cost, 1-3 s) and a second authority on « is the answer complete ».
- **A multilingual reader of relative dates**: see section 3.
- **A per-fact attempt counter in code**: the loop cannot tell which call serves which fact.
- **Persisting the directive as a message**: later turns would read it as the person's words.
- **A second lookup to confirm a fallback fact**: owner decision.
- **Recovery in pipeline mode**: out of scope; the date contract benefits both modes.

## Risks

- A model that never writes `<unresolved>` gets no pass — today's behaviour, measured by the
  bench (declaration rate).
- A model that over-declares costs at most `REACT_RECOVERY_PASSES_MAX` passes per turn.
- The removed draft may already have been streamed as reasoning to the progress panel; it only
  leaves the thread.
- A recovery reaching an unknown host waits for the person (owner decision); the directive and
  the permission question say which source was tried first.

## Acceptance criteria

- The 2026-09-23 turn, replayed with the weather stub serving the wrong day, ends with the
  25 September forecast or with a stated gap listing the rungs tried — never with the 24th
  presented as the 25th.
- With no declared gap, no extra model call; with one, at most `REACT_RECOVERY_PASSES_MAX`
  passes, and none once a budget is reached.
- The thread keeps one answer per turn; the directive never appears in it.
- A fallback fact reaches the answer with its source; an unresolved fact is said missing.
- `demain` sent to the weather tool is refused with the accepted format and today's date; the
  English words and localized absolute dates still read.
- Every existing gate is green (lint, unit fast, guards, ratchets, documentation preview), and the
  bench stays within 2 USD with no Anthropic call.
