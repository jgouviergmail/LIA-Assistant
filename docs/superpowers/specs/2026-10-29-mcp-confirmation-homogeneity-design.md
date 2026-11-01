# MCP confirmations — one rule, every mode

Date: 2026-10-29. Status: design, awaiting owner approval. Nothing is implemented.
The analysis, the probes and a paid measurement are done (see *Evidence*).

## Intent

Owner's words (2026-10-29): *« MCP pour React et Pipeline il serait pertinent d'avoir
un fonctionnement homogène et réutiliser ce qui fonctionne sur React pour l'appliquer
sur pipeline. »* And: *« Cela doit être simple et logique pour l'utilisateur final et
générique, élégant, robuste et fiable techniquement. »*

Today an MCP tool's confirmation depends on where it runs. The manifests already
carry the right rule — `derive_mcp_mutation_policy` (`infrastructure/mcp/registration.py`)
derives `confirm` from the server's HITL setting or a destructive declaration,
`reversible` from an additive one — but three readers ignore it, so a destructive
personal tool runs unasked in Pipeline, in a standard server under ReAct, inside an
iterative task, and nothing of it reaches the effect register.

## What the person gets

| A tool whose rule is… | Pipeline | ReAct | Routine (nobody there) | Workboard ticket |
|---|---|---|---|---|
| `confirm` | done with the rest of the task, then one card per action, after the task | asked in the loop, which continues | refused and named — unless the routine pre-approved its server | asked on the ticket |
| `reversible` | runs, recorded in « Actions menées » | same | same | same |
| no rule | unchanged | unchanged | unchanged | unchanged |

- In Pipeline the whole task runs: reads, additive actions. Each action awaiting
  approval is prepared, never performed, and presented after the task, one card at a
  time (ADR-288). Nothing is asked before a task starts.
- A plan step that needs the RESULT of an action awaiting approval waits for that
  approval; once the action is approved and performed, the plan resumes with the real
  result (« crée le ticket et envoie le lien à Paul »: ticket card → yes → ticket
  created → the e-mail card carries the real link). Refused, the waiting steps do not
  run and the answer says so. A step that merely comes after, without reading that
  result, does not wait.
- A server whose confirmation the person switched ON asks for everything, reads included
  (`hitl_required` derives `confirm` for every tool). In ReAct each call is asked. In
  Pipeline a standard server's call is a card like any `confirm` call, and D7 resumes what
  needed its result; an ITERATIVE server's task is asked once before it starts (the task
  tool's existing rule, `build_mcp_react_task_manifest`) and the approval covers that task —
  turning every read of the loop into a card after the task would leave it nothing it can
  read. No production server has it on today.
- The register shows every personal and administrator MCP action, named after its
  server (« Notes : supprimer la note »).
- A routine acts on a confirmation-requiring tool only on the servers the person ticked
  for that routine.

### Non-goals

- The e-mail-to-oneself exception for MCP tools (owner decision 2026-10-16): a later
  lot, made possible by the per-call refinement hook `_call_effect_policy` already has.
- Native tools' policies, the card designs (ADR-289), the ADR-288 presentation.
- The personal-servers settings screen.

### Anti-goals

- A question before every task of a server (measured cost: most tasks are reads).
- The model's prose taken as the record of what was done.
- A model able to grant itself an authorisation.
- A step executed on a placeholder, or reported failed because it waited.
- Anything tuned for one provider or one model.

## Evidence (2026-10-29)

**Code, executed.** Probes ran the real gate, adapters, manifest builders, ReAct
selector and Pipeline executor against a fake ledger (scratchpad, not in the repo;
they become lot 0's tests):

| | Finding |
|---|---|
| H1 | `resolve_policy` (`effects/runtime.py`) reads the global registry only: a personal manifest declaring `confirm` reads as no policy |
| H2 | Pipeline: a personal `confirm` tool reaches its server unasked, no effect row |
| H3 | Admin iterative individuals are registered WITHOUT a manifest (`admin_registration.py::_register_iterative_server`): unasked, unrecorded |
| H4 | Calls inside an iterative sub-loop share the parent's idempotency key: the second recorded action loses its claim and never runs (`repository.claim`, `ON CONFLICT DO NOTHING`) |
| H5 | The personal iterative task tool is not gated at all (a copy of an `@tool` no registry ever gated) |
| H6 | A confirmation born in a sub-loop is lost: `_MCPReActWrapper` returns it as text; the model reads « Action requise : confirme, modifie ou annule » — French, addressed to the person |
| H7 | ReAct, standard personal server, confirmation off: a declared-destructive tool is not asked (`react_tool_selector._manifest_tools` reads the server setting alone) |
| H8 | A routine refuses a `confirm` tool without asking (`decide_effect`, unattended) |
| P1 | After approval a personal iterative individual can be replayed (`_reactive_manifest`); an admin one cannot |
| Dep | A step depending on a draft step: `$steps.s1.x` → reported FAILED; `{{ steps.s1.x }}` → RUN with the literal template; `$steps.s1.result` → RUN with the person-facing French preview — true of every Pipeline draft, native ones included |

**Production, read-only.** 28 personal servers (10 enabled, all iterative, none with
HITL on, 2 accounts); 352 tools: 62 declared destructive, 33 additive, 180 declared
read-only, 77 without annotation; 7 iterative servers hold at least one destructive
tool. 30 days: 604 MCP calls from routines, none to a `confirm` tool (no routine
breaks); 486 from conversations, all ReAct; 0 effect rows for any MCP tool. One admin
server (Excalidraw, an MCP App, 2 tools): expanding admin iterative servers adds 0
tools there and on dev. Turns in 30 days: 863 ReAct, 104 Pipeline — this instance is
ReAct-heavy, Pipeline is the default elsewhere.

**Paid bench (owner budget 1 $, spent 0.37 $).** The real `mcp_react_agent` runner and
prompt over a fake notes server, task « delete the duplicates, then archive the notes
older than a year », 5 families (deepseek-flash, claude-haiku-5-5, gpt-6-luna,
gemini-3.7-flash, qwen3.6-flash) × 2 languages × 5 runs per variant:

| Final message | A (today's preview) | B (« not performed yet… ») | C (adopted line) |
|---|---|---|---|
| claims the deletion was done | 11/50 (one family 10/10) | 11/50 (same family 10/10) | 0 clean, 4/50 self-contradictory (« deleted — awaiting your approval ») |
| states it awaits approval | 37/50 | 37/50 | 49/50 |
| offers to confirm it ITSELF | 5/50 | 1/50 | 0/50 |
| quotes the internal `draft_…` id | 19/50 | 0/50 | 0/50 |
| calls it again | 2/50 | 1/50 | 0/50 |

Conclusion: the line C is the best wording, and no wording makes prose a record — the
truth must come from the code (D6).

## Design

**D1 — One manifest per MCP tool, one builder.** Every MCP tool, standard or iterative,
administrator or personal, gets its manifest from `build_mcp_tool_manifest`. An
iterative server's individuals live in a REACTIVE store, admitted only through their
offered task tool: the personal one already exists (`UserMCPToolsContext.reactive_tool_manifests`);
the administrator's is new, in a module of its own beside `agent_registry.py` (3 lines of
size margin). `request_tool_identity._reactive_manifest` admits both origins. The turn
catalogue (`build_request_tool_manifests`) is unchanged: no individual reaches the planner.

**D2 — The gate reads the turn's offered manifest when the registry does not know the
tool.** A name the global registry knows (natives, administrator standard tools, whose
configuration is fixed for the life of the process) is memoised as today. Any other name
resolves through `resolve_tool_manifest_named` — the turn's offered snapshot, personal
manifests and reactive individuals included — and is never memoised: a personal server's
setting changes, and an 8-hex name prefix is not an account boundary.

**D3 — Every MCP callable is gated.** The personal task tool is gated under its own name
before `bind_task_identity`. A completeness check refuses a `UserMCPToolsContext`
instance without the gate (the registry's boot assert does not see per-request tools).

**D4 — One key per call inside an iterative sub-loop.** The wrapper publishes a child
scope `"{parent_key}:sub:{tool_call_id}"`, inheriting the parent's approval only. The id
travels inside the call's own arguments, never in a `ContextVar`: LangChain prepares the
arguments before it copies the context, so a variable set there would outlive the call. A task
re-run happens only after a zero-tool-call answer, so it can repeat no act.

**D5 — The work is done, the confirmations wait for the end of the task.** When an inner
call returns a draft, the wrapper keeps it and returns the line C (a versioned
`key|template` lines file, ADR-284):

> Queued for the person's approval: this call was NOT performed. The person will be asked
> to approve it right after this task. Do not call it again and do not try another way to
> achieve it. Continue with the rest of the task, and in your final answer list it as
> awaiting the person's approval: neither done nor failed.

The runner returns the pending drafts; the task output publishes them
(`requires_confirmation` and the list). The Pipeline executor accepts a LIST of drafts per
step; ReAct queues all but the first in `pending_drafts_queue`. Both reach the existing
one-at-a-time sequence. MCP App servers (which keep their task tool in ReAct) follow the
same path.

**D6 — The record is the code's.** The task's message is the model's narrative followed by
a code-written statement of its acts — performed (the calls `core/tool_outcome.explicit_success`
reads as succeeded) and awaiting approval (the drafts) — introduced as authoritative over
the narrative.
After the decisions, the response reads each action's real outcome through the existing
channels (draft execution results, the performed-actions directive of ADR-263 §23).

**D7 — A step needing a pending result waits, then the plan resumes.**
- *Hold.* A step whose parameters reference — directly or through another held step — a
  step awaiting approval is held: excluded from the waves (`get_next_wave(..., excluded)`),
  never run on a placeholder, never reported failed. References are read by the graph's
  own extractor (`dependency_graph._extract_step_references`); a step merely ordered after
  (`depends_on`, sequential chaining) runs.
- *Resume.* When the sequence settles and a held step's blockers are all confirmed, the
  graph routes back to the orchestrator (the FOR_EACH precedent: `initial_completed_steps`),
  which executes the confirmed drafts through the existing executor, records their results
  in the state, injects them as their steps' results, and runs the held steps. Execution
  happens in the response node today: the response then reads the recorded results and
  executes nothing twice — the ledger key `call:{draft_id}` would serve a second execution
  as a record anyway (executed 2026-10-29: two replays, one performance). **The response
  composes**: the executed drafts' result cards AND the results of the steps run after them.
  Today it REPLACES the whole summary by the draft's result (`response_node.py:2081`), which
  after a resume would hide the very step the person waited for.
- *Refusal or failure.* A held step runs only when EVERY blocker was confirmed and its
  execution succeeded. A refused blocker, or one that failed when executed, leaves the step
  unrun; the answer says what was not done and why (a failure through the ADR-303 channel).
- *Termination.* A resumed step may raise new drafts → another sequence; every step runs at
  most once.
- New state keys are declared in `MessagesState`, reset by `draft_turn_reset()`, and
  round-trip tested.

**D8 — ReAct asks on one predicate.** `requires_confirmation(manifest)` =
`permissions.hitl_required or mutation_policy == "confirm"`, read for every MCP tool
(standard servers included). Non-App administrator iterative servers are expanded like
personal ones (`_expand_iterative_user_mcp` generalised); MCP App servers keep their task
tool and D5. Stated consequence: in ReAct a task tool that hands up drafts ends the loop at
the hand-off like any draft (ADR-298 measured it), so what the outer loop would have done
afterwards is lost — accepted for MCP App servers alone (none declares a destructive tool
in production today); every other iterative server is expanded and asked in the loop.

**D9 — A routine may pre-approve servers.** `scheduled_actions.mcp_preapproved_servers`
(JSONB list of server keys, `none_as_null`): written only by the routine form and its REST
route, strict on write (the account's personal servers, administrator servers not disabled
for it), forgiving on read. The agent's routine tools (`automation_tools`, the Studio's
`application_routine_tools`) can neither set nor widen it (guarded); their confirmation
card shows it. The run carries the set (`StreamRequest` → a `ContextVar`); the gate and
ReAct's `_approve` treat a `confirm` call of a covered server as approved
(`approval_kind="routine_preapproval"`, `approval_ref` = routine id). Off by default.

**D10 — Docs.** ADR-263 and ADR-322 amendments; `docs/knowledge/11_mcp_servers.md`
(today's state written 2026-10-29, rewritten to the target), the routines page, the FAQ
answer « readable name / confirmation » and the MCP blog article in six languages,
`docs/technical/` MCP page, CLAUDE.md at most three lines + `task docs:sync-agents`.

### My calls (the owner may override)

- Pre-approval per server, not one switch per routine (an injected instruction can only
  reach what was ticked).
- Hold on DATA reference, not on ordering.
- The wording of line C (measured best of three).
- The administrator's reactive store as a separate module (size cap), not a registry flag.

## Hypotheses still to prove — each has its test

| | Hypothesis | Proved by |
|---|---|---|
| Ha | The model's call id reaches the wrapper's `_arun` through the call's own arguments, concurrent calls included, and leaves nothing behind | **executed 2026-10-29** (design double over the real `_MCPReActWrapper`, real `BaseTool.ainvoke`, real gate): two concurrent calls → `step-1:sub:cA` / `step-1:sub:cB`, the private key never reaches the server, a following direct call carries none of theirs, an approved parent lets a `confirm` child run. Lot 1 turns it into the repository test |
| Hb | A confirmed draft the orchestrator executed is not executed again by the response | **executed 2026-10-29**: `execute_tool_call_draft` twice on one draft id → one server call, one key `call:draft_p1`, the second served the record. Refusal rows take a suffixed key (`repository.refuse`), so a refused first attempt never blocks the replay. Lot 4 adds the response-side test |
| Hc | A held step's reference resolves on the injected result (a TOOL_CALL replay returns the tool's own output) | **executed 2026-10-29** on the real `_execute_tool_step` / `_merge_single_step_result`: `$steps.s1.deleted_id` and `{{ steps.s1.deleted_id }}` both deliver `n-42` to the held step. Also executed: today's `_check_plan_completion` reads a held step as a DEADLOCK, so it must learn the held set (plan, Task 4) |
| Hd | The final answer states every awaiting / confirmed / refused action correctly, across families | lot 7: paid measure on a full turn, budget announced before |
| He | No individual reaches the planner's catalogue | lot 2: guard over `build_request_tool_manifests` |
| Hf | The routine form lists exactly the servers the routine can call | lot 5: test against the turn catalogue's rule |
| Hg | Replaying an interrupted node repeats no effect | lot 3b: two-pass replay against the ledger |

## Constraints

- Size caps: `parallel_executor.py` 2 055/2 097, `agent_registry.py` 776/779,
  `hitl_dispatch_node.py` 672/686, `effects/runtime.py` 555/600 — additions go to new
  modules; a touched frozen file shrinks where it safely can.
- No function at cyclomatic complexity ≥ 15; no new import cycle.
- Prompt text in versioned files; no inline model-facing text; model-facing text in English.
- Six languages for every user-visible string; i18n parity.
- A new metric only if a panel, rule or alert reads it.
- A cold adversarial review at the end of every lot; runtime proof on Docker dev with the
  proof account; no git action.

## Risks

| Risk | Mitigation |
|---|---|
| Resume re-runs an effect | ledger keys per call and per draft; Hg |
| Resume loops | each step runs at most once |
| A routine needing a tool now refused | none in production today; pre-approval (D9); refusal names the tool |
| A model claims an awaiting action was done | D6, measured in lot 7 |
| ReAct catalogue grows on an instance with many admin iterative servers | ADR-293 ranking and cap apply |
| Approval inherited by a whole task (pre-approved routine) | per-server scope; every act recorded with its authority |

## Amendment 2026-10-30 — measured on full turns (lot 7)

The Docker-dev proof (fake personal Notes server, only the pool's network edges replaced)
found two places where the rules above, applied as written, failed the person:

- **D7 Hold.** « supprime la note n2, puis montre-moi la liste à jour » was planned
  `list → delete → list` with the re-read ORDERED after the deletion (`depends_on`) without
  reading it. Under « a step merely ordered after runs » it ran BEFORE the act, on the old
  notes, and after « oui » the answer was the card alone. Now a step the planner explicitly
  orders after a pending act is held too, by order only: it waits for the decision, then runs
  whatever it was (it reads no placeholder), staying held only while an approved act itself
  still waits. A step READING the act keeps the rule above. Implicit sequential chaining still
  holds nothing (`held_steps.held_by_order_only`, `held_plan["ordered"]`).
- **D5 / D7 Resume — what the answer tells.** « archive la note n3 et supprime la note n2 »
  archived n3 before the card; after « oui » the answer was the deletion's card alone, after
  « non » it was « OK, c'est annulé » — the archiving was never told. Work that ran BESIDE
  the acts (neither what an act reads nor what it follows, `held_steps.told_after_the_answer`)
  now brings the decision back to the plan like a held step (`held_plan["told"]`,
  `resume_due`), and the response composes the acts' accounts with those results.

The same proof also found, outside this design: the structural FOR_EACH check reading
« read, act, read again » as an iteration (fixed: every copy must be fed by the same single
producer), the planner catalogue dropping a server's third tool under its coverage cap, and a
step unable to reference a personal MCP list by the paths its manifest publishes (both
reported, not changed here).
