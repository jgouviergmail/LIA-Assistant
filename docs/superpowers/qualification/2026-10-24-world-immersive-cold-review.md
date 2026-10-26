# World experience completion — iterative cold review

## G13: qualified and published

This is a bounded repair lot, not final artistic or functional acceptance. The
[execution plan](../plans/2026-10-24-world-art-completion.md) retains the remaining
contextual activities, conversations, poses and art work.

The [evidence](assets/world-immersive-g13/evidence.json) records the actual tested
snapshot, source equality and measurements. Published captures show the
[desktop](assets/world-immersive-g13/desktop.png) and
[phone viewport](assets/world-immersive-g13/phone.png).

### Findings and corrections

- The pointer path used every grid turn and snapped a valid target to its cell
  centre. A bounded coarse search now removes turns only when the entire body
  has collision clearance. Combined keys follow the floor axes. Behavioral
  tests first reproduced the detour and sideways snap, then verified wall/corner
  clearance, exact destinations and invalid/fully blocked destinations.
- Equal movement components could change facing through floating-point noise.
  Client and authority use the same tie tolerance; a real coordinate sequence
  reproduced the server defect before the correction.
- Wall corners lacked one joined side; chairs faced away from their furniture.
  Corner artwork and chair orientation were corrected, including orientation in
  colour/occlusion cache identity. Browser pixels verify masks and unclipped art.
  The generated authority catalogue was updated and its collision bitmap was
  compared with the preceding index snapshot: unchanged.
- Application preferences were mixed into the activity catalogue. An explicit
  settings entry now separates their presentation while preserving the living
  availability registry, native ownership and exclusion of administration.
  Mixed panels and unified world settings remain subsequent work.
- The added HUD action exposed two real layout defects: narrow landscape wrapping
  into the heading/minimap, then touch-tablet overlap with the direction pad.
  A further narrow-phone/enlarged-text probe exposed zoom overflow. The final
  layout reserves the pad, removes the status dot from the short-screen flow and
  keeps icon-only targets and the numeric zoom label bounded. No hit-target or
  overlap assertion was relaxed; the final optimized output passed the extended
  matrix in all three engines.
- The catalogue generator initially could not resolve the newly extracted pure
  route module. Its trusted loader now accepts explicitly declared dependencies
  only; arbitrary modules remain unavailable.

### Verification and provenance

The full frontend suite passed all its tests. Its first coverage run correctly
failed the unchanged world geometry floor after the helper was added: blocked
pointer destinations were insufficiently exercised. Those meaningful scenarios
were added; the complete world suite and the unchanged scoped coverage gates then
passed. The report distinguishes the full test run from this targeted coverage
run rather than labelling the initial coverage failure green.

The initial hermetic matrix found the layout defects above and one Firefox
whole-test timeout under concurrent compilation/coverage. Its unchanged non-touch
journeys passed. Exact affected cases were replayed on successive optimized
candidates; the final extended touch matrix and separate settings journeys pass
in Chromium, Firefox and WebKit. Test-only CSS previews helped inspect the narrow
layout; they are not counted as final compiled-output evidence.

Native SQL/Redis journeys verify private memory read/edit, rejected cross-owner
mutation, LIA without implicit sending, two-account direct messaging, translation
before display, a third account's isolation, failure without resend and mobile
composition in three engines. The final quiet optimized probe uses five native
server clients, one full UI renderer, and desktop/phone/CPU-throttled profiles.
These are browser-emulation measurements, not five physical rendering devices.

Publication uses the task's isolated containers only. A server-process guard
stopped one activation on a terminated zombie process; the guard was corrected
before retrying. Initial publication probes ran before the restarted API was
ready and failed; the later authenticated entry, movement and zoom proof passed
with no account takeover or paid action. The worktree, candidate and published
frontend production sources have matching hashes.

### Security, resource and acceptance review

No new LLM invocation, prompt, token rule, shared-state field, business permission
or persistence model was introduced. Private account guards and native forms
remain authoritative. No profile or message is added to renderer metadata. The
new path calculation is client-side and bounded by the authored navigation grid;
art variants remain cached and disposal stays unchanged.

No unresolved defect was identified within this bounded lot after the corrections
and final replay. The world still needs the subsequent experience/art lots. In
particular, a separated menu is not yet object-driven activity integration, and
fixed furniture direction is not a seating implementation. Physical Pi/low-end
phone capacity and actual supplier translation fidelity remain unqualified.


## G14: qualified and published development preview

This lot adds contextual object/actor entry, private conversation docking and
recipient-bound drafts. It also corrects the owner's reported sideways walking:
human geometry has eight world-space orientations, walking phase follows distance,
and remote actors derive their orientation from actual movement and retain it at
rest. The LIA atlas and native facial rig remain intact. This is not final art
acceptance; the owner's illustrative mock-up is a direction, not copied content.

### Adversarial findings and corrections

- A four-direction artwork could not represent eight-direction motion. True
  rotated orthographic human faces now use the existing bounded sprite families.
  Tests reproduce diagonal orientation errors, including remote motion, and a
  browser pixel sheet checks every heading without clipping or empty frames.
- Actor picking reads the same foreground-masked pixels as drawing. A solid wall
  therefore cannot select a hidden person. Object interaction uses collision-safe
  approach points, rechecks current availability on arrival, expires old intent
  and cancels on manual input, blur, suspension or lost authority. It opens owned
  native panels or an unsent native LIA draft; it does not invoke a model or write.
- Recipient selection previously shared a draft and a global read marker. Drafts,
  reading positions and unread accounting are now scoped to the selected person.
  A departed recipient keeps their draft and alias but cannot receive a send.
- A portal can attach after its parent opens. The dock now measures its actual
  callback ref and cleans up its viewport listeners on detach. The first approach
  mutated a DOM node stored in React state; the strict React ratchet caught it.
  A callback ref with lifecycle cleanup removes that violation.
- Production CSS optimization merged the independent translation reset into
  `transform`, leaving the shared dialog's Tailwind translation active. Explicit
  preservation of `translate` fixes the mobile offscreen panel. Development-only
  evidence did not reveal this defect; the optimized browser suite did.
- Firefox restored history before the resumed private portal had final geometry,
  clamping the position to zero. A regression test reproduced that lifecycle;
  restoration is reapplied once after attachment without recording the transient
  clamp. A separate real-browser measurement established that programmatic
  `scrollTop` quantizes fractional values to CSS pixels. The native assertion
  therefore requires less than one pixel difference, not unattainable decimal
  precision; it still detects the original complete loss of history.
- Five functions exceeded the existing complexity ratchet. Dedicated controls,
  headings, feedback and help components, plus separate actor/object picking,
  restore the original ceiling. No quality threshold was relaxed.

### Qualification boundaries

The native memory journey now selects the shelf in the actual scene, walks from
its courtyard spawn under server authority, reads and pins a disposable owner's
memory, then verifies denial for another account. Its focus expectation follows
that entry point back to the canvas. Native conversations exercise real isolated
cookies, SQL and Redis, including reciprocal delivery, interrupted reads, a lost
acknowledgment, account changes and retained drafts. Translation uses the explicit
inert fixture; supplier translation quality and cost are not inferred from it.

Intermediate failures are retained in the working evidence. Concurrent compilation
caused a whole-test timeout; one replay logged a Redis timeout and a bounded 503,
not a successful delivery. Subsequent qualification runs are separated from build
work. Test changes are limited to the new nonmodal status scope, the scene focus
return and the empirically measured pixel precision.

No new server field, LLM slot, prompt, token policy, shared private context or data
persistence is introduced. The only data passed to scene picking are public actor
identities and authored object IDs. Private panels retain native identity,
availability, quota and HITL gates. The targeted coverage ratchet for contextual
intent is new; existing floors remain unchanged.


### Final G14 evidence

The [evidence manifest](assets/world-immersive-g14/evidence.json) records the scope:
182 world tests in 34 files, the frontend lint/type/ratchet gates, six-locale parity,
an optimized build, and 27 UI cases across Chromium, Firefox and WebKit.
The [native results](assets/world-immersive-g14/native.json) contain 15 distinct
logical cases from the same production sources; the final affected six were replayed
after correcting test assumptions. The full frontend suite was last run at G13.

The quiet [performance probe](assets/world-immersive-g14/performance.json) measured
56.3 fps on the desktop profile, 29.7 on the phone viewport and 25.5 under 4x CPU
slowdown, with five native clients and one full renderer. These are emulated
profiles, not physical device guarantees. The [publication probe](assets/world-immersive-g14/publication.json)
verified entry, walking and zoom without paid actions or account takeover.

Visual review: [published desktop](assets/world-immersive-g14/desktop.png),
[published phone](assets/world-immersive-g14/phone.png),
[desktop conversation](assets/world-immersive-g14/conversation-desktop.png),
[phone conversation](assets/world-immersive-g14/conversation-phone.png), and
[eight human headings](assets/world-immersive-g14/eight-directions.png).
The dock is contained and usable; the scene still lacks the architectural and
material refinement requested by the owner. G15-G17 remain open.
