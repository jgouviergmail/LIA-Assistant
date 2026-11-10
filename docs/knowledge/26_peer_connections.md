# Peer Connections

## Sharing a skill, MCP server or plugin

Use **Share with a connection** on your own settings card, choose an accepted
peer and confirm the preview. They receive their own copy, installed disabled,
with a badge naming you and the sharing time, and LIA tells them in their chat
who shared which kind of capability and its title. They can edit, activate or
delete it independently. Credentials stay private: the recipient supplies their own.
Once enabled, a shared skill has the same execution capabilities as one the
recipient authored, under their connector permissions and ordinary approvals.
See [the implementation contract](../technical/PEER_CAPABILITY_TRANSFERS.md).

## How do I connect with someone?
Both of you enable **discovery** in Settings → Connections (it is off by default), then one searches the other's **exact full name** — your own searchable name is shown in the section with a copy button. Send a request (with an optional note); the other person accepts or declines in one click, from the chat card or the settings.

A masked email fragment (j…@g….com) helps tell homonyms apart. Nothing else is shared by connecting.

## How do I send a message to a connection?

Tell LIA, for example: *tell Marie I am running late*. The message is **queued directly, without a confirmation card**. An ambiguous recipient still needs clarification. The recipient’s assistant then conveys it in its own voice and language, naming you as the sender. Being queued does not mean it has been delivered. The small AI cost belongs to the sender; connection, block, length and daily quota checks still apply. Replying sends a new message.

## Can I name a connection by their first name?
Yes. Asking about a connected person — their availability, their tasks, or a message to relay — a first name is enough when it designates **one** of your connections ("is Marie free tomorrow?").

When several connections share it, or when it also designates someone in your **Relations** who is not connected, LIA asks which one you mean instead of guessing — and reads nothing until you say. When it designates only people who are not connected, LIA says so and answers from your own sources instead. Its answer always names the person it read, so a mix-up shows at once. Merging two cards on the Relations page never makes a nickname select a connection.

## What can I share, and what does the other person see?
Per connection, you choose **read-only** shares:
• **Calendar** — free/busy only, or slots with event titles
• **Tasks** — pending task titles only

Nothing is shared by default. Both directions are visible to both sides in the Connections section, every access is re-checked at the moment of the read, and recorded in an **access log** you can consult. You can change or revoke a share at any time.

Once a calendar is shared, you can simply ask LIA: *is Marie free tomorrow at 10?* LIA reads the calendar **Marie chose as her default** — not an arbitrary one — and gives you the hours on **your own clock**. All-day entries (a birthday, a reminder) are listed apart from real meetings, so they never make someone look busy all day.

If the other person's own connection to their calendar has broken, LIA says exactly that — a temporary fault on their side — instead of claiming they share nothing.

## How do I block someone, and what do they notice?
Block from the chat (under a relayed message) or from the Connections section, with a confirmation.

Blocking **ends the connection silently**: the other person is not notified, can no longer find you in discovery, and any message they try to relay quietly goes nowhere. Unblocking does not restore anything — you would have to reconnect explicitly.

## Can someone find me without my consent?
No. Discovery is **opt-in and off by default**. Search only matches your **exact full name** (accents and case are forgiven, but there is no partial or fuzzy search), and without a full name on your profile you are unfindable.

Blocked, unknown and declined targets all receive the exact same neutral answer, so nobody can probe whether you exist, declined, or blocked them.

## What happens when I remove a connection, or delete my account?

Removing a connection immediately ends its shares and both assistants inform their users. Each person sees only their own side of relayed messages: the sender’s instruction or the recipient’s delivered text. These texts expire after the configured retention period; the record remains for dates and counts. Your export includes your connections and shares. Deleting your account removes its peer records.

## How do I share a generated image with a connection?
On the card of an image LIA generated for you — in the chat as well as in **Settings › Preferences › My generated files** —, tap **Share with a connection**, pick the person and add a comment if you like. The click is your confirmation: no model is involved.

**📥 What they receive:**
A copy of the image, filed in their own gallery as if they had generated it, with its own retention period, and a bubble in their chat carrying the image, your name and your comment — quoted exactly as written, never turned into a link or a hidden image.

**🔒 The rules:**
• Only your own generated images can be shared, with an accepted connection and no block between you
• It is a copy: deleting your image does not remove theirs
• A daily limit caps sharing, for you and for each connection; the message tells you when to try again

## How do I send a skill, MCP server or plugin to a connection?

Use **Share** on its settings card, choose an accepted connection, review the package and confirm. The recipient receives an independent copy, **disabled by default**, with the sender and sharing date/time. Credentials and permissions do not transfer. They can edit, configure, activate or delete it through the usual controls. Once enabled, a received skill has the same execution capabilities as one they created, so review it before activation. Later changes at the sender do not update the copy.

A notice confirms the share once the copy is installed — or says why it did not complete, and the dialog stays open to retry. LIA tells the recipient in their chat who shared which skill, MCP server or plugin with them, and its title.

## Can I see whom I shared a capability with, and share it again?

You can see it: under the rule of each skill, MCP server or plugin card, a folded
**Shared with** list names each connection that received it and when, marked
“incomplete” when part of it could not be installed. A copy you received shows
**Shared by**, with the sender and the date, in the same place. For now a share is
final: the share window no longer offers a connection that already received it.
