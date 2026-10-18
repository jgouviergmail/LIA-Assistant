# Meetings search, peer transfer, JEV qualification and Position implementation plan

Implementation and inline reviews: see the [delivery and qualification record](../qualification/2026-10-18-evolutions-delivery.md).
The frozen native holdout did not qualify; its failed attempts and paid accounting
are retained explicitly. The campaign did not enable the usages. Their subsequent
DEV activation, observed read-only and left unchanged, is recorded in the delivery report.

> **For agentic workers:** Execute strictly INLINE with
> superpowers:executing-plans after the owner's explicit go. The owner's
> instruction overrides subagent execution/review defaults. No business code,
> deployment, peer send or runtime setting change is authorized by this document.

**Goal:** Implement the four approved-for-analysis outcomes and their regression
proof without disturbing concurrent work.

**Architecture:** Reuse canonical meetings and their list, hardened importers and
peer fences, the registered native JEV runtime, and native Google map admission/
rendering. Keep display projections separate from source data, policy and action
authority. New interfaces below are proposed, not existing APIs.

**Tech Stack:** Existing FastAPI/SQLAlchemy/PostgreSQL/Redis, Next.js/React/
TypeScript, native JEV transport and Google Maps JavaScript SDK; no new UI stack.

**Spec:** [Design and evidence](../specs/2026-10-18-meetings-peer-sharing-qualification-position-design.md).

## Global constraints

- Wait for the owner's implementation go; strictly inline, no subagents.
- Word/PDF changes are withdrawn. Preserve all unrelated staged/unstaged files.
- All automatic installs are disabled from their first durable publication.
- Peer skills get authored-equivalent execution after manual activation, without
  system/admin privileges or transferred credentials/approvals.
- Email category is professional/personal/spam/phishing_scam/unknown; accepted
  phishing_scam takes precedence over the generic categories. Its localized
  French label is 'Phishing/Arnaque'. Use semantic danger red, a warning icon
  and stable readable text; animate its outline/halo at one cycle per second
  for four seconds, then keep it static. Reduced motion is static immediately;
  ordinary re-renders/history must not replay attention animation.
- Email category and priority are independent; priority is one of
  normal/urgent/critical, with unknown permitted. No badge for unknown or normal
  priority. No action/filter/memory write follows from a label.
- The Position card appears automatically; interactive loading is a paid explicit
  click. Keep all selected places visible and state missing coordinates.
- Use six locales, UTC instants with recipient/user timezone, typed API hooks and
  existing account lifetimes, native accessible controls and mobile reflow.
- Platform spend answers to account and instance ceilings and actual ledgers.
- No ratchet relaxation, unauthorized git delivery or production operation.

## Review focus

1. A report edited/reset/regenerated while searched must never leave an old
   positive match or make the exact count disagree with the filter.
2. A peer copy must never be observable as enabled, even between component
   commits or after an unknown SQL acknowledgement.
3. Credential-bearing bytes in a plugin archive must not survive because only
   its database MCP configuration was sanitized.
4. The model must actually receive the same annotation a badge shows, including
   ReAct, detail=metadata and compact dashboard projections.
5. Old answer HTML, theme changes and shared SDK callbacks must not silently
   create paid maps or move markers from unrelated turns/accounts.

Each item is pinned by the tests in its owning task below.

## Task 1: Native current-minutes search and paged API

**Files:** modify meetings/repository.py, router.py and service.py under
apps/api/src/domains/; create meetings/search.py for the typed field-path
declaration and SQL expressions. Reuse core/sql_search.py. Extend meetings unit
tests and real PostgreSQL integration tests, including existing job publications.
No search model column, migration or write-path instrumentation is baseline scope.

**Interfaces:** proposed minutes_search_predicate(query: str) -> ColumnElement[bool]
over Meeting.report_current and location_label, composed from static schema-owned
text paths and a section-kind completeness declaration. SQL normalization follows
the specified NFD/lowercase/typography contract. Repository list_for_user adds
keyword-only query: str | None, retaining tuple[list[Meeting], int]. GET /meetings
adds optional q with maximum 200 input characters; response shape is retained.

- [ ] Write tests for every SectionKind, no JSON-key/internal-id matches,
  accents/case/apostrophes/spaces, literal %, _, backslash, null/mistyped fields,
  per-field phrase boundaries and current vs generated report. Share a corpus
  with frontend normalizeSearchText, including nonexpanded ligatures and
  combining marks. Run red on real PostgreSQL rather than testing SQL text alone.
- [ ] Add tests for a match beyond page one, foreign-owner exclusion, exact total,
  equal-time id ordering and requested offset beyond the final page. Pin the
  count/row snapshot with concurrent edits/deletions. Verify edit/reset/initial
  synthesis/regeneration/location-only writes need no indexing synchronization.
- [ ] Implement schema-owned JSON scalar projection, per-field EXISTS matching
  and normalization inside the query. Reuse escape_like and LIKE_ESCAPE; user
  input never becomes a JSON path or SQL fragment. Do not cast the whole JSON
  document to searchable text, load every report into Python, or query RAG.
- [ ] Derive total and paged rows from the same filtered set in one SQL snapshot,
  returning total even for an empty out-of-range page. Do not rely solely on a
  window count which disappears when no row is returned. Keep current-report
  validity/diagnostics behavior and the existing list DTO.
- [ ] Run targeted unit/PostgreSQL tests and representative EXPLAIN/latency/memory
  measurements with long reports and large account histories. Capture this
  baseline before proposing additional persistence or indexes. If it proves
  insufficient, amend this task with a measured optimization and its migration/
  writer/backfill tests; do not silently restore the earlier unproven design.

## Task 2: Meetings search UX and navigation

**Files:** apps/web/src/app/[lng]/dashboard/meetings/page.tsx and [id]/page.tsx;
apps/web/src/hooks/useMeetings.ts; apps/web/src/lib/meetings/{api,list-location}.ts;
corresponding page/hook tests, six locale files, and
apps/web/e2e/smoke/meetings-back-navigation.spec.ts.

**Interfaces:** meetingsApi.list and useMeetingList accept optional normalized
query without changing existing positional enabled arguments for old callers.
List location owns {query, page, origin}; its encoder/decoder is shared by list
and detail. Query and account identity both participate in request lifetime.

- [ ] Write hook/page tests for 300ms debouncing, empty clear, new-query offset
  and selection reset, reversed network replies, abort/unmount/account switch,
  failed refresh vs no-match and recovery retaining focus/input. Run red.
- [ ] Add browser coverage searching a row omitted from page one, then detail
  and back with q/page/from preserved; verify browser back/forward and deletion
  of the last matching row. Include a pending bulk confirmation when q changes.
- [ ] Reuse SearchInput, EmptyState, Pagination and current account guards.
  Send q to the server; never filter the loaded page locally. Keep the input
  mounted and announce refresh/count without focus theft or stale rows stated
  as current results. Preserve live-recording controls and existing deep links.
- [ ] Run task test:frontend with targeted page/hook proof and the Docker-dev
  hermetic browser journey. Verify keyboard and 320px/zoom reflow in light/dark.

## Task 3: Peer transfer data, receipts and policy

**Files:** new capability-transfer schemas/models/repository and snapshot modules
inside apps/api/src/domains/peers/; extend peers/models.py and an Alembic migration;
skills/models.py, repository.py, trust.py and native/gallery projections;
plugins models/projections as needed; users/account_deletion_service.py;
account_export/builder.py; tests/unit and tests/integration/domains/peers/.

**Interfaces:** proposed CapabilityKind = skill | mcp | plugin;
CapabilityTransferRequest(connection_id, kind, source_id, idempotency_key,
expected_digest); SanitizedCapabilitySnapshot(kind, digest, inventory,
authentication_requirements, package/config); TransferReceipt(id, status,
transferred_at, component_outcomes, recipient_resource_ids). Closed DTOs accept
no arbitrary owner, execution trust, local path, credentials or activation flag.

- [ ] Write failure tests for wrong owner/scope/pair, pending/blocked/self peer,
  duplicate key with different input, changed source digest, malicious name,
  archive links/junctions/traversal/bombs, runtime files, URL/header credentials,
  secrets in both DB fields and original package files. Observe red.
- [ ] Pin system-name collision behavior: preserve the importer's current
  rejection, leave the existing active system skill visible, and create no
  personal disabled row which would shadow it through request-state resolution.
- [ ] Implement exact-scope static snapshots through bounded existing archive
  readers. Add a sanitizer/inventory validator and explicit suspicious-package
  refusal. Sender preview and send bind the same sanitized digest. Resource
  omission is stated; unresolvable embedded secrets are not promised detectable.
- [ ] Implement durable receipts/claims, component identities, constrained
  transitions and idempotency, with every status produced/read. No resource
  overwrite on name conflict. Resource identities and package snapshots are
  recipient-owned, independent of sender storage.
- [ ] Add the peer execution-policy distinction at the one request-state/trust
  boundary. Personal peer origin is explicit; plugin group ownership remains
  intact. Test authored-equivalent active behavior and unchanged ordinary URL/
  library/plugin isolation; test system-widget privilege refusal and upstream
  update policy resolution instead of inherited trust. Frontmatter cannot grant it.
- [ ] Add scrub/hard-delete and per-side export tests: sender erasure anonymizes
  origin without deleting the recipient's copy; recipient erasure removes their
  data; no blocked-by or credential disclosure. Replay migrations and assert
  rollback/retry/concurrent transfer identities on real PostgreSQL.

## Task 4: Disabled installation adapters and durable transfer flow

**Files:** peers capability-transfer service/installation modules and router;
skills/import_service.py, preference_service.py and import_hooks.py;
plugins/import_service.py and import_hooks.py;
user_mcp/service.py and internal installation DTO; notification integration;
resource invalidation and affected import/cancellation tests.

**Interfaces:** proposed InitialActivationPolicy, defaulting to existing import
behavior for ordinary callers, with disabled for every peer creation. Internal
install_shared_mcp(snapshot, recipient_id, origin) retains auth requirements but
allows absent credentials and creates disabled/auth_required rows. A peer flow
returns a durable TransferReceipt, not an optimistic installation message.

- [ ] Add tests observing the DB/cache after EACH first component commit;
  assert inactive skills and disabled servers, no automatic MCP connection,
  OAuth, script/model call or tools exposed in the recipient catalogue. This
  is review-focus item 2; an end-of-request-only assertion is insufficient.
- [ ] Add crash/cancellation/lost-ack tests at staging, swap, skill commit,
  server write and plugin-root commit. Include quota races, source deletion,
  block/disconnection races and opposing transfers/lock order. Observe red.
- [ ] Persist component id/fingerprint/origin and its receipt outcome in the
  component transaction, not only in an after-commit callback. Add a crash
  between commit and callback, then retry with an already edited, enabled,
  deleted or replaced recipient component: preserve the recipient's action,
  never upsert/recreate a completed component, and conflict on identity capture.
- [ ] Extend importer initialization/hooks minimally. Reuse ordinary validation,
  quota checks, lifecycle locks, staging and cross-worker invalidation. Existing
  plugin partial commits remain resumable; every successful partial component
  is recorded and disabled, and the receipt states partial truthfully.
- [ ] Enforce both source and recipient authority at publication without keeping
  DB locks over IO/DNS/model waits. Retry only missing receipt work after
  reconciliation, never a blind re-import. Notifications follow committed
  outcomes and retry independently with a stable occurrence identity.
- [ ] Enforce existing capability switches and sender/pair/recipient installation
  and byte caps. Reset transferred MCP HITL overrides to recipient inheritance;
  learned approvals/allowlists are not portable. File the explicit send and its
  truthful outcome through the shared action sink with receipt idempotency,
  without a peers-to-agents import cycle or duplicate notification action.
- [ ] Cover credential -> explicit test/OAuth -> readiness -> explicit enable for
  API-key, bearer, OAuth and no-auth servers. Credential save/toggle alone do
  not clear auth_required today. Successful validation keeps the received
  server disabled; failure exposes no tools. Use existing connection-test
  accounting for description/embedding work, never automatic receipt-time calls.
- [ ] Run unit and real PostgreSQL/filesystem flow tests for all three kinds.
  Prove review-focus item 3 by opening the recipient's actual retained plugin
  files; sanitizing an in-memory DTO is not its oracle.

## Task 5: Peer transfer UI and origin badge

**Files:** apps/web/src/components/settings/{SkillsSettings,MCPServerCard,
PluginsSettings}.tsx and their item/detail components; new reusable peer transfer
dialog/badge; new typed useCapabilityTransfer hook; current recipient hook and
account lifetime primitives; six locales and corresponding UI/E2E tests.

**Interfaces:** resource rows provide exact kind/id and a snapshot preview; the
dialog submits only the server-validated digest and selected connection.
OriginBadge accepts server sender display metadata and a UTC transfer instant.

- [ ] Write tests for lazy recipients, loading/error/no peers, malicious/long
  sender names, timezone/DST formatting, duplicate clicks, stale account callback,
  partial/failed/lost-response receipts and keyboard focus return. Run red.
- [ ] Integrate one named row action through RowActions, shared dialog, truthful
  outcome report, and a wrapping translated origin badge. No recipient acceptance
  step is introduced; installed components require ordinary manual activation.
- [ ] Show missing credentials via existing MCP forms and disabled controls.
  Verify ordinary edit/delete/export/enable/uninstall behavior and local origin
  retention, plus independent sender/recipient mutations.
- [ ] Run frontend gates and a hermetic two-account flow with controlled API
  responses; inspect mobile/light/dark and full accessible names. No real peer
  message or notification is sent as a test.

## Task 6: JEV typed semantics, bounded service and cache

**Files:** proposed apps/api/src/core/entity_qualifications.py;
apps/api/src/domains/entity_qualification/ small service, prompts adapter and cache;
llm_config/{jev_registry,constants}.py, system_settings models/registry,
core config/constants, infrastructure/cache/key_families.py, spend/decision
declarations; versioned question files; unit/integration calibration fixtures.

**Interfaces:** EmailQualification(category, priority, evidence_scope,
evidence_fingerprint, model, policy_version, assessed_at, expires_at);
EventQualification with category and the same provenance fields.
Proposed qualify_emails/qualify_events accept detached typed observations,
user_id, source_scope, reference time/timezone, run/config and return results
keyed by observation identity. No service receives a long-lived AsyncSession.

- [ ] Freeze category/priority meanings and a multilingual labeled corpus/holdout.
  Add deterministic tests for independent abstention, unknown-first choices,
  confidence ties, class thresholds, sparse evidence and unsupported values.
- [ ] Extend the category Choice with phishing_scam. Add phishing/impersonation/
  fraudulent-payment positives and legitimate banking/security/training/reporting
  negatives; test category precedence, adversarial instructions and scam-claimed
  urgency without a real urgent priority. Low confidence yields no badge. Keep
  two questions per email, account for extra criteria tokens and invalidate the
  prior policy/taxonomy cache version; make no automatic URL/attachment reads.
- [ ] Freeze quality/coverage criteria before opening the holdout. Pin accepted
  unambiguous positive fixtures as well as abstentions, so all-unknown cannot
  pass. Publish per-class sample counts, false positives, coverage and uncertainty;
  tune on calibration only and distinguish mocked contract success from semantic
  evidence required before enabling the new usage.
- [ ] Add native-runtime tests for final request token/byte budgets, two questions
  per email/one per event, local 24-question/32,000-byte ceilings read from the
  transport constants, stable answer binding, unexpected model and malformed
  paid responses. Run red with mocked HTTP and real accounting boundaries.
- [ ] Implement two independently switchable registered usages, typed accepted
  annotations and versioned prompts. Do not copy relevance thresholds or put
  questions in Python prose. One failed/uncertain decision has no generative
  fallback and never mutates canonical source facts.
- [ ] Add cache tests for two users/grants/calendars sharing ids, evidence/detail/
  model/policy changes, urgency expiry, negative caching, Redis outages and
  multi-worker misses with cancellation/owner expiry. Implement the bounded
  cache/flight seam using existing owners/TTLs and declared key families.
- [ ] Enforce parent cancellation/total time/concurrency and both spend ceilings.
  Assert a paid invalid/cancelled native answer is accounted once, a cache hit
  costs no native call, and source results survive optional qualification failure.
- [ ] Run targeted gates. Real JEV calibration, if separately approved for dev,
  uses bounded spend, one attempt per sample, frozen holdout and recorded
  precision/coverage/cost/latency. Leave the new usages off until qualified.

## Task 7: Qualification across chat, ReAct, dashboard and other readers

**Files:** agents/tools/emails_tools.py and calendar_tools.py through small
cohesive adapters; mixins/context projections where needed;
agents/display/{llm_serializer,components/email_card,components/event_card}.py;
agents/tools/react_tool_wrapper.py and context round-trip tests;
briefing/{fetchers,schemas,formatters}.py and synthesis inputs;
web briefing types/MailsCard/AgendaCard, card styling, labels and six locales.
Inventory direct_client_callers/consultation_surfaces and actual other producers.

**Interfaces:** the selected allowed detail observation is qualified once before
publication. A single annotation formatter produces bounded explicit model text
and closed UI labels from the same accepted values. Existing display-only body
fields remain inaccessible to every model projection.

- [ ] Write pipeline and ReAct tests inspecting the actual stubbed model input,
  structured_data, registry and checkpoint reconstruction for one source item.
  Assert metadata mode supplies no hidden body to JEV and unknown/normal
  priority yields no attention badge. This pins review-focus item 4.
- [ ] Write dashboard fetcher -> DTO/cache -> component and synthesis-input tests,
  covering cache hit/miss and all Google/Apple/Microsoft normalized shapes.
  Inventory relationship/background/voice serving paths and give each a tested
  integration or an explicit reason it serves no structured item.
- [ ] Pin the scope of systematic qualification: no new JEV spend on background
  indexing/synchronization/availability-only reads that show no entity and supply
  no evidence to the current answer. Low-level connector clients remain neutral.
  An observation skipped by budget remains unqualified, never default-normal.
- [ ] Wire the service before publication; update compact DTOs and explicit
  response serialization rather than relying on nested generic serialization.
  Add accessible category/priority badges retaining existing unread/important
  provider indicators. No filtering/reordering, provider write or memory update.
- [ ] Add the red 'Phishing/Arnaque' badge to both email renderers and the
  dashboard, with six-locale labels, warning icon and semantic alert/danger tokens.
  Implement a finite outline/halo attention treatment, not the unchanged infinite
  Badge.pulse. Test stable text/contrast, multiple badges, 1Hz/four-second stop,
  reduced-motion suppression, no re-render/history replay, screen-reader naming,
  no repeated live alerts, mobile wrapping and light/dark/OLED rendering.
- [ ] Inspect actual ReAct/pipeline/dashboard-synthesis model inputs for the
  phishing category and its evidence scope. Assert it cannot default to safe,
  normal or personal when unqualified, and that malicious mail instructions
  remain external data rather than authority for a tool call.
- [ ] Test historical messages/bookmarks with no new JEV call, changed revision
  invalidation, feature off/missing key/price/quota/429/timeout, large partial
  evidence, rapid account switch and native-source failure.
- [ ] Run backend/frontend gates and hermetic chat/dashboard flows. Measure total
  cold/warm turn latency and total cost including digest and downstream tokens.

## Task 8: Position projection and native marker host

**Files:** new agents/display/components/places_position.py and pure aggregate
projection module; response_node.py via a cohesive post-selection helper;
display/sentinel_filter.py; new web place-map wire parser, marker controller and
lazy MarkdownPositionMap host; shared SDK/metering helpers extracted from
google-route-map.ts without route behavior changes; MarkdownContent.tsx,
app-config types, key/map-id availability/admission and card styling/locales.

**Interfaces:** proposed PositionMapV1(version, places, unlocated_count,
omitted_count), each place carrying source/card ref, label, lat/lng and safe link.
The inert server sentinel contains no key, executable code or raw provider data.
An authenticated place-map admission reuses the existing Dynamic Maps report
contract while enforcing its own availability policy.

- [ ] Write backend projection/injection tests for zero/one/many places,
  relevant-id exclusion, correlated/reference turns, repeated identities,
  coordinate variants/zero/NaN/Infinity/ranges, missing positions and complete
  list/explicit overflow. Assert no fake LOCATION/tool item or prompt tokens.
- [ ] Write actual response HTML -> sanitizer -> React tests, forged sentinel
  stripping and archived replay. Write SDK-boundary tests for shared loader,
  theme changes, source/account change, mount/unmount, blocked key/offline,
  antimeridian/coincident points and keyboard/list equivalence. Run red.
- [ ] Implement the aggregate Position card once after the final selected place
  cards, in card modes only. Use existing coordinates with no automatic
  Places/geocode/GPS call. Missing coordinates remain visible with links.
- [ ] Add supported AdvancedMarkerElement loading and configured map ID for the
  place controller. Keep route polylines and their styling contract unchanged.
  No new UI dependency and no arbitrary script/iframe allowlist expansion.
- [ ] Integrate click-to-admit with cost display, restricted browser key,
  account/instance quota and idempotent construction reports. Test no report at
  admission or initial render and the same grant on lost report acknowledgements.
  Document the browser-report vs invoice limitation. Pin review-focus item 5.
- [ ] Run frontend/backend gates, route-map regression suite and Docker-dev
  browser flows with mocked SDK/network. If CSP changes, run both native mobile
  probes; otherwise verify required origins are already permitted. A real
  restricted-key browser proof needs a separately bounded dev configuration.

## Task 9: Consolidated documentation, gates and inline self-review

**Files:** CLAUDE.md then generated AGENTS.md; ADR-327 amendment for explicit peer
trust exception and an appropriate new transfer/qualification decision if needed;
existing meetings, plugins, peers, JEV and native card technical docs; knowledge
docs and six-language living maps for any new ADR/domain/infrastructure module.

- [ ] Update documented contracts and examples to the final implementation,
  including disabled receipt, no credentials, trusted peer exception, JEV
  availability/abstention and map activation/accounting. Do not restate code-owned
  thresholds or registry counts; link their source.
- [ ] Regenerate AGENTS.md only with task docs:sync-agents. Run living-map
  generation and strict i18n parity. Use lint:docs:preview for new untracked
  documentation; never fix index-only findings cleared by that preview.
- [ ] Run task lint, task test:backend:unit:fast, the sequential backend coverage
  gate where async/accounting paths changed, task test:frontend and
  task test:frontend:coverage. Run disposable DB replay/integrations and the
  relevant Docker-dev hermetic E2E journeys. Record exact results/counts/skips/
  warnings and environments not verified. Do not use exhaustive backend tests.
- [ ] Review each risk row against implementation and actual assertions inline.
  Verify no namespace, registry member, FK policy, import cycle or spend site is
  left unaccounted, no inherited work was overwritten and no ratchet increased.
- [ ] Present the completed changes and evidence for review. Commit, push or
  deployment remain separate authorization scopes; task ci:fast precedes a
  separately authorized push. Never bypass hooks.

## Sequencing and exit criteria

Recommended order: 1 -> 2; 3 -> 4 -> 5; 6 -> 7; 8; then 9. These are independent
reviewable feature groups, all executed inline. Shared type/policy contracts
precede their consumers; UI work never invents an unimplemented backend status.
Do not bundle an unused scaffold into a separate deliverable.

Implementation may start after the explicit go. Completion requires the
behavioral proofs above, not this analysis or a passing mocked happy path.
No day estimate, model accuracy guarantee or savings claim is inferred from
source size. New product choices require revising this design before dependent
implementation; routine measured technical choices stay with the implementer.
