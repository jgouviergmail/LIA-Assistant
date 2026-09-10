# Workboard — design (2026-09-08)

A personal ticket board — seven columns, tickets carrying a priority, dates,
one level of sub-tickets, comments — that the person, LIA or a connected peer
can be assigned to. A ticket assigned to LIA is EXECUTED by LIA out of turn,
through the same pipeline a routine uses. The chat can create, read, move and
comment tickets, and LIA reports what it did on a ticket in the chat only when
the person asked to follow that ticket.

Owner arbitration recorded 2026-09-08 (answers 1-14 to the design questions):
LIA runs a ticket at its start date or immediately when it has none; a run
ends in « en validation » or stops in « en attente retour » when it needs the
person; the run happens on the person's single conversation thread (option A);
one shared ticket row for a peer assignment (no per-board copies); sub-tickets
are child tickets on ONE level (a checklist is the fallback if that proves too
complex — the feature exists mostly so LIA can decompose complex work); four
priority levels; NO header destination (the header is full) — the board is
reached from a settings section and from every ticket notification in the
chat; the product word is « Workboard » in every language and the agent domain
is `ticket`; drag-and-drop between columns in v1, plus a listbox on the card;
LIA creates tickets from the conversation only in v1, but the model must
already carry who created a ticket so LIA can create some on its own
initiative later; a heartbeat nudge for overdue and stalled tickets; done and
cancelled tickets are never purged, hidden after 30 days by default, and a
ticket can be deleted in any state; `WORKBOARD_ENABLED` defaults to `true`;
comments are plain text, no attachments.

## 1. Problem

The person asks LIA for things that are not one conversational turn: a piece of
research to do next week, a decomposed project, something a connected peer must
handle, something to validate later. Today those live in three places that were
each built for something else — Google Tasks (a provider's to-do), reminders (a
push at an instant), routines (an instruction repeated on a schedule) — and
nothing holds « a unit of work with a lifecycle, an assignee and a result ».

## 2. What already exists (measured, not assumed)

| Piece | Where | What it gives |
|---|---|---|
| CRUD domain template | `domains/reminders/` (`router.py:32-160`) | models, repository, service, router with exact totals, settings section, agent tools |
| Program domain, flag-gated, without touching frozen files | `agents/registry/program_domain_configs.py`, `program_manifests.py:52-58`, `agents/peer/catalogue_registration.py` | a domain + agent + tools registered through the aggregators |
| Tool execution without an agent builder | `orchestration/parallel_executor.py:2724` (`tool.coroutine(**args)`) | `reminder_agent` and `peer_agent` have no `register_agent`; a manifest is enough |
| **Out-of-turn execution through the pipeline** | `infrastructure/scheduler/scheduled_action_executor.py:158-560` | `AgentService.stream_chat_response(is_automated_source=True, auto_approve_plan=True)`, quota pre-check (`:212`), HITL-pending guard, retries, FCM + SSE result |
| What that path records by construction | `agents/api/service.py:769-785` | token tracker, consultation collector, decision row — the three registers, ADR-263 |
| Chat notification out of turn | `infrastructure/proactive/notification.py:279-445` | archive-first, FCM, SSE, channels; `proactive_*` metadata |
| Chat rendering of proactive messages | `components/chat/ChatMessage.tsx:371-376`, `app/[lng]/dashboard/chat/page.tsx:273-303`, `hooks/useNotifications.ts` | tint, toast, append; prefix-routed |
| Out-of-turn ACTION claim | `agents/effects/out_of_turn_effects.py:69-93` | `proactive_notification_effect(user_id, run_id, task_type)` |
| Peer resolution by name | `agents/tools/peers_read_tools.py:68-110` | folded exact match over accepted connections |
| Two-sided tables in export and purge | `account_export/builder.py:98-105`, `users/account_deletion_service.py:85-142` | the shape a shared ticket row needs |
| Heartbeat source template | `heartbeat/context_sources.py:308-380` (`fetch_open_loops_context`), `context_aggregator.py:232,426-428`, `source_policy.py:55,74`, `schemas.py:25-38`, `proactive_task.py:690-712` | fetcher, aggregation, policy, label, post-delivery cooldown bump |
| Settings section that opens a page | `components/settings/MeetingsSettings.tsx:304`, `lib/settings-sections.ts:279-283`, `settings-section-registry.tsx:160`, `lib/settings-search.ts:334` | the door the owner chose instead of a header slot |
| Deep-link execution from a notification | `hooks/useAutoSendIntent.ts` (`?intent=`, ADR-173/210) | « finish this in the chat » from a card or a notification |
| Generic confirmation card | `agents/effects/confirmation.py` (`DraftType.TOOL_CALL`) | a `confirm` policy asks without a bespoke `DraftType` |
| Peer recipients hook | `hooks/usePeerRecipients.ts` | the assignable peers, already fetched for the composer |

Four constraints measured on the code, each of which shapes a decision below:

1. **An automated run shares the person's ONE conversation thread**
   (`conversation_orchestrator.py:114-115`, `service.py:773`), archives a
   synthetic user row (`archive_first.py`) that the frontend renders as an
   ordinary bubble (no reader of `is_automated_source` in `apps/web/src`), and
   archives the assistant answer unconditionally (`service.py:1297`).
2. **No active-run lock out of turn**: only the chat's background runner takes
   `chat:active_run` (`background_runner.py:137-212`); a routine can interleave
   with a live turn on the same thread today.
3. **An unattended run cannot confirm**: the gate refuses a `confirm` tool in
   source `scheduled` (`effects/gate.py:117-126`), and a `draft` tool raises a
   HITL interrupt the routine executor turns into a non-retryable error
   (`scheduled_action_executor.py:404`), the interrupt staying on the thread.
4. **`agents/api/service.py` is 9 logical lines under its frozen cap**
   (1 028 / 1 037, `file_size_baseline.json`): any behaviour added there is an
   extraction, never an insertion.

## 3. Decisions

| # | Decision | Why |
|---|---|---|
| D1 | A ticket run is the routine engine, EXTRACTED into a shared module (`infrastructure/scheduler/out_of_turn_run.py`) that `scheduled_action_executor.py` then calls | one implementation of « LIA runs an instruction out of turn »; the three registers, both quota ceilings and the HITL guard come by construction; the routine file shrinks (Boy Scout) |
| D2 | The run happens on the person's conversation thread (option A), under the `chat:active_run` lock; a held lock SKIPS the tick (next minute), never waits inside the sweep | consistent with routines; the lock closes the pre-existing interleaving for ticket runs; a sweep that waits is a sweep that stalls every other ticket |
| D3 | A ticket run archives BOTH its rows exactly as any turn does, flagged `hidden = true` (a boolean COLUMN, D3b) with `workboard: {ticket_id, run_id}` in their metadata, and the conversation READ path excludes hidden rows by default (`include_hidden=True` for the export and the registers). The chat learns of the run only through the follow notification; the result is ALSO a ticket COMMENT signed by LIA | the first version of this decision archived nothing — and the decision register (ADR-263, lot 6) POINTS at the request and the answer with `SET NULL` tombstones, so a run with no rows would have been indistinguishable from a deleted conversation. Archive-first (ADR-117) and the pointers stay whole; the owner's rule (no chat noise unless followed) is met at the read, not by destroying the record |
| D3b | **Hidden rows are BOUNDED and VISIBLE as a volume** (owner concern, 2026-09-08). Bound: a hidden row lives exactly as long as its ticket (deleted with it, by a partial expression index on `message_metadata->'workboard'->>'ticket_id' WHERE hidden`), a ticket runs at most `workboard_max_runs_per_ticket` times (default 10, « Run now » included), and a retention sweep deletes the hidden rows of a ticket CLOSED for more than `workboard_hidden_rows_retention_days` (default 90) — the ticket comment keeps the answer, the register keeps its dated tombstone, which is its designed answer to a purged record. Visible: `lia_hidden_run_rows` / `lia_hidden_run_bytes` gauges on the product rollup (the `lia_ledger_rows` pattern, a panel each), and the workboard settings section states « N run transcripts hidden from the chat, X KB, kept N days after closing ». `hidden` is a real boolean column (NOT NULL, server default false — a metadata-only change on PostgreSQL), never a JSONB test, so the read predicate costs the pagination index a filter and not a JSON parse per row | measured on the dev instance 2026-09-08: 2,4 KB per archived row all structures included, an automated assistant answer averaging 832 characters of content and 455 of metadata; a run is two rows, ≈ 5 KB. Worst case under the bounds: 2 000 tickets × 10 runs × 2 rows ≈ 96 MB for one account that never closes anything; a person creating five LIA tickets a day adds ≈ 50 KB a day and the retention returns it. A routine, by comparison, archives the same two rows VISIBLY every day of its life and purges nothing |
| D4 | The stamp travels through a ContextVar the runner sets around the call (`out_of_turn_origin_ctx`, the `capability_directive_ctx` pattern) and ONE metadata enricher reads it for both rows; `stream_chat_response` gains no parameter | the file has 9 logical lines of headroom; a ContextVar costs it none |
| D5 | A run that needs the person STOPS: status → `waiting`, a LIA comment says what is pending, and a chat notification carries a `?intent=` link to finish it in the chat. Two mechanisms, in this order: (1) the gate refuses a `draft` tool in an unattended source exactly as it refuses a `confirm` one (amendment to ADR-263: an unattended turn owes a draft the same answer, and today a routine reaching a draft dies on a `RuntimeError` while the interrupt stays on the thread), the refusal being COLLECTED on the runner's ContextVar so the settle reads a code, never prose; (2) a HITL interrupt that can still arise (a clarification) is the safety net: the run settles `waiting` and clears the pending interrupt from the store. Unattended runs are forced to `pipeline` mode: ReAct interrupts BEFORE its gate for every mutation | ADR-263: an unattended turn cannot obtain a confirmation; ADR-182: never announce as done what was not; the routine `requires_approval` model already does exactly this |
| D6 | Notifications on a ticket are gated by a per-SIDE follow flag (`follow_owner`, `follow_assignee`), default off, EXCEPT two events that are not progress reports: « this ticket now waits for you » (D5) and « a ticket was assigned to you » | the owner asked for no spam; a stalled ticket nobody was told about is not the absence of spam, it is work silently stopped — the same reason a routine's approval request always notifies |
| D7 | One ticket row; the assignee is (`assignee_kind` ∈ {human, lia}, `assignee_user_id` NOT NULL). Owner = (human, owner); LIA = (lia, owner); peer = (human, peer). The fourth combination the shape allows — a peer delegating to THEIR OWN LIA — is REFUSED by the service in v1 (`workboard_cross_account_delegation`, stable code) | the run executes on `assignee_user_id`'s account, quota, language and conversation. An instruction written by one account, executed unattended with another account's tools, is a cross-account injection surface: a `read` tool would put the peer's mail in a comment the owner reads. The shape stays so a later lot can open it under a consent step; the refusal is a guard, not a missing branch |
| D8 | A ticket is on U's board iff `owner_user_id = U` or `assignee_user_id = U`; a non-owner assignee needs an ACCEPTED connection, re-checked at every write (`peer_connection_id`), and a removed or blocked connection resets the assignee to the owner and notifies both sides | the peers doctrine: sharing is re-validated at execution time, never trusted from a stored row |
| D9 | Sub-tickets are child tickets, ONE level, same table (`parent_id`); a child's child is refused by the service and pinned by a test; deleting a parent cascades; closing a parent does NOT cascade | one shape for LIA to decompose work (a child is a full ticket LIA can run); a cascade on close would silently « finish » work nobody did |
| D10 | Delete is `confirm` through the generic `TOOL_CALL` card; create, update, move, comment are `reversible`. No new `DraftType` | the draft cascade (display, renderer, i18n_drafts ×6, executor) buys nothing here; ADR-263 policies already say what each tool owes |
| D11 | A ticket is referred to in the chat by id or by a UNIQUE folded title match; two candidates → a failure listing them, never a guess | ADR-269's rule on the debrief directory: a false positive hands one thing's fate to a question about another |
| D12 | The agent domain is `ticket` (singular vocabulary), the agent `workboard_agent`, and the DomainConfig description disambiguates from `task` (provider to-dos), `reminder` and `automation`. Routing quality is MEASURED on a six-language corpus before the domain ships | « crée une tâche » is ambiguous by construction; the analyzer misrouted peers 3/4 before it was given the facts (`peer_directory.py`) |
| D13 | Who created a ticket is stored (`created_by` ∈ {user, lia, peer}) and the creation tool is callable from any turn, so a proactive creation later is a NEW CALLER of an existing door, not a new door | owner answer 10 |
| D14 | Heartbeat nudge: a `WORKBOARD` source (overdue, due soon, waiting too long, cooldown per ticket) built on the open-loops template, in its own lot | owner answer 11; the shape exists end to end (fetcher, policy, label, bump) |
| D15 | The board is reached from a settings section (features tab) and from every ticket notification (link to the ticket and to the board); the notifications hub gets a « needs you » badge; no header destination | owner answer 7; the header is at seven, its measured maximum |
| D16 | Drag-and-drop with `@dnd-kit/core` + `@dnd-kit/sortable` (6.3.1 / 10.0.0, peer `react >= 16.8`, verified on the dev container 2026-09-08), pinned exactly; every card also carries a native `<select>` for its status | owner answer 9; keyboard equivalence is a correctness rule (`apps/web/CLAUDE.md`), and dnd-kit ships keyboard sensors and announcements the locale can fill |
| D17 | Counts shown on the board (per column, per filter) come from ONE aggregate over the same statement the page reads; the page carries rows only | ADR-185 |
| D18 | A ticket's run cost is read from `token_usage_logs` by `run_id` after the run and SNAPSHOTTED on the ticket (tokens, EUR); the comment carries the `run_id` | the debrief precedent; a join at render time on a register that outlives the account is the wrong direction |

## 4. Architecture

```
chat turn ──► workboard tools ──► WorkboardService ──► workboard_tickets / comments / events
                 (tool gate: effects + treatments, source user)

sweep (1 min, jittered) ──► claim (SKIP LOCKED, conditional UPDATE)
   ──► out_of_turn_run.run_instruction(user=assignee, prompt=ticket brief,
        archive_policy=NONE, lock=chat:active_run)
   ──► outcome: comment + status (validating | waiting | in_progress+error)
   ──► cost snapshot from token_usage_logs[run_id]
   ──► WorkboardNotifier (follow flags) ──► NotificationDispatcher
        under proactive_notification_effect(task_type="workboard")

peer side ──► same rows, visibility by owner OR assignee, connection re-checked

heartbeat ──► fetch_workboard_context (WORKBOARD source) ──► decision ──► bump cooldown
```

### 4.1 Backend modules

- `domains/workboard/` — `models.py`, `repository.py`, `service.py`,
  `schemas.py`, `router.py` (`/workboard`, flag-gated), `constants.py`,
  `notifications.py` (the follow-gated notifier), `brief.py` (the prompt LIA
  runs for a ticket, loaded from a versioned file), `resolution.py` (ticket
  references from the chat, D11).
- `infrastructure/scheduler/out_of_turn_run.py` — the engine extracted from
  `execute_single_action` (D1): user guards, quota pre-check, HITL-pending
  guard, optional `chat:active_run` lock, retries, timeout, the origin
  ContextVar (`out_of_turn_origin_ctx`) that stamps the archived rows.
  `scheduled_action_executor.py` keeps its condition gate, propose-first and
  run-history logic and delegates the pipeline call.
- `infrastructure/scheduler/workboard_runner.py` — the sweep: claim, run,
  settle, snapshot cost, notify. One claimed ticket at a time per worker
  (`FOR UPDATE SKIP LOCKED`), a stale-claim reaper (a claim older than the
  execution timeout is released with `run_attempts + 1`).
- `agents/workboard/catalogue_manifests.py` + `catalogue_registration.py` —
  agent manifest + six tool manifests; `agents/tools/workboard_tools.py`.
- `core/config/workboard.py` (`WorkboardSettings`), constants in
  `core/constants.py`, `.env.example` / `.env.prod.example` / `.env.min.prod`.
  Settings, every one env-overridable (`WORKBOARD_*`), defaults in
  `core/constants.py`: `workboard_enabled` (true), `workboard_run_sweep_seconds`
  (60), `workboard_run_timeout_seconds` (the routine timeout's value),
  `workboard_run_max_attempts` (3), `workboard_quota_retry_minutes` (30),
  `workboard_max_tickets_per_user` (2 000, counted exactly at create),
  `workboard_max_runs_per_ticket` (10), `workboard_hidden_rows_retention_days`
  (90),
  `workboard_max_children_per_ticket` (50), `workboard_title_max_chars` (200),
  `workboard_description_max_chars` (8 000), `workboard_comment_max_chars`
  (4 000), `workboard_closed_hide_days_default` (30),
  `workboard_nudge_due_hours` (24), `workboard_nudge_waiting_hours` (48),
  `workboard_nudge_cooldown_days` (2). Every bound a tool parameter meets is
  published from the same setting (ADR-184).

### 4.2 Frontend modules

- `app/[lng]/dashboard/workboard/page.tsx` (thin shell) + `?ticket=<id>` deep
  link opening the detail panel.
- `components/workboard/` — `WorkboardPage`, `Board` (dnd-kit context),
  `Column`, `TicketCard`, `TicketDetailPanel`, `TicketForm`, `CommentThread`,
  `TicketHistory`, `BoardFilters`, `StatusSelect`, `WorkboardNotificationActions`
  (chat), `workboard-reducer.ts` (pure board state: optimistic move, rollback).
- `hooks/useWorkboard.ts` (`useApiQuery` / `useApiMutation`), `types/workboard.ts`.
- `components/settings/WorkboardSettings.tsx` (door to the board + the two
  preferences), entries in `settings-sections.ts`, `settings-section-registry.tsx`,
  `settings-search.ts`.
- Notifications hub: `workboard` count in `HubCounts` + a section listing the
  tickets that need the person.

## 5. Persistence

Three tables, all `USER_PURGED` + `ExportPolicy.FULL` in `user_data_map`, the
ticket table TWO-SIDED (`owner_user_id`, `assignee_user_id`) for export and
purge, like `peer_messages`.

**`workboard_tickets`**

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | `UUIDMixin` |
| `owner_user_id` | FK users CASCADE, NOT NULL, indexed | the board it was created on |
| `parent_id` | FK self CASCADE, nullable | D9; depth 1 enforced by the service |
| `title` | Text NOT NULL | ≤ `workboard_title_max_chars` (published in manifests) |
| `description` | Text nullable | ≤ `workboard_description_max_chars`; the brief LIA runs |
| `status` | String(20) | `idea, todo, in_progress, waiting, validating, done, cancelled` (str-Enum, lowercase, the open_loops pattern); column order = enum order, ONE tuple |
| `priority` | String(10) | `low, medium, high, urgent`, default `medium` |
| `start_at`, `due_at` | DateTime(tz) nullable | UTC; the person's zone at display |
| `assignee_kind` | String(10) NOT NULL | `human` / `lia` (D7) |
| `assignee_user_id` | FK users, NOT NULL, indexed | RESTRICT on delete; the purge resets assignments FIRST (see §5.1) |
| `peer_connection_id` | FK peer_connections SET NULL, nullable | non-null iff `assignee_user_id != owner_user_id` (D8) |
| `position` | Integer NOT NULL | order inside a column, on the OWNER's board; a peer's board has tickets from several owners, so it orders by priority then due date and ignores `position` |
| `follow_owner`, `follow_assignee` | Boolean, default false | D6; `follow_assignee` reset on reassignment |
| `created_by` | String(10) NOT NULL | `user` / `lia` / `peer` (D13) |
| `status_changed_at` | DateTime(tz) NOT NULL | the « hide closed after N days » filter and the heartbeat's « waiting too long » |
| `run_not_before` | DateTime(tz) nullable | quota back-off; set by the sweep, never by a person |
| `run_claimed_at`, `run_attempts` | DateTime(tz) nullable / Integer | the claim and the reaper |
| `last_run_id`, `last_run_at`, `last_run_outcome`, `last_run_error` | String / DateTime / String(20) / Text | `success, waiting, failed, skipped_quota, skipped_busy`; error text is a typed code + a bounded message, never a traceback |
| `last_run_tokens_in`, `last_run_tokens_out`, `last_run_cost_eur` | Integer / Integer / Numeric | D18 snapshot |
| `last_nudged_at`, `nudge_count` | DateTime(tz) nullable / Integer | heartbeat cooldown (D14) |
| `created_at`, `updated_at` | `TimestampMixin` | |

Indexes: `(owner_user_id, status)`, `(assignee_user_id, status)`, and the
sweep's partial index `(start_at)` WHERE `assignee_kind = 'lia' AND status = 'todo' AND run_claimed_at IS NULL`.
CHECK: `(peer_connection_id IS NULL) = (assignee_user_id = owner_user_id)`.

**`workboard_comments`** — `ticket_id` FK CASCADE, `author_kind`
(`user`/`lia`/`peer`), `author_user_id` FK users SET NULL nullable, `body` Text
(≤ `workboard_comment_max_chars`), `run_id` String nullable, `created_at`.

**`workboard_ticket_events`** — immutable (`created_at` only, the
`peer_access_log` pattern): `ticket_id` FK CASCADE, `actor_kind`, `actor_user_id`
nullable, `kind` (`created, status_changed, assigned, priority_changed,
dates_changed, run_started, run_finished, follow_changed`), `payload` JSONB
(`from` / `to`, bounded), `created_at`. What humans did lives here; what LIA did
is ALSO in the ADR-263 registers through the tool gate and the notification
claim. The two never add up and are never joined.

### 5.1 Lifecycle rules

- Any status → any status by a person (UI or chat), including `done` →
  `todo`. Only the RUN's own transitions are conditional
  (`WHERE status = 'in_progress' AND last_run_id = :run_id`), so a person
  moving a ticket during a run wins and the run's late settle is a no-op that
  logs `workboard_run_settle_lost`.
- Delete in any state (owner only; a peer assignee may not delete). Parent
  delete cascades children — the confirmation card says how many.
- Account deletion: BEFORE the cascade, `UPDATE workboard_tickets SET
  assignee_kind='human', assignee_user_id=owner_user_id,
  peer_connection_id=NULL WHERE assignee_user_id = :deleted AND owner_user_id
  <> :deleted` (declared in `build_purge_statements`, asserted by the
  user-data-map guard); then the purge DELETES the rows the account owns
  (`USER_PURGED`, explicit statement — comments and events follow by FK
  cascade). The `assignee_user_id` FK is RESTRICT on purpose: a row that
  escaped the reset makes the account deletion fail loudly rather than
  vanish from someone else's board in silence.
- Connection removed / declined / blocked (the `PeerEvent` hook in
  `PeersService`): same reset for every ticket carrying that
  `peer_connection_id`, both sides notified through the existing peer
  notification path, one event row per ticket.
- Timezone change: nothing to recompute — `start_at` and `due_at` are instants
  the person chose, not wall clocks (unlike a reminder's schedule).

## 6. Execution by LIA (the run)

Eligible: `assignee_kind = 'lia'`, `status = 'todo'`, `run_claimed_at IS NULL`,
`(start_at IS NULL OR start_at <= now)`, `(run_not_before IS NULL OR
run_not_before <= now)`, `run_attempts < workboard_run_max_attempts`, and the ticket's total run
count below `workboard_max_runs_per_ticket` (D3b — « Run now » refuses past
it with a stable code). `idea` never runs; « Run now » sets `status = todo` and `start_at = NULL`.

One tick of the sweep (`workboard_run_sweep_seconds`, default 60, jittered):

1. Reap stale claims (older than `workboard_run_timeout_seconds`); delete the
   hidden rows of tickets closed for more than
   `workboard_hidden_rows_retention_days` (D3b, one bounded DELETE per pass).
2. Claim ONE eligible ticket per pass with `FOR UPDATE SKIP LOCKED` and the
   conditional `UPDATE … SET status='in_progress', run_claimed_at=now,
   last_run_id=:new, run_attempts=run_attempts+1 RETURNING`; write the
   `run_started` event; commit. The ticket is `in_progress` on both boards
   from this instant.
3. `run_instruction` on the assignee's account:
   - user inactive → settle `failed` (`assignee_inactive`), no retry;
   - quota blocked (`is_user_blocked_for_llm`, layer `workboard_runner` — both
     ceilings, ADR-272) → release the claim, `run_not_before = now +
     workboard_quota_retry_minutes`, outcome `skipped_quota`, status back to
     `todo`, logged « skipped », never « failed »;
   - HITL pending on the conversation, or `chat:active_run` held → release,
     outcome `skipped_busy`, status back to `todo`, next tick;
   - otherwise take the lock (`register_active_run`, heartbeat while running,
     release in `finally`, shielded), set `out_of_turn_origin_ctx` to
     `{kind: "workboard", ticket_id, run_id, refusals: []}`, run with
     `is_automated_source=True`, `auto_approve_plan=True`,
     `user_execution_mode="pipeline"` (D5), the ticket brief as the message,
     the assignee's language, zone and display mode. Both archived rows carry
     `hidden = true` and the ticket stamp (D3, D3b).
4. The brief (`prompts/v1/workboard_ticket_brief_prompt.txt`, versioned) frames
   the description as the task, names the ticket, its parent's title and its
   sibling titles when it is a child (so a decomposed plan keeps its context)
   — the OWNER's words only: comments, which a peer may have written, are
   never part of the instruction (ADR-167/170, data are never instructions) —
   and instructs: do the work with the tools, answer with the result the person
   will read on the ticket, and if an action needs the person's confirmation
   say so and stop (the gate will refuse it anyway — D5).
5. Settle from an EXPLICIT result:
   - answer streamed, no interrupt → LIA comment with the answer (post-processed
     `content_replacement` when present, the routine lesson), status
     `validating`, outcome `success`;
   - a tool refused by the gate with `confirmation_impossible_unattended` (a
     `confirm` OR, after the D5 amendment, a `draft` tool), or a
     `hitl_interrupt` chunk (a clarification — the safety net) → status
     `waiting`, outcome `waiting`, comment « waiting for you: <what> ». The
     refusal is read from a STRUCTURED signal, never from the prose: the gate
     appends `(tool_name, error_code)` to the `refusals` list of
     `out_of_turn_origin_ctx` when one is set (one line in the gate,
     best-effort, no I/O), and the settle reads that list. On an interrupt the
     pending interrupt is cleared from the store (`hitl_store.clear_interrupt`,
     the call `service.py:1469` already makes) so the person's next chat
     message is not read as a decision — and lot 2 PROVES on the real graph
     that a new user message after an abandoned interrupt is answered normally
     and rehydrates no card. The notification carries `?intent=` whose
     sentence, built by `ProactiveMessages`, names the ticket by id and asks
     LIA to do the pending action and then comment and move the ticket with
     its own tools — the turn is attended, so drafts and confirmations show
     their cards;
   - transient errors retried up to the cap with the routine's back-off;
     exhausted or non-retryable → stays `in_progress`, outcome `failed`,
     `last_run_error` = typed code + bounded message, no automatic retry until
     the person acts (« Run now »).
6. Cost snapshot from `token_usage_logs` where `run_id = :run_id` (one
   aggregate); write `run_finished`; commit; notify (§7).

The ticket's turn carries `source = scheduled` in the three registers
(`resolve_source(automated=True)`) — the person's own deferred instruction, the
same authorship as a routine (ADR-263). A run of a ticket LIA created on its own
(D13, later) will pass `proactive=True` through the existing seam; nothing else
changes.

## 7. Chat: notifications and commands

**Notifications** go through `NotificationDispatcher.dispatch(task_type="workboard")`
inside `proactive_notification_effect(task_type="workboard")`, archive-first
(the archived row IS the chat message), with metadata `type =
proactive_workboard`, `ticket_id`, `ticket_title`, `event` (`run_started`,
`run_finished`, `waiting`, `assigned`, `comment`, `status_changed`),
`board_url`, `ticket_url`, and — for `waiting` — `intent`. Titles and bodies are
written sentences in `ProactiveMessages` (no model call: a notification about a
ticket is a fact, not prose to personalise), the LIA comment excerpt bounded.

Who is notified, per event, subject to D6:

| Event | Owner | Assignee (if another person) |
|---|---|---|
| run started / finished / LIA comment | if `follow_owner` | if `follow_assignee` |
| waiting for the person | ALWAYS the account the run belongs to | — |
| assigned to you | — | ALWAYS, once per assignment |
| status / priority / dates changed by the other side | if follow | if follow |

The frontend renders `proactive_workboard` with the generic proactive tint and a
`WorkboardNotificationActions` row (the `PeerMessageActions` precedent): « Open
the ticket », « Open the board », and for `waiting` « Finish in the chat »
(`?intent=`). `useNotifications` needs no new route: `proactive_*` is
prefix-matched.

**Commands** — six tools, agent `workboard_agent`, domain `ticket`
(`PROGRAM_DOMAIN_CONFIGS`, `result_key = "tickets"`, `related_domains = ["peer"]`
so a peer name in the sentence keeps the peer directory in play, metadata
`feature_flag = workboard_enabled`):

| Tool | Policy | Notes |
|---|---|---|
| `create_ticket_tool` | reversible | title, description, priority, start/due (local ISO, `normalize_user_datetime`), `assignee` = `me` / `lia` / a peer name (resolved like `_resolve_shared_peer`, accepted connections only), `parent_ticket`, `follow` |
| `update_ticket_tool` | reversible | any field incl. `status` and `assignee`; `run_now` |
| `comment_ticket_tool` | reversible | plain text |
| `list_tickets_tool` | read | filters status / assignee / priority / overdue / due window / text; exact total; `RegistryItemType.TICKET`, `CONTEXT_DOMAIN_TICKETS` |
| `get_ticket_tool` | read | children, comments, last run, cost |
| `delete_ticket_tool` | confirm | generic `TOOL_CALL` card; names the children it cascades |

Every bound the service enforces is published as a `ParameterConstraint`
(ADR-184). Ticket references resolve by id or unique folded title (D11). The
tools execute in both modes; LIA may call `create_ticket_tool` several times in
one plan to decompose work (children of the ticket it was asked about).

**Routing** (D12): the DomainConfig description says what a ticket is NOT
(a provider to-do, a reminder, a routine) and lists the words (workboard,
ticket, board, kanban, column names in prose). A measured corpus
(`tests/unit/domains/agents/workboard/routing_corpus.json`, ≥ 8 families × 6
languages: create for me / for LIA / for a peer, move, comment, list mine,
overdue, delete, and NEGATIVE cases that must stay `task`, `reminder`,
`automation`) has a deterministic half (prompt contract: the domain and its
disambiguation reach the analyzer prompt; the tool manifests carry the
keywords) and a provider half run as a script (`task workboard:corpus:measure`,
the recurrence-corpus shape — never a test that skips on a missing key,
ADR-155). The oracle is the tool selected, per sentence.

## 8. Peers

- Assignment to a peer requires `peers_enabled` and an ACCEPTED connection;
  the connection id is stored and re-checked on every write and at every run
  claim (a peer-delegated LIA run executes on the peer's account and stops if
  the connection is gone).
- The peer's board lists the ticket under « assigned to me » with the owner's
  name; they may change status, priority, dates, comment, set their own follow
  flag, reassign to the owner; they may not delete, may not reassign to a
  third person nor to their own LIA (D7), may not edit the title or
  description (the owner's words). Refusals are stable error codes the
  frontend translates.
- Both sides read the same row, so no reconciliation exists to get wrong; the
  event log names the actor.
- Export: side-scoped like `peer_messages` — each side receives the tickets on
  its board. Purge: §5.1.

## 9. Heartbeat (D14, own lot)

`fetch_workboard_context` (open-loops template): tickets on the person's board
that are overdue, due within `workboard_nudge_due_hours`, or `waiting` for
longer than `workboard_nudge_waiting_hours`, outside a per-ticket cooldown
(`workboard_nudge_cooldown_days`), capped. Wiring: `HeartbeatSourceLabel +=
"WORKBOARD"`, the source tuple in `context_aggregator`, `source_policy` lists,
the heartbeat surface's domain table in `consultation_surfaces`
(`workboard → ticket`), the prompt section, and `_bump_used_workboard` after a
DELIVERED notification that used the source. The domain noun `ticket` joins
`treatments.domains` (six locales) and `TREATMENT_DOMAIN_LABELS`.

## 10. API

All under `/workboard`, `Depends(get_current_active_session)`, flag-gated in
`routes.py`, `workboard_enabled` published in `/config` features.

| Route | Purpose |
|---|---|
| `GET /workboard/tickets` | the board: filters (`status`, `assignee` = `me`/`lia`/`peer`/`all`, `priority`, `overdue`, `due_before`, `q`, `include_closed_before`), `sort`, `limit`/`offset`; returns rows + EXACT total + `counts_by_status` (one `GROUP BY` over the same filter) |
| `GET /workboard/tickets/{id}` | detail: children, comments, events, last run |
| `POST /workboard/tickets` | create (the peer connection resolved server-side from `assignee_user_id`) |
| `PATCH /workboard/tickets/{id}` | partial update; own follow flag; reassignment |
| `POST /workboard/tickets/{id}/move` | `{status, position}` — the drag-and-drop write, ONE statement re-numbering the column |
| `POST /workboard/tickets/{id}/run-now` | `todo` + `start_at = NULL`, refused for a non-LIA assignee |
| `POST /workboard/tickets/{id}/comments` | add |
| `DELETE /workboard/tickets/{id}` | owner only |
| `GET /workboard/needs-me` | hub section: `waiting` on my account + overdue on my board, exact total |

Errors through the centralised raisers; `check_resource_ownership` semantics:
private resource, `hide_existence=True` (a peer probing an id they are not on
gets 404, byte-identical to « unknown »).

## 11. Frontend

- **Board** (`lg` and up): seven columns inside ONE horizontally scrolling
  container (`overflow-x: auto`, the body never scrolls sideways), column
  header = name + exact count, cards sortable within and across columns
  (dnd-kit pointer + keyboard sensors, `announcements` from the locale; the
  touch sensor takes a delay-and-tolerance activation constraint so a finger
  scrolling the column never starts a drag — measured on 390 px in e2e).
  Below `lg`: a column selector (native `<select>` + prev/next) and the
  column's list; the same reducer, the same `move` call.
- **Card**: title, priority badge (`priorityTone`), assignee chip (me / LIA /
  peer name), due date (overdue in `destructive`), children done/total, run
  state (running spinner, waiting badge, failed badge with the bounded
  message), follow bell (own side), `RowActions`: open, status `<select>`,
  delete (owner). Status change from the select and from a drop share one
  mutation with optimistic update and rollback on error.
- **Detail panel**: every field editable per §8 rights, children list with
  inline add, comments thread, history, last run (outcome, cost, tokens,
  « Run now », « Finish in the chat » when waiting), delete.
- **Filters and sorts**: assignee, priority, overdue / due this week, text,
  « show closed older than N days »; sort by priority, due, updated, created.
  Filter state in the URL (`?assignee=…`) so a link is a view.
- **Settings**: `WorkboardSettings` — door to the board, `closed_hide_days`,
  a `follow_default` (applies to tickets the person creates). Searchable.
- **Hub**: `workboard` badge + « Needs you » section listing `/needs-me`.
- **Chat**: `WorkboardNotificationActions`; the `?intent=` path is the existing
  one.
- **i18n**: `workboard.*` namespace in the six locales (parity hook), the
  dnd-kit announcements included; `treatments.domains.ticket`;
  `effects.labels.<tool>` for the six tools.
- **Design system**: `FormSection`, `FieldFrame`, `RowActions`, `SectionToolbar`,
  `EmptyState` (`reason` distinguishes « no ticket yet » from « filter matched
  none »), `Skeleton` on first load, `aria-busy` on refresh.

## 12. Registers, quotas, observability

- **Registers**: chat-driven changes are recorded by the tool gate (source
  `user`, policies above). A LIA run records its consultations and effects
  inside the turn (source `scheduled`) and its decision row, whose two
  pointers resolve to the HIDDEN archived rows (D3) — the export and the
  register readers open them with `include_hidden=True`, and a guard test
  refuses any message read in the conversation repository that neither
  applies the visibility predicate nor names the flag; the notification is a
  claimed-then-settled action (`proactive_notification_effect`). Conversation
  totals (`message_count`, token totals) INCLUDE hidden rows: they say what
  ran on the account, which is what a total is for. The
  runner spends no model call of its own, so `LLM_SPEND_ROADS` gains no
  entry; `NOT_A_READER` gains `workboard` with the reason « runs the pipeline
  inside a turn, whose tool gate records every consultation; the runner itself
  opens no source » — verified against the guard's call-site enumeration at
  lot 2, and moved to `CONSULTATION_RECORDERS` only if the guard proves the
  runner reads something the turn does not record.
- **Quotas**: the account ceiling and the instance ceiling both apply to a run
  by construction (pre-check + in-turn guards, ADR-272); a refusal is
  `skipped_quota`, degraded and logged as skipped.
- **Metrics** (each wired to a panel in a new `29-workboard.json` dashboard,
  `... or vector(0)`): `workboard_runs_total{outcome}`,
  `workboard_run_duration_seconds`, `workboard_ticket_events_total{kind,actor_kind}`,
  `workboard_notifications_total{event}`, `workboard_tickets_open`,
  `lia_hidden_run_rows`, `lia_hidden_run_bytes` (gauges from the product
  rollup, D3b). Logs: ids and counts at INFO, never a title or a body.
- **Redis**: `chat:active_run` only (already declared); no new family.

## 13. Out of scope (YAGNI)

Recurring tickets (a routine exists), attachments on comments, labels or tags,
several boards per person, ticket templates, LIA creating tickets on its own
initiative (D13 keeps the door), a second-level hierarchy, real-time board
sync between two browsers (the page refetches on focus and after every
mutation; a peer's change is seen on the next load), a « checklist » shape
(the fallback the owner allowed if D9 proves too heavy — decided at lot 1
review, not before).

## 14. Test plan

The plan grows during implementation and is executed in full at review.

**Unit (backend)** — `tests/unit/domains/workboard/`, `tests/unit/domains/agents/workboard/`,
`tests/unit/infrastructure/scheduler/test_workboard_runner.py`:
- model enum order = column order (one tuple), status/priority vocabularies;
- service: every transition, depth-1 refusal, rights per side (owner / peer /
  reassignment), follow reset on reassignment, delete cascade count, title
  resolution (unique / ambiguous / none), bounds published = bounds enforced;
- runner: eligibility predicate as a table (every combination of assignee,
  status, claim, start, back-off, attempts), settle conditional on
  `last_run_id`, each outcome path, quota refusal logged as skipped, busy
  skip on a held lock and on a pending HITL, `waiting` clears the interrupt,
  cost snapshot from the aggregate, the notification effect claimed BEFORE
  and settled FROM the dispatch result;
- out-of-turn engine extraction: characterisation tests of
  `execute_single_action` BEFORE the extraction, kept green after it; the
  hidden stamp lands on BOTH rows through the enricher when the ContextVar is
  set and on neither when it is not;
- hidden-row bound: delete-with-ticket, the runs-per-ticket cap refused at the
  API and the tool, the retention sweep touching ONLY closed tickets' rows and
  leaving the register's tombstones; the two gauges read what the sweep
  removed;
- conversation reads: every repository read excludes hidden rows by default,
  `include_hidden=True` returns them, the export and the register readers pass
  it, the guard refuses a new read that names neither (AST over the
  repository's `select(Message)` statements);
- gate: `draft` in an unattended scope is refused with
  `confirmation_impossible_unattended`, `draft` in an attended scope still
  passes through, `confirm`/`draft` refusals append to the runner's collector
  when one is set and touch nothing when none is (the routine and chat paths
  unchanged), decision table re-enumerated;
- cross-account delegation refused (`assignee_kind = lia` with
  `assignee_user_id != owner_user_id`) from the API, the tool and the peer
  side alike;
- tools: each tool via `.coroutine(...)`, policy declared, gate decision in
  source `user` and `scheduled`, planner sees `min`/`max`;
- notifier: recipient table of §7 as a parametrised test, per-side flags;
- guards that must go green by declaration: mutation-policy completeness,
  domain vocabulary parity, treatment labels ×6, user-data-map + purge
  statements, metric coverage baseline, effect labels, i18n_effects,
  `.env.example` sync, tool-registry smoke, file-size and complexity ratchets.

**Integration (PostgreSQL)** — `tests/integration/domains/workboard/`:
- claim with two independent actors (`SKIP LOCKED`, exactly one wins);
- stale-claim reaper; settle lost to a person's move;
- purge of a deleted assignee resets the owner's ticket and deletes the
  owner's; export side-scoped for both sides;
- the sweep's partial index is used (EXPLAIN on the eligibility statement).

**Routing corpus** — deterministic half in unit, provider half measured on the
dev instance with the report attached to the PR (D12).

**Frontend (vitest)** — reducer (move, optimistic, rollback, re-numbering),
filters and sorts, card accessible names in en + fr, keyboard move through
the select and through dnd-kit's keyboard sensor, first-load skeleton vs
refresh `aria-busy`, detail panel rights, `WorkboardNotificationActions`
links, `useWorkboard` verbs return `{ok, errorCode}`.

**E2E (Playwright, hermetic)** — board journey (create, drag between two
columns, select-based move, comment, delete with card), mobile 390 px
(no horizontal body overflow, column selector), axe on the board and the
panel, a `proactive_workboard` SSE message rendering its actions and the
`?intent=` path sending exactly one message.

**Runtime proof on docker dev** (before any completion claim): a ticket
assigned to LIA with no start date runs within two minutes; the comment,
status, cost and the three register rows exist and the decision row's two
pointers resolve to hidden rows; the chat history endpoint shows NO row of
the run with follow off and exactly ONE notification row with follow on,
while the account export contains all three; a ticket needing an email stops
in `waiting` with a working intent link and no `RuntimeError` in the logs; a
new chat message typed after an abandoned clarification is answered normally
and no card rehydrates; a live chat turn started during a run
is refused nothing and the run is skipped as busy (and the oracle is
falsified once by disabling the lock); a peer assignment appears on the
second account's board, and removing the connection resets it on both.

## 15. Lots

0. This spec, ADR-276, `docs/technical/WORKBOARD.md`, `docs/knowledge/38_workboard.md`, index and architecture docs.
1. Backend core: config, constants, models + migration (replay-check), repository, service, router, user-data-map, purge, export, hub count, i18n messages, unit + integration tests.
2. Out-of-turn engine extraction + origin ContextVar and enricher + hidden-row read predicate + gate amendment (draft unattended) + workboard runner + notifier + effects/registers + metrics + dashboard + runtime proof.
3. Agent domain: manifests, tools, brief prompt, resolution, corpus (deterministic + measured), registry guards.
4. Frontend: types, hook, board (dnd-kit), panel, filters, settings section, hub section, chat actions, i18n ×6, vitest, e2e, ratchets raised.
5. Peers: assignment rights, connection lifecycle hook, both-side notifications, export/purge tests, runtime proof on two accounts.
6. Heartbeat source `WORKBOARD`.
7. Review: full test plan executed, `task ci:fast`, coverage floors raised (≥ 2 pts margin), Docker start verified.
