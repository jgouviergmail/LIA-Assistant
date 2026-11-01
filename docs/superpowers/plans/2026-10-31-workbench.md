# Workbench (« Outils ») — implementation plan

> **For agentic workers:** executed INLINE by the main session (owner directive: no
> subagent), with superpowers:executing-plans and superpowers:test-driven-development. Steps
> use checkbox (`- [ ]`) syntax. Nothing is committed and nothing is staged (owner
> directive, tree shared with the MCP session `lia-b6`): a task ends on its ledger line in
> `.superpowers/sdd/2026-10-31-workbench/progress.md`.

**Goal:** a « Tools » section of the dashboard where the person reads and acts on their
mail, calendar, tasks, contacts, Drive files and Hue lights BY HAND — no model in the path,
0 token, 0 € — with the provider parity and the assistant-tool updates the owner decided.

**Architecture:** a REST bounded context `domains/workbench/` (no LangGraph, no database
table, no register row) opens every provider client through the ADR-304 door, answers in
the connectors' normalised vocabularies, refuses with stable `detail.code`s, and is guarded
by one operator switch. The frontend is a rail + one screen per tool under
`/dashboard/tools`, built on the app's tokens and primitives, drill-down below `lg`.

**Tech stack:** FastAPI, Pydantic 2, httpx clients, Redis (rate limits, idempotency, cache
generations), Prometheus; Next.js 16 / React 19 / Tailwind v4, vitest, Playwright + axe.

**Spec:** `docs/superpowers/specs/2026-10-30-workbench-design.md` (approved 2026-10-30;
mock-ups canvas `WZCZCjhdrmTtaZvXgV7eqP`).

## Global constraints

- CLAUDE.md (root + `apps/web/CLAUDE.md`) and the memory directives apply; inline only;
  no git action; never `git add`; never revert a change that is not this programme's.
- D1 one active provider per category; D2 a gesture one provider's client has exists for
  the others AND reaches the assistant's tools in the same lot (display-only HTML exempt);
  D3 e-mail HTML only in a sandboxed `srcdoc` frame; D4 contacts written multi-valued;
  D5 NO register row (consultation, effect, decision) — every workbench module that opens
  a client is declared in `effects/direct_client_callers.NOT_A_CAPABILITY_READ` with D5 as
  its reason; D6 unconnected tools drawn in « To connect », instance-withheld ones not drawn.
- No model call, no `TrackingContext`, no entry in `LLM_SPEND_ROADS`.
- ADR-304: no workbench route depends on `get_db`; every route authenticates through
  `get_current_active_session_for_stream`; every provider client is opened through
  `connectors/active_client` (category door or `open_client_by_type`).
- ADR-184: a bound that is enforced is published (`GET /workbench` → `limits`, `bounds`);
  ADR-185: a count shown is exact or absent, a cut is stated (`truncated`, `skipped`).
- ADR-221: a send/create whose outcome is unknown is never relaunched; the idempotency key
  settles `unknown` (cancellation included) and a replay answers it.
- ADR-317: workbench log lines carry counts, codes, provider types — never a subject, an
  address, a name, a file name, a query.
- Identifiers travel in the body or the query string (bounded length, checked charset),
  never in the path.
- Every new file < 600 logical SLOC (`scripts/audit/measure_sloc.py`); frozen files only
  shrink: `google_gmail_client.py` 786/795, `apple_contacts_client.py` 588/600,
  `apple_email_client.py` 557/600, `calendar_tools.py` 1127/1150,
  `google_contacts_tools.py` 1210/1233, `emails_tools.py` 977/997 — growth goes to mixins
  or new modules.
- Six languages, strict key parity (`lia-i18n` skill: script FILES, read+write in one pass,
  this programme's keys only); zh `_one` duplicated; backend payloads carry codes and enums,
  never sentences.
- No new frontend dependency (ADR-112/331): grids, date inputs, colour inputs are native.
- Themes: every screen proven in light, dark and OLED (`html.dark[data-oled]`) and the five
  accents, through tokens only (literal colours only for calendar colours and attendee
  statuses, which are data); an HTML e-mail keeps its light paper; text follows the theme.
- ADR number reserved by coordination: **ADR-369** (ADR-368 is the MCP session's).
  No Alembic migration in this programme (head stays `278c441eaae6`, the MCP session's).
- Tests: unit on the host venv (`apps/api/.venv/Scripts/pytest`); integration on the host
  with testcontainers, `--no-cov`, `TEST_REDIS_URL=redis://127.0.0.1:<port>/15`; vitest via
  `task test:frontend`; e2e and proof builds in `lia-web-dev`, ALONE, under
  `.superpowers/sdd/E2E_BUILD.lock` (session name + start time; checked before, removed
  after); runtime proofs on Docker dev (no stack recreation, no dev DB reset).
- Real writes on the owner's provider accounts only with the owner's explicit accord
  (`[LIA-TEST]` items, cleaned up); Microsoft Graph and iCloud by doubles only.

## Review focus

1. **A provider page cut at its ceiling** (`api_max_items_per_request`, 25) — the list says
   more exists (`next_page_token`) and never shows a short page as the whole folder
   (Tasks 6.1, 4.2, 7.1, 8.1).
2. **A write followed by a read within the cache TTL** — the trashed / read / relabelled mail
   is not served stale from the Gmail or IMAP cache (Task 2.2, proven again in 4.3).
3. **A timeout after a send left** — the composer never re-sends by itself; a second click
   with the same key answers `already_submitted` with `outcome: unknown` (Tasks 1.4, 4.5).
4. **An all-day event across a DST change and across zones** — the date the person picked
   is the date stored (end exclusive at the provider, inclusive on screen) on the three
   providers and in the HITL card (Tasks 2.4, 5.2).
5. **A contact with two e-mails edited by the assistant's legacy `email=`** — the second
   e-mail survives on the three providers (Task 2.5).

Each line's test lives in the named task.

---

## Lot L0 — Baseline, measurements, ledger

### Task 0.1 — Ledger and naming check

**Files:** create `.superpowers/sdd/2026-10-31-workbench/progress.md`.

- [ ] Check the names are free: `grep -rn "workbench" apps/api/src apps/web/src` returns
  nothing; `apps/web/src/app/[lng]/dashboard/tools` does not exist; `navigation.tools` and
  `workbench.` are absent from `apps/web/locales/en/translation.json`.
- [ ] Ledger line « L0 started » with the tree state (counts of staged / modified / untracked).

### Task 0.2 — Golden net of the client behaviours the programme must NOT change

**Files:**
- Create: `apps/api/tests/unit/domains/connectors/clients/test_workbench_client_golden.py`
- Create: `apps/api/tests/unit/domains/connectors/clients/golden/workbench_client_requests.json`

Capture, through `httpx.MockTransport` (Google, Graph) and the existing CalDAV / IMAP
doubles of the client test suites, the exact requests these produce TODAY:
`create_event` / `update_event` for a TIMED event (×3 providers), `update_contact` with
`name`, `organization`, `notes` only (×3), `list_tasks` first page (×2),
`search_emails(headers_only=True)` first page (×3), Gmail `batch_modify_labels`.

- [ ] Write the capture test: a helper records method, path, query and JSON body per call;
  `UPDATE_GOLDEN=1` writes the file; otherwise the test compares byte for byte.
- [ ] Run with `UPDATE_GOLDEN=1`, inspect the file (no PII: fixture values only), then run
  without it: PASS.

### Task 0.3 — Measurements before trusting

**Files:** scripts in `.superpowers/sdd/2026-10-31-workbench/` (not in the repo).

- [ ] S1 — Gmail metadata page latency: `docker exec lia-api-dev python <script>` opening the
  owner's dev mailbox through `open_active_client("email", …)`, timing
  `search_emails("in:inbox", max_results=25, headers_only=True)` cold and warm, five runs;
  record timings and hit count only (read-only, nothing printed from the messages).
- [ ] S5 — Drive export sizes: metadata only (`size`, `mimeType`) of the dev account's ten
  largest Google-native files; no content downloaded.
- [ ] S9 — header width: Chrome DevTools on the dev web app, `/fr|de|en|es|it|zh/dashboard`
  at 1024, 1280 and 1536 px, record the header nav's `scrollWidth - clientWidth` and the
  logout button's right edge — the margin a ninth label must fit in.
- [ ] Ledger: the three measurements, verbatim.

---

## Lot L1 — Backend base

### Task 1.1 — Settings, constants, operator switch, router wiring

**Files:**
- Modify: `apps/api/src/core/constants.py` (one `WORKBENCH_*` block, after the e-mail share
  block), `apps/api/src/core/config/__init__.py` (MRO),
  `apps/api/src/domains/system_settings/models.py` (`CAPABILITY_WORKBENCH_ENABLED`),
  `apps/api/src/domains/feature_switches/registry.py` (`PlatformCapability.WORKBENCH`, spec),
  `apps/api/src/domains/capabilities/service.py` (`CAPABILITIES_OFF_THE_MAP` reason),
  `apps/api/src/api/v1/routes.py` (include under the flag; `/config.features.workbench_enabled`),
  `.env.example`, `.env.prod.example`, `.env.demo-instance.example`,
  `.env.demo-instance.prod.example`, local `.env`, `.env.prod`, `.env.demo-instance`,
  `.env.demo-instance.prod` (block appended by a script that prints nothing),
  `apps/web/src/hooks/useAppConfig.ts` (feature type)
- Create: `apps/api/src/core/config/workbench.py`
- Test: `apps/api/tests/unit/core/config/test_workbench_settings.py`; update
  `tests/unit/domains/feature_switches/test_capability_coverage.py` (`EXPECTED_CAPABILITIES`),
  `tests/unit/domains/feature_switches/test_capability_route_wiring.py`
  (`WORKBENCH: "src.domains.workbench.router"`), and whichever of
  `test_installer_wizard_backend_alignment.py` / `test_demo_instance_exposed_routes.py`
  enumerates capability flags or demo routes.

**Interfaces — produces:**
```python
class WorkbenchSettings(BaseSettings):
    workbench_enabled: bool = True
    workbench_read_rate_limit_calls: int = 120;  workbench_read_rate_limit_window_seconds: int = 60
    workbench_write_rate_limit_calls: int = 30;  workbench_write_rate_limit_window_seconds: int = 60
    workbench_send_rate_limit_calls: int = 10;   workbench_send_rate_limit_window_seconds: int = 60
    workbench_bulk_rate_limit_calls: int = 6;    workbench_bulk_rate_limit_window_seconds: int = 60
    workbench_download_rate_limit_calls: int = 10; workbench_download_rate_limit_window_seconds: int = 60
    workbench_page_size: int = 25            # published as min(this, api_max_items_per_request)
    workbench_calendar_window_max_events: int = 500
    workbench_download_max_bytes: int = 25 * 1024 * 1024
    workbench_idempotency_ttl_seconds: int = 86_400
    workbench_bulk_max_items: int = 50       # largest selection one bulk act carries
```
Every default is a `WORKBENCH_*_DEFAULT` constant; every field has `ge`/`le` and a
description. Spec: `family="work"`, `route_enforced=True`, label `capabilities.items.workbench`.
Off-the-map reason: « A door onto the connectors, whose per-account state the connector
nodes already draw; it keeps no state of its own, so a star could only ever be lit. »

- [ ] RED: `test_workbench_settings.py` — every default equals its constant; bounds refuse
  0 and an over-limit value; capability coverage and route wiring tests red on the new member.
- [ ] GREEN: settings module, MRO, constants, switch, map reason, router include (empty
  router module created in Task 1.5 — create the file now with the bare `APIRouter`).
- [ ] Env templates: block with comment header « Workbench (Tools section, ADR-369) »,
  `WORKBENCH_ENABLED=true` in main templates, `false` in the four demonstrator files with
  the reason written in their `CAPABILITIES OFFERED` block; the env-template parity guard
  `tests/unit/test_env_template_parity_guard.py` green.
- [ ] Run: `cd apps/api && .venv/Scripts/pytest tests/unit/core/config tests/unit/domains/feature_switches tests/unit/test_env_template_parity_guard.py -q` → PASS.

### Task 1.2 — Error vocabulary and provider-failure classification

**Files:**
- Create: `apps/api/src/domains/workbench/__init__.py`, `apps/api/src/domains/workbench/errors.py`
- Test: `apps/api/tests/unit/domains/workbench/test_errors.py`

**Interfaces — produces:**
```python
NOT_CONNECTED = "not_connected"            # 409
RECONNECT_REQUIRED = "reconnect_required"  # 409
PROVIDER_RATE_LIMITED = "provider_rate_limited"  # 429, retry_after beside it + Retry-After header
PROVIDER_UNAVAILABLE = "provider_unavailable"    # 502
ITEM_GONE = "item_gone"                    # 404
STALE_HANDLE = "stale_handle"              # 409
CONFLICT = "conflict"                      # 409 (etag / revision)
TOO_LARGE = "too_large"                    # 413, max_bytes beside it
INVALID_RECIPIENT = "invalid_recipient"    # 422
ALREADY_SUBMITTED = "already_submitted"    # 409, outcome: "done" | "pending" | "unknown"
OUTCOME_UNKNOWN = "outcome_unknown"        # 504
NOT_SUPPORTED_BY_PROVIDER = "not_supported_by_provider"  # 422
WORKBENCH_CODES: Final[frozenset[str]]
def refuse(code: str, **detail: Any) -> NoReturn            # BaseAPIException, detail={"code", **detail}
def refusal_for(exc: BaseException, *, act: bool) -> tuple[str, dict[str, Any]]
def refuse_provider_failure(exc: BaseException, *, act: bool) -> NoReturn
```
`refusal_for` classifies STRUCTURALLY (status codes through `__cause__`, exception classes —
never message text, guard `test_no_message_substring_classification_guard.py`):
`ConnectorAPIError` 429 → rate limited with its `Retry-After`; 404/410 → gone; 409/412 →
conflict; 401 / `ConnectorTokenExpiredError` → reconnect; 403 → reconnect (scope);
`MailboxDraftNotFoundError` → gone; `MailboxDraftChangedError` → conflict; IMAP stale
handle error → stale_handle; `httpx.TimeoutException` / 5xx → `OUTCOME_UNKNOWN` when
`act=True` (the request may have reached the provider), `PROVIDER_UNAVAILABLE` otherwise;
`httpx.ConnectError` → `PROVIDER_UNAVAILABLE` (never left).

Also create `apps/api/src/domains/workbench/ids.py`:
```python
ProviderId = Annotated[str, StringConstraints(min_length=1, max_length=1024, pattern=r"^[\x21-\x7e]+$")]
```
printable ASCII without whitespace or control characters (IMAP handles carry `/` inside a
folder name, so the id never travels in a path); every client that interpolates an id into a
provider URL quotes it (`quote(id, safe="")`) — checked for each client a route reaches,
fixed where it does not (Task 10.1 re-verifies).

- [ ] RED: one test per row above; `refuse()` sets status and `detail.code`; the 429 carries
  `retry_after` and the header; a message containing « rate » with no status classifies as
  unavailable (structural only); `ProviderId` refuses an empty id, a newline, 1 025 chars,
  and accepts an IMAP handle with `/`.
- [ ] RED: frontend pairing guard (radio pattern) — every code in `WORKBENCH_CODES` has
  `workbench.errors.<code>` in the six locales, and `apps/web/src/lib/workbench/errors.ts`
  `WORKBENCH_ERROR_CODES` equals `WORKBENCH_CODES` (test skips nothing: it reads the files;
  the TS file and the keys are created in Task 3.2 — the test stays red until then and is
  recorded in the ledger as an expected red across L1→L3).
- [ ] GREEN, run `pytest tests/unit/domains/workbench/test_errors.py -q` (pairing test
  excepted until L3).

### Task 1.3 — The door for Drive and Hue

**Files:**
- Modify: `apps/api/src/domains/connectors/active_client.py`
- Test: `apps/api/tests/unit/domains/connectors/test_active_client_by_type.py`

**Interfaces — produces:**
```python
@asynccontextmanager
async def open_client_by_type(
    connector_type: ConnectorType, user_id: UUID
) -> AsyncIterator[ActiveClient | ClientUnavailable]
```
One short session reads the connector row: absent or not `ACTIVE` → `NO_CONNECTOR`; Hue →
`get_hue_credentials`; OAuth (Drive) → `read_connector_credentials` then `.fresh()` AFTER the
session closed; client built on `DetachedConnectorService()`, closed on every path. Check
first how `PhilipsHueClient` refreshes a REMOTE-mode token (`hue_remote_target`) and keep
that path (no new refresh door).

- [ ] RED: absent row, inactive row, no credentials, Drive happy path (token freshened after
  the session closed — asserted by call order on doubles), Hue happy path, client closed when
  the caller raises.
- [ ] GREEN; existing `tests/unit/domains/connectors/test_active_client*.py` still PASS.

### Task 1.4 — Rate limits and send idempotency

**Files:**
- Create: `apps/api/src/domains/workbench/rate_limits.py`, `apps/api/src/domains/workbench/idempotency.py`
- Modify: `apps/api/src/infrastructure/cache/key_families.py` (`"workbench:idem"` →
  `USER_RUNTIME`), `apps/api/src/core/constants.py` (`REDIS_KEY_WORKBENCH_IDEMPOTENCY_PREFIX`)
- Test: `apps/api/tests/unit/domains/workbench/test_idempotency.py`,
  `apps/api/tests/integration/domains/workbench/test_idempotency_redis.py`

**Interfaces — produces:**
```python
rate_limit_read / rate_limit_write / rate_limit_send / rate_limit_bulk / rate_limit_download
# create_user_rate_limiter("workbench_<window>", …, authenticate=get_current_active_session_for_stream)

class SubmissionOutcome(str, Enum): PENDING = "pending"; DONE = "done"; UNKNOWN = "unknown"
async def run_once(
    user_id: UUID, key: UUID, operation: Callable[[], Awaitable[T]],
    *, record: Callable[[T], dict[str, str]] = lambda _: {},
) -> T
```
`run_once`: `SET NX EX` `{state: pending, token}` on `workbench:idem:{user_id}:{key}`; an
existing key → `refuse(ALREADY_SUBMITTED, outcome=<state>, **stored_ref)`; the operation
runs; success → `done` + `record(result)` (an id, never content) under a compare-and-set on
the token (Lua); a classified certain failure (`refusal_for(..., act=True)` gives anything
but `OUTCOME_UNKNOWN`) → the key is DELETED (compare-and-delete on the token) so the person
may try again; `OUTCOME_UNKNOWN`, any other exception and `CancelledError` → `unknown`
(written through the cancellation, `write_through_cancellation` pattern), then re-raise.
Redis down at the claim → the operation runs WITHOUT the guard and a counter says so (our
throttle never makes a send fail — ADR-254 doctrine), logged at WARNING with codes only.

- [ ] RED (unit, fake Redis): fresh → done; replay done → 409 with ref; replay pending →
  409 pending; timeout → unknown then replay 409 unknown; certain failure → key gone, retry
  runs; cancellation → unknown; Redis error at claim → runs, counter incremented.
- [ ] RED (integration, real Redis on 127.0.0.1/15): two concurrent `run_once` with one key →
  exactly one operation call; TTL set; a stale token cannot settle a reclaimed key.
- [ ] GREEN; key-family guard `tests/unit/test_redis_key_family_guard.py` PASS.

### Task 1.5 — Descriptor, availability, `GET /workbench`, metrics

**Files:**
- Create: `apps/api/src/domains/workbench/features.py`, `availability.py`, `clients.py`,
  `schemas/__init__.py`, `schemas/common.py`, `router.py`,
  `apps/api/src/infrastructure/observability/metrics_workbench.py`
- Modify: `infrastructure/observability/grafana/dashboards/10-oauth-connectors-mcp.json`
  (a « Workbench » row: requests by tool/outcome, p95 provider latency, downloads, idempotency
  replays — every expression with `or vector(0)`, panels `"noValue": "0"`),
  `apps/api/src/domains/agents/effects/direct_client_callers.py` (D5 entries for every
  workbench module importing the door or a client, added as each module appears)
- Test: `tests/unit/domains/workbench/test_features.py`, `test_availability.py`,
  `test_router_availability.py`

**Interfaces — produces:**
```python
class WorkbenchTool(str, Enum): MAIL="mail"; CALENDAR="calendar"; TASKS="tasks"; CONTACTS="contacts"; FILES="files"; LIGHTS="lights"
class ToolState(str, Enum): READY="ready"; NOT_CONNECTED="not_connected"; RECONNECT_REQUIRED="reconnect_required"; UNAVAILABLE="unavailable"
class WorkbenchFeature(str, Enum)   # closed vocabulary, e.g. MARK_READ, LABELS, DRAFTS, HTML,
    # VACATION, FILTERS, ALL_DAY, CONFERENCE, NOTIFY_ATTENDEES, MULTI_VALUED, CONTACT_GROUPS,
    # OTHER_CONTACTS, SUBTASKS, LIST_MANAGEMENT, DUE_DATE_ONLY, EXPORT, COLOR, COLOR_TEMPERATURE, SCENES
TOOL_PROVIDERS: Final[dict[WorkbenchTool, tuple[ConnectorType, ...]]]
PROVIDER_FEATURES: Final[dict[ConnectorType, frozenset[WorkbenchFeature]]]
PROVIDER_BOUNDS: Final[dict[ConnectorType, dict[str, int]]]   # e.g. Graph emails_max=3
def assert_descriptor_completeness() -> None                  # called at import; ADR-085

class ToolAvailability(BaseModel): tool; state; provider: str | None; features: list[WorkbenchFeature]; bounds: dict[str, int]
class WorkbenchLimits(BaseModel): page_size; bulk_max_items; download_max_bytes; calendar_window_max_events
class WorkbenchAvailability(BaseModel): tools: list[ToolAvailability]; limits: WorkbenchLimits
async def read_availability(user_id: UUID) -> WorkbenchAvailability

@asynccontextmanager
async def open_tool_client(tool: WorkbenchTool, user_id: UUID) -> AsyncIterator[ActiveClient]
#   category door for mail/calendar/tasks/contacts, open_client_by_type for files/lights;
#   ClientUnavailable → refuse(NOT_CONNECTED) or refuse(RECONNECT_REQUIRED) (find_error_connector_type)

workbench_requests_total = Counter(..., ["tool", "operation", "outcome"])   # outcome: ok | <code>
workbench_provider_latency_seconds = Histogram(..., ["tool"])
workbench_downloads_total = Counter(..., ["tool", "outcome"])
workbench_idempotency_replays_total = Counter(..., ["tool", "outcome"])
workbench_idempotency_unguarded_total = Counter(..., ["tool"])
def observed(tool: WorkbenchTool, operation: str) -> AbstractAsyncContextManager[None]
#   times the provider call, counts ok / the refusal code, re-raises
```
Availability, in ONE `DetachedConnectorService().unit_of_work()`: per tool, an active
provider of its category (or the Drive / Hue row) → `ready`; one in `ERROR` → `reconnect_
required`; every connector type of the tool globally disabled
(`ConnectorGlobalConfig.is_enabled`, the same predicate the connectors settings page uses to
offer a type) → `unavailable`; otherwise `not_connected`. Features and bounds come from the
descriptor of the provider (`ready` / `reconnect_required` only).

- [ ] RED descriptor: every connector type of every tool has an entry (and no stray entry);
  a mutant table missing Apple contacts fails the assert.
- [ ] RED availability: each state per tool with doubles; Apple active for mail and nothing
  for tasks → tasks `not_connected`; switch off → route 403 `CAPABILITY_DISABLED`; one
  session opened for the whole read (counted on the double).
- [ ] RED router: unauthenticated 401; guard; payload shape; rate-limited read answers 429.
- [ ] GREEN; metric coverage ratchet `tests/unit/test_metric_coverage_ratchet_guard.py` PASS
  (no baseline entry added); `direct_client_callers` guard PASS.

### L1 gate

- [ ] `cd apps/api && .venv/Scripts/ruff check src tests && .venv/Scripts/black --check src tests && .venv/Scripts/mypy src` (touched files clean).
- [ ] `task test:backend:unit:fast` → PASS except reds owned by `lia-b6` (named in the ledger).
- [ ] Integration: `pytest tests/integration/domains/workbench -q --no-cov` → PASS.
- [ ] Runtime: `docker logs lia-api-dev | grep application_ready` after reload; `docker exec
  lia-api-dev curl` of `/api/v1/workbench` with the proof account's cookie → 200, states.
- [ ] Cold adversarial review of every L1 file; ledger.

---

## Lot L2 — Client contracts across providers, and the assistant

### Task 2.1 — Read state on the three mail clients + the assistant tool

**Files:**
- Create: `apps/api/src/domains/connectors/clients/gmail_mail_state_mixin.py`,
  `apps/api/src/domains/connectors/clients/apple_mail_state_mixin.py`,
  `apps/api/src/domains/agents/tools/email_state_tools.py`
- Modify: `clients/protocols.py` (`mark_read` on `EmailClientProtocol`),
  `clients/google_gmail_client.py` (mixin; shrink by moving `trash_email` /
  `untrash_email` / `delete_email_permanently` into the mixin),
  `clients/microsoft_outlook_client.py`, `clients/apple_email_client.py` (mixin),
  the e-mail catalogue manifests (`agents/emails/catalogue_manifests.py` or where
  `get_emails_tool`'s manifest lives), `core/constants.py` (`EMAIL_READ_STATE_MAX_IDS = 50`)
- Test: `tests/unit/domains/connectors/clients/test_mark_read_parity.py`,
  `tests/unit/domains/agents/tools/test_email_state_tools.py`

**Interfaces — produces:**
```python
async def mark_read(self, message_ids: Sequence[str], read: bool) -> dict
#   {"updated": [ids], "failed": [{"id": str, "status": "not_found" | "failed"}]}
@tool  async def set_email_read_state_tool(message_ids: list[str], read: bool, runtime) -> UnifiedToolOutput
#   manifest: category email, mutation_policy="reversible" (reason: « restoring the previous
#   state is the same tool with the other boolean »), bounds from EMAIL_READ_STATE_MAX_IDS
#   in BOTH the manifest and the @tool schema; @track_tool_metrics + @rate_limit
```
Gmail: `batch_modify_labels(ids, add_label_ids=[] if read else ["UNREAD"],
remove_label_ids=["UNREAD"] if read else [])`; Graph: `PATCH /me/messages/{id}`
`{"isRead": read}` per id under a bounded `asyncio.Semaphore`; IMAP: group runtime handles
by folder (`imap_handles`), `flag(uids, SEEN, read)` in `asyncio.to_thread`, refusing legacy
handle shapes as the tools do.

- [ ] RED parity test on realistic payloads ×3 (two ids, one gone → `failed` not_found);
  read and unread both ways; IMAP two folders → two selects.
- [ ] RED tool test: registry smoke covers it (`tests/unit/domains/agents/tools/test_tool_registry_smoke.py`);
  manifest bound == schema bound == constant; provider-neutral (Outlook double, IMAP double).
- [ ] GREEN; golden net PASS; `measure_sloc` of the three clients ≤ caps (Gmail SHRINKS).

### Task 2.2 — Mail cache generations (freshness after any write)

**Files:**
- Create: `apps/api/src/infrastructure/cache/mail_generation.py`
- Modify: `google_gmail_client.py` (search + message cache keys read the generation; every
  write — trash, untrash, delete, labels modify/batch, mark_read, drafts — bumps it),
  `apple_email_client.py` / its message cache key helper, `key_families.py`
  (`"mail:generation"` → `USER_RUNTIME`, NOT purged by a conversation reset), `core/constants.py`
- Test: `tests/unit/infrastructure/cache/test_mail_generation.py`,
  `tests/unit/domains/connectors/clients/test_mail_cache_freshness.py`

**Interfaces — produces:**
```python
async def mail_generation(account: str) -> int            # 0 when absent or Redis fails
async def bump_mail_generation(account: str) -> None        # INCR + EXPIRE(MAIL_GENERATION_TTL_SECONDS); never raises
```
The generation key's TTL (one day) exceeds every mail cache TTL, so its expiry can never
resurrect a live entry. Gmail keys become `…{account}:g{n}:…`.

- [ ] RED: search → trash → same search within the TTL returns the message gone (fake Redis);
  mark_read → `get_message` serves the new `is_read`; Redis down → caches bypassed, writes
  still succeed.
- [ ] GREEN; Gmail SLOC ≤ 795 and lower than at L0.

### Task 2.3 — Tasks and Graph contacts paging

**Files:** `clients/protocols.py` (`list_tasks(..., page_token=None)`), `google_tasks_client.py`,
`microsoft_tasks_client.py`, `microsoft_contacts_client.py`; create
`clients/normalizers/graph_paging.py`
- Test: `tests/unit/domains/connectors/clients/test_paging_parity.py`

**Interfaces — produces:**
```python
def graph_page_token(next_link: str | None) -> str | None      # the $skiptoken / $skip VALUE only
def graph_page_params(page_token: str | None) -> dict[str, str] # rebuilt server-side
```
A Graph `@odata.nextLink` is NEVER followed as a URL from a client-supplied token (SSRF): the
token carries the skip value, the client rebuilds the request on its own base URL.
`list_tasks` answers `next_page_token` on both providers.

- [ ] RED: Google `pageToken` round trip; Graph nextLink → token → same next request; a
  token carrying a URL is refused (`ValueError` → 422 at the route); golden first pages
  unchanged.
- [ ] GREEN.

### Task 2.4 — All-day events and drained windows on the three calendar clients + the tools

**Files:**
- Create: `apps/api/src/domains/connectors/clients/normalizers/all_day.py`,
  `apps/api/src/domains/agents/tools/calendar_event_times.py` (extracted from
  `calendar_tools.py` to make room)
- Modify: `clients/protocols.py`, `google_calendar_client.py`, `microsoft_calendar_client.py`,
  `apple_calendar_client.py`, `agents/tools/calendar_tools.py` (`all_day` on
  `create_event_tool` / `update_event_tool`), their catalogue manifests,
  `agents/tools/calendar_draft_execution.py`, the calendar draft card renderer under
  `agents/drafts/` (a date, « all day », never « 00:00 → 00:00 »)
- Test: `tests/unit/domains/connectors/clients/test_all_day_parity.py`,
  `tests/unit/domains/connectors/clients/test_events_window.py`,
  `tests/unit/domains/agents/tools/test_calendar_all_day.py`

**Interfaces — produces:**
```python
def exclusive_end(last_day: date) -> date                 # last_day + 1 day
def inclusive_last_day(exclusive: date) -> date
async def create_event(..., all_day: bool = False) -> dict    # all_day: start/end are ISO dates, end INCLUSIVE
async def update_event(..., all_day: bool | None = None) -> dict  # None keeps the event's shape
async def list_events_window(self, calendar_id: str, time_min: str, time_max: str, *, bound: int) -> dict
#   {"events": [...normalised...], "truncated": bool}
```
Google: `{"date": …}` start / exclusive end, the `dateTime` keys removed (and the reverse on
timed); Graph: `isAllDay: true`, midnight `dateTime` bounds in the event's zone, exclusive
end; CalDAV: `DTSTART;VALUE=DATE` / `DTEND;VALUE=DATE` exclusive. Read side checked
symmetric with `calendar_normalizer.py` (an all-day event read back shows the same inclusive
last day). Windows: Google `pageToken` loop (`singleEvents=true`, `orderBy=startTime`),
Graph `calendarView` with paging, CalDAV one time-range REPORT — all cut at `bound`.

- [ ] RED parity ×3: one-day and three-day all-day create; timed → all-day and back on
  update; an all-day event on the DST weekend (2026-03-29 Europe/Paris) keeps its dates;
  the window cuts at `bound` with `truncated: true`, and returns `false` below.
- [ ] RED tool: `all_day=True` reaches the client; manifest bound/description from one
  constant read by both readers; the HITL card of an all-day draft reads « Mon 3 Nov, all
  day » (fr/en asserted); golden timed bodies unchanged.
- [ ] GREEN; `calendar_tools.py` ≤ 1150 and not grown.

### Task 2.5 — Multi-valued contacts on the three clients + a non-destructive tool

**Files:**
- Create: `apps/api/src/domains/connectors/clients/normalizers/contact_values.py`,
  `apps/api/src/domains/connectors/clients/apple_vcard_write.py` (vCard building moved out
  of `apple_contacts_client.py`)
- Modify: `clients/protocols.py`, `google_people_client.py`, `microsoft_contacts_client.py`
  (+ `normalizers/microsoft_contacts_normalizer.py` write side), `apple_contacts_client.py`,
  `agents/tools/google_contacts_tools.py` (docstring + description: the legacy single value
  sets the primary and keeps the others)
- Test: `tests/unit/domains/connectors/clients/test_contacts_multi_valued_parity.py`,
  `tests/unit/domains/agents/tools/test_update_contact_keeps_values.py`

**Interfaces — produces:**
```python
class TypedValue(TypedDict): value: str; type: str | None
class TypedAddress(TypedDict): formatted: str; type: str | None
async def create_contact(..., emails: list[TypedValue] | None = None, phones: list[TypedValue] | None = None, addresses: list[TypedAddress] | None = None) -> dict
async def update_contact(..., emails: … | None = None, phones: … | None = None, addresses: … | None = None) -> dict
#   a list REPLACES that list; None keeps it; legacy email=/phone=/address= replace the PRIMARY value only
```
Google: `updatePersonFields` names exactly the lists sent, the fresh etag kept; Graph:
`emailAddresses` (≤ 3, published in `PROVIDER_BOUNDS`), phones mapped to
`mobilePhone` / `businessPhones` / `homePhones`, addresses to `home` / `business` / `other`
(one each, published) — a list the provider cannot hold is refused
`not_supported_by_provider` with the bound, never truncated; CardDAV: `EMAIL` / `TEL` /
`ADR` lines with `TYPE=`, every other vCard line preserved.

- [ ] RED parity ×3: replace emails list; keep phones when `phones=None`; legacy `email=` on a
  two-email contact keeps the second (Review focus 5); Graph fourth e-mail refused with the
  bound; vCard unknown lines survive.
- [ ] RED tool: `update_contact_tool(email=…)` on a two-email double keeps the second.
- [ ] GREEN; `apple_contacts_client.py` SHRINKS; golden name/notes bodies unchanged.

### L2 gate

- [ ] `task lint:backend`; `task test:backend:unit:fast`; touched client and tool suites
  in full (`pytest tests/unit/domains/connectors tests/unit/domains/agents/tools -q`).
- [ ] Measurement with the owner's accord only: S6 all-day create/delete on Google and S7
  People two-email write with etag, `[LIA-TEST]` items removed at once — otherwise recorded
  as « doubles only » in the ledger.
- [ ] Runtime: the assistant on dev (proof account) — `set_email_read_state_tool` and
  `all_day` appear in the catalogue (`/api/v1/...` debug catalogue or registry smoke).
- [ ] Cold adversarial review (every client diff line ×3 providers); ledger.

---

## Lot L3 — Frontend base

### Task 3.1 — Destination, availability helper, header measurement

**Files:**
- Modify: `apps/web/src/lib/dashboard-nav.ts` (`segment` union + `{ segment: 'tools',
  labelKey: 'navigation.tools', feature: 'workbench_enabled' }` after `chat`;
  `DestinationFeatures.workbench_enabled`), the `DESTINATION_ICONS` table (Lucide `Wrench`),
  `apps/web/src/hooks/useAppConfig.ts`, six locales (`navigation.tools`,
  `capabilities.items.workbench`)
- Create: `apps/web/src/lib/workbench/availability.ts`
- Test: `apps/web/src/lib/__tests__/dashboard-nav.test.ts` (extend),
  `apps/web/src/lib/workbench/__tests__/availability.test.ts`, the header reachability e2e
  (extend its locale × width matrix with the ninth destination)

**Interfaces — produces:**
```ts
export function workbenchAvailable(config: WorkbenchConfig | null | undefined): boolean
// capabilityEnabled(config?.capabilities, 'workbench', config?.features?.workbench_enabled)
```
- [ ] RED: hidden when the flag is off or unknown; visible and ordered after Chat when on;
  icon table complete (type-enforced).
- [ ] GREEN; e2e header reachability ×6 languages at 1024 / 1280 / 1536 (S9): no overflow,
  logout visible. If German overflows at `xl`, shorten the label in that locale (never a
  layout hack) — recorded in the ledger.

### Task 3.2 — Rail, shell, drill-down, errors

**Files:**
- Create: `apps/web/src/app/[lng]/dashboard/tools/layout.tsx`, `page.tsx`, `loading.tsx`,
  `error.tsx`; `apps/web/src/components/workbench/WorkbenchShell.tsx`,
  `WorkbenchRail.tsx`, `WorkbenchToolHeader.tsx`, `WorkbenchUnavailable.tsx`;
  `apps/web/src/lib/workbench/tools.ts`, `errors.ts`, `types.ts`;
  `apps/web/src/hooks/useWorkbenchAvailability.ts`; six locales (`workbench.rail.*`,
  `workbench.tools.<tool>.*`, `workbench.errors.<code>`, `workbench.states.*`)
- Test: `components/workbench/__tests__/WorkbenchRail.test.tsx`,
  `WorkbenchShell.test.tsx`, `hooks/__tests__/useWorkbenchAvailability.test.ts`,
  `lib/workbench/__tests__/errors.test.ts`

**Interfaces — produces:**
```ts
export type WorkbenchToolId = 'mail' | 'calendar' | 'tasks' | 'contacts' | 'files' | 'lights';
export const WORKBENCH_TOOLS: readonly WorkbenchToolSpec[]   // order: mail, calendar, tasks, contacts, files, lights
export const WORKBENCH_ERROR_CODES: readonly string[]          // pinned to WORKBENCH_CODES by the backend test
export function workbenchRefusal(error: unknown): { key: string; values?: Record<string, number> } | null
export function useWorkbenchAvailability(): { availability?: WorkbenchAvailability; loading; error; refetch }
//   useApplicationAccountQuery('/workbench', …) + useApplicationResourceSync(ownerId, 'connectors', refetch)
```
Rail: `<nav aria-label>` of links with `aria-current="page"`, « Tools » group (ready +
reconnect with a warning badge) and « To connect » group (not_connected → link to
Settings › Connectors); unavailable tools absent. Below `lg`: the rail IS the `/tools`
screen; a tool screen shows a back button to it (ADR-227 §7). `/tools` on desktop redirects
(client-side `router.replace`) to the first ready tool in rail order; none ready → the rail
with an empty state that names the exit (connect a service).

- [ ] RED: rail groups, `aria-current`, links; landing choice; drill-down at 390 px (back
  button, focus moved to the tool heading); connectors resource event refetches.
- [ ] GREEN; the backend pairing test of Task 1.2 turns GREEN.

### Task 3.3 — The cursor-page hook

**Files:** create `apps/web/src/hooks/useWorkbenchPage.ts`; test
`hooks/__tests__/useWorkbenchPage.test.ts`

**Interfaces — produces:**
```ts
export function useWorkbenchPage<T>(path: string | null, params: Record<string, QueryParamValue>):
  { items: T[]; nextToken: string | null; loading: boolean; loadingMore: boolean; error: unknown;
    loadMore(): Promise<void>; refresh(): Promise<void>; replaceItem(id: string, next: T | null): void }
```
Derived loading per key (params serialised); a late answer to old params is dropped; an
owner change clears the list; `refresh` re-reads page one IN PLACE (items kept until the
answer); `replaceItem` applies an optimistic or confirmed change.

- [ ] RED: late answer dropped; refresh keeps items until answered; owner change; loadMore
  appends and stops at null token.
- [ ] GREEN.

### L3 gate

- [ ] `task lint:frontend` (ESLint, tsc non-incremental, ratchets held); `task lint:i18n`;
  `task test:frontend` (workbench + nav + config suites).
- [ ] Runtime on dev: `/fr/dashboard/tools` renders the rail in light, dark, OLED (DevTools
  screenshots kept in the ledger dir, never committed).
- [ ] Cold review; ledger.

---

## Lot L6 — Tasks (first full traversal)

### Task 6.1 — Backend tasks routes

**Files:** create `domains/workbench/schemas/tasks.py`, `tasks_service.py`, `tasks_router.py`
(mounted by `router.py`); D5 entry for `tasks_service.py`
- Test: `tests/unit/domains/workbench/test_tasks_service.py`, `test_tasks_router.py`

**Routes:** `GET /workbench/tasks/lists`; `POST /workbench/tasks/lists` {title,
idempotency_key}; `DELETE /workbench/tasks/lists?list_id=`; `GET /workbench/tasks?list_id=
&show_completed=&page_token=` → `{items, next_page_token}`; `POST /workbench/tasks`
{list_id, title, notes?, due?, parent?, idempotency_key}; `PATCH /workbench/tasks`
{list_id, task_id, title?, notes?, due? (explicit null clears when the descriptor says so),
status?}; `DELETE /workbench/tasks?list_id=&task_id=`.

- [ ] RED: page cut stated (Review focus 1); completed toggle; due date-only on Google
  (`DUE_DATE_ONLY` feature); create replay → 409; gone task → 404 `item_gone`; ids bounded
  and charset-checked (422 on 300 chars or a `/`); rate limits per window.
- [ ] GREEN.

### Task 6.2 — Tasks screen

**Files:** create `app/[lng]/dashboard/tools/tasks/page.tsx`,
`components/workbench/tasks/TasksTool.tsx`, `TaskListsPane.tsx`, `TaskRow.tsx`,
`TaskEditor.tsx`, `NewTaskListDialog.tsx`, `hooks/useWorkbenchTasks.ts`; locales
`workbench.tasks.*`
- Test: `components/workbench/tasks/__tests__/*.test.tsx`; e2e
  `apps/web/e2e/smoke/workbench-tasks.spec.ts` (mocked API: success, a toggle refused and
  rolled back, keyboard path, 390 px, axe, light/dark/OLED)

- [ ] RED: optimistic completion rolled back on refusal with the code's sentence; subtasks
  indented under their parent; « Load more » appears exactly when `next_page_token`; empty
  list names the exit (« Add a task »).
- [ ] GREEN; e2e under the lock.

### L6 gate — as L3, plus the backend suite and a runtime proof (proof account: tasks screen
shows « To connect » when it has no tasks connector).

---

## Lot L9 — Lights

### Task 9.1 — Backend lights routes

**Files:** create `schemas/lights.py`, `lights_service.py`, `lights_router.py`; D5 entry.
**Routes:** `GET /workbench/lights` → `{rooms, lights, scenes}` (one bridge read);
`POST /workbench/lights/light` {light_id, on?, brightness?, color_hex?, mirek?};
`POST /workbench/lights/room` {room_id, on?, brightness?}; `POST /workbench/lights/scene`
{scene_id}. Colour: `#rrggbb` → CIE xy server-side (`lights_service.hex_to_xy`, sRGB gamma
→ XYZ → xy), clamped by the bridge; a lamp without colour refuses a colour
(`not_supported_by_provider`).
- [ ] RED: hex→xy on reference colours (white D65 ≈ 0.3127/0.3290 within 0.002); a lamp
  without colour; bridge unreachable → `provider_unavailable`; Hue limiter 429 →
  `provider_rate_limited`.
- [ ] GREEN.

### Task 9.2 — Lights screen

**Files:** `app/[lng]/dashboard/tools/lights/page.tsx`, `components/workbench/lights/*`
(`LightsTool`, `RoomCard`, `LightControls`, `ScenePicker`), `hooks/useWorkbenchLights.ts`
- [ ] RED: controls drawn from capabilities; brightness/colour committed on release
  (`pointerup` / `change`, never `input`); a refused change restores the previous value.
- [ ] GREEN; e2e `workbench-lights.spec.ts` under the lock.

---

## Lot L4 — Mail

### Task 4.1 — Folders and labels (backend)

**Files:** `schemas/mail.py`, `mail_service.py` (folders, labels), `mail_router.py`;
D5 entries.
**Routes:** `GET /workbench/mail/folders` → `{folders: [{id, name, kind: system|user,
system_role?: inbox|sent|drafts|trash|spam|starred, unread?}]}` from `list_labels` (Gmail
system labels as folders, user labels under them; Graph well-known folders; IMAP folders);
Gmail only (descriptor `LABELS`): `GET /workbench/mail/labels`, `POST` create, `PATCH`
rename, `DELETE ?label_id=` (system labels refused, as the tools refuse them),
`POST /workbench/mail/labels/apply` {message_ids, add: [ids], remove: [ids]}.
- [ ] RED: three providers' folder shapes; a system label delete refused; apply bumps the
  cache generation; labels on Outlook → `not_supported_by_provider`.
- [ ] GREEN.

### Task 4.2 — Listing, search, reading (backend)

**Routes:** `GET /workbench/mail/messages?folder=&q=&unread=&attachments=&after=&before=
&page_token=` → `{items: [MailSummary], next_page_token, skipped}` (headers only; the query
composed server-side from the folder and the chips into the Gmail-style language the three
providers translate, F12; the free text is quoted, never interpreted as operators);
`GET /workbench/mail/message?id=` → `MailMessage` (text body, quoted history folded,
attachments list with handles, `is_read`); reading does NOT mark read (an explicit act, as
in the providers' « mark as read on open » setting off — phase 1).
- [ ] RED: chips compose exactly (`in:inbox is:unread has:attachment after:2026/10/01`);
  free text with `from:` stays a literal; `skipped` exact when Gmail could not fetch hits;
  empty folder vs empty search distinguished (`reason`).
- [ ] GREEN.

### Task 4.3 — Acts on messages (backend)

**Routes:** `POST /workbench/mail/read-state` {message_ids, read} (bulk window above one
id); `POST /workbench/mail/trash` {message_ids} (bulk window above one; each failure
reported per id, never all-or-nothing).
- [ ] RED: bulk over `workbench_bulk_max_items` → 422 with the bound; partial failure
  reported; generation bumped once per act.
- [ ] GREEN.

### Task 4.4 — Attachments download

**Routes:** `GET /workbench/mail/attachment?message_id=&attachment_id=&filename=` →
`StreamingResponse`-free `Response` (clients read into memory, bounded) with
`Content-Disposition: attachment; filename*=UTF-8''…` (sanitised by the existing regex),
`Content-Security-Policy: sandbox`, `Cache-Control: no-store`; `max_bytes` passed to the
client (ceiling BEFORE the body is read where the provider states the size); one download
in flight per account (Redis claim, owner token, short TTL); `download` window.
- [ ] RED: headers exact; 413 `too_large` with `max_bytes`; stale Gmail handle →
  `stale_handle` path through `select_attachment` by name; second concurrent download → 429.
- [ ] GREEN.

### Task 4.5 — Compose, reply, forward, drafts (backend)

**Routes:** `POST /workbench/mail/send` {to, cc?, bcc?, subject, body, idempotency_key};
`POST /workbench/mail/reply` {message_id, body, reply_all, idempotency_key};
`POST /workbench/mail/forward` {message_id, to, cc?, body?, idempotency_key};
`GET /workbench/mail/drafts?page_token=`; `GET /workbench/mail/draft?id=`;
`POST /workbench/mail/drafts` {draft_id?, to?, cc?, bcc?, subject?, body?,
expected_revision?} (create or update); `POST /workbench/mail/drafts/send`
{draft_id, expected_revision, idempotency_key}; `POST /workbench/mail/drafts/trash`
{draft_ids}; `GET /workbench/mail/recipients?q=` (reuses
`email_share.recipients.suggest_recipients`, bounded query, read window).
Recipients parsed strictly (`infrastructure/email/recipients.py`) → `invalid_recipient`
naming the index; sends through `run_once` (Task 1.4) with `single_attempt=True`.
A new message may carry `attachment_ids` — the person's OWN files (generated files and
uploads, spec §13), resolved through the e-mail share's file checks (ownership, live
deadline, the provider class's `OUTGOING_FILE_MAX_BYTES`) and handed to `send_email` as
`OutgoingAttachment`s; replies and forwards carry none (phase 2). A
`GET /workbench/mail/attachable?q=` lists them (page + exact total, the gallery's query).
- [ ] RED: timeout after send → 504 `outcome_unknown` then replay → 409 `already_submitted`
  `outcome: unknown` (Review focus 3); invalid address; IMAP draft id changes on save and
  the answer carries the new id; a changed draft refuses the send (`conflict`).
- [ ] GREEN.

### Task 4.6 — Mailbox settings (Gmail)

**Routes:** `GET/PUT /workbench/mail/vacation` (enable, subject, body, start/end dates,
contacts-only); `GET /workbench/mail/filters`; `POST /workbench/mail/filters`
{criteria: from/to/subject/query/has_attachment, action: add_labels/remove_labels/
archive/mark_read/forward?} — exactly what `GoogleGmailSettingsClient.create_filter`
accepts; no delete (the panel says so).
- [ ] RED: descriptor gate (`VACATION`, `FILTERS` Gmail only); round trip of the vacation.
- [ ] GREEN.

### Task 4.7 — Mail screen

**Files:** `app/[lng]/dashboard/tools/mail/page.tsx`; `components/workbench/mail/`
`MailTool.tsx` (three panes ≥ xl, two at lg, drill-down below), `FolderList.tsx`,
`MessageList.tsx`, `MessageRow.tsx`, `MailSearchBar.tsx` (chips), `MessageReader.tsx`,
`AttachmentList.tsx`, `Composer.tsx` (dialog on desktop, full screen on phone; one
idempotency key per open composer; Send disabled while sending; recipients input with
suggestions), `DraftsView.tsx`, `LabelsManager.tsx`, `MailboxSettingsPanel.tsx`,
`SelectionBar` bulk acts; `hooks/useWorkbenchMail.ts`; locales `workbench.mail.*`;
the list density (comfortable / compact) is a per-device preference (`localStorage`, try/catch)
- [ ] RED: selection + bulk trash with partial failure toast; read toggle optimistic with
  rollback; composer double-submit guard; `outcome_unknown` keeps the composer content and
  tells to check Sent; search chips; the selected message rides `?id=`; keyboard: list
  arrows, Enter opens, Escape closes the reader.
- [ ] GREEN; e2e `workbench-mail.spec.ts` (list, read, trash, compose success, unknown
  outcome, 390 px, axe, three themes) under the lock.

---

## Lot L4b — Mail HTML

### Task 4b.1 — `get_message_html` ×3 and its route

**Files:** mail mixins (Gmail: raw `format=full` read of the `text/html` part, base64url
decoded, charset honoured; Graph: `$select=body` with `Prefer: outlook.body-content-type="html"`;
IMAP: `msg.html`), `clients/protocols.py`; route `GET /workbench/mail/message/html?id=` →
`{html: str | null, truncated: bool}` bounded by `workbench_mail_html_max_bytes` (2 MB; a
new field of `WorkbenchSettings` with its constant and its lines in the eight env files,
added in this task).
- [ ] RED parity ×3 (multipart/alternative, html-only, text-only → null); size cap stated.
- [ ] GREEN. Not exposed to any tool (ADR-287), asserted by a test that no manifest reads it.

### Task 4b.2 — The sandboxed frame

**Files:** `components/workbench/mail/MailHtmlFrame.tsx` (+ test)
```tsx
<iframe sandbox="" referrerPolicy="no-referrer" title={t('workbench.mail.html_frame_title')}
  srcDoc={`<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><base target="_blank">${html}`} />
```
Fixed height with its own scroll; a light paper background whatever the theme.
- [ ] RED: exact attributes (no `allow-*` token at all); the CSP meta precedes the content;
  the frame is absent for a text-only message (the text reader shows instead).
- [ ] GREEN; e2e: an HTML mail with a remote image and a script renders, no network request
  to the remote host, no console error.

---

## Lot L5 — Calendar (Agenda + Week)

### Task 5.1 — Backend calendar routes

**Files:** `schemas/calendar.py`, `calendar_service.py`, `calendar_router.py`; D5 entry.
**Routes:** `GET /workbench/calendar/calendars`; `GET /workbench/calendar/events?
calendar_ids=&start=&end=` (window drained per calendar under
`workbench_calendar_window_max_events`, `truncated` per calendar); `GET /workbench/calendar/
event?calendar_id=&event_id=`; `POST /workbench/calendar/events` {calendar_id, summary,
start, end, all_day, timezone, location?, description?, attendees?, conference?,
idempotency_key → provider idempotency}; `PATCH /workbench/calendar/events` {…, notify};
`DELETE /workbench/calendar/events?calendar_id=&event_id=&notify=`. Wall time + zone id,
never an offset.
- [ ] RED: window bound and `truncated`; recurring occurrence update targets the
  occurrence id (and says so in the schema); all-day create through the route; `notify`
  absent where the descriptor lacks `NOTIFY_ATTENDEES`.
- [ ] GREEN.

### Task 5.2 — Calendar screen

**Files:** `app/[lng]/dashboard/tools/calendar/page.tsx`; `components/workbench/calendar/`
`CalendarTool.tsx`, `CalendarList.tsx` (visibility per device, localStorage in try/catch),
`AgendaView.tsx`, `WeekView.tsx`, `EventChip.tsx`, `EventDetail.tsx`, `EventEditor.tsx`;
`lib/workbench/calendar/zoned.ts` (Intl-only wall time ↔ instant for a zone),
`lib/workbench/calendar/layout.ts` (overlap columns, « +N »); `hooks/useWorkbenchCalendar.ts`
**Interfaces — produces:**
```ts
export function wallTimeToInstant(date: string, time: string, zone: string): Date   // DST gap → next valid minute; overlap → earlier
export function instantToWall(instant: Date, zone: string): { date: string; time: string }
export function layoutDay(events: PositionedInput[]): PositionedEvent[]           // columns, widths, overflow count
```
- [ ] RED: 02:30 on the spring-forward night → 03:00 (Europe/Paris) and the overlap night;
  multi-day timed event split per day; all-day row; overlapping events side by side;
  « +N » past the column budget; the editor sends wall time + zone; response colours from
  data only.
- [ ] GREEN; e2e `workbench-calendar.spec.ts` under the lock.

## Lot L5b — Month view

### Task 5b.1 — Month grid

**Files:** `components/workbench/calendar/MonthView.tsx` (+ layout helper in `layout.ts`)
- [ ] RED: six-week grid from the locale's first weekday; multi-day bars; « +N more » opens
  the day in Agenda; keyboard grid navigation (arrows, Home/End).
- [ ] GREEN.

---

## Lot L7 — Contacts

### Task 7.1 — Backend contacts routes

**Files:** `schemas/contacts.py`, `contacts_service.py`, `contacts_router.py`; D5 entry.
**Routes:** `GET /workbench/contacts?q=&group=&page_token=` (list by cursor or search);
`GET /workbench/contacts/contact?id=`; `POST /workbench/contacts` {name, emails, phones,
addresses, organization?, notes?, idempotency_key}; `PATCH /workbench/contacts`
{id, …lists (None keeps)}; `DELETE /workbench/contacts?id=`; Google only (descriptor):
`GET /workbench/contacts/groups`, `GET /workbench/contacts/other`.
- [ ] RED: page cut stated; Graph list bounds refused with the bound; etag conflict →
  `conflict`; delete gone → `item_gone`.
- [ ] GREEN.

### Task 7.2 — Contacts screen

**Files:** `app/[lng]/dashboard/tools/contacts/page.tsx`; `components/workbench/contacts/`
`ContactsTool.tsx`, `ContactList.tsx`, `ContactDetail.tsx`, `ContactEditor.tsx`
(`MultiValueField` for e-mails / phones / addresses with types), `GroupFilter.tsx`;
`hooks/useWorkbenchContacts.ts`; « See the relationship » via `lib/relations-routing.ts`
when the folded name matches a known relation exactly.
- [ ] RED: add/remove/retype values; the editor never sends a list it did not change
  (None keeps); bounds from `bounds`; relation link only on an exact fold.
- [ ] GREEN; e2e `workbench-contacts.spec.ts` under the lock.

---

## Lot L8 — Files

### Task 8.1 — Backend files routes

**Files:** `schemas/files.py`, `files_service.py`, `files_router.py`; D5 entry.
**Routes:** `GET /workbench/files?folder_id=&q=&page_token=` (folder listing or search,
shortcuts shown as such, shared drives stated as not shown); `GET /workbench/files/file?id=`
(metadata + breadcrumb walked up to the root, bounded depth); `GET /workbench/files/download?
id=&format=` (binary or export: Docs → pdf|docx, Sheets → xlsx, Slides → pdf|pptx;
`too_large` past the ceiling, read with `max_bytes`); `POST /workbench/files/trash` {file_ids}.
- [ ] RED: breadcrumb depth bound; export mime map exact; ceiling; download headers as 4.4.
- [ ] GREEN.

### Task 8.2 — Files screen

**Files:** `app/[lng]/dashboard/tools/files/page.tsx`; `components/workbench/files/`
`FilesTool.tsx`, `Breadcrumb.tsx`, `FileList.tsx`, `FileDetail.tsx`; `hooks/useWorkbenchFiles.ts`
- [ ] RED: navigation pushes `?folder=`; search replaces the listing and says so; download
  through `apiEndpointUrl`; « Open in Drive » `rel="noopener noreferrer"`.
- [ ] GREEN; e2e `workbench-files.spec.ts` under the lock.

---

## Lot L10 — Hardening

### Task 10.1 — Matrix and gates

- [ ] e2e workbench suite at 1280 / 390 / 320 px, zoom 200 %, light / dark / OLED, five
  accents (screenshot per screen in the ledger dir); Firefox and WebKit smoke on the rail +
  mail + calendar.
- [ ] Security pass: every route's id validation, download headers, the frame's attributes,
  logs at INFO carry no content (`tests/unit/test_log_content_guard.py`).
- [ ] Performance pass: no N+1 provider calls in listings (counted on doubles); calendar
  window per calendar in parallel under a semaphore.
- [ ] `task ci:fast` → exit 0 (reds owned by `lia-b6` named in the ledger if any).

---

## Lot L11 — Documentation

### Task 11.1 — Records and maps

- [ ] `docs/architecture/ADR-369-Workbench-The-Persons-Own-Door-To-Their-Services.md`
  (decisions D1–D6, the door, idempotency, cache generations, parity reaching the tools,
  what is NOT recorded and why); `docs/architecture/ADR_INDEX.md`.
- [ ] `docs/technical/WORKBENCH.md` (routes, codes, descriptor, limits, metrics, themes);
  `docs/INDEX.md`; `docs/ARCHITECTURE.md`; the connectors pattern doc; `docs/knowledge/`
  corpus entry; FAQ ×6 (a « Tools » section — lia-i18n skill).
- [ ] Living maps: ADR-369 entry (date, theme, bricks) in six languages, `domains/workbench`
  claimed by its brick; `task docs:maps` (`--restamp` only for re-translations).
- [ ] CLAUDE.md: one pointer line; `task docs:sync-agents`; `task release:sync-counts`.
- [ ] `task lint:docs` (or `lint:docs:preview`, nothing staged); `task lint:i18n`.

### Task 11.2 — Closing

- [ ] Frontend coverage: scoped-glob thresholds for `src/lib/workbench/**`,
  `src/components/workbench/**` and `src/hooks/useWorkbench*.ts` at the measured value minus
  two points (ratchet doctrine), in the vitest configuration.
- [ ] `task lint`, `task test:backend:unit:fast`, workbench integration suites,
  `task test:frontend`, `task test:frontend:coverage`, e2e (alone, under the lock),
  `task ci:fast`.
- [ ] Closing runtime proof on Docker dev; exhaustive cold review of every touched file;
  final self-evaluation; memory updated (project memory, MEMORY.md line).
