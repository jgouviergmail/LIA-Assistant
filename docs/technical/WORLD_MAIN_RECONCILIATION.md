# LIA World: main reconciliation

Status: the reconciled source is installed in the main working tree and the
planned qualification phases have passed. No commit, staging, push or production deployment is
part of this handoff.

Claude Code's final commit was
`fe7843c10dcd0a1a3362f6565272a9e262457ab5`. Its session had returned its final
answer and main was clean before integration. Both main's HEAD and index are
preserved. The isolated worktree was subsequently removed at the operator's
request after a complete verified backup and source comparison against main.

## Reconciliation decisions

The integration retains main's current authentication and Turnstile protections,
meeting imports, JEV evidence/projection, ReAct clock, token counter and spam
classification changes. It retains the world's authoritative presence and
movement, private native workspaces, direct/public correspondence, appearance,
day/night rendering and independent sound controls.

The shared paths were reconciled semantically, including:

- Chat capabilities: bookmarks and readable generated files remain available;
  meeting import requires its native capability and does not require recording.
- Meeting imports: ordinary navigation remains native; an import started from
  the meeting table opens its result inside the same world workspace. A late
  completion cannot navigate after its host has been dismissed.
- Workspace history: selection, unsent draft, gallery tab and meeting identity
  form one bounded entry. Closing and reopening cannot restore stale details.
- Account ownership: native panels retain their existing authentication, HITL,
  usage limits and account lifetime checks. Private content never enters world
  presence broadcasts.
- Locales and registries: key trees and declarations were combined rather than
  replacing either complete file. Generated maps and instruction mirrors were
  regenerated from their authorities.
- Quality gates: main's coverage union/diff gates, strict assertion ratchet and
  documentation checks remain enabled. Existing budgets were not increased.

The unintegrated world ADR was renumbered to
[ADR-365](../architecture/ADR-365-Private-Native-LIA-In-An-Authoritative-Isometric-World.md).
Main's ADR-363 and ADR-364 remain unchanged in identity.

## Findings corrected during cold review

| Finding | Resolution and regression evidence |
| --- | --- |
| New native composer capabilities missing from the embedded workspace | Shared capability projection; native and embedded tests |
| Imported meeting navigating away from the world | Host navigation context, cancellation guard and atomic history; real upload browser journeys |
| Message storage keyed by the trailing scene version alone | One bounded hash of the complete instance/scene authority key for Redis and SQL; separate-namespace delivery tests |
| Expired spend fences left in retired namespaces | Indexed bounded expiry collection across namespaces; live fences remain protected |
| Canvas test proxies hidden behind double assertions | Complete typed Canvas fixture; assertion budget unchanged |
| Wrong registered translation quota chokepoint | Register the actual shared accounted translation function |
| Cached-weather read missing from the reviewed demo route census | Review the owner-only cached projection and add its exact GET contract |
| Synthetic Git tests inheriting a foreign qualification index | Use the repository's isolated Git fixture for both tests |
| Empty lines wasting time in reply trimming under coverage | Skip impossible empty header/signature candidates; preserve the corpus and the existing timing ceiling |
| Private home close focusing a toolbar control hidden on mobile | Reuse the visible world-control focus fallback |
| Migration census ignoring tuple-valued merge parents | Parse literal metadata using AST without executing migration code; malformed metadata fails closed |
| Proof public translation adapter present only in a running container | Track both bounded inert adapters; keep the proof application separate from the ordinary API |
| Preview depending on main's stale shared dependency volume | Rebuild from the current lockfile; give the preview its own image dependencies |
| Deployment sandbox reusing the caller's Git index | Remove Git-declared repository-local variables at the Pester runner boundary; a hostile inherited index/worktree regression fails before the fix and passes afterwards |
| Old browser fixtures targeting dev-only pages or folded controls | Exercise the real native world page and deliberate HUD expansion; include the independent sound widget and measure rectangles in the same layout snapshot |
| WebKit multi-person HTTP transport starvation in one test browser process | Give simulated people independent browser processes; keep real native SSE, sockets, privacy assertions and unchanged limits |

## Migration convergence and rollback boundary

The migration
`2026_10_26_0535-e9c014ab7f62_merge_world_and_current_main_histories.py`
joins `8e4c20f65b91` and `a85f7c4d2e19`. It changes no schema or data itself.
Neither parent's history was rewritten.

Disposable PostgreSQL replays passed from a fresh database, from the main
parent and from the world parent. Each path reached the single head twice
without replaying changes and preserved a seeded probe and native meeting-import
schema. The merge-only downgrade was checked using the explicit target
`8e4c20f65b91`, followed by re-upgrade. Relative `-1` is ambiguous at a merge
and is not the documented rollback command.

Main's development database was backed up before the additive upgrade.
Integration tests ran against disposable databases, never against the shared
development schema. File preimages, the original Git index, the development
database dump and the old dependency links were retained outside the repository.
Do not restore them over subsequent user work without a fresh comparison.

## Qualification

Completed evidence includes:

| Surface | Result |
| --- | --- |
| Backend unit coverage task | 46,997 passed; 31 platform/fixture skips and nine normal marker exclusions |
| Full backend integration task | 5,435 passed plus four marked service tests; two POSIX-only cases skipped on Windows |
| Latest world SQL/Redis regressions, appended to integration coverage | 74 passed |
| Agent suite | 1,102 passed; 36 normal marker exclusions |
| Frontend unit coverage | 1,234 files, 14,641 tests passed; all configured global and scoped thresholds held |
| Backend combined coverage and changed-line gate | Combined report rounded to 88%; 2,414 of 2,625 changed lines covered (91.96%); native gates passed |
| Main checkout lint | Complete Taskfile lint passed from D main using a disposable verification index; the real index remained untouched |
| Hermetic browser suite | All 760 Chromium cases validated through the full pass and targeted recovery runs described below |
| Engine-diverse browser extension | 69 journeys passed across Chromium, Firefox and WebKit; the updated production-world cases also passed across the engines |
| Native optimized world | All 24 case/engine combinations validated on isolated SQL/Redis/session keys through the base pass and focused reruns |
| Deployment and installer | 179 Pester tests, shell readiness checks, release artifact tests, installer tests, strict tooling checks and all 24 Compose scenarios passed |
| Database graph | Fresh replay and replay from either parent passed, including repeat upgrade, seeded-data preservation and explicit-parent merge-only downgrade |
| Web build and runtime | Optimized image built; normal development API healthy; world enabled with capacity five; proof-session route absent from ordinary LIA |
| Secret scan | No new finding in the candidate snapshot; all 58 directory-scan matches were exact lines already present on main |

The first complete CI invocation exposed a Pester sandbox that inherited the
verification index. The backend and frontend covered suites had passed; after
fixing the test-runner boundary, the deployment and complete installer/release
phases were replayed successfully. This is phase-by-phase evidence, not a claim
that the failed invocation itself returned success.

The full hermetic browser pass had 738 successful cases. Its remaining cases
were replayed after correcting the harness: localhost-only/WebAuthn origin
requirements, production tests pointing to a development-only route, real mobile
HUD unfolding, the added independent sound widget and an atomic layout
measurement after scrolling. No assertion budget, timing ceiling, route
deployment guard or production feature was disabled to obtain these results.

The optimized native base pass had 18 successful case/engine combinations.
The public-message journey was moved onto the same real-entry adapter as the
other journeys. WebKit transport traces showed deferred same-origin requests
and a timed-out lazy chunk while several simulated people shared one browser
process. Replaying the same application with independent browser processes for
those people passed appearance, direct messages, owner-only proactive notices
and public delivery; Chromium/Firefox public delivery also passed. The fixture
retains real cookies, SSE, sockets and SQL/Redis checks.

Source hashes, canonical main index entries and HEAD were compared before and
after installation. Operational active environment files and dependency junctions
were preserved separately from tracked source. No production deployment occurred.

The final operational check recovered stopped preview dependencies and a
development API whose reload supervisor no longer had a serving child.
Diagnostics were retained. API health, world configuration, ordinary-API proof
route isolation and a fresh browser entry into the preview passed after restart.
The cause of the process exits was not established.

The retired operator worktree contained local receipts, source hashes,
RED/GREEN logs, migration replays and browser captures under `.tmp/world-g35/`.
They are preserved in the complete external worktree archive. Retirement receipts
and the backup location are recorded under `.tmp/world-retirement/` in main.
Those operational artifacts are not application assets and are not committed.

The standalone shared preview and its dedicated SQL/Redis containers, volumes
and networks were retired. Ordinary LIA remains the entry point through
`dashboard/world`. The development image also used by main was retained under
a main-development tag; its obsolete world tag and the two dedicated build
records were removed. Common BuildKit cache and shared LIA volumes were retained.

## Runtime boundaries

Local development enables the world through its active environment. The final
comparison preserved newer main-side edits setting WORLD_ENABLED=true in the two
example environment templates; it did not overwrite them with the candidate's
earlier values. Each deployment still reads its own active configuration and
native operator capability. Ordinary LIA does not mount proof-session endpoints
or inert translation adapters.

Rendering remains in the browser; the server owns shared authority and normal
LIA operations. The world itself does not call an LLM to render or animate.
Native translations keep their dedicated slot, consent, accounting and quota
checks.

Desktop and emulated mobile behavior were exercised. These runs do not certify
physical phone thermals, low-end GPU behavior or Raspberry Pi production load.
Paid translation fidelity and live voice-provider behavior were not inferred
from the inert proof adapters. The broader V1 scope remains described in
[the world implementation guide](WORLD_PROTOTYPE.md).
