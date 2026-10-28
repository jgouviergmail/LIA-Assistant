# ADR-365 — Private native LIA in an authoritative isometric world

**Status**: accepted design, implemented behind the native World capability;
physical-device and paid translation fidelity qualification remain release gates.
**Date**: 2026-10-23

**Amends**:
[ADR-067](ADR-067-Account-Lifecycle.md) adds owner preference and ephemeral World cleanup to account revocation/deletion;
[ADR-145](ADR-145-Account-Export.md) includes owner World preferences in native account exports;
[ADR-280](ADR-280-Complete-Capability-Control.md) adds World to the complete platform capability registry;
[ADR-339](ADR-339-Application-Commands-With-Current-Authority-And-Secure-Continuations.md) adds a private spatial entry to existing native activities, retaining their current authority and approval boundaries.

## Context

The owner wants a generous, pleasant social world as another way to use LIA,
inspired visually by MalinosLand. Browser drawing must remain affordable on
ordinary computers and phones while LIA is hosted on a Raspberry Pi. Shared
presence must never share assistant context, personal decoration or messages.
The prototype alone did not establish final visual quality or hardware capacity.

## Decision

Keep the original Canvas 2D isometric renderer, independent authored scene,
navigation, input, simulation and DOM interface. Cached repeated drawing, viewport
culling, bounded resolution/particles and an elapsed-time render cadence limit
client work. There is no server video renderer or additional engine dependency.
Map size is independent of viewport size; camera follow/pan, anchored zoom and
minimap retain open space. LIA uses its existing native eyes and mouth with
original directional body art. Localized controls, conversations and accessible
interaction labels use DOM text; cached Canvas nameplates retain only public
names and decorative marks.

The `world` bounded context owns one authoritative instance state in Redis CAS.
Native session cookies obtain one-use tickets; WebSocket authentication uses the
first frame, never URL credentials. Version, epoch, controlling-tab token,
sequence, live leases, native account/operator policy and bounded messages fence
commands. Native owner row locks serialize admission with deletion/deactivation.
Capacity, FIFO offers and all deadlines come from the
[world settings](../../apps/api/src/core/config/world.py), not client claims.
Redis failure suspends authority; there is no process-local substitute world.

Shared projections contain the consented native account name, chosen appearance
and public actor movement only; World does not offer a separate pseudonym.
Assistant, home, weather, peer-directory and human-message projections stay
owner/participant scoped. Home preferences currently change only the colour
palette, following the owner's simplified scope. Undeployed motif/placement
contracts and their artwork are removed; no memory or interest source is read.
Colour edits use owner/revision checks and native export/deletion
lifecycle registration.

Function placement derives from native settings/search/command inventories.
Existing panels and the ordinary conversation workspace preserve authentication,
capabilities, HITL, registers, accounting and quota behavior. A station/command
selection only opens a private panel or prepares a draft. It never sends or
executes implicitly, consumes a host URL intent or bypasses native approvals.

Human text has ephemeral private Redis bodies and durable content-free SQL
attempt fences. A dedicated translator slot uses native model resolution, spend
guard and token accounting, a strict versioned prompt, bounded context/output,
one transport attempt and no content tracing. Only explicit consent can start a
paid translation; failed/uncertain attempts never replay automatically. Recipient
language changes do not cause a paid request. Variant capacity is reserved before
dispatch, and usage receipts remain private to their payer. Human text is neither
assistant history nor learning material.

Atmosphere borrows only fresh native cached weather and account timezone with a
server clock anchor. No provider/model call or location is needed for decoration.
Accepted, unblocked peers receive a coarse World connection status: online,
inside the private home, away after ten minutes of inactivity, or offline.
A private controller-fenced connection lease supplies it; neither native session
TTL nor assistant activity is evidence of World presence. Idle eviction still
releases capacity, while a live socket retains away status until explicit
readmission or disconnect. Visible actors also remain in the private directory.
Consent names this coarse home/presence disclosure; positions and home contents
never enter the directory. Failed refreshes show unavailable rather than offline.

## Consequences and qualification

The browser carries drawing; the server carries bounded native authority and
ordinary LIA work. A replacement renderer can reuse the typed scene and commands.
No speculative ECS, scripting/plugin framework, voice, federation, timed visits
or shared furniture physics is introduced by this V1.

The guided installer asks the operator whether to offer World and writes its
deployment ceiling, `WORLD_ENABLED`, with a disabled default. Older answer/state
files retain that default; reconfiguration keeps the recorded choice and tuned
authority settings. The native operator switch and participant consent remain
independent checks. World reuses the existing SQL/Redis and boot migration path;
neither a companion service nor another instance credential is provisioned.

Account changes, authority/capability loss, backgrounding and disposal are explicit
lifetimes. Tests cover protocol attacks, reconnect/control races, native SQL/Redis
privacy and revocation, billing fences, responsive native panels, touch and all
three browser engines. The
[technical guide](../technical/WORLD_PROTOTYPE.md),
[execution plan](../superpowers/plans/2026-10-23-lia-world-v1.md) and
[qualification ledger](../superpowers/qualification/2026-10-23-world-v1-ledger.md)
record measured evidence and remaining release limits. Browser emulation cannot
certify a physical Pi, phone thermals/battery or supplier linguistic fidelity.

## Amendment: interactions, arcade and private photos (2026-10-27)

Private exploration preferences use revision-checked owner persistence. Discovery
is derived from the current function/scene catalogue; the optional route and
introduction do not execute assistant actions. A generic table offers the normal
dashboard only after confirmed seating and explicit acceptance; declining keeps
the pose. Signals and LIA's acting state consume bounded native presentation
sources. Ten editable starting appearances, deterministic seasons, finite scenery
interactions and finite public emotes introduce no model call or learning input.

Arcade commands share the existing authoritative socket sequence. Participant-only
projection, current round/revision/controller/epoch fences, fresh canonical account
policy locks and bounded idempotency receipts protect human consent and legal
moves. The computer uses bounded deterministic search rather than an LLM. No
winner, move or board is inferred optimistically by the browser. Explicit rejoin,
limited reconnect grace, expiry and complete selective account erasure are part
of the game lifecycle. See the [World technical guide](../technical/WORLD_PROTOTYPE.md)
for contracts and the native UI host.

Photos use an independent allowlisted still and renderer; copying the live Canvas
would leak visitors or overlays. A bounded local JPEG preview precedes any explicit
share. Native shells advertise the capability positively and validate bytes before
private expiring-cache storage. A separate Android provider exposes only those
files; iOS uses an anchored system activity sheet. Browser and native outcomes do
not assert downstream publication. No server upload, photo persistence, memory
extraction, prompt or new token cost is introduced by these presentation features.

The [implementation qualification ledger](../superpowers/qualification/2026-10-27-world-interactions-and-play.md)
separates source/tests/browser evidence from physical-device and performance
qualification. iOS compilation and actual native chooser behavior remain release
gates until performed on appropriate hosts and devices.

The [feedback refinement](../superpowers/qualification/2026-10-27-world-feedback-refinement.md)
keeps these boundaries: zoom-aware cover cropping and compulsory photo signature,
finite public lamp/screen appearance, shared device widgets and approached local
decor reactions. Workout furniture uses the same authoritative lying/standing
contract and shared occupancy rules; private furniture remains scoped by its
home geometry. Expanding a toolbar is not opening a private panel and does not
disable sibling widgets. No new provider, memory, quota or persistence surface is
introduced.

## Amendment: protocol generations, integrity failures and the policy fence (2026-10-28)

A client is told what kind of failure ended its socket. A frame whose envelope
declares another socket protocol generation closes 4426 so the client reloads
instead of retrying; the generation is read before strict validation, and an
outdated authentication frame consumes no ticket. Any other invalid frame, and
the frame-rate refusal, closes 1008. A record a transition produced that the
strict reader refuses is a server defect: it raises a dedicated integrity error,
is never published, is logged by its rule code alone and counted on the
[World arcade dashboard](../../infrastructure/observability/grafana/dashboards/32-world-arcade.json),
and closes 1011. A stored record of another generation keeps the reader's own
error, which account erasure uses to try the declared older generations.

Game commands hold the canonical account fence through the one Redis commit,
a deliberate and bounded exception to
[ADR-304](ADR-304-No-Transaction-Across-A-Network-Call.md). Contact policy is
written in SQL (block and unblock, deactivation, deletion, the World capability)
while the game is committed in Redis, and only a serialization point spanning both
keeps a block committed after the policy read from being overtaken by a move it
should have refused. Releasing the fence before the commit reopens exactly that
window. A Redis-side marker would have to be written by every policy writer before
its own commit, moving the network call into more transactions — the peers pair
fence, the account lifecycle, operator switches — and making those domains depend
on World. The fence therefore stays, and is held to what it needs: lock
acquisition and policy reads within `WORLD_POLICY_TIMEOUT`, the commit within
`WORLD_AUTHORITY_TIMEOUT`, the outer deadline their sum, with the server's lock and
idle-in-transaction bounds as backstops; `FOR NO KEY UPDATE`, so it orders policy
writers and every UPDATE or DELETE of those accounts but never an insert merely
referencing them; and a command refused before the commit (input cap, disabled
arcade) takes no fence, no cookie revalidation and no computer search. The
[peers pair fence](../../apps/api/src/domains/peers/pair_fence.py) uses the same
strength: as `FOR UPDATE`, a share write holding the pair row and a block holding
the fence waited on each other and PostgreSQL aborted one (40P01), reproduced on a
real server before the change.

A policy-hidden cabinet now reads as full, like any full table, and only a
joinable cabinet carries the round fence a join needs: a distinct state disclosed
the block. An accepted join is a new pairing on the canonical fresh board (host on
the first color), never a continuation of a solo rematch's alternation. A
finished table can be explicitly rejoined while its result is displayed.

The introduction was retired with discovery and the decorative-actions menu. The
private experience document is exactly `{version, revision, show_route,
season_mode, hemisphere}`; a stored document still carrying the introduction's
fields is unsupported and reads as needing the existing explicit repair. The
contract was never released, so no migration accompanies the change.

## Amendment: private activities outlive a revalidation, a reconnection and a copy (2026-10-28)

A private native activity keeps its effects for as long as its account does. A
revalidation of the identity — on focus, on visibility, on another World tab's
notice — runs in the background for an owner a read has already confirmed: the
private subtree stays visible and mounted, and only a read that fails, or that
names another or an inactive account, withdraws it. Hiding it on every return of
the focus placed it under a hidden `Activity`, whose effect cleanups cancelled a
streamed answer and ended a Live session. A transport reconnection keeps the
private panels mounted for the same reason, marked busy under the reconnection
dialog; the retained seated dashboard is keyed by its owner alone, so opening the
conversation panel no longer remounts it and never buys a second synthesis. Until
a read confirms the owner, the subtree stays hidden, as before.

A refused gesture is said, never dropped: the receipt is read like a pose's, a
gesture within its own duration is refused in the browser before any frame is sent,
and both outcomes reach one status region in the person's language.

The translator's one-attempt copy of a factory-cached model is lent for exactly
one call (`infrastructure/llm/single_attempt.py`). On Gemini the copy shares the
cached instance's client, and the adapter closes `self.client` when an instance is
collected: the copy's reference is released when the call ends, so concurrent
callers keep an open client and an interrupted request is never sent twice.

The photo's mandatory signature names the project's website through one declared
attribution module (`apps/web/src/lib/project-attribution.ts`). The host-neutral
release guard of [ADR-215](ADR-215-Self-Host-Installer.md) holds that module to its
single reader, so the project's address can never become a deployment origin.
