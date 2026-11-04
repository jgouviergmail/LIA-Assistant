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

Technical reference: [WORKBENCH.md](../technical/WORKBENCH.md).
