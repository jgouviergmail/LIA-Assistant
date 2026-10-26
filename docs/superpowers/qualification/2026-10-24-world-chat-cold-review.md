# World conversation — cold review

This review covers the delivered chat corrections, their shared notification
lifecycle dependency, and the private editor/session behavior exercised during
fault injection. It does not certify every possible fault or physical device.
The [execution ledger](2026-10-23-world-v1-ledger.md) records interrupted and
superseded runs separately from successful qualification.

## Findings and disposition

| Failure mode | Disposition | Verification |
|---|---|---|
| Disconnected notification streams retain Redis connections and eventually prevent mailbox/admission work | Shield bounded ASGI cleanup; release Pub/Sub before registry work; propagate cancellation | Actual ASGI cancellation during subscribe and poll, real Redis with a two-connection pool, native EventSource churn and post-run subscription inventory |
| Proof-host compression buffers native notification events | Mount existing application security middleware in the proof host | Immediate native EventSource connection event through the real Next BFF; no duplicate business header policy |
| An accepted send loses its HTTP acknowledgment during a socket interruption | Settle only the original owner, generation and intent; recover by reading | Real accepted HTTP send, socket close, lost response, one recipient message and one send request |
| Initial connection failure accidentally retains active authority | Derive active/recovering from prior admission and controlling authority | Initial-failure regression; read/write projections remain scoped |
| Escape on an automatic connection dialog unexpectedly leaves the world | Keep automatic recovery modal open; retain explicit leave | Connecting, reconnecting and unavailable regressions; real editor reconnect journey |
| Same-owner identity checks discard drafts or native editor state | Retain private Activity lifetime while hiding private surfaces | Healthy LIA draft/focus journeys; native memory and home editor journeys |
| Another account's cookie leaves the previous account's conversation visible | Hide while checking; destroy previous owner subtree after confirmed mismatch | Actual same-browser account change; server foreign-controller refusals remain in force |
| Restored controlled Select loses an unsaved choice | Reject Radix's transient empty event while a nonempty controlled value remains authoritative | Native FormData/Activity regression, explicit clearing/uncontrolled behavior, real home save/conflict flow |
| Recovery moves focus or incoming text scrolls a reader away from history | Restore focus only to the resumed visible owner surface; retain reader anchor/offset | Background-focus guard, resize/observer cleanup, incoming message and explicit latest-message navigation |
| Reduced motion still allows message entry to shrink a control before its first frame | Add message entry to the existing motion opt-out list | Frozen-first-frame regression failed at 41.8 pixels; nine real-browser detail-card cases passed after correction |
| Test harness reports unrelated failures on an insecure HTTP hostname | Use the E2E contract's loopback origin; deny real API fallthrough | Five unchanged failing journeys passed on the correct origin; full-suite results recorded separately |

## Security and ownership

Public world snapshots, private mailbox reads and private native application
panels retain separate authority. A temporarily missing socket scope cannot
publish a read made under an obsolete projection. A write completion can only
settle its still-owned intent; discard and disposal invalidate late completion.
A confirmed account switch destroys the old owner's private client lifetime.

The native qualification uses independent browser processes for separate people.
Only the deliberate account-switch/controller tests share a browser context.
Cookies, CSRF/Origin enforcement, SQL ownership, ordinary quotas and admission
limits stay native. No session keys, cookies, message payload traces or runtime
environment files are published as evidence. The source snapshot is scanned
from the actual Git index before handoff.

## Resource and failure boundaries

The fix removes leaked connections rather than increasing pool capacity. Cleanup
has the native Redis socket deadline; failed registry cleanup leaves expiring
markers rather than an unbounded shutdown task. The regression with real Redis
asserts that repeated disconnects work even with only two pooled connections.
The post-browser inventory checks that the original accumulating subscriptions
are gone. Native stream compression behavior is shared with the normal app.

Movement, rendering and decorative atmosphere do not start model calls. The
translation proof uses explicitly labelled authored text without billing. It
qualifies delivery, ownership, retry boundaries and accounting integration, not
real supplier linguistic fidelity. Physical device load and rendering quality
remain separate from software correctness.

## Acceptance evidence

The [final native matrix](assets/world-v1-lot7/final-native-delivery.json)
contains the successful Chromium, Firefox and WebKit journeys, with no retry.
The [software gates](assets/world-v1-lot7/software-gates.json) distinguish the
broader suites and their measured coverage. Their final refresh follows the
completed executions, never an estimated count.

Physical Pi/phone behavior, sustained thermals/battery, real translation-provider
quality and owner acceptance of final art remain unqualified. Software passing
is not a claim of perfection or a hardware-performance guarantee.
