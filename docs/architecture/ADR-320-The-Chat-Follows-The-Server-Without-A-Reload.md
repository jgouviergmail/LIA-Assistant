# ADR-320 — The chat follows the server without a reload: a signal after every commit, a merge instead of a replace

**Status**: accepted — 2026-09-25 (owner request: « the discussion does not always refresh; the latest messages should appear automatically without any reload visible to the person, positioned on the last message unless the reader is browsing the list or doing something else on the page, and never disturbing an action in progress »; owner arbitration Q5: keep the end-of-stream alignment — the question at the top, the start of the answer visible — and keep the existing conditional indicator for what arrives while the reader is away)
**Amends**: ADR-117 (background-run reattachment — the foreground return keeps it and nothing else), ADR-138 (the `done` chunk's archived ids), ADR-276 (hidden rows of out-of-turn runs), ADR-279 (the reset copy)

## Context

A person's conversation receives messages from many places: the tab they are
typing in, another tab or device, a Telegram turn, a voice relay, a routine, a
reminder, a proactive notification. Measured before the change:

1. **Most of those paths published nothing.** Only reminders, proactive
   notifications and routines put an event on the person's real-time channel;
   a Telegram turn, a voice relay or the same account in another browser left
   an open tab silent until it was reloaded by hand.
2. **The foreground return compared LENGTHS.** On `visibilitychange` the page
   read the newest page (50 messages) and replaced the list only when the page
   was LONGER than the list on screen — once 50 messages were loaded, no new
   message was ever seen.
3. **Every refresh REPLACED the list.** A routine's result or a relayed voice
   turn triggered `setMessages(newestPage)`: every bubble remounted (a flash,
   a lost selection, closed disclosures), and the older pages the reader had
   scrolled into vanished with their pagination cursor.
4. **Notifications built their own bubbles** under an id no row carries
   (`reminder_id`, `target_id`) — so the next read of the history showed the
   same message a second time.
5. **The real-time channel gave up after five failed reconnections**, until a
   manual reload, and never caught up what it missed: Redis Pub/Sub keeps
   nothing.

## Decision

1. **A committed change is announced from the one door every message goes
   through.** `ConversationService.archive_message` arms a
   `conversation_updated` signal and `reset_conversation` arms
   `conversation_reset` (`domains/conversations/sync_signal.py`). The signal
   leaves on the session's `after_commit` — `archive_message` does not commit,
   and a tab told before the commit would read the old page and conclude
   nothing had changed; a rollback drops what was armed. One signal per account
   per transaction, a reset winning. It carries no content: the tab reads its
   own history through the authenticated route. A hidden row (ADR-276)
   announces nothing. Every outcome is counted
   (`conversation_sync_signals_total{kind,outcome}` — `published`, `no_redis`,
   `failed`, `no_loop` — drawn on dashboard 09). Proven on real PostgreSQL:
   nothing before the commit, nothing after a rollback, one signal per
   transaction, the account (not the conversation) named.

2. **The channel has ONE name.** `infrastructure/cache/user_channel` holds
   `user_notifications_channel()` and `publish_to_user()`; the SSE route and
   the five existing publishers read the same function instead of spelling
   `f"user_notifications:{user_id}"` six more times.

3. **A turn's `done` names both rows it archived.** `archived_user_message_id`
   joins `archived_message_id`, through a branch-free enricher
   (`with_archived_message_ids`) that REPLACED an `if` in the codebase's worst
   hotspot; the reducer gives the live question its `message_db_id`. **A
   bubble that already names its row is never renamed** — neither the question
   nor an answer: when the `done` finds no bubble of its own, the reducer's
   older fallback attaches it to the last assistant bubble, which may be an
   EARLIER answer, and giving that bubble the new row's id would have brought
   its own row back as a second copy at the next merge (found by the frontend
   coverage gate, 2026-09-25; pinned by `chat-reducer.sync.test.ts`).

4. **The thread is MERGED, never replaced** (`lib/chat-merge.ts`, a pure
   function behind the reducer's `MERGE_SERVER_PAGE`):
   - a bubble is recognised by the ids it may carry — its own id (a history
     row, a live-session row) or its `message_db_id`; a bubble that learned
     neither (an interrupted turn, a HITL question archived after its stream
     ended) is paired by role and whitespace-normalised text, only among the
     bubbles nothing else claimed and never an archived row against another;
   - what did not change keeps its identity (the same object: no re-render);
     a history row the server changed since (a rewritten card, a restated file
     — ADR-319 — a late token count) is taken from the server under the SAME id
     (a re-render, never a remount); a live bubble keeps what its stream gave it;
   - a bubble that exists only here (an error, a question in flight) stays after
     the bubble it followed; a second bubble naming an already-claimed row is
     dropped;
   - an empty page never empties the thread (a failed read looks the same); a
     page older than the thread adds nothing; a page beyond everything on
     screen (more than a page arrived while away) replaces the thread and the
     caller restarts its scroll-up pagination from it.

5. **Asks are coalesced and deferred** (`lib/chat-sync.ts`, a plain class
   tested without React, wired by `hooks/useConversationSync.ts`): ten signals
   during one read make one more read; nothing touches the thread while a turn
   streams, a past page of history is on screen (QW-2) or older messages load —
   the ask runs once the thread is free; a reader holding a text selection or
   an open menu is waited for by looking again 1.5 s later; a failed read merges
   nothing and loops nowhere — the next ask reads again. A reset announced by
   the server empties the thread once it is free. The tab asks on its own when
   it may have missed something: back in the foreground, back online, the
   stream reconnected.

6. **The channel is never given up on** (`hooks/useNotifications.ts`): retries
   wait one more 3-second unit each time up to one minute while the tab is
   visible, pause while it is hidden and restart at once on `online`; a
   reopened stream is announced so the thread catches up what Pub/Sub dropped.
   The two sync signals are routed to their own callback — never listed,
   counted or rung as notifications.

7. **The page composes, it no longer decides** (`hooks/useChatServerSync.ts`):
   a reminder, a proactive notification or a routine keeps its toast and asks
   for a sync; its message reaches the thread as the archived row. The
   foreground return keeps ONLY the background-run reattachment (ADR-117, which
   still replaces with DB truth when a run resumes). The scroll rules are
   untouched (Q5): a reader at the bottom follows an arrival, a reader away is
   not moved and the floating button's badge counts it.

8. **The reset confirmation says what a reset removes.** It announced the
   deletion of « all your attachments — AI-generated images included »; since
   ADR-279 a reset removes the files the person attached and keeps what LIA
   generated. The copy (six languages) and the FAQ now say so, and mention a
   kept file (ADR-319).

Measured on Docker dev with the real stack (browser, API, Redis, PostgreSQL): a
message archived by another process appeared in an open chat less than 0.5 s
after its commit, once, with exactly one read of the history, the bubble
already on screen still the same DOM node and the page never reloaded; a reset
confirmed in one tab emptied another tab 200 ms later, without a reload. Two
hermetic browser journeys pin both properties (`chat-conversation-sync.spec.ts`).

## Consequences

- An open chat shows what lands elsewhere — Telegram, voice relays, routines,
  reminders, another device — without a reload, and a reader's position,
  selection and open panels survive it.
- The older pages a reader scrolled into survive a sync; only a return after
  more than a page of new messages restarts the pagination from the newest page.
- Each committed change costs one Redis publish and, per open tab, one read of
  the newest page (coalesced).
- **Limits, stated**: a change to an EXISTING row (a card rewritten, a late
  TTS backfill) is not signalled by itself — it reaches the tab at its next
  sync (a new message, a return, a reconnection), except where its path already
  notifies (the live relay). A signal lost with Redis down is caught up at the
  next foreground return or reconnection, not before. A bubble paired by its
  words could, in theory, pair with a different row of identical words among
  the unclaimed ones — both would show the same text.

## Alternatives rejected

- **Polling the newest page on a timer.** A read every few seconds per open tab
  for changes that happen a few times a day, and still a delay when they do.
- **Replayable events (Redis streams, `Last-Event-ID`).** A per-account log to
  keep, trim and secure, where a read of the newest page on reconnection says
  the same thing.
- **Replacing the list and restoring the scroll position.** Still a remount:
  selections, focus and open disclosures lost, and the older pages dropped.
- **Keeping the locally built notification bubbles, matched later by a
  synthetic id.** A second identity for one message is exactly what showed it
  twice.
