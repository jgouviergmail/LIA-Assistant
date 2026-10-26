# World staged review corrections — 2026-10-26

Scope: corrections applied over the existing staged change set, inline, without
committing, pushing or deploying. Unrelated staged work and the user's index are
preserved. Measurements below refer to this local checkout and disposable proof.

## Reviewed batches

1. **Ground working set and pending controls.** The fixed ground LRU could evict
   still-visible chunks during one traversal. The renderer now retains exactly
   its visible working set, reuses it on stationary frames and frees departed
   surfaces. Regression tests reproduce the original failures on Full HD and
   ultrawide viewports at minimum zoom. Busy message/appearance/home controls
   retain native focusability, guard repeat submissions and freeze pending edits.
   Browser tests hold requests, exercise keyboard resubmission and release them
   with an error or revision conflict; values and focus survive.
2. **Shared Select boundary.** The application-wide empty-value filter is removed.
   The actual Activity/Radix form-bridge event is contained at World's private
   boundary: an aria-hidden native select with no selected option cannot turn
   effect restoration into an edit. The portal-based characterization checks
   retained form data, explicit clearing and native form reset. Nested portal
   hiding and confirmed-account-change destruction remain covered.
3. **Copy, identity and prompt contract.** Seventy strings were edited individually
   for consistent informal address in French, German, Spanish and Chinese. All
   six locale trees retain parity. Empty public account names use the account
   language through gettext, verified with real SQL accounts in all six languages.
   The public translator prompt renders its character bound from the same
   constant as validation, preserving literal JSON and untrusted-text separation.
   Three new icon imports use `MapIcon`, leaving JavaScript's `Map` available.
4. **Palette-only home.** Undeployed motif/placement models, validators, renderer
   hooks, texture-key components, artwork, catalogue data, copy and fixtures are
   removed. Requests reject retired fields. Owner/revision checks, collision
   geometry, source-read isolation, cancellation and explicit unreadable-data
   repair remain covered. No migration or compatibility write is introduced.
5. **Reproducible qualification.** The repository launcher creates labelled SQL,
   Redis, API and web resources from current sources. API/SQL/Redis have only an
   internal network; web alone publishes a loopback port. Credentials are fresh,
   provider keys and shared development volumes are absent, and cleanup verifies
   ownership. Integration uses a separate database and Redis DB 15, requiring
   infrastructure rather than silently skipping. Each native scenario starts a
   new authority epoch through an origin-guarded fixture route on this exact inert
   host. Startup waits for the build and API readiness with a bounded deadline;
   startup failures erase temporary credentials and source archives. This removes
   inherited private-home positions while preserving the real
   application's reconnect semantics. The route is absent from application entry.
6. **Backend contracts.** Every World function has a docstring; Pydantic fields,
   nested position fields and World settings have descriptions. The static gate
   has no documentation-debt allowlist and is included in hygiene linting.
   Synthetic contracts verify inherited fields, nested functions, empty
   descriptions, TypedDict metadata and the explicit ORM exclusion. Metadata
   changes retain strict validation, defaults and response shapes.
7. **Public artifacts and decision trace.** The original BIP image and manifest
   are retained under offline authoring sources instead of public delivery.
   Repacking verifies identical RGBA pixels and the unchanged runtime atlas hash.
   The guide gives executable lifecycle commands instead of retired preview
   links. ADR-365 names its amendments to lifecycle, export, capabilities and
   native application command decisions.

Each batch received a cold review of ownership, stale completions, cancellation,
privacy projections, resource lifetimes, allocation bounds, input handling and
native keyboard behavior before continuing. Runtime replay also exposed stale
test selectors, missing proof prerequisites and cross-scenario state; those were
corrected at the harness boundary without bypassing application authorization.

## Verification

- `task test:frontend:coverage`: 14,644 tests passed; aggregate and scoped
  thresholds passed. No coverage floor or exclusion was weakened.
- Current World frontend suite: 406 tests passed. All twelve browser focus
  scenarios passed across Chromium, Firefox and WebKit with controlled pending
  failures/conflicts.
- Backend World/runner/documentation/template suite: 174 tests passed.
- Final runner/documentation guards: 9 tests passed, including failed network
  creation cleanup, readiness after temporary unavailability and bounded timeout.
- World SQL/Redis integration: 79 tests passed on disposable services, without
  infrastructure skips; all 79 passed again after a complete host recreation.
- Full fast backend run: 47,004 passed, 30 platform-marked skips. Two template
  annotation failures were repaired and their complete guard rerun passed. Two
  remaining documentation assertions depend on new files entering the index;
  `task lint:docs:preview` passes on the complete proposed snapshot.
- Backend and frontend lint passed. Hygiene, i18n, type-debt, observability,
  dependency cycles, backend/frontend complexity, accessibility, hooks,
  double-assertion, lockfile, workflow-parity, wake and dependency-tool gates
  passed. App and E2E TypeScript checks passed; both new Python tools also pass
  strict MyPy. The World documentation gate reports zero missing contracts;
  normalized AST comparison confirms that all 36 metadata-only domain modules
  preserve their behavior relative to the original index.
- The complete native matrix initially found six harness failures (among 51
  passes and six development-only chooser skips). Harness corrections covered
  premature initial reload, shared browser transport pools, foreground retry
  timing and observing completed departure before FIFO assertions. The final
  replay of all seven affected journeys on
  all three engines passed: **21/21**, including capacity/FIFO/takeover, bilingual
  and interrupted delivery, account withdrawal and the paged private gallery.
- The optimized standalone journey passed **3/3**, with five real server clients,
  one full UI renderer, mobile controls, Chromium touch/CPU slowdown, native
  navigation, axe, no browser errors and no paid-call request.
- The original public PNG returns HTTP 404; the runtime atlas returns HTTP 200.
  The source repacker reports exact RGBA equality and the unchanged runtime hash.
- Hermetic artwork/interface/settings/focus journeys: 54 passed and four existing
  Chromium-only audio cases skipped on the other engines. The two full WebKit
  art tours initially exceeded the generic 90-second test timeout even alone.
  Their explicit authoring-tour budget is now 240 seconds; both final tours
  passed (2.4 and 2.6 minutes) with all captures and assertions intact. Far-zoom
  textures were 88.5 MiB by day and 90.2 MiB by night, below the unchanged 128 MiB
  ceiling. This gives 56 passing hermetic scenarios across the matrix and final
  art replay, including all twelve focus scenarios.
- The development-only chooser passed **6/6** on a completely recreated host,
  covering French/English admission, native HttpOnly sessions and no World ticket
  before consent. It inherits the suite's bounded timeout to include cold Next
  compilation (the first cold Chromium journey took 42.8 seconds). Credentials
  and source tar files were confirmed absent after startup completed.

The source corrections remain outside the index, as required by the repository's
Git-operation rule. The normal index-based documentation gate and its two unit
assertions therefore see the old file inventory; this is the only remaining
global-gate discrepancy. The documented unstaged-preview gate passes with zero
broken living links, stale living paths, or living orphans. No Git mutation,
coverage exclusion or quality-debt baseline increase was used to clear a finding.

## Optimized local measurements

These are samples from this Windows host's pinned headless engines, under the
same night/snow scene and five native clients. The other four clients use native
transports; this is not five simultaneous full UI renderers or a device benchmark.

| Engine | Desktop FPS | Desktop render p95 | Phone viewport, low quality FPS | Phone render p95 |
| --- | ---: | ---: | ---: | ---: |
| Chromium | 60 | 2.2 ms | 30.1 | 1 ms |
| Firefox | 58.7 | 20.5 ms | 30 | 6.8 ms |
| WebKit | 7.5 | 112 ms | 11.7 | 61 ms |

Chromium's additional 4x CPU slowdown sample retained 30 FPS with a 6 ms render
p95. WebKit is slow on this local runner; passing functional/axe assertions does
not certify Safari performance. Physical Safari/iPhone and Pi qualification
remain release gates. No FPS claim is inferred from screenshots.

The proof uses inert translation ports and emulated viewports. These results do
not certify paid-provider linguistic fidelity or physical phone/Pi thermals.
Fresh proof resources are removed after qualification using the labelled cleanup.
