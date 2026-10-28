# World interactions, acting and arcade implementation plan

> **For agentic workers:** Use superpowers:executing-plans and execute strictly
> INLINE. The owner explicitly forbids subagents. This file is a plan, not an
> authorization to start business implementation in the analysis turn.

**Execution status:** completed after the owner's implementation instruction.
See the [qualification report](../qualification/2026-10-27-world-interactions-and-play.md)
for measured results, corrected findings and physical-platform limits.

**Goal:** Deliver the twelve selected World improvements with native private
dashboard access, expressive acting, safe photos and authoritative two-player games.

**Architecture:** Keep the existing Canvas renderer, authored scene, native
workspaces and Redis CAS authority. Derive one affordance projection from current
registries; isolate owner presentation from public emotes and participant games.
Extract the dashboard once and add a bounded native sharing bridge where the web
platform cannot provide file sharing.

**Tech stack:** Existing Next/React/TypeScript, Canvas 2D, FastAPI/Pydantic,
PostgreSQL, Redis, Vitest/Playwright/pytest and current Capacitor shells. No game
engine, external multiplayer service, sharing SDK or LLM game opponent.

**Spec:** [Functional and systemic analysis](../specs/2026-10-27-world-interactions-and-play.md).

## Global constraints

- Execute inline; preserve concurrent working-tree changes and the real index.
- No business implementation until the owner accepts the analysis/plan.
- Keep every existing auth, account lifetime, capability, HITL, accounting and
  private projection boundary. No admin panels become World activities.
- Six locales; native semantic controls; reduced motion; mobile and desktop.
- Every new public/Pydantic field is documented; strict TS/MyPy and shrink-only
  ratchets remain authoritative. Do not raise thresholds, caps or debt baselines.
- Newly authored docs/comments are English. User-facing copy is localized.
- Art/physics/geometry and owner state are separate. No LLM for visual/game logic.
- Actual dashboard opening retains the native dashboard's provider/LLM behavior.
- Use Taskfile gates and Docker/native proof workflows; no ad-hoc host Next server.
- No commit/push/deployment or production network change is authorized here.

## Review focus

1. A receipt for an emote or move must never satisfy an old pending seat request.
2. A dashboard card can contain an executable intent, a draft, filters or a native
   route; these are different contracts and cannot be collapsed into one string.
3. Erasure must find a person held only in game state after their actor disappeared.
4. Live Canvas has names and speech baked into pixels; a screenshot with hidden
   DOM is not a safe photo.
5. Share-file support, transient activation and chooser completion differ between
   browsers and native shells; synthetic WebKit is not physical iOS evidence.

## Traceability and dependency order

| Requirement | Delivering lots | Principal regression oracles                                       |
| ----------- | --------------- | ------------------------------------------------------------------ |
| R01         | 2               | New registered action appears; unavailable activity cannot open.   |
| R02         | 1, 2            | True default; saved off; navigation unchanged.                     |
| R03         | 4               | Same owner inbox in phone and props; no shared DTO data.           |
| R04         | 2, 3            | Real pose ack; decline stays seated; full native dashboard.        |
| R05         | 4               | Prepared is not succeeded; real speech state; four art directions. |
| R08         | 1, 2            | Three real events; skip/replay; no paid request.                   |
| R09         | 5               | Bounded responsive effects; no collision/art regression.           |
| R10         | 6               | Current controller and pair policy; receipt/expiry; no replay.     |
| R11         | 5               | Exactly five masculine and five feminine valid presets.            |
| R12         | 10, 11          | Pixel/input privacy; download/share; physical shell chooser.       |
| R13         | 1, 5            | Civil season/hemisphere, stable physics and bounded caches.        |
| R17         | 6, 7, 8, 9      | Pure rules + live two-worker CAS and browser match lifecycle.      |

Sequence: 0 -> 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9 -> 10 -> 11 -> 12.
Lots 5, 7 and 10 are technically independent of some preceding lots; execute
sequentially under the owner's inline constraint. First complete a minimal
two-client morpion slice in lots 6–9, and a photo/share slice in lots 10–11;
qualify their uncertain boundaries before adding art polish or stronger bots.

All paths marked **Create** below are proposed new files. A migration filename
and revision are generated from the then-current single Alembic head at execution;
do not invent or freeze a future revision now.

## Lot 0: execution baseline and reviewed acceptance examples

**Read:** `CLAUDE.md`, `apps/web/CLAUDE.md`, Taskfile commands, the linked spec,
current Git status, World proof instructions and active migration head.

**Deliverable:** A dated qualification ledger under
`docs/superpowers/qualification/`, with the selected contract examples, exact
environment and source identity. No code change needed for this lot.

- [x] Inventory staged/unstaged/untracked changes. Recheck source hashes; do not
      overwrite the concurrent dashboard/hook/security work seen during analysis.
- [x] Confirm disposable SQL/Redis proof can start via `task world:proof:start`.
      Diagnose the interrupted analysis pytest attempt before treating backend
      baseline tests as green. Keep shared development databases untouched.
- [x] Capture current desktop/mobile World, plain dashboard and photo candidate
      framing through the repository's Docker/proof workflow.
- [x] Pin three examples: generic terrace seat offers dashboard; meeting chair
      opens meetings; library chair opens knowledge. Confirm all room/cabinet
      approaches are reachable before adding geometry.
- [x] Record before-measurements: per-device frame/render p95, cache bytes,
      current EventSource/socket count, and dashboard spend/request count.

**Pass:** reproducible baseline, disposable infra ready, scope and native behavior
reviewable. Infrastructure unavailability is a gate to fix, never a reason to
replace integration with mocks.

## Lot 1: durable owner experience preferences

**Create (proposed):** `apps/api/src/domains/world/experience.py`,
`experience_service.py`, `experience_router.py`.
**Modify:** `apps/api/src/domains/world/router.py`,
`apps/api/src/domains/users/models.py`, `user_column_map.py`,
`account_deletion_service.py`, the generated additive Alembic migration,
`apps/web/src/features/world/useWorldOwnerPreferences.ts`.
**Create (proposed):** `apps/web/src/features/world/experience-protocol.ts`,
`useWorldExperiencePreferences.ts`.

**Interfaces (new):**

- `ExperiencePreferences(version=1, revision, show_route=True,
tutorial_version=1, tutorial_status, season_mode, hemisphere)`; closed enums
  from the spec, bounded integer revision and explicit repair semantics.
- `ExperienceUpdate(expected_revision, show_route, tutorial_status,
season_mode, hemisphere, reset=False)`; no arbitrary dictionary updates.
- `GET/PUT /world/experience`: owner-scoped `ExperienceView`, same fresh policy,
  timeout and optimistic-concurrency pattern as home/avatar.
- `read_owner_experience(owner: UUID) -> ExperienceView` and
  `update_owner_experience(owner: UUID, request: ExperienceUpdate) -> ExperienceView`.
- `useWorldExperiencePreferences(ownerId: string, enabled: boolean)` returns
  current parsed preferences, save/repair/conflict state and existing query lifetime.

* [x] RED: add `test_experience_defaults_do_not_rewrite_storage`,
      `test_experience_unknown_fields_and_versions_require_repair`,
      `test_experience_concurrent_write_has_one_winner`,
      `test_experience_is_private_exported_and_erased`.
      Assert route defaults true, unknown storage remains intact after GET,
      simultaneous expected revisions produce one conflict, and no peer DTO
      contains this column.
* [x] RED frontend: `experience-preferences.test.tsx` asserts invalid owner data
      is hidden, failed saves retain local UI value, late saves after account
      change cannot apply, and the resource union uses the existing hook.
* [x] Run the new tests and observe intended failures before implementing.
* [x] Implement the additive column, strict DTO, fresh owner lock and typed hook.
      Register export/scrub behavior with the existing user-column map; no new
      user-data table or assistant memory entry.
* [x] GREEN: run targeted tests, real persistence and fresh/up/down/up migration
      replay on disposable SQL. Run the column-map and World contract-doc guards.

**Pass:** home palette and avatar saves do not change experience preferences;
experience saves do not change either old document.

## Lot 2: one affordance projection, discovery, route and introduction

**Create:** World feature modules `scene-affordances.ts`, `WorldDiscovery.tsx`,
`route-presentation.ts`, `world-tutorial.ts`, `WorldTutorial.tsx`.
**Modify:** `types.ts`, `scene-activities.ts`, `scene-interactions.ts`,
`scene-pointer.ts`, `WorldShared.tsx`, `WorldHud.tsx`, `WorldPrototype.tsx`,
`runtime.ts`, `useWorldRuntime.ts`, `renderer.ts`, `house-authoring.ts`,
`house-furniture.ts`, `house-garden.ts`, `scripts/world-catalogue.cjs` and its
compiled server asset. Keep cohesive extractions out of already large renderer/UI files.

**Interfaces (new):**

- `SceneAffordance`: stable ID, `SceneTarget`, action category, title key,
  footprint, approach and availability reason; no private content or callback.
- `buildSceneAffordances(world: WorldDefinition, policy: SceneAvailability):
readonly SceneAffordance[]` consumes the native catalogue and current activation
  policy. Static authored data may be cached; policy must remain current.
- `seatContext(slotId: string): {tableKey: string; activity: SceneActivity | null}
| null` uses explicit authored associations, not proximity.
- `TutorialState` / `advanceTutorial(state, event)` is a pure FSM with events
  from confirmed movement, successful activity opening and LIA-menu opening.
- Runtime setters update route/discovery presentation without remounting Canvas.

* [x] RED: `scene-affordances.test.ts` inserts a future catalogue action with an
      authored prop, then asserts discovery and activation share availability;
      disabled/unknown/unbound actions do not invent an object.
* [x] RED: `seat-context.test.ts` enumerates every table/seat binding; rejects
      duplicates, missing references and table associations that steal a specific
      activity. Every generic table has a reachable associated sitting slot.
* [x] RED: `route-presentation.test.ts` and `world-tutorial.test.ts` cover toggle,
      cancelled/replaced routes, static reduced motion, skip/replay, unavailable
      target, restored seat, account loss and completion without any model call.
* [x] RED component/browser: discovery's accessible list retains focus past the
      six-second footprint timeout; tap and keyboard open the same target.
* [x] Implement derivation and the two small UI controllers. Preserve the existing
      clipped ground-footprint style. Do not recolor the objects or add window halos.
* [x] Regenerate the authored catalogue, verify parity and ordinary interaction/
      reach/seat tests. Update all six locales with behavior-specific accessible names.

**Pass:** adding a future registered physical activity needs no discovery-UI edit;
route is on by default and optional; tutorial targets are always real and currently usable.

## Lot 3: confirmed-seat offer and shared complete dashboard

**Create:** World modules `seat-dashboard-intent.ts`, `WorldDashboardOffer.tsx`;
dashboard modules `DashboardWorkspace.tsx`, `DashboardNavigation.tsx`.
**Modify:** dashboard route `apps/web/src/app/[lng]/dashboard/page.tsx`,
`TodayBriefing.tsx`, dashboard cards/quick-access/hints that navigate,
`useBriefing.ts`, relevant account-owned dashboard hooks;
World `activity-catalogue.ts`, `activity-entry.ts`, `WorldWorkspacePanel.tsx`,
`WorldFunctionControls.tsx`, `WorldShared.tsx`, `useWorldSession.ts`;
`apps/web/src/components/workboard/WorkboardPage.tsx`.

**Interfaces (new/extended):**

- `DashboardWorkspace({lng, ownerId, active, navigation?})`: same content in the
  ordinary route and World; hooks pause under `active=false`, old data remains
  owner-bound. Existing ordinary route defaults active true.
- `SeatDashboardIntent`: accepts the current confirmed seat/stream/epoch and
  explicit offer choice. It never reads dashboard data itself.
- Add workspace identity `dashboard`; add typed workboard initial filters/ticket
  to the existing bounded activity entry/history, rather than reading host URL.
- `DashboardDestination`: closed native settings/draft/workboard/meeting/gallery/
  registers shapes. Executable native intent remains its existing deep-link
  transition, explicitly labeled as opening Chat.

* [x] RED: `seat-dashboard-intent.test.ts` asserts one offer after matching ack,
      zero on reconnect/hydration/refusal/old stream, and no activity override.
* [x] RED: `dashboard-offer.test.tsx` asserts both buttons, Escape and outside
      dismissal; declining sends no stand and triggers zero dashboard queries.
* [x] RED: `DashboardWorkspace.embedded.test.tsx` covers all three principal
      dashboard parts, account replacement, refresh preserving values/focus,
      suspended reads, and close/reopen without another synthesis fetch.
      Specifically cover re-enabling a query after an aborted paid initial read;
      only explicit retry may trigger new text, and invalidations remain cards-only.
* [x] RED: `DashboardNavigation.test.tsx` covers workboard filters, selected
      meeting, settings tokens, draft retention and explicit native intent departure.
      Preserve two-different-people deep-link replay regression tests.
* [x] Implement extraction, not a copy of the page. Catalogue/table entry merely
      mounts after acceptance. Existing native dialogs and lifecycle guard own it.
* [x] Implement active/suspended hook behavior with tests before each shared hook
      change. Use explicit `enabled` contracts rather than hidden mounted readers.
* [x] GREEN: run ordinary dashboard/account/card tests and World tests; hermetic
      browser accepts/refuses at actual generic seats and retains seated pose.

**Pass:** the owner sees the actual full dashboard; the unaccepted offer costs
nothing; native route behavior, card filtering, meetings/import and HITL remain valid.

## Lot 4: private object signals and evidence-driven LIA acting

**Create:** World `useWorldPrivateSignals.ts`, `private-signal-projection.ts`,
`world-acting.ts`; eye shared reader extraction if required for one background owner.
**Modify:** `WorldDeviceControls.tsx`, `device-inbox.ts`, `WorldShared.tsx`,
`WorldFunctionControls.tsx`, `renderer.ts`, `art/lia-atlas.ts`, `runtime.ts`;
`components/eyes/ApplicationEyes.tsx`, `behavior-context.ts`,
`components/companion/CompanionPresence.tsx`, embedded `ChatWorkspace.tsx` only
where its phase publication must be made host-aware.

**Interfaces (new):**

- `WorldPrivateSignals` is a bounded readonly owner-local snapshot of inbox
  identities and verified native resource availability. Renderer receives only
  presentation data; bodies remain in existing native readers.
- `openPrivateSignal(signalId: string): boolean` resolves a current owner-store
  identity into the existing focused SMS/reminder reader or a typed workboard/
  gallery entry. Authored props contain only a signal family, never private
  message/ticket IDs. A stale/missing identity opens no unrelated item.
- `WorldActingFrame` contains native expression/family/gaze/emphasis, confirmed
  activity outcome and a one-shot event key; no message or tool arguments.
- `deriveWorldActing(inputs, now): WorldActingFrame` delegates expression choice
  to the current native resolver. `LiaAtlas.setActing(frame)` changes pose inputs,
  while its existing World clock advances the rig.

* [x] RED: `private-signal-projection.test.ts` verifies owner filtering, duplicate
      SMS/reminder delivery, reconnect uncertainty, stale reads and unavailable
      counts; phone and object acknowledgment use the same inbox.
* [x] RED: `world-acting.test.ts` covers HITL, actual playback, creating/reading,
      prepared/succeeded/failed/waiting/unknown, duplicate completion, history replay
      and expiry. Wrong run/account evidence never produces a success accent.
* [x] RED lifetime tests assert no additional notification/poll owner, no late
      callback after disposal, and no acting/store values in shared snapshots.
* [x] Implement shared ownership plus the initial four signal families from the
      spec. Add a small authored support only where the existing props cannot
      convey the function without semantic confusion.
* [x] Implement pose adapter and restrained body/head overlays; preserve atlas
      fallback and back-view silhouette. Do not mount `useEyesBehavior` timers in Canvas.
* [x] GREEN browser: act while private chat is open; waiting/error stay readable,
      two accounts see their own signals, reduced motion stays static, and ordinary
      application eyes/chat/voice tests remain green.

**Pass:** visible state explains actual activity and never discloses another
person's data or claims a draft was executed.

## Lot 5: reactive decoration, ten presets and seasons

**Create:** World `cosmetic-interactions.ts`, `cosmetic-effects.ts`,
`avatar-presets.ts`, `season.ts`, `art/seasonal-palette.ts`.
**Modify:** existing World authoring, prop picking, ambient life and art modules,
`WorldAvatarEditor.tsx`, `WorldAvatarFields.tsx`, `WorldHelp`/settings UI,
`renderer.ts` texture keys and invalidation.

**Interfaces (new):**

- `CosmeticActionId` is a finite enum from the spec; `CosmeticEffects.activate(id,
targetKey, now)` returns a bounded accepted/refused presentation event.
- `AvatarPreset = {id, presentation: 'masculine'|'feminine', titleKey,
appearance: AvatarAppearance}`; ten authored entries with schema-valid data.
- `seasonAt(serverInstant, timezone, mode, hemisphere): Season|'neutral'`; invalid
  or unavailable clock input returns neutral. `seasonalPalette` is a pure projection.

* [x] RED: effect queue limits, cooldowns, hidden/offscreen behavior and frame-step
      invariance; dynamic cat target does not become collision geometry.
* [x] RED: preset count 5+5, uniqueness, schema validation, five-tone distribution,
      preview-only selection, modified preset/custom indicator and conflict save.
* [x] RED: month boundaries and hemisphere offset, account timezone around midnight,
      absent/expired anchor, off/manual season, bounded cache growth after switches.
* [x] Implement the initial nine cosmetic interactions with existing art first.
      Add no ambient sound outside existing activation/priority rules.
* [x] Implement presets as existing-field combinations, not new persisted gender
      or generated portraits. Implement seasonal drawing without changing geometry.
* [x] GREEN: art/occlusion/collision gates plus day/night/weather/shelter, directions,
      posture and small-screen screenshots on three engines.

**Pass:** a close-up animator review signs off anticipation, clear contact,
readable response, clean settle and no drift. A passing unit count alone does not pass art.

## Lot 6: socket v2 contracts and social emotes

**Create:** backend World `socket_models.py`, `emotes.py`; frontend
`emote-catalogue.ts`, `WorldEmoteControls.tsx`, `art/emotes.ts`.
**Modify:** World backend schemas/transport/service/authority/lifecycle/router,
frontend `protocol.ts`, `shared-link.ts`, `shared-simulation.ts`, `useWorldSession.ts`,
renderer, all wire fixtures, scene version and compiled catalogue.

**Interfaces (new):**

- `SocketVersionedModel(version=2)` separate from preference/message v1 base.
- `CommandReceipt(seq, kind, result)` on the owner view; explicit pose receipt
  correlation replaces relying on generic `ack` plus stale `pose_result`.
- `EmoteCommand(version=2, epoch, seq, emote)` with closed enum and actor-local
  serial/expiry state; server-time anchor in snapshot.
- Participant/table DTOs are introduced atomically with the lot 8 authority,
  after lot 7 supplies strict board types. They remain on socket v2, with a new
  authored scene generation fencing older strict clients; no dormant command
  or unvalidated participant payload is exposed in this lot.

* [x] RED: backend `test_socket_v2.py`, `test_emotes.py`; frontend
      `emote-protocol.test.ts`, extended `shared-link`/`seat-activity-intent` tests.
      Assert an emote with a newer generic ack cannot open a pending seat activity.
* [x] RED: strict unknown/private field rejection, old client reload outcome,
      old stored state decode for erasure, max UTF-8 frames and numeric strictness.
      Legacy cleanup must still decode under its old strict reader: defaults
      for new fields cannot be serialized into a still-active old scene.
* [x] RED: current-controller rate fence, hidden/home sender, block/visibility,
      disconnect expiry and reconnect without replay; typing does not emote.
* [x] Implement new socket base, explicit receipts and emote projection. Preserve
      old home/avatar/message DTO versions. Reset serial fences correctly on takeover.
* [x] GREEN: existing transport, prediction, pose and privacy suites; native
      two-client browser emote; maximum-capacity serialized snapshot size.

**Pass:** v2 is a coherent scene release. Updated clients explain reload on a
version mismatch; frozen old clients fail safely through their existing UI.
Strictness, frame ceilings and ownership are not relaxed for compatibility.

## Lot 7: pure game rules and deterministic computer opponents

**Create:** backend World `game_models.py`, `game_catalogue.py`,
`game_rules.py`, `game_bots.py`; split per-game rules into a cohesive package if
needed to stay below complexity/SLOC limits. Add authored semantic cabinet keys.
**Modify:** frontend authored cabinet metadata and `scripts/world-catalogue.cjs`.

**Interfaces (new):**

- `GameKind = Literal['tic_tac_toe','four_in_row','reversi']`.
- `GamePosition`: closed typed game-specific board/turn/result union; no `Any` board.
- `legal_moves(position) -> tuple[GameMove, ...]`,
  `apply_game_move(position, move) -> GamePosition`,
  `choose_computer_move(position, node_budget=6000) -> GameMove | None`.
- Immutable rule inputs; all randomness/tie-breaking deterministic and testable.

* [x] RED: `test_game_rules.py` exhaustive reachable tic-tac-toe states and
      terminal immutability; four-in-row horizontal/vertical/both diagonals,
      full columns/board and out-of-range/bool coordinates; Reversi eight
      directions, edge wrapping, forced pass, double-no-move and disc counts.
* [x] RED: `test_game_bots.py` proves every returned move is legal, immediate
      win/block cases, deterministic tie breaks and budget exhaustion fallback.
      Count work; avoid fragile wall-clock assertions as the sole budget oracle.
* [x] Implement minimal rules, then bounded opponent strategy. No browser-trusted
      score, downloaded game bundle, Python sandbox skill or LLM call.
* [x] GREEN: test generated cabinet identity/rule correspondence and catalogue parity.

**Pass:** rule correctness is independent of networking, rendering and bot strength.

## Lot 8: game authority, policy races and lifecycle

**Create:** backend World `games.py`, `game_service.py`, `game_projection.py`.
**Modify:** WorldState/commands/service/pruning/projection/lifecycle, constants,
World settings, public config projection, active target env and env templates;
`apps/api/src/domains/peers/service.py` for the canonical pair lock only.
The current config surfaces are `apps/api/src/api/v1/routes.py` and
`apps/web/src/hooks/useAppConfig.ts`. Create the proposed bounded server metrics
module `apps/api/src/infrastructure/observability/metrics_world.py` and register
its imports through the existing World ownership boundary.

**Interfaces (new):**

- `GameCommand`: closed join/request/accept/decline/start_computer/move/leave/
  rematch/rejoin union with epoch, sequence, cabinet/round/action identities and
  expected round revision; move fields are game-specific and bounded.
- `GameTable`: one state per authored cabinet, members/controllers, board, deadlines,
  one pending join, revision and at most sixteen request receipts.
- `apply_game_transition(state, scope, command, now, prepared_result) -> GameOutcome`
  is pure. `prepared_result` contains a precomputed legal human+bot state fenced
  by the original round revision; no CPU search repeats inside CAS.
- `project_games(state, viewer, policy, now)` yields participant boards or only
  public cabinet availability. `prune_games(state, now)` is pure and idempotent.

* [x] RED: pure authority tests cover every spec transition, one-table/account,
      2-slot limit, host consent, fresh-board solo handover, alternating rematch,
      legal human activity vs bot-only inactivity, timeout and reconnect clocks.
* [x] RED integration: two independent service instances with real disposable
      Redis contend for the second slot and same move; exactly one wins. Unrelated
      actor movement does not invalidate a match revision.
* [x] RED integration: SQL block/deactivate/delete races with join/move; add the
      pair lock to both block/unblock and game transitions. Test lock ordering
      with opposite actor order and bounded failure, without a domain cycle.
      Use a session-aware policy reader inside the canonical locks; calling the
      existing session-opening `read_policy` there must not deadlock itself.
* [x] RED integration: cancel after EXEC, retry exact action ID, changed payload
      with same ID, changed round, stale controller, admission expiry, corrupt
      state and Redis timeout. No repeated move or invented winner.
* [x] RED cleanup: account exists only as table member; purge removes it and
      any pending requests/receipts in old and current scene namespaces.
* [x] Implement authority and small dispatch boundary. Commands acquire fresh
      policy and rate fences; pure CAS owns final identity/epoch/revision checks.
      Preserve the existing bounded policy-projection refresh window explicitly.
* [x] Implement the subordinate deployment arcade limit (default true beneath
      WORLD) on mutation and projection; verify disabled startup and restart
      behavior. Test live withdrawal through the existing WORLD capability.
      Do not claim the environment setting is a new restart-free admin switch.
* [x] GREEN: `task test:backend:world:integration`, account export/deletion
      regressions, strict MyPy and World contract docs. Measure authority bytes,
      contention, frame sizes and bounded bot CPU on representative boards.

**Pass:** one authoritative outcome across workers, safe revocation/erasure and
no new service, unbounded worker pool or persistent game-history table.

## Lot 9: accessible cabinet games and two-client feasibility proof

**Create:** World `game-protocol.ts`, `game-client.ts`, `WorldArcadePanel.tsx`,
`games/TicTacToeBoard.tsx`, `games/FourInRowBoard.tsx`, `games/ReversiBoard.tsx`.
**Modify:** existing World interaction host, session link/controller and activity host.

**Interfaces (new):**

- Typed game projections are strictly parsed before entering UI.
- Extend `SceneActivity` with `{kind: 'arcade'; id: CabinetId}` and a dedicated
  `world-arcade` entry carrying the closed cabinet identity. `CabinetId` derives
  from the three stable authored cabinet keys; dynamic discovery and activation
  use this same binding and the effective arcade limit.
- `WorldGameClient` owns one round/controller generation, one pending command
  and resynchronization; it never supplies local authority/winner or silently
  replays an uncertain action against a new revision.
- A shared board shell owns title, participants/turn/status, invitation, rematch,
  reconnect and Leave; game components own only coordinates and visual rules.

* [x] RED: protocol unknown/private fields, out-of-order snapshots, superseded
      commands, operation dedup, stale round and unavailable-switch states.
* [x] RED component: keyboard cell/column navigation, legal/illegal move feedback,
      Reversi pass, screen-reader turn announcement, reduced motion, 320px layout.
* [x] RED browser: independent browser processes A/B/C enter through real native
      admission. A waits, B joins, C is refused; then play a complete morpion
      match, rematch, disconnect/resume and leave.
* [x] Implement morpion end-to-end first; inspect actual CAS/bytes/latency and
      keyboard/touch UX. Resolve authority/policy failures before adding the
      other board renderings. Then deliver four-in-row and Reversi.
* [x] GREEN: solo computer on each cabinet, explicit acceptance of a human
      joining a solo table, three concurrent cabinets and two tabs of one account.
      Closing a panel or moving away leaves exactly once.

**Pass:** two humans and a lone human can actually finish each game using the
same native World server, without any paid model or mocked authority boundary.

## Lot 10: safe photo composition and browser sharing

**Create:** World `photo-projection.ts`, `photo-export.ts`, `WorldPhotoPanel.tsx`.
**Modify:** renderer drawing entry/seams and World runtime/control UI only as
needed; reuse existing sprite/occlusion functions rather than copying painters.

**Interfaces (new):**

- `PhotoScene`: allowlisted decor, own appearance, LIA, frozen pose/time and camera;
  no `WorldSpeech`, notice inbox, private DTO, peer actors or public name strings.
- `projectPhotoScene(input): PhotoScene` constructs this independently of live
  Canvas pixels. `renderPhoto(scene, format): Promise<Blob>` enforces spec bounds.
- `shareWorldPhoto(file: File): Promise<'offered'|'cancelled'|'unsupported'>` checks
  actual file-share support; failures use the existing translated error UI.

* [x] RED: `photo-projection.test.ts` uses secret marker values in every forbidden
      input and proves none enter the photo projection or renderer calls.
* [x] RED: `photo-export.test.ts` covers null encoder, tainted canvas exception,
      oversized output/downscale, single flight, account change, and Blob URL
      cleanup. Capture never advances live simulation or face clocks.
* [x] RED browser: screenshot/pixel oracle confirms no names/bubbles/other humans
      while retaining the owner's avatar and original decor. Verify landscape/
      portrait framing and restoration of live camera/UI after cancel.
* [x] RED sharing: unsupported `canShare`, absent API, permission rejection,
      user cancellation and transient activation after asynchronous encoding.
* [x] Implement safe still, bounded encoding, preview, explicit fresh Share click
      and local Download. No server upload or new photo persistence.
* [x] GREEN: three browser engines plus memory after repeated open/export/cancel.

**Pass:** sharing is useful and privacy is structural, not an overlay hidden
briefly before copying a live canvas.

## Lot 11: bounded native photo sharing

**Modify authored sources:** `apps/mobile/native/android/app/src/main/java/com/lia/assistant/LiaShellPlugin.java`,
`apps/mobile/native/android/app/src/main/AndroidManifest.xml`,
`apps/mobile/native/ios/App/App/LiaShellPlugin.swift`,
`apps/web/src/lib/native/shell.ts`, mobile prepare logic where required.
**Create:** narrow Android native resource `res/xml/world_share_paths.xml` and
platform-specific cohesive helper modules if the existing plugin would grow too large.

**Interfaces (new):**

- `LiaShell.shareImage({base64, mimeType: 'image/jpeg', filename})` receives only
  bounded bytes for an already previewed photo; reports chooser/cancel/failure
  truthfully where the OS supplies that information.
- Runtime capability detection distinguishes an older shell without the method
  from a current shell and from an ordinary browser. Old shells retain preview
  and supported download; do not attempt arbitrary `openExternal(blobUrl)`.

* [x] RED native/bridge: wrong MIME/signature, oversized base64/decoded bytes,
      oversized dimensions, unsafe filename, parallel calls, no presenter,
      disposed page, cache bound and missing old-shell method.
* [x] Implement Android with the existing FileProvider library and a dedicated
      `.worldshare` authority exposing only the new cache directory. Keep the
      original provider/camera paths intact; request no broad storage permission.
* [x] Implement iOS system activity controller with appropriate iPad popover,
      one presentation and bounded temporary image lifetime.
* [x] Regenerate source-derived shells through the existing prepare tasks.
      Verify the file ownership/copy policy before adding a resource.
* [x] GREEN locally available: native-shell static/prepare tests, authored JVM
      input/cache tests and Android compilation/package. Report chooser offered
      separately from downstream publication.
* [x] Record the owner decision to complete here: iOS compilation and physical
      Android/iPhone/iPad chooser, cancellation, selected target, background/return
      and repeated sharing remain documented platform qualification checks.

**Local completion:** authored code, preparation, Android build and available
tests pass. The owner requested completing here and documenting unavailable
Apple-host/device checks. They remain platform release gates, never synthetic
passes.

## Lot 12: integrated qualification, documentation and delivery boundary

**Modify at implementation time:** World technical guide, ADR-365 amendment or a
new numbered ADR if the final protocol merits one, user FAQ/guide source in six
locales, generated maps/knowledge through native tasks, and qualification ledger.
Update the public screenshots only after final safe visual review. Never edit
generated AGENTS.md separately from CLAUDE.md.

- [x] Run focused suites after each lot, then the broader gates justified by
      shared dashboard, socket, user-model and native-shell changes.
- [x] Execute the risk matrix, including 3 cabinets active, maximum configured
      World capacity, slow/disconnected links, private-home exclusion and killswitch.
- [x] Compare fresh same-device rendering/CPU/memory against lot 0; target <=10%
      render-p95 regression, existing cache/frame/state ceilings, bounded bot CPU.
      Qualify target Pi/phone behavior separately from browser emulation.
- [x] Review day/night/shelter, ten presets, all directions/poses, small-scale
      acting and reduced motion visually; fix readability, contact, timing and
      occlusion rather than only adjusting screenshot baselines.
- [x] Verify no provider call from decorative/tutorial/game/decline paths, no
      new memory extraction or fake agent ledger rows, and ordinary dashboard
      accounting including failure-spend/quotas/TTS.
- [x] Check source/compiled catalogue, strict API/OpenAPI/Pydantic descriptions,
      translation parity, no domain import cycle, fresh migration replay and
      account export/deletion. No baseline is increased to absorb findings.
- [x] Record exact commands, exits, counts, skips, warnings and unverified real
      environments in the ledger. Show concrete artifacts to the owner.
- [x] Commit/push/deploy only on a later explicit request. Until then preserve
      the user's original index and unrelated working-tree changes.

Local qualification is complete. The qualification report records the native
gates, initial broad-suite failures and successful reruns. The rendering
comparison is observational: different lighting/load prevents claiming the
controlled <=10% target, and 4x slowed emulation remains below cadence. iOS
compilation and physical sharing/performance checks remain disclosed platform
qualification, per the owner's instruction to finish on this Windows host.

## Validation commands and their scope

Existing baseline successfully executed during analysis:

```powershell
task test:frontend -- src/features/world/__tests__/seat-activity-intent.test.ts src/features/world/__tests__/scene-interactions.test.ts src/features/world/__tests__/scene-pointer.test.ts src/features/world/__tests__/activity-entry.test.ts src/features/world/__tests__/functions.test.ts src/features/world/__tests__/avatar-protocol.test.ts src/features/world/__tests__/runtime.test.ts src/features/world/__tests__/device-inbox.test.ts src/features/world/__tests__/shared-link.test.ts
node scripts/world-catalogue.cjs --check
```

Result: 9 files / 65 tests passed; catalogue check passed. No new feature is tested
by those existing tests. The four-file backend probe was interrupted without a
usable result and must be rerun once the lot-0 environment baseline is ready.

Implementation gates, selected from current Taskfile (do not quote a coverage
floor here; the native task owns it):

```powershell
task lint
task test:frontend
task test:frontend:coverage
task test:backend:unit:fast
task test:backend:unit:coverage
task world:proof:start
task test:backend:world:integration
task test:e2e:world-native
task test:e2e:world-production
task test:e2e
task db:migrate:replay-check
task lint:docs:preview
task ci:fast
```

Run frontend file arguments through `task test:frontend -- ...`; run new backend
unit files through the repository venv while preserving native markers/network
guards. Real integration must target disposable infrastructure. The full backend
integration/combined/diff-coverage gates become required when delivering model,
lifecycle or shared backend changes. Do not default to the exhaustive suite.
Run native shell preparation/validation through the actual Taskfile entries
after inspecting their platform requirements; iOS compilation/physical tests
require an appropriate Apple build host and device.

The initial documentation-only study ran documentation/format checks. The
subsequent authorized implementation and its complete available qualification
are recorded in the qualification report. No purchase, production networking,
commit, push or deployment is included.

## Design-stage self-review

- All twelve accepted IDs map to a lot, behavior and regression oracle.
- New interfaces are distinguished from existing source contracts.
- Every lot has RED behavior, a minimal implementation boundary and GREEN proof.
- The five review-focus failure classes have explicit test owners (lots 6, 3, 8,
  10 and 11 respectively).
- No irreversible action is needed to start implementation; no external business
  decision or invented existing service is hidden behind “TBD”.
- At design time, physical-device availability, measured CPU/rendering and the
  interrupted baseline were qualification conditions. The implementation report
  records their actual outcomes and the remaining physical-platform boundary.
