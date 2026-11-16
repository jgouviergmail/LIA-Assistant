# ADR-384 — A message written while LIA works waits its turn

**Status**: Accepted, 2026-11-13.
**Date**: 2026-11-13

**Relates to**:
[ADR-117](ADR-117-Background-Chat-Runs.md) — one graph per account, held by a durable admission
and closed only once its producer has joined;
[ADR-378](ADR-378-Permanent-Main-And-Isolated-Discussion-Runtimes.md) — every act names one immutable
target, and a death is never inferred from a timeout;
[ADR-263](ADR-263-Execution-Authority-Chain-And-Effect-Register.md) — an effect is claimed
before it happens and closed from an explicit result;
[ADR-320](ADR-320-The-Chat-Follows-The-Server-Without-A-Reload.md) — the open tabs follow what the
server archives.

## Context

An account runs one graph at a time (ADR-117 amendment 2026-11-10). While LIA answered, the web
composer was closed; a message that still reached the server (a second tab, a routine running, a
race with the end of the answer) was refused with HTTP 409 and the person read « message not
sent ». Writing the next thing while LIA works on the previous one is how people talk, and the
words were lost.

The behaviour was described to the owner on 2026-11-12 and approved as described: the wait is the
ACCOUNT's and the server keeps it; one waiting message per discussion, later words added to it; it
leaves by itself when the account is free; it is never read as the answer to a question; it leaves
by itself only after an answer that ended normally; « Send now » stops, then sends; the voice is
unchanged; Telegram follows the same rule in its own lot.

## Decision

1. **The server keeps the message, one per discussion** (`waiting_messages`). A message written
   while the account is busy is no longer refused: the person's text is kept with the discussion
   it was written in and the generation it was written for. A second message is ADDED to the
   first (a blank line between them) within `CHAT_MESSAGE_MAX_LENGTH`; the person can edit or
   withdraw it until it leaves. Only plain typed text waits: a message carrying attachments,
   dictation costs, a capability directive, a card composition or a one-click decision keeps the
   409 it had, because each of those holds something only the live request carries.

2. **Each run declares how it ended, and the close writes it down.** The driver of a run states
   its end on its authority (`RunAuthority.end`): the browser producer from its status and whether
   it published an error, the out-of-turn runner from its `RunOutcome`, the channel gateway from
   the stream it relayed. The close writes it on the execution row
   (`conversation_executions.end_state`: `normal`, `interrupted`, or `unstarted` for a
   reservation that never ran), in the same transaction that frees the account. An end nobody
   declared is written `interrupted`, never normal (ADR-303: a failure is never read as success).

3. **After a normal end, the oldest waiting message leaves by itself.** Once the close is
   committed, the release listener (`agents/api/waiting_departure.py`, installed into
   `infrastructure/streaming/release_listener.py` and checked at boot) takes the oldest waiting
   message of the account whose discussion has no pending question and sends it as the person's
   own turn: the same settings as a browser turn, a stoppable run on a reconnectable stream that
   the open tab joins. The browser's live authority is never persisted (`core/application_origin`),
   so a departed message runs without it, like every turn the server starts for the person.

4. **After any other end, the waiting messages are held.** In the close's own transaction, every
   waiting message of the account becomes `held`: the person stopped LIA, or the answer failed, and
   what they wrote next may no longer make sense. A held message leaves only on the person's click.
   An operator's recovery of a dead run holds them too.

5. **Never read as an answer.** A discussion with a pending question keeps its waiting message
   waiting: it was written before the question was seen. It leaves after the answer's run ends
   normally. « Send now » is refused while a question is pending there.

6. **Exactly once.** A departure claims the message and the account in ONE transaction: the
   execution is admitted and the message becomes `departing` with that run's stream. Archiving the
   person's message deletes it in the archive's own transaction, so the text either entered the
   discussion or is still there. A run that ends before archiving leaves its departing message
   `held`, said to the person, never sent again by the server.

7. **« Send now » stops, then sends.** It marks the message; if the running answer belongs to the
   same discussion and can be stopped, it asks that run to stop; at the release, whatever the end,
   the marked message leaves first. On a free account it leaves at once. A run in another
   discussion is not stopped from here (an old tab cannot stop another discussion's work,
   ADR-378): the marked message leaves first when it ends.

8. **No race leaves a message behind a free account.** The message is kept under the account's
   lock, the one admission takes, after reading whether the account is busy. When the account is
   already free, the request names the run it was written behind (`behind_stream_id`): if that run
   ended normally the message leaves now, otherwise it is held.

9. **The discussion owns it.** A reset or a deletion of the discussion removes its waiting message
   in the same transaction; deleting the account removes them all.

## Consequences

- One indexed `DELETE` joins every archive of a person's message, and one `UPDATE` every close
  that did not end normally.
- `chat_waiting_messages_total{event}` counts what happens to a waiting message (kept, added,
  departed, held, sent now, edited, withdrawn) on the agents dashboard.
- The composer stays open while LIA answers, for text.

## What this decision leaves, and says so

- **Telegram** answered « busy » and dropped the message: lot 34 of the channel programme
  applies this rule there since — see the amendment of 2026-11-15 below.
- **A note handed to the running answer** (the message read by the loop at its next step) is a
  separate decision, not taken here — taken since by
  [ADR-385](ADR-385-A-Note-Joins-The-Answer-Being-Written.md) (2026-11-13): a waiting message can
  join a ReAct answer a person waits for, read at the loop's next model call.
- An archive that fails while a departed run goes on (the archive is best-effort, ADR-117) leaves
  the message `held` although LIA answered it: the person sees both and withdraws it.

## Amendment 2026-11-15 — words written on Telegram wait too (lot 34)

Telegram follows the rule in its own lot, as the context announced:

1. **A message written on Telegram while the account is busy is kept like the app's**, for Main,
   through the channel gateway (`agents/api/waiting_channel.keep_from_channel`), under the same
   owner lock. Its channel is written on the row (`waiting_messages.reply_channel`, set once and
   kept: an edit from the app never moves the answer away), and the person's message is marked
   « seen » by a 👀 reaction, a sentence where Telegram refuses it. A voice note waits as its
   transcription.
2. **It is answered where it was written.** The departure reserves the account unrelayed and runs
   the person's channel turn (`channels/waiting.start_channel_turn`), which owns the reservation
   from its first instruction; a channel switched off or unlinked meanwhile answers in the app.
3. **A message a release held is told on its chat.** The close returns the ids it held
   (`SettledRelease.held_ids`), the release announces them, and the notice quotes the words with
   the bubble's two answers as buttons — send it now, withdraw it — refused like a question's
   button for an unknown chat, a deactivated account or a channel switched off. A notice that
   cannot be sent never undoes the release.
4. **What cannot wait does not.** An answer to a pending question (it IS the answer), a shared
   position and a file: kept, each would leave as words alone, its meaning lost. The person is
   told to send it again.

The migration `5ad5dfadfe7a` adds the column and its `CHECK`. The rest of the Telegram lot is
[ADR-389](ADR-389-Telegram-Reads-And-Answers-Like-The-Chat.md).

## References

- `apps/api/src/domains/conversations/waiting_models.py`, `waiting_repository.py`
- `apps/api/src/domains/agents/api/waiting_departure.py`, `waiting_router.py`
- `apps/api/src/infrastructure/streaming/release_listener.py`, `run_admission.py`
- `apps/api/src/domains/conversations/execution_repository.py` — `close_owned(..., end=)`
- `apps/web/src/hooks/useWaitingMessage.ts`, `apps/web/src/hooks/useWaitingComposer.ts`,
  `apps/web/src/components/chat/WaitingMessageBubble.tsx`, `apps/web/src/lib/waiting-message.ts`
- `docs/technical/WAITING_MESSAGES.md` — the whole mechanism, with its limits
- `apps/api/src/domains/agents/api/waiting_channel.py`, `apps/api/src/domains/channels/waiting.py`,
  `apps/api/src/infrastructure/channels/telegram/waiting_keyboard.py` — the channel's half
  (amendment 2026-11-15)
