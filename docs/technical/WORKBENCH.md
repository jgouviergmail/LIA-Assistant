# The workbench — « Tools »

The person's own door to their connected services: mail, calendar, tasks, contacts, files
(Google Drive or OneDrive) and Hue lights, consulted and acted on **by hand, with no model in the path**. The decisions are
[ADR-369](../architecture/ADR-369-Workbench-The-Persons-Own-Door-To-Their-Services.md); this page is
the map of the code. What a click asks of LIA from these screens is another door, in another bounded
context: [TOOL_ASSISTS.md](TOOL_ASSISTS.md).

## Opening a record from an assistant card

Decision record: [ADR-376](../architecture/ADR-376-A-Card-Opens-Its-Record-In-The-Tools-On-A-Signed-Proof-Of-Its-Source.md).

The native email, event, calendar, contact, task, file and Hue cards open their record
in Tools. The address is produced from the received provider identifier and its
received scope, never from a provider URL, a registry-id suffix or the current default
calendar/task list. An event needs its calendar; a task needs its list. A mail's
provider handle remains intact, including Apple's folder and UIDVALIDITY scope. A
file declares whether it is a folder. A Hue lamp's owner-device id is not a room id.

`agents/display/card_navigation.py` stamps the actual answering client/provider at
the common connector-tool boundary. Its signed envelope lives in `RegistryItemMeta.display`
and in the card's `data-card-target` attribute, outside model-facing payloads. The
signature binds the complete destination to the LIA account and the instance secret.
`core/content_source.py` supplies the existing credential-source fingerprint: OAuth
grant, Apple principal, or a known Hue bridge id. A bridge without that identity has
no guessed replacement from its IP address, token or lamp name.

The authenticated, capability-gated and read-rate-limited `POST /workbench/card-target`
revalidates the signature and freshly resolves the active provider/source at the
click. It fetches no record content and grants no mutation. A matching source returns
only the typed native address (`card_targets.py`); a missing or invalid proof, changed
source or unavailable connection returns an explicit refusal. Network errors and
timeouts do not open a third-party site as a fallback. The browser keeps the same
proof in the destination's `card_source` parameter. At request time,
`lib/workbench/card-source.ts` forwards it only from the current Tools page to that
same family's API routes: `apiClient` and XHR uploads use `X-LIA-Card-Source`, while
`apiEndpointUrl` adds the query proof for direct file/attachment downloads, contact
exports and multipart upload URLs. No third-party link receives it. CORS allows the
header only for the application's already allowed web origins.

The request-local `card_source.py` dependency accepts either transport; two present
proofs must be identical. It checks the signature against the authenticated account,
then `open_tool_client` checks the expected provider and source fingerprint on the
client actually acquired, before that client can read or act. A replacement source
returns HTTP409 `card_source_changed`, including a switch between admission and the
actual request. The two strict download query variants in `schemas/card_queries.py`
remove the transport proof before passing the unchanged business models to services.

This is a source constraint, not an item permission or a session-wide lock. It applies
only to the proof's family; auxiliary reads of another family keep their ordinary
provider resolution. The native tool still owns authentication, provider grants,
missing-item states and action validation. Requests without a proof remain ordinary
Tools navigation, including the explicit unscoped-tool fallback; nothing stores the
constraint globally after the source-bound page is left.

Archived cards keep their original proof. Older archives without one remain readable
but cannot target a record by guessing the current account; the interface explains
that limit and may offer the tool itself. Reconnection to another OAuth grant,
changing provider/Apple principal/Hue bridge cannot silently retarget the historical
record. A different LIA account UUID or signing secret invalidates the proof; cloning
both is not a separate identity boundary. Switching Tools off removes source actions
and leaves source titles/previews noninteractive, while preserving their content.
Unknown frontend availability offers no opening either. The API capability guard
remains authoritative, and withdrawing the capability cancels a pending browser open.

Source titles, file previews and explicit source actions use the same navigation
door. Contextual links (meeting attendance, directions, telephone, email addresses,
attachments and cited web sources) retain their separate meaning.

Source identity also applies before publication: Google Contacts record caches are
namespaced by the answering credential binding, and Apple's full contact book by its
principal. Old unscoped entries are cache misses, never proof of the currently
connected source; missing identity disables those record caches. Existing TTLs,
registered cache families and user invalidation remain in force. Gmail already scopes
its message cache by the OAuth grant; Apple's message cache and handles retain their
principal/folder/generation scope.

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

On narrow screens, Calendar keeps **New event** at the right of the same row as
search and **Refresh**. On desktop it stays in the calendar sidebar, with its icon
and label left-aligned. The existing calendar selection, permissions and creation
form remain the same.

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
| `task_dates.py` | A task's due is a DAY: written as Google's date or To Do's local midnight with its zone named (`due_zone`), read back through `core/task_due`, the door every reader of a task's day shares. |

Every form of the Tools opens and ends through `components/workbench/ToolForm.tsx`: a head at the
left, acts that stack the whole width on a phone, one neutral outlined « Cancel » and one way of asking
(`useToolConfirm`); a list is `components/ui/native-select.tsx`. `toolForm.guard.test.ts` refuses a
tool's own.

On the web side, the frame is `WorkbenchShell` (the availability read once, the row of tools
above the open one) and every vertical pane a person sizes by hand on a large screen is declared
once in `lib/workbench/panes.ts` (its bounds and the share of its row it may take), drawn through
`useWorkbenchPane` and moved by the shared window splitter `components/ui/pane-separator.tsx`; the
widths are a preference of the device (`stores/workbenchPanesStore.ts`). On a computer the section
runs the whole window: the dashboard layout gives it `PAGE_FRAME_WINDOW` (`lib/dashboard-nav.ts`)
from `lg`, and every other page keeps the rail.

The tool's name is said by the open pill of the rail, which also names the vendor
(`providerVendor`); the page's `h1` is for the outline and the ear, and the tool's actions follow
the rail through a portal (`WorkbenchActionsSlot`), so a tool starts right under them: on the
rail's own row from `xl`, on a line of their own below it, the search and **Refresh** at its start
and the act the tool leads with at its end (`WORKBENCH_HEADER_PRIMARY`). Its square buttons share
one size (`WORKBENCH_HEADER_ICON`). They hold
**Refresh** (`WorkbenchToolHeader`, `useToolRefresh`): the screen re-reads what it shows, and
coming back to the page after `WORKBENCH_RETURN_REREAD_MIN_MS` does it unasked. An unasked re-read takes nothing away (`useWorkbenchPage`, `useWorkbenchItem`): it
leaves alone a listing of several pages, a read still on its way and a failed one, and it keeps
what is on screen when it fails.

A tool's keys go through `useToolShortcuts`, declared with the header: never in a field or a
dialog, never with Ctrl, Cmd or Alt, switched off per device (`ShortcutsHelp`, WCAG 2.1.4). One tool
hands another what it starts through `lib/workbench/handoff`, held in an account-owned, expiring observable store and taken once through `useHandoff`, since
a subject has no place in an address a server logs; `useToolBridges` offers a way out only where its
tool is ready, and `seedInputDraft` leaves words for the chat the same way, unsent. A task handed
over opens the Tasks tool's « New task » form (`NewTaskDialog`), every value it carries shown, its
list and, with To Do, its importance, reminder and repetition; the quick add stays for a title typed
by hand. A message handed with `assisted` opens the composer on « Write from an instruction ». A
contact handed with a `phone` (the home's SMS sender) opens the new-contact form on that number,
and nothing empty is added beside it. Pending proposals never overwrite an open editor;
a notice names the wait, and closing that editor presents the proposal. Logout/account
change clears the handoff and native editor state. The same handoff serves application-wide
selection actions, including the memory settings form; see [Tool assists](TOOL_ASSISTS.md).
`useListSelection` is the selection every list shares: it belongs to one listing, and Shift ticks a
range.

The home opens its items here (owner, 2026-11-07, `docs/technical/BRIEFING_DOMAIN.md`), on the
addresses the tools already read. Two of them name something the screen must find first: an event
in the account's own calendar may come as `cal=primary`, the connector's alias, which
`useOwnCalendarAlias` names again by that calendar's real id once the calendars are read; a task
may sit past the pages the list read, so `useKeptTask` reads it alone and keeps it at the head of
the list (`WorkbenchPageState.keepItem`), where every act reaches it, its own page putting it back
in its place.

A document is read through `useShownDocument`, which starts a read once the page has settled, and
`ShownReading` (`components/workbench/ShownDocument.tsx`), which draws the wait, the refusal with
its second try, or the viewer the answer's type names. `viewers/PdfViewer.tsx` draws a PDF with
PDF.js (`lib/workbench/pdf-document.ts`, its runtime copied by `scripts/copy-pdf-runtime.mjs`), page
by page as they come near, `viewers/WordViewer.tsx` hands docx-preview's output
(`lib/workbench/word-html.ts`) to `AuthoredHtmlFrame`, and `viewers/MarkdownViewer.tsx` lets React
draw a Markdown. `DetailClose` is the way out of a detail: a cross beside the list, the tool's name
where the detail takes the screen. `DetailBar` holds it and what can be done, a task's detail
included: a tool declares its acts (`DetailAct`), the bar draws them as icons at its end at every
width, what is less common behind « … », never opened for one act. An act that must be told where
(`choices`, the calendar's « Move to… ») opens its own list under its icon, even for one place.
Where the room runs out, larger text on a small phone, the tool's name gives way, then the icons
take another line: an act is never cut. Whatever order a tool declares, every bar ends on the
deletion, then the question to LIA (`askAct`), « … » before them; the mail's reader, which draws its
own toolbar, keeps that order.

From `xl` the mailbox opens on the inbox's newest message (`useFirstLook`), the reader standing
beside a list it would replace below. Nobody opened it, so it rides no address, `useReadAfterLook`
leaves it unread and a message arriving does not take its place; closing it, opening a message or
leaving the inbox lets go of it for the visit.

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
| | `GET` `POST /mail/drafts` · `GET /mail/draft` · `POST /mail/drafts/send` · `/mail/drafts/trash` | Drafts, against their revision; files join and leave by name, and a quiet composer saves by itself (`draft_autosave_seconds`). A first save may name an `origin`: a reply or a forward kept in its thread, the provider's own reply or forward draft, saved once and never by itself |
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
| | `GET /tasks/task` | One task, whole: the home opens one past the pages read (`item_gone` when gone) |
| | `GET /tasks/due` | The open tasks due over the days a calendar shows, every list read a few at a time (`failed`, `truncated`) |
| Contacts | `GET` `POST` `PATCH` `DELETE /contacts` · `GET /contacts/contact` | Contacts (a list sent replaces that list) |
| | `GET /contacts/groups` · `GET /contacts/other` | The account's groups, on the three providers · Google's « other contacts » (listed and searched; an act on one is refused unsent, the screen shows its row) |
| | `GET /contacts/history` | The latest mail each way and meetings each organised, by `address`; the calls LIA placed and the texts received, by `phone` (one of the two at least); each source says why it has nothing (`not_requested` when nothing was given to look under); `no-store` |
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
`retry_after`), `provider_unavailable`, `provider_refused`, `item_gone`, `card_source_changed`, `stale_handle`, `conflict`,
`name_taken`, `name_refused`, `folder_not_empty`, `file_locked`, `too_large` (with `max_bytes`),
`too_many_cards`, `not_a_contacts_file`, `not_an_image`, `invalid_recipient`, `invalid_request`,
`event_left_behind`, `task_left_behind`, `event_start_outside_series`, `already_submitted` (with the
outcome), `outcome_unknown`, `not_supported_by_provider` (with the bound and field when a list is
too long). The six `assist_*` codes share this vocabulary: [TOOL_ASSISTS.md](TOOL_ASSISTS.md).

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
