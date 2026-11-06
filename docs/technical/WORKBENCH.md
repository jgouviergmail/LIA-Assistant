# The workbench — « Tools »

The person's own door to their connected services: mail, calendar, tasks, contacts, files
(Google Drive or OneDrive) and Hue lights, consulted and acted on **by hand, with no model in the path**. The decisions are
[ADR-369](../architecture/ADR-369-Workbench-The-Persons-Own-Door-To-Their-Services.md); this page is
the map of the code.

## Where it lives

| Layer | Path |
|---|---|
| Bounded context (REST, no LangGraph) | `apps/api/src/domains/workbench/` |
| Settings | `apps/api/src/core/config/workbench.py` (`WORKBENCH_*` in the env templates) |
| Constants (bounds published to the page) | `apps/api/src/core/constants.py` (`WORKBENCH_*`) |
| Metrics | `apps/api/src/infrastructure/observability/metrics_workbench.py`, panels on dashboard `10-oauth-connectors-mcp.json` |
| Capability switch | `PlatformCapability.WORKBENCH` (`domains/feature_switches/registry.py`) |
| Page | `apps/web/src/app/[lng]/dashboard/tools/` and `apps/web/src/components/workbench/` |
| Page model and types | `apps/web/src/lib/workbench/` |
| Hooks | `apps/web/src/hooks/useWorkbench*.ts` |
| Hermetic journeys | `apps/web/e2e/smoke/workbench-*.spec.ts` |

## The pieces every tool shares

| Module | Role |
|---|---|
| `availability.py` | `GET /workbench`: per tool `ready`, `not_connected`, `reconnect_required` or `unavailable`, the active provider, its features and bounds, and the section's `limits`. |
| `features.py` | The descriptor: per connector type, the gestures its client accepts (`WorkbenchFeature`) and the bounds it imposes (`PROVIDER_BOUNDS`); boot completeness assert. |
| `clients.py` | `open_tool_client`: the category door (`open_active_client`, which also reads the owner's default container when `container` names one), files included, or `open_client_by_type` for the Hue bridge; no session held while a provider answers. |
| `calls.py` | `provider_call`: times one provider call, turns its failure into one refusal (by type and status, act-aware), counts it. |
| `errors.py` | The refusal vocabulary and `refuse()`. |
| `ids.py` | The shapes an id, a cursor or a name may take on the way in. |
| `rate_limits.py` | Per-account windows: read (a preview included), write, send, bulk, download; `charge_selection` charges a selection of several as a bulk act. |
| `idempotency.py` | `run_once`: a submission key claimed in Redis before the provider call, settled `done` or `unknown`; a replay answers the stored outcome. |
| `downloads.py` | One transfer at a time per account (a preview waits its turn, `one_preview`), and the response a browser saves and never renders. |
| `previews.py` | The best a document can be read as, for the mail and the files: its type names the page's viewer. |
| `selection_acts.py` | An act on a selection, item by item, a few at a time, each answered (`ActOutcome`). |

On the web side, the frame is `WorkbenchShell` (the availability read once, the row of tools
above the open one) and every vertical pane a person sizes by hand on a large screen is declared
once in `lib/workbench/panes.ts` (its bounds and the share of its row it may take), drawn through
`useWorkbenchPane` and moved by the shared window splitter `components/ui/pane-separator.tsx`; the
widths are a preference of the device (`stores/workbenchPanesStore.ts`). On a computer the section
runs the whole window: the dashboard layout gives it `PAGE_FRAME_WINDOW` (`lib/dashboard-nav.ts`)
from `lg`, and every other page keeps the rail.

The tool's name is said by the open pill of the rail, which also names the vendor
(`providerVendor`); the page's `h1` is for the outline and the ear, and the tool's actions end the
rail's row through a portal (`WorkbenchActionsSlot`), so a tool starts right under it. They hold
**Refresh** (`WorkbenchToolHeader`, `useToolRefresh`): the screen re-reads what it shows, and
coming back to the page after `WORKBENCH_RETURN_REREAD_MIN_MS` does it unasked. An unasked re-read takes nothing away (`useWorkbenchPage`, `useWorkbenchItem`): it
leaves alone a listing of several pages, a read still on its way and a failed one, and it keeps
what is on screen when it fails.

A tool's keys go through `useToolShortcuts`, declared with the header: never in a field or a
dialog, never with Ctrl, Cmd or Alt, switched off per device (`ShortcutsHelp`, WCAG 2.1.4). One tool
hands another what it starts through `lib/workbench/handoff`, held in the page and taken once, since
a subject has no place in an address a server logs; `useToolBridges` offers a way out only where its
tool is ready, and `seedInputDraft` leaves words for the chat the same way, unsent.
`useListSelection` is the selection every list shares: it belongs to one listing, and Shift ticks a
range.

A document is read through `useShownDocument`, which starts a read once the page has settled, and
`ShownReading` (`components/workbench/ShownDocument.tsx`), which draws the wait, the refusal with
its second try, or the viewer the answer's type names. `viewers/PdfViewer.tsx` draws a PDF with
PDF.js (`lib/workbench/pdf-document.ts`, its runtime copied by `scripts/copy-pdf-runtime.mjs`), page
by page as they come near, `viewers/WordViewer.tsx` hands docx-preview's output
(`lib/workbench/word-html.ts`) to `AuthoredHtmlFrame`, and `viewers/MarkdownViewer.tsx` lets React
draw a Markdown. `DetailClose` is the way out of a detail: a cross beside the list, the tool's name
where the detail takes the screen.

A text is drawn through `components/ui/linked-text.tsx`: `lib/text-links.ts` reads it in one pass
(ADR-326), turns the API's `[link](address)` into the host's name, keeps an address a person wrote
as written, follows `http`, `https`, `mailto` and `tel` alone, and never one carrying credentials.

## Routes

All under `/api/v1/workbench`, behind the capability guard and the session cookie.

| Tool | Method and path | What it does |
|---|---|---|
| — | `GET /workbench` | The tools the account can use, and the bounds they enforce |
| — | `GET /search` | Words looked for in mail, calendars, contacts and files at once: the first of each, what was cut, and the tools that could not answer |
| Mail | `GET /mail/folders` | The folder pane: system places, then the person's own folders, by path (`truncated` when Graph's walk stopped at its bound) |
| | `GET /mail/messages` | One page of a folder, narrowed by the person's words and chips |
| | `GET /mail/message` · `GET /mail/message/html` | One message (reading marks nothing read) · its HTML for the isolated frame |
| | `GET /mail/conversation` | What was said around a message: headers alone, oldest first, drafts left out, one page of the newest (`truncated` states the cut) |
| | `GET /mail/message/images` | The images a message's HTML names, as `data:` addresses, under `WORKBENCH_MAIL_INLINE_MAX_BYTES` (what is left out is counted) |
| | `GET /mail/message/unsubscribe` · `POST /mail/unsubscribe` | How a message says it can be left · its one-click POST (RFC 8058), by the message alone, through `pinned_stream` |
| | `GET /mail/counts` | What the mailbox leaves unread, keyed as the pane names each folder (`truncated` when one was left out) |
| | `POST /mail/read-state` · `POST /mail/star` | Read state, star — each message answered |
| | `POST /mail/move` | A selection sent to a place, as the pane names it (`to`, `origin`): each message answered, with what it is called from now on (`moved`) |
| | `POST /mail/delete-forever` · `POST /mail/empty-trash` | Deleting for good, messages of the trash alone (`permanent_delete`: Outlook and iCloud) · the trash, within `WORKBENCH_MAIL_EMPTY_TRASH_MAX`, saying what remains |
| | `POST` `PATCH` `DELETE /mail/labels` · `POST /mail/labels/apply` | Gmail's labels; Outlook's and iCloud's folders on the same routes (`folder_management`), a folder holding anything refused |
| | `GET /mail/attachment` | One attachment, served as a file |
| | `GET /mail/attachment/preview` | The best one attachment can be read as, through `previews` (under the read window) |
| | `POST /mail/send` · `/mail/reply` · `/mail/forward` | Once per submission; words, files, an alias, formatted words (`html`, rebuilt by `infrastructure/email/html_body`) |
| | `GET /mail/reply-recipients` | Who a reply would reach, by the clients' own rule, read when the person answers |
| | `POST /mail/files` | A file of the device kept for a message, as an upload under the same deadline (`PlatformCapability.ATTACHMENTS`) |
| | `GET` `POST /mail/drafts` · `GET /mail/draft` · `POST /mail/drafts/send` · `/mail/drafts/trash` | Drafts, against their revision; files join and leave by name, and a quiet composer saves by itself (`draft_autosave_seconds`) |
| | `GET /mail/recipients` · `GET /mail/attachable` | Contact suggestions for an address being typed — a message's recipients AND an event's guests (`lib/workbench/recipients.ts`) · the person's own files a message may carry |
| | `GET` `PUT /mail/vacation` · `GET` `POST` `DELETE /mail/filters` | The vacation responder and the filters: Gmail's, and Outlook's automatic replies and rules |
| | `GET` `PUT /mail/signature` | What the active mailbox signs with, on every provider, from LIA's own records (`connectors/preferences/mail_signature`) |
| | `GET /mail/send-as` | The addresses a Gmail message may leave from (`send_as`) |
| Calendar | `GET /calendar/calendars` | The account's calendars, the settings' default named |
| | `GET /calendar/events` · `GET /calendar/event` | A window over the account's days · one event |
| | `POST` `PATCH` `DELETE /calendar/events` | Create (provider idempotency), change or delete — an occurrence alone |
| | `GET /calendar/search` | Words looked for in the calendars shown, a year on each side of today (`failed`, `truncated`) |
| | `POST /calendar/events/answer` | The person's answer to an invitation, the organiser told |
| | `POST /calendar/events/move` | An event to another calendar (`event_move`; with guests `event_move_with_guests`, Google alone) |
| | `POST` `PATCH` `DELETE /calendar/calendars` | The person's own calendars (`calendar_management`), `manageable` deciding whichever a request names |
| Calendar | `POST /calendar/events` (`recurrence`) · `PATCH` `DELETE /calendar/events` (`scope=series`) | A repeating event; a whole series, its first day kept |
| Contacts | `GET /contacts/export` · `POST /contacts/import` | A contact or the book as a vCard file (cut said in the name); a file, card by card, once per submission |
| | `GET` `PUT` `DELETE /contacts/photo` | A contact's photo: read as an image nothing can run, redrawn before it leaves |
| | `GET /contacts/member-of` · `POST /contacts/groups/join` · `/leave` · `PATCH` `DELETE /contacts/groups` | A contact's groups; a name nobody holds makes the group |
| | `POST /contacts/other/save` | Keeps a contact met in mail (`other_contacts`, Google) |
| Tasks | `GET` `POST` `PATCH` `DELETE /tasks/lists` | Lists, the settings' default named |
| | `GET /tasks/view` | What every list holds for today, overdue or the days ahead (`failed`, `truncated`) |
| | `POST /tasks/selection/completed` · `/delete` · `/move` | An act on ticked tasks, each answered; a move says what each is called from now on |
| | `POST /tasks/clear-completed` | Deletes what a list holds as done, within `WORKBENCH_TASKS_CLEAR_MAX` (`remaining`) |
| | `POST /tasks/place` | A task after a sibling, or first (`task_order`, Google) |
| | `POST` `PATCH` `DELETE /tasks/steps` | A task's steps (`task_steps`, To Do) |
| | `GET` `POST` `PATCH` `DELETE /tasks` | Tasks |
| | `GET /tasks/due` | The open tasks due over the days a calendar shows, every list read a few at a time (`failed`, `truncated`) |
| Contacts | `GET` `POST` `PATCH` `DELETE /contacts` · `GET /contacts/contact` | Contacts (a list sent replaces that list) |
| | `GET /contacts/groups` · `GET /contacts/other` | The account's groups, on the three providers · Google's « other contacts » (listed and searched; an act on one is refused unsent, the screen shows its row) |
| | `GET /contacts/history` | The latest mail each way and meetings each organised, by address; each source says why it has nothing |
| Files | `GET /files` · `GET /files/file` | A folder, a view (`file_views`) or a drive-wide search, by cursor, in the `order` asked (refused beside a search or a view) · one item and its breadcrumb |
| | `GET /files/download` · `GET /files/preview` | A file, a Google document exported · the best it can be read as (`previews`, under the read window) |
| | `GET` `PUT /files/text` | A plain text read whole with its version, written back on it (`editable`) |
| | `GET /files/quota` | What the account uses of its drive |
| | `POST /files/upload` · `POST /files/from-mail` | A file sent to a folder, under `WORKBENCH_UPLOAD_MAX_BYTES` · a mail's attachment kept there, each once per submission |
| | `POST /files/folders` · `PATCH /files/file` · `POST /files/move` · `POST /files/copy` | A new folder · a rename · a move, each answered · a copy, under way on Graph |
| | `PATCH /files/star` | A star (`file_views`) |
| | `POST /files/trash` · `POST /files/restore` | The trash and the way back, each answered |
| | `POST /files/delete` · `POST /files/trash/empty` | Deleting for good (`file_views`), by hand alone |
| | `GET` `POST /files/sharing` · `POST /files/sharing/link` · `POST /files/sharing/remove` | Who reaches an item, a person told by the drive · a link anyone can follow · an access taken back |
| Lights | `GET /lights` · `POST /lights/light` · `/lights/room` · `/lights/scene` | The bridge (rooms and zones, each lamp's reach), a lamp, a room or zone with its tone, a scene as it stands, in motion or held still |

## Original mail layout

`AuthoredHtmlFrame` parses the received markup under its own CSP, rewrites every link
(including SVG, `noscript` and template content), removes sender bases and refresh
directives, then renders the document in a sandbox whose only permissions are
`allow-popups allow-popups-to-escape-sandbox`: no script, no form, no same origin.
A link survives only as an `http`, `https` or `mailto` address with no credentials,
rewritten to `target="_blank"` with `rel="noopener noreferrer"`, whatever its sender
wrote; any other keeps its words and loses its address. A base target is only a
default: a sender's explicit target would otherwise override it. Embedded images
always show; remote ones load only once the reader asks, for that message, the
policy of the frame then adding `img-src https:`. A dark theme turns the whole page
down with one filter, whatever colours its author wrote, and turns its pictures back:
a fully saturated colour comes back a little paler, and the sender's own colours are
one click away. The DOM-dependent reader is loaded without SSR; template fragments are
walked iteratively. Styles, tables and readable text remain in the original layout.
An Android shell older than its `frameLinks` capability opens no tab from a sandboxed frame, and
a download lands nowhere ([measured](../guides/GUIDE_MOBILE_ANDROID.md)): the reader asks the shell
and says the links open from the text only to one that cannot.

## Refusals

Every refusal is a `detail.code` with a sentence in six languages on the page
(`workbench.errors.*`): `not_connected`, `reconnect_required`, `provider_rate_limited` (with
`retry_after`), `provider_unavailable`, `provider_refused`, `item_gone`, `stale_handle`, `conflict`,
`name_taken`, `name_refused`, `folder_not_empty`, `file_locked`, `too_large` (with `max_bytes`),
`too_many_cards`, `not_a_contacts_file`, `not_an_image`, `invalid_recipient`, `invalid_request`,
`event_left_behind`, `task_left_behind`, `event_start_outside_series`, `already_submitted` (with the
outcome), `outcome_unknown`, `not_supported_by_provider` (with the bound and field when a list is
too long).

## Adding a gesture or a provider

Contact listings follow `connectors/clients/normalizers/contact_order.py`: family
name, then given name, with the shared name fold. A name without a family part
uses its displayed value; an unnamed contact comes last. Google and Graph sort
at the provider before cursor pagination; iCloud sorts its complete result before
paging. Searches and groups returned as one result use the same key in the service.

1. Give the CLIENT the contract, on every provider of the category (parity), with its tests.
2. Make the assistant's tool reach it in the same change when it is not display-only (ADR-369 §4).
3. Declare it in `features.py` (and its bound in `PROVIDER_BOUNDS` when it has one); the page reads
   the descriptor and offers nothing else.
4. Call it through `open_tool_client` and `provider_call`; a module that imports a connector client
   is declared in `effects/direct_client_callers.py` (`NOT_A_CAPABILITY_READ`, D5).
5. Add its words in six languages and prove the screen in light, dark and OLED at 1440 and 390 px.

## What it records

Counts and codes only (`workbench_requests_total`, `workbench_provider_latency_seconds`,
`workbench_idempotency_replays_total`, `workbench_idempotency_unguarded_total`). Nothing reaches a
register, the token ledger, memory, habits, journals or open loops: an act the person does by hand
is not LIA's.
