# World feedback refinement qualification

Scope: the owner's photo, widget, season, catalogue and approached-decor feedback.
Implementation is inline, without subagents, commit, push or deployment. The
[plan](../plans/2026-10-27-world-feedback-refinement.md) records the binding choices.

## Source evidence

RED assertions preceded the photo crop/signature, catalogue/season, arrival,
workout pose/models, fountain trajectory and photo-decor projection changes.
The review added explicit rejected/expired workout, interrupted fishing,
day/night lamp, moving-target and seat-lifetime checks.
Strict TypeScript exposed fixture omissions; these were corrected and the clean
non-incremental type check passed. Existing a11y, hooks, complexity and double-cast
ratchets held; the complexity baseline was refreshed without increasing a cap.

Runtime evidence and final coverage results are retained in the task's
ignored `.superpowers/sdd/2026-10-27-world-feedback-refinement/` directory. The
task-owned isolated preview uses the existing `interactions-01a17aa3` containers
and loopback port, separate SQL test database and Redis test index. No production
or shared development database is used by these tests.

The live development API inspection established a separate workout refusal: its
worker predated the new catalogue and Uvicorn's actual default filter rejected
JSON changes. A behavioral filter test failed on all four development entry
commands, then passed after adding the JSON include. Only the development API
service was recreated; its new command includes that filter and health returned
success. The isolated World suite passed with shared workout occupancy,
serialization and release checks, and the private-bed fixture now selects actual
private-home geometry instead of the first lying slot.

The pond follow-up adds a finite take-rod/cast/wait/reel response. The three
machines use distinct generated sounds, routed by authored object identity.
Existing generated source receipts were reused when adding the two extra sounds;
their charges are not counted twice.

Native verification exposed an additional navigation problem: the four pond
approaches straddled shore-rock cells once the actor radius was applied. A real
cross-campus navigation test reproduced the refusal. Object approaches now use
grid-cell centres; the arcade's authored entry point is retained. The pond,
fountain, billiards and machine approach simulations passed, followed by actual
desktop and phone fishing journeys. No obstacle or collision rule was weakened.

The visual review also found that the HUD still announced decorative actions
and could expose an untranslated screen key. HUD and tooltip labels now share
one policy: decorative targets keep their pointer/footprint affordance, while
functional targets retain their label. Three expected component failures
preceded the change; all four cases then passed, including the Health label.

## Platform boundary retained from the accepted delivery

This Windows host cannot compile iOS or exercise physical Android/iPhone/iPad
share choosers. The owner explicitly accepted finishing here and documenting
those remaining checks. This refinement does not change native bridge code.
Browser engines and responsive viewports do not prove physical-device behavior
or constrained-device performance. The original native validation evidence and
remaining hardware work are retained in the
[previous ledger](2026-10-27-world-interactions-and-play.md).

## Review boundaries

Navigation and lying/standing use existing authoritative contracts; decorative
appearance and sound remain owner-local. No memory, prompt, token accounting,
quota, new endpoint or persistence contract is introduced. Photo projection is
an allowlist and does not capture the live canvas or private context. Audio
receipts retain prompts, provider, measured charges and digests. The owner
authorized eight ElevenLabs generations; their receipts total 126 credits. The key
was read through a masked one-time console input and was not written to the
repository, environment files, logs or process arguments. The eight normalized
files total 98,272 bytes. Superseded local/CC0 receipts are historical only. Playback makes no external request beyond same-origin bounded assets.

Acceptance is limited to measured source, Docker and browser evidence; it does
not claim universal perfection or physical-device qualification.

## Final qualification

| Verification | Measured result |
| --- | --- |
| Complete frontend suite with coverage | 14,989 tests in 1,308 files passed; all global and scoped thresholds passed. The complete run exited successfully after 731.04 seconds. |
| World behavior closure | The World-only closure passed 669 tests before the final five controller cases were added. The full suite above includes those additional cases. |
| World backend unit and integration suite | 491 passed against the task-owned PostgreSQL test database and Redis test index. |
| Development entrypoint and proof/contract guards | 30 passed, including all four real Uvicorn filter configurations. Actual JSON modification also triggered a new development API worker after the reload fix. |
| Final optimized native journeys | 13 passed: all three arcade games with humans and computer, same-account takeover, seated private dashboard/retry, desktop and phone decor, widgets at three widths, and both workout benches. Dashboard data/synthesis use hermetic fixtures; these checks do not bill a model. |
| Photo browser matrix | Six passed across Chromium, Firefox and WebKit, covering zoomed framing, peer exclusion, both JPEG formats, narrow portrait, rotation and focus restoration. |
| Audio browser matrix | Six passed. Chromium and Firefox decoded all 23 active MP3s and passed audio lifecycle checks. Windows WebKit exercised explicit unsupported-audio behavior. Three machine asset requests and three effort cues per workout were also verified during the native decor journey. |
| Static and cross-cutting gates | Frontend lint, strict non-incremental TypeScript, E2E TypeScript, all existing frontend ratchets, catalogue parity, hygiene, CI parity, six-locale parity, docs preview and formatting of refinement files passed. Diff whitespace check passed. |

The first complete coverage run was rejected despite all its tests passing:
several existing scoped floors exposed untested cancellation, presentation,
navigation, permissions and download paths. Behavioral tests closed those gaps.
Existing scoped floors were raised and an interaction-controller floor was
added from measured coverage. None was lowered. The final complete run above
passed the strengthened gates.

The optimized task-owned preview was rebuilt after the final source change.
Source/media/localization manifests match between the checkout and that preview;
the compiled campus catalogue also matches the isolated API. Three machine MP3
digests are distinct. Final close-ups on both benches were inspected at multiple
lift phases: both plate ends are visible and clear of the face. Indoor plants
stay green in the winter captures and decorative action labels are absent from
the final HUD. No known blocking defect remains in the exercised scope.

## Adversarial review

| Area | Evidence and decision |
| --- | --- |
| Authority and races | Shared workouts wait for the actual lying pose. Rejected/expired confirmations, authority loss and bounded failed-standing retries do not fabricate local shared state. Activity callbacks from an old seating generation cannot close the new workspace. |
| Privacy | Photo appearance is reconstructed from authored IDs and finite values. Private board, peer, conversation and dashboard data are not captured. Three-engine native photo journeys exercise peer exclusion and both formats. |
| Navigation | Real routes precede activation. Moving targets are replanned; unreachable or interrupted targets cannot resurrect an old intent. Authored obstacles and actor radius stay enforced. |
| Memory and performance | Cosmetic cooldowns, effect counts, sprite bytes, finite presentation states and audio voices remain bounded. Cancellation and owner destruction clear retained appearance/reactions. The held bar uses the existing actor layer and bounded sprite cache. |
| Sound and costs | Playback uses same-origin assets and existing opt-in, mute, priority and visibility fences. Chromium and Firefox decode all active files. Windows WebKit reports unavailable Web Audio and remains silent; this is not Safari-device audio proof. No runtime provider, prompt, token or quota path is added. |
| Responsive and accessibility | Widgets reuse the application button primitive and folded device controls. Native journeys cover narrow portrait and landscape, focus restoration, overflow and axe checks. Physical devices remain the accepted qualification boundary. |
| Quality gates | Coverage failures were addressed with behavior tests, never reduced thresholds. Existing scoped floors were raised and a controller floor was added from measured coverage. Complexity, hooks and double-cast caps were not increased. |

The broad World formatting inspection reports eight already-staged files outside
this refinement; they have no unstaged modification from this work. All files
changed by this refinement were formatted. Concurrent changes and the external
index were preserved; this work did not stage, commit or push files.

## Final self-assessment

| Required question | Verdict |
| --- | --- |
| Engineering and game-design acceptance | Accepted within the exercised scope: authored animations, approach/pose truth, thin visible weights, local sound and state, widgets and photo behavior have source and runtime evidence. No known blocking defect remains. |
| Test plan implemented and successful | The complete frontend coverage run, affected backend and host guards, native journeys and engine matrices above passed. Strengthened coverage gates are enforced. |
| Simulations and degraded paths | Real isolated authority/navigation plus cancellation, rejected/late poses, unreachable moving targets, stale owners, interrupted dashboard streams, audio unavailability and bounded cleanup are covered. This is bounded evidence rather than a claim that every conceivable failure was simulated. |
| Templates, registries and platform costs | Existing UI and native hosts are reused; no new server state, memory, prompt, quota or token path was introduced. Local presentation/cache/voice ownership is bounded and generation credits are recorded separately. |
| Mobile and completion | Responsive browser checks passed. iOS compilation and physical Android/iPhone/iPad sharing remain explicitly accepted follow-up qualifications, as recorded above. All implementation lots and Windows-host qualification are complete; no deployment or Git delivery was performed. |

## Cold review of workout contact

The owner's close-up exposed block-like weights and a bar intersecting the head.
The final model uses thin octagonal plates outside the hand grips, a supported
shaft, a smooth rack-to-chest handoff, three synchronized lifts and a return to
the rack. Body placement and bar/hand reach share authored constants. The
existing geometry guard caught an initial shaft extending beyond the furniture
footprint; the model was corrected inside that footprint without changing the
guard. The contact, geometry and pose tests passed. Native close-ups explicitly
turn reduced motion off so low/high captures prove the moving geometry.

The final visual review found a second, independent cause: a bar baked into the
furniture layer could lose its far plate behind the torso. The held bar now
composes after the owner's body and before the existing foreground masks. The
supporting-prop mask exemption was already present and remains unchanged.
The native journey passed on both benches; close-up captures show both plate
ends clear of the face during a lift. A renderer regression assertion checks
this composition order, alongside the contact and footprint guards.
