# World presence and controls qualification

Date: 2026-10-26. Scope: the follow-up to the
[staged review corrections](2026-10-26-world-staged-review.md).
See the [technical guide](../../technical/WORLD_PROTOTYPE.md) and
[human voice proposal](../specs/2026-10-26-world-human-voice-proposal.md).

## Delivered contract

The French product name is “Le monde de LIA”. The private accepted-peer directory
shows online, home, away and offline with green, red, light orange and gray markers
and accessible translated text. It includes visible actors and never uses native
login TTL as World connection evidence. Entry consent explicitly names this coarse
presence/home disclosure. Private home contents and peer positions remain private.

Away starts after ten minutes of inactivity. Idle admission eviction still frees
capacity; an idle live socket retains away status without automatically readmitting
its actor. Heartbeats extend connection life without resetting human activity.
Disconnect withdraws only its own fenced presence, including during failed socket
startup. Missed heartbeats expire the bounded lease. Account revocation/deletion,
blocks and controller changes retain the existing native privacy boundaries.

Desktop follow/camera/zoom controls align with bottom actions, with bounded icon
controls at narrower desktop widths. LIA and peer discussion docks both leave the
focused scene movable. Text input retains its draft and never controls movement.
Modal activities and compact layouts still pause the scene. The redundant game
voice widget is removed; the application menu retains normal voice behavior.

## Red-to-green evidence and cold review

Real browser regression tests reproduced the vertical control mismatch and blocked
peer movement. A separate LIA conversation test reproduced its remaining pause.
All fifteen desktop cases passed on Chromium, Firefox and WebKit after correction,
at desktop widths from narrow tablet-sized layouts to wide desktop layouts.
Both drafts remain intact while the canvas moves, and arrow keys in either input
do not move the scene. No model request is needed for these tests.

The complete frontend coverage run passed 14,650 tests across 1,235 files, with
86.09% statements, 80.79% branches, 84.33% functions and 87.62% lines. Every global
and scoped floor passed. Backend World unit tests: 167 passed, including 100%
statement and branch coverage of the new coarse presence module. All 82 World
integration tests passed against disposable SQL/Redis, without infrastructure
skips. Strict backend typing passed across the application and typed test seams;
application and E2E TypeScript also passed.

The contract documentation ratchet remains at zero undocumented functions or
wire fields; six-language key parity, code hygiene, backend/frontend complexity,
hook, accessibility and double-cast ratchets passed. The marker gate found no
new orphaned tests. No threshold or debt baseline is increased.

Cold review covered stale controller teardown, epoch mismatch, idle reconnect,
home/away precedence, pre-presence state round-trip, policy revocation, capacity
release, bounded connection state, public snapshot exclusion, and failed directory
refresh. Directory refresh is serialized, paused while hidden and aborted on
disposal. Failed refresh retains focus/list state and labels status unavailable.

Further cold review found and fixed two regressions with failing tests first:
account erasure initially skipped a presence-only idle account, and transport
resume initially reset its human inactivity deadline. Erasure now removes idle
presence while preserving peers; automatic resume retains last human activity.
The existing cancellation-safe writer can report background settlement when the
ASGI test client cancels repeatedly; the disconnect regression waits for and
verifies its completed offline transition.

Browser runs against the recreated proof host passed:

- 44 hermetic interface/focus/settings/desktop cases; four existing non-Chromium
  simulated Live start cases remain explicitly excluded. Application-menu voice
  starts are tested on Chromium and navigate through the native chat route.
- 21 final layout cases across Chromium, Firefox and WebKit, including six touch
  rotation scenarios with enlarged text and real hit tests. A desktop-width touch
  collision found during review is corrected by raising the joystick above the
  action bar while keeping camera tools aligned.
- Six light/dark contrast and keyboard navigation cases on the same three engines.
- Three native SQL/session/World socket journeys, checking the accepted-peer
  directory pagination, actual online/offline statuses, private authority denial,
  native draft behavior and responsive controls.

The layout run retains browser notification-stream errors printed during fixture
teardown; its in-scenario console checks and assertions pass. These messages are
not evidence of a production notification defect. The native captures were also
visually inspected for readable status labels and unobstructed desktop controls.

Documentation preview passed with no broken living links, stale living paths,
or living orphans. Formatting, strict types and whitespace checks passed. The
normal index-based gate still sees the original inventory until owner staging.

## Qualification boundaries

Disposable Docker SQL/Redis and three desktop browser engines qualify the code
paths; they cannot establish physical phone audio, Pi thermals/battery or audible
human calls. Direct human voice remains a proposal, with no provider purchase,
microphone implementation or deployment in this delivery. Existing rendering
hardware limits remain documented in the earlier qualification.

The original index is preserved. Documentation checks must use the repository's
preview mode until the owner stages new/moved files. No commit, push or deployment
is performed by this work.
