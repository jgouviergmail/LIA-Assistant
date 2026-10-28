# Compact World social interface qualification

Date: 2026-10-28. Scope: the existing working checkout; unrelated staged and
unstaged changes retained. No commit, push or deployment.

## Resulting behavior

- The desktop quick bar and the full conversation panel share one mailbox client,
  account boundary, drafts and explicit translation consent.
- Phone and short landscape layouts start with the bar hidden. Chat folds the
  world controls and opens the bar; recent history can be reduced, the full
  conversation opened, or the bar closed without losing the addressed draft.
- Automatic selection uses the nearest reachable participant within the approved
  radius, otherwise the existing public audience. Composing and delivery pin the
  address; no private draft is implicitly published.
- Folded controls expose every existing social gesture with native touch targets.
  The sky/date line has additional separation from presence.

## Behavioral evidence

RED was observed for missing proximity projection, seated participants, direct
gesture buttons, compact controls, stable drafts, expanded-panel focus return,
scene-height budgeting, phone opening and the request to fold expanded controls.
The corresponding focused suites then passed. The final targeted messaging,
controlled-HUD and shared-world run passed 30 tests across three files.

Independent review found and resolved four issues: hidden history marked read,
recipient capture during expansion and delivery recovery, focus restoration to a
remounted opener, and duplicate-name disambiguation. New component/helper
boundaries keep changed functions below the frontend hotspot threshold.

## Browser evidence

The hermetic [social journey](../../../apps/web/e2e/smoke/world-compact-social.spec.ts)
uses controlled API and socket traffic and checks initial visibility, native
hit tests, control collisions, draft transfer, reduction/closing/reopening,
private/public transitions and the date/presence gap. The viewport matrix is
390x844, 320x568, 568x320 and 1280x900.

The final matrix passed all 12 cases in Chromium, Firefox and WebKit, including
Chat from expanded mobile controls. One early Chromium 320px development-server
run lost its world stylesheet after folding controls; that run had no trace, so
its cause remains unclassified. Three subsequent traced repetitions passed with
no failed CSS responses, followed by a complete green Chromium matrix. Geometry
and hit-test assertions were not relaxed and no arbitrary delay was added.

WebKit initially exposed a pre-existing global Firebase rejection before world
admission, with no compact component mounted. The optional Firebase configuration
was made inert only on the owned QA server, matching the hermetic test boundary;
no browser errors were filtered and no application environment file was changed.
All browser engines then passed the complete initial matrix.

The existing native mobile full-panel journey now expands the quick bar before
checking the full panel. Its TypeScript check passed. The real-service native
suite was not rerun; this change adds no backend permission or protocol.

## Final gates

- `task test:frontend:coverage -- --maxWorkers=8`: exit 0; 15,026 tests across
  1,311 files. All configured aggregate and scoped floors passed. Measured
  statements 87.06%, branches 81.74%, functions 85.29%, lines 88.59%.
- `task lint:frontend`: exit 0, including accessibility, strict hooks, complexity,
  double assertions, catalogue consistency and non-incremental TypeScript.
- `task lint:docs:preview`: exit 0 over tracked plus unstaged files.
- `task lint:docs lint:i18n`: exit 0 on the final index and working files.
- Non-incremental TypeScript after QA artifact cleanup: exit 0.
- The focused browser matrix passed 12 cases across the three installed engines.

The initial full lint was blocked by pre-existing references to files absent
from the Git index. The documentation preview cleared those references; the
final indexed documentation gate also passed after concurrent staging. No links
were removed and this task staged no unrelated file to bypass that check.

## Isolation and cleanup

Browser checks use an owned local Next server with a separate build directory.
No shared Docker service or cache is restarted. The owned server is stopped and
its generated nested AGENTS file and temporary tsconfig includes are removed;
diagnostic specs remain outside the Playwright test directory. Screenshots and
full command output remain in task-specific ignored proof directories.

A concurrent staging operation captured the two generated Next artifacts. Their
exact Git hashes and the tsconfig-only include diff were verified before a
scoped restoration, with an index backup and before/after entry manifests.
Every other index entry remained identical. The generated paths are clean in
both the index and working tree.
