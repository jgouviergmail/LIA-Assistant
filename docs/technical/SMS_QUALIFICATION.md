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
| Erasure, hosted export invalidation, bounded readable archive and key stability | [erasure](../../apps/api/tests/integration/test_sms_erasure.py), [streaming export](../../apps/api/tests/integration/test_sms_export_stream.py), [isolation](../../apps/api/tests/integration/test_sms_isolation.py) |
| Durable per-destination attempt/fence, timeout and unknown result | [delivery worker](../../apps/api/tests/integration/test_sms_delivery_worker.py), [transport destination](../../apps/api/tests/unit/domains/notifications/test_sms_transport_destination.py) |
| Both assistant modes, proof/budget/card contracts and real compiled tool-to-model flow with fake model | [tool flows](../../apps/api/tests/integration/test_sms_tool_flows.py), [compiled model flow](../../apps/api/tests/integration/test_sms_agent_model_flow.py), [SMS unit contracts](../../apps/api/tests/unit/domains/agents/sms/) |
| Relationship exact aggregates, alias/partial-directory cases and publication freshness | [relations](../../apps/api/tests/integration/test_sms_relations.py) |
| Missing, invalid or loading 360 scope never adds SMS; explicit SMS selection survives | [server scope](../../apps/api/tests/unit/domains/relations/test_overview_scope.py), [form commit](../../apps/web/src/components/relations/__tests__/RelationScopeSection.test.tsx) |
| Home counts without decryption, profile-lookup withdrawal, paid-result refusal and consultation trail | [summary](../../apps/api/tests/integration/test_sms_summary.py), [briefing SMS](../../apps/api/tests/unit/domains/briefing/test_sms_section.py) |
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
