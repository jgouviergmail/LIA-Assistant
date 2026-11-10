# ADR-372 — What LIA does from the Tools: a click, a call, a proposal

**Status**: Accepted, 2026-11-06.
**Date**: 2026-11-06

**Amends**:
[ADR-369](ADR-369-Workbench-The-Persons-Own-Door-To-Their-Services.md) — what a person does by hand
in the Tools still involves no model; what a click asks of LIA lives beside it.
[ADR-272](ADR-272-Every-Platform-Paid-Token-Answers-To-Both-Ceilings.md) — a text readout answers to both
ceilings before a paid voice speaks.

## Context

The Tools were built as the person's own door: mail, calendar, tasks, contacts, files and lights, by
hand, with no model. Their only bridge to LIA was « Ask LIA », which dropped a sentence in the chat.
The specification of 2026-10-30 announced assisted actions from the same screens as the next step,
and the owner asked for them on 2026-11-06, with one constraint that outweighs the others: the
screens, a phone's above all, are already full, and an assist must serve the person without costing
the page its legibility.

Everything a person would want already existed somewhere in LIA: the digest, the reply writer, the
attachment reader, the readout, dictation, routines, tickets, spaces. What did not exist was a way
to reach them from a click without turning a screen that promises « what you click is what happens »
into a chat in disguise.

## Decision

### 1. An assist is one click, one call, one proposal

A click asks LIA once, on one thing, and the answer is words the person reads or a form they check.
**An assist never writes to a provider**: nothing is sent, created or saved until the person does it
by hand, through the same routes as ever. That is why no assist files an effect in the register:
there is none. What a model read is filed as a consultation, the turn as a decision, the spend on the
account: an assist is an act of LIA, traced and billed to the person who clicked (owner, 2026-11-06).

### 2. `domains/tool_assists/` is its own bounded context

`domains/workbench/` keeps no model in its path, as ADR-369 promised, and imports nothing from here.
The assists call the workbench's doors for what they read, and the assistant's own writers where
they exist, so the two never disagree and never pay twice: a mail summary is the digest, in its
cache, under its key.

### 3. One door

`door.py::run_assist` is the only way in. It asks both ceilings before anything is read (ADR-272; a voice asks them itself: a free engine answers to none),
captures the spend and bills it whatever happens, files what was read on the same run, counts the
outcome under closed labels, and turns every failure into the workbench's refusal vocabulary.
Nothing retries: a model that failed is said, and paying again is the person's choice (ADR-221). No
session is open across a model's answer (ADR-304). An answer served from what was already held
opened nothing and cost nothing: it files nothing and carries no usage.

A file is read by what it is, so the slot that answers is known only after reading: `AssistRun.slot`
moves to the vision slot, and the bill reads it at the end, on success and on failure alike.

### 4. Discretion is a rule, not a preference

**No control is added to a screen that has no room for one.** The icon that ended every bar now opens
a list: what LIA can do first, what is left for later next, the question to the chat last. In a form,
the icon stands in a line the form already has: a field's label line, the composer's format row,
inside the quick add. A panel takes no room until it is asked for. On a phone the page's triage waits
behind « Filters » with the other chips, and an attachment's row keeps the width it had: one icon
stands where the drive's did. A search's icon appears only once the box holds a sentence.

What the page does not add in room it adds in meaning: every one of these icons is the same yellow
stars (`AssistStars`, owner 2026-11-06), a fixed palette whatever the accent, so one sign says where
LIA can help. Only the stars take the colour, and the contrast guard measures them on every ground.

### 5. What a model answers is held to what the screen can take

A form is the review, so the answer goes straight to it, but a value it cannot read is left out,
never guessed at (ADR-310): a day the page cannot understand would read as today. Asking for nothing
is a refusal, never an empty form. Where a value claims a source, the source is checked, not trusted:
a contact's proposed phone number reaches the page only if the cited message holds its digits, word
for word for anything else. What refuses invention is structural (ADR-343). A contact's messages are
read whole, from their HTML turned into text, because the assistant's own body leaves the signature
out (ADR-287): that is the one reader of a display contract outside the reader, and no markup reaches
a model.

Words from a third party reach a model wrapped as external content. A passage addressed to an
assistant is neither obeyed nor mentioned: measured on the real models, asking the model to report
such a passage made it comment on itself.

Amendment 2026-11-07 (owner): one door, and an act read whole. Every act LIA reads in a message
stands under « Ask LIA » alone: « … » keeps its plain task and event, named after the message with
no model, only where the assists are switched off, as the one way left. What LIA reads for a form
is read whole: whom the message went to and the names of its files reach the model with it; a task
is read against the person's lists, which the page sends, and is important only when the mail says
it is urgent; an event's guests are the sender when the mail proposes or confirms the meeting with
the reader and the people it names with an address, never the mailbox's own, which is filtered after
the model rather than asked of it; a video call is proposed where the mail asks for one and gives no
link, never where its place already holds one. The summary's « make a task » reads the message again
for that one action (`focus`), its words wrapped as the message's own. A task handed to the Tasks
tool opens a form that shows every value before anything is added: the quick add it used to land in
saved a day and notes nobody saw. An instruction can be said as well as typed, in every box that
takes one.

Amendment 2026-11-07 (owner): a new contact is written with LIA too, from a photographed card or from
a sentence typed or said (`/contacts/from-words`). A value said is a value heard: a contact's value
reaches the form only when every word of it was in the sentence, a number by its digits, case and
accents aside (`said_in_words`), so a dictated « arobase » address passes and an invented one never
does. The notes of a contact have their writing helper (`contact_notes`).

Historical amendment 2026-11-07 (selection scope superseded by the 2026-11-09 amendment below): a passage selected in what the person reads is acted on beside it.
The chat's selection toolbar sends its acts to the chat; in the Tools the answer stays in a small
bubble by the passage, so the person keeps their eyes on the message or the file. One call per act
(`/text/passage`: explain, translate, simplify, ask), the passage sent by the page and wrapped as a
third party's words; in a message a task or an event is read for the passage (`focus`). The original
layout keeps its isolated frame, which the page cannot select in: « Act on a passage » turns the
message to its text. See [TOOL_ASSISTS.md](../technical/TOOL_ASSISTS.md).

### 6. A switch, and what a demonstrator keeps

`PlatformCapability.TOOL_ASSISTS` is on by default on an instance and off on the public demonstrator.
Off, every line served under `/tool-assists` leaves, « Keep in a space » and reading aloud with those
that need a model, because the router is the ability; the person's other acts stay.

## Acts of the person

Some lines call no model and are no assist: « Remind me », « Ticket for LIA » (a ticket for the board,
ADR-276), « Keep in a space » (the space's own upload, ADR-291), « Tell me when they reply » (a
`mail_match` routine, ADR-281) and « See the minutes » (the meeting filed on the event, ADR-258). They
share the list because a person looks for them there, and file what those features always filed.

Since 2026-11-07 « Block a slot in the calendar » joins them on a task: the calendar's editor
opens on it, nothing is created until the person saves. « Write to the guests with LIA » and
« Send by mail with LIA » open a message on « Write from an instruction »: a model runs only
when the person writes one.

## Reading aloud

`POST /tool-assists/read-aloud` reads the words on the person's screen: no provider is read and no
model runs. The readout it reuses asked no ceiling before a paid voice spoke, on the briefing as well:
`synthesize_user_text` now does, and a closed ceiling reaches the briefing as a refusal, never as an
internal error. A player the person holds stands in the reader, because a phone may refuse to start
audio by itself once the synthesis took a while.

Dictation is the chat's own recorder, mounted only once the person pressed: mounted earlier it would
hold a connection for every field. The server already bills a remote engine when it transcribes.

## Consequences

- A second bounded context reads the workbench's doors: a new read there is available here, and a
  refusal added there must keep its stable word.
- `tool_assist` is a new slot, seeded from `email_digest` (migration `c8e4a1f27b53`); `vision_analysis`,
  `email_digest` and `emails_agent` keep their own administrators' choices.
- An assist costs money the person did not see coming when they opened the page, so what it cost is
  always said: beside the answer, in a toast when the answer leaves for a form.

## Measured

On production's models, on the proof account, for about 0.03 EUR in all: the summary of a message
then its cached second click, every writing helper, the reading of an event in another time zone, a
scanned PDF and a photographed card by sight, a conversation with an injected order, a mailbox page
weighed then weighed again for nothing, a contact completed from a message quoting someone else's
signature. Each answer was read, the ledger, the decision and the consultation each proved by query.


## Amendment — cross-application selection proposals (2026-11-09)

The assist capability now stands independently of the Tools capability for words
supplied by the person. Source-specific reads retain both gates. Reading and editing
selections share one typed action door and one accountant; creation actions propose
native form values and perform no write. A memory proposal retains explicit quotation
attribution and is embedded only when saved. The full request is budgeted before a
model call; an oversized proposal is refused rather than silently cut. SSE waiting
comments carry long configured calls through idle proxies, ending in one typed
result/refusal. No timeout or disconnect triggers a second generation. See
[the implementation contract](../technical/TOOL_ASSISTS.md#cross-application-selections-2026-11-09).

The browser now shares one account-owned selection engine across read-only and editable
DOM text, including nested modal readers. Native replacement preserves the editor's events
and undo; a revision change refuses replacement. One observable handoff supplies existing
creation forms, including memory settings, without putting source text in URLs or storage.
A busy form retains its edits; the proposal waits. The person alone saves. Opaque frames,
canvas and secret fields are excluded; original mail offers its existing text view.

The selection follow-up keeps translation explicit: suggested languages and free entry
feed the existing translation assist, never an implicit account-language target. Format
is one more rewrite intention. The owner's later menu revision removes dictation from
the generic editing menu. The later caret clarification keeps a distinct compact Dictate
control on a focused editable field, including an empty one, gated by STT and browser
support. Its recorder mounts only after the click and retires with its source, account,
route or focus. Native insertion preserves undo; a refusal keeps the transcript copyable.
Dedicated dictation controls elsewhere retain their existing ownership and review behavior.

Native touch release is independent evidence that a selection gesture finished: it retires
orphaned touch pointers when WebKit consumes their terminal event, never a held mouse or pen.
Both lifetimes are observed, so pointer cancellation alone cannot expose a menu while the
finger still extends its selection. Capture-phase selection observation includes native
field events. This is a gesture contract, not a browser-version heuristic.

Reading gains the existing TTS door, a faithful passage summary and the existing unsent
chat-draft handoff. The audio resource is released when its bubble closes. Reminder and
ticket actions propose values in the account-owned native forms; they never create or
assign records themselves. A reminder's proposed schedule uses the actual recurrence
engine and consumer limits; missing temporal information opens an incomplete form,
without an invented hour. Ticket constraints remain reviewable in its description.
Internet remains between Translate and Task in the owner's declared action order.

Internet is a distinct accounted assist: one model prepares a bounded query from the
whole external passage, then one existing search client returns attributed sources. It
prefers a connected Brave service, then Perplexity, otherwise available Wikipedia; it
never retries through another provider after failure. The web-search switch is checked
before both phases, and connector authority is rechecked before lookup. The existing
consultation surface declares the actual provider, including failed/abandoned reads.
The model's platform spend and a search service's personal-key billing remain distinct.
The bubble presents source links without fetching them or executing their markup.
