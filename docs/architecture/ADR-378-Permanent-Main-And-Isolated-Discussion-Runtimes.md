# ADR-378 — A permanent Main discussion and an isolated runtime for each discussion

**Accepted** · 2026-11-11

## Context

One account can pursue several topics without losing its usual place for reminders, routines and unsolicited messages. A visible title, the PostgreSQL record and the LangGraph checkpoint have different lifetimes. Reusing a checkpoint identity after a reset can expose previous context or let a late producer recreate it. A TTL, closed browser connection or SSE completion cannot establish that its producer joined.

The [analysis](../superpowers/plans/2026-11-09-secondary-conversations-analysis.md), [counter-review](../superpowers/plans/2026-11-09-secondary-conversations-counter-review.md), [implementation plan](../superpowers/plans/2026-11-09-secondary-conversations-plan.md) and [qualification report](../superpowers/plans/2026-11-09-secondary-conversations-qualification.md) record the native probes and acceptance tests.

## Decision

- **One permanent Main.** Existing users retain the original Main record and its history. Its display label is translated. PostgreSQL enforces a single Main per account. Omitted targets, automatic openings, notifications, routines and autonomous channel returns resolve through Main. A manually selected annex supports the same account preferences and learning admissions.
- **One immutable target per act.** `ConversationRef` binds account, stable discussion ID, kind, revision and runtime UUID. A confirmed request identifies the revision it reviewed. The graph, Store, pending state, file usage and SSE reattachment use the admitted target. A stale selection receives a typed refusal. The browser stores drafts and accepts late data by that identity.
- **One graph execution slot per account.** Adding discussions creates no model calls and opens no additional parallel graph slot. A browser Live session reserves its starting discussion separately, including delegated turns, standbys, direct lookups and closing. The slot is released only when its durable work is joined. An unknown stop goes to recovery.
- **One SQL transition with a durable cleanup receipt.** Reset retains the business record and rotates runtime identity. Deleting an annex removes it from the catalogue. The transition detaches historical bills and releases file usages atomically. A leader cleans the exact retired checkpoint, Store namespaces, pending keys and proven orphan files in restartable phases. Idempotent request receipts recover lost responses without retiring a later generation. Main cannot be deleted.
- **One accounting and learning contract.** Each discussion gets its own history, context footprint and attributed spend. Account memories, journal and preferences use their existing readers and consent checks. Deferred writes validate their source at publication. Previously paid attempts remain in the account and instance ledgers after retirement. Their association with the retired discussion cannot be restored by a late first write. Live standby settlement and the closing card share a short SQL authority, so either completion order keeps the recap and cost.

## Consequences

The catalogue pages metadata without loading histories or checkpoints. Background producers keep using the account's two spend ceilings and provider retry policy. Existing unscoped requests keep the Main contract, and existing annexes stay available when creation is switched off. A reviewable migration and worker rollout are required before creation is served; the switch is on by default, and an operator sets it off for the duration of a rollout. Returning to the old singleton schema would discard identities once annexes exist, so the downgrade refuses that state. The [technical reference](../technical/SECONDARY_CONVERSATIONS.md) describes the operational rollback and user-visible states.

This decision extends [conversation lifecycle management](ADR-042-Conversation-Lifecycle-Management.md), [background chat runs](ADR-117-Background-Chat-Runs.md), [chat synchronisation](ADR-320-The-Chat-Follows-The-Server-Without-A-Reload.md) and [Live mode](../technical/LIVE_MODE.md).

## Amendment 2026-11-12 — an annex may wait for its first message to give it its title

Creating a discussion asked for a title before a single word of it existed, which is the moment a
person knows least what the discussion will be about. The title is now optional.

- **A flag, not a comparison.** `conversations.title_auto` (migration `dd5668ab9b2c`, false for
  every existing row) marks an annex created without a title. It holds a placeholder in the
  person's declared language (`APIMessages.conversation_untitled`) so the catalogue's `CHECK`
  keeps holding. Reading « still automatic » from the title being equal to the placeholder would
  break on the person typing those very words, and on a language change.
- **The title is the person's own words.** `titles.derive_title` reads the first line of the
  first message that says something, on one line, cut on a word
  (`CONVERSATION_AUTO_TITLE_MAX_LENGTH`). No model is called: adding discussions still creates no
  model call (this ADR's third decision), the title costs nothing, exists before the answer, and
  is recognisable in the list because the person wrote it. A title written by a model would be a
  slot, a spend road and a measure of its own.
- **A typed title is never replaced.** The catalogue takes the derived title through ONE
  conditional `UPDATE` on `title_auto` (`claim_waiting_title`), so the order two writers commit
  in cannot overwrite what a person typed; a rename clears the flag, and so does saving the rename
  form unchanged over the placeholder. A rename begun over the placeholder after the title
  arrived is the existing stale-edit refusal.
- **Said the way a rename is.** The turn offers its archived request to
  `auto_title.title_waiting_discussion` in a short transaction OF ITS OWN, after the archive
  committed. Written inside the archive's transaction, the `conversation_metadata` signal would be
  absorbed by the archive's own `conversation_updated` — one signal per discussion and transaction
  (ADR-320) — and the open discussion's header would keep its placeholder until a reload. The
  price is one conditional statement, paid once per worker and discussion: a discussion never
  goes back to waiting, so each worker remembers the ones it already asked about (a bounded
  set of identifiers) instead of spending a transaction on the turn's latency path at every
  request typed in an annex.
- **What never names a discussion**: Main (its label is fixed), an answer to a question (not a
  subject), an automated run (nobody typed it), a request that could not be archived. A Live
  delegation names its discussion from the person's spoken words, not from the voice model's
  restatement of them.
- **The API stays strict about what is sent.** `title` omitted or `null` asks for an automatic
  title; a blank string is still refused, never read as that request.

Guards: `tests/unit/domains/conversations/test_titles.py`, `test_auto_title.py`,
`test_catalogue_contract.py`; `tests/unit/domains/agents/api/test_turn_preparation.py`; on
PostgreSQL `tests/integration/domains/conversations/test_auto_title.py`; the form in
`ConversationCreateDialog.test.tsx`.

## Amendment 2026-11-13 — the person's words are searched in every discussion, through one door

A person who opened annexes could no longer find in the history search what they had said in
another one, and LIA could not either: a question asked in one discussion had no way to the
words of another. Both now read the account's discussions, and the isolation decided above stays
what it was.

- **One door.** `conversations/discussion_search.search_discussions` reads every ACTIVE
  discussion of the account (a deleted annex is not read) and only what the chat shows (no
  hidden row, no blank progress row), with the history search's own matching (`unaccent` +
  `ILIKE`, LIKE wildcards literal), newest first, the primary key ending the order. It is
  registered `VISIBLE_ONLY` with the `ACCOUNT` scope (`message_readers.py`). Two readers:
  `GET /conversations/me/search` (an opaque, versioned cursor; `has_more`; no total, which an
  `ILIKE` over the whole account would pay for nothing) and the memory agent's
  `search_conversations_tool`.
- **The page of history searches nothing of its own.** `GET /me/messages` lost its `search`
  filter, which read one discussion: two doors would be two readings of « which messages hold
  these words ». A tab still holding the previous browser build sends a filter the API no longer
  reads and lists the newest page instead of matches until it reloads.
- **Isolation is the runtime's.** Nothing of another discussion enters a turn's context,
  checkpoint or Store. The tool reads another discussion only when the turn asks it, and returns
  cited passages — the discussion, who spoke, the minute in the person's zone, an excerpt around
  the words — never a history to continue. Reading the person's own words at their request is not
  distilling a memory: the tool calls no model, stores nothing and is not gated by
  `memory_enabled`.
- **The turn that asks is not its own answer.** Archive-first (ADR-117) stores the question
  before the run; the door leaves out the asking run's `run_id`.
- **One way out of a discussion.** A result found elsewhere opens through the switcher's door
  (`ChatDiscussionHost.open`) under the switcher's rule, one function for both
  (`lib/discussion-leave.leavingCancelsTurn`: mid-turn, only where background runs are enabled).
  The jump crosses the switch in `lib/discussion-jump.ts`, taken once by the discussion it
  names, within `DISCUSSION_JUMP_TTL_MS`, after its history loaded.
- **A page is not a total** (ADR-185): while more results follow, the panel says « the N most
  recent ».
- **Measured, not indexed.** The door reaches the account's messages through the discussion
  index and filters them: 1.1 ms for the heaviest development account (404 messages, a frequent
  word and an absent one alike), linear in the account's size, as the one-discussion filter it
  replaces was in its discussion. A trigram index on `unaccent(content)` is the lever a heavy
  account would call for; it is not added before a measurement asks for it.

Guards: on PostgreSQL `tests/integration/domains/conversations/test_discussion_search.py` and
`test_discussion_search_route.py`; `tests/unit/domains/conversations/test_search_cursor.py`,
`test_messages_pagination.py`; `tests/unit/domains/agents/tools/test_conversation_search_tools.py`;
in the browser `useChatHistorySearch.test.ts`, `ChatSearchBar.test.tsx`,
`discussion-jump.test.ts`, `discussion-leave.test.ts` and the journey
`e2e/smoke/chat-history-search-discussions.spec.ts`.
