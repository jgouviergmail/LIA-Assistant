# Mes SMS — qualification and reproducible evidence

The [approved plan](../superpowers/plans/2026-10-19-phone-ingestion-sms.md) and
[design](../superpowers/specs/2026-10-19-phone-ingestion-sms-design.md) define the acceptance contracts.
This reference distinguishes real local database/browser execution from simulated providers.

## Coverage map

| Contract | Verification source |
|---|---|
| Strict/malformed wire values, bearer scope, owner/source/token revocation, idempotence and atomic writes | [HTTP ingestion](../../apps/api/tests/integration/test_sms_ingest_http.py), [ingestion](../../apps/api/tests/integration/test_sms_ingestion.py), [authority races](../../apps/api/tests/integration/test_sms_authority_races.py) |
| Exact pagination, owner isolation, broad-query refusal, Unicode/index bounds and sender selection | [reads](../../apps/api/tests/integration/test_sms_reads.py), [read races](../../apps/api/tests/integration/test_sms_read_races.py), [sender selection](../../apps/api/tests/integration/test_sms_sender_selection.py), [index](../../apps/api/tests/integration/test_sms_search_index.py) |
| Confirmed mutations, two browser sessions, stale/expired approvals and secret delivery once | [commands](../../apps/api/tests/integration/test_sms_ui_commands.py), [command races](../../apps/api/tests/integration/test_sms_ui_command_races.py), [authority boundaries](../../apps/api/tests/integration/test_sms_ui_authority_boundaries.py) |
| Direct settings toggles, strict session-only input, concurrent fields, delivery cancellation and consent invalidation | [preference settings](../../apps/api/tests/integration/test_sms_preference_settings.py), [browser settings](../../apps/web/e2e/smoke/sms-settings.spec.ts) |
| Erasure, hosted export invalidation, bounded readable archive and key stability | [erasure](../../apps/api/tests/integration/test_sms_erasure.py), [streaming export](../../apps/api/tests/integration/test_sms_export_stream.py), [isolation](../../apps/api/tests/integration/test_sms_isolation.py) |
| Durable per-destination attempt/fence, timeout and unknown result | [delivery worker](../../apps/api/tests/integration/test_sms_delivery_worker.py), [transport destination](../../apps/api/tests/unit/domains/notifications/test_sms_transport_destination.py) |
| Both assistant modes, proof/budget/card contracts and real compiled tool-to-model flow with fake model | [tool flows](../../apps/api/tests/integration/test_sms_tool_flows.py), [compiled model flow](../../apps/api/tests/integration/test_sms_agent_model_flow.py), [SMS unit contracts](../../apps/api/tests/unit/domains/agents/sms/) |
| Relationship exact aggregates, alias/partial-directory cases and publication freshness | [relations](../../apps/api/tests/integration/test_sms_relations.py) |
| Missing, invalid or loading 360 scope never adds SMS; explicit SMS selection survives | [server scope](../../apps/api/tests/unit/domains/relations/test_overview_scope.py), [form commit](../../apps/web/src/components/relations/__tests__/RelationScopeSection.test.tsx) |
| Metadata counts without decryption, bounded personal previews, source withdrawal, paid-result refusal and consultation trail | [summary](../../apps/api/tests/integration/test_sms_summary.py), [briefing SMS](../../apps/api/tests/unit/domains/briefing/test_sms_section.py), [personal projection](../../apps/api/tests/unit/domains/briefing/test_sms_card_preview.py) |
| Proactive consent, useful offered IDs, post-delivery bookkeeping, private audit and no implicit continuity memory | [heartbeat](../../apps/api/tests/integration/test_sms_heartbeat.py), [source decisions](../../apps/api/tests/unit/domains/heartbeat/test_sms_source.py), [private dispatch](../../apps/api/tests/unit/infrastructure/proactive/test_sensitive_dispatch.py) |
| Radio exclusion before SQL limits, flash and personal corner | [real PostgreSQL reader](../../apps/api/tests/integration/domains/radio/test_reader_notifications_db.py) |
| Frozen migration downgrade/upgrade, columns/indexes/foreign keys | [migration round trip](../../apps/api/tests/integration/test_sms_migration.py) |
| Version repair, atomic replacement and arrivals/erasure concurrent with staging | [index version repair](../../apps/api/tests/integration/test_sms_index_generation.py), [rebuild](../../apps/api/tests/integration/test_sms_index_rebuild.py) |
| Mobile/desktop archive, literal cards, relationship view and home timezone/counts, keyboard/axe/overflow | [archive](../../apps/web/e2e/smoke/sms-archive.spec.ts), [cards](../../apps/web/e2e/smoke/sms-chat-cards.spec.ts), [relations](../../apps/web/e2e/smoke/sms-relations.spec.ts), [home](../../apps/web/e2e/smoke/sms-home.spec.ts) |
| Old and in-flight home text cannot return after an SMS invalidation; no automatic paid regeneration | [real hook](../../apps/web/src/hooks/__tests__/useBriefing.application.test.tsx) |
| One committed source event traverses archive, both model/card projection, relation, home, durable notification, proactive settlement and streamed export | [cross-surface flow](../../apps/api/tests/integration/test_sms_cross_surface_flow.py) |
| Actual serialized tool pages fit the smallest receiving model budget; export text cannot activate HTML or Markdown images | [small-model budgets](../../apps/api/tests/unit/domains/agents/sms/test_tool_budget.py), [literal readable export](../../apps/api/tests/unit/domains/account_export/test_sms_rendering.py), [shared literal projection](../../apps/api/tests/unit/domains/shared/test_markdown_literal.py) |

## Capacity and degraded cases

The [index qualification](../../apps/api/tests/integration/test_sms_qualification.py) emits the actual population, term/index occupancy, ingestion duration, resident-memory delta and PostgreSQL EXPLAIN timing for rare/common/CJK queries. This is a reproducible local benchmark, not a production SLO or a claim that PostgreSQL will choose one physical plan on every installation.

The export test measures streaming memory on synthetic messages. Body/index/query/directory/time/receipt/archive bounds are read from the code, not copied into an independent prose limit. Unicode normalization, code-point continuations, timezone/DST grouping, partial directories, concurrent arrivals, malformed source proof, SQL timeouts and source withdrawal have focused regressions.

Tests use isolated PostgreSQL/Redis and fake model/transport seams. No private phone data, production write or paid provider call is required. Backend/TypeScript static checks, global shrink-only ratchets, registry/i18n completeness and documentation preview are separate gates; a passing unit suite is not their substitute.

## Local measurements

Recorded on 2026-10-20 in owned disposable Docker services. These are observed results on synthetic data, not production guarantees or new thresholds.

| Probe | Observed result |
|---|---|
| Controlled committed-source flow and explicit fake-transport worker tick | Service commit acknowledgement 26.759 ms; explicit worker tick 346.231 ms; fake destinations reached 1998.669 / 2097.557 ms after acknowledgement, including the intervening archive/tool/relation/home reads |
| Actual PostgreSQL ingestion/index | 2000 retained messages, 30000 terms, 2916352 index bytes; ingestion 4.882 s; observed resident-memory delta 847872 bytes |
| PostgreSQL rare/common/CJK query plans | 0.677 / 0.037 / 0.024 ms execution time |
| Actual streaming SMS writer and literal renderer, synthetic row generator | 10000 messages; 138380 ZIP bytes; 1.073 s; traced Python peak 809730 bytes; sampled resident-memory delta 643072 bytes; every JSON row/body/order and readable entry checked |
| Full schema custom-format dump and restore into a second empty database | 552655 dump bytes; dump 0.396 s; restore 2.324 s |
| Application verification after restore | 100 decrypted retained messages, 1 excluded event and 101 receipts; 101 identical retries remained duplicates; 100 index rows rebuilt in 0.037 s; no transport started |

The controlled flow uses a manually invoked worker and fake external transports. Its acknowledgement timing is the SQL service boundary, not an iPhone/TLS HTTP round trip; its elapsed delivery values are not scheduled polling or physical push latency.

The export volume probe exercises the production writer and SMS renderer with a generator; its rows do not come from a large SQL database. The integration export tests separately verify the actual owned-row/decryption/streaming boundary. Memory figures above describe this probe, not an operating-system-wide peak. The restore preserves wrapping material and proves application readability/idempotence; reconciliation of later erasures or revocations remains the operator's responsibility described in the recovery runbook.

## Software validation record

The broad backend run executed the Taskfile's serial CI selection and its unchanged coverage floor in a disposable Linux checkout. The original worktree, index, Git configuration and object store were not modified by the test harness. PostgreSQL and Redis belonged to this qualification; external transport/model seams were simulated.

| Verification | Observed result |
|---|---|
| Whole backend unit selection with coverage | 44,989 passed, 18 skipped, 9 deselected; 2137.00 seconds; 78.99% whole-source coverage |
| Final JSON-metadata reader follow-up, domain schemas/taxonomy and global file-size/exception guards | 85 passed, including the 16 nominal/hostile metadata cases |
| Whole backend Ruff, Black and MyPy | Passed; MyPy checked 3486 source files |
| Latest canonical CI marker census | 51226 collected; 49 existing intentional out-of-PR cases; no new orphan |
| Focused SMS/ingestion backend regression with real database flows | 543 passed; measured scoped coverage 90.91% |
| Separate final regression selection for global-run corrections and the debrief quota | 543 passed; this overlaps other selections and is not added to their counts |
| Whole frontend coverage run | 13297 passed across 1090 suites; statements 87.74%, branches 81.77%, functions 85.52%, lines 89.27%; subsequent affected scope/hook and capability selections also passed |
| Built-application Chromium journeys | Initial whole run: 657 passed, two debrief-fixture failures; corrected fixture, then all 21 affected journeys passed. This is not presented as one uninterrupted green whole-browser run |
| Final frontend lint, nonincremental TypeScript, accessibility/hooks/complexity ratchets and production build | Passed; 422 generated pages; temporary Next type includes restored exactly |
| Installer/release-script regression and shell readiness assertions | 331 passed; shell assertions passed; no deployment executed |
| Complexity, coupling, hygiene, typing-debt, lockfile/CI/observability, wake/dependency-tool and documentation checks | Checked separately; no quality gate relaxed |

The final whole-backend content-tree ID is `59549ba8103549ad637037b52656c6d3f08972e1`. It includes the final JSON-metadata reader and its hostile-input tests. The repository now explicitly selects the supported CTracer measurement core, with the same test selection and coverage floor. A preceding SysMonitor run had one native `ast.iter_fields` iterator exception; the unchanged guard passed in isolation. The recorded result establishes the selected validation configuration, and does not assert a proven upstream defect. See the [coverage core reference](https://coverage.readthedocs.io/en/7.13.5/config.html#run-core). Later changes only completed documentation. Counts from separate selections above overlap and are not added together.

The skipped backend cases remain explicit: environment-dependent Docker socket, process-limit, PowerShell and feature-flag paths, plus existing intentional non-applicable cases. The marker census retains the repository's existing out-of-PR allowlist. This record does not claim that every CI job, physical device or optional integration ran.

Raw local logs, coverage JSON/XML and the validation receipts are retained under the ignored task directory `.tmp/sms-implementation/`; the commands and durable test contracts are in the approved plan and the coverage map above. The browser acceptance exercised desktop and a mobile viewport, keyboard navigation, account timezone differing from browser timezone and no critical/serious axe findings on the checked SMS surfaces.

## Adversarial review

The reviews were performed INLINE at each lot boundary, including source inspection and hostile/degraded flows; no subagent reviewed or implemented a lot. The final review covered indirect readers, registries, exports, source withdrawal, model budgets and existing non-SMS contracts.

Concrete findings corrected before closure include:

- The new relationship debrief lookup alias omitted the existing daily-budget dependency. An exhausted-budget HTTP regression proved the bypass; both the historical route and the alias now reject before model execution through the same dependency.
- A missing or old relationship overview scope must never opt into SMS. Server defaults and frontend fallback exclude it; an explicit selection remains available and persistent.
- Serialized tool results must fit the smallest model slot that will receive them, including framing overhead. Small-window regressions exercise both assistant modes and continuation boundaries.
- Readable personal exports and native cards preserve SMS as literal external text; hostile HTML and Markdown images cannot become active content. Fresh source proofs and account-bound invalidation prevent re-serving withdrawn content through model context or home caches.
- Capability routes, model/prompt vocabulary, client-call recording, six-language treatment labels, constellation placement, offline evaluation and observability were checked against their independent inventories. Generated skill templates do not implicitly gain the sensitive SMS tools.
- Full-backend typing, beyond the changed-file check, found a reader assuming generic JSON registry metadata was a string list. Eight hostile-metadata cases first failed beside eight passing nominal cases. The reader now narrows lists and string members explicitly; both the focused tests and full-backend typing were replayed.
- Staged index rebuilding was exercised against real concurrent erasure and arrivals. Durable deliveries keep their fencing and terminal unknown states; a timeout is never converted into a claim of physical exactly-once delivery.

The first whole backend coverage run also exposed five qualification issues: an instrumented timing probe, an incomplete heartbeat mock, a file-size boundary, a clean-container Git prerequisite and an empty exception handler. The timing budget and billing assertions were retained; cache-state extraction preserved the original calculation; no quality ceiling, network guard or permission rule was relaxed. A fresh normal-runner regression selection then passed before freezing the final validation snapshot.

## Acceptance limits

Browser evidence exercises the actual built Next application against hermetic API fixtures. The compiled agent test executes the real graph/tool path against a fake model. Neither proves a specific paid model's judgment or physical push delivery.

An actual iPhone must still confirm its iOS trigger criteria, permissions, lock/background behavior, reachability and native/browser push behavior. The [Shortcuts guide](../guides/GUIDE_IPHONE_SHORTCUTS_SMS.md) gives a synthetic acceptance sequence and states the generic native relay boundary. Unknown transport acknowledgements are never presented as exactly-once physical delivery.

## Final self-assessment

| Question | Evidence-bounded assessment |
|---|---|
| Is the requested software implemented and the cross-domain scope accounted for? | Yes: archive/settings, ingestion/token authority, notifications/Alerts, both assistant modes/cards, relations, home/proactivity, export/purge and indirect consumers have their owned paths and regressions. |
| Were architectural assumptions checked against the application? | Source contracts, real migrations/SQL races, independent completeness guards and the cold-review findings above were verified. Physical iOS behavior remains outside those proofs. |
| Are model costs, quotas, registries and memory accounted for? | Ingestion invokes no model or embedding. Later authorized reads use receiving-slot budgets and existing accounting/quotas. SMS source proofs, sensitive contexts and consultation/effect registries have producers/readers/guards. Later discussions retain LIA's normal memory contract. |
| Is responsive UX verified? | The checked built Chromium journeys cover desktop/mobile viewport, keyboard, literal content, timezone and axe checks; this is not Safari or physical iPhone certification. |
| Did the testing plan run successfully? | The software selections and structural checks recorded above passed after correction. Historical failed probes are disclosed. The device/provider cases and explicit environment skips remain unexecuted. |
| Is there a known remaining implementation blocker? | None identified by these checks. Real Shortcuts, locked/background behavior, certificate reachability and physical push acceptance remain required before certifying that deployment/device combination. |

An absolute 100% or "perfect under every real condition" claim would exceed the evidence. Software closure is supported by the recorded tests and reviews; the physical acceptance boundary is deliberately left open. Local integration into the main checkout was subsequently authorized and is verified separately from these branch qualification results. No publication or deployment is included.

## Local integration follow-up

The local Windows commit hook exposed an additional test-runner limit: pytest derived a CJK/emoji test ID from the full long payload, exceeding the Windows environment-variable limit while setting `PYTEST_CURRENT_TEST`. A focused replay reproduced the setup/teardown errors. Short explicit parameter IDs retain every payload and assertion; the complete hook is rerun before integration. The ADR index and all backend environment templates, including minimal-production and demo profiles, are included in this handoff. Actual local environment values are preserved and their encrypted copies are checked without exposing secrets.

## Reading directly in SMS settings

The shared archive now mounts directly below statistics in an initially open disclosure at `/dashboard/settings?section=sms`. Existing archive links redirect there while preserving the focused message. Setup and management folds retain their previous defaults.

TDD reproduced missing inline consultation and stale focused content after source invalidation. The focused reader now withdraws old text before rereading, including after deletion from the same settings pane, and subsequent refreshes preserve keyboard focus. The settings archive has its own component to keep the complexity ratchet unchanged.

Hermetic Chromium journeys exercise the built application at mobile and desktop widths, keyboard collapse/reopen, private search failure/retry, legacy-link targeting, confirmed deletion of the focused message, unchanged direct preferences/token approval, axe and reflow. No backend contract, LLM call, permission, storage setting or environment variable is added by this adjustment.

## Personal dashboard previews follow-up

The subsequent dashboard refinement replaces the archive footer link with the latest retained messages using the shared Mails row primitive. `BRIEFING_MAX_SMS_ITEMS` is declared in backend settings and the applicable unencrypted backend environment profiles/templates; encrypted environment files are outside this adjustment. The older metadata-only dashboard decision is amended in ADR-357, while other aggregation readers and model-consent boundaries retain their prior contracts.

TDD covers the default/configured limit, archive-wide descending selection beyond the recent-count window, batched identity resolution, bounded excerpts, old metadata-only response compatibility, and rejection after concurrent arrival or erasure. Projection canaries prove that personal preview text never enters the generic model prompt. Final source-proof checks protect publication after slower sibling fetches and after text generation during a global refresh. Real authenticated [HTTP tests](../../apps/api/tests/unit/domains/briefing/test_sms_http_privacy.py) verify cache prohibition on cards and both refresh routes. Browser-hook regressions cover immediate preview withdrawal, failed refresh and an older first-load response.

The built Chromium journeys exercise the latest-message rows at mobile and desktop widths, account timezone differing from the browser, literal hostile text, keyboard navigation into the focused message, axe and reflow. Real PostgreSQL integration tests exercise the card reader, its internal non-serialized proof and concurrent source changes. These display reads add no model call, token budget, persisted memory or implicit assistant permission.

## Radio, phone and scoped-erasure follow-up

SMS is now registered as an explicit Radio personal source and owner phone/direct-Live
read domain. The spoken adapter keeps catalogue/capability identity while validating
flat filters through the existing request models. Radio uses sensitive day facts,
receiving-slot projection budgets and private source proofs. No new ingestion model,
memory writer, mutation capability, dependency or environment setting is introduced.

The archive defaults to sender threads and exposes the existing reviewed command for
one message, a whole sender or an account-civil-day interval. Read-only relation and
notification surfaces remain read-only. SMS is placed directly above provider emails
in relations. The requested capture-time sentence is removed from visual output;
timestamp provenance remains available to the data/model contracts.

The INLINE cold reviews found and corrected a source invalidation race in sender
results, a confirmation dialog closing before commit, and a late initial message
read stealing keyboard focus. Radio facts now put excerpt/read-status limitations
before body text so the existing character clamp cannot remove them. The spoken
result no longer suggests a continuation tool unavailable to the phone host.

| Verification | Observed result for this follow-up |
|---|---|
| Whole frontend coverage selection | 13389 tests across 1098 suites passed; all global and scoped floors passed |
| Whole backend strict typing | MyPy passed over 3496 source files; changed-source Ruff and Black also passed |
| Built Chromium SMS journeys | 22 passed, covering mobile/desktop deletion scopes, cancellation/confirmation, focus recovery, sender default, relation ordering, source settings, title geometry, accessibility and reflow |
| Real PostgreSQL SMS integration | 30 passed: exact deletion retained sets, direct source consent/withdrawal, export, source summaries, command confirmation and races |
| Application and E2E TypeScript | Clean nonincremental checks passed |
| Shrink-only quality gates | Backend complexity tightened by one hotspot; runtime cycle, hygiene, typing-debt, locale and lockfile/CI-parity checks passed |

The new [channel integration](../../apps/api/tests/integration/test_sms_channel_reads.py)
uses committed source rows and verifies consent off/on, withdrawal and erasure for
both direct readers. The [Radio tests](../../apps/api/tests/unit/domains/radio/test_sms_source.py)
exercise actual listener-day source exclusions, hostile prompt framing, missing/stale
proof and erasure during writing before speech. The final ten source tests also
withdraw access during checking, speech and mixing: no new audio is published,
spent speech usage is retained, and an older unrelated output remains untouched.
An initial simulation fixture was correctly rejected for using a news anchor on
sensitive personal material; the corrected fixture uses the authorized host, with
the production privacy rule unchanged. The
[spoken-reader tests](../../apps/api/tests/unit/domains/agents/telephony/test_sms_reads.py)
exercise disabled domains/capabilities and malformed, foreign or withdrawn proof.
Existing literal JSON/Markdown export tests were rerun against PostgreSQL; the export
already included SMS and required no production change.

The broad fast-unit selection also found an older SMS guard forbidding the phone
domain entirely. Its expectation now matches the requested explicit native reader,
while retaining the original prohibition of an extra collection-decision call.
Its whole module and the general admin-route guard passed together (8 tests).
Administration source-inspection and documentation guards passed in a native Linux
copy with a private prospective Git index (24 tests); Git-isolation tests passed
with a container-only qualification identity (2 tests). The original Windows index,
Git configuration and concurrent staged changes were preserved. These are separate
replays and are not presented as an uninterrupted green broad run.

The fast backend selection initially collected 45263 cases. On the Windows bind
mount, 44758 passed, 136 were skipped, and six failed before interruption of the
last slow prompt-source guard. One failure was the obsolete phone-domain assertion
above; three concerned source inspection with reused Windows Python cache paths,
one used the original index without the new files, and one lacked a container Git
author email. All six were superseded by the passing replays described above.
The unchanged pure prompt guard then passed all 392 cases on a native source copy.
A result census confirms every non-prompt case had completed before interruption;
the selections overlap and their counts must not be added. The three newly added
production-withdrawal cases ran in the separate final ten-test source selection.

The 136 skips include existing tests requiring an unavailable database, Docker socket,
PowerShell or enabled optional features. They are not treated as passes. The dedicated
SMS PostgreSQL selection above did run its actual database flows. No physical-phone
or paid-provider acceptance was attempted. The built frontend's source and locale
snapshot matches all 2684 current files checked; no source mismatch was found.

## SMS terminology and direct single-message deletion

The UI no longer presents retained SMS as an archived state: dashboard, settings,
search hints, help, HTML-card continuation labels, assistant descriptions and the
documentary map titles use received or retained messages in all six languages.
Existing technical identifiers and receipt/schema compatibility remain intact.

A visible message has one red trash icon under its date. Clicking it invokes the
existing authenticated prepare/confirm command flow without opening a dialog. The
client accepts only that same single ID with no sender/date/all selector, at most
one affected row and an unexpired proposal. Account switches, duplicate clicks and
lost acknowledgements remain guarded; the action never retries automatically or
publishes a secret. Group deletion and agent actions retain reviewed confirmation.
Keyboard focus returns to a surviving disclosure only when the deleted control
disappeared and the person has not focused another control.

The real SQL retry test covers both stable event IDs and stable payloads without
an ID. Erasure keeps a content-free receipt, so the same source/event/payload cannot
recreate the message. Changing source/event identity, or changing an unkeyed payload
including its date, can represent a new event; this is not semantic deduplication
across devices or newly generated IDs.

| Verification | Observed result for this refinement |
|---|---|
| Frontend TDD | Four intended RED failures before implementation; 43 targeted tests passed after implementation, including account switch, widened scope, busy controls, unknown acknowledgement, focus and localized icon names |
| Full frontend coverage | 1098 suites / 13398 tests passed; statements 87.88%, branches 81.92%, functions 85.64%, lines 89.41%; existing global/scoped floors passed |
| Frontend quality | Full ESLint, clean nonincremental application/E2E TypeScript and all a11y/hooks/complexity ratchets passed without a baseline increase |
| Docker production builds | Initial SMS build and final documentary-title build passed |
| Built Chromium journeys | 22 passed at mobile/desktop widths, including a single keyboard activation without a dialog, icon geometry below the date, focus after deletion and retained group confirmations |
| PostgreSQL integration | 24 passed: both non-resurrection identities, erasure, export, command confirmation and race flows |
| Backend regression | 76 SMS/tool/registry/Radio tests passed; final HTML-card labels and shared rendering corpus separately passed all 14 cases |
| Documentation and locales | Six-language key parity, documentary translation fingerprints and documentation preview passed |

The first concurrent coverage/build run had one timeout in the unrelated eye-style
settings test (13397 passed). Its 33-case module passed in isolation with the same
deadline. A fresh full run with bounded workers and no competing build/browser work
passed all 13398 tests; no test timeout, threshold or assertion was relaxed. The
initial backend harness also named a nonexistent card-test path; that run was stopped
and the corrected selection above passed. These failures are not treated as passes.

The staged index remained byte-for-byte unchanged during this refinement. A final
source comparison found only three concurrent French administrator LLM-slot labels
outside SMS; they were preserved. Actual phone/provider acceptance remains separate
from the software evidence above. This refinement adds no environment variable,
dependency, schema migration or new LLM call.

These checks run the built UI with hermetic APIs and simulate model/speech boundaries.
They do not certify physical phone calls, an actual paid Radio model or already
delivered audio recall. Original source deletion and previously delivered copies
retain their separate lifecycle contracts described in the technical reference.

## Relations and Alerts presentation refinement (2026-10-20)

Alerts now uses the shared notification hub shell, timeline rows and pagination
for received SMS, ordered by the existing server predicate (received time then
ID, both descending). Pages remain lazy and use opaque cursors in a private POST
body. Paging retains the current page and its keyboard controls during the read;
source invalidation clears it immediately. Closing the section clears its snapshot
before the next opening. Settings keeps its sender-first default independently.

Relations presents SMS, calls, relayed messages, emails and appointments in nested
panels. The requested sections no longer use a left accent stripe. SMS and calls
are native links whose content is the selection target; the explicit SMS-open text
is removed. The destination opens the exact owned SMS or call in settings. Older
calls use an authenticated owner-scoped read and the existing public call projection;
recent calls reuse their loaded row. The selected call preserves its visible civil
day, disclosure and actions. A delayed read cannot steal focus after the person has
moved elsewhere. Memories and messages carry theme-coloured decorative icons.
Email selection, direction labels, expired-message placeholders and appointment
roles retain their previous contracts. The simplified section titles ship in all
six languages.

The first complete frontend run identified an authentication coupling while SMS
was disabled. The capability boundary now excludes the account-bound subtree,
and all existing notification-hub tests pass without adding a test-only provider.
The first complexity gate also rejected two new hotspots; extracting the read
projection and history toolbar corrected them rather than raising a baseline.
No additional model call, environment variable, memory write, schema migration or
data-export shape is introduced by this refinement.

| Verification | Observed result |
|---|---|
| Full frontend coverage | 1099 suites / 13407 tests passed; 87.89% statements, 81.94% branches, 85.65% functions, 89.43% lines; all existing floors passed |
| Frontend quality | Full ESLint, cold application and E2E TypeScript, a11y/hooks/complexity ratchets passed; no baseline increase |
| Backend | 14 route unit tests and 16 real PostgreSQL repository tests passed, including foreign/missing IDs and history outside the recent page; both touched sources passed MyPy and Ruff |
| Built UI | Docker production build passed; 40 Chromium scenarios qualified across desktop, mobile, the reflow floor, six locales, keyboard navigation, literal content and axe checks |
| Visual review | Built mobile Relations subpanels and the paginated SMS Alerts timeline inspected from captured screenshots |
| Docker dev runtime | The running HTTPS API's OpenAPI document exposes `/api/v1/telephony/calls/{call_id}` after its automatic source reload; no service restart was needed |
| Source integrity | Eight changed frontend implementation files and all eighteen relevant locale checks matched the built snapshot; staged index unchanged |

The first browser attempt passed 38 scenarios and failed the two new older-call
journeys because their mock used the reserved-name lookup route for an ordinary
person. The fixture now uses the application's `relationReadEndpoint` generator;
both journeys then passed against the same build, including exact ID navigation,
opened details, keyboard focus and accessibility. No product fallback, assertion
or timeout was relaxed. The complete quality script also passed after correcting
its Windows line ending; its initial wrapper failure remains in the evidence log.

Concurrent proactive-discussion files and locale changes were preserved. The
qualified native snapshot freezes the implementation above; these checks do not
claim qualification of unrelated edits made later in the shared workspace.
