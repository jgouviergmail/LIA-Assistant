# Workstream 1 — Accompanied focus lounge

[Master plan](README.md) · [Contracts](contracts.md) ·
[Decisions](decisions.md) · [Launch prompt](prompts/01-focus.md)

**Status:** first-release direction accepted on 2026-11-03; detailed design only.
Business implementation is not authorized by this framing request.
**Accepted decisions:** D01, D02, D07, D09, D10 and D11.

## Job and useful result

“When I struggle to begin or keep going, help me commit to one concrete step,
work alongside others without exposing my work, and leave knowing what to do next.”

Example: choose “draft the introduction,” optionally select a native ticket, join
a quiet interval, work, then record whether the intended step advanced. The useful
result is the work interval plus a deliberate next step, not avatar attendance.

## Accepted first-release scope

- Solo focus and voluntary peer co-presence using existing accepted-peer rules.
  Participants may share a rhythm without sharing their intention or screen.
- A duration chosen from server-published bounds, explicit start, leave/stop and
  a clear end state. Shared sessions use a common deadline; a person's departure
  never silently pauses everyone else.
- Private intention and optional Workboard reference. Public projection contains
  only consented participation/availability and the shared rhythm.
- Optional private LIA assistance at preparation, an explicit request for help,
  or debrief. No continuous surveillance, per-minute LLM or generated heartbeat.
- A small private recap and next-step draft; saving and ticket updates are explicit.

Deferred under D01: paid group facilitator, peer audio rooms, screen monitoring,
automatic productivity scoring, mandatory streaks and team dashboards. The basic
interval remains useful when LLM access is disabled or quota is exhausted.

## Interaction and game design

The lounge gives a visible transition into a quiet period, a shared clock and a
gentle completion cue. Avoid unnecessary animations or chat interruptions.
Display encouragement from explicit peer gestures, not inferred judgments about
how hard somebody is working. The owner controls whether peers see participation.

At the end, distinguish “interval ended” from “objective achieved.” Offer a short
self-report and an optional next step. A person can leave without being publicly
labelled as failing. Existing radio/Live audio priority must remain intact.

## Lifecycle and technical direction

Recommended session lifecycle: prepared → active → ended or stopped; an interrupted
client re-reads authority. Any expiry or recovery state must be explicit. Final
names and whether a solo pause exists belong to the feature design.

Keep a server-owned deadline and revision, so backgrounding, another tab or a
slow clock cannot extend or complete an interval incorrectly. No per-second API
write is needed. Separate an individual's session from the shared rhythm and
consent. The room host is not an authority over another account's private data.
Account/capability loss revokes interaction and stops further paid work.

Reuse World entry/privacy contracts (F01), native timer/lease/revision patterns
(F12), and Workboard references (F10). Do not put private intentions into shared
World state. Choose minimal persistence after D07; no new project entity is
required for focus alone.

## Paid work and actions

| Operation | AI needed? | Attribution and records | Authority |
|---|---|---|---|
| Join, timer, presence, end cue | No | Session metadata only; no invented token usage | Native account, peer consent and session revision |
| Help formulate one step | Optional | Requester's platform run and decision, bounded input | Explicit request; only selected context |
| Private debrief | Optional | Requester's platform run and decision | Explicit request; no automatic personal learning |
| Update/create a real ticket | Native operation; AI optional | Existing Workboard/action/consultation path | Existing permissions and HITL where applicable |

“No AI coaching available” does not prevent stopping, reading or saving a
deterministic result. A quota refusal must never trigger a fallback paid model.

## Acceptance criteria

| ID | Observable pass condition |
|---|---|
| FOC-01 | Start, work and finish an interval with all LLM calls disabled; no provider request is emitted by timer/presence/rendering. |
| FOC-02 | Refresh, backgrounding and a second tab preserve the same server deadline; duplicate start/end commands do not create a second interval or completion. |
| FOC-03 | Another participant and an unrelated account cannot retrieve the intention, selected ticket, coaching, recap or usage by HTTP, socket, guessed ID or shared projection. |
| FOC-04 | Explicit private coaching produces usage attributed once to its requester and a native decision with matching run identity; deterministic activity produces none. |
| FOC-05 | Account or instance quota refusal blocks new coaching; rate/concurrency limits stop repeated requests; the running timer and exit remain usable. |
| FOC-06 | A provider timeout after dispatch becomes an uncertain attempt; reconnect/refresh does not pay again automatically. |
| FOC-07 | Leaving, blocking a peer, capability loss and account change stop inappropriate presence/interaction; a departed host cannot erase another person's result. |
| FOC-08 | Ending an interval does not mark a Workboard ticket done. An explicit update follows the same native permissions and action path as outside World. |
| FOC-09 | Keyboard, touch, narrow-screen and reduced-motion flows can start, inspect and stop the activity; audio controls obey existing arbitration. |
| FOC-10 | Retained records obey approved export/delete/expiry rules; a late model response cannot recreate deleted content. |

## Qualification and value signals

Use real Redis/database tests for claims, deadline recovery and cross-account
revocation, plus native browser journeys for backgrounding, account changes and
mobile layout. Test billed assistance with native accounting fixtures before a
separately authorized real-provider probe.

Measure whether users begin the intended work, complete a voluntary interval and
report a useful next step. Compare solo and co-presence feedback without treating
elapsed time as productive output. Export reusable lifecycle conventions and test
fixtures to the theatre chat; avoid imposing the focus state machine on rehearsal.
