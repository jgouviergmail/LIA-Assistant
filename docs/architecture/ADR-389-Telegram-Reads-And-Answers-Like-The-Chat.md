# ADR-389 — Telegram reads and answers like the chat

**Status**: Accepted, 2026-11-15.
**Date**: 2026-11-15

**Builds on**:
[ADR-384](ADR-384-A-Message-Written-While-LIA-Works-Waits-Its-Turn.md) — a message written while
LIA works waits its turn (amended the same day for Telegram, lot 34);
[ADR-280](ADR-280-Complete-Capability-Control.md) — a switch removes the capability, read at the act;
[ADR-304](ADR-304-No-Transaction-Across-A-Network-Call.md) — nothing is held across a wait;
[ADR-272](ADR-272-Every-Platform-Paid-Token-Answers-To-Both-Ceilings.md) — every euro the platform pays
answers to both ceilings;
[ADR-316](ADR-316-Sharing-A-Generated-Image-With-A-Connection.md) — a third party's words are quoted literally;
[ADR-323](ADR-323-Declared-Language-Complete-Tables-English-For-The-Model.md) — one declared language.

## Context

Telegram is LIA's only external channel, and it read and answered less than the chat it stands
for. Measured in the code before the lot (programme « inspirations from hermes-agent », lots 1,
3, 8, 11, 25, 33, 34; the owner's go on 2026-11-14):

- the result of a routine never reached Telegram, though the FAQ promised it;
- headings, tables and quotes arrived as raw Markdown; an answer citing ten sources drew the large
  preview of the first link;
- nothing could stop a running answer from Telegram, and a message written meanwhile was answered
  « busy » and dropped;
- a shared location, a photo, a document were answered with nothing; a reply lost the message it
  answered;
- a file LIA made never left the app; a voice note was answered in writing only.

## Decision

1. **One door draws everything sent to Telegram** (`formatter.telegram_answer_html`): an answer
   that is an HTML document is converted, its cards left out; what Telegram's HTML subset cannot
   show is drawn (`telegram/structure.draw_structure`: a heading in bold, a table as one group per
   row, a quote, a list, a task box, a rule), the punctuation between a label and its value the
   reader's language's. Notifications pass the content as the chat shows it, and the language.
   Link previews are off unless `TELEGRAM_LINK_PREVIEW_ENABLED`.

2. **A routine's result reaches the channels**, served BEFORE the FCM push: the push sequence
   leaves uncommitted writes on the tick's session, and a channel never waits behind it (ADR-304).

3. **A channel turn can be stopped.** It is reserved cancellable and watches the chat's stop
   signal: `/stop` and the app's Stop end it; a stopped turn says nothing more (a partial answer
   would read as the answer). `/stop`, `/help` and `/start` are answered before any turn is
   claimed; the command menu is published in the six languages by the scheduler's leader.

4. **What a message shares reaches the turn.** A shared position is the turn's consented
   geolocation (the tools read it as the browser's; it is remembered only under the person's
   last-known-location opt-in) and is said in words too; a venue names a place, never the person's
   position; a reply carries the message it quotes, literally and bounded
   (`CHANNEL_QUOTE_MAX_CHARS`), except an answer to a question, which the question frames.

5. **Files travel both ways, through the chat's own doors.** A received photo or document is
   stored by the chat's upload door (`AttachmentService.upload`: type from the bytes, the
   instance's limits, the conversation's source) under the ATTACHMENTS switch read at the act,
   all or nothing, a refusal said. An album is ONE message: its parts meet in Redis, the first
   owns it for `CHANNEL_ALBUM_WINDOW_SECONDS`, a late part is answered alone and a Redis failure
   answers each part alone. A file a turn made is sent from its own row — the person's, ready —
   as a photo or a document; one Telegram cannot carry is named.

6. **A voice note is answered aloud too when voice comments are on** (`users.voice_enabled`):
   the answer's words — no cards, no marks, no link address — capped like the chat's voice, read
   by the voice domain under a run of their own, billed to the person under both ceilings
   (ADR-272); Telegram plays the MP3 as a voice message. A question stays written.

7. **The channel boundary holds.** The channel domain imports no assistant code: each new need is
   a port of the injected gateway (`stop`, `keep`, `act_on_waiting`, `speak`) or a field of the
   request (`position`, `attachment_ids`), required, never defaulted — a caller that forgot it
   would drop a pin or a file in silence.

## Consequences

- `channel_messages_received_total{message_type}` adds `file`, `location`, `command`;
  `channel_messages_sent_total{message_type}` adds `photo`, `document`, `voice`. The channels
  dashboard sums by type, so they appear without a new panel.
- The Redis family `channel_album` (GLOBAL: named by the chat and the album, gone within a minute).
- Every channel-side refusal and outcome is said in the person's language, in six languages.

## What this decision leaves, and says so

- A video, a sticker, an animation are still answered with nothing.
- A turn started on Telegram is not relayed live to an open app; the app shows it once archived
  (ADR-320).
- Found while reading, not changed here: the sender's fallback after a `BadRequest` resends the
  HTML as raw text; `strip_html_cards` cuts at a closing tag even inside code; outbound channel
  notifications read `CHANNELS_ENABLED` but not the CHANNELS capability switch.

## References

- `apps/api/src/infrastructure/channels/telegram/formatter.py`, `structure.py`, `sender.py`,
  `webhook_handler.py`, `files.py`, `bot.py`, `waiting_keyboard.py`
- `apps/api/src/domains/channels/commands.py`, `message_words.py`, `channel_files.py`,
  `albums.py`, `waiting.py`, `inbound_handler.py`, `message_router.py`
- `apps/api/src/domains/agents/api/channel_gateway.py`, `waiting_channel.py`
- `apps/api/src/infrastructure/scheduler/scheduled_action_notices.py`
- `docs/guides/GUIDE_TELEGRAM_INTEGRATION.md`, `docs/technical/CHANNELS_INTEGRATION.md`,
  `docs/technical/WAITING_MESSAGES.md`
