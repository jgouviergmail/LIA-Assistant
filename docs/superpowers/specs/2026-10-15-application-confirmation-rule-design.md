# One confirmation rule per application operation: design

**Status:** Approved design (owner, 2026-10-15, sections 1 to 3), amended the same
day after an adversarial self-review, a reading of the 60 own-path tools and two
measurements: the door decides and records (§4.2), conditional direct rules
(§3.1, tickets), the ADR-336 switch (§4.10), reminder modification and deletion
direct (§3.5), the register label by operation (§4.6). Refined while writing the
plan (owner approval of the spec, 2026-10-15): an always-asking operation stays
on the gate's path, a replayed direct act is served from its record, a ticket
update that answers asks, manifests keep their literals under an equality test,
and the wording a flip touches (§3.4, §4.2, §4.4, §4.6). No decision open; not
implemented.
**Date:** 2026-10-15.
**Execution:** Inline source inspection and read-only measurement on the Docker dev stack; no provider call, no production access.
**Amends (once implemented):** [ADR-339](../../architecture/ADR-339-Application-Commands-With-Current-Authority-And-Secure-Continuations.md) (requirement F03 of the [application tools design](2026-10-06-lia-application-tools-design.md)), [ADR-263](../../architecture/ADR-263-Execution-Authority-Chain-And-Effect-Register.md), [ADR-268](../../architecture/ADR-268-Generic-Recurrence-And-Reminder-Management.md), [ADR-276](../../architecture/ADR-276-Workboard.md), [ADR-336](../../architecture/ADR-336-Requested-Outcomes-Checked-Against-Canonical-Observations.md).

## 1. Context and evidence

### 1.1 The defect that started this

On the dev stack, 2026-10-15 06:06:53 UTC (run `a7b033b2`), the request
« rappelle moi de chanter dans une minute » produced, in order:

1. The router detected the `reminder` domain; the ReAct selector bound the
   native `create_reminder_tool` and dropped the four `*_lia_reminder_tool`
   settings tools by relevance. The settings tools were not chosen.
2. First call: `trigger_datetime` plus `repeat='once'`. The tool refused it as
   two ways of saying when, with a message naming `relative_trigger`, which the
   call did not use (`tools/reminder_tools.py:290-296`,
   `core/i18n_api_messages.py:2651`).
3. Second call: `08:07:00` local, refused at `08:07:02` as « A new reminder
   requires a future first occurrence » (`application/reminder_creation.py:43`),
   relayed as the opaque « Invalid reminder configuration. ».
4. Third call: `08:08:00`, which built an `APPLICATION_ACTION` draft stamped
   `create_lia_reminder_tool` (`tools/application_reminder_tools.py:163-173`).
   The card was the generic settings card: ⚙️ « Modifier les réglages de
   l'application », a formal note about LLM tokens and quotas, the parameters
   as raw JSON with a UTC instant, an expiry. It left 56 seconds to confirm a
   one-minute reminder. Confirmed, it answered « ✅ Réglages de l'application
   enregistrés ».

Before 2026-10-11 the same request was answered in one step: on 2026-07-09,
« Rappelle-moi demain à 10h de vérifier le déploiement » → « C'est noté. Un
rappel est programmé pour demain, vendredi 10 juillet, à 10h00… », no card.

### 1.2 Root cause

Commit `499c4cecc` (2026-10-11, application tools programme) rewired the
native `create_reminder_tool` from a direct write (`mutation_policy="reversible"`)
to `reminder_creation_proposal`, the settings tool's draft builder, and declared
it `draft`. That reversed an owner decision recorded in ADR-268 (« It is now
`reversible` (owner decision): the write happens without asking ») without
amending it; `CLAUDE.md` still states the tool is `reversible`. The same commit
made four other formerly direct acts ask: switching a routine on or off, and
creating, editing and commenting a workboard ticket (all `reversible` before).

There was no flag to remove: `hitl_required` is already `False`
(`registry/catalogue.py:237`). A confirmation is asked because the tool's code
returns a draft marked `requires_confirmation: True` (`drafts/service.py:183-196`).

### 1.3 What the application programme already has

A field-level criterion exists: `CONFIRMATION_FREE_FIELDS`
(`application/confirmation_policy.py:9`), filled for 8 preference operations,
read by the shared preparation door `prepare_native_tool`
(`application/native_tool_preparation.py:54`), which then executes directly
through `execute_reversible_change` (`application/reversible_execution.py`).

Measured in `lia-api-dev` on 2026-10-15 over `APPLICATION_OPERATIONS`
(184 operations: 56 read, 109 action, 17 device, 2 secure handoff):

| Path of the 128 non-read operations | Count |
|---|---|
| Through the shared door, which reads the criterion | 68 |
| Building their own draft (always ask, whatever is declared) | 60 |

Counted by following the functions each tool actually calls, by identity (a
first count by name read 62/66: the peer tools reach the door through the alias
`prepare_peer_tool`, `application/peer_tool_preparation.py`).

Three further gaps:

- The direct path answers « Application settings saved. », a settings wording,
  not the act's own result.
- For the 8 field-level operations the decision is computed twice on two
  inputs: the effect gate on the raw call arguments (`policy_for_call`,
  `confirmation_policy.py:86-98`) and the door on the prepared intent. They
  agree today by construction, nothing guarantees it, and a disagreement would
  either run an act no register row records or record an act that never ran.
- The planner is told whether the user will be asked from the manifest's static
  policy (`requires_user_approval`, read at `registry/agent_registry.py:761`):
  it is told today that `create_reminder_tool` asks.

## 2. Goals and non-goals

**Goals**

1. One declaration per application operation decides whether the confirmation
   card is shown — the counterpart of `mutation_policy` for classic tools.
2. Every application action builds its effect through one door that reads it.
3. The effect register, the planner, the outcome evidence (ADR-336), the
   capability switch and the register labels read the same declaration through
   one resolver.
4. Seven operations become direct: `reminder.create`, `reminder.update`,
   `reminder.delete`, `routine_state.update`, `workboard_ticket.create`,
   `workboard_ticket.update` (unless it launches a run) and
   `workboard_ticket.comment` (unless it answers a pending action).
5. The reminder path is robust to the two failures of §1.1.
6. The ADR-336 requested-outcome check can be switched off from the `.env`
   files, and ships off, until its own programme repairs it (§4.10).
7. No other behavior changes, except the three visible changes listed in §4.9.

**Non-goals**

- The generic card title « Modifier les réglages de l'application » on the
  operations that keep asking. (The reminder cards that showed raw JSON with a
  UTC instant no longer appear: the three reminder operations become direct.)
- `user_timezone` and `locale` being exposed to the model and overriding the
  account's value on about 25 tools (`tools/decorators.py:410`).
- Classic tools: they keep `mutation_policy` as their criterion.

## 3. The contract

### 3.1 The declaration

`ApplicationOperationSpec` (`application/operation_spec.py`) gains one
`confirmation: Confirmation = ALWAYS_ASK` — a frozen value holding the three
parts below, so that a declaration is one argument even where specs are built
in a loop — plus `aliases` and `binds_origin`:

| Part | Meaning |
|---|---|
| `rule: ConfirmationRule = ASK` | `ASK`: every call shows the confirmation card (today's behavior). `DIRECT`: executes at once and is recorded as a reversible act, unless `ask_when` says otherwise for this call. |
| `reason: str \| None` | Required for `DIRECT`, like `mutation_policy_reason`; says why acting without asking is acceptable. |
| `ask_when: AskWhen \| None` | `DIRECT` only: a named, pure predicate over the PREPARED intent that sends this call to the confirmation card instead, with its own written reason. |
| `aliases: tuple[str, ...]` (on the spec) | Native tools that serve this operation through the same door (`create_reminder_tool` → `reminder.create`, `cancel_reminder_tool` → `reminder.delete`, `toggle_scheduled_action_tool` → `routine_state.update`). |
| `binds_origin: bool = False` (on the spec) | The command is bound to the originating browser although the operation is neither a device nor a secure one (§4.1). |

The former field-level rule is one `ask_when`: « a field outside the free list
changes, or a sensitive field is enabled ». `CONFIRMATION_FREE_FIELDS` and
`SENSITIVE_ENABLE_FIELDS` become that predicate's arguments on their 8
operations and disappear as separate tables. Because the predicate reads the
prepared intent, never the raw call, it can see what only the source knows —
whether a comment answers a pending action — which a rule on the call arguments
could not.

### 3.2 Rules checked at construction and at boot

- `DIRECT` is allowed for `OperationKind.ACTION` only: the 19 device and secure
  handoff operations need the person's device or a secure form. Never on an
  administrative operation: the direct path refuses one today
  (`reversible_execution.py:28`).
- `DIRECT` requires a non-empty `confirmation_reason`; an `ask_when` requires its
  own reason and is allowed with `DIRECT` only.
- An alias names a registered tool and belongs to one operation only.

### 3.3 One decision function

`requires_confirmation(spec, intent)` is the only reader of the declaration:
`ASK` → true; `DIRECT` → `ask_when(intent)` when declared, false otherwise.

### 3.4 Semantics that follow

- A `DIRECT` operation also runs where nobody can answer — a routine, a ticket
  LIA works on — exactly like a classic `reversible` tool; an `ASK` operation is
  refused there, as today.
- Changing an operation's behavior is one declaration on its spec, plus the
  words the model reads about its tool — the manifest description, the tool's
  docstring, the progress label — by the ADR's checklist. A test fails a tool
  declared `DIRECT` without `ask_when` whose description or docstring still
  promises a confirmation.

### 3.5 Initial declarations

| Operation | Rule | Reason (summary) |
|---|---|---|
| `reminder.create` | `DIRECT` | Anodyne and undoable (owner decision, ADR-268, reaffirmed 2026-10-15). |
| `reminder.update` | `DIRECT` | Modifying a reminder is not critical (owner decision 2026-10-15). |
| `reminder.delete` | `DIRECT` | Deleting a reminder is not critical (owner decision 2026-10-15; supersedes ADR-268's « the deletion is the step that asks »). |
| `routine_state.update` | `DIRECT` | Undone by one call; owner decision 2026-10-15. |
| `workboard_ticket.create` | `DIRECT` | A ticket the person can edit or delete; owner decision 2026-10-15 (ADR-276 before 2026-10-11). |
| `workboard_ticket.update` | `DIRECT`, `ask_when`: the change requests a run (`run_now`) or answers a pending action (`answer` set on the prepared selection) | An edit is undoable; launching LIA on the ticket is autonomous, billed work; and an update that hands a « confirming » ticket back to LIA applies the owner's last note as the answer (`workboard_update.py`, `_answer_update_preview`), exactly like a comment (owner decision 2026-10-15: « direct sauf réponse/lancement »). |
| `workboard_ticket.comment` | `DIRECT`, `ask_when`: the comment answers a pending action (`answer` set on the prepared selection, `workboard/service.py` `comment_answer`) | A note is anodyne; on a « confirming » ticket the comment IS the approval or refusal of what LIA waits to do (ADR-276 lot 9), so it stays the person's click (owner decision 2026-10-15). |
| The 8 preference operations | `DIRECT`, `ask_when`: a field outside their free list changes, or a sensitive field is enabled | Their current free fields, unchanged. |
| Every other action, device and secure operation | `ASK` | Unchanged. |

## 4. The mechanism

### 4.1 One door

`prepare_native_tool` becomes the only place that decides. Each application
action tool hands it:

- its input model and its own preparation, including the resolution it performs
  today before preparing (« the next reminder », a routine toggle's desired
  state, a ticket's legacy fields);
- its own refusals, so that its current codes, messages and metadata stay
  identical (`REMINDER_BUSY`, `ALREADY_EXECUTING`, `workboard_error`…), as an
  exception-to-output mapping applied before the door's generic one.

The door then reads the declaration on the prepared intent:

- ask: the `APPLICATION_ACTION` draft plus the persisted command, with the
  origin and device binding the door already applies (`_save_native_proposal`);
- direct: immediate execution (§4.3).

What the 60 own-path tools do beyond the door, read module by module, and how
each specific is carried without changing it:

| Specific | Where | Carried by |
|---|---|---|
| A resolution before preparing | reminders (« the next one »), routine toggle (desired state), ticket creation (legacy fields), habits, open loops and channels (one helper dispatching several actions), management exports (source per operation) | The tool's preparation closure handed to the door |
| A browser origin passed to the preparation and bound to the command | session revocation (2), account export (2), health token creation, management exports (3) | A spec declaration `binds_origin`, true for device and secure kinds as today and declared for `device_session.revoke`, an action that binds its origin although it is neither |
| « Authenticated browser required. » when no origin is known | session revocation, account export, health token creation | A pre-check inside the preparation, refused with its current code (`FORBIDDEN`) |
| Domain exceptions with their own codes | `LiveConnectorSettingsRefused` (its code), `NotificationDeviceUnavailable`, `ConnectorPreferenceStateUnavailable`, `ConnectorIdentityUnavailable`, `SessionListingLimitError`, a `BaseAPIException` read as `PREPARATION_REFUSED`, `ResourceConflictError` read as `CONFLICT`, `STALE_STATE`, `REMINDER_BUSY` or `ALREADY_EXECUTING` | The tool's refusal table |
| `ValidationError`/`ValueError` read as `INVALID_INPUT` before preparation and, for most tools, `INVALID_RESPONSE_FORMAT` after it, each with its own sentence | every tool | The refusal table, split by stage |
| Device binding | own-path device operations | Unchanged: every one declares `addressed_device=False` (measured), which is what the door passes |

### 4.2 One decision per call, and the registers as they are

An `ASK` operation's decision is static — every call asks — so the gate keeps
it exactly as today: its manifest says `draft`, the gate files the consultation
row and refuses the call before the tool runs where nobody can answer it, and
the door only builds the card and the command. A `DIRECT` operation, with or
without `ask_when`, is decided by its door alone, on the exact prepared
content — never a second time on the raw call arguments:

- **The effect gate hands a `DIRECT` operation's tool, and each alias of it, to
  the door**: it resolves the tool to its operation (§4.5), keeps the activity
  observation around the call, and claims nothing. Application READ tools and
  `ASK` operations keep the gate's path untouched — which also keeps the tools
  not yet migrated recording exactly as today during the migration.
- **What the door records**: an action row for a direct act; for a call it
  sends to the card, the consultation row the gate's pass-through files today;
  for a call that stops before the decision — invalid input, an access or
  preparation refusal — a failed consultation row, never an action row, since
  no act was attempted.
- **A replay is served before anything is prepared.** LangGraph replays a
  node's tool calls after an interrupt under the same idempotency key (a ReAct
  `tool_call_id`, a pipeline step key), and a preparation re-reads a state the
  first execution already changed: a replayed deletion would answer « not
  found ». So the door first re-checks current authority (the guard that keeps
  a replay from bypassing a switched-off capability, `authorize_reversible_replay`
  today), then reads the register by the call's key and serves what an earlier
  attempt recorded, exactly as the gate serves a lost claim
  (`_serve_lost_claim`); only then does it prepare.
- **Asking.** When `ask_when` fires, the door refuses the call where nobody can
  answer it with the gate's own verdict and refusal (`decide_effect` on
  `draft`, carrier rule and unattended stand-in included — one implementation
  each), decided before the card and the command are written; otherwise it
  builds them as today. The confirmed draft is claimed later by its executor's
  gate, unchanged.
- **Direct.** The door claims the act, executes it and closes the row from the
  explicit outcome, through the gate's own claim → perform → close path,
  extracted from its LEDGER branch into one function both use (lost claims
  served from the record, abandonment on cancellation, unrecorded fallback,
  counters). A tool claiming an act its gate does not see already exists for
  the network sandbox runs (`effects/in_turn_effects.py`, ADR-298); this is the
  same shape with the full replay semantics. The gate keeps its ledger
  primitives in `effects/runtime.py` — about thirty test modules replace
  `_LEDGER` there — and the door-facing composition gets a module of its own
  (`effects/application_effects.py`): `runtime.py` already counts 555 of its
  600 logical lines.

This removes the field-level double decision of §1.3 by construction: there is
no gate decision left to disagree with, and `policy_for_call` with its raw-call
reading (`_call_intent`, the font-size special case) disappears.

### 4.3 Direct execution

`execute_reversible_change` is renamed for what it now does (direct execution of
an application operation) and keeps its body: current authority and capability
switches re-read, the operation's own executor — the same code a confirmed draft
runs — under a write receipt, then the screen refresh hint
(`publish_preference_change`). Its output:

- neutral technical messages instead of the settings wordings (« Application
  settings saved. », « Application setting change did not complete… »,
  « Application setting access refused. »), which now also speak for a
  reminder or a ticket;
- `application_result` (the outcome, as today);
- the operation's own result projection (`public_application_values`,
  `application/result_projection.py`), which already exists for every
  operation; for a reminder it gains the local readable time and, for a series,
  the schedule in words, so the answer never has to convert a UTC instant;
- `setting_choices` when the operation carries setting fields, as today.

### 4.4 Manifest policy implied by the declaration

The policy a manifest must carry follows from its operation's declaration:
`ASK`, and `DIRECT` with an `ask_when`, → `draft` (the planner is told « may
ask », the conservative answer); `DIRECT` without `ask_when` → `reversible`.
Every static reader reads it — the planner through `requires_user_approval`,
the label completeness assertion, the activity classification, the gate for an
`ASK` operation. The manifests keep their literal policy: the 131 of them are
spread over some sixty modules, several specs are declared in the registry
module itself, and a helper import in each would risk import cycles for no
behavior gain. Instead a test asserts, for every application tool and alias,
that the manifest's policy equals the one its declaration implies, and a
`reversible` manifest reads its `mutation_policy_reason` from its declaration
(`SPEC.confirmation.reason`), so the reason is written once. A declaration
flipped without its manifest fails the build.

### 4.5 One resolver from tool to operation

One function resolves a tool name — the operation's own tool or one of its
aliases — to its spec: `OperationRegistry.get_by_tool_name`, which indexes the
declared aliases at registration (refusing an alias that is another
operation's tool or already taken). It is read by:

- the effect gate (`effects/runtime.py`), to hand a `DIRECT` operation's tool
  to its door (§4.2);
- the outcome evidence (`services/outcome_evidence.py`, `_pending_confirmation`,
  `:167`), which already calls it and so resolves an alias with no change of
  its own. Moot for the three aliases — their operations become `DIRECT`
  without `ask_when`, their manifests `reversible`, never pending (`:165`) —
  but true by construction for a later alias of an operation that may ask;
- the register label (§4.6).

The `APPLICATION_TOOLS` capability (`feature_switches/registry.py:157-162`)
keeps reading its tool list from the plain tuples of `core/application_tools.py`:
`feature_switches` imports `agents` only under `TYPE_CHECKING`
(`feature_switches/registry.py:41-54`) because `agents` imports
`feature_switches`, so deriving the list from the operations would close an
import cycle. Instead, a test asserts that the tuples equal the operations' tools
plus their declared aliases plus an explicit list, each entry with its reason, of
the capability members that serve no operation (`create_scheduled_action_tool`,
which builds its own routine draft; `import_user_skill`; the ticket and list
readers) — the shape of the identity test that already exists for the names
(`test_application_registry_capability_and_manifest_share_tool_identity`).

### 4.6 Register label of an application act

The register names the act, whichever of its tools performed it and whether it
was confirmed or direct. An application act is labelled by its OPERATION, from
its prepared content (`ApplicationActionDraftContent.intent`), the way a
confirmed one already is (`draft:application_action`, `_application_label`,
`effects/labels.py:205`), and never from the raw call, which for a change or a
deletion carries a reference (« the next one ») rather than the object:

- the seven operations of goal 4 declare, in a table of their own beside the
  label builders (`APPLICATION_LABELS` in `effects/labels.py`, keyed by
  operation: `EFFECT_LABEL_BUILDERS` is keyed by capability, and its tests
  require every key to produce a wording of its own), the field of their
  prepared content that names their object
  (the reminder's content, the routine's name, the ticket's title) and the
  wording the register already uses for that act: « Rappel « … » créé »
  (`create_reminder_tool`), « Rappel « … » supprimé » (`draft.reminder_delete`),
  « Action planifiée « … » activée ou suspendue »
  (`toggle_scheduled_action_tool`) and the three ticket wordings
  (`create_ticket_tool`, `update_ticket_tool`, `comment_ticket_tool`); a modified
  reminder gets one new wording, in the six languages of both catalogues
  (`core/i18n_effects.py`, the web locales);
- every other operation keeps the label its confirmed acts carry today
  (« Action dans l'application : … »), which copies nothing from the content on
  purpose: an arbitrary operation's content may hold what a register line must
  not. Only a declared field reaches a label.

The two ticket operations that may still ask therefore name their object
whether the person confirmed them or not. The label completeness assertion
(`assert_effect_label_completeness`, which refuses to boot on an acting tool
without a label — ADR-268 met it when `create_reminder_tool` became
`reversible`) reads an application tool or alias through its operation, so
flipping a declaration needs no second entry. Rows already written keep their
stored label.

### 4.7 The card path stays complete for every action

Whatever its declaration, every action operation keeps its preview and its
confirmed executor; draft editing stays exactly as supported today, which is not
every operation (`application/draft_editing.py:169-232` covers part of them).
For a `DIRECT` operation this path is only exercised by tests until the
declaration flips back: it is the half of the contract that makes the flip one
line, not dead code. A completeness assertion refuses an action operation
without a preview or an executor. The ADR states this explicitly.

### 4.8 Guards

- No `APPLICATION_ACTION` draft and no persisted command are created outside the
  door (AST guard), with a shrink-only list of the modules not yet migrated,
  empty at the end of the programme.
- The gate claims no act for an application tool or alias: its door does
  (§4.2).
- Manifest policy equals the declaration's, and a `reversible` manifest's reason
  is its declaration's (§4.4).
- A tool declared `DIRECT` without `ask_when` — its own or an alias — promises
  no confirmation in its manifest description or its docstring (§3.4).
- `DIRECT` requires `OperationKind.ACTION` and a reason; an `ask_when` carries
  its own reason (§3.2).
- Every action operation has a preview and a confirmed executor (§4.7).
- Each guard is proven by a sample that must make it fail.

### 4.9 Visible changes outside the seven direct operations

1. The 8 preference operations, when they run directly, are labelled in the
   register by their operation (« Action dans l'application : … ») instead of
   the generic tool label.
2. The technical messages the model reads on the direct path are neutral
   instead of the settings wordings (§4.3); `setting_choices` is unchanged.
3. When the preparation of one of those 8 operations refuses (an invalid value,
   a withdrawn access), the register files a failed consultation instead of a
   failed action: the gate used to claim before the tool ran, the door decides
   after preparing, and no act was attempted (§4.2).

Nothing else changes for the 121 operations that keep their declaration: same
card, same codes, same messages, proven by characterization tests (§6.2).

### 4.10 The ADR-336 requested-outcome check: switched off, repaired later

A direct act is judged by the requested-outcome check of ADR-336 whenever the
query analyzer extracted a requirement for it. Two verdicts can then contradict
a successful creation:

- **`unknown`** when the requirement carries no literal field: an action is only
  proven with at least one checked field (`services/outcome_evidence.py:248`,
  `_action_proven` at `:265-271`), and the response directive tells the model
  not to turn `unknown` into success;
- **`missing`** when a literal field differs only by case — the requirement
  quotes « chanter », the reminder's content is « Chanter »: the comparison is
  exact string equality (`services/outcome_evidence.py:212`). In ReAct a gap
  discards the final answer and starts a recovery pass
  (`nodes/react_observed_gaps.py`, `proven_final_content` and `observed_gaps`),
  and the response is told to state the missing result plainly: LIA would say
  the reminder was not created when it was.

This is already true of every direct tool (mailbox drafts, an e-mail to
oneself…); making reminder creation direct exposes it. On the turn of §1.1 the
analyzer extracted no requirement at all (read from the turn's checkpoint), so
the check did not apply.

**Measured on 2026-10-15** (dev, Anthropic excluded; dev and production both run
`claude-haiku-5-5` on these slots, which this measurement therefore does not
cover):

- *Analysis stage, 232 analyses* (semantic pivot + analyzer + both anchorings,
  3 models × 24 requests × 3 passes, plus 16 without the pivot; 0.49 USD).
  With the deployed pivot, **no requirement survives for a non-English request**
  (0 of 117 reminder analyses; 4 of 27 other acts, where a quoted title came
  through the translation verbatim): the analyzer sees the English pivot and
  quotes it, then the second anchoring compares that quote with the ORIGINAL
  message (`services/query_analyzer_service.py:1332`). In English, 31 of 72
  analyses carry a checked requirement, model-dependent (16/24, 15/24, 0/24 —
  the third model always invents a `min_count`, which the anchoring refuses).
  Field names are mostly invented (`title`, `reminder_text`, `instruction`…).
- *Real English turns, proof account* (24 turns, 0.09 EUR): reminder creation
  made direct in the measuring process drew no requirement and answered
  naturally (3/3). Every direct settings change drew a requirement judged
  `unknown` — even `font_size = 18` exact, because an application result nests
  its values under `application_result.values` where the check never looks —
  and one answer in four said the change had failed while the register shows it
  `succeeded`. A read asking for « the next 2 » of an empty list was judged
  `missing` and paid a recovery pass for nothing.

**Owner decision 2026-10-15**: the check gets an operator switch in the `.env`
files and ships OFF, so that no end user meets these false negatives; a `TODO`
at the switch and at its gate states the measured defects and points to the
dedicated programme, which follows this one. The switch turns off the CHECK,
not the extraction: the requirements still reach the pipeline planner, which
reads them as a planning hint (`services/planner/human_message.py:77-79`) and
judges nothing. One predicate reads the switch at the two places the verdict is
formed: `build_requested_outcomes_block` (the response directive, pipeline and
ReAct) and `requested_requirements` (`nodes/react_observed_gaps.py`, which also
feeds the ReAct evidence collection, the gaps, the recovery trigger and the
final report). Off, a turn behaves as one whose analyzer extracted nothing —
the measured state of every non-English turn today — including on a checkpoint
written while it was on.

## 5. Reminder specifics

- **A single instant at most one minute in the past is accepted** and fires at
  the next pass of the reminder sweep, which runs every minute
  (`startup/schedulers.py:233-247`), like any due reminder. One minute is the
  precision of the clock the model writes (`HH:MM`), so « dans une minute »
  rounded down can land a few seconds behind. The rule applies to a
  creation and to a modification that moves a reminder
  (`application/reminder_update.py`, the `changes_schedule` check), at
  preparation and at execution; under an `ASK` declaration, a confirmation that
  arrives more than one minute after the approved instant therefore stays a
  `STALE_STATE` refusal, as today. An older instant is refused at preparation
  with an actionable message carrying the current local time, never the opaque
  « Invalid reminder configuration. ». The constant lives in `core/constants.py`
  with this reason; it is structural, not tunable.
- **`repeat='once'` with `trigger_datetime` is the same single firing.** When no
  other schedule field is set and `repeat_every` is 1, the redundant `repeat` is
  dropped before validation (a mechanical repair). Any other combination stays a
  conflict.
- **The conflict and missing messages name the three ways** (`trigger_datetime`,
  `repeat` and its schedule fields, `relative_trigger`), in the six languages.
- **The result** of a creation or a modification carries the reminder's content,
  its local readable time and, for a series, its schedule in words; a deletion
  names what it deleted (§4.3).
- **A deletion from a dashboard card keeps its card scope.** The preparation
  captures the card selection and the execution runs under it
  (`application/reminder_card_selection.py`); executed in the same call, the
  selection is the one just captured.
- **« Delete all my reminders » deletes them one by one without asking** in the
  ReAct loop, which has no bulk confirmation. The pipeline keeps its FOR_EACH
  confirmation above its threshold — decided by the tool's catalogue category
  (`orchestration/plan_predicates.py:116`, `tool_is_mutation`, read by
  `services/hitl/scope_detector.py:384-401`), never by the declaration — and no
  longer shows the grouped card of drafts that followed it
  (`nodes/hitl_dispatch_node.py:648-653`). Accepted by the owner (« ce n'est pas
  critique »); stated in the ADR so it is not rediscovered.
- **A routine toggle states its target.** Direct again, the native
  `toggle_scheduled_action_tool` inverts the current state on every call, so a
  model that calls it twice inverts it twice — as before 2026-10-11, and
  contrary to scenario T11 of the application tools design (« same desired state
  is a truthful no-op »). The alias accepts the target state (pause or resume);
  with a target, a repeated call is a no-op; without one, it toggles as before.
- **Four progress labels become neutral** in the six locales:
  `create_lia_reminder`, `update_lia_reminder`, `delete_lia_reminder` (« Preparing
  reminder creation / changes / deletion… ») and `set_lia_routine_state`
  (« Preparing the routine state change… »). The other direct tools and aliases
  already have neutral labels (`create_reminder`: « Creating reminder… »,
  `cancel_reminder`: « Cancelling reminder… », `toggle_scheduled_action`,
  `create_ticket`, `update_ticket`, `comment_ticket`).

## 6. Delivery

### 6.1 Lots

Every lot: characterization tests first, then the migration, then the lot's
tests and gates, then an exhaustive cold review of every file of the lot.

The implementation plan is written in two parts: lots A, 0, 1 and 2 first —
they carry every visible change and the whole mechanism —, then lots 3 to 6
and the closing, written once the door has shipped, so that 51 migrations are
transcribed against the door's real interface rather than a planned one.

| Lot | Content | Visible effect |
|---|---|---|
| A — ADR-336 switch | `REQUESTED_OUTCOMES_CHECK_ENABLED` (default off) in settings and in the files that carry its ADR-310 neighbour `REACT_RECOVERY_PASSES_MAX`: `.env.example`, `.env.prod.example`, the four demonstrator files (two templates, two live) and the live `.env` and `.env.prod` (their `*.encrypted` copies are re-encrypted by `deploy-prod.ps1`, never by hand; the minimal file lists only what boot requires), one predicate read where the verdict is formed (§4.10), the planner hint untouched, the `TODO` with the measured defects, an ADR-336 amendment. Independent of the rest, shipped first. | English turns no longer meet the check's false negatives |
| 0 — Contract and door | Declaration with `ask_when` and its checks; the 8 field lists turned into their predicate; manifest policy equality test; resolver read by gate, outcome evidence, capability and labels; the gate handing `DIRECT` operations to their door; door with own preparation, own refusals, `binds_origin`, the replay served from the record, the draft verdict where nobody can answer and the claim → perform → close path shared with the gate; direct execution renamed with its neutral output; the label by operation (§4.6) and the completeness assertion reading application tools and aliases through it; AST guard with its shrink-only list of the tool modules not yet migrated (the 60 operations of §1.3). | §4.9 only |
| 1 — Reminders and routines | 8 operations (`reminder.create`, `.update`, `.delete`; `routine.create`, `.update`, `.delete`, `.execute`; `routine_state.update`) and 3 aliases (`create_reminder_tool`, `cancel_reminder_tool`, `toggle_scheduled_action_tool`) through the door; then the three reminder operations and `routine_state.update` → `DIRECT`, with their register labels (one new wording, for a modified reminder); §5. | The defect of §1.1 is fixed; modifying and deleting a reminder no longer ask |
| 2 — Tickets | `workboard_ticket.create` through the door; then create → `DIRECT`, update → `DIRECT` asking when it requests a run, comment → `DIRECT` asking when it answers a pending action; their register labels. | As before 2026-10-11, minus the two unattended approvals |
| 3 — Memories, interests, journals | 19 operations, migration only. | None |
| 4 — Peer settings, relations | 6 operations (`peer_preferences.update` and the 5 relation operations; the 6 other peer operations already use the door), migration only. | None |
| 5 — Sessions, connectors, channels, phone, live, notifications, location, shared MCP | 13 operations, migration only. | None |
| 6 — Habits, open loops, psyche, health, account export | 13 operations, migration only. | None |
| Closing | The guard's list is empty; full gates (`task ci:fast`). | — |

### 6.2 Tests

- Characterization, per migrated operation, before its migration: draft type
  and content, `source_tool`, persisted command, origin and device binding,
  every refusal's code, message and metadata.
- Real PostgreSQL, for the seven direct operations: one row written, capability
  switch honored, act recorded `reversible`, no draft, no command, refresh hint
  published; reminder due-instant rule at the one-minute bound.
- Outcome evidence (ADR-336, switch on): a direct act, through the operation's
  tool or an alias, is not read as pending.
- The ADR-336 switch: off, no requirement reaches the directive, the ReAct gaps,
  the recovery trigger or the evidence, including from a checkpoint written
  while it was on; the planner still receives its hint.
- The registers: an asking application tool still files its consultation row, a
  direct one its action row and no consultation; an application read is
  untouched; an unattended `ASK` call is refused before any preparation.
- The door's decision: a direct act claims exactly one register row and closes
  it from its outcome (success, failure, cancellation, replay served from the
  record); a draft where nobody can answer is refused with the gate's verdict;
  each `ask_when` sends its call to the card on its sample and not on its
  near-miss.
- The register label: each of the seven operations names its object from its
  prepared content, through its tool and each alias, confirmed and direct (the
  deletion of « the next one » reads « Rappel « chanter » supprimé », never the
  reference); any other operation keeps the label that copies nothing; the application boots with every declaration flipped to `DIRECT`
  (the completeness assertion).
- Guards, each with its failing sample.
- Gates per lot: `task test:backend:unit:fast`, `task test:backend:agents`, the
  integration tests of the touched families, `task lint`; closing: `task ci:fast`.

### 6.3 Runtime proof on the Docker dev stack, no spend

Restart `lia-api-dev` and check the boot completeness assertions. Call the tools
directly in the container on the proof account, without any model call: the
seven direct operations write and record; a sample of asking operations still
returns its card. The real conversational test is left to the owner.

### 6.4 Documentation

- A new ADR (ADR-347, or the next free number when written) — one confirmation
  declaration per application operation — amending ADR-339, ADR-263, ADR-268
  and ADR-276, with the checklist to flip an operation (declaration, reason,
  `ask_when` when needed, manifest policy literal, manifest description and
  tool docstring, progress label).
- An ADR-336 amendment: the switch, why it ships off, the measurements of §4.10
  and the defects the dedicated programme must fix (anchoring against the
  original language, field paths never published to the analyzer, nested
  application values, invented counts, case-sensitive equality, the `unknown`
  directive turning into a claimed failure).
- `docs/technical/APPLICATION_COMMANDS.md`.
- Living maps in the six languages, ADR index, counts.
- One pointer line in `CLAUDE.md`, then `task docs:sync-agents`.

### 6.5 Method

Work in the `main` working tree, never committed. Several files the lots touch
already carry other lots' uncommitted changes: each is checked before editing,
and nothing else in them is touched.

## 7. Risks

| Risk | Mitigation |
|---|---|
| A migration changes a code, message or binding | Characterization tests written before each migration, kept green. |
| Gate and door decide differently | Impossible by construction: the door alone decides, and the gate passes application tools to it (§4.2). |
| The door's claim path drifts from the gate's | One extracted claim → perform → close function used by both (§4.2). |
| A direct act runs unattended | Declared with a written reason; same semantics as classic `reversible` tools. Reminder creation, the routine toggle and the three ticket acts were direct before 2026-10-11; modifying and deleting a reminder become direct by the owner's decision of 2026-10-15. |
| A declaration flipped without its manifest | §4.4: asserted equal, the reason read from the declaration; the words the model reads guarded (§3.4). |
| A replayed direct act prepared again on a state it already changed | §4.2: the record is served before anything is prepared. |
| Concurrent uncommitted lots in the same files | Checked before each edit (§6.5); stabilizing the in-flight lots of the shared `main` tree before lot 0 is safer, and is the owner's call. |
| ADR number collision with another planned lot | The number is taken when the ADR is written. |
| The 51 operations of lots 3 to 6 do not all fit the door unchanged | Every own-path tool module was read for its preparation, binding and refusal shape (§4.1 table); each migration is still preceded by characterization tests. |
| A register line copies what it must not | Only a field an operation declares reaches its label; every other operation keeps the label that copies nothing (§4.6). |
| A direct act is reported as not done (§4.10) | The ADR-336 check ships off (lot A) until its own programme repairs it. |
| A direct operation's executor keeps an approval-only check | Read for the seven: the routine toggle, the ticket and the reminder removal executors only re-check expiry, ownership and the prepared snapshot (and the card scope for a removal), which a direct call passes milliseconds after preparing; the past-instant checks of reminder creation and modification are the §5 rule. |
