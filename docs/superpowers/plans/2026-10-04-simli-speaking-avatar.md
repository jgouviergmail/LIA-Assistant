# Simli speaking avatar — implementation and TDD record

Date: 2026-10-04. Execution is strictly inline. No agent, commit, push or production
deployment is part of this work. The concurrent working tree is preserved.

The [design analysis](../specs/2026-10-04-simli-speaking-avatar-design.md) records
the source inspection, decisions, risk matrix and original acceptance criteria.
The [integration guide](../../technical/SPEAKING_AVATAR.md) describes the actual
implementation. The [qualification record](../specs/2026-10-04-simli-media-qualification.md)
separates automated evidence from the device trials assigned to the owner.

## Scope and final decisions

- A personal encrypted Simli connector, explicit account opt-in and face selection.
- One movable window with small, medium and large presets, touch and keyboard controls.
- A persistent connection while voice comments, Live or Live direct are active.
  Live takes priority; standby closes Simli and suppresses comments; wake opens again.
- Exclusive audio routing at each production boundary. A cold production stays local.
  Interruption sends SKIP; session teardown sends DONE. Silence never ends a mode.
- PCM and native WebRTC paths share bounded DSP and playback ownership contracts.
- Radio is deferred. Psyche decoration is omitted: it does not improve generated
  facial motion, and Compose has no verified facial emotion or gaze command.
- No additional LLM, prompt or synthesis; no platform key or personal Simli billing ledger.

## Atomic lots and review gates

Each retained lot followed behavioral RED/GREEN tests, refactoring and an inline
cold review before the next implementation lot. Paths below are the delivered
boundaries, replacing the provisional filenames in the original plan.

| Lot | Implementation | Behavioral evidence and adversarial review |
|---|---|---|
| 0 — native contracts | Live transport callbacks and borrowed stream ownership | Late callbacks, replacement, autoplay rejection and teardown; SDK capture seam inspected before its amplitude filter. |
| 1 — declarations | Connector category/type/verifier, user preference, feature/capability registries, cost bearer, migration, six locales and dotenv profiles | Closed registries extended; default opt-out; key rotation preserves face while dropping obsolete verification; migration replay validates comments and downgrade. |
| 2 — protected API | `apps/api/src/domains/avatars/`, shared `apps/api/src/infrastructure/simli.py` | Fixed origin, bounded HTTP/ICE/token payloads, no paid POST retry, strict HTTP body, owner identity, no-store, detached DB units, digest-scoped Redis CAS and UNKNOWN quarantine. |
| 3 — voice port/DSP | `apps/web/src/lib/voice-output/`, AudioQueue seam | Actual sample rates, anti-alias attenuation, block equivalence, endian/clipping/channel mix, weak audio/interior silence, FIFO, finite pacing/backpressure and no prefix replay. |
| 4 — Simli runtime | `apps/web/src/lib/avatars/` | Signalling/ICE races, first video frame plus audio unlock, independent connection/phrase epochs, persistent demand, SKIP/DONE, finite sequential renewal and cleanup. |
| 5 — settings/window | `apps/web/src/components/avatars/`, AvatarSettings, geometry store/shared drag hook | Account isolation, cancelled/late save, preserved focus, viewport bounds on appearance, batched drag commit, derived Eyes suppression, production CSP. |
| 6 — comments | Voice SSE boundary and existing AudioQueue | Claim before decode, immutable destination, late completion/stop, replay suppression, Radio/meeting priority preserved. |
| 7 — PCM Live | RoutedLivePlayer and controller seams | Delegated/direct EOF versus transcript quiet, handover, standby/wake, malformed/rate-changing input, bounded next-generation buffering and late drain. |
| 8 — native Live | Receive-only AudioWorklet and exported ElevenLabs adapter | Unfiltered weak speech, interior silence, borrowed tracks never stopped, output fallback without replay, hot opt-in boundary, capture flush epochs, cancelled SDK import. |
| 9 — psyche | Deliberately omitted | Existing prosody remains authoritative; no new prompt, inference, memory or invented provider control. |
| 10 — qualification | Cross-contract guards, integration, coverage, lint, browser flows, guide and ADR | Real local WebRTC media under production CSP; physical realism, latency and hardware validation remain the owner's separate acceptance work. |

## Test director

| Risk | Unit/component coverage | Real infrastructure or browser coverage |
|---|---|---|
| Credentials/authorization | `apps/api/tests/unit/domains/avatars/` validates strict commands, repr masking, capability off, account/key/face epochs and authenticated HTTP contracts | `apps/api/tests/integration/domains/avatars/` uses encrypted PostgreSQL records and real Redis claims; vendor HTTP is simulated. |
| Duplicate paid sessions | Concurrent claims, CAS, UNKNOWN, cancellation before/after POST, provider count, release identity | Redis contention across owners; no real paid session is created. |
| Audio quality/order | `apps/web/src/lib/voice-output/__tests__/` covers DSP, sample clock, backpressure, weak samples, clipping, malformed bursts and FIFO | `apps/web/e2e/fixtures/simli.ts` carries generated audio and canvas video over a genuine local RTC peer. |
| Lifecycle/concurrency | `apps/web/src/lib/avatars/__tests__/` covers stale mint/ICE/frame/heartbeat, source takeover, renewal, opt-out and teardown | Comments and Live browser journeys verify a single persistent mint, standby close and new wake connection. |
| Native capture | Actual adapter/transport contracts, module import cancellation, flush and borrowed-track ownership | OpenAI-shaped local WebRTC plus exported ElevenLabs adapter tests; real providers and devices are not inferred from mocks. |
| UI/accessibility | Rendered provider/window/settings, persisted geometry rejection, focus, visual viewport and shared drag | `apps/web/e2e/smoke/speaking-avatar-comment.spec.ts` checks viewport sizes, keyboard/pointer movement, audio exclusivity, storage and axe. |
| Existing voice behavior | AudioQueue/PCM/controller/transport/hooks and SSE regression suites | Existing chat/voice/Live browser journeys with avatar disabled plus the full dashboard suite. |
| Platform contracts | Capability, user export/purge, cost bearer, feature registry, demo route decisions, CSP and six-language parity | Migration replay, Taskfile hygiene/marker/CI/lockfile gates, production build and coverage floors. |

Simulations explicitly exercise lost network, refused/malformed/oversized provider
responses, timeout after a potentially accepted POST, Redis failure, stale tokens,
account switch, key rotation, autoplay denial, media not ready, late callbacks,
interruption, silence, queued EOF, standby/wake and finite-cap renewal. Tests do
not claim that a mocked provider proves real lip motion or mobile audio behavior.

## Regression and quality discipline

The port is introduced at existing output seams; no new agent, tool manifest,
LangGraph state, prompt or conversational memory is added. Radio and meeting
priority remain in their existing owners. Errors after a potentially heard prefix
do not replay the phrase. A future boundary can select local output.

No coverage floor, a11y/hooks/complexity cap or strict registry invariant is relaxed.
Coverage is extended for the new DSP/output scope. Measured complexity improvements
are locked by shrink-only ratchets. New tests retain real CI markers.

Development/production dotenv files and encrypted profiles carry the same operator
declarations. Demo/example/test profiles remain opt-out by default. Long-lived
Simli keys are never placed in those files or browser storage.

## Remaining external acceptance

The owner explicitly undertakes Android and iOS trials. The qualification record
provides the checklist and unchanged proposed AV/latency acceptance criteria.
No new paid session is opened to substitute for those trials. Vendor silence,
actual finite-cap renewal, mobile audio output and real facial realism remain
measurement requirements, not implementation claims.
