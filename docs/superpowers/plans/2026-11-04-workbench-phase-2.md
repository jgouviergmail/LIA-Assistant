# Workbench phase 2 — plan

**Owner decisions (2026-11-04).** Analysis accepted, executed lot by lot: each lot is implemented in TDD,
reviewed adversarially and cold, then WAITS for the owner's validation and a GO. Nothing is
committed during the programme: the owner stages each lot once validated.

| Id | Decision |
|---|---|
| A1 | The mail frame gains `allow-popups allow-popups-to-escape-sandbox`, stays an opaque origin; only http, https and mailto links survive, rewritten to a new tab. Remote images load directly on a click, the sender seeing the address, and the page says so. |
| A2 | Permanent delete and empty trash: by hand only, with a confirmation. No assistant tool (a written exception to D2). |
| A3 | The signature also reaches the mails the assistant sends, visible on the confirmation card. |
| A4 | Everything offered with Google Drive must be possible with OneDrive, depending on the connector connected. The two are EXCLUSIVE, like every other category (`files`). |

Provider truth a lot may not forget:

- **Parity is the rule** (D2): a gesture of one provider exists for the others, unless proven impossible, and what the clients gain
  reaches the assistant in the same lot. `features.py` carries the proven limits: the page offers only what the connector accepts.
- **Apple has no test account**: every Apple path is proven by faithful doubles alone, with extra care.
- **Microsoft test account** exists (personal). Entra: both registrations hold the delegated `Files.Read`, `Files.ReadWrite`,
  `Files.Read.All`, `Files.ReadWrite.All`.
- **OneDrive limits (documented)**: `sharedWithMe` and `recent` deprecated (data stops November 2026); the recycle bin cannot be
  listed, `restore` is OneDrive Personal only and needs `Files.ReadWrite.All`; the Excel API is absent on consumer OneDrive (read by
  download and `openpyxl`, write refused there); no Word content API (`python-docx`, writes guarded by the eTag); a change
  subscription needs `Files.Read` (personal) or `Files.Read.All` (work), and Graph refuses write scopes where read is enough.
- **Apple**: no iCloud Drive API, Reminders left CalDAV with iOS 13 (third-party sources): stated on screen, never hidden.

Scope legend: Front = the page alone; G, M, A = Google, Microsoft, Apple; + IA = reaches the assistant in the same lot.
ROI and Risk 1 to 5. Effort S under 1 h, M 1 to 3 h, L 3 to 8 h, XL beyond.

## Lot 1 — repair what shipped (5-7 h)

| # | Item | Scope | ROI | Effort | Risk |
|---|---|---|---|---|---|
| 1.1 | Links clickable in the mail's text view, `[link](url)` drawn properly | Front | 5 | S | 1 |
| 1.2 | Refresh on the six tools, a re-read on coming back to the tab | Front | 5 | S | 1 |
| 1.3 | Links clickable in event, task, contact and file notes | Front | 4 | S | 1 |
| 1.4 | Open an « other contact » without an impossible read | G | 3 | S | 1 |
| 1.5 | Zone scenes reachable | Front | 3 | S | 1 |
| 1.6 | The default calendar and task list of the settings honoured | G M A | 3 | S | 1 |
| 1.7 | Outlook nested folders, label tree | G M | 3 | M | 2 |
| 1.8 | Stable frame, bounded height for Tasks | Front | 2 | S | 1 |
| 1.9 | Delete a Gmail filter | G + IA | 2 | S | 1 |
| 3.1 | Remote images on demand (A1), brought forward at the owner's request | Front | 5 | S | 2 |
| 3.2 | Live links in the HTML frame (A1), brought forward at the owner's request | Front | 5 | S | 3 |

Also: measure S10 (a download in the WebView), never measured in phase 1. Measured 2026-11-04 on
Android 16, Capacitor 8.5.3: a same-origin attachment lands nowhere, another origin goes to the system
browser with no session, and a `_blank` link in a sandboxed frame opens nothing. Both need the shell
(item 13.6), so a store release: the owner's decision.

## Lot 2 — ergonomics, no new provider contract (12-16 h)

| # | Item | Scope | ROI | Effort | Risk |
|---|---|---|---|---|---|
| 2.1 | A click on a slot creates an event | Front | 5 | S | 1 |
| 2.2 | Non-modal composer, message and quote visible | Front | 5 | M | 2 |
| 2.3 | Phone: raise the mail list (first row at 422 of 844 px) | Front | 5 | M | 2 |
| 2.4 | Day view and the current-time line | Front | 4 | S | 1 |
| 2.5 | Actions on the mail row (`RowActions`) | Front | 4 | S | 1 |
| 2.6 | Files: type icons, sort, multi-select, copy link | Front + G | 4 | S | 1 |
| 2.7 | Lights: all off, scenes on the room card | Front | 4 | S | 1 |
| 2.8 | Undo send (a short delay before sending; `beforeunload` guard) | Front | 4 | S | 2 |
| 2.9 | Ask LIA about an item (text handed over outside the URL: `?draft=` would log it) | Front | 4 | S | 2 |
| 2.10 | Title merged with the pills, provider visible (validate on a screenshot) | Front | 4 | S | 2 |
| 2.11 | Bridges: mail to task or event, contact to compose, sender to contact | Front | 4 | M | 1 |
| 2.12 | Keyboard shortcuts, `?` help, can be switched off (WCAG 2.1.4) | Front | 4 | M | 2 |
| 2.13 | Drag to move or resize an event (`@dnd-kit`, existing PATCH, keyboard alternative) | Front | 4 | M | 3 |
| 2.14 | Join the call from the chip, series icon | Front | 3 | S | 1 |
| 2.15 | Duplicate an event | Front | 3 | S | 1 |
| 2.16 | Agenda view beyond the week | Front | 3 | S | 1 |
| 2.17 | Range selection, next message after an act | Front | 3 | S | 1 |
| 2.18 | Contacts: initials, separators, copy, map | Front | 3 | S | 1 |
| 2.19 | Tasks: quick due dates, autosave | Front | 3 | S | 1 |
| 2.20 | Month readable on a phone | Front | 3 | M | 2 |

## Lot 3 — reading a mail (6-8 h)

| # | Item | Scope | ROI | Effort | Risk |
|---|---|---|---|---|---|
| 3.3 | Inline images (`cid:`) resolved to bounded `data:` | G M A | 4 | M | 2 |
| 3.4 | Unsubscribe: the link first, then one-click POST through `pinned_stream` | G M A | 4 | M | 3 |
| 3.5 | Attachment preview: images, then PDF | Front | 4 | M | 3 |
| 3.6 | Print (text view) | Front | 2 | S | 1 |

## Lot 4 — sorting the mail (9-12 h)

| # | Item | Scope | ROI | Effort | Risk |
|---|---|---|---|---|---|
| 4.1 | Restore from the trash | G M A + IA | 5 | S | 2 |
| 4.2 | Unread counts, badge, automatic freshness (counters polled, not listings) | G M A | 5 | M | 2 |
| 4.3 | Archive, with « All mail » for Gmail | G M A + IA | 5 | M | 2 |
| 4.4 | Star | G M A + IA | 4 | S | 1 |
| 4.5 | Move to a folder, drag to the pane | G M A + IA | 4 | M | 3 |
| 4.6 | Undo after trash, archive, move (Graph and IMAP change the id: the act returns old and new) | G M A | 4 | M | 3 |
| 4.7 | Spam and not spam | G M A + IA | 3 | S | 2 |
| 4.8 | Paperclip in the list (exact on Graph, to prove elsewhere) | G M A | 3 | M | 2 |
| 4.9 | Manage Outlook and iCloud folders | M A + IA | 3 | L | 3 |
| 4.10 | Permanent delete, empty the trash (A2) | G M A | 3 | M | 4 |

## Lot 5 — calendar: invitations and search (7-9 h)

| # | Item | Scope | ROI | Effort | Risk |
|---|---|---|---|---|---|
| 5.1 | Answer an invitation (CalDAV proven first) | G M A + IA | 5 | M | 3 |
| 5.2 | Search events (`list_events` already searches ×3) | G M A | 4 | S | 2 |
| 5.3 | A call on an existing event | G M + IA | 3 | S | 2 |
| 5.4 | Reminders | G M A + IA | 3 | M | 2 |
| 5.5 | Dated tasks in the calendar | Front | 3 | M | 2 |
| 5.6 | An event's own zone | Front | 2 | S | 2 |
| 5.7 | Busy or free, private | G M A + IA | 2 | M | 2 |
| 5.8 | Change an event's calendar | G M A | 2 | M | 3 |
| 5.9 | Manage calendars | G M A | 2 | L | 3 |

## Lot 6 — files: neutral contract, Drive AND OneDrive in the same lot (22-28 h)

New category `files`, `FilesClientProtocol`, `ConnectorType.MICROSOFT_ONEDRIVE`, `manage_files_tool`. Every gesture lands on both
providers in this lot; what OneDrive cannot do is a `PROVIDER_FEATURES` limit.

| # | Item | Scope | ROI | Effort | Risk |
|---|---|---|---|---|---|
| 6.1 | The contract, the connector (OAuth, settings, exclusivity), the neutral tools | G M + IA | 5 | L | 3 |
| 6.2 | New folder, rename, move, copy | G M + IA | 5 | M | 2 |
| 6.3 | Upload, drag and drop | G M + IA | 5 | M | 3 |
| 6.4 | Recent, starred, shared with me (OneDrive limits above) | G M | 4 | S | 1 |
| 6.5 | Trash and restore (OneDrive limits above) | G M + IA | 4 | S | 2 |
| 6.6 | Preview in the detail | Front | 4 | M | 3 |
| 6.7 | File to mail, attachment to file | G M | 3 | M | 2 |
| 6.8 | Shared drives (SharePoint libraries to prove) | G M | 3 | M | 2 |
| 6.9 | Share | G M + IA | 3 | M | 4 |
| 6.10 | Storage quota | G M | 2 | S | 1 |

## Lot 7 — composing (10-14 h)

| # | Item | Scope | ROI | Effort | Risk |
|---|---|---|---|---|---|
| 7.1 | Attach a file from the device (the upload door takes images and PDF for 24 h only) | G M A | 5 | M | 3 |
| 7.2 | Attachments on reply and forward | G M A + IA | 4 | M | 3 |
| 7.3 | Signature in `connectors/preferences` (A3) | G M A + IA | 4 | M | 2 |
| 7.4 | Rich text (`is_html` exists ×3) | G M A | 4 | L | 3 |
| 7.5 | Editable recipients, Cc on a reply | G M A | 3 | M | 2 |
| 7.6 | Attachments on drafts, autosave | G M A | 3 | L | 3 |
| 7.7 | Send-as alias | G | 2 | M | 2 |

## Lot 8 — conversations (5-7 h)

| # | Item | Scope | ROI | Effort | Risk |
|---|---|---|---|---|---|
| 8.1 | Conversation view in the reader | G M A + IA | 5 | L | 3 |
| 8.2 | List grouped by conversation | G M | 3 | L | 3 |

## Lot 9 — tasks and contacts (9-12 h)

| # | Item | Scope | ROI | Effort | Risk |
|---|---|---|---|---|---|
| 9.1 | Today, overdue, upcoming views | G M | 4 | M | 2 |
| 9.2 | Birthday, job title, website, given and family names | G M A + IA | 4 | M | 3 |
| 9.3 | Rename a list | G M + IA | 3 | S | 1 |
| 9.4 | Save an « other contact » | G | 3 | S | 1 |
| 9.5 | vCard export | G M A | 3 | M | 2 |
| 9.6 | Move a task between lists | G M + IA | 3 | M | 3 |
| 9.7 | To Do subtasks (`checklistItems`) | M + IA | 3 | M | 3 |
| 9.8 | Contact photos | G M A | 3 | M | 3 |
| 9.9 | Manage groups | G M A | 3 | L | 3 |
| 9.10 | Clear completed, multi-select | G M | 2 | S | 2 |
| 9.11 | Reorder tasks | G | 2 | M | 2 |
| 9.12 | Priority, reminder, repetition | M + IA | 2 | M | 2 |
| 9.13 | vCard import | G M A | 2 | L | 3 |

## Lots 10 to 13

| # | Item | Scope | ROI | Effort | Risk |
|---|---|---|---|---|---|
| 10.1 | Create a repeating event (`RecurrenceEditor` reused) | G M A + IA | 4 | L | 4 |
| 10.2 | Change or delete a whole series | G M A + IA | 3 | M | 4 |
| 11.1 | OneDrive everywhere else: Excel and Word content, RAG spaces, change tracking (delta + subscription), briefing. First migration of the programme (the provider of a RAG source). A switch of provider keeps the sources, sync paused | M + IA | 5 | XL | 4 |
| 12.1 | Outlook automatic replies (`MailboxSettings.ReadWrite`, reconnection) | M + IA | 3 | M | 3 |
| 12.2 | Outlook rules | M + IA | 3 | M | 3 |
| 13.1 | Global search (Ctrl+K) | G M A | 4 | L | 3 |
| 13.2 | Hue zones | Hue | 3 | M | 2 |
| 13.3 | Unreachable lamp | Hue | 3 | M | 2 |
| 13.4 | Dynamic scenes | Hue | 2 | S | 2 |
| 13.5 | Temperature and colour of a whole room | Hue | 2 | M | 3 |
| 13.6 | Android shell: downloads (`DownloadListener` with the session), links of the mail frame (`onCreateWindow` to the system browser), a store release | Shell | 4 | M | 3 |

Not retained: merging duplicates (no API, data-loss risk), scheduled send and snooze (no common contract, a deferred act leaves D5),
a floating button (competes with the companion), a home screen in the section (the dashboard is one), « find a slot » and document
editing (owner, spec §14), several accounts per category (D1).

## Method of each lot

1. Pin the touched clients with a golden test where one exists.
2. Parity tests ×3 in red, then the contract; the descriptor; the route and service; the assistant in the same lot.
3. The screen and its six languages.
4. Gates: `task lint`, `task test:backend:unit:fast`, `task test:backend:agents` when a tool changes, `task test:frontend:coverage`,
   the affected e2e, `task ci:fast`.
5. A cold adversarial review of every line, then docs (WORKBENCH.md, FAQ ×6, maps when an ADR changes), and a report with commands
   and figures. The ledger `.superpowers/sdd/2026-11-04-workbench-phase2/progress.md` carries every ruling.
