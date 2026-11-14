# Main and secondary discussions

The badge in the middle of the chat header opens the discussion manager. The account always has **Main** (**Principale** in French). Its **Reset** action clears the conversation. When creation is available, **New discussion** opens a title form. The title is optional: left empty, the discussion is created under a placeholder (« New discussion », in the person's language) and takes its title from the first message its owner writes in it — the first line that says something, cut on a word, with no model call. A title the person typed, at creation or through the rename form, is never replaced. The list opens an existing discussion, offers rename and delete for an annex, and exports any discussion — Main included — as a Markdown file. Deleting the selected annex returns the chat to Main after the server confirms the transition. The same manager works in the chat inside World.

The session badge shows the selected discussion's tokens, recorded cost and current context usage. Switching preserves a draft in its original discussion and applies the account's existing display and assistant preferences. Reminders, notifications and automatic openings appear in Main. Learning from a manual discussion reaches the account's memory and journal through the same consent, eligibility and budget checks.

When deletion takes effect while another tab is editing the annex, that tab withdraws its history and composer. It offers the unsent text from the open composer in a read-only field. Returning to Main opens Main's own draft.

## Searching every discussion

The history search of the chat header filters the loaded messages at once; its **Search all discussions** button asks the server across every active discussion of the account (Main and annexes; a deleted annex is not read). A result names its discussion when it is not the one on screen, and opening it switches through the manager's own door (`ChatDiscussionHost.open`, the focus landing on the badge that now names it), carrying the jump in `lib/discussion-jump.ts`: the arriving discussion, once its history is loaded, shows the page ending at the message with the words marked, and « Back to present » returns to its newest page. A jump is taken by the discussion it names, once, within `DISCUSSION_JUMP_TTL_MS`. Leaving for a result obeys the switcher's rule, one function for both (`lib/discussion-leave.leavingCancelsTurn`): mid-turn, only where background runs are enabled. While more results follow, the panel counts « the N most recent », never a total it does not have (ADR-185).

The assistant reads the same door: `search_conversations_tool` (memory agent) returns what was said, word for word, so a question asked in one discussion can recall another without its history entering the turn. See [long-term memory](LONG_TERM_MEMORY.md), section « 2 ter ».

## Target and storage

| Record | Contract |
|---|---|
| Catalogue | Stable owned business ID and kind, one Main, titles on annexes, exact paged counts. Main's translated display label is independent of a stored title. |
| Graph runtime | The admitted revision and runtime UUID address checkpoints, Store namespaces, pending turns, targeted file usages and stream control. A reset rotates them. |
| Active work | PostgreSQL admission fences writers. Redis delivers the stream and hints, and an expired key cannot free an unjoined writer. Live pins the discussion where it starts, including when the chat selection changes. |
| Learning and records | The account's existing memory and settings remain shared. Deferred personal-data publication checks both consent and source revision. Decisions keep durable facts when message references become null, and bookmarked copies keep their content. |
| Billing | The badge aggregates historically recorded usage for the current discussion. The global account and instance ceilings apply before the same model boundaries as before. Already billed attempts remain recorded after source retirement, including when the response fails. |

## HTTP contract

Routes below are under `/api/v1/conversations`. The authenticated account supplies the ownership context.

| Operation | Request and result |
|---|---|
| List or create | `GET /` pages the catalogue. `POST /` takes a client request UUID for retries and an optional title: omitted or null, the annex waits for its first message to name it (`conversations.title_auto`); a title that is sent must be a valid one, a blank string is refused. |
| Read or rename | `GET /{conversation_id}` reads the owned entry. `PATCH /{conversation_id}` reviews the previous title and revision before changing an annex's title. |
| Automatic title | No route: the turn offers the archived request to `conversations/auto_title.title_waiting_discussion`, in a short transaction of its own after the archive committed. The catalogue takes the title only while `title_auto` holds (one conditional `UPDATE`), writes a `titled` audit row and announces a `conversation_metadata` change, as a rename does. Each worker asks once per discussion: the answer cannot change. An answer to a question, an automated run and Main never name a discussion; a Live delegation names it from the person's spoken words. A rename begun over the placeholder after the title arrived is refused as a stale edit. |
| Reset or delete | `POST /{conversation_id}/reset` and `DELETE /{conversation_id}` both take JSON with `operation_id` and `expected_revision`. They return a `202` receipt for a committed logical change. Main is resettable. Deletion applies to annexes. |
| Observe or resume cleanup | `GET /operations/{operation_id}` reads the owner's receipt. `POST /operations/{operation_id}/retry` resumes the original cleanup when eligible. |
| History and badge | `/me/messages` and `/me/totals` accept the same `conversation_id` and `conversation_revision` selection used by the chat. Legacy omission selects Main. Context usage is absent when its checkpoint cannot be read. |
| Search | `GET /me/search?q=` takes no selection: it searches every active discussion of the account through `conversations/discussion_search.search_discussions`, the door the assistant's `search_conversations_tool` reads too. Only what the chat shows (no hidden row, no blank progress row), case- and accent-insensitive, LIKE wildcards literal, newest first with the primary key ending the order; `q` is 2 to 200 characters. Each result carries its message and its discussion's identity, kind, title (annexes only) and revision. `limit` pages it and `next_cursor`, opaque and versioned, resumes exactly after the last result; `has_more` says whether more follow, and no total is computed. `/me/messages` no longer filters by words: one door. |
| Export | `GET /me/export` takes the same selection and returns the discussion as a Markdown attachment (`conversations/discussion_export.py`): every message the chat shows — nothing hidden, no blank progress row — oldest first, read through a server-side cursor with no ceiling and closed at the instant the export was asked (`X-Discussion-Truncated: false`). The language and the clock are the account's; the person's words are exported as typed, an answer drawn as an HTML document is converted through `core.html_markdown`. No count is printed: a discussion can be reset between a count and the read it would describe. The manager asks for an annex by its identity and generation, and for Main with no selection. Per-account rate limit `RATE_LIMIT_CONVERSATION_EXPORT_PER_MINUTE`. The route holds nothing while the document streams (ADR-304): it authenticates through the stream door and reads ownership on a short session of its own, with no lock. Only an HTML DOCUMENT is converted; a Markdown answer that merely carries an HTML block is exported as written. |

A busy target must finish or join cancellation before it can be retired. An old confirmation or intent for a changed revision is refused. On a lost response the client can reconcile the same operation UUID. `logical_applied` confirms that the current history changed. `cleanup_complete` confirms that all native cleanup phases acknowledged success.

## Rollout and recovery

1. Apply the [Alembic chain](../../apps/api/alembic/versions) with the new schema. Rehearse upgrade, downgrade and structural comparison on a disposable database.
2. Drain old graph and Live writers before switching workers. Confirm the installed head, verify Main and the existing history, and inspect the [cleanup and recovery dashboard](../../infrastructure/observability/grafana/dashboards/09-conversations-users.json).
3. Creation is on by default (`SECONDARY_CONVERSATIONS_ENABLED`). An operator who must drain old writers first sets it to `false` for the rollout and removes the override once the compatible API and browser build are serving. `GET /api/v1/config` publishes the effective creation setting.
4. Withdraw creation with the same switch if needed. Existing annexes, their histories and unfinished cleanup receipts remain available. Use the [lifecycle runbook](../runbooks/alerts/ConversationLifecycle.md) for a stuck operation or reservation.

After an annex has been created or a runtime has been rotated, the migration refuses a return to the singleton schema. Keep compatible code during operational rollback.

Related references include [ADR-378](../architecture/ADR-378-Permanent-Main-And-Isolated-Discussion-Runtimes.md), [long-term memory](LONG_TERM_MEMORY.md), [attachment lifecycle](ATTACHMENTS_INTEGRATION.md) and [Live binding](LIVE_MODE.md#discussion-binding-and-recovery).
