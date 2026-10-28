# World interactions and play: implementation qualification

Date: 2026-10-27. Status: implemented and qualified here, strictly inline;
physical-platform limits are explicitly recorded below.
Authority: [specification](../specs/2026-10-27-world-interactions-and-play.md)
and [TDD plan](../plans/2026-10-27-world-interactions-and-play.md).

Only completed lots with their verification and adversarial review recorded here
are delivered. Existing concurrent main changes and the index are preserved.
No commit, push or deployment is included.

## Lot 0: baseline and isolation — accepted

The existing default proof containers and networks are stopped but retained.
Their ownership is not inferred from their names. This execution adds a distinct
proof instance rather than deleting or restarting those resources.

The previously blocked backend unit run was diagnosed with faulthandler: Windows
asyncio creation blocks inside the sandbox's loopback socketpair. The same run
outside it passed all nine existing pose tests in 0.58s. No test fixture or
network guard was disabled.

The implementation ledger lives in the plan's ignored `.superpowers/sdd/`
workspace. At every lot boundary it records RED/GREEN evidence, adversarial
findings, corrections and remaining qualification conditions.

The named disposable instance `interactions-01a17aa3` runs on port 3014. Its
launcher isolation was developed RED/GREEN: six new intended failures, followed
by all twelve runner tests passing. Scoped Black and Ruff pass. The existing
frontend pose, navigation-to-object and acknowledged-seat suites pass 25 tests.
Every authored sitting/lying approach is reachable in that baseline.

The desktop proof browser measured frame/render p95 of 18/2.3 ms and 111.8 MiB
decoded textures (472 visible draws); at 390 by 844 it measured 18/1.1 ms,
94.9 MiB and 83 draws. Screenshots are retained in the ignored execution workspace.
These are observations in this development browser, not physical-device results.
Dashboard request/spend qualification belongs to the instrumented lot 3 workspace.

Adversarial review: bounded independent names, argument-array subprocesses,
label-checked deletion and archive path/secret exclusion preserve other resources.
No blocking finding remained at this boundary. No production service was changed.

## Lot 1: private experience preferences — accepted

The additive nullable JSONB document is independent of home/avatar. Strict
read/write contracts preserve unsupported storage, require explicit repair,
fence concurrent writes and merge only explicitly edited fields. The frontend
uses the existing owner query/mutation lifetime and rejects foreign/late results.

Evidence: initial missing-module failures preceded implementation; 47 backend
contract/registry/doc tests and 19 HTTP/deletion tests pass, as do eight frontend
owner-lifetime tests. All 93 disposable World integration tests pass. A final
four-test SQL rerun verifies actual account export, concurrent writes, partial
edits and schema-local upgrade/downgrade/upgrade with existing user preservation.
Nonincremental TypeScript, scoped ESLint/MyPy/Ruff/Black and whitespace checks pass.
The zero-debt World documentation ratchet remains zero; no baseline was relaxed.

Adversarial review covered ownership, capability withdrawal, revision races,
corruption, JSONB tracking, export/erase, query aborts and unintended shared/LLM
projection. No blocking finding remains in this lot. Its visible controls are
integrated by the following presentation lots.

## Lot 2: exploration and introduction — accepted

Physical discovery derives from the live native catalogue and activation policy.
It retains an accessible searchable list after the temporary floor marks expire.
Route display is on by default, optional and owner-persisted. Generic tables have
explicit stable seat bindings; specific seated activities retain their identity.
The optional three-step introduction advances on confirmed server movement and
actual native activity/menu opening, with explicit skip/replay and failed-save retry.
Mobile guidance leaves the joystick available by folding the toolbar.

Adversarial review found and reproduced three movement/lifetime defects: a
remaining segment crossing a chair after correction, a path surviving replacement
authority, and a consumed final segment leaving its approach beside the goal.
Focused RED tests preceded each correction. Routes retain their original goal;
unreachable/expired/withdrawn intents cancel. The approached local companion waits,
faces the owner and resumes its patrol afterwards. Peer control is unaffected.
Collision rules and product approach timeouts were not weakened.

Evidence on the final business snapshot:

- `task test:frontend:coverage`: 14,724 passed in 1,249 files; all existing floors
  pass. Global statements/branches/functions/lines: 86.16/80.94/84.45/87.74%.
- Four canonical Chromium native journeys pass in 2.2 minutes: desktop/mobile
  preference/discovery/seat, full introduction and shared/private pose/reconnect.
  Discovery axe checks report zero violations; the journeys trigger no paid call.
- `task lint:frontend`, browser-scenario nonincremental TypeScript,
  `task lint:i18n`, `task lint:hygiene`, scoped formatting and whitespace pass.
- The preceding real PostgreSQL/Redis World integration run passed all 94 tests.
  The regenerated scene catalogue passes parity; geometry was not moved.
- Four container/host SHA-256 comparisons match after removing diagnostic probes.
  Native JSON evidence is retained in the ignored execution workspace.

New coverage ratchets are derived from that full report, with at least two points
of margin: experience/discovery/tutorial, explicit seat context and authoritative
prediction. The existing pointer/social branch floor rises from 92 to 94.
Those four configured groups were checked against the retained report after the
threshold-only edit; the full test run above preceded that metadata edit.
No threshold or debt baseline was relaxed. This is development-browser evidence,
not a physical-device or production-build claim. No blocking finding remains at
this boundary; the dashboard offer belongs to lot 3.
## Lot 3: confirmed-seat native dashboard — accepted

The offer follows a matching local seat receipt and an explicit authored generic
seat/table binding. Decline, dismissal and Escape keep the person seated and
mount no dashboard reader. A contextual action can offer it again. A different
seat, standing or account change disposes the retained dashboard lifetime.

One DashboardWorkspace serves the ordinary route and World. Its full native
briefing, radio, results and consumption remain intact. A typed navigation port
preserves workboard filters, meetings, local drafts, settings, registers and SMS;
executable intents retain the existing native Chat transition and replay guard.
A separate stable modal host preserves dashboard state through non-modal Chat.

The retained host owns one explicitly gated briefing controller outside the
suspended visual tree. Hidden reads abort, owner invalidations remain queued,
and withdrawn SMS-derived text cannot resurface. An interrupted or withdrawn
text needs explicit retry; reopening never automatically buys another synthesis.
Statistics/limit transports also abort, and retained obsolete callbacks do no IO.

Adversarial RED/GREEN cases include retained state lost on modal-mode changes,
private invalidations lost under React Activity, late manual POST publication,
manual query loading stuck after abort, an old seat offer remaining visible,
and focus restoration competing with the native modal. WebKit mouse activation
also requires explicitly focusing the retry source before loading. The compact
browser helper now waits for account verification before expanding the toolbar.

Verification:

- Complete frontend suite: 14,775 tests in 1,258 files (458.32s), with coverage
  86.21/81/84.52/87.8 and all previous floors. Four new coverage groups retain
  at least two points of margin against this retained report. Their metadata
  edit follows the run. Later small focus/panel-width changes and two additional
  dismissal cases have focused verification; the full run preceded these edits.
- Full frontend lint and ratchets, subsequent scoped ESLint, nonincremental
  frontend/e2e TypeScript, six-locale parity, formatting and whitespace pass.
- Optimized Next build and TypeScript pass. All twelve final native journeys
  pass in 1.7 minutes across Chromium, Firefox and WebKit: desktop/mobile full
  dashboard, real confirmed seating, refusal without reads, unchanged pose,
  filtered Workboard/Back, close/reopen without repurchasing text, focus recovery,
  no horizontal overflow and axe without violations. Paid data is an explicit
  inert fixture; admission, movement, seating and native workspaces are real.
- A real HTTP RED/GREEN test proves the seventh admission remains refused while
  the fixture reset restores only its eight inert-account budgets. The initial
  cross-scenario 429 was test isolation, not permission to relax a product limit.
- Seven critical source hashes matched the container; the final Safari focus
  source hash was rechecked after rebuilding. Reports/screenshots are retained
  in the ignored execution workspace. No physical-device claim is made.

Final adversarial review covers owner/capability lifetimes, private projection,
consent/cost boundaries, pending transports, typed destinations and actual modal
focus/visibility on all three engines. No demonstrated blocking issue remains
in this lot. No provider, prompt, global budget or production service changed.

## Lot 4: private signals and truthful acting — accepted

Four private signal families reuse native readers: SMS, reminder, Workboard and
generated assets. Only finite counts/status reach local sprite painting; private
identities remain in the current owner controller, and no private body enters a
World socket. The phone and scene objects share one notification/inbox owner.
Reconnect uncertainty and failed reads are distinct from an empty resource.

The existing native expression resolver and rig drive LIA from current chat,
HITL, actual playback and execution evidence. A prepared draft does not announce
an executed action. The World clock samples existing stores without an extra
poll, timer, provider or prompt. Body accents expire independently of their longer
semantic label, cannot replay after culling or a suspended tab, and use static
distinguishable cues under reduced motion. Conversation headers retain a readable
state on phones; desktop follow framing keeps nearby characters in the exposed
scene without changing movement authority or overriding a manual camera pan.

Adversarial RED/GREEN cases found and fixed failure priority hidden by background
work, revoked SMS callbacks surviving a feature toggle, focus lost from an
unmounted phone opener, fast verification leaving an obsolete focus bookmark,
culled completion animations replaying later, and visual preferences not reaching
a replacement runtime. The observer regression also proves current-account
publication with no runtime replacement when the callback changes.

The complete frontend run before the final framing/header additions passed
14,807 tests in 1,265 files, with statements/branches/functions/lines coverage
86.25/81.13/84.61/87.83%; all floors pass. Seven new scoped floors were checked
against that retained report with at least two points of margin. The later
framing/header changes pass 31 focused cases and all 1,740 tests in the affected
World/eyes/companion suites. Full frontend lint and unchanged complexity/type/
accessibility ratchets, nonincremental frontend/browser TypeScript, formatting
and whitespace pass. The framing projection measures 100% on all four coverage
instruments and has a new scoped floor with two points of margin.

All 21 final native journeys pass on Chromium, Firefox and WebKit (7.1 minutes):
desktop/mobile dashboard regression, shared phone/object acknowledgement, actual
badge hit pixels, second-account isolation, nonempty socket frames without the
private marker, axe without violations, and all five chat evidence states at
1,280 and 390 pixels. Desktop and phone captures were inspected; five additional
host/container source hashes match. The preceding optimized five-client probe
measures desktop/mobile balanced frame p95 18ms, render p95 2.1/1.7ms and decoded
textures 45/39.5MiB; low mobile uses 23.2MiB, and CPU4x low uses 20.2MiB. This
snow/optimized profile differs from the lot0 development/clear baseline; no
like-for-like performance gain is asserted. The final layout additions have
native and focused verification rather than another full performance probe.

Backend World/proof unit verification passes 202 cases. Six-locale parity,
hygiene, scene catalogue and contract documentation checks pass. No prompt,
provider, token/quota policy or production service changed. These are disposable
desktop-browser simulations, not physical-device certification. The inline cold
review leaves no demonstrated blocking finding at this boundary.

## Lot 5: reactive decoration, presets and seasons — accepted

Nine local responses reuse authored artwork: cat turn/purr, bird and butterfly
responses, pond/fountain ripples, leaves, flowers, billiard cue ball and machine
indicator. A currently visible scene target and its DOM equivalent share one
bounded owner runtime. Explicit menu selection frames the decor without moving
the player; phone selection folds the HUD and restores Canvas focus. Direct
Canvas taps preserve the chosen camera. Responses use absolute time, cooldowns,
quality limits and a byte/entry-bounded sprite cache; they cannot add collision
geometry or replay excess effects after a quality change or hidden-tab expiry.

Ten editable combinations of existing avatar fields provide five masculine and
five feminine styles, with all five skin tones in each set. Selection changes
the preview; the existing consent/revision save remains the only publication.
No gender or preset identity is stored. Manual edits retain their values and
show the custom indicator. Calendar seasons use only the native fresh server
anchor and account timezone, with explicit hemisphere, manual and off choices.
Foliage and flowers change; weather, walkability and furniture identity do not.

Inline cold review corrected private seasonal-surface invalidation, winter
petals, a hidden reaction under the HUD, and mobile camera gestures swallowed
by expanded controls. The native camera helper now checks its actual Canvas
drag origin and restores the original toolbar state. Renderer doubles implement
the complete public typed port, preventing silent fixture drift. No scope,
rate limit, timeout or quality baseline was relaxed.

Verification on the final business sources:

- The affected World suite passes 529 tests in 121 files (46.15s). Scoped new
  logic coverage is 99.39/90.78/100/100; five new floor groups retain measured
  margin. A subsequent two-case art run also exercises all ten presets in eight
  directions and standing/seated/lying poses within the existing sprite budget.
- Full frontend lint passes; final complexity remains 37 hotspots/max46,
  double assertions119/74 and accessibility violations0. Final scoped ESLint,
  nonincremental frontend/browser TypeScript, six-locale parity, formatting,
  catalogue and whitespace checks pass. All24 source/locale hashes match the
  optimized qualification container.
- Twelve distinct native scenarios are verified across Chromium/Firefox/WebKit:
  nine mobile/private-signal regressions passed in the first final batch; its
  three desktop cases stopped at the intentionally required reload takeover.
  After adding that existing native gesture to the scenario, all three desktop
  cases pass (2.5 minutes), including nine real reactions, menu dismissal/focus,
  four seasonal night palettes/off and persisted preferences. Day/night, avatar
  and mobile captures were inspected; axe reports no violations. Product
  authority correctly stayed withdrawn until explicit takeover.
- The optimized five-client probe passes with one full UI and four independent
  transport browsers. Evening/snow, balanced desktop/mobile:59.6/60fps,
  frame p95 16.7ms, render p95 4.3/2.5ms, textures64.7/59.6MiB. Low mobile:
  29.7fps,33.4/2.8ms,24MiB. The stressed CPU4x/pinched158% sample measures
  17.1fps,266.8/14.8ms,20.5MiB; the preceding invocation measured21.7fps.
  These are emulation observations, not physical-device certification or a
  guaranteed frame rate. The earlier afternoon baseline has different lighting;
  no unsupported like-for-like gain or regression percentage is asserted.

The final metric reader now also records hidden toolbar zoom text, and its pinch
oracle requires a real nonempty starting zoom; the retained measurement already
shows the actual95%→158% gesture. This test-only oracle tightening follows the
last probe; browser TypeScript passes. No provider, prompt, token/quota policy,
shared authority record or production service changed. No demonstrated blocking
issue remains within this lot; the stressed-device observations remain visible.


## Lot 6: socket v2 and finite social gestures — accepted

The scene now uses socket v2 and a separately declared persistence generation.
Preference, avatar, home and correspondence contracts retain their v1 formats.
An owner-only ring of typed command receipts confirms an exact pose sequence;
a newer gesture or movement acknowledgment cannot open a seat activity. Six
authored gestures have bounded expiry/cooldown, controller and sequence fences,
visibility/home refusal and takeover-safe event identities. Home gestures remain
local. Native menus and scene-only shortcuts provide the same six actions, with
finite accessible announcements and reduced-motion rendering.

The old authority fixture was captured before this upgrade. Erasure uses the
same bounded Redis CAS with an explicit legacy reader and original-field-set
encoder, preserving peers, epoch, FIFO and old-reader compatibility. Current
admission never uses the legacy writer. Oversized text is refused before an
encoded copy is allocated. Game participant DTOs move together with their real
authority in lot 8, after the pure typed boards; no dormant game command ships.

Verification and inline adversarial review:

- Backend: 218 unit tests pass; new social/legacy/socket modules measure 100%
  statement coverage under a targeted 90% gate. Final disposable SQL/Redis
  integration: 95 tests pass, including real two-socket gesture/cooldown/privacy
  and selective erasure of both root and versioned v1 documents. Full-capacity
  snapshots with sixteen owner receipts remain below the existing wire ceiling.
- Frontend: 546 World tests pass, followed by fifteen owner/speech checks after
  eliminating hidden-tab empty-array rerenders. Targeted coverage measures
  93.79/86.56/97.87/97.75; new timing/projection and native-menu floors retain
  margin. Strict frontend/browser TypeScript, scoped ESLint, MyPy, Ruff,
  formatting, catalogue parity, six-locale parity and zero contract-documentation
  debt pass. Complexity holds at 37 hotspots/max46; no baseline was raised.
- Six final native scenarios pass across Chromium/Firefox/WebKit and 1280/390px,
  with independent browser processes, real accounts/Redis, receiver visibility,
  exact owner cooldown refusals, expiry and no peer receipt disclosure. Axe
  reports zero violations without filtering. Two additional real confirmed-seat
  Dashboard journeys pass on desktop/mobile with the new receipt contract.
- The initial native mobile run exposed a hidden primary heading when the HUD
  collapsed. The heading now remains in the accessible document independently
  of toolbar visibility. Visual review also exposed a nameplate overlap and
  potential gesture clipping: a RED/GREEN geometry test now holds every phase
  inside the existing actor layer, beside the head, with unchanged ground contact.
- Absolute monotonic deadlines prevent a suspended simulation clock from
  replaying a stale gesture. Event identities and receipts are bounded; old
  socket/scene refusal offers an explicit reload, without credentials in URLs
  or logging validation payloads. All 202 World/locale source hashes match the
  final optimized qualification build. Captures and detailed logs are retained
  in the ignored execution ledger.

No provider, prompt, generated-media service, token quota or persistent game
history is involved. The final cold review found no remaining blocking issue
within this lot. Production and physical mobile devices were not deployed or
certified by this local proof.


## Lot 7: pure game rules and deterministic opponents — accepted

Three immutable, closed rule families now cover tic-tac-toe, four-in-row and
Reversi. Legal moves and rule-derived outcomes are independent of networking
and rendering. Reversi explicitly handles a forced pass, double-no-move ending
with empty cells, eight capture rays and exact terminal disc counts. Gravity,
all alignment directions, full-board draws, terminal immutability, occupied
cells, malformed fields and contradictory winners are qualified.

The deterministic computer has a hard counted expansion budget and a legal
fallback. Search and heuristic code perform no I/O, LLM call or persistent
history write. All reachable tic-tac-toe positions are enumerated, and both
computer colors are checked against every legal human continuation: no loss.
The other opponents take immediate wins, block immediate losses and finish
complete games even under a small budget. They are heuristics, not a claim of
perfect play. The table service must run this CPU work outside CAS/SQL locks.

Three existing authored cabinets receive stable semantic keys. One compiled
asset binds the same client/server rule identities and reachable approaches.
RED tests caught an approach too close to the collision-grid boundary and a
permutation of rules that a mere uniqueness check missed. Native collision
fits, a route from the actual spawn, exact identity sets and startup rule/key
correspondence now agree. No active game command or game UI ships in this lot.

Verification: 289 World backend tests pass, followed by 71 focused rule/bot/
catalogue tests with 98.72% statement coverage over all four new modules under
a targeted 90% gate. Frontend catalogue coverage is 100% on every axis with a
new 98% floor; 39 affected navigation/discovery/decor tests pass. MyPy, Ruff,
ESLint, frontend TypeScript, formatting, generated catalogue parity and zero
World contract-documentation debt pass. Every new backend function stays below
the strict complexity threshold (maximum 13). The global ratchet remains
260 hotspots/max77; its lifecycle increase from the preceding lot was removed
by a shared erasure predicate, with six real SQL/Redis lifecycle tests passing.

An owned profiler measures initial and midgame positions chosen from twenty
deterministic legal continuations, three samples each. Tic-tac-toe opening
uses the 6000-node cap and takes roughly70–127ms on this Windows host; its
midgame uses96 nodes. Four-in-row samples use236/142 nodes; Reversi48/345.
The observed overall range is roughly2–127ms. These are local observations,
not a wall-clock performance guarantee. No unbounded search or new service
is introduced. Final inline adversarial review found no remaining blocking
issue in this pure-rule lot; multiplayer authority and user-facing play remain
the next two lots.

## Lot 8: game authority and native lifecycle — accepted

The scene advances independently of socket v2, and the current persistence
generation gains strictly typed bounded cabinet records. Frozen legacy readers
preserve the previous authority generations and nested field sets during account
erasure. Each command authenticates its native cookie, uses a distributed account
budget, prepares bounded computer work outside locks, then checks fresh eligibility
and mutual blocks under canonical SQL parent locks through a bounded Redis CAS.
The existing contact block/unblock source now takes those same locks.

Only participants receive boards. Requesters receive no board; spectators receive
coarse cabinet availability. Refusals also redact policy-hidden round identity.
Pause and remaining-turn clocks are durably anchored once. Explicit rejoin,
fresh-board host consent, alternate-color human/solo rematches, independent round
and turn deadlines, admission loss, erasure and the optional child deployment
limit are implemented. No LLM, provider, prompt, agent registry or durable game
history is added. Native World operator policy remains authoritative, with its
existing bounded projection-refresh window and fresh checks on every mutation.

Cold adversarial review reproduced and corrected blocked-outsider cancellation
and round-ID disclosure, takeover acceptance without rejoin, shape-valid corrupt
boards/results/rosters, unnecessary bot work for invalid controllers, repeated
disconnect deadline extension, admission-generation inheritance, orphaned rematch
consent on departure and concurrent-move departure conflicts. Leaving remains
account/controller/round-fenced while permitting a newer revision of that same
round. A late invitation is capped by the table's remaining lifetime. Pure
transition tests now validate complete state through the real storage codec.

Verification includes 480 passing World unit/integration and native peer-fence
tests on real disposable PostgreSQL/Redis, followed by the final 391-test unit
and game-integration run with 96.14% statement coverage over all game modules.
Independent SQL connections prove opposite-direction blocks wait for game locks.
Competing requests/moves, an acknowledgment lost after real EXEC, deactivated or
deleted peers, cookie mismatch, game-only erasure, distributed throttling and
disabled startup/re-enable are exercised. Declared worst-case UTF-8 snapshots
stay within the strict browser frame ceiling; CPU remains node-bounded with
two admitted preparations per process and an immediate legal fallback.

All 550 World frontend tests pass. The strict game parser measures 100% on all
four coverage axes and gains a 98% floor. TypeScript, MyPy over 74 source modules,
Ruff/Black, generated catalogues, contract documentation and documentation preview
pass. No World function reaches the strict complexity threshold; backend and
frontend ratchets remain unchanged. Four finite-label metrics reach the new
World arcade dashboard. Active environment files and templates contain the
bounded settings; the isolated process reports the expected public limits.

The final inline review found no remaining blocker in this server lot. Gameplay
UI and browser feasibility are the next lot. The running optimized browser proof
still represents the preceding scene; this acceptance makes no new live-browser
or physical-device claim and includes no production deployment.


## Lot 9 — accepted: native cabinet games and adversarial review

The authored cabinets now open owner-bound, accessible native game panels.
One game client shares the existing socket sequence, fences the exact rendered
round/revision/transport generation, accepts only correlated receipts and never
changes a board speculatively. One pending timeout, explicit uncertainty recovery,
rejoin, invitation consent, alternating rematches and deduplicated departure cover
the interaction lifecycle. Grid coordinates, gravity columns, explicit Reversi
pass, translated status and keyboard controls use the authoritative legal moves.
All six locales are complete. Board boundaries measured 5.26:1 in the final mobile
capture after correcting the original low-contrast lines.

Inline cold review corrected observed failures before acceptance: policy-hidden
blocked reservations, lost or refused departures, an uncertain acceptance racing
panel closure, missing no-frame timeout, duplicate pending-click feedback and
native focus returning to BODY. The native focus trace identified BODY being
retained as an opener; the activity shell now falls back to the scene for root
or disabled targets. Dedicated regressions reproduce both cases. Busy choices
preserve focus; reduced motion and server-time announcements remain bounded.
There are no new providers, prompts, assistant-history rows, memory or token costs.

Current evidence includes 590 passing World frontend tests, 487 World unit and
real PostgreSQL/Redis tests, and focused game coverage above the new shrink-only
floors. The initial nine native game/engine journeys pass. The strengthened matrix
checks actual win/draw/rule outcome; eight pass together, and the remaining Firefox
rejoin case passes after correcting its test's stale peer-round expectation.
The final three-engine same-account takeover/Escape/focus matrix passes without
DOM instrumentation. A final five-process run completes two human games and one
computer game simultaneously: three independent cabinet rounds, valid winners,
no paid request, maximum observed snapshot 5949 bytes and confirmation p95 164 ms.
These disposable-host observations are not phone or production performance claims.

The complete frontend run passes all 14899 tests; its coverage gate identifies
missing seasonal-tree branches from lot 5. A new geometry/color simulation restores
100% tree coverage on all axes without changing or lowering its existing floor.
The complete coverage command has not been repeated after that test-only fix;
it remains an integrated lot-12 gate. The full frontend lint/ratchet/type gate,
backend type/lint checks, size guard, six-locale parity, catalogue and documentation
preview pass. Scope-local checks pass again after the final focus correction.

No known source blocker remains in this lot after inline adversarial review.
Physical devices, screen readers and Raspberry Pi performance remain separate
qualification boundaries. The original index and concurrent working tree are
preserved; no commit, push or deployment is included.

## Lot 10 — accepted: safe local photos

A frozen allowlist selects own appearance/pose, LIA, camera and decor. A separate
photo renderer reuses the existing painters, excluding visitors, names, bubbles,
private signals, interaction markers and activity indicators. It never copies the
live Canvas. Landscape and portrait JPEGs have bounded physical size, bytes,
encoding attempts and lifetime. Blob URLs are owner-bound and revoked; Share is
a separate explicit click, with cancellation and chooser offered distinguished.
No upload, provider call, memory, message or server photo persistence is introduced.

Inline cold review reproduced and fixed a disposal-exception lease trap and
StrictMode double allocation. Real mobile axe found a preview scroll region
without keyboard access; the corrected single-scroll layout passes in all three
engines at 320px, 390px and rotated landscape, including repeated close/reopen
and return of focus. The actual visitor-before/after pixel comparison passes in
Chromium, Firefox and WebKit. Exported JPEGs visibly preserve the owner, LIA and
decor; both formats download with a generic filename below the byte limit.

Evidence: 616 World frontend tests in 140 files; 22 focused photo tests; measured
photo coverage 96.99% statements, 88.63% branches, 96.29% functions and 98.55% lines.
New shrink-only photo floors, existing complexity ratchet, strict changed-source
lint/type checks, E2E typing, six-locale parity and documentation preview pass.
Physical native choosers remain lot 11 qualification, not claimed by browser tests.

## Lot 11 — accepted here; physical qualification documented separately

The native bridge advertises a positive optional versioned capability. Older
shells keep the preview/download path. Browser sharing preserves the fresh click;
native sharing receives only the selected completed JPEG and rechecks ownership
after reading it. Native MIME, filename, bytes, image signature and dimensions
are bounded; neither platform accepts a path or URL. One chooser is fenced by
current page/presenter lifecycle. Android uses a distinct read-only FileProvider;
iOS anchors the activity sheet for iPad. The private temporary cache is bounded
and expires independently of downstream publication. Results say offered or
cancelled where supported, never that a target has published.

The inline cold review checked actual Capacitor threading and method registration,
Android minimum API compatibility, private cache ownership, background/disposal,
user activation and memory allocation. The second browser owner check is retained.
The native build path now runs authored JVM tests before packaging.

Bridge tests and native declaration guards pass; native photo coverage is 100%
on all four axes. Android compiles and packages with the installed JDK 21 and
build-tools 36 using task-owned isolated outputs; three authored JVM tests pass.
The default local build requires unavailable build-tools 35 and is not reported
as passing. No SDK was installed and no licence was accepted. iOS preparation
and source declaration pass, but Windows cannot run Xcode. No Android device is
attached. Actual Android/iPhone/iPad chooser, cancel, target and background-return
qualification remains a release gate. The owner explicitly requested completing qualification here and documenting
these remaining platform checks; they are outside this Windows run.

## Lot 12 — integrated qualification accepted here

All approved feature lots are implemented. The photo/native review additionally
exercises the real application lifetime guard, without the earlier partial mock:
closing the preview before native handoff and switching owner while a previous
renderer completes both remain fenced. No duplicate lifetime mechanism was added.
The final photo/native group has 34 passing tests and measured coverage of 97.44%
statements, 92.44% branches, 96.82% functions and 98.74% lines. The panel branch
floor is tightened to 84%; all earlier floors remain intact.

The final native photo matrix passes all six journeys in Chromium, Firefox and
WebKit, including actual JPEG privacy, both formats, 320px/reflow/rotation, axe,
focus and repeated reopen. Its pixel reference is copied from the displayed safe
photo before Blob URL revocation. Visitor positioning uses a real canvas click
through authored reachable foreground and awaits server-confirmed arrival. No
privacy threshold was relaxed to absorb a test setup or detached-image failure.

The optimized menu/navigation/performance journey fills the configured capacity
with five independent native clients and verifies the pinch result, 95% to 158%.
A fresh run after frontend coverage reports desktop 60 fps, phone balanced 59.6,
and economic 30; the 4x slowdown sample reports 18.8 fps and render-p95 9.2ms.
The earlier lot-5 observation was 17.1 fps and 14.8ms under slowdown. These are
host observations with different lighting/time/load, not a controlled hardware
benchmark or physical-phone/Raspberry Pi guarantee. The heavy slowed profile is
still below economic cadence; no phone release-performance claim is inferred.
The strict browser-frame ceiling also covers ten maximum-size aliases and the
full declared legal-move/receipt vocabulary in the backend simulation.

Current completed gates: final full frontend coverage 14937 tests/1294 files
and every scoped threshold; World backend 489 with real PostgreSQL/Redis; virgin
migration replay, every explicit-head-parent downgrade/upgrade and structural
comparison; frontend lint/types/all ratchets; backend Ruff/Black/MyPy and the
strict test set; cross-cutting hygiene, catalogue, cycles, dependency,
observability, lock and CI-parity gates; marker census with no new orphan;
deployment tests including 179 PowerShell cases; installer 92 passed/3 POSIX skips.
Six-locale FAQ and UI parity, generated maps and documentation preview pass.

The complete hermetic browser invocation finished with 764 passing and five
console-only failures. Current static flags were missing from the disposable
server, and the shared World fixture lacked the needs-me read endpoint. Those
five cases pass after the environment/fixture corrections; all 61 World
hermetic journeys also pass. No console error was hidden or assertion weakened.

The complete backend unit invocation finished with 47245 passing, eight failing,
30 skipped and nine deselected. The source findings were nullable metadata,
an empty best-effort handler, three dashboard conventions and generated counts.
Their final focused group passes 52 tests; the final World group passes 489.
The obsolete untracked OAuth sender was investigated against Git history and
current callers. The owner authorized removing its exact archived copy; the
unchanged single-sender guard passes all eight tests. The index-based
documentation failure passes with an isolated candidate index and object store;
the real index SHA-256 is unchanged. These are documented reruns, not a claim
that the initial complete invocation exited green.

The complete integration invocation finished with 5368 passing, 101 failing,
three skipped and ten deselected. The disposable test host lacked the public
test configuration and cached public tokenizer, and its flat layout broke two
artifact paths. All 101 cases pass after restoring the native test environment.
The native slow selection adds three passing cases. A complete host collection
selects exactly four cross-root integration cases; all four pass on real
PostgreSQL/Redis with CI-equivalent localhost access. The unit network guard is
unchanged. The external-DB strategy skip and two Windows-only contracts are
explicit; no unavailable database was counted as a pass.

The first cross-root container collection also exposed a native Python crash;
the next reached unrelated full-checkout file errors. The exact four-node
manifest from successful complete host collection avoids those unrelated
module imports while executing every selected cross-root case. It introduces
no allowlist or test-selection change in the repository.

Coverage retains raw measurements. Container paths are normalized to the actual
checkout. Superseded World/user/bootstrap line measurements are removed before
merging fresh unit and SQL measurements into their respective suite files;
the deliberately removed OAuth relic contributes no obsolete missing source.
The native combined and changed-line gates run on these completed suite data.

Both native coverage gates pass: combined coverage reports 88%; changed-line
coverage measures 1448 of 1508 lines, 96.02%, across 45 files, including new
untracked modules. These are measured results; configured thresholds remain in
their native sources. No threshold is lowered. The final rebuilt preview also
passes a fresh real two-player/computer game. All 3725 runtime Python modules
match the delivered checkout after newline normalization; no stale source
remains in the running proof.

The original `ci:fast` command stopped at index-based documentation auditing,
which cannot see new untracked files. Its remaining components are executed
separately. The official documentation preview and the native guard against
the isolated candidate index pass. The real index stays unchanged.

### Final self-assessment boundaries

| Criterion | Current verdict |
| --- | --- |
| Approved functional scope and code/registry/ownership contracts | Implemented and reviewed; no known source finding remains |
| Privacy, model calls, token/quota accounting | Local decorative/game/photo paths introduce none; native assistant/dashboard accounting retained |
| TDD, degraded paths and browser simulations | World 489, frontend 14937 and browser matrices pass; broad initial failures and successful reruns are disclosed above |
| Combined and changed-line backend coverage | Native gates pass on current, normalized suite measurements; raw evidence retained |
| Native Android source/build and JVM guards | Compiled/tested with disclosed installed-tool override |
| iOS compilation, physical chooser/accessibility and Pi/phone performance | Unverified environment; explicit release gates, not waived |
| Delivery boundary | No commit, push or deployment; original index and concurrent changes preserved |

The owner explicitly chose to complete the available qualification here and
document the remaining platform checks. Appropriate Apple hosts and actual
devices remain required for those checks; no platform pass is inferred.

The final inline adversarial pass found no outstanding demonstrated source
defect in the approved scope. All available functional, integration, privacy,
accessibility and quality checks described here have completed. Universal
perfection, physical platform behavior and a controlled target-device performance
guarantee are not established by this run. The slowed emulator's cadence and
the uncontrolled baseline comparison remain explicit performance limitations.
