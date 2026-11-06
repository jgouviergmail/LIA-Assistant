# Workstream 4 — Base camps for real projects

[Master plan](README.md) · [Contracts](contracts.md) ·
[Decisions](decisions.md) · [Launch prompt](prompts/04-base-camps.md)

**Status:** first-release direction accepted on 2026-11-03; detailed design only.
Business implementation is not authorized by this framing request.
**Dependencies:** native Workboard authority; focus only for its launch/result
integration. Theatre and language links are optional.
**Accepted decisions:** D01, D07–D11, especially D08 (owner-private first release).

## Job and useful result

“When a project takes several days, help me see the outcome, resume the next
useful step, and distinguish actual results from plans and waiting work.”

Example: prepare a presentation. The camp holds the intended outcome and selected
references, displays the real Workboard tickets, starts a focus interval on the
next step, and brings back its explicit recap. Completion depends on the
presentation/result and the native ticket state, not on time spent in World.

## Accepted first-release scope

- An owner-private durable camp with a clear outcome and completion criteria.
- References to native tickets, selected documents/results and optional
  rehearsal/focus sessions. The camp does not copy their authority or content.
- A view of current next steps, blockers and evidence derived from authorized
  records. Show unavailable/revoked references honestly.
- Explicit LIA assistance to break down a goal or review progress, initially
  producing a proposal. Creating/updating tickets uses native commands.
- Launch focus on a selected step and return to the same project.
- Native peer assignment through Workboard, without granting a shared camp ACL.
- Explicit archive/delete and account export behavior.

Deferred under D08: full project memberships/roles, public/shared project
dashboards, cross-account assistant delegation and a new task workflow.
Avoid a second scheduler, reminder engine or multi-agent executor.

## Product and game design

The camp is a stable place to resume work. Show a small number of actionable
objects: desired result, next step, blocker and evidence. Visual progress must
read native work facts; an unverified result cannot produce a “completed” badge.

Let the user choose the next step when priorities are subjective. Assistance
should explain a recommendation using permitted project context. A completed
rehearsal can be evidence of preparation, never proof that the real conversation
occurred. A finished focus interval is activity evidence, not a ticket transition.

## Domain and authority direction

Recommendation: a small project aggregate owns outcome, user-approved criteria
and references. Workboard remains the ticket authority. Do not store a duplicate
ticket status, assignee or result in the camp; derive the current view under the
same native visibility predicate. The owner OR assignee rule is not project-wide
access control. Native child-ticket depth also remains unchanged.

Choose minimal milestone representation only if outcome criteria and current
tickets prove insufficient. A board grouping must not invent unsupported
grandchildren or silently close children when a parent closes.

A source link requires a fresh read permission check when opened or used as LLM
context. Selecting a link earlier does not preserve a revoked grant. Prompt
context must remain scoped to the account and current selected resources; document
content is data, never authorization to call tools or widen scope.

## Paid work, registers and completion

| Operation | Path and evidence |
|---|---|
| List tickets and display known results | Native scoped reads; no new generation just to redraw the camp |
| Propose a breakdown or review | Explicit accounted planning act; name source consultations; bounded context and output |
| Create, assign or update work | Existing Workboard service/commands, current permissions and native action/HITL policy |
| Execute work assigned to LIA | Existing Workboard runner and run lifecycle; never a second background executor |
| Show progress | Derive from visible authoritative tickets and explicit outcome evidence; exact counts or unavailable |
| Save a focus/rehearsal reference | Owner-checked domain edit; no fabricated external-effect success |

Ordinary real-work learning follows current LIA policy. Fictional training content
must not enter it through a camp link. The user may explicitly promote a selected
real goal or edited next step through the ordinary native flow.

## Acceptance criteria

| ID | Observable pass condition |
|---|---|
| CMP-01 | A camp survives logout, World exit and process restart; it resumes the same outcome and references under the correct account. |
| CMP-02 | Updating a native ticket inside or outside World changes the camp view consistently; there is no parallel ticket-status authority. |
| CMP-03 | A peer assigned one ticket sees only what native Workboard authorizes, not sibling tickets, private project sources, feedback or costs. |
| CMP-04 | Revocation, reassignment or deletion of a linked source is reflected at the next access and model-context read; stale cached data cannot bypass authority. |
| CMP-05 | A generated plan is reviewable before any real action; tool execution and ticket changes retain native permissions, approval and effect records. |
| CMP-06 | Focus/rehearsal completion never automatically completes real work; project completion uses explicit criteria and actual native outcomes. |
| CMP-07 | Concurrent edits are fenced by revision or native transaction semantics; duplicate commands do not duplicate tickets, runs or paid reviews. |
| CMP-08 | Planning/review usage belongs to the requesting account and joins its native decision and source consultations; a peer cannot charge another user's assistant. |
| CMP-09 | Quota refusal blocks new paid work while preserving read/export/delete access; no repeated background synthesis runs just because the camp is open. |
| CMP-10 | Account deletion removes owned project data and appropriate links without deleting another person's tickets; resetting chat does not erase a durable camp. |
| CMP-11 | Native ticket hierarchy, waiting/approval/result behavior and runner recovery remain unchanged by the new projection. |
| CMP-12 | Keyboard/touch navigation can inspect the outcome, next work, blocker and evidence without spatial precision; every completion claim has a visible basis. |

## Validation and useful signals

Use real PostgreSQL tests with two accounts, reassignment/deletion and concurrent
writes. Exercise native Workboard approval/run integration and browser journeys
crossing World and the existing board. Qualify lifecycle cleanup with late tasks
and missing source references.

Measure resumed projects that lead to a real next action and completed outcomes
with evidence. Distinguish suggested, started, waiting, verified and abandoned
work; do not treat plan generation as accomplishment.
