# Private native functions in the world

The F5 implementation described below is the integration baseline, not final
experience acceptance. Its presentation is superseded by the owner clarification
below. F5 reuses the current settings identity/availability model and SettingsPane.
Each non-administrative section receives one placement among the existing
places or the transverse catalogue. Administrator entries are excluded even
for an administrator; administration remains in its ordinary application UI.
The living registry supplies labels and native rendering. Native endpoint
authentication/permissions remain the authority; spatial affordances add no
business grant and no owner identifier is sent by a station.

An explicit place button opens a private responsive DOM panel when the server's
current position is inside that place. The transverse catalogue also permits
accessible direct consultation, avoiding mandatory movement for keyboard and
assistive users. Only one private activity is open at a time. Its content is
mounted lazily and keyed by authenticated account. Changing account or losing
authority removes it. Remote world projections continue while local walking
is paused. No query string carries private state or a user-written prompt.

LIA opens the same conversation workspace as the chat route, under the same
auth, history, SSE, active-run, HITL, quota and media owners. Extract the existing
workspace rather than recreate these contracts. Embedded mode ignores chat
deep-link parameters on the world's URL, uses the available panel height and
never sends a message merely because a station or LIA was opened. Closing the
panel follows native stream detach/reattachment; it does not invent rollback
or cancellation of a job already accepted by the backend.

Qualification requires living inventory completeness, rejected administrative
tokens, unavailable flags, account replacement and no intent consumption in
embedded mode. Exercise at least one real owner data read/edit through the
native panel and one denied cross-owner attempt. Paid provider output remains
unqualified without an actual authorized supplier probe; fixtures cannot prove
translation fidelity or model behavior.

## Owner clarification: activities, conversations and configuration

Status: required next-stage experience, not implemented or accepted by the F5
embedding above. Reusing business services and form primitives remains required;
a generic settings catalogue is not the intended primary world experience.

Classify each exposed action by its purpose, not by the name of its existing
settings component. An object provides a contextual activity (read or edit a
memory, consult an agenda, work with documents); a compact HUD widget provides
an appropriate transverse activity; a separate settings menu configures behavior.
A mixed native section must expose the activity independently when feasible,
keeping configuration behind an explicit settings action. Preserve availability,
permissions and accessible alternative entry points; do not hide a capability to
make the separation look complete.

The settings menu groups world controls (input, display quality, reduced-motion
preferences where available) separately from LIA application preferences. It
reuses existing account settings and must not create a competing preference
store. Administration retains its existing permission boundary. Navigation,
conversation and activity controls must not become a row of settings shortcuts.

Widgets are optional, compact and collapsible: candidates include unread
conversations, native notifications and upcoming agenda/reminder items. Inventory
the existing read/refresh contracts before selecting them. Opening the world or
revealing a widget must not silently trigger synthesis, a provider refresh or
other paid work. Prefer existing data subscriptions and bounded reads, suspend
unnecessary refresh work when hidden, and clear owner data on account changes.
Widget layout must preserve the scene, minimap, touch controls and input focus.

Qualification must demonstrate an actual activity started from an appropriate
scene object, independently reachable configuration, available functions that
have not disappeared during the split, owner isolation and a narrow-phone layout
with the software keyboard open. These are pending acceptance criteria, not
additional test results.
