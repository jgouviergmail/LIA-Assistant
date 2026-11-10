# Cross-application adjustments — implementation ledger

Plan: [approved execution sequence](2026-11-08-cross-app-adjustments-plan.md).
Implementation authorised on 2026-11-09. Inline execution only; no Git mutations.
The initial working-tree inventory is in `output/implementation-20261109/initial-status.txt`.
Pre-existing staged changes belong to concurrent work and are preserved.

| Lot | State | Evidence / cold review |
|---|---|---|
| 0 Contracts and baseline | Qualified; browser contracts exercised in 7–9 | Display search RED (11 missing behaviour cases), then 21 backend and 11 frontend tests pass. Existing identity rules unchanged. |
| 1 Automatic display schedule | Qualified; final aggregate gates in 9 | 2,028 backend cases plus 15 profile cases, 6 real PostgreSQL cases, 154 frontend cases, 3 browser engines; strict React/complexity, cold tsc and scoped MyPy pass. |
| 2 Knowledge-space filters | Qualified; aggregate gates in 9 | 553 domain tests, 15 PostgreSQL/HTTP cases, 23 frontend cases, 6 browser journeys with axe; strict types, CC, cycles and size pass. |
| 3 Activity timeline | Qualified; aggregate gates in 9 | 53 unit cases, 10 PostgreSQL cases, 19 frontend cases, 3 browser engines with axe; cold types, CC and documentation preview pass. |
| 4 Received / upcoming sections | Qualified; aggregate gates in 9 | 2,058 backend unit cases; native PostgreSQL races, migration and quota-ceiling corpus; 69 frontend cases plus client URL tests; 39 browser journeys across three engines; strict types, size, CC and cycles pass. |
| 5 Direct peer messages / delivery | Qualified; aggregate gates in 9 | 2,098 unit cases, 66 PostgreSQL cases including migration and races; 17 final cancellation/export cases; strict types, CC, size, cycles and documentation pass. |
| 6 Accounted selection assists | Qualified; browser integration in 7–8 | 757 expanded cases, 282 final API/stream/boot cases; 16 PostgreSQL memory cases; strict types, size, cycles, CC and docs preview pass. |
| 7 Generic selection menus | Qualified; final aggregate gates in 9 | 265 unit cases plus microphone/target regressions; 12 three-engine keyboard/edit/undo/axe journeys. Complexity ratchet reduced. |
| 8 Native creation handoffs | Qualified; aggregate gates in 9 | 498 native integration cases, 75 form hardening cases, 34 review cases, 21 browser-derived regressions and 8 final focus/position cases; 90 journeys pass across Chromium, Firefox and WebKit. |
| 9 Integrated qualification | Completed within the limits below | Aggregate suites and repaired failures recorded below; working-tree documentation passes, while the index-based guard awaits the user's Git operation. |

Prior analysis evidence is not implementation verification. Each completed lot must
record fresh commands, outcomes, a separate adversarial review and remaining limits.

## Lot 0 review

Cold review: display matching deliberately uses NFD/lowercase, not identity NFKD/casefold;
literal percent/underscore remain data. The shared Unicode corpus pins both runtimes.
No SQL filter may be narrower than this matcher. No dependencies or baseline increases.
Browser selection probes from the counter-review are promoted with the real menu in lot 7;
handoff implementation and its subscription tests belong to lot 8. They are not claimed done.
Commands and summaries: `output/implementation-20261109/lot0-{backend,frontend}.txt`.
The first sandboxed backend run stalled reading the external tiktoken cache; the owned
process was stopped and the same test ran with cache access. No application infrastructure used.

## Lot 1 cold review

Reviewed the schema/profile/assistant vocabulary, migration, merged-write locking,
bootstrap and provider lifecycle, native controls, localization and rendered journey.
The review exposed retained callbacks after account change/unmount and a failed
schedule being dropped by a later mode write. Added failing behavioural tests and
fixed the owning queue/identity checks. No API writes from the clock. One timer
and observer per provider, cleaned up on unmount. No LLM, ledger or quota path added.

Fresh evidence in `output/implementation-20261109/`: `lot1-backend-final.txt`
(2,028 passed), `lot1-integration.txt` (6 passed including independent concurrent
transactions and upgrade/downgrade), `lot1-frontend-final.txt` (154 passed),
`lot1-browser-final.txt` (Chromium/Firefox/WebKit, 3 passed, narrow viewport),
`lot1-strict-react.txt` (zero new violations), `lot1-types.txt`, `lot1-e2e-types.txt`,
and `lot1-mypy.txt` (six files; existing unused override notes only).

The initial full frontend gate found new synchronous effect-state updates; these
were removed by deriving account snapshots during render and observing the actual
OLED DOM state. The full aggregate gate is rerun after the correction. No ratchet
ceiling was raised. Browser harness corrections: relay the dev server's fixed HMR
channel; click the visible radio label instead of the clipped native input.
Physical-device/assistive-technology qualification remains a final-suite limitation.

Final cold review reproduced a stale profile overwriting a failed local preference;
the account-owned choice now retains the failed change and clears its error on
account switch (RED `lot1-profile-red.txt`, GREEN included in the 154 cases).
The complete backend fast run measured 53,461 passed / 30 skipped / 4 failed:
three profile-fixture failures were fixed without weakening the oracle (15 rerun
cases pass); the documentation guard sees the Git index and cannot see this new
document or a concurrent new plan. Documentation preview passes; no Git mutation
was made. The full frontend static gate passes. The seven existing Chromium
settings journeys pass after correcting the radio-group scope in the test.

The full frontend run on the earlier snapshot measured 20,381 passed / 37 failed
and one unhandled missing-provider exception. All failures belong to the four
theme/provider test modules subsequently corrected and rerun (154 + 3 cases);
this is not claimed as a green global run. Repeat the whole suite in lot 9.

## Lot 2 cold review

Reviewed the entire ownership/query/projection/mutation path, rather than only
the displayed first page. One SQL snapshot supplies complete metadata and
counts; search uses the display normalizer, includes all file states, retains
managed and inactive spaces, excludes system/foreign spaces, and never applies
the creation quota as a read cap. Filename aggregation is disabled for name
search. Sorting ends on the primary key; filenames and document bodies never
leave this DTO. No model call, database migration or register change.

On the client, new criteria retire the prior request and hide its old data;
filtered mutations publish account-scoped invalidations. The shared toolbar
uses native controls and wraps on phones. A failed read exposes retry rather
than an empty collection; switching account discards the search and forms.
The previous three mocked statistics tests were replaced by actual PostgreSQL
isolation/count/query-count tests, without weakening their assertions.

Evidence under `output/implementation-20261109/`: `lot2-unit.txt` (553 passed),
`lot2-integration-final.txt` (15 passed), `lot2-frontend.txt` (23 passed),
`lot2-browser-final.txt` (6 passed, both routes × Chromium/Firefox/WebKit,
390px viewport and scoped WCAG axe), MyPy/cold app + E2E tsc/i18n/ESLint
and complexity/cycle/size guards pass. A historical corpus beyond both current
creation quotas measured 1,111 file metadata rows in 0.0143 seconds for the
listing query in disposable PostgreSQL (`lot2-integration.xml`), not a production
load guarantee. No frozen size/complexity entry was improved by this change;
no baseline was raised. The service shrank and stays below its cap.
Initial browser correction: the registered settings token is `rag-spaces`.
One attempted guard command named a nonexistent complexity test; the actual
`task lint:cc` and size guard were then run successfully.

Owned disposable resources: Redis container `lia-adjustments-20261109-redis`
(`425080a5bf98493a440eb9b5974298f05ff3eeb6a39b8460658deae9b6c58b72`),
loopback-only development relay on port 3219. Remove these at final cleanup.


## Lot 3 cold review

All seven source streams match the displayed text before capping and count the
complete owned window in one statement. A text query streams that statement in
bounded batches through the shared Unicode matcher; an unfiltered query carries a
window count. This documented departure from an SQL-only text predicate avoids a
second, unproved collation authority. Source projections load no embeddings,
undisplayed journal bodies, routine prompts or relationships. A cancelled cursor
is closed; no model, provider, cache, migration or register change is involved.

Cold review found and corrected three defects: creation and closure of one loop
competed for one pool; merging capped pools could skip an unseen earlier event;
a retained pagination callback could revive after filter A → B → A. Separate
streams, a provably ordered prefix and a per-filter generation address them.
One hundred deterministic tie-heavy corpus simulations compare the capped merge
with the complete reference. The server's upper instant travels on later pages;
it excludes later insertions, not later edits/deletions, which remain a stated
mutable-source limitation. Every requested category is registry-validated and
unselected sources do not run. Failed sources have no invented zero count.

The UI uses the shared native toolbar, an account-owned request lifecycle,
account-timezone dates, distinct no-match/unavailable states and a warning when
refresh fails while retaining rows. All six locales and the settings FAQ were
updated, with the architectural contract amended in ADR-234.

Fresh evidence in `output/implementation-20261109/`: `lot3-unit-final.txt` (53),
`lot3-backend-final.txt` (51 unit + 10 real PostgreSQL), `lot3-ui-final.txt` (19),
`lot3-browser-final.txt` (3 engines, narrow viewport and scoped axe), cold MyPy,
app and E2E tsc, strict scoped ESLint, backend CC, i18n and documentation preview
all pass. The complete scan measured 1,153 rows in 0.0325 seconds on disposable
PostgreSQL (`lot3-final.xml`), not a production load guarantee. An earlier XML
measurement used incompatible xunit2 properties; the final run uses legacy XML
and has no warning. Initial E2E failures were a test expecting a French 24-hour
clock on the English page; the correct English display is asserted explicitly.
No frozen baseline improved or increased; newly introduced hotspots were reduced
before qualification. Physical-device and production-load qualification are not
claimed. No Git operation was performed.


## Lot 4 cold review

The existing received/upcoming rubrics and independent proposals stay in place.
Display filters run before pagination and return exact counts; absent source
counts remain unknown on failure. Thin source projections preserve ownership,
peer-side privacy and hidden-message rules. Sorting ends on identity, missing
next-run dates stay last, and an upper instant travels with subsequent pages.
Mutable edits/deletions are not falsely described as a frozen database snapshot.

SMS display search is separate from the assistant's lexical search. Its versioned
HMAC index is only a candidate filter; decrypted literal verification is decisive.
Missing/incomplete indexes remain candidates, never false negatives. Name matching
has a separate bounded directory, and cursor identity includes the query, account,
revision and contact-name fingerprint. Exactness beyond the verification budget is
refused with a period-restriction path. The additive migration and dual-index byte
accounting are exercised on real PostgreSQL, including rollback and erasure races.
Generation is offloaded from the async loop; cancellation rolls back without a
cleanup query replacing the original exception. No model or provider write is added.

Client review exercised account/filter A-B-A changes, cancelled and late responses,
page failures, query changes, stale cursors, invalid periods, literal markup and
Auckland date conversion. The API URL builder had appended a second question mark
to already-paged relative URLs: browser evidence reproduced it, then a central fix
and URL contract tests closed it. The bounded name prefix now uses a max-heap,
avoiding repeated insertion shifts. Attention queries join the existing Workboard
summary module instead of increasing the repository's size cap. No baseline rose.

Fresh evidence in `output/implementation-20261109/`:

- `lot4-back-unit-final.txt`: 2,058 passed. Old direct-route tests now supply the
  actual dependency and assert the new typed repository contract, including scope.
- `lot4-sql-final.txt`: 37 PostgreSQL cases passed; `lot4-load-final.txt`: 9 passed,
  including independent-actor races, actual cancellation and the archive ceiling.
- `lot4-extraction-final.txt`: 503 Workboard/alert unit and PostgreSQL cases plus
  size guards passed. A pre-existing integration import referred to a moved
  briefing helper; it now names its actual owner without changing its assertions.
- `lot4-front-final.txt`: 69 passed; `lot4-client-url-green.txt`: 37 client/query
  cases passed; `lot4-hub-flow.txt`: 2 real-hook hub flows passed.
- `lot4-browser-final.txt`: 9 passed. `lot4-notifications-recovery.txt`: all 30
  existing presentation journeys passed across Chromium/Firefox/WebKit, including
  320px reflow, light/dark/absolute black, keyboard, focus and axe. The reopen test
  now waits for the body to unmount: native toggle events coalesce same-task toggles.
- Scoped ESLint/Ruff, cold app/E2E TypeScript, MyPy, i18n, documentation preview,
  backend complexity and three coupling/cycle guards pass. The other 75 transverse
  guards passed before the size extraction, whose final guard is green above.

The local ceiling corpus contains 10,963 messages using 1,073,705,257 logical bytes
of the configured 1 GiB allowance. Name-first page: 0.1954 seconds; Python allocated
peak: 1,490,675 bytes. Physical projection size differs from logical quota. These
are one measured synthetic corpus, not production latency, ingestion throughput or
process RSS guarantees; details are in `docs/technical/SMS_QUALIFICATION.md`.

Chromium's native Autofill network lookup was refused by the strict network guard.
The test launcher disables `AutofillServerCommunication` (the Chromium feature),
without permitting that host through the guard. No real account or paid model was
used. Physical mobile and assistive-technology qualification remains unclaimed.

The shared development web container stopped externally. It was not restarted.
Owned isolated web container `lia-adjustments-20261109-web` serves port 3218 from
read-only sources and dependencies; only its separate Next cache is writable.
Clean up that container, `lia_adjustments_20261109_next_fresh` and the earlier owned
`lia_adjustments_20261109_next` volumes at final qualification, together with the
previously recorded Redis container and relay. No Git mutation was performed.


## Lot 5 cold review

Direct is a declared native mutation policy with execution identity and a durable
claim. It neither invents approval nor weakens MCP/other confirmations. Ambiguous
names still ask. The shared admission command fences membership and quota in the
same transaction. Legacy reviewed peer drafts use this command after their own
strict claim; new sends return an honest pending receipt, not a delivered card.

Delivery uses renewable token/generation claims, an encrypted paid-rendition
checkpoint, and atomic archive plus conditional settlement. No SQL transaction
survives a model wait (observed on PostgreSQL). A lost lease stops the model, stale
owners cannot settle, and a paid unknown outcome is terminal. Delivery retries
reuse the rendition, never purchase it twice. Optional transport and sender notices
are best effort after commit; their loss never replays a durable message. Sender
quota admission remains the existing cancellation contract. Retention runs even
when peers are disabled. Deployment must drain old delivery workers before the
claim migration: mixed old/new workers are unsupported.

The separate adversarial pass found and closed two additional defects with failing
counter-examples: generic account export leaked the internal encrypted checkpoint
and claim fields, and repeated cancellation could abandon renewal cleanup. Both
are now refused/awaited. Final capability revocation, duplicate generation start,
checkpoint overwrite, side-scoped history, rollback, crash, timeout, concurrent
quota, two-worker takeover and migration round-trip have behavioral evidence.

Evidence in `output/implementation-20261109/`: `lot5-unit-final.txt` (2,098 passed,
1 skipped; this is not full-suite qualification), `lot5-pg-final.txt` (66 passed),
`lot5-close-green.txt` (17 passed, including final export and double cancellation),
`lot5-mypy-final.txt` (23 source files; only existing unused override notes),
`lot5-docs.txt`, `lot5-i18n.txt`, scoped Black/Ruff and `task lint:cc` pass. Size
ratchet measurement found no eligible reduction; no threshold or cap was raised.
The old mocked delivery state-machine tests were replaced by real PostgreSQL
worker/atomicity tests; prompt/accounting and metadata tests remain unit tests.
No production provider, real recipient or application database was used.


## Lot 6 cold review

Cross-app text assistance is independent of Workbench. Source reads still require
both switches; task/event destinations are rechecked against current capability and
connection metadata. A selection carries no server identity and runs no tool. The
new typed request rejects incompatible actions/questions and preserves whitespace.
All source words are external content. Memory suggestions require exact evidence,
retain translated quotation attribution and cannot auto-pin a procedural mandate.
No memory embedding or provider write occurs until the native form is saved.

The full prompt, schema and resolved output allowance are budgeted before a paid
client is constructed. Provider usage remains the billing authority. Review found
silent clipping in existing task/event projections: the model schema now publishes
those bounds and rejects overlong output instead of losing the end. The shared
manual/application embedding preparation asks both ceilings before each vector,
restores its owner context on failure/cancellation, revalidates authority before
write and preserves the no-transaction-across-network rule. A concurrent changed
memory is refused rather than written from stale inputs.

The original fixed client timeout cannot bound an administrator's longer slot.
The selection transport therefore emits SSE waiting comments and one terminal
result/refusal. Code inspection confirmed the existing security middleware's
no-transform handling is SSE-specific, so the initially considered NDJSON transport
was replaced before qualification. Model timeouts and retry policy stay at their
owner. Counter-examples exposed repeated cancellation interrupting cleanup: the
common cancel-and-join utility now awaits it, and peer lease closure reuses it.

Fresh evidence: `lot6-cold-green.txt` (757 passed, including PostgreSQL and registry,
prompt, language, spend, streaming-session, size and cycle guards), `lot6-final.txt`
(282 passed after final SSE/boot changes), `lot6-memory-green.txt` (16 PostgreSQL
cases), `lot6-mypy-final.txt`, `lot6-final-types.txt`, `lot6-cc.txt`, `lot6-docs.txt`.
Black and Ruff pass on owned files. Ratchet measurement found no lower eligible
frozen cap; no threshold was relaxed. Earlier command mistakes naming a nonexistent
test file and a MyPy run outside the backend config are not counted as evidence.
No paid provider or application database was contacted. Browser/menu/form wiring
and its browser evidence belong to lots 7–8; aggregate gates remain in lot 9.


## Lot 7 cold review

The shared account-owned selection engine distinguishes native editable fields, rich
editing and read-only DOM ranges. It keeps exact selected text, rejects secrets and
cross-surface ranges, and mounts one lazy interaction inside its modal owner. The
native insertText command preserves React input events and browser undo; an altered
or detached target is never overwritten. Results remain copyable when stale. The
shared call hook fences account/scope generations, including A-B-A and old retries.
There is no paid call or microphone capture merely from selecting text.

The separate adversarial pass reproduced and fixed late microphone grants after
unmount/timeout, capture ownership across two composers, resource leaks on terminal
voice errors, a stream-cleanup exception masking a valid answer, and reading a DOM
selection while a native input retains its caret. Losing microphone ownership ends
dictation permanently for that act; releasing the other owner never re-arms it.
A new call consumes the server-published slot timeout and SSE refusal contract.

Evidence: lot7-final-unit.txt (265 passed), lot7-focused-field-green.txt (11 passed),
lot7-microphone-owner-green.txt (1 passed), lot7-sms-regression.txt (18 passed);
lot7-browser-recheck.txt (12 passed: Chromium/Firefox/WebKit, English/French keyboard
access, 320/1280 px native field/rich editing, undo, focus and axe). ESLint including
the strict touched-function complexity limit, non-incremental TypeScript, and six
locale parity pass. The measured frontend complexity ratchet fell from 35 to 34
hotspots; the former voice-input hotspot was removed, with no raised cap. Browser
proof is desktop engine simulation, not physical phone or assistive-technology
certification. Creation destinations and old-menu retirement are lot 8.

## Lot 8 cold review and qualification

The existing handoff now has one observable, account-owned payload, an explicit expiry
and atomic consumption. Re-entering the same route receives it; busy forms retain their
fields and present the waiting proposal only after closing. Task lists and writable
calendars gate consumption. Account changes clear both pending proposals and native
editors. No content enters the URL, localStorage or sessionStorage. All three destinations
remain ordinary forms; no mutation happens before Save. Memory proposals cost no
embedding until that save, whose result must explicitly confirm a created memory.

Cold review reproduced a same-frame task double-submit and added a synchronous claim.
Memory tests exercise refusal, duplicate clicks and a response after an account switch.
Event proposals with missing dates identify the form defaults rather than pretending
the source specified them. A mail test previously retained a navigation mock between
cases; it now resets that implementation instead of weakening the assertion.

The first full browser matrix passed 82 cases and exposed five failures. Firefox's
question composition cleared the selection because the global IME listener also watched
its own bubble: the observer now excludes that surface, verified by a failing-then-passing
unit test and the replayed Firefox journeys. WebKit's displayed Selection string includes
a trailing line break absent from Range.toString under the chat's actual CSS; the captured
range now has its own comparison text, preserving the user's selected words unchanged.
The source DOM in the trace was unchanged. Focus is checked after layout and the next
owned animation frame, covering removal of a question field; valid focus inside the
bubble is never stolen. The frame is cancelled on teardown.

WebKit can focus the dialog container itself after removing the question input;
the browser attachment proves that state. The focus repair recognises that container
and selects the close control, while preserving focus on any actual control. A field
covering the viewport previously hid every action; a bounded, scrollable overlay now
keeps the actions reachable. Both defects have failing-then-passing unit evidence.
The final 90 browser journeys pass on all three engines, including the oversized
textarea, undo, keyboard focus, responsive reflow and all three native destinations.
Evidence: `output/implementation-20261109/lot8-browser-qualified.txt` (exit 0, 9.1 min).
No provider write occurs before the native form's explicit save.

### Surface coverage

| Surface | Integration and proof |
|---|---|
| Native Input/Textarea and controlled fields | Shared observer; native replacement and undo, three-engine editor journey. Readonly uses reading actions. |
| RichBody/contenteditable | Same DOM range adapter, native insertText and undo, three engines. |
| Chat messages, settings, lists and World DOM overlays | Locale-root provider; one message boundary per chat message. Chat keyboard/scroll/reflow journeys cover 320, 640 and 1280 px. Canvas remains excluded. |
| Mail text, document panels and enlarged modal readers | Old local selection menus removed. Document unit coverage and mail bubble browser journeys; common Dialog/AlertDialog hosts, plus maps/onboarding direct Radix hosts. |
| Task, calendar, contact and mail handoffs | Existing bridge uses the same owner store; native screen suites verify current routes and waiting data. |
| Memory settings | Lazily mounted native create form consumes the same store; editable proposal, failure and account transition tested. |
| Secrets and opaque content | Password/OTP/autocomplete rules plus explicit exclusions on revealed keys, ingestion tokens and recovery codes; iframe/canvas excluded. HTML mail retains its visible text-view action. |

Physical touch, operating-system IME and native WebView permissions remain device
qualification limits; desktop engine simulations do not claim those measurements.

## Lot 9 integrated cold review

The aggregate gates exposed defects the targeted suites had not found. Each was
reproduced before its correction:

- The spaces settings fixture lacked authentication. Restoring that boundary also
  revealed duplicate creation controls in the empty state. The existing native
  EmptyState contract is preserved, with one creation action on both surfaces
  (13 focused cases).
- Broadcast-history tests now exercise the real account-owned paging hooks through
  the API-client boundary. Refresh keeps the mounted list, retry and offset paging
  remain asserted (17 cases together with the spaces reader).
- The memory prompt was missing from the cache-layout completeness guard. It is
  now registered, and its configurable content bound follows the dynamic marker.
  Notification test doubles were aligned with the current conversation-id argument;
  three overrides were checked, without changing notification business code.
  The combined prompt/assistance/notification repair suite passes 361 cases.
- A global resource-refresh error referenced a settings-only translation subtree.
  Its generic wording now lives in the common catalogue in all six languages,
  without loading the complete settings catalogue on public routes (108 cases).
- SelectionLayer now mounts Radix Content directly, reducing ref forwarding and
  declaring keyboard semantics at the component that owns them. The dictation
  interruption latch updates under a render guard, while its effect only notifies
  the owner; microphone availability never automatically re-arms capture.
- Query failures previously logged search parameters and provider error words.
  Their log now contains only the component, status and parameter count; the
  caller still receives the original typed error (31 hook cases, including RED/GREEN
  privacy evidence).
- The from-scratch migration replay caught two model/column-comment mismatches.
  The migrations now carry their exact comments. The complete replay, parent cycle,
  structural equivalence and Alembic check pass on dedicated disposable containers.

The second full fast backend gate reports **53,534 passed, 30 skipped and one
failure**: the index-based documentation-link guard cannot see newly created files.
`task lint:docs:preview` passes on the working tree. No index mutation or guard
exception was used to manufacture a green result. The complete cross-cutting static
task sequence also passes (documentation preview, i18n, MyPy debt, observability,
cycles, complexity, hygiene, lockfiles, CI parity and dependency/wake scripts).

The subsequent full coverage, database integration and production-browser results
are recorded in the final qualification table below. Earlier attempts remain here
as evidence of the defects found, not as substitutes for those final results.

The frozen production artifact compiles and serves independently on the owned
qualification container. Its Firefox/WebKit matrix passes **70 journeys** across
selection, native destinations, existing mail assists, automatic appearance,
knowledge spaces, alert sections and activity filters (`final-browser-matrix.txt`).
The E2E transport harness passes **18 cases**, and its separate TypeScript project
passes. The complete backend static task passes; the frontend's cold TypeScript
check subsequently exposed stale generated route declarations (see below). The double-assertion
baseline shrinks to **113 across 72 files**; no ceiling was raised.

The first complete frontend unit task passed **20,430 tests in 1,488 files**
(`final-frontend-verified.txt`, exit 0). No unhandled error or resource warning
follows its summary.

The full Chromium run exposed two existing interactive-page test assumptions.
The retained trace shows Chromium reporting an image request rejected by CSP
(`failureText: csp`, no send/wait/receive timings). The security assertion now
checks the refusal and the independent transport proxy, including HTTPS CONNECT,
instead of mistaking a request event for network transmission. The keyboard
journey now waits for the opaque document's load before sending Tab: the parent
iframe receives focus earlier. No application change was needed. All 39 page
journeys pass across Chromium, Firefox and WebKit (`final-page-app-qualified.txt`);
a repeated keyboard run checks the readiness correction under concurrent load.

### User-observed selection regressions and second cold review

The reported development window (09:10–09:20 Paris) was inspected in both Docker
logs. The web log contains calls from the removed chat `SelectionActions` module
into the new hook signatures (`anchorOf`, `setHandoffOwner`), plus a stale lazy
module export. The deleted component is absent both on disk and in the running
container's bind mount. There is one locale-root provider and no legacy-menu import.
This supports a mixed Fast Refresh client graph, not a second current menu. A fresh
production artifact shows one toolbar on all three engines. The user confirmed that
Ctrl+F5 restored a single menu on the affected open page. No shared container or
cache was restarted/erased.
No further matching error appears in the inspected web log after 09:20.

Two independent defects were reproduced and corrected:

- The positioning hook overwrote authored `max-width`, making both the toolbar and
  answer span 1,264 px in a 1,280 px viewport. Rendered-box tests fail on that build
  and pass with the compact toolbar and the original mail bubble's 24rem bound.
  Editable controls, readonly text and modal hosts share the same fix; screenshots
  are stored beside the browser evidence.
- A debounce alone opened the menu while a pointer or Shift selection remained held.
  The shared observer now waits for release, handles pointer cancellation and window
  blur, and clears every listener/timer on teardown. Cold review found and corrected
  a further blur regression: an established selection/answer survives switching
  windows, while an unfinished gesture is abandoned. Each change has RED/GREEN proof.

The compact menu fits the old short-screen fixture without scrolling. The scrolling
oracle was retained and the fixture shortened to a genuinely constrained viewport;
no assertion was weakened. `user-selection-qualified.txt` records **108 passed**
across Chromium, Firefox and WebKit, including native drag pauses, dimensions,
keyboard, reflow, modal editing/undo, the three creation forms and the other lots.
`user-selection-final-unit.txt` records **41 passed** for the final observer and
selection transport/secret boundaries. The last blur correction was included in
the final production build and complete Chromium run. The final Firefox/WebKit replay passes all
62 selection, modal, handoff and existing mail-assist journeys.

The authority review also exercises the actual destination guard under each
capability/connection combination and after a capability is withdrawn. The memory
prompt is checked in all six languages with its attribution allowance and external
quotation. Three new negative probes exposed blank evidence being accepted as a
literal substring; admission now refuses it and the schema states this requirement.
No embedding or provider write is added. Coverage for this module was cleared before
the fresh family run, so the previous implementation cannot inflate its measure.

### Recovery and backend qualification

The user-confirmed Docker restart at 09:08 interrupted owned integration/browser
processes and one PostgreSQL fixture teardown. Only the owned qualification
resources were restarted. The complete integration selection was replayed as three
disjoint file partitions on independent PostgreSQL/Redis instances: exactly 5,737
collected, 7 deselected and 5,730 executed, matching the original collection.
The co-located integration selection adds four passing cases and two explicit
POSIX-only skips. Ten initial failures were investigated, not discarded:

- Four direct interest-history calls needed the new typed display criteria.
- Four activity cases had a collection-time clock and real-time claims, so a long
  suite aged the actions outside the fixture's one-minute upper bound. All fixture
  instants are now explicit; the same account, period, totals and authorship oracles
  remain unchanged.
- The SMS migration round-trip omitted the new additive display projection. Its
  downgrade/upgrade now includes that revision and still compares every column,
  index, foreign key and check against the ORM.
- Cancellation during SQL-budget initialization could leave a transaction open.
  The protected lifetime now includes initialization, execution and restoration.
  Three deterministic phase probes first failed, then passed; arbitrary body errors
  retain their identity and restore the previous setting. PostgreSQL verifies the
  cancellation/timeout behavior. The repair run passes all 15 affected integration
  cases; the SMS/guard suite passes 78 cases.

The independent agents gate passes **1,113 cases**, 36 explicitly deselected.
The sequential coverage run's stale prompt/notification fixtures and interrupted
PostgreSQL teardown were replayed in a **938-case** passing repair, including real
database creation and disposal. The Git-index documentation failure remains distinct
from runtime/test failures: the working-tree preview passes and no Git mutation was
used to hide unstaged files.

Combined backend coverage finally measures **89.25%**, and the full working-tree diff
**97.29%** (5,055 of 5,196 executable changed lines). The backend floor rises to 87,
with more than two points of margin; its source, Taskfile and living documentation
are synchronized. Frontend global floors rise to 86/81/84/88 and a selection-boundary
scope is added from its measured coverage. The final complete frontend coverage
run passes those floors and all existing scoped thresholds.

The cold host TypeScript gate found two generated route universes: old `.next/types`
and a retired `.next-e2e` proof tree. The obsolete proof-tree includes are removed;
canonical route types are refreshed from the owned production build, with no host
development/build process and no generated business-code exclusion.

### Final qualification record

Evidence files below live under `output/implementation-20261109/`. Tests never
sent mail, created provider records or called a paid model. Browser journeys use
the real production UI with controlled API/SSE/media traffic; persistence and
concurrency checks use disposable PostgreSQL and Redis.

| Command / boundary | Final result | Evidence |
|---|---|---|
| `task test:frontend:coverage` | 20,447 passed in 1,488 files; statements 88.82%, branches 83.48%, functions 86.76%, lines 90.28%; all thresholds pass | `final-frontend-ratchets-qualified.txt` |
| `task test:backend:unit:fast` | Task exit 201: 53,561 passed, 30 explicit skips, one index-only documentation failure | `final-backend-fast-sealed.txt` |
| Sequential unit coverage and PostgreSQL integration | Complete selections measured; interrupted/failed cases repaired and replayed as described above, not represented as one uninterrupted green invocation | `final-backend-unit-coverage.txt`, `final-unit-coverage-repair.txt`, integration partition logs, `final-integration-repair.txt` |
| Final assistance family and accounting integration | 284 unit cases and three real PostgreSQL cases pass after the nonblank-evidence correction; earlier module coverage was purged first | `final-selection-authority-qualified.txt`, `final-selection-integration-sealed.txt` |
| `task test:backend:coverage` and `task test:backend:diff-coverage` | Floor 87 passes; 89.25% combined, 97.29% changed lines across 293 files | `final-backend-coverage-sealed.txt`; precise `coverage report --data-file=.coverage-combined --format=total --precision=2 --fail-under=87` also exits 0 |
| `task test:backend:agents` | 1,113 passed, 36 deselected; exit 0 | `final-backend-agents-recovered.txt` |
| `pnpm exec playwright test --project=chromium --workers=4 --reporter=list` from `apps/web/e2e` | 1,166 passed, one explicit skip, one readiness failure subsequently repaired and replayed; original command remains a failed run | `final-browser-current.txt` |
| Corrected presentation readiness, eight repeated journeys | Eight passed; exit 0 | `final-presentation-readiness.txt` |
| Final selection/native-form/mail-assist Firefox and WebKit replay | 62 passed; exit 0, on the final production artifact | `final-selection-current.txt` |
| `task lint:backend`, `task lint:frontend`, cold E2E TypeScript | Pass: backend 4,014 source modules plus 71 strict test fixtures; frontend shrink-only ratchets and non-incremental types; five additional changed Python fixtures also pass strict typing | `final-backend-static-sealed.txt`, `final-frontend-static-qualified.txt`, `final-e2e-types-sealed.txt` |
| Isolated migration replay and read-only development revision check | Complete replay, parent cycle and model equivalence pass; development already reports `d94b62a10e73 (head)` | `final-migration-replay.txt`, `dev-current-migration.txt` |

The one final Chromium failure clicked the presentation control before React
hydrated it. The existing `waitForHydration` helper now gates that click. The test
still verifies unavailable media, explicit retry, actual video, Escape and restored
opener focus; no business code or success oracle changed. Its eight repetitions
pass under load. The complete Chromium suite was not rerun after this test-only fix.

The final production build compiled, type-checked and generated its pages in an
owned Docker container (`user-selection-final-build.txt`). All 366 frozen code,
configuration and test inputs matched their recorded hashes at final review; the
later landing readiness test was reviewed separately. No shared development server,
database data, unrelated working-tree change or Git index was modified by this
qualification. Development's migration revision was read, not changed.

### Final adversarial assessment and limits

The final review followed ownership from the selected DOM range through cancellation,
account changes, quota admission, model accounting, decision/consultation registers
and the native creation handoff. It rechecked secret-field exclusions, untrusted
selected content, stale targets, stale network answers, keyboard focus, undo and
bounded responsive placement. The pointer lifetime and SQL-budget cancellation
defects, and the blank memory evidence, were reproduced before correction. No
remaining implementation blocker was found in the exercised scope.

This is a qualified delivery, not a claim of infallibility or a completely green CI
invocation. The index-based documentation guard still cannot see new, unstaged
documents; the working-tree preview passes. The user retains Git operations.
Physical touch devices, operating-system IMEs, native WebView permissions and
assistive technologies were not measured. Live paid-provider behavior was simulated
at controlled boundaries, not exercised against a real person's accounts.
Explicit platform-dependent skips remain visible in their logs.

No commit, push or deployment was performed. The peer-delivery deployment must
still drain old workers before migrating; mixed old/new delivery workers are not
supported. The three-engine desktop browser evidence does not remove those stated
operational and device limits.

After the final suites exited, cleanup verified each temporary container's name
and recorded id before stopping/removing it: nine owned containers, six owned
Next.js build volumes and the owned migration network were removed. Shared
development containers and volumes were excluded; test evidence remains in the
workspace (`final-owned-cleanup.txt`). The final documentation preview exits 0
with no living broken link, stale code path, orphan or quoted-fact drift
(`final-docs-preview-sealed.txt`).

## Selection-menu follow-up — 2026-11-09

The follow-up restores an explicit target-language choice in both selection modes,
with localized suggestions and a freely named language. A translation without that
choice is rejected before model spend. Editing also offers formatting, which keeps
the meaning and presents readable plain-text paragraphs/lists. Reading uses shorter
Question, Task and Event labels and offers Internet research. Summarize (reading)
and Expand (editing) remain suggestions, not additional implemented actions.

Dictation admits a caret, including an empty input, textarea or rich editor. It
starts only on an explicit click, proposes words locally and inserts them only on
confirmation, retaining native undo. An editing target is retired immediately when
focus leaves its field and its own assistance controls, or the window loses focus.
Closing for that reason does not restore focus to the old editor. An eligible new
field owns its own caret menu. Explicit dismissal suppresses delayed selection
events, while a different native selection remains usable without a pointer event.

Internet research prepares one bounded query from the complete selected passage,
then consults one available native provider: Brave, Perplexity or Wikipedia, in that
order. Provider failures do not become empty results and do not silently trigger a
second provider. The response names the actual service and query, preserves citation
order and renders source text without active markup. Credentials and unsupported URL
schemes are refused in source links. No result page is fetched by this feature.

The existing assistance door owns quota admission, model accounting, cancellation
and the consultation register. Search credentials are detached before network work;
the capability is checked again after query preparation. The model slot owns its
deadline, with a separately bounded search phase. No new database schema, persistence
of selected text, external write or model dependency is introduced. Translation and
formatting remain proposals; creation actions retain their native form handoffs.

### Adversarial verification

Tests first reproduced missing language admission, unsupported empty-field dictation,
new action contracts and dismissal/reselection behavior. Review then exercised unsafe
URLs, absent credentials, capability withdrawal during the model call, malformed
provider replies, successful empty searches, citation order, cancellation and real
PostgreSQL consultation/accounting transitions. The whole backend fast suite passes
with 53,617 tests and 30 explicit platform/configuration skips. Six PostgreSQL
integration tests pass. The targeted research module measures 98% statement coverage;
this is not a claim about aggregate backend coverage.

`task lint` passes, including cold frontend typing and the shrink-only ratchets.
The intermediate full frontend coverage run passes 20,470 tests in 1,488 files and
all configured thresholds. Its evidence is `menu-frontend-coverage-final.txt`; an
additional run after the final source freeze is recorded separately below.

The initial browser replay exposed a stale development bundle: the compiled layout
still contained `dismissedElement` and lacked `shouldRestoreFocus`, although the
mounted source contained the fix. Those results are not evidence for the final code.
Qualification consequently uses an isolated production build from a clean copied
source tree, with no inherited image source files or environment files. Shared
development services and volumes are not modified. Source parity is checked against
the workspace before browser qualification.

### Owner's final menu revision

The later explicit order supersedes the initial follow-up above. Reading now offers
Read, Question, Explain, Summarize, Simplify, Translate, Internet, Task, Event,
Reminder, Ticket, Remember and LIA. Editing offers Translate, Correct, Format,
Shorten, More formal and Warmer. Dictate was removed from the generic selection menu;
the later caret clarification is recorded below. Dedicated dictation controls
remain separate. The Tools' shared Cancel control and confirmations use the neutral
outlined variant.

Read reuses the existing TTS and cost/ceiling paths. Summary uses the existing passage
slot. Reminder and ticket actions prepare native form values only. The reminder's
schedule uses the real recurrence engine and consumer bounds in the account's zone;
an incomplete schedule opens without an invented hour. The ticket keeps stated
constraints in its description and defaults to the person's own holder. LIA reuses
the existing unsent chat draft handoff. Its explicit draft persistence is distinct
from the ephemeral record proposals.

The cold review reproduced same-frame duplicate requests, stale account feedback,
audio release during loading and Strict Mode resource replay. Corrections preserve
the single-call guard, account lifetime and native form ownership. Tests also
exercise an already open form, which must retain its draft until it closes before
receiving a waiting proposal.

The owner's screenshot also exposed an unstyled waiting paragraph. The shared
waiting view now has compact spacing, the shared animated spinner and a translated
label distinguishing audio preparation, an answer and a record proposal. Reduced
motion disables its animation; one live status announces the wait. Browser evidence
covers a narrow viewport, accessibility and the transition to the actual answer.

The full translation-scope guard exposed a global dependency introduced by the LIA
action: its URL builder lived alongside dashboard-only translation readers. The
existing chat URL builders now live together in `lib/chat-href.ts`, with their
consumers and existing tests moved to that single owner. URL encoding, unsent
drafts and one-shot intent identities are unchanged; public routes no longer pull
the dashboard utility module into their global selection host.

The Windows WebKit runner rejected the MP3 even in an isolated HTML audio element.
The same native-decoding assertion passes in the repository's official Linux
runner, using its virtual display and native audio sink. WebKitGTK's test embedder
does not bind Ctrl+Z, also reproduced in a bare input: its tests invoke the actual
native undo command and verify the restored controlled value. The other engines
and Windows WebKit retain the keyboard gesture. No production fallback, mocked
media element, direct value assignment or removed assertion hides these limits.

### Final verification of the menu revision

Evidence lives in the workspace's `output/implementation-20261109/` folder.

| Check | Result and evidence |
| --- | --- |
| Backend fast unit gate | `task test:backend:unit:fast`: exit 0, 53,640 passed and 30 explicit platform/configuration skips (`menu-final-backend-fast.txt`). The earlier Windows socket exhaustion and its incomplete-event-loop cleanup error did not recur. |
| Real PostgreSQL integration | Eight assist accounting, consultation and proposal-only persistence scenarios pass (`menu-latest-integration.txt`), using disposable PostgreSQL and the owned test Redis. |
| Static gates | `task --concurrency 1 lint`: exit 0, including strict backend typing, non-incremental frontend typing, translation parity, documentation and the shrink-only ratchets (`menu-final-static.txt`). |
| Complete frontend coverage gate | `task test:frontend:coverage`: exit 0, 20,511 tests in 1,490 files, 878.09 seconds; every global and scoped threshold passes (`menu-complete-frontend-coverage.txt` and its `.exit.txt` companion). Aggregate statements 88.87%, branches 83.54%, functions 86.82%, lines 90.34%. No warning, unhandled rejection or post-summary resource error is reported. |
| Final TypeScript checks | `pnpm type-check` runs `tsc --noEmit --incremental false` and exits 0 after the final test changes (`menu-complete-cold-tsc.txt`, recorded exit in `menu-complete-cold-tsc.exit.txt`); the separate E2E TypeScript check also exits 0 (`menu-complete-e2e-typecheck.txt`). |
| Scope and URL regression | 163 tests pass after separating the chat URL builders, with the existing URL-encoding and one-shot-id assertions retained (`menu-route-boundary-green.txt`). |
| Selection boundary coverage | 105 tests pass; statements 91.62%, branches 87.35%, functions 100%, lines 94.44% (`menu-boundary-sealed-coverage.txt`). The scoped floors rise to 89/85/98/92, keeping at least two points of measured margin. This measurement is scoped, not aggregate frontend coverage. |
| Production source parity | All 2,188 frontend application/locale files match the isolated build; tests are excluded explicitly (`menu-sealed-runtime-parity.json`). |
| Chromium and Firefox | 80 hermetic production-bundle journeys pass, exit 0 (`menu-sealed-chromium-firefox.txt`). |
| WebKit | The same 40 journeys pass in the native-media Linux runner, exit 0 (`menu-sealed-webkit-linux.txt`). Four additional Windows WebKit journeys confirm keyboard undo on the final bundle (`menu-sealed-webkit-windows-undo.txt`); Chromium/Firefox's eight keyboard-undo journeys are included in their matrix above. |

The browser journeys cover the exact action order, compact menus and answers,
selection completion, editor focus changes, native undo, explicit target-language
choice, Internet attribution, audio loading/release, an unsent LIA draft, the five
native creation forms, keyboard access, accessibility scans and narrow reflow.
The waiting state is inspected in French and tested with reduced motion. Provider
responses are controlled: no paid provider is called, and no real record is created.
These desktop engine runs do not claim physical iOS/Android or assistive-technology
qualification, nor a new live-provider voice quality assessment.

The aggregate frontend run exposed a pre-existing race in the activity-feed test:
it treated the clearing of an error at request start as proof that replacement data
had arrived. A deferred response reproduces the exact wrong assertion, then the
corrected test waits for the received fields and also verifies the pending state
and retained rows (`menu-activity-timeline-race-red.txt` and `-green.txt`). The
production query lifecycle is unchanged. All five activity-feed tests pass with
the deterministic schedule.

After browser and backend qualification, cleanup checked each temporary container's
exact id and task label, and every volume's exclusive consumer. It removed the
three owned containers and four exclusive volumes, including Redis's anonymous
volume. The shared development web service remained running; shared volumes and
images were retained (`menu-complete-owned-cleanup.txt`, exit 0). Docker reported
only the deprecation of its stop command's `--time` spelling.

The complete frontend run includes the deterministic activity-refresh test and
the strengthened recurrence-selector boundary cases. The full-scope coverage gain
does not justify lifting the global floors while retaining their required margin;
the selection boundary's improved floors are enforced by the same successful run.

The final inline adversarial review found no unresolved defect in the exercised
scope. The stated provider and physical-device limits remain: mocked service
answers prove client behavior and persistence boundaries, not every live provider
or device. No commit, push or deployment was performed.

### Caret dictation and iOS selection follow-up

The owner clarified that Dictate must remain available on a focused field, independently
of the selected-text editing menu, and reported the latter missing in the chat composer
on Chrome for iOS 27.2. Work remained inline, with no repository operations.

The former removal had deleted the caret entry point along with the editing action.
`FieldDictation` restores a distinct compact control for an eligible native or rich caret,
including an empty field. The existing STT capability and browser microphone support gate
it independently of text-assist metadata. The existing recorder mounts only on the click;
the native editor remains the owner of insertion and undo. Failed insertion keeps the
words copyable. No new backend, model call, persistence or accounting route is introduced.

The observer's pointer-only gesture lifetime could remain held indefinitely when native
selection consumed its terminal event. The related iOS 27 behavior is documented in the
[upstream Flutter fix](https://github.com/flutter/flutter/pull/189608). This is corroborating
evidence, not a measurement of the owner's phone. Native touch count now independently
holds selection until the final release, then clears touch pointers alone; mouse and pen
holds remain intact. Field selection changes are observed in capture phase. No user-agent
test or timeout guesses that a finger has lifted.

Adversarial tests first reproduced the missing caret entry, the lost pointer release,
premature opening after pointer cancellation, a touch-only gesture after dismissal,
discarded uninsertable words, an idle control disappearing after typing, and metadata
arriving after focus. A final account-switch simulation also delivered an old transcription
from the new account's layout effect, before passive cleanup. It reproduced an attempted
insertion; synchronous commit cleanup now revokes both the field callback and the recorder's
words, cost and error feedback. The corrections preserve the recorder's existing resource cleanup
and reject late results after focus, route, account or field-revision changes. English
and French accessible names, keyboard dismissal, secret fields, multi-touch and a held
mouse are exercised. Shared target invalidation and caret admission rules have one owner.

Evidence is recorded under `output/implementation-20261109/dictation-ios-*`. The initial
Docker build was interrupted when the daemon stopped; its empty output is not evidence.
Docker Desktop was started again, restoring its existing services, and a clean owned build
completed. No targeted restart or cache purge of the shared web service was performed.
All 2,190 runtime source/locale files match the final qualified snapshot
(`dictation-ios-sealed-source-parity.json`). Black stalled inside the Windows sandbox,
including with one worker; those attempts were interrupted, and the unchanged static task
was rerun on the host. The first browser invocation refused worker-level launch settings
inside a describe block; the actual-recorder journey now lives in its own spec, with the
same Chromium-only microphone flags used elsewhere in the suite.

Unit and integration boundaries pass 285 tests in ten files
(`dictation-ios-commit-lifetime-green.txt`, exit 0). The browser matrix exercises
real controlled inputs, rich text, nested dialogs, the chat composer, native replacement
and undo. Its tactile event replay controls DOM events, not the native iOS selection UI.
The actual browser recorder is tested with Chromium's fake microphone and a controlled STT
WebSocket; Firefox/WebKit do not claim microphone capture coverage through Chromium flags.
No production API, provider or user's microphone participates in these journeys.

The final browser replay exposed an incorrect test assumption: an immediate recording
may overtake the existing idle prewarm and open its own connection. The original test
expected exactly two close events across two recordings, whereas all four connections
could legitimately close. The revised test deliberately holds the first ticket until
recording asks for another, assigns every ticket a distinct identity, waits for actual
audio chunks and requires every issued connection to close with no ticket pending.
It retains insertion, undo and focus assertions and also proves zero ticket requests
before the click. Five consecutive repetitions pass (`dictation-ios-recorder-race.txt`);
the recorder implementation is unchanged by this test correction. The cold E2E type
check passes (`dictation-ios-e2e-types-sealed.txt`, exit 0).

The final three-engine production-bundle matrix passes 94 journeys with two explicit
fake-microphone exclusions on Firefox/WebKit (`dictation-ios-browser-final.txt`, exit 0).
Its connection evidence contains four distinct tickets, four openings, four closures and
zero pending requests (`dictation-ios-recorder-connections.json`). The complete static gate
also exits 0 (`task --concurrency 1 lint`, `dictation-ios-static-sealed.txt`), including cold
frontend typing, strict backend typing, documentation and all shrink-only ratchets.

`task test:frontend:coverage` exits 0 on the final application/test sources: 20,544 tests
in 1,491 files, 1,368.33 seconds (`dictation-ios-frontend-coverage-sealed.txt`). Aggregate
statements/branches/functions/lines are 88.94/83.60/86.88/90.40%, with no warning, unhandled
error or post-summary resource failure. The earlier full run was interrupted to repair
the reproduced account-switch race and is not counted as a successful qualification.

The fresh whole-suite coverage map supports stronger selection floors. The native
boundary floor becomes 90/87/98/92; new observer and invalidation floors are 95/88/98/97,
and caret/recorder floors are 96/89/98/98. Each keeps at least two measured points of
margin. The global floors stay unchanged because their measured gain does not yet leave
that margin for another step. After tightening `vitest.config.mts`, a separate scoped
coverage run executes 180 tests in nine files against the real updated configuration,
passes every applicable floor and reproduces the whole-suite measurements for those
exact globs (`dictation-ios-scoped-ratchets.txt`, exit 0). Its report directory is separate;
it does not replace the complete frontend result.

Final cleanup verified the two proof containers' exact task label and recorded their
mounts before removing those containers alone. No volume was removed; the shared web
service remains running (`dictation-ios-sealed-cleanup.txt`, exit 0).

After a complete reload, the owner confirmed that selecting text in the chat composer
opens the editing menu on Chrome on a physical iPhone running iOS 27.2. This user-reported
device check complements the automated WebKit and tactile DOM-event replay evidence;
its scope is the chat selection menu, not physical-device microphone capture. No live
provider assessment, commit, push or deployment is claimed.

### iOS keyboard-open placement follow-up

The owner's first device check confirmed that the editing menu appears. A subsequent
report identified a separate placement defect on Chrome iOS 27.2: with the keyboard
open, both the editing menu and Dictate appeared far above a field near the page bottom.

The positioning hook treated native client rectangles as fixed CSS coordinates. WebKit's
keyboard pan can give those frames different origins; the maintained
[Floating UI coordinate conversion](https://github.com/floating-ui/floating-ui/blob/master/packages/dom/src/utils/getVisualOffsets.ts)
also accounts for this distinction. The reproduction uses the browser boundary rather
than a user-agent assumption: five visual-origin cases fail while their five layout-origin
counterparts pass, with a 180-pixel pan producing a 188-pixel gap instead of eight
(`ios-position-red.txt`).

The shared hook now measures the translation from the overlay's assigned fixed position
and its actual client rectangle, then converts the anchor before choosing free space.
It initializes the fixed origin once, not on every sample. Opening, panning and closing
the keyboard, horizontal pan, differing menu/answer sizes, offscreen anchors, internal
scroll preservation, absent surfaces and missing viewport/observer APIs are exercised.
No input value, native selection, focus policy, model or accounting path changes.

The scoped position measurement passes 16 tests with 100/94.87/100/100 percent coverage
for statements/branches/functions/lines. Its new shared floor is 98/92/98/98, retaining
the required margin (`ios-position-scoped-coverage.txt`). Browser journeys replay the
coordinate boundary in the real chat and mail forms and compare engine-painted quads;
this is not a claim to have operated the physical iPhone's software keyboard.

The final production-bundle browser matrix passes 106 journeys across Chromium,
Firefox and WebKit, with the two existing Chromium-only fake-microphone exclusions
(`ios-position-browser-final.txt`, exit 0). Its twelve new cases cover chat/mail,
caret/selection and all three engines; selection cases also check the answer bubble.
The first browser fixture incorrectly expected no voice-ticket request in the chat:
`ChatInput` already owns an idle prewarm. The corrected fixture waits for that existing
request before focus, then proves that opening and moving the overlays add none.
The application recorder is unchanged. The cold E2E type check exits 0
(`ios-position-e2e-types-final.txt`).

All 2,192 runtime source/locale files match the isolated production build
(`ios-position-source-parity.json`). The build exits 0; its output-file-tracing warnings
come from the proof's shared read-only dependency directory outside the snapshot root,
with the proof server resolving that directory explicitly. No production packaging or
dependency change is part of this fix. Cleanup verified each proof container's task
label and removed those two containers alone; all volumes were retained and the shared
web service remained running (`ios-position-cleanup.txt`, exit 0).

The complete static gate passes (`task --concurrency 1 lint`,
`ios-position-static-final.txt`, exit 0), including cold frontend typing, strict backend
typing, all shrink-only ratchets, lockfile/i18n parity and documentation checks.
The documentation audit reports zero stale living-code paths; its historical and
roadmap path inventories remain informational. Prettier also accepts the changed
hook, its unit test, the new browser spec and the coverage configuration.

The first complete frontend run exposed an unrelated stale navigation assertion:
`settings-sections.test.ts` still expected ten header destinations, although the
knowledge-spaces entry had already made eleven. An isolated replay reproduces that
single failure (`ios-position-settings-diagnostic.txt`). Its expected count and
explanatory comment now include knowledge spaces; the workboard exclusion and its
settings destination remain asserted, and no navigation implementation was changed.
The two navigation/settings test files then pass all 157 tests
(`ios-position-settings-green.txt`, exit 0).
The initial whole-suite process, started before that correction, finishes with
20,564 passes and this one failure across 1,492 files in 1,651.89 seconds; it is
not counted as a successful coverage gate (`ios-position-frontend-coverage.txt`,
Task exit 201, underlying Vitest exit 1).

Cold review followed the sole production caller, the body-portalled `SelectionLayer`,
through caret, editing, reading and response surfaces. It checked that the correction
is measured afresh rather than accumulated, that internal scrolling and focus ownership
remain intact, and that resize/scroll observers are detached on teardown. The positioning
path adds no provider request, event-content logging, persistent state or new dependency.
The owner then reloaded the physical iPhone and confirmed that both Dictate and the
editing menu are correctly placed near a bottom-of-page field with the keyboard open
on Chrome iOS 27.2. This device check specifically validates the placement defect,
beyond the earlier confirmation that the selection menu appears; it makes no new
claim about physical-device microphone capture or the answer bubble.

The final whole-frontend gate passes all 20,565 tests in 1,492 files in 1,458.51 seconds
(`task test:frontend:coverage`, `ios-position-frontend-coverage-final.txt`, exit 0).
Aggregate statements/branches/functions/lines are 88.95/83.64/86.91/90.42 percent;
all global and scoped floors pass, including the new positioning ratchet. The global
floors remain unchanged because their next integer step would not retain the required
two-point margin. No warning, unhandled error or post-summary resource failure is emitted.
The final report is checked with `task lint:docs:preview`; its evidence is recorded in
`ios-position-docs-sealed.txt`. No commit, push, deployment or shared-dev restart is
part of this placement correction.
