# The workbench — « Tools »

The person's own door to their connected services: mail, calendar, tasks, contacts, Drive files
and Hue lights, consulted and acted on **by hand, with no model in the path**. The decisions are
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
| `clients.py` | `open_tool_client`: the category door (`open_active_client`), or `open_client_by_type` for Drive and Hue; no session held while a provider answers. |
| `calls.py` | `provider_call`: times one provider call, turns its failure into one refusal (by type and status, act-aware), counts it. |
| `errors.py` | The refusal vocabulary and `refuse()`. |
| `ids.py` | The shapes an id, a cursor or a name may take on the way in. |
| `rate_limits.py` | Per-account windows: read, write, send, bulk, download; `charge_selection` charges a selection of several as a bulk act. |
| `idempotency.py` | `run_once`: a submission key claimed in Redis before the provider call, settled `done` or `unknown`; a replay answers the stored outcome. |
| `downloads.py` | One download at a time per account, and the response a browser saves and never renders. |
| `selection_acts.py` | An act on a selection, item by item, a few at a time, each answered (`ActOutcome`). |

On the web side, the frame is `WorkbenchShell` (the availability read once, the row of tools
above the open one) and every vertical pane a person sizes by hand on a large screen is declared
once in `lib/workbench/panes.ts` (its bounds and the share of its row it may take), drawn through
`useWorkbenchPane` and moved by the shared window splitter `components/ui/pane-separator.tsx`; the
widths are a preference of the device (`stores/workbenchPanesStore.ts`).

## Routes

All under `/api/v1/workbench`, behind the capability guard and the session cookie.

| Tool | Method and path | What it does |
|---|---|---|
| — | `GET /workbench` | The tools the account can use, and the bounds they enforce |
| Mail | `GET /mail/folders` | The folder pane: system places, then the person's own folders |
| | `GET /mail/messages` | One page of a folder, narrowed by the person's words and chips |
| | `GET /mail/message` · `GET /mail/message/html` | One message (reading marks nothing read) · its HTML for the isolated frame |
| | `POST /mail/read-state` · `POST /mail/trash` | Read state, trash — each message answered |
| | `POST` `PATCH` `DELETE /mail/labels` · `POST /mail/labels/apply` | Gmail labels |
| | `GET /mail/attachment` | One attachment, served as a file |
| | `POST /mail/send` · `/mail/reply` · `/mail/forward` | Once per submission |
| | `GET` `POST /mail/drafts` · `GET /mail/draft` · `POST /mail/drafts/send` · `/mail/drafts/trash` | Drafts, against their revision |
| | `GET /mail/recipients` · `GET /mail/attachable` | Contact suggestions for an address being typed — a message's recipients AND an event's guests (`lib/workbench/recipients.ts`) · the person's own files a message may carry |
| | `GET` `PUT /mail/vacation` · `GET` `POST /mail/filters` | Gmail's vacation responder and filters |
| Calendar | `GET /calendar/calendars` | The account's calendars |
| | `GET /calendar/events` · `GET /calendar/event` | A window over the account's days · one event |
| | `POST` `PATCH` `DELETE /calendar/events` | Create (provider idempotency), change or delete — an occurrence alone |
| Tasks | `GET` `POST` `DELETE /tasks/lists` | Lists |
| | `GET` `POST` `PATCH` `DELETE /tasks` | Tasks |
| Contacts | `GET` `POST` `PATCH` `DELETE /contacts` · `GET /contacts/contact` | Contacts (a list sent replaces that list) |
| | `GET /contacts/groups` · `GET /contacts/other` | Google's groups and « other contacts » |
| Files | `GET /files` · `GET /files/file` | A folder or a Drive-wide search, by cursor · one item and its breadcrumb |
| | `GET /files/download` · `POST /files/trash` | A file, a Google document exported · the trash, each answered |
| Lights | `GET /lights` · `POST /lights/light` · `/lights/room` · `/lights/scene` | The bridge, a lamp, a room, a scene |

## Original mail layout

`MailHtmlFrame` parses the received markup under its own CSP, removes link
navigation (including SVG, `noscript` and template content), sender bases and
refresh directives, then renders the document in an opaque sandbox. A base
target is only a default: a sender's explicit target would otherwise override
it. The DOM-dependent reader is loaded without SSR; template fragments are
walked iteratively. Styles, tables and readable text remain in the original
layout, while remote resources and navigation stay disabled.

## Refusals

Every refusal is a `detail.code` with a sentence in six languages on the page
(`workbench.errors.*`): `not_connected`, `reconnect_required`, `provider_rate_limited` (with
`retry_after`), `provider_unavailable`, `provider_refused`, `item_gone`, `stale_handle`, `conflict`,
`name_taken`, `too_large` (with `max_bytes`), `invalid_recipient`, `invalid_request`,
`already_submitted` (with the outcome), `outcome_unknown`, `not_supported_by_provider` (with the
bound and field when a list is too long).

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
