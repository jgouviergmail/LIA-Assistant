# Direct human text in LIA World

This extends the accepted V1 without putting human conversation in the assistant's
thread, memory, tools or learning pipeline. One explicitly selected visible actor
is the recipient. Room broadcast, voice, invitations and federation remain deferred.

## Authority and lifecycle

The normal HTTP-only session, native operator switch, active account, current world
epoch, controlling tab, cookie binding, actor leases, mutual block policy and private
home visibility are checked before accepting, reading and publishing a message.
The browser supplies a public actor ID, never a recipient account ID. No shared
snapshot contains messages. A replacement controller cannot publish an old job.

Input is plain text: up to 1,000 Unicode code points and 4 KiB UTF-8, rejecting
control/bidirectional format characters except line breaks, tabs and Unicode joiners. It remains
literal text in both the UI and translation prompt. No HTML, markdown rendering,
URL preview, tool call or model instruction is executed. Translation receives only
the message and the two native language codes, never profiles or previous messages.

Content and bounded inbox references expire after thirty minutes in Redis. SQL
retains a minimal idempotency/attempt record, without body or translation. Account
deletion removes its records and cache content through the existing lifecycle port.
Records past their replay window are removed in bounded batches on subsequent
enqueue activity, not by a guaranteed periodic sweep. Client IDs are
fresh UUIDs with a bounded creation time; changed payloads cannot reuse an ID.
Inbox ownership follows the account across a fresh admission, while current
session/controller/epoch authority is still required for every read. Redis body
keys hash client-selected message IDs so they cannot impersonate account-cleanup
patterns. Corrupt cache bodies and invalid mutations fail closed before publication.

## Costs and failures

Same-language delivery makes no model call. Other languages use the dedicated
`world_message_translator` configuration and the ordinary account/instance spending
guard and token tracker. The sender explicitly accepts this cost in the composer.
No automatic retranslation follows a language change. The recipient can explicitly
request a missing variant using their own consent, quotas and fresh attempt ID.
A completed variant is reused without another model call. The original is retained as
an explicitly labelled fallback; a failed translation is never presented as one.

Each accepted attempt has one durable claim before provider I/O. At most one paid
pending attempt per account and two for this world may run. A SQL-fenced FIFO
wait holds at most five pending acts and expires after twenty seconds. Work beyond
that bound is refused promptly. An accepted manual send starts its asynchronous work immediately.
Request disconnect does not create a second attempt. Provider timeout, cancellation,
worker death, unreadable ownership or uncertain completion never automatically retry.
The UI can re-read status with the same ID; it cannot silently resubmit a new ID.
Only verifiably bounded native client transports may perform this single attempt.
An unsupported transport fails explicitly before spend.
The SQL record is reserved before Redis staging and becomes dispatchable only
after the content write is acknowledged. A worker disappearing cannot strand a
permanently pending status: the owned read projects uncertainty at its deadline.

No SQL lock is held while a model runs. The model timeout is bounded. Late output
is validated and published only under the original actor/session/epoch authority.
Native quota accounting is retained; it is not represented as an atomic reservation
of the deployment's global budget. Tokens already spent cannot be refunded by a
delivery revocation. No message text is written to logs, traces or metric labels.

## Qualification

Behavioral tests must cover Unicode/byte bounds, forged recipients, hidden homes,
both block directions, expired leases, stale controller/epoch, session revocation,
duplicate and changed IDs, competing claims, Redis/SQL loss, cancellation and late
provider completion. Translation tests use an inert supplier to verify one call,
native quota/accounting ownership and no implicit learning. These are not evidence
of real supplier linguistic quality or real Pi/phone capacity.

The native browser journey sends between two inert accounts, verifies target-language
presentation, confirms a third account sees nothing, and exercises mobile/landscape
composition, focus and a failed translation. SQL/Redis simulations cover expiry,
revocation and retained-history ownership. All languages follow LIA's
existing locale catalogue and fallback rules.

## Owner clarification: conversational experience

Status: required next-stage presentation; current transport qualification does
not establish acceptance of this experience. Conversations with LIA and people
should feel welcoming and remain connected to their visible participants.

Selecting an actor offers a clear contextual conversation action. Show the
interlocutor and channel throughout composition; changing selection must never
silently retarget a draft. Use a restrained conversation dock on desktop and an
adapted sheet on phones, with an accessible history, unread cue and a clear way
to return to the scene. Preserve scroll position and drafts within their existing
authorized lifetime. Do not let typing, IME composition or the software keyboard
move the avatar or obscure the send control.

Short dialogue cues can be anchored to the interlocutor in the local scene; any
message text is visible only to its authorized reader, never put into shared
world state or broadcast to nearby avatars. LIA retains its expressive eyes and
mouth and its own native conversation state. Human exchanges remain separate
from assistant history and learning. Sending, delivery uncertainty, translation
pending/unavailable and unread states must remain understandable; do not invent
read receipts, typing activity or successful delivery without a supporting
protocol. Closing a panel does not implicitly cancel or repeat an accepted act.

Verify actor-to-conversation entry, recipient switches with drafts, private cues
with a third account, translation and reconnect states, keyboard/IME behavior,
focus return and mobile software-keyboard geometry. Conversation polish changes
presentation, not authorization, retention, consent or billing contracts.
