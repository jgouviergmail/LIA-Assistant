# World mobile, appearance and social interactions

Status: approved for inline implementation on codex/lia-world-prototype.
Preserve concurrent changes and the existing public preview. No deployment or merge.

## Accepted decisions

1. Mobile: folded HUD, contextual action, optional analog joystick (auto/show/hide). Keyboard and tap navigation remain available. Local device preference contains no account content. Panels pause local movement, never deliberately reduce visible animation to 5 fps.
2. Identity: account full name; explicit visibility consent; neutral fallback, never email. Finite versioned appearance, explicit choices only, separate persistence from home colors. First entry and private studio mirror use the same editor.
3. Bubbles: five-second previews with replacement; no additional translation/model call. Private text is restricted at server projection. Proactive LIA events reuse native notifications and deduplicate transport deliveries; full text remains in the native history.
4. Public discussion: explicit audience, eligible current-world recipients frozen at send, blocks and private-space visibility respected. Translate once per target language with native spend controls. No newcomer replay.

## Execution sequence and gates

### Lot 1: mobile and rendering
Red tests for panel cadence, joystick boundaries/cancellation, preference fallback, compact HUD.
Implement small components using native controls and six locales. Verify types/lint, targeted and broader tests, real desktop/mobile geometry and animation. Cold review input ownership, focus, lifecycle, work per frame. Publish preview.

### Lot 2: identity and appearance
Red tests for strict finite DTOs, account ownership/CAS, first-entry flow, mesh variants and mirror.
Implement account-scoped persistence and finite public appearance projection; upgrade all producers/consumers together. Verify SQL/Redis integration, malformed input, cross-account isolation, backward compatibility, cancel/save and real mobile editor. Cold review projection and caches. Publish preview.

### Lot 3: private and proactive bubbles
Red tests for delivery scope, expiry/replacement, duplicate notifications, owner changes, deferred display and safe text.
Reuse mailbox/notification contracts and local companion navigation. Verify two independent accounts and non-recipient exclusion, panel timing, long messages, reconnect and reduced motion. Cold review confidentiality, time and ownership. Publish preview.

### Lot 4: public discussion
Red tests for audience admission, frozen recipients, blocks, private homes, distinct-language translation reuse, idempotency and bounded history.
Extend native durable attempts/mailbox and typed UI; avoid simulated client broadcast or repeated private sends. Verify real SQL/Redis workers with inert translator, independent sessions and all browsers. Cold review billing, partial failure, cancellation, reconnection and privacy. Publish preview.

## Quality objectives

No provider calls in automation; no extra model calls for decoration or bubbles. Strict types, six-locale parity, bounded storage/work, native authentication and permissions. Ratchets may only tighten. Hardware FPS claims require measurements on that hardware. Final report distinguishes measured checks, skipped checks and limitations.


## Lot 4 implementation refinement after native-contract inspection
The public channel is an explicit audience, not a synthetic peer UUID. Keep the
private mailbox projection and its history budget intact; add a separately bounded
public projection to the same authenticated read response and reuse the existing
client lifetime, immutable intent, lost-ack/status and unread machinery.

Freeze the live eligible audience at acceptance, excluding private studios and
bilateral blocks. Atomically stage one ephemeral public record and its owner
indexes. A newcomer never receives an old index entry. Recheck native policy,
controller, language and visibility around translation; expose no recipient list,
account identifiers or controller material in the public DTO. Extend selective
account erasure to these bodies and indexes, and isolate a corrupt public cache
from private correspondence.

Public messages have a short game-chat limit. Foreign languages are deduplicated
and translated in one strict structured batch using the existing translator slot,
native quota/accounting, single provider attempt, bounded fair SQL queue and
persistent idempotency tombstone. Same-language display is immediate and free.
No automatic paid retry, language-change resend or original-text fallback. A
failed translation is stated; original text is an explicit native-history action.

Keep public/private drafts, read positions and consent choices separate. The
public channel is visibly labelled; its ready deliveries reuse the owner-local
speech presenter (including the sender's own public echo). Native LIA discussion,
private studios and parameter menus retain their confidentiality boundaries.

## Delivery status
All four approved lots are delivered in the isolated world worktree and retained
local preview. The technical prototype guide describes the final boundaries.
The execution ledger records test-first failures, cold-review corrections, native
multi-engine proof, source publication hashes and selective Docker cleanup.
Physical-phone/Pi benchmarks and paid-provider translation quality are explicitly
outside the measurements performed here; the delivery does not claim them.
