# World V1 — qualification and inline cold review

Implementation sequence: [V1 plan](../plans/2026-10-23-lia-world-v1.md).

## Lot 1 — navigation and animated LIA

The POC is not accepted final art. This unit corrects movement orientation,
pinch-to-drag continuity, automatic camera following after manual movement,
minimap orientation, preview viewport overflow and permanent HUD clutter.
Material seams, original foliage, authored furniture clusters and cutaway beam
details were refined. The assistant is named **LIA** in all six world locales.
Its directional BIP-identity atlas uses the existing native EyeRig and mouth
geometry, with one world-owned clock and a deterministic failure fallback.

Preview published to <http://localhost:3002/world-preview?lot=navigation-lia>.
HTTP 200 and the running container's atlas-renderer source digest were checked
after publication. Candidate work continues separately on port 3004.

Fresh checks:

- 51 targeted frontend tests passed. The final model change (LIA faces the
  caller at rest) then passed its affected model/atlas selection: 15 tests.
- Full frontend coverage run: 14,002 tests in 1,128 files passed. Aggregate
  statements 86.87%, branches 81.33%, functions 84.79%, lines 88.38%; all
  configured floors passed. The last model change was verified by the targeted
  run above, rather than attributing the earlier aggregate to a later edit.
- `task lint:frontend` passed after the final model change, including strict
  nonincremental TypeScript and all three ratchets. Two new art hotspots were
  removed, not added to a baseline. The new pure direction/minimap modules now
  belong to the existing scoped coverage floor.
- Final hermetic Docker browser run: 59 passed, 4 intentional exclusions,
  zero unexpected/flaky outcomes. It covers Chromium, Firefox, WebKit,
  keyboard/touch, focus, graphics failure recovery, repeated ownership changes,
  network isolation, six-locale header geometry and axe (zero violations).

Adversarial findings fixed: ordinary lost-pointer-capture cancelled the other
finger; walking after camera exploration could leave the actor offscreen;
the preview had page scroll; minimap axes differed from the main camera;
secondary controls obscured mobile play; the flat robot had no directional
identity; a fixed-delay Firefox oracle sampled the actor mid-route. The latter
now waits for observed rest without enlarging the timeout. Private account
data and paid calls remain absent from this development preview.

Measured limits: [browser evidence](assets/world-v1-lot1/browser-evidence.json)
reports headless Docker measurements, not physical device or Pi acceptance.
WebKit and CPU-throttled mobile remain below the intended smoothness target.
Art finish, real social/private functions and minimum-device qualification are
still required. Passing these checks is not final visual acceptance.

## Server foundation in progress

The isolated Redis campaign passed four real-infrastructure scenarios: twelve
concurrent workers preserve five admissions and one epoch; takeover fences old
movement/releases; tickets consume once and bind the browser cookie; corruption
does not create a local fallback. The pure authority/protocol corpus is also
being extended. These are not yet passes of a complete authenticated world.

One design refinement replaces a process simulator/leader with serialized Redis
transactions: each bounded movement intent commits under the account controller
fence and current world epoch. Workers own only connections and projections.
This removes competing simulator ownership without introducing a process-local
fallback. Pi load and reconnect behavior remain required empirical gates.

World is governed by the native operator capability switch as well as its
deployment flag. It is deliberately off the assistant capability constellation:
it presents existing functions and has its own dashboard entry; home decor is
not a second configuration of those functions.

## Lot 2 — native shared authority

Usable native preview: <http://127.0.0.1:3005/fr/world-preview?shared=1>.
It uses six inert accounts in an isolated, fully migrated PostgreSQL database
and a separate Redis on an internal network. The normal application entry never
loads the proof host. No developer account, provider credential or paid call was
used. Port 3002 remains the previous qualified renderer snapshot.

Fresh behavioral evidence:

- Backend world/native-capability/account-deletion selection: 293 passed.
  Real Redis concurrency, real SQL account/block/session policy and real ASGI
  socket transport are distinct oracles; the ASGI transport's policy double is
  explicitly not presented as SQL proof.
- Native BFF browser flow: passed on Chromium, Firefox and WebKit, no retries.
  Five independent accounts enter one epoch; the sixth sees a queue without
  participant data. Remote movement, explicit duplicate-tab takeover and FIFO
  offer acceptance work. Six account languages render their native controls.
  The 390px scan reports zero WCAG A/AA violations, no page errors, no unexpected
  external requests. Fonts are the repository's fixed offline fixture.
- Frontend world selection: 66 passed; four additional hook lifetime tests
  passed (late ticket, account switch, wrong-account ticket, StrictMode disposal).
- Updated protected shell/SPA ownership journeys: seven passed, two intentional
  engine exclusions; the unchanged canvas/input selection passed fourteen cases
  separately. The final world/navigation/mobile/FAQ selection passed 226
  tests in 26 files. Detached canvas buffers shrink to one pixel across repeated
  navigation. The inert shell socket does not stand in for native multiplayer.
- Strict world MyPy: 13 source files passed. Runtime domain-cycle and logical
  file-size guards: twelve passed. The frontend complexity baseline was held
  by extracting the shared effective-availability predicate, never increasing it.
  `task lint:frontend` subsequently passed every step, including strict tsc.
  The final backend selection passed 295 tests; native deletion-port wiring and
  environment-template checks passed a separate 21-test selection.

Cold review closed: arrival overlap, delayed walking-stop, grapheme-safe alias
clipping, locale handoff, invalid generic-span ARIA, bounded Redis claim release,
malformed/stale scene refusal, and a deactivated account's stale re-entry.
Tickets now join native account-key cleanup. Shared presence uses a selective
CAS purge behind an installed lifecycle port, avoiding a users/world import
cycle. Short SQL owner locks fence admission against deactivation/deletion;
movement does not take a SQL transaction. Native client-IP resolution is reused.

Qualification did catch failures; they were not hidden with retries or enlarged
timeouts. One shell run used an unsupported development-HMR hostname, then the
supported loopback target; a later shell run detected the removed menu import,
which was restored and the affected seven journeys replayed successfully.
Physical Pi/mobile performance, final visual quality and later V1 lots are
still unqualified. Whole-project final gates remain required at F8.

## Lot 3 — private home

Usable preview: <http://127.0.0.2:3006/fr/world-preview?shared=1>.
The previous ports remain frozen. This preview uses a separate API process,
namespace and inert accounts on the owned SQL/Redis infrastructure. Its
loopback binding isolates its cookies from the previous preview and main app.

The nullable owner preference document is migrated natively, exported and
scrubbed with account data. Saving uses a short native owner row lock and
expected revision. Manual palette/motif choices persist; bounded read-only
preference memories and active interests suggest coarse catalogue motifs.
Source text/IDs are absent from the response and persisted layout. Forgotten
sources disappear on refresh without changing manual choices or memory usage.
Unreadable stored versions require an explicit reset; GET never overwrites them.
No model, embedding, provider lookup or learning write is used.

Six fixed furniture anchors support local preview, move/replace, save, cancel
and defaults. Automatic motif suggestions can be switched off independently
of the profile palette. Existing interests remain readable with notification
or extraction switches off, following native semantics. The owner's memory
preference and home suggestion opt-out are enforced. Home art changes no
collision footprint and never enters another account's world projection.

Fresh evidence:

- 119 backend behavioral tests passed against disposable SQL/real Redis and
  the unit/account data map/deletion corpus. Strict MyPy passed 15 world files.
- 87 frontend world tests passed in 18 files. The pause regression was replayed
  after decomposition: seven lifecycle tests passed. Pausing local input keeps
  applying remote movement/visibility projections.
- [Native browser matrix](assets/world-v1-lot3/native-three-engines.json): six
  tests passed on Chromium, Firefox and WebKit, zero retries. Real save,
  atomic motif movement, no-write cancel, concurrent-edit conflict/reload,
  cross-owner isolation, generic private 422, phone axe and landscape footer
  reachability are covered alongside the five-plus-one multiplayer journey.
- [Desktop](assets/world-v1-lot3/home-desktop.png),
  [phone](assets/world-v1-lot3/home-mobile.png) and
  [landscape](assets/world-v1-lot3/home-landscape.png) were inspected visually.
  These are development captures, not final art acceptance.
- `task lint:frontend` passed with the original per-file a11y, hooks and
  complexity ratchets and non-incremental TypeScript. The observed runtime
  complexity regression was fixed by decomposition, never by raising a cap.

Cold review found and fixed the Firefox native-select Escape/draft loss,
missing close-focus restoration, a footer falling below short viewports,
obsolete save closing a newer edit, duplicated automatic/manual motifs and
shared projections freezing while editing. Browser inspection also exposed
missing field names and the preview loopback HMR allowlist; both were corrected.

One targeted pytest invocation accidentally activated the repository's whole
backend coverage floor: its 118 behaviors passed, but aggregate coverage failed
because only the selected files ran. This is not a coverage pass. The final
119-case behavioral selection used the repository's fast-test convention
(`--no-cov`); the unchanged whole-project coverage gate remains required at F8.
Physical Pi/phone and final professional art remain unqualified.

## Lot 4 — private native functions and LIA

Usable preview: <http://127.0.0.3:3007/fr/world-preview?shared=1>. Previous
qualified previews remain frozen. This preview has its own API process, namespace,
loopback cookies and six inert accounts. It uses the ordinary API routes without
starting an agent graph or loading provider keys: LIA's native offline state is
expected there, and no paid provider result is claimed.

The existing settings inventory and gates provide the place/transverse catalogue;
administrative sections are excluded. Opening an activity pauses local walking
while remote projections continue. The selected native panel is removed when
account/world authority disappears. The shared chat workspace retains history,
SSE, active-run recovery, approvals and cost visibility. Embedded mode ignores
the host URL's intents and initial-message fields, including their consumption
ledger, and never implicitly submits a message.

Fresh evidence after the final loading optimization:

- 85 settings registry, pane and asynchronous ownership tests passed. All native
  section identities/props remain checked; loading memories imports no admin panel.
  Late or denied module loads cannot replace the current panel.
- [Native three-engine result](assets/world-v1-lot4/native-functions-lazy-three-engines.json):
  three passed, no retries. Real private memory read/pin and SQL confirmation,
  denied foreign mutation, embedded no-send, mobile axe and reachable 44px HUD/close
  controls passed on Chromium, Firefox and WebKit.
- [Ordinary settings and HITL browser matrix](assets/world-v1-lot4/settings-hitl-three-engines.txt):
  99 passed on the same three engines. Native fixtures cover pending approval,
  explicit cancel/typed reply, stale approval, egress/mailbox choices, rail/deep-link
  navigation and mobile interface behavior. Fixtures do not prove provider fidelity.
- `task lint:frontend` passed: a11y zero, inherited hooks ratchet unchanged,
  complexity shrunk from 39 to 38 hotspots with the maximum unchanged. Strict
  frontend and complete E2E TypeScript checks passed. Six-locale parity passed
  earlier in this lot. The final whole frontend replay subsequently passed
  14,051 tests in 1,140 files with four workers; no thresholds were changed.
- Updated [desktop](assets/world-v1-lot4/native-memory-desktop.png),
  [phone](assets/world-v1-lot4/native-memory-mobile.png) and
  [LIA phone](assets/world-v1-lot4/native-lia-mobile.png) captures were inspected.

Cold review found and corrected memory metadata contrast on a pinned row, mobile
toast obstruction of Close, lost intent isolation, and a heavy eager module load.
The real Firefox run exposed that last issue; it was not hidden by a larger timeout
or retry. The native entry chunk fell from 7,941,400 to 420,616 development bytes,
below the new 512KiB browser budget. Native settings now load one selected panel
through their shared registry; the world frame avoids the full icon table/error
barrel. Extracted pane timing constants remain exported for existing consumers.

Final art, private atmosphere, direct text/translation, minimum physical devices
and the full mixed-load acceptance are still outstanding in F6–F8.

## Lot 5 — private direct text and translation lifecycle

Usable preview: <http://127.0.0.4:3008/fr/world-preview?shared=1>. F5 remains
available on its frozen host. Older POC/F3 containers were paused, preserving
their files, to release development memory. The social host has distinct inert
accounts, namespace and cookies. Its banner explicitly identifies an unbilled
authored phrase translation fixture; other cross-language text fails honestly.

The new private HTTP surface requires native session/account/operator authority,
the controlling world tab, current epoch, live leases and mutual block policy.
No body, account identifier, language or billing receipt enters public snapshots.
Same-language sends make no model call. Cross-language sends and recipient-owned
explicit retranslation use the dedicated configurable slot, native spending guard
and token callback. Strict JSON output, bounded transport/deadline, a small FIFO,
two-phase dispatch and durable attempt tombstones prevent implicit paid retries.
Receipts belong to the payer; native SQL accounting also persists refused output.

Fresh evidence:

- The consolidated World backend selection passed 156 cases. Subsequent focused
  replays passed the two additional deadline cases and four additional in-flight
  revocation cases. The final messaging selection passed all twelve cases,
  including native SQL token records on valid and refused model output.
- All 108 World frontend cases passed. Behavioral regressions demonstrate retained
  owner drafts through reconnect, account-switch aborts, no automatic resend,
  literal markup, hidden originals, bounded polling and recipient-owned translation.
- [Native three-engine result](assets/world-v1-lot5/native-three-engines.json):
  three passed, no retries. Real BFF/session/SQL/Redis sends, translated-before-display,
  third-account isolation, literal unsafe markup, failed translation, phone axe,
  short landscape controls and close-focus restoration passed.
- [Desktop](assets/world-v1-lot5/messages-desktop.png) and
  [phone](assets/world-v1-lot5/messages-mobile.png) were inspected. The fixture
  translation and development indicators are not final product presentation.
- Full `task lint:backend` passed, including MyPy across all source files.
  Full `task lint:frontend`, E2E strict TypeScript and six-locale parity passed.
  A11y remains zero, inherited hooks unchanged, CC remains 38/max 46. No cap rose.

Cold review found and corrected premature dispatch before acknowledged staging,
cache corruption reflection, mutation validation, participant projection bypass,
cleanup using the session Redis instead of the world cache, client-ID cleanup-key
impersonation, indefinite pending status, lost drafts and unnecessary full-rate
painting behind private panels. The economic render cadence now keeps fractional
frame time. A failing simulation measured 149 paints over irregular ticks where
186–190 were expected; the corrected behavioral oracle passes. Shared simulation
continues while panel rendering is capped. WebKit qualification activates the real
foreground page; background state is not treated as a foreground interaction.

No physical Pi/phone, supplier linguistic fidelity or final professional art claim
is made. Whole-project coverage and mixed-load acceptance remain F8. The parallel
main correction is now committed as `7777d13c4`; integration must reparent the home
migration behind `213b9ac595c5`, replay the migration chain and align only the owned
proof database. The main development database must not be migrated by this work.

## Lot 6 — native catalogue, private atmosphere and responsive presentation (F7)

Qualified preview: <http://127.0.0.5:3009/fr/world-preview?shared=1>.
The previous social host stays frozen. The collapsible proof guide identifies
inert accounts, authored translation and fictional weather; these are not claims
of provider quality. The world still exceeds the viewport, with camera movement,
zoom, minimap and native LIA's eyes and mouth on the original directional body.

The catalogue derives localized search, available settings, application links and
prepared actions from their native inventories. Canvas `E` shares the place
action without intercepting text entry. Peer vignettes are private and bounded;
unknown native application presence is stated honestly, and visible live avatars
suppress duplicates. Cached atmosphere uses account timezone/server time and no
provider or ambient model call. A redundant floating companion is quiet while its
notification receiver stays alive and exposes unread/working attention.

Fresh evidence:

- [Twelve native journeys](assets/world-v1-lot6/native-three-engines.json) passed
  across Chromium, Firefox and WebKit, with no retry: home save/conflict,
  owner-only native memory edit, ordinary LIA without implicit send, private text,
  catalogue composition, paginated peers, foreign-controller denial, cached
  weather isolation and reachable phone/short-landscape controls with axe.
- 148 focused frontend cases passed. Three real SQL/Redis integration cases
  passed for accepted-directory filtering, live-duplicate/block policy and
  private cached environment projection. E2E strict TypeScript passed.
- Full backend lint/type checking passed. Full frontend lint/type checks and all
  existing ratchets passed; the final ticket-lifetime change additionally passed
  its behavioral suite and scoped hooks lint. No ratchet increased.
- [Desktop](assets/world-v1-lot6/desktop.png),
  [phone](assets/world-v1-lot6/mobile.png),
  [landscape](assets/world-v1-lot6/landscape.png),
  [peers](assets/world-v1-lot6/peers.png) and
  [native prepared action](assets/world-v1-lot6/native-action.png) were inspected.
  The guide no longer consumes a paragraph of phone scene height.

Cold review reproduced and fixed an old-account environment surviving a switch:
the new query dependency aborts its request and the owner tag hides it immediately.
It also reproduced two ticket requests for a StrictMode setup: only the surviving
microtask now starts transport, preserving the native rate limit. A route left
before setup spends no ticket. The mixed browser matrix caught an incorrect
gallery-test assumption about reconnect leases; all authored non-playing peers
are now checked exactly once while actual live actors retain duplicate suppression.

This establishes functional and browser presentation evidence. Physical hardware,
real translation fidelity and owner approval of final art remain separate from
automated qualification. F8 now integrates current main in this worktree, verifies
migrations and the full gates, and measures the bounded mixed workload.

## F8 qualification — direct-conversation regression (in progress)

Current interactive preview:
<http://127.0.0.6:3010/fr/world-preview?shared=1>. Earlier preview hosts are
historical evidence, not a promise that their containers are still running.
Use visitors 1 and 7 for arbitrary French text, in separate browser profiles or
devices. A browser's tabs share the native HttpOnly account cookie. Cross-language
proof translation remains limited to the authored phrase stated by the guide.
This limitation does not describe the production translator's supported input.

The reported symptom was an accepted message absent from the other person's
view. Investigation reproduced an account-cookie change leaving the previous
private conversation visible while HTTP already authenticated another account.
The world now rechecks native identity on focus/visibility and after a private
401/403, withdraws private portals while verification runs, and destroys the old
owner subtree on a confirmed mismatch. Recoverable verification retains the
owner draft. Server authority and foreign-controller rejection remain enforced.

The expanded conversation journey also reproduced a missing path back to arrivals
while reading history, and a viewport resize leaving the log above the latest
message. The localized latest-messages action restores keyboard focus; resize
observation follows the bottom only when the reader has not scrolled back. Its
behavioral regression failed before the correction and passes afterward, including
observer teardown. The real-browser journey exercises scrolling, an incoming
message, reload, mobile layout and focus restoration together.

Qualification is isolated from the interactive preview: separate native SQL
database/role, newly generated signing/encryption keys, separate session/cache
Redis databases and a separate optimized frontend snapshot. No interactive
session secret is copied to the host. Test identities retain ordinary native
cookies, admission, controller fences, message storage and rate limits. Distinct
people use independent browser processes; the deliberate account-switch case
alone shares a browser context. Cleanup explicitly leaves each controlled tab
before closing its shared context. Rapid fixture reuse reached native 429 limits;
the limits were not increased or bypassed to obtain a passing result.

The initial full backend replay completed: 5,342 integration cases passed, followed by
four co-located integration cases and two explicitly POSIX-only skips. Combining
the preserved unit and integration measurements produced 87.41% line coverage.
The canonical changed-line guard measured 1,759 of 1,914 lines covered (91.90%).
That guard was read from the concurrent main checkout with an explicit isolated
worktree root; its digest was unchanged before/after and main was not edited.
The worktree's older Taskfile does not contain that new union/diff task, so this
is equivalent measured execution, not a claim that the missing task ran here.

Cold review reproduced three more lifecycle defects: same-owner verification
destroyed a catalogue query, a resumed Radix select cleared an unsaved home motif,
and Chromium returned keyboard focus to the dialog's first control. Private
Activity boundaries preserve the actual editor state, the shared controlled
select ignores the transient empty native event, and owner verification restores
the preceding field without taking focus from another surface or document.
Behavioral regressions failed before correction. A healthy, hermetic LIA replay
then passed all six journeys across the three engines, including unsent draft,
keyboard focus and explicit pending-approval cancellation. No implicit prompt was
sent. The additional background-focus guard is also covered before final replay.

An overlapping compiler/coverage/native run produced timeout failures. They stay
in the local evidence and are not counted as passing qualification. The focus
unit oracle now controls the animation frame explicitly instead of racing a
real frame against test scheduling. Final acceptance runs separate compilation
from browser/coverage execution without increasing deadlines or rate limits.

Further fault injection exposed two real transport-lifecycle defects. Escape on
the automatically displayed session dialog could leave the world, and an HTTP
send could remain `sending` when its WebSocket scope disappeared before the HTTP
response. The session dialog now keeps Escape from implicitly leaving; explicit
leave remains reachable. Known reconnects suspend and restore the private native
panel while permanent loss of authority retains its withdrawal contract. The
mailbox settles a write under its unchanged owner/generation/intent, independently
of a temporary socket gap; disposal and explicit discard still refuse late
completion. Reads retain their strict current-scope projection check.

The new behavioral cases failed before correction. All 143 focused World/select
cases then passed, including refusal to retain authority before admission. A native six-journey campaign across the three engines also
passed: the browser's actual socket is closed after a real accepted send but
before its HTTP response is released, or while a private editor is open. Cookies,
Origin and frames remain native; the probe captures no session material and
does not synthesize server answers. Exactly one send, recipient delivery,
reconnection, retained editor state and explicit Escape behavior are asserted.
The optimized bundle oracle now measures scripts loaded by the explicit native
action instead of depending on a development-only chunk filename. Its existing
size bound is retained; CSS target measurements normalize sub-pixel float noise
without lowering the target.

The admission incident was subsequently reproduced and explained. Redis held 91
abandoned notification Pub/Sub subscriptions in the isolated qualification cache;
the ordinary pool reached its bound and World failed with `MaxConnectionsError`.
Starlette's disconnect cancels the AnyIO scope repeatedly at asynchronous
checkpoints. The former generator cleanup could therefore be interrupted before
closing its pinned Pub/Sub connection. A manual `generator.aclose()` test did not
reproduce that cancellation model.

The notification stream now re-raises cancellation and shields its bounded
cleanup. It frees Pub/Sub before registry writes need another pooled connection;
the native Redis socket deadline bounds cleanup, and stale markers retain their
TTL if registry cleanup cannot finish. The pool and admission limits were not
increased. Two actual ASGI disconnect regressions failed before this fix. The
expanded notification tests passed, including 24 real ASGI disconnects against a
two-connection Redis pool and a registry-write timeout. A native EventSource
campaign passed 72 successive opens/closes across Chromium, Firefox and WebKit,
with zero remaining subscriptions afterward.

The proof host now uses LIA's existing `SecurityHeadersMiddleware`, including its
SSE `no-transform` policy. The missing middleware in the proof host had caused
Next.js compression to buffer small SSE events; no duplicate header policy was
added to the business router. Temporary failure classification was removed and
the native World router's source digest was verified against the worktree.
The cancellation model follows the primary
[AnyIO documentation](https://anyio.readthedocs.io/en/stable/cancellation.html).

The full hermetic replay first exposed five failures under an HTTP Docker
hostname, where `crypto.randomUUID` is unavailable outside a secure context.
Those same five journeys passed unchanged on the loopback origin required by
the existing E2E harness. The internal asset forwarder used for that proof refuses
all real API paths, non-read methods, WebSocket upgrades and CONNECT tunnels.
Neither application security nor assertions were weakened to repair the harness.

The final optimized native matrix passed all 21 journeys across Chromium,
Firefox and WebKit, with no retry, skip or flake. Redis had zero remaining
subscriptions after the campaign. The
[structured native proof](assets/world-v1-lot7/final-native-reconnect.json)
records the tested source digest and every result. The inspected real captures
show the [desktop scene](assets/world-v1-lot7/final-scene-desktop.png),
[phone scene](assets/world-v1-lot7/final-scene-mobile.png) and
[phone conversation](assets/world-v1-lot7/final-conversation-mobile.png).
These captures are runtime evidence, not owner approval of final art.

A full integration replay stalled on a local Windows/PostgreSQL connection during
a bulk fixture insert; the server was waiting for client input. Only that
identified qualification process was stopped. The isolated regression passed on
a fresh Testcontainers database, then the fresh full replay passed the same probe.
The interrupted replay is retained and is not counted as a passing suite.

Final global software evidence is consolidated below. Physical
Pi/phone qualification, sustained thermal/battery behavior, real supplier
translation fidelity and owner acceptance of final art remain unverified.

The [chat cold review](2026-10-24-world-chat-cold-review.md) consolidates the
findings, security/resource boundaries and acceptance limitations of this pass.

The capacity campaign passed on all three engines: five admitted accounts, the
sixth waiting, position agreement, explicit duplicate-tab control and a private
FIFO offer. See the [capacity proof](assets/world-v1-lot7/final-capacity-three-engines.json).
Each person has a separate browser process; only the intentional duplicate shares
its account context. An earlier WebKit run exhausted the aggregate browser-harness
memory while simulating six full devices plus the duplicate. The corrected harness
has room for those independent browsers and reports no OOM. Server admission,
Redis pool and per-user limits remain unchanged. Cleanup preserves an original
failure while attempting to close every test context and browser.

The first complete hermetic run on loopback reported 698 passes and two failures.
One was a harness classification error: the production server was declared as a
development runtime, so an existing development-only HMR assertion ran without
HMR. The final optimized run uses the production contract, with that existing
conditional skip and the strict API/WebSocket guard intact.

The other failure exposed a real accessibility defect outside the direct-chat
panel: message-entry scaling could shrink a target while reduced motion was
requested. A deterministic frozen-first-frame regression reproduced the measured
41.8-pixel target. Adding message entry to the existing reduced-motion opt-out
list retains final geometry immediately. All nine detailed-card journeys across
the three engines then passed without lowering the target size or waiting out
the defect. The fresh optimized build includes this shared correction.

The full backend coverage campaign reached its floor and passed all functional
cases, but one unchanged hostile-text guard exceeded its wall-clock ceiling
under concurrent host load. The exact same case, with the same coverage
instrumentation and unchanged threshold, passed in isolation afterward. Its
original failure remains in the evidence; a fresh complete fast-unit campaign
and the full integration replay are collected separately.

The final rebuilt artifact passed the combined 27 native journeys across all
three engines, without retry, skip, flake or browser-harness OOM. The
[delivery proof](assets/world-v1-lot7/final-native-delivery.json) includes the
post-format production-source digest and normalized global CSS digest. The
interactive preview and optimized qualification source snapshots match. Their
only post-build CSS normalization changed line endings, verified byte-for-byte
after normalizing newlines; no styles changed during the campaign.
The complete official fast-unit suite passed 46,049 cases with 33 environmental
skips. The earlier coverage timing failure remains separately documented.

F8 software qualification is complete. The final global campaigns passed 46,049
fast-unit cases, 14,102 frontend cases, 5,347 integration cases, 699 hermetic
Chromium journeys and 27 native journeys across the three engines. The documented
environmental exclusions remain explicit; there were no browser retries or
flakes. Combining the preserved backend measurements produced
87.41% line coverage, and the canonical
changed-line guard measured 91.90%. The final
[software gates](assets/world-v1-lot7/software-gates.json) and
[hermetic proof](assets/world-v1-lot7/final-hermetic-suite.json) carry the measured
counts. The interactive preview returns HTTP 200 and shares the verified source
snapshot. No production deployment or main-checkout edit was performed.

The final `task lint` completed successfully, including all configured static
checks and shrink-only ratchets. The inherited hook findings remain within their
unchanged baseline. The final indexed-blob Gitleaks scan found no secret.

### F9 — touch HUD and delivery requalification

See the [touch cold review](2026-10-24-world-touch-cold-review.md) for the bounded
HUD changes, failing oracles, preserved ownership boundaries, dependency-harness
repairs and final evidence. Rendering algorithms and backend business source
remain unchanged by this follow-up.

### Artistic continuation

The [art completion plan](../plans/2026-10-24-world-art-completion.md) continues
inline through material, place and character lots, with a usable preview at
each completion. The native V1 contracts and prior qualification remain in force.

### F10: sculpted materials and garden

Bounded cached foliage variants, material-aware floors and shared face lighting
replace flat repetitive surfaces. Native geometry and privacy contracts are
unchanged. World units passed (31 files, 143 cases). Real pixel/silhouette and
six-place camera journeys passed in all three browser engines (6 cases).
Optimized five-client journeys passed in all three engines. The published
preview passed authenticated phone entry and zoom.
[Evidence and measurement limits](assets/world-art-f10/evidence.json),
[arrival](assets/world-art-f10/arrival.png),
[library](assets/world-art-f10/library.png),
[phone](assets/world-art-f10/phone.png).

### F11: architectural and interior detail

Original window joinery, inset panelling, books/pages, furniture seams, fabric,
fountain ripples, three authored paintings and brass tripod optics enrich the
existing footprints. The six-place gallery and pixel oracle passed all engines,
including the complete authorized private motif/palette catalogue. Desktop
walking and phone controls passed all engines before the final creative detail;
the published final source passed authenticated phone entry and zoom.
[Evidence](assets/world-art-f11/evidence.json),
[studio](assets/world-art-f11/studio-final.png),
[observatory](assets/world-art-f11/observatory.png).

### F12: people, night lighting and final qualification

Human faces/clothing rotate with their body; cached walk phases retain complete
silhouettes. LIA retains the native atlas, eyes and mouth. Cached, view-culled
window light complements the personal native night/weather context. A native
Firefox recovery race was reproduced in a failing unit test and corrected:
a confirmed foreign identity stays withdrawn until explicit document reload.

The full frontend coverage suite and canonical frontend gate passed after that
correction. The affected browser matrix uses a fresh fixture per climate and
retains strict error checks. Native qualifications include an exact isolated
replay of one late Firefox capacity timeout; it is not counted as an original
first-pass success. Optimized samples run outside compilation and full suites.
The published preview passed authenticated touch entry, zoom, desktop and phone
captures, with no paid action or authority takeover.

[Final evidence and limits](assets/world-art-f12/evidence.json),
[cold review](2026-10-24-world-art-cold-review.md),
[desktop](assets/world-art-f12/desktop.png),
[phone](assets/world-art-f12/phone.png),
[night](assets/world-art-f12/night.png),
[studio](assets/world-art-f12/studio.png),
[animation sheet](assets/world-art-f12/actors.png).
