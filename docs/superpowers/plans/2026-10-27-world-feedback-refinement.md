# World feedback refinement implementation plan

Execute strictly inline with TDD and a cold self-review per lot. The owner's
explicit implementation and detailed feedback authorize this refinement.
No commit, push or deployment. Preserve the existing index and concurrent work.

## Binding scope and decisions

Keep the camera's selected zoom and center in both photo formats, cropping the
viewport with a cover scale instead of widening its field. Always stamp the
fixed `LIA World - https://lia.jeyswork.com` signature; there is no opt-out.
Add the effective localized season after civil time/phase. Put route, gestures
and photo in the existing device widget group, using Footprints, Hand and Camera.
Remove discovery, introduction/replay and the decorative-actions menu.

The atrium catalogue lists SMS. News moves from the cafeteria reading table to
the small meeting-room table to the right of its sofa. Only the rightmost gym
bench opens Health; the other two use authoritative lying poses for three lifts.
Indoor foliage remains green independently of the outdoor season.

Decorative clicks navigate before playing. Existing feature bindings retain
precedence and their labels. Pure decor shows a clickable pointer/footprint,
without action text. Flowers and birds lose their interactive affordances.
Plants rustle, billiards clack, the cat meows, machines start with distinct
authored cycles, the fountain shows an avatar coin toss followed by impact and
ripples, lamps toggle locally, screens cycle five contents. Sounds use the
existing opt-in, volume, lifecycle and audio-priority engine; no provider call,
prompt, memory, quota or remote mutation is introduced on the playback path.

Follow-up feedback adds a fishing rod/cast/wait/reel sequence to the pond and
three distinct machine sounds. The owner authorized one-time ElevenLabs asset
generation; eight active cues have recorded provider receipts and local playback.
The reported workout refusal also requires checking the actual development API
process, its catalogue generation and JSON reload filters, then exercising both
benches through native acknowledged poses.

## Lots and verification

- [x] 1. Photo, widgets, season and authored catalogue. RED camera crop/zoom,
  mandatory full signature, localized season, SMS/news/Health bindings and indoor
  foliage; update meaningful existing interaction tests. GREEN focused frontend
  suites, generated server catalogue parity, source typing and cold review.
- [x] 2. Walk-before-reaction and stateful decor. Reuse scene navigation,
  cancellation and authoritative arrival/pose gates; test interruption, hidden /
  disposed owners, missing/unreachable targets and rapid clicks. Retain no
  unbounded pending intent, timer, sprite or audio voice. Keep local lamp/screen
  state isolated and exclude interaction text only for non-feature decor.
- [x] 3. Authored animation and sound. Three distinct machines, phased coin toss /
  impact / rings, three bench presses with supported lying poses, per-object
  cues and reduced-motion alternatives. Assets need recorded provenance and
  bounded sizes; no external read on an interaction path. Verify timing,
  repeated toggles, cache invalidation, audio cancellation and voice priorities.
- [x] 4. Full affected frontend/backend suites, coverage/ratchets, static checks,
  six-locale parity and docs preview. Rebuild the task-owned Docker proof and
  inspect desktop/mobile, day/night, multiple zooms and three engines where
  relevant. Record exact results and physical-platform limits. Cold adversarial
  review of ownership, navigation/pose truth, memory/cache and audio lifetimes.

Completed qualification and accepted platform boundaries are recorded in the
[delivery ledger](../qualification/2026-10-27-world-feedback-refinement.md).

Primary files: photo-renderer/export/panel/preview, WorldPrototype/Hud/device
controls, exploration/emote/photo controls, sky badge, functions, house furniture,
pose slots and compiled campus catalogue, runtime/scene interactions, cosmetic
scene/effects, renderer/object painters, useWorldSound and audio catalogue/engine.
Keep strict typing, existing UI primitives and shrink-only quality gates.
