# Private home implementation contract

The shared floor remains immutable. V1 editing moves catalogue decorations
between six authored furniture/display anchors and changes the home palette;
it never changes shared collision footprints. A selected decoration is rendered
within its furniture's sprite. This keeps server and client navigation equal
without turning cosmetic editing into a physics or shared-layout operation.

One nullable `users.world_preferences` JSONB column follows the native briefing
preference pattern. Strict, bounded writes hold the fresh owner row lock and
compare the expected revision. Export includes these explicit preferences;
account deletion scrubs them. The general profile update cannot write the field.
Only the authenticated owner's `/world/home` interface can read/write it.

Automatic decoration is derived, never persisted as a second memory. Read only
the bounded active source set, without vectors, learning counters or provider
calls. Structured display preferences choose the default palette. Non-sensitive
active interest categories and conservatively recognized affirmative preference
memories contribute catalogue motifs. Invalidated, sensitive, procedural,
negative, unsupported and disabled sources contribute nothing. The selector is
deliberately incomplete rather than inventing a semantic interpretation.
The native learning/notification switches do not revoke reads of existing
interests or memories. The home never restarts these subsystems; its own
automatic-decoration switch and the owner's memory-use preference govern reuse.

The private response has an owner fence and a digest of selected source/motif
identities. A relevant source change replaces only automatic decoration;
explicit catalogue choices remain manual choices. No original text, source
digest, palette or furniture choices enter shared snapshots. Refresh on load,
focus and return from native source panels; ignore stale owner responses.

Acceptance: real concurrent SQL saves, conflict/reload/cancel/reset, malformed
payloads, source invalidation and feature opt-out, unchanged learning counters,
owner isolation, explicit-choice preservation, export/deletion classification,
and the same collision catalogue before/after every cosmetic preview.
