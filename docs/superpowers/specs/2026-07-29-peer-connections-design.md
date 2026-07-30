# Peer Connections Program — Verified Design

**Date:** 2026-07-29 · **Status:** arbitrations signed off (A1–A6 + delivery mechanism + CRM
bridge), no lot started
**Baseline:** HEAD `27b68e0a` (v1.26.3). **Working tree:** 2 uncommitted doc-only files
(`docs/superpowers/specs/2026-07-29-self-host-installer-design.md` modified,
`docs/superpowers/plans/2026-07-29-self-host-installer.md` untracked) — zero overlap with this
program (docs only; this program touches none of those paths). Re-run `git status` at every lot
start and re-check overlap.
**Scope:** 6 lots (execution order in §14). Multi-session program.

Every claim below was verified in-code on 2026-07-29 (file:line evidence inline).
Sibling program docs (same format): `2026-07-22-ux-refinements-program.md`,
`2026-07-28-ux-actions-program.md`.

---

## 1. Feature summary

Users of the same LIA instance can discover each other **opt-in**, request connections,
accept/decline **in the chat or in a new settings section**, block/unblock silently, later
remove an accepted connection (both sides notified by their own assistant in their own chat),
relay messages **assistant-to-assistant** (the recipient's assistant delivers the message with
its own personality, memory and context), and share **read-only** domains per connection
(nothing shared by default), with **both directions visible** (what I share with them, what
they share with me).

Confirmed interpretation of the relay flow: *the recipient's assistant conveys the message
according to the sender's directives, naming the originating user*. Canonical example (signed
off, names anonymized — repo guard forbids real ones): sender asks "Demande à Paul Dupont
comment ça va" → sender's assistant emits "Marie Dupont veut savoir comment Paul Dupont va" →
Paul's assistant, using **its** personality and **Paul's** long-term memory ("Marie is my
mother"), delivers e.g. "ta mère veut savoir comment tu vas. C'est déjà la troisième fois
aujourd'hui…".

Out of scope (deliberate): cross-instance federation, email/contacts domain sharing (deferred
by A1), group connections, real-time presence.

## 2. Signed arbitrations

| # | Decision |
|---|----------|
| A1 | v1 shareable domains: **calendar** (two levels: `availability` free/busy — default — or `details` with event titles) and **tasks** (titles only). Email & contacts sharing deferred to a later program (third-party PII). |
| A2 | **Blocking deletes the connection** (plus its shares and any pending request), silently — no notification to the blocked user. Unblocking restores nothing; a new request is required. |
| A3 | Sending a relayed message requires an **explicit sender-side confirmation** (same class as sending an email) plus a daily quota. |
| A4 | LLM cost of the delivery generation is **charged to the sender** (abuse prevention). Precise token accounting is a hard requirement with its own tests (§9). |
| A5 | Backend bounded context **`peers`**; UI section name localized per language ("Connexions", "Connections", "Verbindungen", "Conexiones", "Connessioni", zh final wording at the i18n lot). |
| A6 | Homonym discrimination: results carry a **masked email fragment** (format in §5.1). |
| D1 | Delivery mechanism: **constrained recipient-side pipeline run** (§8) — the user-approved "as if it were a chat turn" ideal, with a deterministic no-tools guarantee. |
| D2 | CRM bridge: the `relations` read-only CRM surfaces the peer-connection state for a matching person (§11). |

## 3. Verified foundations (evidence)

- **Identity**: `User.full_name` is a single nullable, non-unique, **plaintext** column
  (`apps/api/src/domains/users/models.py:67`). No first/last split exists. Discovery matches on
  normalized `full_name`; users without one are undiscoverable (documented UI hint).
- **Active account**: lifecycle `Active → Deactivated → Deleted → Erased`
  (`users/account_deletion_service.py:4`); active = `is_active AND deleted_at IS NULL`.
  Background-run guard precedent: `scheduled_action_executor.py:175`.
- **Cross-user chat delivery**: `NotificationDispatcher` archives an assistant message into the
  recipient's conversation, commits **before** FCM/SSE/Telegram push (anti-race), localized
  titles via `ProactiveMessages.notification_title`
  (`infrastructure/proactive/notification.py:231,348`; `core/i18n_proactive.py:108`).
- **In-chat approval**: proactive body embedding `[label](…/dashboard/chat?intent=…)` links
  (`infrastructure/scheduler/scheduled_action_executor.py:90-118`), consumed once by
  `useAutoSendIntent` (ADR-173, `apps/web/src/hooks/useAutoSendIntent.ts`).
- **Background pipeline run for a user**: `AgentService.stream_chat_response(user_message=…,
  user_id=…, session_id=…, is_automated_source=True, auto_approve_plan=True,
  archive_user_message=…)` with HITL-pending guard, usage-limit pre-check, inactive guard,
  per-attempt session ids and retry (`scheduled_action_executor.py:267-369`).
- **Personality access**: `PersonalityService.get_prompt_instruction_for_user(user_id)`
  (`domains/heartbeat/proactive_task.py:534-551`).
- **Shareable domain granularity**: connector functional categories, one ACTIVE connector per
  category per user (`domains/connectors/models.py:205`).
- **Anti-enumeration precedent**: user search by email is superuser-only "prevents account
  enumeration" (`domains/users/router.py:148`).
- **Name normalization**: NFKD + casefold folding already exists
  (`domains/relations/service.py:47-56`) — hoisted to a shared helper (Lot 1), relations
  updated to import it (no duplication).
- **GDPR guard**: every new table must be classified in `users/user_data_map.py` (CI-guarded,
  lines 1-19) and covered by purge statements.
- **Provenance framing for third-party content**: ADR-167/170, deployed (v1.25.30) — reused
  verbatim for relayed messages and peer-read results.
- **ORM trap**: `UserService.get_user_by_id` returns a `UserProfile` schema, **not** the ORM
  `User` (documented in-code at `scheduled_action_executor.py:210`); dispatcher and fetchers
  need the ORM row (`db.get(User, id)`).

## 4. Architecture

New bounded context `apps/api/src/domains/peers/` (models, repository, service,
delivery_service, router, schemas) + new LangGraph domain `peer` (declarative
`DOMAIN_REGISTRY` entry + `peer_agent` + tools + manifests) + a scheduler sweep job + a
frontend settings section. Everything is additive; the only core-graph change is one declared
state key + one router guard (§8, deliberately minimal and reusable).

### 4.1 Data model (all new tables; plus one `users` column)

- `users.discovery_enabled` — bool, NOT NULL, default/server_default `false` (opt-in).
- `peer_connections` — canonical pair `user_a_id < user_b_id` (CHECK + UNIQUE on the pair —
  one row per pair at DB level), `requested_by_id`, `status`
  `pending | accepted | declined | removed` (`Enum(native_enum=False)`, UPPERCASE members —
  telephony enum trap), `context_message` (nullable, length-capped), `requested_at`,
  `responded_at`, `removed_at`. FKs `ondelete="CASCADE"` to `users`.
- `peer_blocks` — `blocker_id`, `blocked_id`, `created_at`, UNIQUE(blocker, blocked), CHECK
  blocker ≠ blocked. Independent of connections; survives connection deletion.
- `peer_domain_shares` — `connection_id` (CASCADE), `owner_user_id`, `domain`
  (`calendar | task` in v1 — singular vocabulary), `level` (`availability | details` for
  calendar; `titles` for tasks), `created_at`, `updated_at`,
  UNIQUE(connection_id, owner_user_id, domain). Absence of row = not shared (default-off).
- `peer_messages` — `connection_id` (CASCADE), `sender_id`, `recipient_id`, `content`
  (sender directive text; **scrubbed to NULL after successful delivery** — the delivered
  wording lives only in the recipient's conversation archive), `status`
  `pending | delivered | failed | cancelled`, `attempts`, `created_at`, `delivered_at`,
  `last_error` (typed code, never raw text). Consumed with `FOR UPDATE SKIP LOCKED` + atomic
  status transition (imitate `scheduled_actions/repository.py`).
- `peer_access_log` — immutable audit (no `updated_at`, pattern `AdminAuditLog`,
  `users/models.py:608`): `accessor_id`, `owner_id`, `connection_id`, `domain`, `tool_name`,
  `created_at`. Read back by the owner in the transparency view (§10).

Model registration in the 3 mandated places (alembic `env.py`, database registry,
`startup/registries.py`); single alembic head; `task db:migrate:replay-check` green.

### 4.2 Config & constants

New module `src/core/config/peers.py` (`PeersSettings`), composed into the `Settings` MRO.
All thresholds settings-driven (never hardcoded — tests read them from `settings`):

- `peers_enabled` (default `false`) — global flag; guards router, scheduler job, tools
  registration and frontend section exposure.
- `peers_discovery_rate_limit_calls` / `_window_seconds` — discovery search rate limit.
- `peers_message_max_per_day` (per sender) and `peers_message_max_per_day_per_pair`.
- `peers_message_max_chars`.
- `peers_request_cooldown_days` (re-request after decline), `peers_request_expiry_days`
  (pending auto-expiry), `peers_max_pending_per_pair = 1` (constant).
- `peers_delivery_sweep_seconds` (default 60) and `peers_delivery_max_attempts`.
- `peers_access_log_retention_days` — the sweep prunes `peer_access_log` rows older than
  this (transparency is recent-history, not an unbounded archive).
- Scheduler job id + defaults in `src/core/constants.py`; `.env.example`,
  `.env.prod.example` (+ `.env.min.prod` if applicable) updated.

### 4.3 API surface (`/api/v1/peers`, flag-guarded include in `api/v1/routes.py`)

All endpoints: `Depends(get_current_active_session)`, ownership checks, centralized exception
raisers, `hide_existence=True` semantics wherever a block/unknown user could be probed.

- `GET /peers/me` — my discovery state; `PUT /peers/me` — toggle `discovery_enabled`.
- `POST /peers/discovery/search` — §5.1. Rate-limited.
- `POST /peers/requests` — create request (guards §5.2); `GET /peers/requests` — incoming +
  outgoing pending; `POST /peers/requests/{id}/respond` — accept/decline.
- `GET /peers/connections` — accepted list incl. both share directions;
  `DELETE /peers/connections/{id}` — remove (notifies both, §6).
- `PUT /peers/connections/{id}/shares` — upsert/remove **my** share rows for that connection;
  categories offered = those where I hold an ACTIVE connector, within the A1 set.
- `GET /peers/connections/{id}/access-log` — transparency view (owner-side reads of MY data).
- `POST /peers/blocks` / `DELETE /peers/blocks/{peer_id}` / `GET /peers/blocks`.

## 5. Discovery & connection lifecycle

### 5.1 Discovery search

Input: a full name. Matching: **exact match on folded `full_name`** (shared NFKD+casefold
helper) — never prefix/substring (enumeration). Result rows only for users who are
`discovery_enabled AND is_active AND deleted_at IS NULL`, excluding self and excluding any
user with a block in **either** direction (indistinguishable from no-match). Payload per row:
`peer_id`, `display_name` (their `full_name`), `email_hint` — first character of the local
part + `…` + `@` + first character of the domain + `…` + public suffix (e.g.
`j…@g….com`) — A6. Nothing else (no avatar, no locale, no activity signal).

### 5.2 Requests

Guards at creation: not self; addressee discoverable per §5.1 rules (else generic not-found);
no existing `accepted` pair row; at most one pending per pair; cooldown after a decline
(`peers_request_cooldown_days`); optional `context_message` (capped, provenance-framed on
display). **Crossing requests auto-accept** (B requesting A while A→B is pending = accept).
Pending requests expire after `peers_request_expiry_days` (sweep marks `removed` silently).

Addressee is notified in chat (dispatcher): localized body naming the requester + context
message + `[Accept](?intent=…)` / `[Decline](?intent=…)` links (executed by the peer tools),
plus the same actions in the settings section. Requester is notified in chat of the outcome
(accept or neutral decline — cooldown prevents nag loops).

### 5.3 Removal & blocking

- Remove (either side, any time): row → `removed`, shares deleted, **both users notified** by
  their own assistant in their own language (explicit user requirement).
- Block: transitions any pair row to `removed` (the pair keeps a single row — UNIQUE
  constraint; re-requests transition `removed`/`declined` rows back to `pending`), deletes
  its shares and pending state, records `peer_blocks`, **no notification** to the blocked
  user; from then on the pair is mutually invisible in discovery and all sends fail
  neutrally ("no connection"). Block is reachable
  from search results, from a pending request (decline+block) and from the connections list.
- Unblock: removes the block row only (A2 — nothing restored).
- Account deactivation: user disappears from discovery, sends toward them fail neutrally,
  peer reads against them fail neutrally; connections remain rows (reactivation restores).
- Account deletion: CASCADE removes all pair rows; the surviving peer simply no longer sees
  the connection (no dedicated notification in v1).

## 6. Chat integration

All peer events reach chats through `NotificationDispatcher` (archive-first + FCM + SSE +
Telegram). New proactive task types with 6-language titles/bodies in `ProactiveMessages`
(`zh-CN` backend-canonical): `peer_request`, `peer_request_outcome`, `peer_removed`,
`peer_message`, `peer_message_delivered`. Bodies are built from i18n templates + data — never
inline French in Python (systemic rule). Accept/decline/remove are also expressible directly
to the assistant ("accepte la demande de Jérôme") via the peer tools — the `?intent=` links
just type those sentences for the user.

## 7. Agent integration

- `DOMAIN_REGISTRY` entry `peer` (singular vocabulary; `result_key="peers"`;
  `related_domains=["contact", "event"]`), `peer_agent` registered in
  `startup/agents.py::init_agent_registry`, catalogue manifests, boot-time completeness
  asserts extended.
- Tools (each `@track_tool_metrics` + `@rate_limit` via the standard decorators, i18n via
  runtime language — never `self` state):
  - `list_peer_connections` — my connections + share states (both directions).
  - `request_peer_connection` / `respond_to_peer_request` / `remove_peer_connection` —
    lifecycle verbs (server-side guards identical to the REST endpoints; the tools call the
    same service).
  - `send_peer_message(recipient_name, message)` — write tool; HITL confirmation (A3) as the
    email-send class; quota + block + connection checks server-side; enqueues `pending`.
    **Fail-closed in HITL-less contexts**: tools running inside a skill subagent runner never
    receive HITL interrupts (known trap — confirmations must happen in two phases INSIDE the
    tool: first call returns a confirmation challenge, second call with the confirmation
    token sends). The tool implements the two-phase pattern unconditionally and the graph
    -level HITL classification comes on top for the interactive path.
  - `get_peer_availability(peer_name, date_range)` — calendar share; free/busy computed in the
    **peer's** timezone, presented in the requester's display timezone; event titles only when
    the peer's share level is `details`.
  - `get_peer_tasks(peer_name)` — task titles (share level `titles`).
- Peer-name resolution inside tools uses the caller's **connection list** (folded exact match;
  on ambiguity the tool returns the candidate list for clarification) — never the discovery
  index.
- Every peer read: share row re-checked **at execution time** (no caching of the
  authorization), `peer_access_log` row written, result wrapped in the ADR-167/170 provenance
  frame before entering the requester's context.

## 8. Message relay engine (D1 — the core design)

Send path: sender's tool validates (connection accepted, no block, quotas, sender not
LLM-blocked via `UsageLimitService`), persists `peer_messages` row `pending`, returns
immediately ("delivery in progress"). Delivery path (immediate best-effort kick after commit +
periodic sweep `peers_delivery_sweep_seconds` as the durable guarantee, SKIP LOCKED):

1. Re-validate at delivery time (block/removal/deactivation since send → `cancelled`,
   sender notified neutrally).
2. Run the **recipient's constrained pipeline**: reuse
   `AgentService.stream_chat_response` exactly as the scheduled executor does
   (`is_automated_source=True`, dedicated session id per attempt, HITL-pending guard,
   inactive guard), with a new **deterministic constraint**: a `forced_route="conversation"`
   input declared in `MessagesState` (undeclared keys are silently dropped — systemic trap)
   and honored by the routing functions so the run can NEVER reach planner/tools/ReAct.
   The run keeps memory injection, journal portrait, psyche and personality — which is what
   produces the signed-off example — while sender-controlled text cannot trigger any tool.
   The input is a versioned prompt (`prompts/v1/peer_message_delivery.txt`, loaded via
   `load_prompt()`, name added to the `PromptName` Literal) framing the sender identity, the
   relay directive and the **provenance-delimited** message (data, never instructions).
   **RESOLVED at Lot 4 opening (2026-07-29)**: the proof ran and the FALLBACK
   won. Memory injection lives in the response-context bundle
   (`services/response_context.py:251` — gated by `user_memory_enabled`, NOT
   by `is_automated_source`, which only skips extraction), so the behavioral
   ingredients (memory, personality, portrait, psyche) are directly callable
   without the pipeline; and the pipeline path books its tokens to the
   EXECUTING user across nodes, making §9 (sender pays, hard requirement)
   practically unattainable there. Delivery is therefore the documented
   single personality+memory-enriched LLM call (`domains/peers/delivery.py`),
   with `build_psychological_profile` invoked deterministically — a stronger
   guarantee than routing hope — and zero core-graph change (`forced_route`
   never shipped). Original decision record kept below.
   **Unverified assumption, gated by proof (Lot 4 opens with this)**: `is_automated_source=
   True` is documented to skip memory/interest/journal/psyche *extraction*
   (`scheduled_action_executor.py:349`), but it is NOT yet proven that memory *injection*
   fires on the conversation branch of an automated run — and that injection is what powers
   the signed-off example. Lot 4 starts with a runtime proof (dev container, real run,
   logged injected-memories evidence); the outcome decides between this main path and the
   fallback. Fallback (recorded decision): if the proof fails or `forced_route` proves
   invasive, degrade to a single personality-enriched LLM call that performs an explicit
   memory search on the sender's name (heartbeat pattern + `MemoryService` search + relay
   history + psyche brief), same external contract — the example then works by construction.
   The fallback also makes §9 token attribution trivial (we own the single LLM call), which
   weighs in its favor if the pipeline wiring resists.
3. The produced text is delivered via `NotificationDispatcher` (task type `peer_message`,
   title naming the sender) — not via the run's own archive path
   (`archive_user_message=False`; no user-role turn exists in the recipient's conversation).
4. Row → `delivered`, `content` scrubbed to NULL; sender notified in chat
   (`peer_message_delivered`, quoting the original directive from the sender's own turn).
5. Failure → `attempts+1`; past `peers_delivery_max_attempts` → `failed`, sender notified
   neutrally. All transitions atomic. **Deferral ≠ failure**: a delivery postponed because
   the recipient has a pending HITL interrupt (scheduled-actions precedent) or a transient
   infrastructure condition leaves `attempts` untouched — only actual generation/dispatch
   failures consume attempts.

Relay history awareness ("3rd time today"): the delivery prompt includes the count of
messages relayed from this sender to this recipient today (cheap SQL) — the assistant may use
it, as in the example.

## 9. Token accounting (A4 — hard requirement)

The delivery run executes under the recipient's pipeline but is **charged to the sender**:

- Pre-checks: sender quota + sender `UsageLimitService.is_user_blocked_for_llm` at send time
  AND delivery time. The recipient's usage limits are NOT consulted (they are not paying).
- Attribution: tokens harvested from the delivery run are recorded against the **sender**
  through the proactive tracking path (`track_proactive_tokens(user_id=sender, …,
  task_type="peer_message")` — `infrastructure/proactive/tracking.py`), and the run is
  configured/compensated so the recipient's counters do not also book them (no double count).
  Exact wiring is a Lot 4 implementation task with these test oracles: (a) sender's daily
  usage increases by the run's tokens, (b) recipient's usage unchanged, (c) sender at quota →
  send refused with localized error, (d) sender becoming blocked between send and delivery →
  message `cancelled`, sender notified.

## 10. Frontend

New section in the **features** tab: `components/settings/PeerConnectionsSettings.tsx`
(decomposed into subcomponents — CC ratchet counts new files), hook
`src/hooks/usePeerConnections.ts` (`useApiQuery`/`useApiMutation`, never raw fetch). Content:
discovery toggle, exact-name search + request with optional context message, incoming/outgoing
pending lists (accept/decline/block), connections list with per-domain **outgoing shares
(editable: calendar availability|details, tasks)** and **incoming shares (read-only badges)**
(explicit requirement), transparency access log ("X read your availability …"), block list
with unblock, remove connection. Section registered in `SETTINGS_SECTIONS`
(`apps/web/src/lib/settings-sections.ts` — order is page order), settings search (ADR-172
normalizer), coverage test allowlists, deep-link token `peer-connections`. Section hidden when
`peers_enabled` is off (reuse the existing feature-flag exposure mechanism — the
conditionally-rendered channels/skills/MCP sections are the precedent to locate at Lot 2). i18n keys in all
6 locales (strict parity; zh `_one` duplication rule). No new chat component (explicit
requirement): messages and notifications render as ordinary assistant messages.

## 11. CRM bridge (D2)

`domains/relations` gains one additional read-only fetcher (own failure boundary, own
session — briefing pattern): when the person's folded display name matches a connected peer's
folded `full_name`, `RelationDetail` carries a `lia_peer` block: connected-since, both share
directions, last relayed-message date. No write path; `relations` remains "not a source of
truth" (its stated contract) — the block is aggregation like every other section.

## 12. Security & privacy invariants

1. Exact-match discovery only, opt-in only, rate-limited, minimal payload (§5.1).
2. `hide_existence` everywhere a block or non-opted-in account could be probed; block outcomes
   indistinguishable from absence; blocking never notifies.
3. Relayed messages and peer-read results are **untrusted third-party content**: provenance
   framing (ADR-167/170) + delivery run structurally tool-less (§8) — prompt injection cannot
   reach tools on either side.
4. Peer reads: share re-checked at execution time; read-only tool subset; immutable
   `peer_access_log` visible to the data owner.
5. No PII at INFO (ids and counters only; names/contents at DEBUG or redacted);
   `peer_messages.content` scrubbed post-delivery; typed error codes, no raw exceptions to
   the LLM.
6. GDPR: all 5 tables classified in `user_data_map.py` (CI guard) — purge covers rows where
   the user sits on either side; export includes connections/blocks/shares/message metadata
   (content only while pending) and access-log rows involving the user.
7. All datetimes tz-aware UTC; availability computed in the peer's timezone, displayed in the
   requester's (no hardcoded timezone — AST guard).
8. **Self-declared identity, residual risk documented**: `full_name` is user-editable, so a
   user can rename themselves to resemble someone else. Mitigations: the masked `email_hint`
   (A6) is shown at discovery AND **pinned permanently on the connection card and in the
   pending-request card**, so the stable identifier fragment is visible at decision time and
   afterwards; relayed messages name the sender by their current `full_name` (the recipient's
   assistant may cross-check against memory). Accepted residual risk on a private instance —
   recorded here, not silently.

## 13. Edge-case ledger

Homonyms (multiple exact matches → list with email hints); `full_name` NULL
(undiscoverable, UI hint on the toggle); self-request; duplicate request; crossing requests
(auto-accept); re-request after decline (cooldown); request expiry; block while pending /
after accept / mutual blocks; unblock (no restore); block between send and delivery
(cancelled); recipient deactivated (neutral failures; reactivation restores); recipient
deleted (CASCADE); discovery toggled off (connections keep working); share revoked during an
in-flight read (execution-time check wins); quota reached (localized refusal); delivery retry
idempotency (atomic transitions, per-attempt session ids); HITL pending on recipient's
conversation (delivery deferred to next sweep — scheduled-actions precedent); sender at/over
limit between send and delivery (§9d); concurrent share toggles (UNIQUE upsert); pair
uniqueness under concurrent requests (DB constraint, not app logic).

## 14. Implementation lots & gates

Boy-Scout, additive-only; no threshold/baseline may move except downward. Git stays with the
user.

1. **Backend socle** — config module + flags + constants + `.env*`; models + migration +
   3-place registration; `user_data_map` + purge/export + guard sync; shared name-folding
   helper (relations refactored to import it); repository/service/router; backend i18n
   scaffolding; unit tests. Gates: `task lint`, `task test:backend:unit:fast`,
   `task db:migrate:replay-check`.
2. **Discovery & management UI** — section + hook + i18n ×6 + `SETTINGS_SECTIONS`/search/tests
   + hermetic e2e journey. Gates: `task lint:frontend`, `task test:frontend:coverage`,
   non-incremental tsc, e2e.
3. **Chat lifecycle integration** — dispatcher wiring for request/outcome/removal,
   `ProactiveMessages` additions, `?intent=` links, bilateral removal notifications.
4. **Relay engine** — `forced_route` state key + router guard (+ fallback decision point),
   delivery prompt v1, delivery service + immediate kick + sweep job (constants, flag guard,
   `replace_existing=True`, registered before `leader_elector.start()`), send tool + HITL
   confirm + quotas, token attribution (§9 oracles), metrics.
5. **Domain sharing** — share endpoints/UI already in Lots 1-2; peer read tools + execution
   -time checks + access log + transparency UI + provenance wrapping + concurrency tests.
6. **Agents, observability, docs** — `DOMAIN_REGISTRY` + agent + manifests + QueryAnalyzer
   coverage + completeness asserts; Prometheus metrics (`peers_requests_total{event}`,
   `peers_messages_total{status}`, `peers_reads_total{domain,outcome}`,
   `peers_discovery_searches_total{outcome}`, delivery latency histogram) + Grafana panels;
   ADR + `ADR_INDEX` + `docs/INDEX.md` + `ARCHITECTURE*.md` + guides; release narrative
   surfaces enriched (never stamped). Final gate: `task ci:fast`.

## 14bis. Implementation notes — recorded deviations (2026-07-29, lots 1-6 shipped)

All six lots shipped the same day, flag-off. Deviations from the letter of
this spec, each an improvement discovered against the real codebase:

- **§4.1 statuses**: `String(20)` + lowercase str-Enums (open_loops pattern),
  not `Enum(native_enum=False)` — which later allowed adding the transient
  `delivering` claim status with NO migration.
- **§8 delivery**: the D1 proof ran and the pre-authorized FALLBACK won (see
  the RESOLVED note in §8) — single enriched LLM call, `forced_route` never
  shipped, zero core-graph change.
- **§8/§14.4 engine location**: the delivery engine lives in
  `infrastructure/scheduler/peer_message_delivery.py`, not `domains/peers/` —
  the F009 cycle ratchet caught `agents<->peers` and the scheduled-action
  executor precedent is the architectural home.
- **A3 confirmation**: implemented as a `PEER_MESSAGE` draft (FN-1 doctrine —
  the draft IS the confirmation, covering pipeline, ReAct AND skill-subagent
  contexts identically); the executor re-validates every guard at
  confirmation time.
- **§6 chat actions**: bodies link to the settings deep link;
  the `?intent=` accept/refuse upgrade remains OPEN (deferred follow-up: the
  peer tools now exist, wiring the intent sentences is a small later change).
- **§7 taxonomy**: the frozen `domain_taxonomy` gained a generic extension
  point (`registry/program_domain_configs.py`, program_manifests pattern) —
  and net-shrank via `_GOOGLE_API_KEY` factoring.
- **§14.6 Grafana panels**: metrics (`peers_events_total`,
  `peers_messages_total`) are exposed; dashboard panels remain OPEN (join the
  next dashboards iteration — ADR-178 practice: pre-wire then light up).
- **Error i18n**: backend HTTP errors carry stable `peers_*` machine codes
  translated CLIENT-side (label-key doctrine) — `APIMessages` additions were
  unnecessary; `ProactiveMessages` carries every chat-facing string ×6.

### Lot 7 — chat UX refinements (2026-07-30, from first runtime use)

- **Runtime fix, semantic validator**: with only the English pivot on display
  the validator flagged French content args, folded names and a phantom
  "reply id". The ORIGINAL user message is now passed and AUTHORITATIVE for
  content/names/language (`semantic_validator_node` → `validate()` →
  prompt block); replies are explicitly "a new stateless relay".
- **Runtime fix, wording**: indirect speech is converted to DIRECT ADDRESS at
  extraction ("demande à X comment il va" → message "comment vas-tu ?") —
  pinned in the tool param/docstring, catalogue manifest, delivery prompt
  (grammatical-person adaptation) and validator authority block.
- **§6 upgrade shipped**: peer bubbles (`proactive_peer_*` metadata) carry a
  subtle primary tint + quick actions under the bubble — Reply (composer
  prefill, A4: never sends) / Block (house confirm) on relayed messages,
  Accept/Decline (freeze into verdict) on incoming requests
  (`PeerMessageActions`, PhoneCallDebriefBlock precedent). Push toasts reuse
  the same tint. Delivery metadata gained `sender_name`.
- **§10 additions**: the settings section surfaces the user's own searchable
  name with one-click copy (empty name = "unfindable", said plainly);
  discovery results carry `relationship` (`none|pending|connected` —
  DECLINED/REMOVED read `none` by §12.2 neutrality) and show a status badge
  instead of a second request button.
- **CC ratchet**: `deliver_claimed_message` decomposed (`_cancel_and_notify`,
  `_record_retryable_failure`) — newcomer stays under CC 15.

## 15. Traps to honor (from memory + systemic rules)

`Enum(native_enum=False)` UPPERCASE members (telephony trap); `get_user_by_id` →
`UserProfile` not ORM `User`; `MessagesState` undeclared keys silently dropped
(`forced_route` MUST be declared); JSONB new-dict rule; one `AsyncSession` per concurrent
fetcher; no `datetime.utcnow()`/hardcoded tz (AST guards); i18n strict parity + zh `_one`;
no env-conditional test skips; settings-read thresholds in tests; new files decomposed under
the CC and 600-SLOC ratchets; tool-module imports fail loudly; no inline French in Python;
prompts only in versioned files.
