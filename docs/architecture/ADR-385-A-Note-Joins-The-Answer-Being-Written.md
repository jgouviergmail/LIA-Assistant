# ADR-385 — A note joins the answer being written

**Status**: Accepted, 2026-11-13.
**Date**: 2026-11-13

**Relates to**:
[ADR-384](ADR-384-A-Message-Written-While-LIA-Works-Waits-Its-Turn.md) — what the person writes
while LIA works waits its turn, kept by the server;
[ADR-310](ADR-310-ReAct-Turn-Judged-On-Its-Result.md) — what a ReAct call is shown beside the
thread, never written to it;
[ADR-306](ADR-306-Claude-Request-Surface-And-Billed-Prompt-Cache.md) — a generation that binds its
thinking to the conversation refuses a history that changed before it;
[ADR-381](ADR-381-A-Model-Reads-When-Each-Message-Was-Written.md) — a model reads when each of the
person's messages was written;
[ADR-276](ADR-276-Workboard.md) — a predicate over a turn's rows names the
KIND of row;
[ADR-320](ADR-320-The-Chat-Follows-The-Server-Without-A-Reload.md) — the open tabs follow what the
server archives.

## Context

ADR-384 keeps what the person writes while LIA works and sends it as the next turn. It left one
case aside, and said so: what the person writes is often a correction or a detail of the request
LIA is working on (« only the ones open on Sunday »). Sent after the answer, it asks for the work
again. In ReAct mode the loop calls the model several times in one turn; words read at the next
call can change what the loop does next.

Lot 27 of the programme drawn from hermes-agent (« note in the middle of a turn », ReAct only, to be
measured), approved by the owner with wave 5.

## Decision

1. **The person chooses, message by message.** While the answer being written in THIS discussion
   takes notes, the waiting message offers « Add to the answer in progress ». Nothing joins by
   itself: by default a waiting message still waits (ADR-384). A message that joins can still be
   edited, completed or withdrawn until LIA reads it.

2. **Only a ReAct loop a person waits for takes notes, and only while it can still call the
   model.** The execution row says so: `conversation_executions.accepts_notes`. The loop's model
   call sets it when a person waits for the turn (`a_person_is_waiting()`); the loop's two exits
   (the finalize node, the hand-off of a draft to its confirmation) withdraw it; every transition
   of the row away from `running` withdraws it in the same statement, and a `CHECK` holds that only
   a running invocation takes notes. The pipeline mode, a routine, a ticket and a relay never take
   one.

3. **Joining is decided under the account's lock.** `POST /agents/chat/waiting/join` reads the
   account's running invocation under the lock admission and close take: when it is this
   discussion's and takes notes, the waiting message becomes `joining` with that invocation's
   stream; otherwise the request answers 409 `waiting_note_closed` and the message keeps waiting.
   A message can never join a run whose close already settled what waited.

4. **The loop reads it at its next call, and archives it in the same transaction.** At the start of
   each model call, the `joining` messages of the invocation's stream are deleted and archived as
   the person's messages (`build_turn_note_metadata`, `turn_note: true`) in ONE transaction: a note
   is in the discussion or still joining, never both and never neither. The archive's signal
   (ADR-320) tells the open tabs. A note that joins while the model is answering is read by the
   call after it.

5. **The model reads it where it arrived; it is never written into the thread.** Each later call of
   the turn shows the note as the person's message right after the last message the loop had when
   it read it, stamped with when it was written (ADR-381) and framed by one versioned line
   (`react_turn_note_lines`). It is composed per call like a recovery pass (ADR-310), and the two
   are ordered by when they happened when they share a place. Nothing before the note changes, so
   a generation that binds its thinking to the conversation reads its own loop unchanged (ADR-306)
   and the cached prefix holds. Written into `messages`, the note would become the turn's question
   for every reader that takes the last human message as such — the loop's own windowing, the
   response, the extractions.

6. **The loop's exit folds the notes into the turn's request.** At the finalize node and at the
   hand-off of a draft, the turn's question (the same message, by its id) receives each note after
   its text, with its stamp and its line; the response's synthesis is given the same completed
   request. The extractions and the later turns read what the person asked, notes included.
   Folding earlier would change the history before the loop's thinking (decision 5).

7. **A note LIA did not read goes back.** The close's settlement turns a `joining` message of the
   closing stream back into a waiting one, then ADR-384 applies: it leaves by itself after a normal
   end, is held after any other. Nothing written is lost; nothing is read twice.

8. **The row says what it is.** A turn now archives up to four kinds of row: the question, the
   answer, the question LIA asked instead of answering, and the person's notes. A note carries
   `turn_note: true`, and the lookup of an invocation's request names its kind.

9. **The answer being written stays last on screen.** The chat merge keeps the bubble the page is
   streaming after every row the server sends: a row archived while the answer is written (a note,
   a notification) takes its place before it, the order the archive will have once the answer is
   saved, instead of jumping above it at the end.

## Measured

`task react:notes:measure` (`apps/api/scripts/react/measure_turn_notes.py`), 2026-11-13, on the
dev instance: three scenarios of deterministic stub tools run through the loop's own functions —
the ReAct prompt, the stamp, the note's record and its place — the note joining after the first
tool results, on four families read from the instance's catalogue, one of them a generation that
binds its thinking to the conversation (`claude-haiku-5-5`, the case decision 5 guards):

| Model | Calls after the note answered | Note followed | Without the note |
|---|---|---|---|
| `deepseek-flash` | 6/6 | 6/6 | 0/3 |
| `gpt-5.4-mini` | 6/6 | 6/6 | 0/3 |
| `gemini-3.8-flash` | 6/6 | 4/6 | 0/3 |
| `claude-haiku-5-5` | 6/6 | 6/6 | 0/3 |

- **No provider refused the shape** — the person's message after a tool result, the loop's
  history unchanged before it — and every answer that followed a note followed it: the places
  open on Sunday alone, the forecast asked again for the other city (one call after the note,
  every time), the dog in the list.
- **The scenarios discriminate**: run with no note, none of the twelve answers « follows » it.
- **`gemini-3.8-flash` sometimes answers nothing**: 3 of 16 note runs of the city scenario ended
  with no text (`STOP`, its output spent on thinking), 0 of 12 without a note — whose final call
  comes one tool result earlier, so the comparison is not like for like. An empty final message
  is a path the loop already serves: the response is synthesised from the tool results, and it
  reads the request with the note folded in (decision 6).
- The measurement cost 0.31 USD, every run included.
- **A real turn on the dev instance**, on a proof account, through the HTTP routes a browser
  uses: the notes opened 7 s into the turn, the note kept then joined, read by the next model
  call and archived between the question and the answer (`turn_note`, the same stream), nothing
  left waiting, the run closed `normal` with its notes withdrawn, and the answer gave the other
  city's forecast, saying it had fetched only that one « after your correction ». 0.034 USD.

## Consequences

- Two short statements open the notes and read them at each model call of a ReAct turn a person
  waits for; one closes them at the loop's exit. None is held across the model call.
- `chat_waiting_messages_total{event}` gains `joined`, `note_read` and `note_returned`.
- The waiting message gains the status `joining` and the response field `can_join`.
- Under the person's bubble, a note carries a mark saying it was added to the answer in progress.

## What this decision leaves, and says so

- **A turn the person stops** keeps the note in the conversation they read, but not in the model's
  memory of that turn — the same as the partial answer of a stopped turn, which is archived and
  never written to the checkpoint.
- **The pipeline mode** takes no note: its plan is decided before anything runs, and a note would
  need a re-plan the mode deliberately does not have
  ([ADR-346](ADR-346-Advisory-Replanner-Retired-A-Pipeline-Failure-Is-Said-Never-Replayed.md)).
- **Telegram** offers no join: the channel programme's lot 34 applies ADR-384 there first.

## References

- `apps/api/src/domains/agents/api/turn_notes.py` — open, read, close
- `apps/api/src/domains/agents/nodes/react_turn_notes.py` — records, composition, fold
- `apps/api/src/domains/agents/nodes/react_shown.py` — what a call is shown beside the thread
- `apps/api/src/domains/conversations/waiting_repository.py` — `join`, `take_joining`, settlement
- `apps/api/src/domains/conversations/execution_repository.py` — `open_notes`, `close_notes`
- `apps/web/src/components/chat/WaitingMessageBubble.tsx`, `apps/web/src/lib/chat-merge.ts`
- `docs/technical/WAITING_MESSAGES.md` — the whole mechanism, with its limits
