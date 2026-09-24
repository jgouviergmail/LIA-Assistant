# ADR-310 — A ReAct turn is judged on its result: what the loop sets out to obtain ends obtained or declared, and a declared gap buys a bounded recovery pass

**Status**: accepted — 2026-09-24 (owner decisions: a result-oriented loop that uses every tool it has within bounds; a network run to an unknown host always asks the person; a fact from a fallback source is given with its source; on by default; approach A below)
**Amends**: ADR-248 (a sixth ReAct invariant), ADR-303 (a gap the loop could not close is SAID, with what was tried), ADR-298 (the sandbox as a rung of the ladder — its permission question unchanged), ADR-284 (no attempt count promised; the script rung only where it runs), ADR-184 (the weather tool's date contract published where the loop reads it)

## Context

On 2026-09-23 the owner asked, in ReAct mode on dev: « je veux aller chez mon frère demain en
voiture, comment faire pour arriver à 19h pour l'apéro ? ». The loop found the contact, computed
the route (arrival 2026-09-25 at 19:00), called the weather forecast with `date: "demain"`, and
answered « I could not get the forecast of the 25th — the service sent me the 24th's ». It
stopped by itself after 4 iterations of the 70 its budget allowed. Four causes, each read in the
logs or the code:

1. **The tool answered another question and said nothing.** `_calculate_target_date` read
   English words only — the pipeline's semantic pivot translates the query, the ReAct loop reads
   the person's own words — and mapped any unknown reference to today:
   `{"date_ref": "demain", "target_date": "2026-09-24", "offset": 0}`. Its manifest invited the
   value (« Accepts: temporal reference ('today', 'tomorrow') »). Counter-proof the next minute:
   with `2026-09-25` the tool served the right day. The initiative was misled the same way.
2. **The recovery rules missed the case.** The prompt recovered on an ERROR or an EMPTY result;
   a success that answers another question is neither.
3. **The prompt told the loop to give up on enrichments** (« Never stall the primary intent for
   secondary enrichment »), and the weather of a trip was a cross-check the loop had started.
4. **Nothing named another source, and nothing checked the end.** The loop ended as soon as the
   model called no tool, so persistence rested entirely on how the configured model read one
   sentence — the wrong place, since every slot is configurable and models are interchangeable.

## Decision

**A ReAct turn is judged on its result, by a mechanism in the loop and not only by a sentence
in a prompt.**

1. **What the loop sets out to obtain ends obtained or declared.** Every fact the loop set out to
   obtain — what the person asked for, and each cross-check it started — goes through the
   recovery ladder when it is missing, wrong or unverifiable, and ends either obtained or
   declared in an `<unresolved>` block that closes the final message, one line per fact with the
   rungs tried — never dropped in silence. No block when nothing is missing. A detail nobody
   asked for and nobody looked up is not a gap, nor is a fact obtained from another source: it
   carries that source (`Source: … (fallback)`). The anchor is what the loop DID, because both
   subjective anchors failed on the bench (Consequences).
2. **One reader, one predicate.** `declared_unresolved` (`nodes/react_recovery.py`) reads every
   block, case-insensitively, wherever the model put it; a block runs from the LAST opening
   before its closing — on the runtime proof the model named the tag in its reasoning before
   writing the real block, and read from the first opening the prose between them became twelve
   « facts »; an empty line, the `...` placeholder or a lone « none » in six languages declares
   nothing. `should_recover` is true when the last message is a final answer that declares a
   gap, fewer passes were taken than `REACT_RECOVERY_PASSES_MAX` (default 1, bounded 0-3, `0`
   switches the pass off), and `react_exit_reason` — which it CALLS, never copies — lets the loop
   go on. The router reads it in its « no tool calls » branch.
3. **A node that calls no model.** `react_recovery` removes the draft from the thread at once
   (`RemoveMessage`, the compaction's own mechanism) and appends `{anchor_id, draft, unresolved}`
   to `react_recovery_passes` — declared in `MessagesState`, reset by `react_turn_reset()`, held
   there by the reset guard, which learned the new decider. Removing the draft AT the pass, not
   at finalize, keeps one answer in the thread on every exit of the loop, the draft hand-off to
   the HITL dispatch included.
4. **What the model is shown is transient.** `with_recovery_directives` puts, on every later call
   of the turn, the draft and a directive (`react_recovery_directive.txt`) right after the
   draft's place — after the system messages glued to it, so the turn's context stays after its
   question (ADR-308). Neither is written to `messages`: no later turn reads the directive as
   something the person said, the roles alternate on every provider, and the prefix before the
   anchor is the one the provider's cache already holds. Passes sharing an anchor (a pass whose
   reply called no tool leaves the next draft the same predecessor) are shown together, in the
   order they were taken. The final message after a pass REPLACES the draft, so the directive
   asks for it complete — every finding restated, updated.
5. **The outcome is counted once, and a pass never trades an answer for nothing.**
   `react_finalize` merges `react_agent_result["recovery"]` (`passes`, `outcome`: `resolved`,
   `partial`, `still_unresolved`, `cut`) through `recovery_report`, which keeps the node's
   complexity where the ratchet froze it, and counts `react_recovery_turns_total{outcome}`
   (dashboard 20). A pass that ends with no usable answer — an empty reply, or a budget that
   stops it with calls pending — hands the last draft back as the final message: the draft left
   the thread AT the pass, and a complete answer the turn already had is never replaced by
   nothing (an empty reply is `still_unresolved`, never `resolved`). The debug panel's ReAct
   section draws the passes and their outcome (« Recovery »).
6. **The doctrine that feeds it** (the ReAct prompt's static part): VERIFY — a result counts only
   if it answers what was asked: the right entity, date or period, place, and complete (a list
   the tool says it cut is not); the RECOVERY LADDER — (1) the loop's own call corrected: an
   absolute date, an exact value, a wider window, a relaxed query, what an error payload says to
   fix; (2) another source: a sibling tool, then, for public facts, the web search or page fetch
   tools of the turn's list, the fact marked with its source; (3) the declaration. Never repeat a
   call that already failed with the same arguments; stop when no rung left can bring new
   information. No attempt count is written, because nothing counts attempts per fact (ADR-284).
   The sandbox rung lives in the `<Computation>` block, rendered only when `run_python_tool` is
   bound; a network run to an unknown host still asks the person (ADR-298). The response prompt
   states a fallback fact with its source, and a declared fact as missing with what was tried —
   never an estimate.
7. **Absolute dates.** The ReAct, pipeline planner and initiative prompts resolve every relative
   date or time expression, in any language, against the current date and timezone of their
   context into ISO 8601 before a tool parameter is written; the ReAct exemplar passes ISO
   values.
8. **A tool never replaces a value it cannot read.** The weather forecasts refuse an unreadable
   date with `ToolErrorCode.INVALID_INPUT` and a technical English message naming the value, the
   accepted format and the person's current date (`tools/weather_dates.py`, extracted —
   `weather_tools.py` shrank from its frozen 922 lines to 820). The contract is ONE constant,
   `FORECAST_DATE_DESCRIPTION`, read by the manifest AND by both `@tool` signatures: the loop
   binds the `@tool` schema, never the manifest, which is how the manifest's promise had never
   reached it. The English words and localized absolute dates are still read, never published.

## Consequences

- **Measured on the bench** (2026-09-24, `task react:recovery:measure`: eight scenarios of
  deterministic stub tools through the loop's own functions — the system prompt builder, the
  predicate, the transient directive, the outcome — on three model families with distinct cache
  mechanisms, deepseek-flash at `none`, gpt-6-luna and gemini-3.7-flash at `low`, three
  repetitions each, the final doctrine against the one it replaces with everything else equal;
  144 runs for the comparison, 1.26 USD for every run of the work, no Anthropic call):
  - facts obtained on the seven obtainable scenarios: **58/63 against 50/63** (deepseek-flash
    21/21 against 18/21, gpt-6-luna 18/21 against 16/21, gemini-3.7-flash 19/21 against 16/21);
  - the incident's own shape — a trip whose weather is a cross-check, today's forecast served
    first: the right day obtained **7/9 against 3/9**; a run that called the forecast and ended
    without the right day **0/9 against 5/9**; the wrong day stated as tomorrow's, 0 in both; 2
    runs of 9 did not check the weather at all, which stays the loop's choice;
  - a clean control turn: no pass and no extra call on any family. The static prompt grew by 388
    tokens (1,654 → 2,042, o200k), read from the cache where the provider's prefix cache works,
    paid in full where it does not;
  - every source failing: the gap declared 9/9 with the rungs tried, one pass each, then
    concluded — at 5.6 tool calls per run against 3.3, and 6 identical failing calls repeated
    against 0: the price of a bounded second effort, which the loop guard (ADR-170) bounds;
  - two passes recovered a fact their draft had declared missing (tomorrow's forecast; a meeting
    found once the search was relaxed); three were spent by one family declaring a fact it held
    from a web search « not confirmed by the official source »;
  - a fallback source was named in 6 runs of 9 against 0.
- **Three wordings and one parser were corrected by measurement before acceptance.** « One line
  per fact the answer needs » made two families of three declare wind and rain on the clean
  control, a pass each that could change nothing. « A fact the answer cannot do without » let 4
  replays of the incident in 9 drop the wrong-day forecast without a word (one wrote « not a fact
  the answer depends on »). « Conclude again » made a model rewrite its draft as a list of gaps,
  and the list of appointments it held never reached the answer. And on dev a model NAMED the
  tag in its reasoning before writing the real block: read from the first opening, the prose
  between them became twelve « facts ».
- **Runtime proof on dev** (a dedicated proof account, ReAct mode): « Quel temps fera-t-il à Lyon
  demain ? » passed `date: "2026-09-25"` to the forecast (`target_date 2026-09-25, offset 1`,
  against `demain` → 2026-09-24 on 2026-09-23) and took no pass. The incident's own question, on
  an account with no contacts connected, climbed contacts, other contacts, the agenda and the
  location, took one pass (`react_recovery_pass_started`, then the mailbox and the drive, sources
  it had not tried), and settled `still_unresolved` with the gaps said and the rungs listed —
  one answer in the thread.
- A turn with a declared gap costs at most `REACT_RECOVERY_PASSES_MAX` passes of at least one
  model call each, under every existing budget: iterations, compute and tool time, ADR-170's
  repeated-call guard, the sandbox's runs per turn. A provider failure on a pass's call fails
  the turn like any other iteration's call would: the draft is in the turn's record, not in an
  answer.
- **The final cold review found three defects before acceptance**, each closed by a failing test
  first: two passes on one anchor were shown in reverse order (reachable for any
  `REACT_RECOVERY_PASSES_MAX` of 2 or 3); an empty reply after a pass lost the draft and was
  counted `resolved`; and the debug panel the Decision promised never read the outcome. The
  lone « none » is also read in the forms the six languages write it (`无。`, `—`, `nessuna`,
  `keins`).
- Deferred, stated: the pass is not drawn in the progress panel (it has no display metadata);
  a turn that took a pass and then prepared a draft for confirmation settles through the HITL
  hand-off and is not counted by the outcome metric; a PAST ISO date is still served by the
  weather tool from today onward, which the VERIFY rule treats as an obstacle.
- The draft may already have been streamed to the progress panel as reasoning; it only leaves
  the thread. The response prompt's static part changed, so its cached prefix is written again
  once at deployment.
- A model that never writes `<unresolved>` gets no pass — the behaviour before this ADR; on
  every-source-failing the declaration rate was 9/9.
- Dollars are not comparable across two runs on DeepSeek, whose tariff has hourly windows
  (off-peak at half price): the two doctrines ran on either side of one. Calls and tokens are.
- Not measured: Anthropic (no credit for this work — unit tests only).

## Rejected

- **Doctrine only**: the prompt already had a recovery rule and it did not fire; persistence
  would stay whatever each configured model makes of a sentence.
- **An independent verifier**: the strongest detection, but one more model call on every ReAct
  turn (cost, one to three seconds) and a second authority on « is the answer complete ».
- **« The facts the answer needs » and « a fact the answer cannot do without »** as the anchor of
  a declaration: both measured and replaced (Consequences).
- **A multilingual reader of relative dates**: a second authority on languages, when the model
  holds both the date and the language.
- **A per-fact attempt counter**: the loop cannot tell which call serves which fact.
- **Persisting the directive as a message**: later turns would read it as the person's words.
- **A second lookup to confirm a fallback fact**: owner decision — the fact carries its source.
- **Recovery in pipeline mode**: out of scope; the date contract serves both modes.

## References

- `apps/api/src/domains/agents/nodes/react_recovery.py`, `nodes/routing.py`, `nodes/react_nodes.py`,
  `graph.py`, `models.py`, `utils/react_budget.py`
- `apps/api/src/domains/agents/prompts/v1/react_agent_prompt.txt`,
  `react_recovery_directive.txt`, `react_computation_prompt.txt`,
  `response_system_prompt_base.txt`, `initiative_prompt.txt`, `smart_planner_prompt.txt`
- `apps/api/src/domains/agents/tools/weather_dates.py`, `tools/weather_tools.py`,
  `weather/catalogue_manifests.py`
- `apps/api/src/infrastructure/observability/metrics_react.py`, dashboard
  `20-react-browser.json` (« Recovery Passes (by outcome) »)
- `apps/api/scripts/react/measure_recovery.py`, `task react:recovery:measure`
- [ADR-248](ADR-248-React-Memory-Parity-And-Progress-Earned-Budget.md),
  [ADR-303](ADR-303-Tool-Failure-Restitution.md), [ADR-298](ADR-298-Sandbox-Egress-Toolbox.md),
  [ADR-284](ADR-284-Prompt-States-What-The-Code-Enforces.md),
  [ADR-184](ADR-184-Published-Bounds-And-Non-Prescriptive-Verdicts.md),
  [ADR-170](ADR-170-React-Compute-Budget-And-Loop-Guard.md),
  [ADR-308](ADR-308-ReAct-Cross-Turn-Prompt-Cache.md)
