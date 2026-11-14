# ADR-369 — The workbench: the person's own door to their connected services

**Status**: Accepted, 2026-10-31.
**Date**: 2026-10-31

**Amends**:
[ADR-263](ADR-263-Execution-Authority-Chain-And-Effect-Register.md) — the registers record what
LIA did; an act the person does by hand in the workbench is no act of LIA, and every module that
opens a client for it is declared as such (`NOT_A_CAPABILITY_READ`, decision D5).
[ADR-304](ADR-304-No-Transaction-Across-A-Network-Call.md) — the connector door gains
`open_client_by_type` (Drive, the Hue bridge: no category); no session is held while a provider
answers, on either door.
[ADR-184](ADR-184-Published-Bounds-And-Non-Prescriptive-Verdicts.md) — what a provider bounds is
published to the page that writes (`PROVIDER_BOUNDS`, `limits`), and a gesture a provider lacks is
refused unsent.
[ADR-287](ADR-287-Email-Content-First-Detail-Levels-Digests-And-Neutral-Message.md) — an e-mail's HTML is a
DISPLAY contract (`get_message_html`), drawn in an isolated frame and never handed to a model.
[ADR-260](ADR-260-Redis-Key-Families-Scope-And-Reset-Purge.md) — three `USER_RUNTIME` families:
`workbench:idem`, `workbench:download`, `mail:generation`.
[ADR-297](ADR-297-Drive-Folder-Is-A-Tree-And-The-Count-Is-Exact.md) — a linked folder names its
drive (`rag_drive_sources.provider`, 2026-11-05).
[ADR-261](ADR-261-Push-Driven-Heartbeat-Wake-And-Incremental-Drive-Sync.md) — Graph's delta feed and
subscription ride the same drain (2026-11-05).
[ADR-268](ADR-268-Generic-Recurrence-And-Reminder-Management.md) — an event repeats on the one
recurrence engine (2026-11-05).
[ADR-288](ADR-288-Independent-Drafts-Reviewed-One-At-A-Time.md) and
[ADR-289](ADR-289-Draft-Surfaces-Drawn-From-One-Description.md) — three more draft types
(`EVENT_ANSWER`, `FILE_SHARE`, `DOCUMENT_REPLACE`, 2026-11-05).

## Context

A person connects their mailbox, calendar, tasks, contacts, Drive and Hue bridge so the assistant
can act on them. Until now the only door onto those services was a conversation: to check what LIA
did, tidy a mailbox, move a meeting or switch a light off, the person asked a model. That costs
tokens, takes seconds, and is not deterministic. The design (2026-10-30, owner decisions D1–D6)
asked for the opposite: a section « Tools » where the person consults and acts **by hand, with no
model in the path**, at the provider's own latency, doing exactly what was clicked.

## Decision

### 1. A REST bounded context, no graph, no model

`domains/workbench/` serves six tools under `/workbench` — mail, calendar, tasks, contacts, files,
lights — one router per tool, mounted by `router.py` behind the capability
`PlatformCapability.WORKBENCH` (route-enforced, family `work`; off on the demonstrator, whose
connectors are closed). No route calls a model, opens a `TrackingContext`, or writes a decision
row; nothing is learned from what the person does.

`GET /workbench` publishes, per tool, one of four states — `ready`, `not_connected`,
`reconnect_required`, `unavailable` (the instance withholds the provider) — with the active
provider, its features and its bounds, and the section's `limits`. A tool whose connector is not
connected stays drawn, under « To connect » (D6); a tool the instance switches off is not.

### 2. One door, one failure contract, one vocabulary

`clients.open_tool_client` opens a tool's client through the category door (`open_active_client`)
or, for Drive and the Hue bridge, `open_client_by_type`; either way the connector session is
closed before the provider is asked. Every provider call runs inside `calls.provider_call`, which
turns a client failure into ONE stable refusal by its type and answered status — never by its
words — knowing whether the call was an act (a lost answer to an act is `outcome_unknown`, never
« unavailable »), and counts it under closed labels. The codes (`errors.py`) each carry a sentence
in six languages on the page.

Identifiers travel in the query string or the body, bounded and pattern-checked (`ids.py`), and
every client that puts one in a URL path quotes it as ONE segment
(`connectors/clients/path_segments.path_segment`; a segment of `.`, `..` or nothing is refused
before any request, since the HTTP client folds it away).

### 3. One provider per category, and a descriptor of what it accepts (D1)

`features.py` declares, per connector type, the gestures its client accepts (read state, labels,
drafts, all-day events, conferences, attendee notification, occurrence edits, multi-valued
contacts, groups, exports…) and the bounds it imposes (`PROVIDER_BOUNDS`). The page offers only
what the descriptor says; a gesture outside it is refused unsent (`not_supported_by_provider`).
A boot assert refuses a connector type of a workbench category with no entry
([ADR-085](ADR-085-Draft-Display-Registry.md)'s completeness rule).

### 4. Parity, and the assistant gains what the clients gain (D2)

A gesture one provider's client has exists for the others, and whatever the clients gain for the
workbench reaches the assistant's tools in the same lot:

- **read state** on the three mail clients (`mark_read`) and a provider-neutral
  `set_email_read_state_tool` (`reversible`, no confirmation);
- **all-day events** on the three calendar clients and `all_day` on the calendar tools, their
  manifests and the confirmation card;
- **multi-valued contacts** on the three contacts clients — a typed list sent REPLACES that list,
  one left out is KEPT — and an `update_contact_tool` that no longer drops a contact's other values;
- **contact listings in family-then-given order** on the three contacts clients (2026-10-31): the
  assistant's listings read the same order;
- **calendar ids as path segments** and attendee notification on an update (`send_updates`, Google;
  Graph notifies on its own, CalDAV cannot);
- **Drive**: file ids as path segments, every value in a `q` expression escaped as Drive's grammar
  asks (the backslash before the quote), a search paged by Drive's cursor, and no `orderBy` beside a
  full-text term (Drive refuses it — the assistant's full-text search failed on every call).

A display-only contract (an e-mail's HTML) reaches no tool: a model reads text, never markup.

**Whoever reads a person's tasks reads ALL their lists (owner rule, amendment 2026-11-10).** The
list a tasks connector's settings name as the default is where a NEW task goes when the chat names
none, and nothing else. The Tools' views across the lists and the home's card came first; the
assistant's tools, the heartbeat and the radio's journal followed in the next lot, through the one
walk (`connectors/clients/task_lists.py`: a few lists at a time, a failed list named, a cut stated,
and « no task » never told on a list nobody could read — `EveryTaskList.tasks_or_failure`). Three
defects were measured on the way and are closed by `agents/tools/task_list_scope.py`:

- a list the model names, by its id or by its name, is THAT list or a refusal
  (`INVALID_INPUT`, pointing at `list_task_lists_tool`): the list's own id was looked up as a name,
  found nowhere, and silently became the provider's default list — a task created where nobody
  asked;
- an act on a task that exists runs in the task's OWN list: the one named, else the one the
  conversation last looked it up in (each task read carries `tasklist_id` and `taskListName`),
  else the one that HOLDS it — every list is asked, the default one first
  (`find_task_lists`; measured on Graph, a list answers 400 for another list's task and 404
  for an id nobody has). A task no list holds is refused (`INVALID_INPUT`), never acted on in
  a list picked for it, and a list that could not be asked is never read as not holding it;
- the creation card says which list the task goes in, and `list_task_lists_tool` gives each
  list's id and name in `structured_data`, the default one marked only when it is known.

The Tools' tasks screen follows the same rule: an address that names nothing opens on « All
tasks » (`useTaskPlaces`), not on the default list; a task named without its list is the one
case still looked for there.

Two readers followed on the owner's explicit decision the same day, each keeping what makes it
what it is:

- **a PEER's tasks** (`get_peer_tasks_tool`, amending ADR-182 §D1ter): every list of theirs is
  read — their default list is where THEY create a task, not what they share. What leaves stays
  what the share level names: the TITLES, the most pressing first, never a list's name. The
  share's label and the FAQ say « every list », so the person sharing reads what they open;
- **the discussions' tasks source** (`connectors/discussion_tasks.py`): each list is its own
  CONTAINER, so a task's reference is minted under its list's scope and read back there only
  (a reference minted under the provider's alias, before this, is still read). The read's
  physical-call budget bounds the lists read (`DISCUSSION_READ_CALL_LIMIT` − 1: one call lists
  them, one reads each) and a page that could not cover them all is `truncated`. A provider's
  failure stays the READ's failure, never a list set aside: the gateway's backoff depends on it.

**An instant is the same for both providers** (same amendment). Measured on Graph: a To Do
`$filter` refuses a numeric offset (`…T00:00:00+01:00`, HTTP 400) and accepts the same instant in
UTC. The radio's journal sent local midnight with its offset: its two tasks readers had never
read a To Do account. `MicrosoftTasksClient` now sends the three filter instants in UTC
(`_filter_instant`); Google is handed them as given.

### 5. An e-mail's HTML, isolated (D3)

`get_message_html` on the three mail clients follows one rule: every `text/html` part in document
order, joined, leaving out a part that carries a file name and anything inside an attached message;
charsets honoured. The page draws it in an `<iframe sandbox="" srcdoc>` — no script, no form, no
same origin — whose document opens with its own Content-Security-Policy, a `no-referrer` policy and a
light colour scheme, cut at `WORKBENCH_MAIL_HTML_MAX_BYTES` and said so. The text reader stays one
click away. Navigation attributes are removed from links, including SVG links and
links inside templates or `noscript`; a sender's base and refresh are removed too.
The browser parses under the document's policy before applying these changes,
and the reader is loaded without SSR because it uses browser DOM APIs. The walk
of template fragments is iterative, independent of sender-controlled nesting depth.

Release review, 2026-10-31: a real-browser probe showed that an explicit
`target="_self"` overrides the base target and navigates the frame to an origin
allowed by the parent's `frame-src`. An empty sandbox alone does not forbid that
navigation. Unit regressions and the hermetic original-layout browser journey
cover explicit targets, SVG, `noscript` and retained readable layout.

Amendment 2026-11-04 (owner, A1): the frame reads as a mail reads. Its sandbox gains
`allow-popups allow-popups-to-escape-sandbox` and nothing else: it stays an opaque origin,
with no script and no form. Links are no longer removed: an `http`, `https` or `mailto` address
survives, rewritten to a new tab that cannot reach back; any other loses its address. Embedded
images always show. Remote images load on the reader's click, for that one message: the sender
then sees the opening and the address. The page offers the button alone (owner, 2026-11-05); what
it tells the sender is said in the help.

### 6. No register row for the person's own acts (D5)

The registers answer « which capability did LIA use »; a person acting by hand uses none. No
workbench route files a consultation, claims an effect, or writes a decision: every module that
opens a client is declared in `effects/direct_client_callers.py` (`NOT_A_CAPABILITY_READ`) with this
decision as its written reason. Send idempotency therefore lives in Redis, not in the effect ledger:
a submission key, claimed before the provider call (`idempotency.run_once`, family
`workbench:idem`), settled `done` or `unknown` — through a cancellation too — and a replay answers
the stored outcome (`already_submitted`) instead of sending twice. Calendar creates keep the
provider's own idempotency.

### 7. Freshness after a write

Every cached read of a Gmail mailbox lives under the mailbox's **generation** (`mail:generation`);
every write through the client's request door moves it, so the next read after a trash, a label or a
read-state change is fresh — for the assistant too. The workbench itself reads with `use_cache=False`.

### 8. What each screen promises

As decided on 2026-10-31. Phase 2 changed several of these promises (the files category, Outlook's
settings, whole series, shared drives): the dated amendments below hold.

- **Mail**: folders and labels, a listing by cursor, search, a reader (text, or the isolated
  original), read state, trash, labels, compose, reply, forward, drafts, Gmail's vacation and
  filters; attachments downloaded through the download door below.
- **Calendar**: agenda, week and month over the account's days; a window is at most
  `WORKBENCH_CALENDAR_WINDOW_MAX_DAYS` days, each calendar drained up to
  `WORKBENCH_CALENDAR_WINDOW_MAX_EVENTS`, a few calendars at a time, and each answers on its own (an
  error, a cut, events whose times could not be read). Times are a wall time and a zone id, never an
  offset; an all-day end is exclusive. An occurrence of a series is edited alone where the provider
  can; a series change is refused, and said. The guests come right under the title, each suggested
  from the account's contacts while it is typed, by the matcher a message's recipients use (owner
  requests 2026-10-31: the same field as « Send by e-mail »; the calendar publishes the shortest
  query searched).
- **Tasks**: lists and tasks by cursor, completion shown at once and rolled back on a refusal.
- **Contacts**: the account's contacts by cursor, a search, a group and Google's « other contacts »,
  each page saying when it may hold more, every listing sorted by family then given name and each
  contact drawn « Given Family » (owner request 2026-10-31): a cursor-paged listing is ordered
  where it is paged — Google (`sortOrder=LAST_NAME_ASCENDING`) and Graph (`$orderby=surname,
  givenName`) sort their pages, iCloud sorts the book it reads whole, and the workbench sorts what
  is answered in one go (a search; a group, read whole — at most
  `GOOGLE_CONTACT_GROUP_MAX_MEMBERS`, one batch — before it is paged), all by ONE key
  (`normalizers/contact_order.contact_order_key`); typed multi-valued editing; « See the relationship » only
  when the API folds the contact's name exactly to a relation's (`name_key`, folded once by
  `fold_name`).
- **Files**: My Drive and its folders by cursor, a Drive-wide search by cursor, a breadcrumb walked
  up to My Drive under `WORKBENCH_DRIVE_BREADCRUMB_MAX_DEPTH`, a Google document exported (Docs to PDF
  or DOCX, Sheets to XLSX, Slides to PDF or PPTX), « Open in Drive » only on Google's own https hosts,
  the trash. Shared drives are not listed, and the root says so.
- **Lights**: rooms, lights and scenes, controls drawn from what each lamp declares, a brightness or
  colour committed on release. Rooms and lamps come in alphabetical order, in the reader's language
  (`inNameOrder`, applied once where the bridge is read, so the room opened by default follows it).
  A lamp's colour temperature and colour sit in one section folded until opened, its pill saying
  the current tone; the temperature comes before the colour, and the colour is the lamp's current
  colour alone — one swatch whose press opens the platform's choice panel (owner requests
  2026-10-31; the eight quick swatches and their « pressed » ring are gone).

### 9. Downloads

One download at a time per account (`workbench:download`, an owner-token claim that expires on
its own; our throttle never fails a download when Redis cannot answer), never past
`WORKBENCH_DOWNLOAD_MAX_BYTES` — refused before the body is read when the provider lists a size — and
served as a file the browser never renders: `Content-Disposition: attachment` with a sanitised name,
`Content-Security-Policy: default-src 'none'; sandbox`, `Cache-Control: no-store`, the declared type
served opaque when it is malformed (`downloads.py`, shared by mail and files).

### 10. The page

A header destination « Tools », right after « 3D » (the world); a row of the six tools ABOVE the open one at
every width — owner decision 2026-10-31: the validated vertical rail took a quarter of a laptop's
width from tools that need it, and a phone had to go back to a list screen to change tool — which
scrolls sideways on a phone and brings the open tool into view; the section opens on the first ready
tool at every width. One tool per screen; the open item rides the address (opening pushes, closing
replaces), and below `lg` it takes the list's place with the focus following it there and back.
Every screen is proven in light, dark and OLED at 1440 and 390 px.

On a large screen the person sizes the vertical panes by hand — owner request 2026-10-31: the mail's
folders and, beside a message, its list; the calendars and, from `xl`, an event's detail; the task
lists and a task's detail; the contact list; the file list (the lights are cards in a grid, not
panes). One window splitter for every hand-sized pane, the debug panel's included
(`components/ui/pane-separator.tsx`: dragged, the arrows, Home/End, Enter or a double-click to
restore), one declaration per pane (`lib/workbench/panes.ts`: its bounds and the share of its row it
may take, so the third pane of a row always keeps at least 30 % of it), and the width a preference of the
DEVICE (`workbenchPanesStore`, outside the purge registry like the dock's). A pane nobody sized keeps
its layout's own responsive widths; a kept width the row cannot hold is drawn clamped and comes back
on a wider window.

On a computer the section runs the whole window — owner decision 2026-11-04: every page stood on the
centred 1280 px rail, so a tool had 1216 px on any screen. From `lg` the page's frame is
`PAGE_FRAME_WINDOW` (`lib/dashboard-nav.ts`: no ceiling, a 16 px gutter); below `lg` it is the rail's,
and every other page keeps the rail. The dashboard layout decides it from the address the header's
active state already reads (`isActiveRoute`), so a new tool inherits it. The notice of a broken
connector takes the frame of the page under it. The header stays on the rail, as it does over the
world: following the page, its icons would move on every way in and out of the section. The panes'
responsive widths do not change, the free pane of each row takes what the window adds, and from `xl`
the lamps take as many columns as hold a 24 rem card (`auto-fill`, so that a lamp alone stays a card).
A 1280 px window gains its gutters alone, 32 px: the ceiling never applied there.

Amendment 2026-11-04 (owner): the rail itself opens, so that the interface breathes when the screen
allows it. Seen across the whole window, every screen looked stretched but the world and the tools,
which keep it; the other pages looked cramped on the rail. Its ceiling becomes half as wide again,
1920 px, and the header stands on that same rail on every page, where it had a width of its own: its
icons still never move, and its two ends line up with the page. The chat's thread and composer gain the
same half from `lg` (1536 and 1344 px), and the words of a rendered text keep a 1024 px reading width
that its tables, code and cards do not have, because the wider thread drew a long answer at 217
characters a line against 136. FAQ answers and plain-text documents take that width too. Each ceiling
is one theme token (`--container-*`, `styles/globals.css`), read by its `max-w-*` class and by the
stylesheets. None can act below `lg`, since the root rem never scales; a window of 1920 px or less is
filled by the rail, behind its 32 px gutter.

Amendment 2026-11-05 (phase 2, ergonomics): what a gesture may not do behind the person's back.
A drag sends a change at once, undone from its toast, except on an event with guests: its editor
opens on the new time with « tell the guests » in sight, and nothing leaves until the person saves,
so nobody is told by a slip of the mouse. Only an event living within one day drags, from `lg`; the
editor is the keyboard's way and the single-pointer one (WCAG 2.5.7). « Send » holds a message for
`WORKBENCH_SEND_UNDO_SECONDS` on the page, the server knowing nothing yet, so taking it back needs no
act of the provider; a screen going away meanwhile sends it, since the person pressed « Send », and
what then fails is said with a way to copy the words, which exist nowhere else. A subject never rides
an address on its way to another tool or to the chat: it is held in the page (`lib/workbench/handoff`)
or left as the person's draft (`seedInputDraft`), nothing sent. A page of a listing is never sorted
on the page: a folder's order is asked of the provider, and a list is headed by letter only where
the provider answered it in that order. The composer leaves what is behind it usable: `role="dialog"`
with `aria-modal="false"`, its focus given back.

Amendment 2026-11-05 (phase 2, reading a mail): an image the message carries is its own part, so
drawing it tells a sender nothing and asks no click. It is read apart, by the `cid:` names the page
found in the HTML, and reaches the frame as a `data:` address of an image type, under
`WORKBENCH_MAIL_INLINE_MAX_BYTES`; what is left out is counted and said. A one-click unsubscribe
(RFC 8058) is an act on a stranger's server: the message is read again rather than an address taken
from the page, the POST leaves through `pinned_stream` with the RFC's one line and nothing of the
person, and only a 2xx counts, a redirect being a new address nobody checked. An attachment is read
in the page as a drive's file is (« the owner's remarks », below).

Amendment 2026-11-05 (phase 2, sorting the mail): one contract on three shapes of a move
(`connectors/clients/mail_moves.py`). A place is a role or a folder of the person's own; Gmail moves
labels and keeps the id, Graph answers a new id, IMAP finds it by the `Message-ID` read before the
move, a header searched only when it is a plain `<…>`. Each message is answered, what became of its
id included, and a failure of the mailbox after one message moved leaves the rest unanswered rather
than hide what moved; `mark_read` now keeps that promise too. Three decisions follow from what was
measured or cannot be otherwise:

- A view (the starred, the sent, Gmail's all mail) is where a message is LISTED, not where it is:
  nothing is sent back to it, so a move from one offers no undo.
- Gmail deletes nothing for good: `messages.delete` needs `https://mail.google.com/`, which LIA does
  not hold. Asking for it would widen what every Gmail account grants for one gesture Gmail does by
  itself after 30 days; `PERMANENT_DELETE` is absent from its features and the screen says so.
- A folder holding anything is never deleted. Measured on outlook.com: `DELETE /me/mailFolders/{id}`
  answers 204 and what the folder held then reaches no folder the person can open, Deleted Items
  included. IMAP's DELETE destroys its messages too. A gesture that reads as tidying up must not be
  the one that loses mail.

The assistant gained `organize_emails_tool` and, on Outlook and iCloud, `manage_mail_folder_tool`,
each undone by one more call; deleting for good stays by hand (A2). The figures on the rail and the
pane are polled every two minutes while the page is seen, never the listings; a figure that grows
reads the listing again.

Amendment 2026-11-05 (phase 2, the calendar): an invitation is answered in three shapes
(`connectors/clients/calendar_answers.py`): Google writes the attendee it marks `self`, Graph has an
act per answer, CalDAV changes the person's own `PARTSTAT` and leaves the rest to the server (RFC
6638). `own_answer` is the ONE reading of what the person answered, the page's and the assistant's:
an organiser has no invitation, though Google lists them among the attendees. The answer leaves for
someone, so `respond_to_event_tool` DRAFTS it (`DraftType.EVENT_ANSWER`): no native tool asks through
a pre-execution card. The card names the event, the answer and who is told; « rather maybe » on it
changes the answer alone, and a word off the calendars' vocabulary leaves the card as it was.

What an event says beyond its time is one contract too (`calendar_options.EventOptions`, Google's
words the normalisers' vocabulary): a reminder, free or busy, private, each left out when nobody
said it, so a provider's own default is nobody's to overwrite by accident. The assistant reads the
same three through `agents/calendar/event_options.py`, whichever the door: a tool's arguments or a
card changed in words.

An event's zone is read where each provider keeps it, Windows' names translated on Graph; UTC is how
a provider keeps an instant, never a zone anybody chose. The form opens on that clock; a drop keeps
the account's, because it reads the view.

Dated tasks reach the calendar through one read of the server (`GET /tasks/due`), never one request
per list from the page: the lists are asked a few at a time, and what could not be read, or was read
in part, is said.

Moving an event and managing calendars are the person's own acts, by hand. Google moves an event by
name. Graph has no such act and CalDAV none its servers share: the event is copied, then the
original removed, last, so that an event is never lost. A copy would reach guests twice and break a
series, and on Graph lose attachments: those are refused before anything is sent, and a copy whose
original stayed is said to stand in both (`event_left_behind`), never left to be found. Measured on
outlook.com: a new id, the original gone, notes, place, reminder, free and private kept, the event's
own zone lost, its instants right. ONE door decides which calendars may be renamed or deleted,
whatever a request names (`manageable`, from the listing): the account's main calendar and those
shared with the person are touched by no request. A name a calendar answers to is refused for every
provider, because iCloud finds a calendar by its name.

Amendment 2026-11-05 (phase 2, the files): one contract, two drives, and three things only Graph
makes hard. `files` is a category like the others, exclusive, and `FilesClientProtocol` the one
contract: OneDrive speaks Drive's words at the client boundary (`onedrive_normalizer`), so the
screen and the assistant name no provider. `manage_files_tool` organises and `share_file_tool`
drafts; `drive_tools` resolves by category.

Graph answers a copy 202 and works on it alone, and `conflictBehavior` is documented unsupported on
OneDrive Consumer: a name a folder already holds would fail where nobody hears it. So a copy and an
upload read the target folder first (`_name_must_be_unused`), a PUT on a path otherwise replacing
what is there, and a copy is said as under way, never as done: nothing polls the monitor, and a
failure Graph finds later (a quota) stays unheard. What OneDrive refuses in a name is refused
before anything leaves (`name_refused`), from one constant the tool's wording reads too.

A view is what a drive keeps across its folders. It stands nowhere, like a search: nothing is
created or sent there, and the walk of a move starts at the top. Drive lists a shared drive as a
folder, so the screen opens one with nothing of its own; every Drive call says it can reach such
items (`supportsAllDrives`), or Drive answers 404. OneDrive offers no view: `sharedWithMe` and
`recent` are deprecated, its recycle bin cannot be listed, and SharePoint libraries need a scope and
a work account nobody here can prove them on. `restore` exists on OneDrive Personal alone, so
**Undo** is offered on both drives and a work account's refusal is said.

Deleting for good and emptying the trash stay the person's own, after a question (owner decision
A2): no tool does it, a guard says so. Sharing tells a third party, so the assistant drafts it
(`DraftType.FILE_SHARE`), and the page's own act runs once per submission. A link anyone can follow
and taking an access back stay on the page. A file sent by the assistant is one LIA holds under a
name the model can read, from the attachment hint or the generated-files lookup: no id is carried,
and its row is read on a session closed before anything leaves (ADR-304).

A preview takes the account's one transfer, now shared by what goes down and what goes up
(`one_transfer`), because a client holds the file in memory; what it serves is told under « the
owner's remarks », below.

A file of the drive leaves with a mail as a third source of `outgoing_files`' caller, read when the
message leaves and stopped the moment their total passes what the provider carries.

Amendment 2026-11-05 (phase 2, composing): one answer, measured on a real mailbox, and four things
a composer must not lose. Graph answers 202 to `forward` with `ccRecipients` beside `toRecipients`
and copies nobody, in silence: a copy rides on `message`, as attachments do. A reply's recipients
are read when the person answers (`GET /mail/reply-recipients`), never with the message, because
the mailbox's own address costs a call the reader has no use for; the rule is the clients' own
(`reply_recipients`), and from then on what leaves is what the person sees. Nothing read, the
provider computes them as it always has.

A file of the device is kept first (`keep_device_file`), as any upload and under its deadline, then
rides like the person's other files. The chat's door takes what a model reads; a message carries
anything, so its type is what its bytes say and only then what its form declares, and an SVG is
served as a download everywhere, being a page that runs scripts.

A draft holds files through one contract on three shapes: Gmail and iCloud edit the raw message
(`edit_draft_message`), Graph writes each on its own resource. They leave by name, the one handle
that lasts from one read to the next (ADR-296). A quiet composer saves by itself after
`WORKBENCH_DRAFT_AUTOSAVE_SECONDS` (`0` switches it off), so most new messages reach « Send » as a
draft: a send waits for the save on its way, and reads the fields and the last save as they stand
then, or a file already on the draft would join it twice. A draft reopened is edited as text:
changing it takes its formatting with it, never its files.

A signature belongs to the mailbox, in its connector's encrypted preferences, on the three
providers. `free_text_fields` declares it: it keeps its lines and quotes, which a preference that
reaches a prompt never may. One door reads it (`mail_signature`), from the database alone, for the
composer and the assistant, which adds it to the body its card shows (owner decision A3). The
delimiter lives there too: the page is given the block to append.

Formatted words are a stranger's HTML to the server: `html_body` REBUILDS them from an allowlist on
one pass of the standard library's parser, so a mark nobody thought of never passes, and what holds
code goes whole. `lxml_html_clean`, already a dependency, says itself it is not for hostile input.
No editor library: `contenteditable` keeps typing, undo, Ctrl+B and input methods the platform's,
and sixty packages for five gestures are not worth their surface. A paste arrives as words. A
formatted reply is the message's whole body on Graph, which refuses a comment beside it, so the
original is quoted there by the rule Gmail and iCloud use (`quoted_reply`, `forwarded_body`), as
words: what it holds is escaped, never run as a page.

An alias is Gmail's alone (`send_as`): it rewrites a `From` it does not know in silence, so the
address is read against `sendAs` first, and refused elsewhere rather than accepted and dropped. It
is stamped in the two doors every Gmail message goes through (`_send_message`, `_save_draft`), the
second because of the first paragraph above: a new message usually leaves as a draft.

The assistant gains what the screen gained: `file_names` and `drive_file_ids` on `send_email_tool`,
`reply_email_tool` and `forward_email_tool`, named on the card and read when the message leaves
(`email_files`), the copies of a reply, and a forward that works where it never did: it read a
Gmail tree Outlook and iCloud do not have.

Amendment 2026-11-05 (phase 2, conversations): what makes a conversation differs, what a reader
gets does not (`mail_conversation`): headers alone, oldest first, the newest kept, the cut said,
drafts left out, and no total. Gmail reads a thread. Graph needs the conversation's id and a sort,
and answers 400 to the pair unless the sorted field leads the filter (measured on a real mailbox):
a date bound that excludes nothing leads it, and `isDraft eq false` stays inside the query, where
a draft cannot take a place of `$top`. IMAP keeps none: `References` starts with the message that
opened the conversation, so that id names it (`conversation_opening`), and a search for it in the
message's folder, the inbox and the sent folder finds the rest. An id is read only if a search can
carry it: a stranger writes these headers, and IMAP's criteria leave in US-ASCII.

The band stands under the reader's toolbar, outside the message: it does not move the words, stays
while the next message loads, and keeps the focus on the link it was on, so every row is a link,
the open one included. It is read once the message landed, so the message never waits for it, and
kept while the person walks it (`conversationAnchor`). The list can draw a conversation as one line
under its newest message, by what is LOADED, so no line claims how many messages it holds. A
selection ticks lines and an act takes the messages they stand for; a star goes to the newest
message and comes off all of them. The plan said Gmail and Outlook alone. iCloud's listing reads
headers anyway, so nothing proved it impossible (D2), and no capability is needed.

`get_emails_tool` takes `whole_conversation` beside `message_id`, under the one bound that caps a
batch of ids, and the cut reaches the model beside the items. A message in the trash stays part of
what was said on Gmail and Graph, which hold it in the conversation; iCloud's search does not read
that folder.

Amendment 2026-11-05 (phase 2, tasks): To Do answers 200 to two requests that change nothing, so
a write is proven by reading back. A PATCH of `parentListId` moves no task, and `isReminderOn:
false` leaves the reminder on: `reminderDateTime: null` takes it off. `/move` answers 400: a task
goes to another list as a copy, its original removed last, so it is never lost, and one left in
both lists is said (`TaskLeftBehindError`, a status of its own in a selection's answer). A copy
keeps the importance, the categories, the body, the steps, the status and the completion date;
it takes another id, which the answer gives.

To Do alone keeps steps, an importance, a reminder and a repetition; Google alone keeps an order.
Each is a capability of the descriptor, refused unsent elsewhere, and Google's client refuses what
it would drop rather than drop it. A repetition is one word on the screen (`repeat_of`): a pattern
the word cannot say stays `custom` and is left as it is. It starts on the task's due day, and
taking that day away takes the repetition with it (measured).

Clearing what is done DELETES it on both providers: Google's `clear` only hides a task from a
listing, and the screen's completed listing asks for the hidden ones. A view gathers what every
list holds for one stretch of the account's days. Reordering is up and down in the detail, which
WCAG 2.5.7 asks for whichever way a drag would go. The assistant gains `rename_task_list_tool`
and `move_task_tool`, each undone by one more call, and writes To Do's details through its drafts;
on Google it is told so before any confirmation.

Amendment 2026-11-05 (phase 2, contacts): a contact's given and family names, job, website and
birthday go by one write contract on the three providers (`clients/contact_details`): left out a
field is kept, an empty text empties it, a birthday goes by a flag. A company and a job share one
Google entry and one vCard card: writing either keeps the other. Google derives its display forms
from the parts, so they never go back beside a changed part; Graph derives its display name too
(measured). A birthday with no year stands in 1604, as on Apple's and Microsoft's own, and is read
back as none on all three; the screen shows it, removes it, and writes none.

A contact leaves and arrives as a vCard through one door (`normalizers/contact_cards`). An export
reads up to `WORKBENCH_CONTACTS_EXPORT_MAX` a page at a time, its cut said in the file's name, the
only channel a download has. An import takes `WORKBENCH_CONTACTS_IMPORT_MAX_CARDS` cards, once per
submission, one at a time, as Google asks of mutations for one person, within one request a
proxy's timeout still answers; it answers card by card, and a card refused costs only itself.

Every picture is redrawn before it leaves (`contacts_photos`): one JPEG of at most
`WORKBENCH_CONTACT_PHOTO_MAX_SIDE` pixels. The metadata stays behind, so a phone's GPS reaches no
provider; a card stays a size iCloud takes; what is no image is refused here. A photo is read by the
server and reaches the page as a blob, believed only when its first bytes say so: a card's script
never leaves as an image, and an address a card names is never followed. Graph writes at
`photo/$value` and deletes at `photo`, where `$value` answers 405 (measured).

A group is one word on the three providers: a Google group, a Graph category, an iCloud group card.
Graph has no group a contact sits in several of, and deleting a contact folder deletes its
contacts, so a category it is: a free word is taken and `categories/any(...)` filters answer
(measured). Graph holds no empty group, so on every provider a group is made by adding someone to
a name. Past the bound of its scan, Graph's list claims no count. The assistant reads groups on the
three providers; only « other contacts » stay Google's, and a contact met in mail can be kept
(`copyOtherContactToMyContactsGroup`).

Amendment 2026-11-05 (phase 2, repeating events): a repeating event is the one recurrence of LIA
(`core/recurrence`), dictated to the assistant in the same words as a routine, and translated once
per provider (`clients/event_recurrence`): an RRULE for Google and iCloud, a `patternedRecurrence`
for Graph. A shape Graph cannot hold (the last day of a month, a fifth weekday, several days of a
month) is refused by name, never held differently: as a 31st it would skip every short month. A
series starts on the event's own day, and a rule that day does not belong to is refused before
anything leaves, because Google would keep the day as an extra occurrence and Graph would refuse.
An end date is the last local day, included: a day for an all-day series, the last second of that
day in UTC for a timed one, as RFC 5545 asks.

A whole series is asked for, never assumed (`scope`): this occurrence stays the default where a
provider can change one alone, and iCloud, which cannot, offers the series only. It reaches the
master (`recurringEventId`), keeps the series' first day and takes the new time of day and length,
since an occurrence's date is no date for the series; what was not asked is not sent, as a provider
may reset a series' exceptions on a new start. Measured on Graph: a master's change reaches every
occurrence, and a master's deletion removes them all.

Amendment 2026-11-05 (phase 2, search and lights): one search reads the four tools that can search,
at once, each its own request, and starts on Enter: a key press would read four providers. A tool
that fails is named beside what the others found, and a bug in one is logged by its type and named
the same way, so it never empties the others (ADR-292). What a search could not cover is said, not
guessed: a page cut at five, a calendar past the published bound, and a mailbox read from its inbox
alone, because « everything » is a place only Gmail has. Tasks are left out: no provider searches
them.

A zone is a room's shape whose children name lamps, not devices, so one reading of a group serves
both, and it stays out of « All off », its lamps going with their rooms. A lamp the bridge cannot
reach offers nothing: a bridge accepts what it cannot deliver, so the gesture would read as done.
Unknown is not lost: a lamp nobody reports on is drawn as usual. A group's tone offers a colour as
soon as one lamp takes it, and the temperatures all of them accept. A bridge without one of the
two new resources (404) reads as holding none, in the client, so the screen and the assistant keep
working; any other refusal stays a failure. Field names follow the public OpenHue description: no
bridge was available, and no lamp of the owner's was moved to prove them.

Amendment 2026-11-05 (phase 2, OneDrive everywhere else): the briefing, the assistant's Excel and
Word tools and the spaces' folders answer to the account's drive. `recent_files` is on the contract,
and on OneDrive it is built from the feed (`onedrive_recent`). Measured on a real personal drive of
30,960 items: a search refuses an empty query, ignores `$orderby` and stops at 200 items, a folder's
date does not follow what changes under it, `recent` answers one item, enumerating takes a minute;
each of these found none of the ten latest files. The window starts from the top of the drive and
is exact for whatever changed since. Office files read from their bytes under an archive budget
(`office_files`). A workbook is written through the Excel API on a work drive and refused before any
card on a personal one, where a rewrite would lose what `openpyxl` does not carry; a document is
rewritten whole on the `eTag` it was read at, Graph not documenting that header on this call. A
source names its drive (`rag_drive_sources.provider`), a folder of the other one is kept and waits,
its documents searchable. Graph's delta speaks Drive's feed so one drain serves both, a forgotten
token rebasing like a long feed; its subscription renews in place, one per resource. The reads, the
walk and the feed are measured on that drive; the Word write, the Excel API and the subscription
still follow Microsoft's documentation alone.

Amendment 2026-11-05 (phase 2, Outlook's settings): automatic replies and rules speak the one
vocabulary of Gmail's settings client, through `mailbox_settings_of`, so the screen and the four
assistant tools carry no branch per provider; the read tool is now `get_mailbox_settings_tool`. A
category tool names the providers that hold it (`served_by`), and leaves the catalogue of an iCloud
account. What Outlook cannot hold is refused before anything is sent: a reply has no subject, a
schedule has an end, a rule reads no Gmail search. They need `MailboxSettings.ReadWrite`, which an
existing connection lacks: Graph answers 403 (measured) and the refusal says to reconnect. The shapes
follow Microsoft's documentation: the test account does not hold the right, so nothing is measured.

Amendment 2026-11-05 (phase 2, Android shell): a file and a new window are the host's to take, and
Capacitor sets neither. A `DownloadListener` hands the file to the system's download manager with
the cookie of the host that set it; `setSupportMultipleWindows` makes a sandboxed frame's link
reach `onCreateWindow`, where only a gesture of the person opens anything, and only http, https
and mailto leave. The API on a sibling host stays in the WebView (`shouldOverrideLoad`), the one
place holding the session. The web asks the shell what it can do (`capabilities`): it moves with
the server and the shell with the store. Measured on the real debug APK against a stand-in
server. It reaches people with a store release, which is the owner's decision.

Amendment 2026-11-06 (the owner's remarks on a phone): a phone reads a line at a time, so a line says
what it holds. The actions of a tool leave the rail's row below `xl`, and on their own line the
search and **Refresh** start it and the act the tool leads with ends it. A detail draws its acts
as a message's reader does, at every width and a task's included: the way out, then icons at the
end of one bar (`DetailBar`), what is less common behind « … ». A tool declares what it offers and
in what order (`DetailAct`), the bar decides the drawing, so a « … » of one is never opened: its act
stands in the bar. An open event keeps all its acts there, « Ask LIA » included, and « Move to… »
opens the calendars it can go to under its own icon (`choices`), even for one: an icon names nothing
on a phone, and a press never moves an event to a place the person has not read. Five icons leave a
small phone little room: the tool's name gives way, and under larger text the icons take another
line, so an act is never cut. Whatever order a tool declares, every bar ends on the deletion, then
the question to LIA, « … » before them; a message's reader keeps that order, with archiving, moving
and reporting spam behind « … », and a file brings moving, sharing and mailing into its bar. A task's
« Save » stands outside its form and still submits it, through `form`.
A phone's native list is as narrow as it likes and cuts a label, so the mailbox's folders leave
`<select>` for the application's listbox, as wide as the pane, with what the column holds in its
order. A message's answers stand above its text as well, a pane being taller than the screen. Its
three views keep a place each on a phone's line, at the start, in the middle and at the end, and
stand together in the middle from `sm`. On a phone a task list's head stands in the middle of its
pane, and the calendar's toolbar starts on today, ends on the period, and gives its search all the
room the calendars leave. A large screen opens the mailbox on the inbox's newest message: nobody
opened it, so it rides no address and stays unread until the person opens it, since a tool does
what is clicked and marking read writes to the mailbox; whatever the person does with the reader
lets go of it for the visit. A room or a lamp that is off stands apart from the page, under it in a
light theme and above it in a dark one, where it never outshines what is lit (`--color-unlit`). The
calendar stops printing the
account's zone at every width: the times were never in doubt, and a zone of its own is still said
on the event. The labels are the owner's; each keeps its long form for the ear where the short one
would lose it (« Open » tells which drive).

Amendment 2026-11-06 (the owner's remarks on forms): a form opens and ends one way, whichever
tool draws it. `ToolForm` holds that way: a head at the left at every width, acts that take a line
each and the whole width on a phone, the act first, a « Cancel » in « Delete »'s style on every
screen, confirmations included (`useToolConfirm`); `NativeSelect` draws a list as a field, keeping
the platform's picker. `toolForm.guard.test.ts` refuses a tool's own head, end, question or list.
In a confirmation the two buttons therefore look alike, and their words and places tell them
apart: the owner's rule, recorded so nobody restores the difference by reflex. An answer is kept
as a message is: `POST /mail/drafts` takes an `origin` at the first save, and the clients' reply and
forward drafts keep the thread, the quote and the files on the three providers, the person's own
recipients and files in the same act. The composer then closes, and an answer never saves itself: a
later save would write the person's words over the whole message, the quote with it. A row's « ⋮ »
says the act (`menuText`), its trigger having named the message. Two defects were the platform's,
fixed there. A menu in a modal dialog closed as it opened, the dialog's focus trap taking back the
focus the portal had received: inside one, a menu is modal itself, which is what let « Write with
LIA » open on an event. And `transition-duration: 0.01ms` on `*` under reduced motion made every
change of every element a transition, `transition-property` defaulting to `all`, painted for a
frame at its old value: a list at no width when its reader closed; the duration is zero, nothing
waiting for `transitionend`. A field under 16 px on a touch screen is one iOS zooms into and stays
zoomed on, buttons out of sight: `globals.css` holds the rule for every screen, outside any layer.

Amendment 2026-11-05 (phase 2, the owner's remarks): a document is read, not peeked at. One door
serves the mail and the files (`previews`) and answers the best a file can be read as; its type
names the viewer. A PDF travels whole and is read in the page by PDF.js: the page's policy admits no
frame of a PDF, and a WebView has no viewer, so one viewer serves every device. The library loads
when a PDF is first shown, its legacy build because a WebView can be older than the browsers its
main build asks for; its worker, character maps, standard fonts and decoders are copied from the
lockfile's version (`scripts/copy-pdf-runtime.mjs`), so a self-hosted install asks nobody for them.
Version 6.4 evaluates no code of any kind, measured in its source, which closes the road of
CVE-2024-4367. Forms and annotations are not drawn, so nothing in a file acts; a link in a PDF is
not followed.

A Word file nobody renders travels as itself, its archive held to the budget the parsers obey first,
and docx-preview lays it out on nodes nothing attaches. The library sanitises nothing, so what it
builds leaves as text for the frame a mail's HTML uses (`AuthoredHtmlFrame`): no script, no form, a
policy before the first byte, links disarmed. An alternative chunk and embedded fonts stay out. A
Markdown is laid out by React, its HTML left out, its pictures their captions: opening a file tells
nobody. A slide deck the provider does not render reads as its text, a workbook and a CSV as tables.
A Google document comes through its PDF export. On OneDrive a Word file or a slide deck comes as the
PDF Graph renders (a 302 to a pre-authenticated address, measured), its own bytes when that fails; a
workbook stays tables, and comes as that PDF when it reads as none, which a real one did. A type
that says nothing leaves it to the file's name (`core/document_types`): OneDrive declares
`application/octet-stream` for `.md`, `.csv` and `.log`, measured. What a page may offer is the
API's word (`previewable`, `editable`), never a second table in the browser, and a generated
document keeps its closed list.

A read a person is looking at waits its turn (`one_preview`, bounded by
`WORKBENCH_PREVIEW_WAIT_SECONDS`) and counts under the read window, because a read the page dropped
still runs on the server: measured on 2026-11-05, Strict Mode's first effect held the account's
claim and 35 reads of 66 answered 429. A save refused stays a click to repeat. The page starts a
read once it has settled on a document, and tells a failure, which can be tried again, from a
document with nothing to show. A Gmail part goes by its place in the message (`part_id`): its
attachment id changes at each read, and two parts of one name left a 409 at every click.

A plain text is changed by hand and by the assistant through one module (`drive_text`): read whole,
written back on its version, its byte order mark and line ends kept, bytes that are no UTF-8 refused
rather than guessed. OneDrive holds the condition (`If-Match`); Drive holds none, so its head
revision is read just before the write, and a change landing between the two calls is the one it
cannot refuse. An Office file or a Google document is changed where it lives, behind « Open in … ».
`documents_of` opens these texts beside the drive's documents, so the assistant reads and adds to
them with the tools it had, and its rewrite is a card of its own (`DOCUMENT_REPLACE`) showing every
word, on the version the card was built on, bounded by what a card can show.

A contact's exchanges (`contacts_history`) are the five latest messages each way and the five latest
meetings each organised, by address. They reuse what `relations` knows of each provider and leave
out its qualification, so no model runs. A calendar answers a window oldest first: the read walks
back from now by spans, stops once both lists are full, and says how far it looked. `organizer.self`
is Google's word; Graph's normaliser gives it, and iCloud's client reads it from the addresses the
server knows the account by. A meeting naming no organiser stands in a list of its own rather than
in a guessed one, and another person's meeting answers neither list. A failed source is said, never
read as empty. On Google the lists are measured, on Graph the searches and `self` only, and iCloud
follows its documentation.

Since 2026-11-07 a contact's NUMBERS are asked too (`contacts_lines`): the five latest calls LIA
placed to them and the five latest texts they sent, read on LIA's own records, each on a session of
its own. A number is stored encrypted (a call) or keyed by the digest of one spelling (a text), so it
is matched, never looked up: the latest records are read newest first under a stated bound and
matched by the rule each domain already owns (`same_line`, `sent_from_lines`). A source the contact
gives nothing to look under says `not_requested`, distinct from `disabled` (switched off, or no
record of that kind at all) and from `unavailable`; a contact with numbers alone has exchanges. The
answer names neither number nor sender, and is `no-store`.

Amendment 2026-11-06 (release review): three things an installation sees and a developer's machine
does not. A scope added to a connector is a scope every refresh of a grant then holds it to, and a
row that fails goes to ERROR: `MailboxSettings.ReadWrite` would have stopped every mailbox consented
before it, where the decision above says only its settings answer 403. `_OFFERED_ONLY`
(`connectors/oauth_bulk.py`) names the scopes a connector asks for and works without. A key minted
in the page cannot be `crypto.randomUUID()`: the plain-HTTP LAN install the installer offers has no
secure context, and the call took a screen down at render; `generateUUID()` serves both, and ESLint
refuses the other. What the manifests read imports nothing from the tool layer, or the catalogue
holds only because a boot happens to import the tools first: `read_recurrence` moved to
`tools/calendar_series`, and a fresh interpreter now loads the catalogue in a test.

## What is NOT recorded, and why

Nothing the person does in the workbench reaches the consultation register, the effect register,
the decision register, the token ledger, memory, habits, journals or open loops (D5): none of it is
LIA's. What remains is operational: `workbench_requests_total` by tool, operation and outcome
(downloads included), `workbench_provider_latency_seconds` by tool, and the idempotency replays and
unguarded submissions — counts and codes, never content.

## Consequences

- The assistant became more capable in the same lots (read state, all-day events, non-destructive
  contact edits, Drive search that works in full text), and safer (ids quoted, `q` values escaped).
- Graph and iCloud were proven through faithful doubles only: no write on a real account without
  its owner's agreement. Gmail, Google Calendar, People, Drive and Hue follow their providers'
  documented contracts, pinned by tests on recorded shapes.
- Phase 2 — « ask LIA » from the same screens as a prefilled draft — needs no change of shape:
  every response already names its provider and its bounds.

Amendment 2026-11-06 (owner): what a person does by hand still involves no model, and
`domains/workbench/` still holds none. What a click asks of LIA from these screens is decided in
[ADR-372](ADR-372-What-LIA-Does-From-The-Tools-A-Click-A-Call-A-Proposal.md): its own bounded context, a proposal the person finishes by hand, filed and billed
as an act of LIA.

Amendment 2026-11-07 (owner): the home's cards open their items here. Where the instance offers
the Tools, a click on an agenda, mail, task, document or birthday item opens it in its tool, on the
address that tool already reads, and the operator's switch keeps the chat. Each card's « More
actions » holds at most five acts, direct ones first: the Tools' own routes (mark read, archive,
done, postpone to tomorrow, download), a hand-over to another tool where that tool is connected
(a file to a new message, a sender to the contacts), a plain link (a map, a video call, a call), a
reminder — none involves a model or files a row (D5); LIA's acts follow, through the chat. What a
card names for this travels with its item (the calendar read, the list's real id, the contact), and
the two the screens must resolve are resolved there: the `primary` alias, and a task past the pages
read (`GET /workbench/tasks/task`). See [BRIEFING_DOMAIN.md](../technical/BRIEFING_DOMAIN.md).

Amendment 2026-11-07 (owner, measured): a task's due day, one door. Measured on Graph, To Do
keeps the instant of midnight in the zone it is GIVEN and answers it in UTC; given UTC, it keeps the
UTC date, so a day the Tools wrote as its UTC instant was the day before east of Greenwich, and the
home's card, the heartbeat and the radio read a To Do due as its UTC date. A day is now written to
To Do as its midnight on the account's wall with the zone named (`due_zone` on both clients; Google
keeps a date and takes none), and every reader of a task's day goes through `core/task_due`: a
Google due is the date it names in every zone, a To Do due its instant read in the account's zone —
the Tools, the home's card, the heartbeat (overdue once the day has passed, never on the day), the
radio and the assistant's told day. The assistant still writes a day as its UTC midnight (read
right east of Greenwich, a day early west of it), and the chat's task card reads its due itself:
both are left as they are, said.

Amendment 2026-11-11 (owner, measured): what a selection can become holds on one line. The
mail's selection bar drew nine buttons in words: measured with three messages ticked, 283px of
a 320px list (a message open beside it), 243px of a 384px one, 283px of a phone's — the list's
first screen. The three tools now declare their acts and one bar draws them
(`ToolSelectionBar`): the count, an icon out of the selection, the acts used most as icons,
the rest behind « … », the deletion last, solid red (ADR-207) — 63px at every width. The bar
is measured, not ruled by a breakpoint: whole while it fits, its quick icons in the list where
the room runs out. An act keeps the words and the icon its row and its reader use, since an
icon alone cannot mean two things: the bar's own short words (`bar_*`) are gone, and marking
read is the opened envelope everywhere. Nothing changes in what an act does, nor in D5.

Technical reference: [WORKBENCH.md](../technical/WORKBENCH.md).
