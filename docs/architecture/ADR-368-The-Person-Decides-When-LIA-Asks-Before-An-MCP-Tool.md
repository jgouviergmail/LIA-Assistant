# ADR-368 — The person decides when LIA asks before an MCP tool: account, server, tool — and a dedicated agent is asked before its task

**Status**: Accepted, 2026-10-31.
**Date**: 2026-10-31

**Amends**:
[ADR-263](ADR-263-Execution-Authority-Chain-And-Effect-Register.md) (the person's explicit
« never ask » for one tool is an approval given in advance, filed `standing_choice`; a
dedicated agent's task is asked when one of its tools would — amendment 2026-10-31),
[ADR-062](ADR-062-Agent-Initiative-Phase.md) (the iterative
sub-agent's task question), [ADR-255](ADR-255-MCP-Tool-Declaration-Conformance.md)
(a server's declaration may be loosened by the PERSON alone, for one tool, bound to that
declaration), [ADR-322](ADR-322-One-Clock-Per-Routine.md) (unattended, a dedicated agent's
whole task needs the routine's pre-approval),
[ADR-289](ADR-289-Draft-Surfaces-Drawn-From-One-Description.md) (a confirmed tool call is no
longer answered by its card alone: its step reports what it returned).

Spec: `docs/superpowers/specs/2026-10-30-mcp-confirmation-strategy-design.md` (with its
owner decision of 2026-10-31).

## Context

Measured on 2026-10-30 before anything changed:

- Nobody could see or set a personal server's confirmation: `user_mcp_servers.hitl_required`
  had no field in the form and the chat refused it; « inherit » meant the INSTANCE
  (`MCP_HITL_REQUIRED`), never the account.
- What LIA asked followed the server's declarations alone (`derive_mcp_mutation_policy`), and
  the person could not predict it per mode: the flows were proven on real turns on the proof
  account (spec lot 0, H1–H5, H8): tools used directly are asked in the ReAct loop, which
  continues, and as a card after a Pipeline task, which the plan resumes from; a dedicated
  agent ended the turn on the card when its server followed its declarations, and after the
  person's yes only that act ran — **the rest of the task was lost** (H1 Pipeline, H3 ReAct).
- The owner's rule (2026-10-31): *whatever the mode and the level, a task runs to completion
  once the person validated an action that needed it.*

## Decision

**1. Four levels, one resolution** (`infrastructure/mcp/confirmation.py`): the TOOL's own
choice (always / never), then the SERVER's (always / follow its declarations / like my
strategy), then the ACCOUNT's strategy (`users.mcp_hitl_required`; NULL follows the instance),
then the instance (`MCP_HITL_REQUIRED`, also the rule of the administrator's servers). Reads
are forgiving (an unreadable value falls through to the level below); writes are strict.

**2. Who drives a server is ONE choice** — LIA uses its tools directly; a dedicated agent in
Pipeline, the tools directly in ReAct; a dedicated agent in both modes — stored as
`iterative_mode` plus a nullable ReAct shape (`user_mcp_servers.react_expand_iterative`, NULL
follows `REACT_MCP_EXPAND_ITERATIVE_ENABLED`), resolved once by the task manifest's builder;
the ReAct selector reads the manifest.

**3. A tool's choice is one row** (`user_mcp_tool_choices`, unique per server and tool name,
an upsert per tool). *Always* applies whatever the tool declares. *Never* is bound to the
declaration it was chosen against (`declaration_fingerprint`: annotations and input schema,
never the description); when the server changes that declaration the choice is SUSPENDED,
the levels below decide, and the synthesis and the server's card say so. A *never* sets
`approved_in_advance` on the manifest: `requires_confirmation` answers false and the effect
gate files the approval as `standing_choice` at its one point (`effects/preapproval.py`).
Only the page's service writes a choice — an install, a share or a plugin never copies one
(AST guard).

**4. A dedicated agent is asked once before each task it is given, whenever one of its tools
would ask** (owner decision 2026-10-31) — in Pipeline and in ReAct, with « always ask » and
with « follow its declarations ». ONE predicate decides it,
`registry/confirmation_rule.task_requires_confirmation`, over the manifests of the agent's own
tools: read by the personal registration, the administrator's and the synthesis. That answer
covers the agent's calls (the task's approved scope reaches every inner call) and the task
runs to completion. A tool on « never ask » does not make the task ask; one on « always »
does. Unattended, a routine is refused the whole task unless its form pre-approved the server.
The sub-loop's « confirmations kept for the end of the task » (ADR-263, 2026-10-30 (b) §4) can
no longer be reached through registration; it stays as the safety net of a task run
unapproved, so no confirmation is ever lost.

**5. The synthesis is computed, never written** (`domains/user_mcp/behavior.py`): it builds
each tool's manifest with the run's own builder and reads the run's own predicates. Per mode:
who drives, and how a question comes (asked in the loop; a card after the task; once before
the task). Per tool: whether LIA asks — the same in both modes now; only WHEN differs — and
why, from a closed vocabulary of reasons, plus a suspended choice. Unattended: what a routine
is refused. The same computation answers « what would LIA stop asking about? » for any
candidate change (`questions_lost`, one entry per tool) — it drives the page's alert and the
assistant's rule.

**6. The page decides; nothing is locked.** The account's strategy, a server's confirmation
and driver, and each tool's choice (in « What it will do » and in the server's form, saved
with it) are the person's. Before any change that would make LIA ask less, the page lists
what it would no longer ask about and says the person stays responsible; the change applies
once confirmed (owner decision 2026-10-30). « Never ask » is drawn in the warning colour.
« Not asked » means LIA runs the tool as if the person had said yes; the act is still
recorded in the actions register.

**7. From the chat, LIA asks more, never less.** The account's strategy travels in the
preferences patch « true » alone (published `const`, applied without a card — it only asks
more); a server's confirmation (« true » alone), the tools to always ask about and who drives
it travel on the personal-server settings card. Each is judged by the synthesis at proposal
and again at the write, against the state the write replaces; any other value, or a change
that would make LIA ask less, is refused (`CONFIRMATION_LOOSENING`) with a sentence naming
Settings › MCP Servers. Reason: an instruction injected into content the assistant reads must
never switch a confirmation off. The private browser form, whose values the person types,
offers no confirmation field.

**8. Asking is not doing.** No choice touches a tool's category, its initiative eligibility
or the invalid-mutation safety net: they keep reading the declaration and the name.

**9. The instance settings are defaults**: `MCP_HITL_REQUIRED` for the accounts that never
chose and the administrator's servers, `REACT_MCP_EXPAND_ITERATIVE_ENABLED` for the servers
that never chose; `MCP_REACT_ENABLED` stays the instance's switch for dedicated agents.

**10. A confirmed tool call is answered from what it returned** (closing proof, 2026-10-31).
In Pipeline, a tool call asked before it runs — every dedicated agent's task under rule 4, a
read under « always ask » — became a draft whose card alone answered the turn: « Action
executed — Notes: task », the very content the person asked for dropped. And when a step the
plan had resumed asked in turn, the answer read its draft « awaiting your confirmation »
after the act had run (measured on dev). So a plan that asks a tool call keeps a held plan,
and every answer to a question a step of the plan asked comes back to the plan
(`nodes/plan_resume.resume_due` reads `pending`): the act runs once, its step's result
becomes the act's, the step is reported with what it returned (`held_plan.acted`), and a step
whose draft was decided is never reported from that draft again. A native draft (an e-mail,
an event) keeps its card: its account says the act whole.

## Consequences

- A routine that delegated reads to a dedicated agent whose server declares one sensitive
  tool now needs the server's pre-approval in its form (or « never » on that tool, or tools
  used directly): its task is asked before it starts, and nobody is there to answer.
- In ReAct, a dedicated agent may be given several tasks in one turn: one question each.
- In Pipeline, the answer to a confirmed tool call is written (one response call the card
  used to spare), where it was the card alone; a native draft's card is unchanged.
- The read surface the assistant uses carries the account's strategy, each server's
  confirmation and shape, and each tool's choice and suspension, so it can describe them.

## Verification

- Proof on real turns (spec lot 0, 0.124 USD): the flows H1–H5 and H8. Decoding the raw
  traces of H4 corrected a first reading: ReAct asked once per TASK, each answer covering
  its calls.
- Closing proof on real turns (0.138 USD): a dedicated agent in ReAct and in Pipeline asked
  before its task, which then ran to completion; « never ask » on the destructive tool ran it
  unasked, filed `standing_choice`, tools used directly and dedicated agent alike. It found
  rule 10's defect, replayed after the fix: « delete note n2, then show me the updated list »
  answers the deletion done with the list, « show me my notes » lists them.
  `test_plan_resume.py::TestAConfirmedToolCallIsAnsweredFromWhatItReturned` (four mutants
  killed).
- `test_behavior_matrix.py` holds the synthesis's decision against the real registration
  path and selector for 3,456 combinations of levels, shapes, choices and switches, including
  `before_task == requires_confirmation(task manifest)`.
- `test_confirmation_resolution.py`, `test_tool_confirmation.py`, `test_standing_choice_gate.py`,
  `test_confirmation_readers_guard.py`, `test_tool_choice_writers_guard.py`,
  `test_reactive_individuals.py`, `test_react_confirmation_rule.py`,
  `test_mcp_sub_loop_pending_drafts.py`, `test_assistant_confirmation.py`,
  `test_personal_mcp_tighten_only.py`, `test_account_strategy_tighten_only.py`,
  `test_behavior_web_contract.py` (the browser reads exactly what the API serves); on
  PostgreSQL `test_tool_choices.py` and `test_application_personal_mcp_settings.py`; a
  hermetic browser journey (`e2e/smoke/mcp-confirmation-strategy.spec.ts`, 1,280 and 320 px).
