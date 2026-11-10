# ADR-375 — Learned usage becomes proposals, decided in one click

**Status**: Accepted, 2026-11-08.
**Date**: 2026-11-08

**Amends**:
[ADR-214](ADR-214-Habitudes-Utilisateur-Apprentissage-Deterministe.md) — the hour no longer
conditions a recurring request: the shape locks and their eight settings retire, a recurring
NEED replaces them, and the heartbeat's missed-routine offer and the chat's text suggestion,
which read those locks, leave with them.
[ADR-238](ADR-238-proposals-inbox-adaptive-react.md) — the proposals inbox reads
`habit_proposals`, accepting carries a proposal out, and `/heartbeat/offers` retires.

## Context

On 2026-11-06 the owner asked why habits had produced nothing in months. Measured that day on
production (read only, counts and hours, no content) and on dev:

- **The lock asked for the impossible.** A routine was offered only for « the same request at
  the same hour » — a resultant length R ≥ 0.8 of the ask hours, agreeing halves, a narrow span,
  a minimum density. Real people ask for their agenda at 7 h one day and at 13 h the next;
  production had never opened a single offer.
- **What LIA already records says more than the hour.** Routines relaunched by hand hours after
  their schedule; notifications sent for weeks without a reaction; a person active long before
  their notification hours start; a domain asked for with no account connected. None of it
  reached a proposal.
- **The two surfaces were mute.** The missed-routine offer ranked fourth in the heartbeat's
  context and lost to any open loop, meeting or e-mail; the chat suggestion read the same lock.

The owner's direction: learn how the person USES LIA and propose concretely, never rely on a
fixed hour, and simulate on the possible usages.

## Decision

1. **The hour describes, it never decides.** A recurring need is a registered domain asked on
   at least `RECURRENCE_MIN_DISTINCT_DAYS` (4) distinct days, over at least
   `RECURRENCE_NEED_MIN_WEEKS` (2) ISO weeks, the latest at most `RECURRENCE_NEED_RECENT_DAYS`
   (14) days ago, inside `RECURRENCE_WINDOW_DAYS` (35). Its usual hour is the median of its
   hours and the time a proposed routine is ready by is their first quartile, floored to the
   quarter hour — both read across midnight (the cut falls in the widest empty arc), so a need
   asked at 23 h and at 1 h is a night need, not a noon one. Cadence: `weekly` when one weekday
   holds `RECURRENCE_WEEKLY_DOW_FRACTION` (0.75) of at least `RECURRENCE_WEEKLY_MIN_SAME_DOW`
   (4) days, `weekdays` with at most `RECURRENCE_WEEKEND_TOLERANCE` (1) weekend day, `daily`
   otherwise. A need is at the automation bar when its days are at least
   `RECURRENCE_AUTOMATE_SHARE` (0.40) of the person's active days and at least
   `RECURRENCE_AUTOMATE_MIN_DAYS` (12) days; a weekly need always is.
2. **Six kinds of proposal, one row per (person, kind, key), facts only.** The sentence is
   built by the reader in their language; the row stores days, hours, counts and ids.
   - `automate_need` (key: the domain) — a need at the bar, on an automatable domain (agenda,
     e-mail, tasks, weather, health, text messages), no routine reading it near its
     hour. Accepting creates a time routine with a title and an instruction in the person's
     language, the cadence and the time pre-filled, in their time zone (`need_domains.py`
     declares which domains a routine can sum up). A routine already
     reading it at another time is CITED, never added to: the new routine is a dedicated one.
     It WAITS for the connector its domain depends on — a routine that would fail every
     morning is not proposed; `connect_source` speaks first. Whether a routine serves a
     domain is read from the domains its LINKED runs read (`scheduled_action_runs.run_id`);
     a routine whose reads are unknown holds the kind for the night, never a duplicate.
   - `shift_routine` (key: the routine) — at least 3 manual launches on at least 3 days, 2 h or
     more from its schedule. Accepting moves the schedule to the median manual time.
   - `fix_routine` — a routine the system disabled, or 3 consecutive failures. Accepting opens it.
   - `extend_notification_window` (key: `heartbeat`) — proactive notifications on, presence
     outside their hours on at least 5 days, 8 hour-cells and 25 % of the present cells;
     the extension takes contiguous frequent hours only, at most 3 h on each side.
   - `review_notifications` (key: `heartbeat`) — at least 20 proactive notifications in the
     window, none with a reaction. A question, not a verdict: accepting pauses them, « Never »
     keeps them.
   - `connect_source` (key: the connector category) — a domain asked on at least 3 days with no
     active connector of its category. Accepting opens the connectors.
3. **A life the person decides.** Open → `accepted` (may reopen after
   `HABITS_PROPOSAL_RESURFACE_DAYS`, 90, if still true), `dismissed` « Later » (reopens after
   `HABITS_PROPOSAL_SNOOZE_DAYS`, 14), `refused` « Never » (a tombstone; three refusals of one
   kind silence the kind). An open proposal whose rule stops holding is withdrawn the next
   night — unless its kind could not be judged (an observation missing): doubt never withdraws.
   « Forget everything » erases them; « Learn my habits » off closes every door.
4. **Accepting is one transaction, claimed before it acts.** The person's row first (the order
   every act and the nightly recompute take), then the proposal by one conditional statement on
   its open status, then the kind's handler, then one commit. A handler that refuses — the
   routine cap reached, a routine gone or changed, the settings changed since — rolls
   everything back and answers 409 with a stable reason the card translates; the proposal
   stays open. Two clicks at once create one routine. Nothing is written to the registers: a
   click with no model involved is not an act of the assistant.
5. **`habits` imports neither `agents` nor `heartbeat`.** What they own reaches it through two
   ports and a handler registry they install at boot (`usage_ports`, `proposal_actions`); the
   boot refuses a missing port, handler or need-domain decision.
6. **The chat shows at most one, decided by code.** Under an answer, the open proposal of the
   turn's own domain (its automation, or the connector it lacks) when the chat has not shown
   it within `HABITS_PROPOSAL_CHAT_REPEAT_DAYS` (7), else the oldest one it never showed; never
   more than one per `HABITS_PROPOSAL_CHAT_GAP_HOURS` (24), whatever became of the last one.
   The response node, where both modes converge, asks for it at the end of an answer the model
   wrote — never under a draft's confirmation, a routine's run, rows that stay out of the chat
   or a surface that draws no card — and hands it on the follow-up chips' channel: archived
   with the answer, carried in its `done` chunk, read back through one schema. The showing is
   claimed before the answer carries it, under the person's lock taken WITHOUT waiting: a
   person busy deciding, writing in another tab or being recomputed simply gets no card this
   turn. The card takes the comfort slot before the chips and yields to a pending approval and
   to the usage wall; its three answers are the inbox's. `RECURRENCE_SUGGESTION_ENABLED`
   switches the card off for the instance.
7. **Retired**: the shape locks and their eight settings; the heartbeat's missed-routine offer
   (context, prompt section, decision field, metric, panel); `/heartbeat/offers`; the text
   suggestion and its promotion in the chat; `user_habits.muted_until_reproof`. The column
   `heartbeat_notifications.habit_offer_id` stays as a record nobody writes. The request ledger
   keeps one hour per clock hour (cap 24) instead of five raw hours a day.
8. **Not in v1**, said rather than half-done: a « shortcut » proposal (no shortcut function
   exists), chains of requests (a routine reading several domains absorbs them), activating
   interests, the person's own wordings as routine prompts, and needs that exist only through
   their parameters (the same web search every morning) — the latter is a need the panel
   shows, never an automation.

## Measurements

**Simulation** (`task habits:proposals:measure`, 13 generative personas × 100 seeds × 35
nights, the real rules every night, the shipped defaults). A persona says what a person does,
never at a fixed hour.

| Persona | Expected, open on night 35 (first night, median) | Unexpected |
|---|---|---|
| Agenda most evenings | automation, daily: 100 % (14) | — (weather reaching the bar, defensible: 3 %) |
| Mail on weekdays | automation, weekdays: 71 % (17) | — (daily when two weekend reads fall in the month, defensible: 29 %) |
| Explorer, varied searches | nothing | a weekly automation by coincidence: 3 % |
| The same web search | nothing (v1) | — |
| Routine relaunched by hand | move it: 100 % (7) | — |
| Night owl | widen the notification hours: 100 % (9) | an agenda automation: 1 % |
| Never reacts | ask about the notifications: 100 % (20) | — |
| Engaged | automation, daily: 97 % (24) | — (hours widened for activity before 9 h, defensible: 22 %) |
| Sparse, no connector missing, drifting (stopped) | as expected | — |
| Missing mail connector | connect: 100 % (9); agenda automation: 96 % (24) | — |
| Sunday planner | agenda and tasks, weekly: 93 % each (28) | — |
| Tester with a morning routine | mail 70 %, agenda 81 %, hours 100 %, question 100 % | — |

False positives stay at or below 3 %. A « defensible » proposal is one an observer would not
expect nor call wrong; it is reported apart, never counted as a hit.

**Production replay** (export of 2026-11-06, read only, the five active accounts, the rules as
shipped): one account would receive five proposals — two automations citing its existing
morning routine, a routine moved to the time it relaunches it by hand, its notification hours
widened, and a question on 102 notifications met with silence; two accounts one question each
(37 and 22 unanswered notifications); two accounts nothing (5 and 2 active days). One account's
web search, asked on 18 of 31 days, is a need v1 does not automate: an honest silence.

**Dev, end to end, proof account, no model**: a weather need seeded on 20 days → the nightly
recompute opens `automate_need:weather` (daily, 07:15, 20 of 20 days) → the chat card is
claimed, a second turn inside the gap shows none → accepting creates « Ma météo », daily at
07:15 in the account's time zone, and adds a positive signal to the need → everything the
proof wrote removed, the ledger restored key by key.

## Consequences

- Proposals come from what a person does, at whatever hour. Nothing new is stored but the
  proposal rows; no model is called; no spend is added.
- An automation needs about twelve days of asks: the first night is reported per persona, and
  lowering a bar to make one appear earlier is a false-positive cost the harness shows.
- Every bar is a setting with its default in `core/constants.py`; recalibrating means replaying
  `task habits:proposals:measure`, never editing a default to make a persona pass.
- `habit_proposals_total{kind, transition}` counts every move, the chat's showings included
  (`shown_in_chat`); `habit_proposal_action_failures_total{kind, reason}` counts the refusals.
