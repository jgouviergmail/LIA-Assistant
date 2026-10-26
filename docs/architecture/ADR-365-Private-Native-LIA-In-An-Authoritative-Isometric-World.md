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
