# LIA World: lived-in house refinement qualification

Scope: the owner's room-by-room brief and subsequent furnishing, circulation, garden, lighting and running corrections. Execution remains inline in the existing external worktree. Main, concurrent checkouts and shared dependency junctions are preserved. No merge, push or production deployment has occurred.

Related documents: [design](../specs/2026-10-25-world-lived-in-house-design.md), [plan](../plans/2026-10-25-world-lived-in-house.md), [technical guide](../../technical/WORLD_PROTOTYPE.md).

## Published iteration (g20)

The usable local preview is [the shared world](http://127.0.0.6:3010/world-preview?shared=1&resume=1). Reload to load the revised authored scene. This is an isolated development proof with inert identities and simulated unbilled translation, not the production assistant.

Automated accounts run only against the separately isolated QA host at 127.0.0.7:3012. Its API uses a fresh SQL database/role and Redis, with newly generated credentials. No credentials were copied from another API. Never run automated account/controller journeys against the owner's public preview: doing so can legitimately take over an account the owner is inspecting.

## Implemented corrections

- One connected house surrounds a central hall reaching the front terrace. The restroom now occupies a visible foreground corner; the studio stands farther away behind a green buffer and a garden path. Exterior entrances on the left and the left terrace were removed.
- Four inward-facing three-person benches surround the marble fountain. Room doors and activity/seat approaches are checked against the generated authoritative collision geometry.
- The professional meeting table faces a full rear wall with the presentation screen; the end chair faces it, with three chairs on each long side and individual papers and pens.
- Multimedia easels line the left wall with distinct image, document, camera and bookmark artwork. Their confirmed seats open the corresponding native gallery family. The drawing table prepares an editable localized image request without sending it.
- Diner upholstery is true red; larger checker squares reduce visual noise. Booths are shifted away from circulation. The bar, bottle shelving, arched jukebox and smaller furniture gained original detailed models.
- The phone seat is nearer its wall phone. The studio sofa faces the bed, the TV is mounted on the left wall and the commitments board is against the wall. Unnecessary tall storage was removed from the studio and divination room.
- Indoor lamps sit on authored side tables; outdoor posts light the paths. Wall fixtures are mounted only on supported visible walls and kept clear of inset window bays. Support-aware depth ordering prevents fixtures from disappearing into their own support.
- The stepped pond sits in grass, with stone banks, reeds and lilies. Ground detail, planted vegetable beds, three tree families and bounded location-based model variations replace flat repetition. Terrace tables have opposing chairs and offset tall parasols.
- Night darkening and precipitation are clipped to exposed space. Interiors retain their normal illumination; exposed lamps and inset windows add warm, culled halos. Fine rain streaks and bounded ripples replace the previous heavy treatment.
- Double click/tap requests running through the existing movement authority. The client sends an intent, never a chosen speed; server collision, elapsed-time caps and controller checks remain enforced.
- Habits belong in the gym, news in the diner and weather in engineering. Radio, smartphone and forecast widgets remain separate from configuration.
- LIA offers conversation, his native journal, alerts and psyche. Native Relations, Meetings, Workboard, SMS and gallery components stay embedded in the world, with ordinary application route behavior retained.

Animations remain bounded by quality, visibility and reduced-motion settings. Static detail is baked into cached textures; no provider or model is invoked for navigation or animation.

## Empirical native checks

The native multi-engine journeys cover separate-user message delivery and replies, reload and lost-acknowledgment deduplication, interrupted mailbox recovery, account changes, denied peer mutations, private memory editing, shared poses/reconnect/standing, gallery filters/confirmed seats/mobile, unsent drafts and server-bounded running. Their latest completed batch passed all 24 cases across Chromium, Firefox and WebKit.

The smartphone was additionally exercised through the application's real notification SSE and owner-encrypted SMS storage in the disposable database. A native SMS arrival and a real reminder-shaped notification produced distinct counters. Opening the reminder showed its content; opening the stored SMS read its native archive body and reading both cleared the counters. No external SMS was sent. An intentionally absent SMS record produced the expected unavailable-message UI and one expected HTTP 404, without a JavaScript exception.

The forecast widget was verified over the real authenticated endpoint for both a cache miss and a schema-validated inert five-day forecast inserted into the disposable owner's native cache with a short TTL. It rendered the native weather card, five daily entries and the timestamp in the owner's Shanghai timezone. The endpoint did not fetch a provider; opening Conversation only prepared an unsent request.

A same-origin notification stream remained open for 105 seconds, receiving native keepalives at approximately thirty-second intervals. Comparison with the direct API isolated Next's previous rewrite idle timeout. The bounded rewrite proxy timeout now exceeds the native keepalive interval; production reverse-proxy and ordinary request timeout settings were not changed.

## Qualification state

| Check | Recorded result |
|---|---|
| Complete frontend suite with matching locked Docker coverage tooling | 1180 files passed; 14255 tests passed, four existing skips; all coverage thresholds passed (global lines 87.05%) |
| Backend world and briefing unit suites | 533 passed |
| Backend MyPy | No issues in 3656 source files |
| Frontend application and E2E TypeScript | Passed |
| Full frontend ESLint, accessibility and complexity ratchets | Passed; no baseline increased |
| Hook ratchet | Holds its existing per-file baseline |
| Locale and generated client/server catalogue parity | Passed |
| Confirmed-seat intent and session-inbox pure contracts | All four coverage axes locked at 100%; 13 targeted tests passed |
| Native service journeys across Chromium, Firefox and WebKit | 24 passed |
| Native five-plus-one capacity/FIFO/control/mobile-axe journey | Passed in Chromium |
| Applicable hermetic world cases across three engines | 71 qualified; four deliberate engine-specific exclusions, as detailed below |
| Decoded textures after all places and far zoom | Chromium 86.6 MiB, Firefox 86.6 MiB, WebKit 86.9 MiB, below the 128 MiB test ceiling |
| Published application-source parity | 1623 frontend/config files and 32 world/backend-route files matched the worktree and QA snapshots |

The complete world smoke batch recorded 70 passes, four declared exclusions and one old ground-click fixture failure on WebKit. The clicked rightward pixel could select autonomous LIA in the revised layout; opening his menu was correct behavior. The test now waits for rest, chooses the clear central aisle, verifies the non-interactive cursor and checks actual displacement. Its corrected replay passed in all three engines. This qualifies 71 distinct applicable smoke cases; the original full report remains retained with its failure rather than being relabeled green. Header-language and CDP-specific scenarios deliberately run only in Chromium.

The expanded touch matrix checks every control's visibility, enabled state, physical bounds and actual center hit target atomically in the browser. It retains a real actionability trial at every viewport and held walking afterward. This avoids hundreds of remote trial-click round trips exhausting the original matrix budget in Firefox/WebKit; timeout bounds, target coverage and overlap checks were not relaxed. A pending hermetic EventSource can log an expected disconnect when teardown cancels it; active-journey console checks run before that cancellation. Native SSE has its separate real-service qualification.

Cold-review hardening also refuses a structurally valid non-weather card in the weather cache and preserves the original timestamp of a stale observation after a failed refresh. Both defects were reproduced with failing tests before correction. Real disposable-cache/browser probes confirmed the null fallback for the wrong card and the explicit error plus original observation date for stale weather. No provider fallback runs. Presentation was split into a focused observation component to preserve the unchanged complexity ratchet.


## Adversarial review and diagnostic history

The review followed actual ownership/authority paths, retained callbacks, stream cleanup, seat acknowledgments, navigation, wall support, window clearance, collision approaches, decoded caches and viewport hit targets, alongside the automated tests.

The first complete frontend run passed its tests but failed global line, prop-style branch and Relations branch floors. Added tests cover private native-panel lifetimes, embedded meeting navigation/focus, Relations refresh/favorite errors, civil-clock/reduced-motion behavior and checker/window cache isolation. No threshold was lowered. The subsequent complete run passed all floors; strict pure-contract floors were added for confirmed seat intent and owner-qualified session arrivals.

The short-landscape gesture matrix exposed a real widget/direction-pad overlap. Widgets now share the lower row with fixed-size icon targets and compact camera controls. Its expanded regression includes the three active widgets in all hit-target and bounding-box checks, rather than ignoring them.

A later trial hit Next's development badge instead of a movement button. Only isolated development builds whose output directory belongs to the world-preview family suppress that status indicator. Build and runtime error overlays remain active, using the documented [Next development-indicator option](https://nextjs.org/docs/app/api-reference/config/next-config-js/devIndicators). Ordinary development and production configuration retain their normal behavior.

The remaining development-issue badge came from unmocked account-shell calls in the old inert fixture, not from an obscured game target. The fixture now supplies schema-correct home/environment data, an empty mailbox, inactive run/broadcast/debug reads, presence acknowledgment and the existing genuinely pending notification stream. The real API/native-account qualification stays separate. Touch verification additionally requires no browser console errors; no forced clicks or overlay-hiding CSS were used.

An early Chromium art run exceeded its timeout while full coverage was running. The same unmodified case completed in nine seconds in isolation. A subsequent multi-engine run completed Chromium/Firefox and then encountered a WebKit process stuck in kernel exit during cleanup. Its interrupted result was retained. Disabling core dumps for the disposable test process allowed a clean full art run; no application assertions, retries or engine selection were weakened. One later test-runner process exited before test discovery; listing the same tests succeeded and the actual gesture verification was run separately.

Raw reports, screenshots, process diagnostics and logs are retained under the worktree's ignored temporary evidence directory; they are not committed or copied into public application assets.

## Acceptance boundaries

Software-rendered container browsers and mobile viewports do not qualify a physical Raspberry Pi, phone GPU, battery or thermal behavior. Decoded texture accounting excludes browser heap, compositor and driver memory. Frame interval and synchronous render work are different metrics. Real supplier translation fidelity, paid agent execution, external calls and SMS delivery remain separate acceptance steps.

The smartphone inbox records arrivals during this world session. It is bounded and ephemeral; it is not a durable notification replay mechanism. Native archives remain the source for stored messages.

Art acceptance belongs to the owner. Automated silhouette, geometry and browser tests establish specific properties; they do not certify aesthetic perfection.

## Owned-resource handover

The final complete frontend run used the frozen published sources and retained its raw log and coverage JSON. Backend, frontend application/E2E type checks, full ESLint, accessibility and complexity gates passed. Documentation is checked against the prospective index with the repository's preview audit.

The fresh QA API and Redis and an inactive owned preview build were removed after evidence preservation. The QA web container was also removed after its final coverage was copied. Shared dependency mounts, database volumes, generic development images and the public preview's four services remain. No global prune, forced removal, shared engine restart or Git mutation is used.

Two obsolete owned containers have kernel-stuck processes: lia-world-qualification-api and lia-world-g18-browser. A bounded graceful stop of the browser timed out; removal was not attempted. Their names and diagnostic history are retained in the local cleanup evidence. They require later host-level recovery when concurrent development can safely stop.

## Delivery self-review

The authored refinement, private native integrations and relevant automated acceptance paths are implemented and qualified as recorded above. Privacy/authority, bounded caches/animations, responsive hit targets and source parity were reviewed independently of test counts. No new LLM prompt or paid execution path is introduced by this refinement. Native quotas and approval remain authoritative.

This closes the software iteration; it does not assert universal edge-case coverage, hardware certification, supplier fidelity or aesthetic perfection. The owner can review the retained usable preview before subsequent artistic changes.


## Cold visual follow-up (g21)

This later pass reviews every authored room, the garden, terrace, pond and vegetable
beds in real browser captures, both by day and by night, at play and enlarged zoom.
The earlier service, backend and full-stack results above remain historical g20
evidence; g21 changes only frontend artwork, compositing and its tests.

### Corrections and detail

- Tabletop materials now respect the authored surface instead of all becoming oak.
  Neutral enamel, linen and dark frames separate furniture from its floor and accent.
- Task chairs, reading chairs and terrace chairs have different bases and backs.
  The drawn cushion meets the authoritative seat height in all authored orientations.
- Shelves carry grouped books and stacks; archive cabinets use green metal and
  contrasting drawer labels. Machines, lamps, plant pots, foliage and framed prints
  have bounded variants. Sofa piping, cushions, rug borders and bed linen add detail.
- Prints are narrower inside their wall bays. A projection regression covers the
  studio's apparent overlap with adjacent window sills, which ground clearance alone
  did not catch. Anchors, collision and interaction positions are unchanged.
- Night shade is applied to the outdoor ground before furniture and to whole outdoor
  sprites. Tall parasols are no longer cut by the floor's indoor/outdoor mask;
  interiors retain their illumination, labels stay legible and lamps have warm pools.
- Shadows are composited behind completed artwork. This fixes a strict opaque-mask
  pixel mismatch without relaxing the browser oracle.

Detail remains cached and finite: no per-object private data enters public texture
keys, obsolete night textures are freed on phase changes, and no LLM, quota,
translation, persistence or backend authority path is changed.

### Validation and limits

The all-place visual matrix includes fourteen zones plus explicit pond and vegetable
bed views. The three-engine world matrix passed 59 cases with four declared
engine-specific exclusions; nine stricter pixel/object cases passed again after the
seat-height correction. Final art captures and the final test record are retained
in the worktree's ignored evidence directory.

Measured decoded texture totals after visiting every place and far zoom were
91.2 MiB by day and 95.4 MiB by night on Chromium/Firefox; WebKit measured 91.2 MiB
and 92.4 MiB. These stay below the browser test's 128 MiB ceiling and do not include
heap/compositor/driver allocations. Physical Pi and phone hardware remain unqualified.

Tests use a separate QA web container and hermetic API fixtures through a local
loopback proxy. They do not sign in to the owner's public preview or take its
controller. Missing cross-stack source fixtures in the first coverage attempt were
supplied verbatim; no application path was bypassed. The next full suite passed all
tests but missed the global line floor by 0.02 points. Focused lighting contracts
were added and their four coverage axes are now ratcheted at 100%; no floor was lowered.

Artistic acceptance remains the owner's. This pass improves the existing stylized
scene; it does not claim that every weather effect, physical device or possible
visual defect has been certified.


The final complete coverage run passed 1182 files and 14261 tests, with four
pre-existing skips; global line coverage measured 87.04% and every configured floor
passed, including all four lighting axes at 100%. This run precedes only the final
narrower-print correction, whose failing projection test was reproduced before
correction and whose final world-unit and browser replay are recorded separately.
The existing React act warnings and intentionally simulated error logs remain in
the raw evidence rather than being suppressed.

Frontend application/E2E type checks, ESLint and accessibility/hooks/complexity
ratchets passed. No existing tolerance was relaxed. The documentation preview audit passed
with zero broken links and zero living orphans; historical roadmap warnings remain
unchanged.


After the last frame correction, all 293 world tests (62 files), application
TypeScript and world/E2E ESLint passed. Nine pixel/object cases passed across the
three engines, followed by new Chromium captures of every place by day and night.
The final studio view was inspected directly to confirm the visible window gaps.
The fourteen product source files were published to the existing preview container,
verified byte-for-byte against the reviewed worktree, and its public URL returned
HTTP 200. A rollback source archive is retained. No account/controller was automated
on that preview.

Both g21-only QA containers were gracefully stopped and removed after evidence preservation. No image or volume was created for this pass; reused images and shared dependency volumes remain. The public preview returned HTTP 200 again after cleanup. The two earlier kernel-stuck containers documented above were not force-removed.


## Rectangular house, garden and HUD refinement (g22)

The shared house now fills one rectangle. The gym, meeting and divination rooms
and the eastern rooms meet its edges; the full front width leads onto one continuous
terrace. The remaining three sides have grass belts and planted trees. The private
studio remains separate, connected by its existing garden path. The scene revision
changes with the collision catalogue, so an older client must reload before rejoining.

The jukebox has a solid upper-wall bay in the cafeteria. The isolated knowledge
shelf joins the back-wall group without obstructing the gym door. Recent calls is
placed between the phone-room windows. Divination now has a contrasting lounge,
rug, side tables, task lighting and plants; the enlarged meeting room has its own
small lounge. Door approaches, arrivals and seat exits remain traversable.

The garden gains bounded tree families (broadleaf, conifer, birch and blossom),
trunk details, low flower groups, additional terrace seating, a curved pond bank,
shallows, submerged detail and two slow fish. The surrounding pond lawn reuses
the terrain painter; physical water cells remain impassable while the curved
surface owns their visible water. This avoids the blue tile edges discovered in
the enlarged visual review. Rain uses two depth layers and finite world-anchored
splashes, skips sheltered positions and respects reduced motion. No animation
allocates persistent particles or calls a model.

The desktop HUD groups named device widgets on the left, actions into a lower
dock and camera controls above it. Settings stay separate from native activities.
The phone badges, private inbox, native feature flags and translated labels are
preserved. Touch layouts retain their compact controls; new checks include tablet
widths and an enlarged font. This is an incremental HUD improvement, not a claim
that the entire mobile interface has been redesigned.

### Evidence and corrections

- The complete frontend suite passed 1185 files and 14272 tests, with four existing
  skips; global line coverage measured 87.30%. All configured floors passed.
  Subsequent work only changes the pond's cached underlay selection and adds the
  measured precipitation/tree ratchets; the final narrow replay is recorded below.
- The final world-only suite exercises 303 tests across 65 files. New contracts
  check a filled building rectangle, terrace extent, tree belts, accessible relocated
  objects, finite precipitation and cached artwork bounds at every quality ratio.
- Backend world unit tests passed 133 cases. Real disposable PostgreSQL/Redis
  integration passed 56 cases, including socket admission, reconnect, FIFO capacity,
  message paths and scene migration.
- Browser qualification on Chromium, Firefox and WebKit passed the 74-case world
  matrix with four engine-specific exclusions. Fifteen further cases cover all-place
  day/night inspection, tablet/enlarged-font layouts and actual rain pixels at every
  quality. Six all-place captures were repeated after the detailed bank correction.
  The final underlay-only replay and source parity are recorded below.
- All fourteen zones, pond and vegetable garden were inspected in actual browser
  captures at play and detail zoom, by day and night. The decoded texture readings
  after visiting every place remained below the existing 128 MiB browser ceiling.
  These figures exclude browser heap, compositor and driver memory.
- Full ESLint, accessibility, hooks and complexity ratchets, application/E2E
  TypeScript and six-language key parity passed. Existing hooks warnings are held
  by their unchanged ratchet. Precipitation and tree geometry now have measured
  100% coverage floors on all four axes; no threshold was relaxed.

The integration replay found a real account-erasure defect predating this visual
iteration: the cleanup scanner only recognized unversioned runtime keys. It now
selectively removes actors and waiters from legacy and versioned states without
touching peers, socket leases or connection counters. Regression tests cover both
historical and current scene revisions and malformed/non-state keys. The socket
harness also stopped hard-coding the first scene revision.

Initial test failures are retained in the evidence: missing disposable environment
configuration, a stale socket fixture, the erasure defect, and a transient existing
meeting-recorder test failure (its isolated replay and subsequent complete runs
passed). Coverage initially missed the unchanged floor; meaningful bounded-geometry
tests closed that gap. Existing React act warnings and intentionally failed
notification streams in the inert Firefox fixture are not suppressed.

All work remains inline in the external worktree. The public preview is only
updated with reviewed product sources and the matching backend catalogue; tests
use separate containers and inert accounts. No LLM prompt, provider call, quota
rule, private context projection or production deployment is introduced here.
Physical Raspberry Pi, phone GPU, battery and thermal behavior remain unqualified.
The captures support visual review; aesthetic acceptance remains the owner's.

The final underlay correction passed all 303 world tests, application TypeScript
and world ESLint. Fresh Chromium captures of every place passed by day and night,
and the pond close-up was inspected again to confirm the tile-edge removal.
All 25 changed frontend product files and three backend files were published to
the retained preview and verified by SHA-256 against the worktree. The restarted
owned API reported successful startup without a traceback; the preview URL returned
HTTP 200. A source rollback archive was saved before publication. The public
preview's accounts and controllers were not automated.

Documentation preview and fact audits pass with no living broken links, stale
code paths or orphans; inherited historical/roadmap warnings remain. Backend
type checking passes for both modified modules. The final measured texture totals
are 100.0 MiB by day and 104.2 MiB by night on Chromium.

The six g22-only QA containers and their two exclusive anonymous data volumes were
gracefully removed after evidence preservation. No new image was built; shared
images and dependency volumes were retained. The public preview remained HTTP 200
after cleanup. The earlier kernel-stuck containers documented above were left
untouched, and no main-branch checkout, index, commit or production deployment was
modified by this iteration.


## Compact native widgets and person conversations (g23)

The [accepted implementation plan](../plans/2026-10-25-world-compact-interface.md)
keeps the scene primary and reuses native LIA controls. This iteration remains
strictly inline in the external worktree.

### Delivered behavior

- The phone always offers Call and, when enabled, the native SMS archive.
  Its ephemeral inbox preserves distinct SMS/reminder badges and account fences.
- The voice widget reuses spoken comments, delegated Live and direct Live with
  native connector/capability checks and microphone exclusivity. Its embedded
  handoff opens the actual chat, not LIA's action menu. Queued Live intent is
  bound to the requesting owner and rejected after an account switch.
- The native theme control is shared with the header. An observer of the existing
  OLED DOM writer keeps both mounted controls synchronized without another store,
  notification transport or duplicate preference write.
- The primary actions form one compact row. Place and peer discovery move into
  the Functions menu; settings remain separate. Widgets flow beneath the actual
  heading height. Short landscape folds them into one accessible action with
  outside-click and Escape dismissal; touch targets remain available.
- Messages have a person directory, safe previews, separate unread counts,
  reading positions and drafts. Opening the directory reads no conversation.
  Wide docks show a sidebar; phones show list/detail navigation. Busy or uncertain
  operations cannot be retargeted. Departed history and addressed drafts remain
  accessible; renamed and homonymous people do not merge by alias.
- Home editing now exposes colour swatches with preview, save, cancel and
  conflict/reload handling. Memory/interest furnishing and motif editing are
  retired. Legacy documents remain readable, GET never rewrites them, and new
  saves normalize the legacy fields. A real SQL trace asserts that home loading
  selects neither memories nor interests. No migration or model call is needed.

### Verification

The complete frontend suite passed 1,186 files and 14,285 tests, with four existing
skips. Its measured statement/branch/function/line coverage is
85.74 / 80.55 / 84.08 / 87.27 percent. All configured floors pass. The subsequent
ratchet-only increase for conversation projection is checked by a focused replay:
100 / 96.77 / 100 / 100 measured, with a two-point branch margin. Both colour
projection modules are measured and ratcheted at 100% on every axis.

Backend world unit and real PostgreSQL/Redis integration pass 176 tests.
Native browser flows pass bilingual delivery, recoverable translation failure,
interrupted reads with retained drafts, account-switch withdrawal, reciprocal
free text, reload and a lost acknowledgment without duplicate delivery. Home
save/cancel/conflict and private text are also replayed on Firefox and WebKit,
including mobile accessibility scans. Those flows use disposable SQL, Redis,
cookies and independent browser processes; supplier translation remains inert.

The hermetic UI matrix passes 29 cases across Chromium, Firefox and WebKit,
with four explicit audio-automation exclusions; three further voice-menu cases
pass on all engines. These verify actual Call/SMS panels, theme cycling, native
voice choices, per-person unread/draft selection, colours, settings separation,
touch rotation, enlarged text and control hit testing. Native Live start reaches
the deliberately refused session POST on Chromium, before a provider or microphone
call. Firefox's headless audio warmup did not complete in the initial run; actual
audio qualification is kept at the repository's existing Chromium-only boundary.
The voice menu and spoken preference are independently tested on every engine.

Static checks cover application and E2E TypeScript, ESLint, accessibility,
hooks/complexity ratchets and six-locale parity. The complexity and accessibility
regressions found during review were removed by controller/view separation and
explicit radio labels; no ceiling or tolerance was raised.

### Review findings and limits

Actual screenshots were inspected on desktop, small portrait and short landscape,
including dark mode. The review corrected unread-badge overflow, enlarged-heading
overlap and a folded toolbar positioned relative to the wrong containing block.
The broader coverage run initially lacked current QA assets and release metadata;
these were supplied verbatim, without changing product code to fit old fixtures.
The native scroll scenario now supplies enough real text to require scrolling in
the more compact layout. Repeated proof logins preserve older public identities;
the harness explicitly chooses the current online person rather than guessing
from a reused alias.

Existing React act warnings and intentionally failed inert notification streams
remain in the logs. Physical phone/Pi performance, microphone permissions, audible
provider output and linguistic fidelity are separate acceptance steps. No paid
call, SMS, translation or Live supplier session is triggered by automation.
No universal edge-case coverage or aesthetic perfection is asserted.


### Publication and resource handover

The reviewed overlay contains thirty frontend product files and two backend
modules, plus deletion of the obsolete motif-move component. Their published
SHA-256 values match the worktree. Source rollback archives were saved first.

During publication the retained preview services were found stopped with the
same shutdown timestamp. Only their four existing containers were restarted.
The API used its verified saved disposable environment, preserving its database
and cache volumes; no application instance secrets were substituted. API startup
completed and the preview URL returned HTTP 200. No preview account, admission
or controller was automated.

The six g23-only QA containers were removed after final browser/coverage evidence
was archived. The two historical stuck containers were also now stopped, had
confirmed task ownership and no mounts, and were removed without forcing them.
The two exclusive g23 anonymous data volumes were removed. Shared dependency and
certificate volumes, borrowed images and the four retained preview services remain.
No global prune, shared-engine restart, main checkout change, index mutation,
commit or deployment was performed by this iteration.

### Delivery self-review

Each item in the accepted compact-interface plan is implemented and verified
within its stated boundary. Privacy, stale-owner intent, unread isolation,
recipient identity, native quota ownership, responsive controls and cleanup were
reviewed separately from unit-test totals. No new prompt is introduced.
The remaining acceptance work is physical-device/audio-provider qualification
and the owner's assessment of the interface; those limits are not represented
as passing simulations.


## Preview bootstrap recovery (g24)

The owner reported that selecting the French visitor did nothing after the g23
runtime restoration. A fresh browser reproduced the failure: server-rendered
buttons had no React handlers, no session request left the page and Next rejected
the development WebSocket from the bound loopback address. The manually restored
web process had omitted its allowed-development-origin setting.

Restoring that exact hostname made the client interactive. The real chooser
journey then exposed a second restoration defect: the API had received a
dotenv-quoted JSON origin list through Docker's raw env-file loader. Literal
quotes reached the effective origin list, so the session POST returned forbidden.
The runtime now uses its original exact allowlist in comma-separated form.
The saved disposable environment was corrected in the same way; account/session
secrets, data volumes and application security checks were preserved.

The actual French visitor click now reaches the pseudonym/consent form. The
native regression journey passes six cases: French desktop and English phone
viewports on Chromium, Firefox and WebKit. Requests are real; it checks successful
session creation and the HttpOnly cookie while asserting zero world tickets.
It never takes over a player's controller or invokes a paid provider. Red runs
record both the unhydrated chooser and the forbidden session before correction.

The prior HTTP-only publication check was insufficient to establish usability;
the [preview runbook](../../technical/WORLD_PROTOTYPE.md) now requires the chooser
journey after a runtime restoration. No business-code change, new dependency,
image, container, volume, database migration or production deployment is needed
for this correction.
