# Workbench — the person's own direct door to their connected services

**Status**: design APPROVED by the owner on 2026-10-30 (Q1–Q5 and the section 14
recommendation); mock-ups under review; no code written.
**Date**: 2026-10-30.
**Decided by**: owner (Q1–Q5 of 2026-10-30) + engineering analysis of the same day.

## 1. Intent and why

A person connects their mailbox, calendar, tasks, contacts, Drive and Hue bridge to
LIA so the assistant can act on them. Today the only door onto those services is a
conversation: to check what LIA did, to tidy a mailbox, to move a meeting or to
switch a light off, the person must ask a model to do it. That costs tokens, takes
seconds, and is not deterministic.

The workbench is a new section of the dashboard, « Outils » / « Tools », where the
person consults and acts on those services **by hand, with no model in the path** —
the way they would in the provider's own application. It costs 0 token and 0 €,
answers at the provider's latency, and does exactly what was clicked.

It also prepares two later steps that are out of scope here: assisted actions from
the same screens (« ask LIA » with a prefilled draft), and the contextual activities
the world specification already asks for (consult an agenda, work with documents).

## 2. Goals, non-goals, anti-goals

**Goals**

- One section in the header, a rail on the left listing the six tools, one tool per
  screen: mail, calendar, tasks, contacts, files, lights.
- Every main action the provider's own application offers for those tools, bounded
  by what LIA's connector clients can do today plus the additions this design names.
- The same behaviour for the three providers of a category wherever the category
  has three (mail, calendar, contacts), two (tasks) or one (files, lights).
- Phone and WebView first: the rail is the phone's home screen, every screen works
  at 320 px with the software keyboard open.

**Non-goals (phase 1)**

- No model call of any kind: no summary, no drafting, no name resolution by
  embedding. « Ask LIA » buttons come in phase 2 as a prefilled chat draft.
- No local copy of provider data, no new database table, no synchronisation.
- No learning: nothing written to habits, memory, journals or open loops.
- Gestures absent from every client today and not named below (archive / move /
  star, meeting responses, recurrence authoring, Drive upload / rename / folders,
  attachments on a reply or a forward, Gmail restore and permanent delete) are
  phase 2.
- Three assistant conveniences are NOT drawn as workbench screens (owner,
  2026-10-30, section 14): « find availability » (a week grid shows it),
  spreadsheet / document reading and writing (a standard files app opens the
  document in its own editor — « Open in Drive »).

**Anti-goals (what would make this a failure even if it worked)**

- An edit that silently destroys data the provider holds (the second e-mail of a
  contact, the recurrence of an event).
- A screen that shows a page cut at a cap without saying so.
- A stale state after an action (a trashed mail still listed for a minute).
- An e-mail's HTML rendered with the application's own privileges.
- A ninth header destination that pushes the logout button off a 1280 px screen.

## 3. Decisions the owner took (2026-10-30)

| # | Decision | Consequence |
|---|---|---|
| D1 | One provider is active per category (mail, calendar, tasks, contacts); the rail shows that one, with no provider switch. | Each API response still names its provider, so an additive category later needs no change of shape. |
| D2 | A gesture that one provider's client already has must exist for the others — and whatever the clients gain for the workbench **reaches the assistant's tools in the same lot**. | Read/unread ×3 + a neutral assistant tool; all-day events ×3 + the calendar tools; multi-valued contacts ×3 + a non-destructive `update_contact`. Display-only contracts (an e-mail's HTML) are exempt: the model reads text, never markup (ADR-287). |
| D3 | E-mails render their HTML, isolated. | A `get_message_html` contract ×3 and a sandboxed `srcdoc` frame (section 8). |
| D4 | Contacts are edited multi-valued. | New typed-list write contract ×3; the single-value call keeps the other values. |
| D5 | **No register row** for anything the workbench does: these are not acts of LIA. | No consultation surface, no effect claim, no labels. Every workbench module that opens a client is declared in `effects/direct_client_callers.NOT_A_CAPABILITY_READ` with this decision as its written reason (the register answers « which capability LIA used »; a person acting by hand uses none). Send idempotency therefore uses Redis, not the ledger. |
| D6 | A tool whose connector is not connected stays visible, in a « To connect » group that links to Settings › Connectors; a tool the instance switches off is not drawn. | The availability payload carries three states (section 6.1). |

## 4. Facts the design rests on (verified in the code, 2026-10-30)

| # | Fact | Where |
|---|---|---|
| F1 | Six functional categories; Drive belongs to none; Apple has no tasks connector. | `connectors/models.py:280-316` |
| F2 | One door opens the active client of a category in a short session of its own and freshens the token after it closes (ADR-304); it covers calendar, email, contacts, tasks. Drive and Hue are in the client registry but not in the door. | `connectors/active_client.py:79-154`, `clients/registry.py:201,243` |
| F3 | The OAuth scopes already requested are read-write (`gmail.modify`, `calendar`, `drive`, `contacts`, `tasks`, Graph `*.ReadWrite`). | `core/constants.py:2843-2911` |
| F4 | A hard per-request ceiling of `api_max_items_per_request` (25, ≤ 50) applies to every provider listing; calendar and tasks listings are one request with no page token; Microsoft contacts ignore `page_token`. | `core/config/connectors.py:721-730`, `clients/google_calendar_client.py:341-375`, `clients/microsoft_contacts_client.py:148` |
| F5 | The normalised e-mail body is clean text, never markup; Gmail prefers `text/plain` and flattens HTML at extraction; the per-message cache stores the normalised form. | `clients/normalizers/email_message.py:59`, `clients/google_gmail_client.py:285-320,597-599` |
| F6 | Read/unread: Gmail's client can modify the `UNREAD` system label, but the label resolver skips non-`user` labels, so no assistant tool can mark a message read; Outlook reads `isRead` and never writes it; IMAP never sets `\Seen`. | `clients/google_gmail_client.py:1131-1146,1558-1560`, `clients/microsoft_outlook_client.py:63-69`, `clients/apple_email_client.py:262` |
| F7 | All-day events are READ by the three normalisers and WRITTEN by none; Google's `update_event` only preserves an existing all-day shape. | `clients/normalizers/calendar_normalizer.py:144`, `clients/google_calendar_client.py:156-167,581-599` |
| F8 | Contact reads are multi-valued and typed; contact writes replace each list with ONE value, on the three providers; Google re-reads the etag just before writing. | `clients/normalizers/contacts_normalizer.py:44-78`, `clients/google_people_client.py:560-595`, `clients/normalizers/microsoft_contacts_normalizer.py:266-270` |
| F9 | Drive: search, list, metadata, download in memory (10 MB default), export, trash. No upload, rename, move or folder creation. | `clients/google_drive_client.py:192-431` |
| F10 | Hue: lights (on, brightness, xy, mirek), rooms (on, brightness), scenes; a per-account Redis limiter; a colour-name resolver. | `clients/philips_hue_client.py:93,211-248,423-556` |
| F11 | Gmail search (60 s) and message (300 s) caches are not invalidated by a trash or a label change; a hit the search could not fetch is skipped in silence; the total is an estimate. | `clients/google_gmail_client.py:444-527` |
| F12 | The Gmail-style query language (`in:`, `is:unread`, `has:attachment`, dates) is translated for Graph and IMAP. | `clients/normalizers/graph_mail_query.py:84-172`, `clients/apple_imap.py:65` |
| F13 | A module that imports a client (the door included) must be declared: recorder, not-a-read with a reason, or debt. | `agents/effects/direct_client_callers.py:40-167` |
| F14 | A shipped feature needs an operator switch; the partition is checked both ways against a hand-kept list; a new settings key needs no migration. | `tests/unit/domains/feature_switches/test_capability_coverage.py:40-114`, `system_settings/models.py:169` |
| F15 | The header renders one table of destinations filtered by instance flags; `/config` publishes flags and effective capability states. | `apps/web/src/lib/dashboard-nav.ts:67-97`, `app/[lng]/dashboard/layout.tsx:63-111`, `api/v1/routes.py:472-544` |
| F16 | Google Workspace calls are not billed. | `usage_limits/cost_bearers.py:143-152` |
| F17 | The existing Gmail attachment proxy holds a `get_db` session across the provider call and serves `inline`; the Drive thumbnail proxy calls a public URL without the token. Neither is reused. | `connectors/router.py:159-241,1154-1203` |
| F18 | A `srcdoc` frame already renders under the production CSP and COEP (the skill widget), with `allow-scripts allow-popups`. | `apps/web/src/components/chat/SkillAppWidget.tsx:206-208,245` |
| F19 | `google_gmail_client.py` is frozen at 795 logical SLOC (786 today); `apple_contacts_client.py` 588/600; `apple_email_client.py` 557/600. | `tests/unit/file_size_baseline.json:36`, `scripts/audit/measure_sloc.py` |
| F20 | The frontend has no calendar, date-picker, rich-text or HTML-sanitising library; `rehype-sanitize` exists; `dangerouslySetInnerHTML` is forbidden for API data. | `apps/web/package.json`, `apps/web/CLAUDE.md` |
| F21 | `toolbox` already names the sandbox's library set (ADR-298, `skills/sandbox_toolbox.py`); `PlatformCapability.APPLICATION_TOOLS` already exists. | `core/constants.py:5226` |

## 5. Constraints that bind the build

- No transaction open across a network call (ADR-304): every provider call goes
  through `connectors/active_client`; no workbench route depends on `get_db`.
- A bound that is enforced is published (ADR-184); a count shown is exact or absent
  (ADR-185); a cut is stated.
- A generation whose outcome is unknown is never relaunched; a connector request is
  resent only when it cannot repeat an act (ADR-221).
- No PII above DEBUG (ADR-317): a workbench log line carries counts, codes, hosts.
- Switch removes the ability, never the record (ADR-280): the switch guards the
  workbench routes alone; the connectors themselves stay untouched.
- Every new file under 600 logical SLOC; frozen files only shrink (mixins for
  Gmail, Apple contacts, Apple mail additions).
- Six languages, strict key parity; backend payloads carry codes and label keys,
  never sentences.
- No new frontend dependency in phase 1 (ADR-112/331): calendar grids, date
  inputs and composition are hand-built on native controls.
- Prompt and manifest bounds come from ONE constant read by the planner manifest
  and the `@tool` schema (ADR-318 pattern) for the two assistant tools this design
  adds or changes.

## 6. Backend design

### 6.1 Bounded context `domains/workbench/` (REST, no LangGraph)

```
domains/workbench/
  __init__.py
  availability.py      # three states per tool + active provider + features
  features.py          # the capability descriptor per provider; boot completeness
  errors.py            # raisers on the central taxonomy (core/exceptions is frozen)
  rate_limits.py       # per-account windows: read, write, send, bulk, download
  idempotency.py       # Redis SET NX + TTL for sends and creates without provider idempotency
  schemas/             # request/response models per tool (Pydantic v2)
  router.py            # mounts the per-tool routers under /workbench, capability guard
  mail_router.py  mail_service.py
  calendar_router.py  calendar_service.py
  tasks_router.py  tasks_service.py
  contacts_router.py  contacts_service.py
  files_router.py  files_service.py
  lights_router.py  lights_service.py
```

- **Availability** (`GET /workbench`): for each of the six tools —
  `state: ready | not_connected | reconnect_required | unavailable`, `provider`
  (connector type or null), `features` (section 6.2), `limits` (page sizes, upload
  ceilings, drain bounds). `reconnect_required` comes from
  `provider_resolver.find_error_connector_type`; `unavailable` names a tool whose
  provider the instance withholds (no Drive OAuth client configured, Hue off).
  Read through `DetachedConnectorService().unit_of_work()` — one short session.
- **Descriptor** (`features.py`): a frozen table keyed by `ConnectorType` listing what
  each provider accepts, e.g. mail `{mark_read, trash, restore: false, labels:
  gmail only, drafts, html}`, calendar `{all_day, conference: google only,
  send_updates: google|graph}`, contacts `{multi_valued: true, groups: google only}`.
  A boot assert refuses a connector type of a workbench category with no entry
  (ADR-085). The UI offers only what the descriptor says (ADR-184).
- **Door**: `active_client.py` gains `open_client_by_type(connector_type, user_id)`
  (Drive) and a `HueBridgeCredentials` branch; the category door is unchanged.
- **Rate limits**: `create_user_rate_limiter` windows, each a setting with a
  constant default and `.env` entries: `WORKBENCH_READ_*`, `WORKBENCH_WRITE_*`,
  `WORKBENCH_SEND_*`, `WORKBENCH_BULK_*`, `WORKBENCH_DOWNLOAD_*`. A provider 429 is
  passed through typed with its `Retry-After` (ADR-108 amendment).
- **Idempotency**: a client-minted key per submission on `POST` sends and creates
  that carry no provider idempotency (mail, tasks, contacts). `SET NX` on
  `workbench:idem:{user_id}:{key}` (family declared `USER_RUNTIME` in
  `cache/key_families.py`, TTL a setting), written BEFORE the provider call with
  state `pending`, settled `done` or `unknown`. A resubmission answers the stored
  state (`409 already_submitted`, with the outcome) and never resends. The
  `unknown` state is written through a cancellation too (`except Exception`
  never sees `CancelledError`; ADR-263 amendment 2026-09-27 b). Calendar
  creates keep the provider's own idempotency (S1).
- **Errors**: one vocabulary of stable `detail.code`s, each with a sentence in six
  languages on the frontend (guarded both ways, the radio's pattern):
  `not_connected`, `reconnect_required`, `provider_rate_limited` (+ `retry_after`),
  `provider_unavailable`, `item_gone`, `stale_handle` (IMAP UIDVALIDITY, Gmail
  attachment), `conflict` (etag), `too_large`, `invalid_recipient`,
  `already_submitted`, `outcome_unknown`, `not_supported_by_provider`.
- **Identifiers** travel in the body or the query string, length-bounded and
  pattern-checked, never in the path (Graph ids and IMAP handles carry characters a
  path mangles).
- **Metrics** (`observability/metrics_workbench.py`): requests by tool/outcome,
  provider latency histogram by tool, downloads by outcome, idempotency replays.
  Every series on a Grafana panel of the connectors dashboard (metric coverage
  ratchet) with `or vector(0)`.
- **Spend**: none; no `TrackingContext`, no decision row (D5), no entry in
  `LLM_SPEND_ROADS`.

### 6.2 Client contracts added (parity across the providers of a category)

| Contract | Gmail | Graph | IMAP | Reaches the assistant as |
|---|---|---|---|---|
| `mark_read(message_ids, read: bool)` | `batch_modify_labels` ± `UNREAD` | `PATCH /me/messages/{id} {isRead}` | `mailbox.flag(uid, SEEN, read)` in the handle's folder | new `set_email_read_state_tool` (`reversible`, no HITL, domain `email`, provider-neutral manifest) |
| `get_message_html(message_id) -> str | None` | re-read the raw payload's `text/html` part | `body.content` when `contentType == html` | `msg.html` | nothing (display only, ADR-287) |
| Cursor paging where a listing has none today: `list_tasks` (Google `pageToken`, Graph `@odata.nextLink`), `list_connections` on Graph (`@odata.nextLink`; People and CardDAV already page) | — | `@odata.nextLink` | — | tool caps unchanged |
| Mail listing: already unified — `search_emails(query, headers_only=True, page_token)` answers `next_page_token` on the three providers (F12 for the folder query) | ✓ | ✓ | ✓ (offset token) | nothing new |
| Cache invalidation on every write of the same client (trash, read state, labels, drafts) | a per-account **generation** key prefixed to every cache key; a write bumps it | idem | idem | the assistant reads fresher data too |

| Contract | Google Calendar | Graph | CalDAV | Reaches the assistant as |
|---|---|---|---|---|
| `all_day: bool` on `create_event` / `update_event` | `start/end: {date}` (end exclusive) | `isAllDay: true`, midnight bounds in the event's zone | `DTSTART;VALUE=DATE` / `DTEND;VALUE=DATE` | `all_day` parameter on `create_event_tool` / `update_event_tool`, their manifests (one constant for both readers), the draft executor and the HITL card (a date, not « 00:00 → 00:00 ») |
| `list_events_window(calendar_id, time_min, time_max, *, bound)` — drains the provider's pages up to a published bound and returns `truncated` | `pageToken` loop | `$skip`/`nextLink` loop | single REPORT, cut at the bound | tool caps unchanged (ADR-286 paging stays the model's) |

| Contract | People | Graph | CardDAV | Reaches the assistant as |
|---|---|---|---|---|
| `update_contact(..., emails: list[TypedValue] | None, phones: list[TypedValue] | None, addresses: ...)` — a list given REPLACES that list; `None` keeps it; the legacy `email=`/`phone=` kwargs become « set the primary, keep the others » | `updatePersonFields` with the full list, etag kept | full `emailAddresses` / phones | vCard rewrite | `update_contact_tool` stops dropping the other values (behaviour change, documented) |

Nothing changes for the ReAct loop or the planner beyond the two tool additions and
the `all_day` parameter; the catalogue is generated from manifests, and the
registry smoke test exercises the new tool.

### 6.3 Per-tool scope (phase 1)

**Mail** — folders / labels (Gmail labels; Graph well-known folders; IMAP folders),
list by folder with cursor paging, search with the Gmail-style syntax and three
chips (unread, attachments, date range), reader (text, then HTML under D3),
attachments downloaded through a new door (`attachment`, `CSP: sandbox`, size
ceiling published, one download at a time per account), compose with
recipient suggestions (`email_share.recipient_match`, deterministic), reply /
reply-all / forward through `reply_recipients`, drafts (list, open, edit, send
once), trash, bulk trash / bulk read-state, read/unread. **Gmail only, because
the tools already exist in LIA and the descriptor says so** (owner's brief:
every main action the assistant's tools already offer): apply / remove labels on
a message or a selection, label create / rename / delete (system labels
refused, as the tools refuse them), and a « Mailbox settings » panel with the
vacation responder (read / write) and the filters (list + create — the client
has no delete, and the panel says so). Restore and permanent delete have a
client method but no tool today: phase 2.

**Calendar** — calendars with visibility toggles stored per device, Agenda (by
day) and Week views in phase 1, Month view in its own lot, event detail
(attendees with Google's response colours, conference link, location), create /
edit / delete with « notify attendees » where the provider has it, all-day
(D2), zone = the account's preference, DST-safe (02:30 tests), occurrences of a
series shown as the provider expands them (`singleEvents`), recurrence authoring
phase 2.

**Tasks** — lists, tasks with completed toggle (optimistic, rolled back on
failure), create / edit / delete, due date (Google: date only), subtasks shown
(Google `parent`), list create / delete.

**Contacts** — list with cursor, search, detail, create / edit / delete with
typed multi-valued e-mails, phones and addresses (D4), a contact-group filter
and « other contacts » (Google only, the three group tools exist), a link « See
the relationship » to the Relations page (`lib/relations-routing.ts`) when the
name folds to a known relation — an exact fold, no inference.

**Files** — breadcrumb navigation from the root, search (name / full text),
detail, download or export (Google Docs → PDF / DOCX, Sheets → XLSX, bounded by a
published ceiling), « Open in Drive », trash.

**Lights** — rooms, lights, scenes; controls drawn from the descriptor (a lamp
without colour shows no colour control); brightness and colour committed on
release, never on every slider tick; the per-account Hue limiter is the
backstop.

## 7. Frontend design

- **Navigation**: `dashboard-nav.ts` gains `{ segment: 'tools', labelKey:
  'navigation.tools', feature: 'workbench_enabled' }` placed right after `chat`;
  the icon joins `DESTINATION_ICONS` (type-enforced); the mobile menu follows for
  free. The header's `reachability` e2e is re-measured in the six languages at
  `lg`, `xl`, `2xl` (S9) before the lot closes.
- **Routes**: `app/[lng]/dashboard/tools/layout.tsx` (rail + outlet) and one page
  per tool: `mail`, `calendar`, `tasks`, `contacts`, `files`, `lights`. The selected
  item (a message, an event, a contact, a file) rides the query string; nothing a
  person typed does.
- **Rail**: a `<nav aria-label>` of links with `aria-current`, grouped « Tools » /
  « To connect » (D6); below `lg` the rail is the screen and a tool replaces it with
  a back button (ADR-227 §7). The rail subscribes to the `connectors`
  application resource so a connector unlinked elsewhere updates it without a
  reload.
- **Hooks**: `useWorkbenchAvailability`, one `useWorkbench<Tool>` per tool built on
  `useApplicationAccountQuery` (owner isolation) with a cursor model shaped after
  `useNeedlePage` (derived loading, late answers dropped); mutations through
  `useApiMutation`; a refresh re-reads in place (never an unmount).
- **Components**: `components/workbench/<tool>/`, every list through
  `RowActions` / `SelectionBar` / `EmptyState` / `Skeleton`; forms through
  `FormSection` + `FieldFrame`; destructive but recoverable acts (trash) need no
  dialog; nothing in phase 1 is irrecoverable.
- **E-mail HTML** (D3): an `<iframe sandbox="" referrerPolicy="no-referrer">` on
  `srcdoc`, the document prefixed by `<meta http-equiv="Content-Security-Policy"
  content="default-src 'none'; style-src 'unsafe-inline'">` so inline styles work
  and no remote resource loads (a parent policy and a `srcdoc` meta intersect:
  the stricter wins). With an opaque origin and no scripts there is no bridge
  back to the page, so the frame takes a fixed viewport height with its own
  scroll. « Show remote images » is phase 2.
- **Downloads** go through `apiEndpointUrl` (API origin, never a relative path).
- **i18n**: `navigation.tools`, `capabilities.items.workbench`,
  `workbench.*` (rail, each tool, every `detail.code`, every empty state with its
  exit), six locales, zh plurals duplicated.
- **Per-device preferences** (calendar visibility, default view, mail density) in
  `localStorage`, wrapped in try/catch, outside the account purge registry.
- **Layout**: full-height views subtract `--radio-banner-h`; the companion is never
  hidden automatically; every title icon is `text-primary`; one neutral line
  colour; sentence case; second person.
- **Themes (owner, 2026-10-30)**: every screen is built and proven in the THREE
  modes — light, dark and OLED (`html.dark[data-oled]`, a refinement of dark,
  never a theme of its own) — and under the five accent themes, through the
  app's tokens only (no literal colour outside the calendar colours and the
  attendee statuses, which are data). An HTML e-mail keeps its own light paper
  in the dark modes (its author's colours; inverting them breaks layouts and
  logos), a text-only message takes the theme. The contrast guard
  (`design-contrast.guard.test.ts`) and an e-2-e pass per mode close each lot.
- **Mock-ups approved (owner, 2026-10-30)**: canvas « Maquettes Outils »
  (claude.ai artifact WZCZCjhdrmTtaZvXgV7eqP) — nine screens, desktop 1536 px and
  phone 390 px. Outils sits right after Chat in the header; the tools pages take
  the full width up to 1536 px (three mail columns do not fit in 1280).

## 8. Security

- Session cookie only, as everywhere. The client never sends a `connector_id`;
  the server resolves the active provider.
- Every provider id validated for length and charset; IMAP handles must be
  runtime-shaped (legacy shapes refused, as the tools already do).
- Attachments and Drive files: `Content-Disposition: attachment`, a sanitised
  file name (the existing regex), `Content-Security-Policy: sandbox`,
  `X-Content-Type-Options: nosniff` (middleware), size ceiling before the body is
  read, streamed where the client streams, one in flight per account.
- E-mail HTML: never through the markdown pipeline, never
  `dangerouslySetInnerHTML`; only the sandboxed frame of section 7.
- Compose: recipients parsed strictly (`infrastructure/email/recipients.py`);
  no relay in phase 1 (the connected mailbox only).
- Logs: counts and codes above DEBUG; the log content guard applies.

## 9. Configuration and switch

- `PlatformCapability.WORKBENCH`, `env_flag="workbench_enabled"`,
  `SystemSettingKey.CAPABILITY_WORKBENCH_ENABLED`, `route_enforced=True`,
  family `work`, label key `capabilities.items.workbench`; added to the hand-kept
  `EXPECTED_CAPABILITIES`; **off the capability map** with a written reason (a
  door onto the connectors, whose per-account state the connector nodes already
  draw; nothing to count).
- `core/config/workbench.py` in the `Settings` MRO: the flag, the five rate
  windows, the drain bound, the download ceiling, the idempotency TTL, the page
  sizes — each with a constant default and lines in `.env.example`,
  `.env.prod.example` and the four demonstrator files (**off** on the
  demonstrator: its connectors are closed; the reason written in
  `CAPABILITIES OFFERED`).
- `/config.features.workbench_enabled` published; the web reads the effective
  state through `capabilityEnabled` (`lib/workbench/availability.ts`, the radio's
  shape).

## 10. Failure vocabulary and edge cases to prove

Connector absent / in error / revoked mid-session / scope missing / switched off
mid-session; provider 429, 5xx, timeout on a write (`outcome_unknown`, the key
kept); etag conflict; item gone between list and click; stale IMAP handle;
expired Gmail attachment handle; empty folder vs empty search (`reason`);
skipped search hits (count stated); unreadable address; attachment above the
ceiling; IMAP draft changing id on save; DST gap and overlap; all-day across
zones; event across midnight; recurring occurrence edit (the occurrence, never
the series, in phase 1 — and said); Google Docs native export; file too large;
Drive shortcut; shared drives invisible (stated); lamp without colour; bridge
unreachable; slider dragged fast; account switch; two tabs.

## 11. Testing

- **Backend unit**: availability (three states, switch off), descriptor
  completeness, services with doubles built from the real producers (never
  `cal.name = "X"`), parity tests ×3 per new contract on realistic payloads
  (`httpx.MockTransport`), routers (auth, guard, 422 on an oversized id, 429 with
  `Retry-After`, every code mapped), idempotency (pending / done / unknown, replay
  answers without resending), downloads (headers, 413, name sanitised), the
  assistant's two tools (registry smoke, manifest ↔ schema bound, HITL card shape
  for an all-day event).
- **Guards to turn green**: capability coverage and route wiring,
  `direct_client_callers` (NOT_A_CAPABILITY_READ entries with D5), env template
  parity (six files), metric coverage ratchet, file-size and CC ratchets, log
  content guard, Redis key family guard, language default guard.
- **Integration**: Redis — limiter windows, cache generation bump, idempotency
  key states (`TEST_REDIS_URL` on 127.0.0.1, run from the host).
- **Frontend unit**: hooks (owner isolation, cursor, late answer dropped,
  refresh in place), rail (`aria-current`, three states, exits), drill-down at
  390 px, the frame's exact attributes, compose (recipients, ceiling, double
  submit guard), calendar (zone, DST, all-day, multi-day, overlaps, « +N »), tasks
  (optimistic toggle rollback), contacts multi-valued editor, files breadcrumb,
  lights (commit on release, controls from the descriptor), accessible names in
  en and fr, six-locale parity.
- **E2E hermetic**: one journey per tool (success, riskiest failure, keyboard),
  reconnection, header reachability ×6 languages, 390 px, axe, 320 px and zoom.
- **Measured on dev before trusted** (owner's account, every real write with
  explicit accord; Graph and iCloud by doubles only — no live account):
  S1 Gmail page latency at 25 metadata hits; S2 Graph id charset (deferred until
  Outlook reconnects); S5 export sizes; S6 all-day on Google (Graph / CalDAV by
  doubles); S7 People multi-valued write with etag; S9 header width in German;
  S10 WebView download (Android).

## 12. Lots, order and estimates (hours of the author's continuous work, gates and proofs included)

| Lot | Content | Estimate |
|---|---|---|
| L0 | Golden tests of the six clients to be extended; S1, S5, S7, S9; naming check; this document's approval | 2–3 h |
| L1 | Backend base: switch, settings + six `.env`, domain, `GET /workbench`, descriptor + boot assert, door extension, rate limits, errors, metrics + panel | 2,5–3,5 h |
| L2 | Client contracts ×3 (6.2) + the assistant's `set_email_read_state_tool`, `all_day` on the calendar tools, non-destructive `update_contact_tool`, manifests, HITL card, mixins for frozen files | 6–8 h |
| L3 | Frontend base: destination, rail, drill-down, availability hook, cursor hook, coverage thresholds | 2–3 h |
| L6 | Tasks (first full traversal of the chain) | 2–3 h |
| L9 | Lights | 2 h |
| L4 | Mail, text reader — Gmail labels and mailbox settings included | 9–12 h |
| L4b | Mail HTML: `get_message_html` ×3 + sandboxed frame | 2–3 h |
| L5 | Calendar: Agenda + Week, detail, CRUD, all-day, Meet | 5–6 h |
| L5b | Month view | 2 h |
| L7 | Contacts multi-valued | 3–4 h |
| L8 | Files | 2–3 h |
| L10 | Hardening: a11y matrix (Firefox/WebKit), headers, perf, `task ci:fast` | 2–3 h |
| L11 | ADR-368, `docs/technical/WORKBENCH.md`, INDEX, ARCHITECTURE, CONNECTORS_PATTERNS, knowledge corpus, FAQ ×6, living maps ×6, CLAUDE.md pointer + `docs:sync-agents`, design skill, CHANGELOG | 3–4 h |
| | **Total** | **≈ 45–60 h** |

Tasks and lights come before mail and calendar on purpose: the two simplest tools
traverse the whole chain (switch → descriptor → door → rail → phone → e2e) after
about fifteen hours, so a defect of the base is paid there.

What lengthens the calendar without being the author's time: the owner's accord
before each real write on their account; reconnecting Outlook for any Microsoft
measurement; e2e proof builds (wall clock, ENOMEM constraints known); validations
between lots.

## 13. Left to the builder (settled calls, open to correction)

- Landing: `/dashboard/tools` opens the first `ready` tool in rail order on desktop,
  and the rail itself below `lg`.
- Rail order: mail, calendar, tasks, contacts, files, lights.
- The « Send » button is the confirmation; no second dialog (ADR-316's doctrine);
  trash needs none either (recoverable); nothing irrecoverable ships in phase 1.
- Code name `workbench` everywhere in code and settings; URL segment `tools`;
  label « Outils » / « Tools ».
- Compose attachments come from the person's own generated files and uploads
  (the email_share doors), not from the file system of the device — phase 2 may
  add a native picker.
- The HTML frame has a fixed height with its own scroll (no bridge, by design).
- Rate-limit defaults, each a setting the operator tunes in `.env`: read 120 /
  min, write 30 / min, send 10 / min, bulk 6 / min, download 10 / min, per
  account. Drain bound of a calendar window: 500 events. Download ceiling:
  25 MB. Idempotency TTL: 24 h.
- « Notify attendees » is a checkbox on calendar update and delete, checked by
  default where the provider carries it (Google `sendUpdates`, Graph), absent
  elsewhere (the descriptor says).
- Date and time inputs are native controls; the page sends the WALL time plus
  the account's zone id, never an offset — the calendar clients take exactly
  that pair (`start_datetime` without offset + `timezone`).
- Mail folders come from `list_labels` on the three providers; Gmail draws its
  system labels as folders (Inbox, Sent, Drafts, Trash, Spam, Starred) and its
  user labels under them.

## 14. Assistant conveniences left out (resolved 2026-10-30)

The brief asks for « every main action the tools already offer ». Three existing
tools are assistant conveniences rather than standard application gestures:
`find_availability_tool`, `read_spreadsheet_tool` / `write_spreadsheet_tool`,
`read_document_tool` / `append_document_text_tool`. **Owner decision: not in
the workbench** — a week grid shows availability, and a files app opens a
document in its editor (« Open in Drive »). Drawing them would have meant
inventing screens no mail or files application has.
