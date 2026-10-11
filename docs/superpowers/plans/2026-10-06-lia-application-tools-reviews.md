# LIA application tools: inline cold reviews

This record accompanies the [implementation plan](2026-10-06-lia-application-tools.md).
The work remains in progress. A slice review does not establish complete interface
parity or production qualification.

## Lot 3: account preferences and saved locations

Reviewed the native preference catalogue, input and projection schemas, encrypted
command lifecycle, draft rendering/modification/confirmation, shared profile and
assistant preference owners, layout owners, location resolution, consent fences,
SSE invalidation, authenticated refresh and the consuming frontend hooks.

The adversarial review reproduced and corrected these defects:

- An expired or obsolete pending proposal could reach the modification model.
  Edit and execution now share catalogue, canonical intent and expiry validation.
- A proposal expiring during modification could be revived by replacement.
  PostgreSQL replacement now conditions the write on current expiry as well as
  ownership, pending phase and the original digest.
- A late write failure could replace the next account's optimistic edit, and
  returning to the original account could revive an old preview or callback.
  List and home-location state now use one opaque account-lifetime owner.
- A late home save could erase another account's unsent address or show its toast.
  Current lifetime checks precede requests and publication of their results.
- Shared mutation diagnostics included private request payloads. Diagnostics retain
  method, endpoint, status and error without copying the payload.
- A saved voice opt-out could be ignored by a frozen stream-start profile.
  All existing voice-start paths reread current active-account consent.
- Each home geocoding lookup leaked its owned HTTP client. Cleanup now runs after
  successful and failed lookups without replacing the outcome or paid usage.
- The modification coordinator exceeded the complexity policy. The pure intent
  transformation is now separate from authorization and durable replacement.

Evidence lives in the application unit suites, the PostgreSQL command lifecycle
and draft-editing integration suites, the geocoding accounting suite, and the
real frontend hook/component suites. PostgreSQL tests use disposable services;
provider/model responses are deterministic doubles. Full-dispatcher effect-ledger
tests use a simulated ledger, which must not be reported as a real-ledger probe.

The complete frontend coverage run and frontend lint, types, accessibility, hook
and complexity gates pass after these corrections. Current application tests,
ownership tests and size/cycle gates pass. No quality ceiling was raised.

Global backend qualification remains separate: concurrent journal/MCP edits
produced transitive type errors, journal state-contract characterization failures
and a journal complexity regression. Preserve those changes and rerun the global
gates during final qualification; their failures are not accepted as a green gate.

Remaining feature scope belongs to subsequent lots: communication/security and
automation, learning management, extensions/assets, administration, addressed
device commands, protected contexts, full interface parity and final release
qualification. Saved account font preferences are covered here; a device's
unsaved preview and actual application acknowledgement require the device lot.

## Lot 4: heartbeat slice, review in progress

The shared domain command now owns the five HTTP preference fields, canonical
refusal lists, null-as-omission, explicit empty-list replacement, a current active
account lock and compare-and-set against the displayed snapshot. Reads reuse the
UI projection and separately expose the delivery platform switch. The UI permits
saving preferences while the platform is paused; native preparation follows that
contract. Saving never changes the platform switch.

The two native tools prepare a durable application confirmation and use the
existing executor. Their schemas, manifests, catalogue identities, modification
path, multilingual preview and addressed heartbeat invalidation are wired.
Direct pipeline dictionaries are validated before preparation. The same defect
found in assistant/layout tools was corrected and their existing PostgreSQL
flows were rechecked.

Adversarial scenarios found and corrected:

- A queued background notification could survive a saved opt-out during its
  decision or generation. Separate short database reads now fence both phases
  and publication; already spent decision/generation billing records remain in
  the existing accounting funnel.
- A generation could cross the end of the local notification window. Publication
  reuses the existing hour-window predicate, including overnight windows.
- A connector revocation could leave prepared content admissible. A single
  owner-filtered query fingerprints connector identity, status, scopes and
  encrypted preferences. Credential ciphertext and refresh timestamps are
  excluded, so normal token refresh does not falsely cancel a notification.
- A failed application restart retained a writer bound to the previous store.
  Startup withdraws the previous writer before acquisition, and shutdown
  withdraws it before closing the store. Continuity writes use an injected
  infrastructure port; heartbeat prompts use the existing shared versioned
  reader, avoiding a new domain cycle without changing prompt bytes.
- Optimistic source refusals updated a request field instead of the displayed
  response field. The frontend now updates the displayed refusal list, serializes
  writes and protects newer previews from earlier failures.
- Old account callbacks, replies and completion toasts survived account changes.
  Account lifetimes refuse obsolete callbacks before HTTP and suppress late
  publication. Addressed hints reread heartbeat through its own endpoint without
  an unrelated profile request; coalesced events retain their own resource batch.

Current evidence: targeted frontend hook/component/SSE tests, native boundary and
authority tests, prompt byte parity, SQL command/conflict/consent integration,
strict typing and the existing size/cycle/complexity instruments. Provider/model
work is simulated; the dispatcher integration uses a controlled effect-ledger
double. No real-provider, production or device validation is claimed. The full
lot remains open for the other communication, security and automation families.

## Lot 4 — Channel read and desired-state slice

Cold review checked the public schemas, private confirmation snapshot, shared
HTTP command owner, draft editor, catalogue/discovery, capability fences, stream
adapter lifecycle and account-bound frontend callbacks. Both preparation and
execution check the current owner and platform switches. The command locks the
actor and binding, compares the displayed identity and sets a desired boolean.
HTTP toggles share that owner. A schema guard rejects unsupported channel kinds
and requires review when the API adds displayed fields.

Corrections driven by adversarial tests: the edit prompt exposed a private chat
identifier; it now offers only the binding selector and desired state. Channel
tools had duplicate capability ownership; application tools remain the unique
owner and channel availability is an explicit operation prerequisite. Account
changes retained a displayed OTP and late success toast; the secure UI remounts
on identity changes and rejects obsolete callbacks. Cancellation closes the
actual assistant generator before resetting its context, and failed startup
withdraws the previous injected gateway.

Evidence: 711 tests in the combined backend review campaign; 17 subsequent
schema, stream cleanup and lifecycle tests; 28 targeted frontend tests; four
PostgreSQL channel command cases and one actual draft-modifier case. The latter
proves durable replacement invalidates the old approval without a binding write.
Strict typing, complexity and React hooks gates passed. The initial Docker lint
process crashed inside V8; a no-JIT rerun is being qualified separately. The
accessibility gate has not yet been requalified. PostgreSQL is disposable and
dispatcher tests use a controlled effect-ledger double. Native unlink and secure
link handoff are not covered by this completed read/update slice.

## Lot 4 — Confirmed channel unlink slice

The removal action freezes the exact owned binding in a private command, shows
its removal and reconnection consequence in all six languages, and reuses the
locked HTTP unlink owner. No deletion occurs at preparation. Execution compares
the current full identity before deletion; only a committed receipt emits the
channels invalidation. Editing uses a public UUID selector, rebuilds current
owned identity and replaces the durable approval digest without deletion. The
model never receives OTPs or the private chat identifier in the editing prompt.

Evidence: 714 combined backend tests; six PostgreSQL command cases including
nominal removal, changed identity and foreign-owner refusal; two PostgreSQL edit
cases; strict MyPy on eleven owners. A failed edit fixture attempted two Telegram
bindings for one user; the real unique constraint rejected it. The corrected
fixture observes the current one-binding-per-type rule and exercises identity
refresh instead. Frontend lint and accessibility now pass with Node's JIT
disabled after the original V8 process crash; no rule or threshold changed.
Shrink-only size review found no further owned reduction. Secure association
still depends on lot 8. Full lot 4 and the later lots remain open.

## Lot 4 — Non-secret connector preferences slice

The cold review covered HTTP reads/writes, shared encryption and sanitization,
owned connector selection, canonical preview/edit/confirm, current source CAS,
model projection, frontend lifetime/write ordering and addressed invalidation.
The native catalogue exposes only saved calendar and task-list defaults. It
promises a saved preference, not provider availability. OAuth, credentials,
activation and disconnect are separate remaining operations.

Adversarial corrections: unreadable ciphertext cannot be replaced as empty
defaults; diagnostic errors carry exception types instead of private payloads.
The connector UUID survives some OAuth relinks, so the snapshot also binds the
current non-secret grant/account identity. Changed account identity refuses an
old approval; ordinary token renewal remains valid. The database has no
per-user/type uniqueness constraint for connectors, so reads are bounded and
cursor-paged with an exact owner-filtered total. When ReAct's token projection
cuts a received page, only this declared native cursor is moved to the last
actually visible UUID; canonical output stays intact and projected token use is
recounted. This prevents omitted rows being skipped by the following query.

Frontend changes reuse account lifetimes and resource invalidation. Writes are
serialized per connector, verified reads retain their own revision, and an
earlier commit cannot replace a later pending preview. Obsolete callbacks are
refused before HTTP; failed native rereads preserve the last known value and
show the existing sync error. Preference values accept the API's real nullable
fields and reject unknown fields. A backend guard requires explicit non-secret
review for new registered connector types or preference fields.

Current evidence: 974 combined backend tests, 141 connector/SSE frontend tests,
seven PostgreSQL connector cases, fourteen earlier SQL editor/command cases and
strict MyPy on thirteen owners. Frontend scoped ESLint and nonincremental
TypeScript passed; the full complexity ratchet returned to its original count
and maximum without raising caps. The owned connector router size cap shrank
through the repository instrument. Provider work was not performed and the
confirmation dispatcher uses a controlled effect-ledger double. Full lot 4
remains open; this evidence is not whole-project qualification.

## Lot 4 shared MCP personal preferences — inline cold review

The shared-server slice covers personal enable/refusal choices and saved tool
counts. It does not cover global administrator configuration or full server/tool
catalogue reads. The existing HTTP list/toggle and native commands share one
domain owner, fresh account locks and exact selected-server identity comparison.
Other saved refusals are preserved; verified no-ops do not commit. Changes to
the displayed catalogue require another preview. Future UI fields require an
explicit projection review through a source-schema guard.

Authority was traced through bound RPC adapters, their effect-cache boundary,
iterative MCP tasks and existing widget proxies. All reread current account,
platform and refusal state before RPC, cached-result access or a paid child
model call. Missing actors, unavailable policies and malformed saved JSON fail
closed. Cold review found false/zero/empty-object/empty-string JSON was being
treated as an empty refusal list; four RED cases exposed the grant, and the
shared strict parser now accepts only a real list or legacy SQL NULL. Widget
proxies no longer trust a previously loaded session row, and their raw provider
exception/resource URI logging was removed.

Runtime ownership uses startup-injected typed access and preference gateways.
Restart withdraws previous readers/writers/policy before acquisition; shutdown
withdraws before closing the manager. This repaired a measured new domain cycle
without relaxing the coupling baseline. Native public schemas accept only a
server selector and explicit desired boolean. The editor receives neither the
private catalogue digest nor global configuration. Confirmation hides the
unchanged digest while checking immutable identity. Public read projections
also omit it, reducing prompt noise. Pages are bounded and a token-budget cut
continues after the last server actually shown, preserving canonical output.

Frontend queries and callbacks follow account lifetimes and targeted native
invalidations. Old-account values and late results are hidden, obsolete callbacks
perform no HTTP, writes are serialized per server, and verified reread failures
retain known data. Cold review added a handled retry failure and account-owned
toasts. Existing responsive settings templates are reused; native browser/device
and whole-project UX qualification remain later lots.

Evidence: 2,095 combined foundation/effects/startup checks before the final
projection change; 1,187 current application/MCP/size/coupling checks afterwards;
21 focused security/coupling checks; eight current real PostgreSQL cases;
17 frontend MCP/SSE cases; strict MyPy on fourteen source modules. SQL uses the
actual native dispatcher/editor and domain owner with a controlled effect-ledger
double; no paid provider probe occurred. Frontend full lint and its existing
complexity ratchet passed with the documented V8 workaround, scoped final ESLint
and six-locale parity passed. Frontend nonincremental TypeScript, accessibility
and hooks gates passed. The final common-query review exposed prior-account
values returning on an A-to-B-to-A transition, and an obsolete refresh callback
issuing HTTP for the new account. Two RED cases now pass through opaque query
lifetimes and an early current-lifetime guard; 62 affected frontend checks and
scoped strict ESLint pass, and full TypeScript was requalified afterwards.
Owned source complexity is
below the ratchet boundary; no size, complexity or coupling cap was raised.

This closes the reviewed server preference/access slice. Full lot 4 and lots
5–10 remain open.

### Lot 4 — Saved connector cards and local unlink

The native read exposes a bounded, owner-filtered projection of saved connection
cards. It explicitly distinguishes saved status from provider availability.
The unlink proposal names a current owned UUID; its private identity includes
the shared grant and timestamps, while the public editor accepts the selector
alone. The actual HTTP and assistant unlink share one source owner, preserving
the existing local-only OAuth cleanup and sibling service access. Provider-wide
consent is retained, as stated in the confirmation in every language.

The adversarial review checked fresh active ownership, exact-state conflicts,
grant replacement, missing targets, shared/last-grant cleanup, and lock ordering.
The owner acquires User then Grant then Connector, matching the OAuth runtime's
Grant-before-Connector order. Two real independent SQL sessions exercise the
runtime writer alongside the unlink owner. A committed receipt precedes cache
invalidation; a cache failure is reported as post-commit failure and still sends
the addressed refresh hint. Authoritative card rereads bypass the list cache.
No provider call or paid-model call is needed to read or unlink a connection.

The frontend preserves account ownership across queries, optimistic setters,
async replies and SSE callbacks. The review reproduced and repaired a retained
callback becoming valid again after A-to-B-to-A. Simli unlink stops the avatar;
Live unlink refreshes its readers, with fresh reads and account fences before
runtime changes. Ordinary connector removal affects neither runtime. Failed
rereads preserve the existing interface. A schema coverage guard requires a
deliberate projection review when the source card gains a field; secret metadata
and host authority never become tool fields automatically.

Evidence: 258 application/source/effect-gate/size tests; three coupling checks;
eleven real PostgreSQL cases covering native confirmation, exact pending-draft
editing, concurrency and post-commit failure; 36 frontend component/hook tests;
strict MyPy on ten source modules; scoped ESLint and six-language parity.
The effect-ledger callbacks in the SQL dispatcher tests are controlled doubles.
The prompt test asserts actual private values and private field names are absent;
it permits the instruction explicitly forbidding credentials. A corrupt saved
identity has a dedicated error and never echoes its raw payload. Source complexity
is below the existing boundary after extracting the resource projection; no
quality cap has been raised. Final nonincremental TypeScript, scoped ESLint,
frontend complexity, React Hooks and accessibility ratchets passed. The last
component complexity regression was removed by sharing the existing resolved
confirmation label and account-query identity, rather than increasing its cap.
The native SQL page test verifies continuation after the last item actually
projected under a reduced model token budget, without altering the canonical
payload. These card/local-unlink tools are now wired into native discovery.

This is the connector-card/local-unlink slice only. Secure activation and
reconnection, service-specific settings, the remaining lot 4 sections and lots
5–10 remain open. No browser, real device, production or paid-provider probe is
claimed by these tests.

### Lot 4 — Saved notification devices

The tools read saved server notification registrations and prepare removal of
one owned device identified by UUID. They expose neither push credentials nor
their comparison digest. A saved active registration is explicitly distinct
from browser/system permission and successful delivery. Enabling permission
remains the device interaction in lot 8. The confirmation states that removal
leaves OS/browser permission unchanged and that reenrolment restores the server
registration.

The HTTP deletion service and native executor share the notification-domain
owner. It locks the current active account and the owned registration, checks
the complete saved identity and private token fingerprint, and refuses rotation,
replacement or absence after preview. The caller retains transaction ownership;
native execution commits before recording its receipt and emits a value-free
addressed invalidation. No Firebase client or paid model is needed for read or
removal. Source UI response-field coverage is guarded against silent future
additions.

The review found an agents/notifications import cycle and replaced it with a
typed infrastructure port and startup-injected domain owner. Initialization
withdraws the prior binding before constructing a replacement; failure and
shutdown leave the port unavailable. Source ownership/query rules stay in
Notifications, with no widening of the coupling baseline.

The frontend review reproduced old-account replies, a credential acquired for
the prior account being registered under a new session, retained A-to-B-to-A
deletion callbacks, and old UI completion toasts. Opaque account lifetimes now
fence local credential/list/error/loading state and every async interaction
boundary. Canonical rereads supersede older replies; an older application sync
awaits the newer reading's result, avoiding a false failure after verified
success. Failed reads preserve the last displayed list. Account changes remount
the settings form, while an ordinary native invalidation retains local input.
The old credential-prefix log was removed. Existing SDK failure diagnostics
remain; this review does not claim a global audit of all notification logging.

The prompt now distinguishes resource selectors from actor/account authority,
forbids invented selectors, and keeps removal withdrawal in cancellation. Public
editor input is only the device UUID; the real SQL modifier replaces the exact
pending command without deleting either device. Malformed saved state uses the
existing INVALID_RESPONSE_FORMAT error vocabulary, including the connector-card
tools, with no raw payload echo.

Evidence: 364 current application/notification/startup/size/coupling unit checks;
six real PostgreSQL cases for native confirmation, rotation, concurrent removal,
global switch-off, pending-draft editing, and foreign-device isolation in both
the UI handler and native tools; 49 frontend checks across the actual web/native
hook, settings and permission prompt. Ledger callbacks and the edit model are
controlled doubles. Strict MyPy, nonincremental TypeScript, scoped ESLint,
six-language parity and frontend complexity/hooks/accessibility ratchets passed.
New source functions remain below the complexity boundary; existing component
caps were preserved through extraction. No quality threshold was increased,
and the shrink-only instrument found no size-cap reduction for this slice.

This closes the saved-notification-device slice. The rest of lot 4 and lots
5–10 remain open; real OS permission/device qualification and provider probing
have not been performed.

### Lot 4 — Live conversation reflexes

The shared locked preference owner preserves the fresh provider choice, compares
the whole saved snapshot before confirmed writes, and records no-op receipts.
Native inputs expose only the three reflexes; provider identity and the saved
digest stay private. Reads identify fields using tolerant source defaults.
The editor rebuilds a fresh proposal and replaces the exact pending command.
The source Live start captures these values; reconnects retain that session's
setup, so the confirmation explicitly applies to future sessions.

Cold review corrected lost rapid full-replacement writes, obsolete callbacks
across A-to-B-to-A account changes, late results, stale toast callbacks, and
an optimistic value remaining displayed when both its save and reread failed.
The addressed Live invalidation rereads preferences without restarting a session
or refreshing unrelated account data. New source preference fields require an
explicit projection review. Saved-state errors use INVALID_RESPONSE_FORMAT.

Evidence: 323 current application/Live/startup/size/coupling unit checks; seven
PostgreSQL confirmation/editor cases; 32 frontend flow/panel checks. The effect
ledger and edit model are controlled doubles. Strict MyPy, TypeScript, scoped
ESLint, six-language parity, complexity and React-hook ratchets pass. No ratchet
threshold increased; the shrink-only size instrument found no reduction.
The final accessibility ratchet passes with no violations. This closes the
Live-reflex slice.

Current registered application identities include the two Live reflex tools.
Live connector model/voice/budget configuration and actual browser/device/provider
qualification remain outside this slice. The independently identified failed
effect-result replay gap must be repaired before extending secure handoffs.

### Foundation repair — Explicit failed-result replay

A PostgreSQL RED test reproduced an explicit post-commit failure being closed
without its returned payload: the second claim retained FAILED but lost the
committed fact. The shared failure close now uses the existing encryption,
payload cap, digest and owner fencing. Exception-only failures retain no invented
result. Existing callers can omit the optional payload unchanged.

Cold review also found that a truncated stored result could be returned by the
draft gate as a complete legacy result. The database runtime and both gates now
refuse partial payloads as completion evidence. No effect is retried, no status
is promoted, and no diagnostic content is exposed by this refusal.

Evidence: 22 real PostgreSQL ledger cases including returned failure replay,
encryption, Unicode truncation and stale/double closes; 1,123 combined effect,
application, file-size and coupling unit checks; 15 focused gate cases including
partial replay through both entry points. Strict MyPy, Black, Ruff and scoped
diff hygiene pass. No migration, provider call, new prompt or raised quality
threshold is needed. This repair is closed; WAITING classification and secure
handoff completion remain a separate prerequisite before those consumers exist.

### Lot 4 — Live connector settings and choice listing

The source UI and confirmed native writes share the locked owner: fresh User,
then owned Connector, with a whole-state fence over metadata, encrypted-key
identity and provider choice. The native proposal merges an explicit delta,
restores a model's remembered settings and writes nothing. An unconfigured model
requires an explicit voice. The genuine confirmation/editor path now uses the
actual operation registry. Provider checking happens only after confirmation;
native capability is rechecked after lock waits and before key access or probing.
No-op writes perform no probe. Reflexes and other model settings are preserved.

Cold review corrected the missing local actor check in Live draft editors,
private snapshots leaking through successful execution enrichment, stale errors
losing their finite refusal code, discarded unsaved form edits during invalidation,
obsolete account callbacks and a fallback voice proposed for a new model. Public
execution values omit private connector/provider snapshot material. All failure
paths retain the commit receipt; a post-commit failure remains explicitly partial.

The source configuration is shared with the UI; native projection contains the
reviewed bounds/defaults, excluding bridge prompt lines and internal tool names.
Choice reads reuse provider owners, retain voice provenance and expose unpriced
models as nonselectable items. Pages are bounded and bound to the catalogue;
continuation follows the last item actually shown after token projection. Changed
catalogues require a new first page. A deadline and the existing user tool limiter
bound discovery; current authority is rechecked before serving its result.
Vendor diagnostic content becomes finite timeout/quota/provider errors.

The catalogue covers what the application source lists. ElevenLabs retains its
existing upstream single-page bound and per-agent configuration reads; this is
not evidence of exhaustive vendor listing. Discovery can consume the person's
API quota; confirmed validation may briefly open a provider connection on that
person's key. Neither was run against a paid provider in this qualification.
Current Live sessions retain their model; standby wake may read saved settings,
so the confirmation note does not promise that every effect waits for a new session.

Evidence: 396 application/source/size/coupling unit checks, two failed-startup
withdrawal checks, 26 real PostgreSQL checks across Live owner/confirmation/reflex
and MCP projection, and 32 frontend flow checks. Independent SQL sessions verify
operator disable during a user-lock wait prevents key access and provider work.
Ledger callbacks, the provider probe and the edit model are controlled doubles.
Strict MyPy, nonincremental TypeScript, scoped ESLint, six-language parity,
frontend complexity/hooks/accessibility ratchets pass. A transient global React
lint-plugin crash was not reproduced in isolated lint and its exact rerun passed.
Complexity was reduced without raising any quality threshold; the shrink-only
size instrument found no further cap reduction.

This closes the Live connector slice and registers its three identities. The
remaining security/custom-voice/telephony/automation slices of lot 4 and lots
5–10 remain open. Browser/device/real-provider qualification is not claimed.

### Lot 4 — Authentication state and passkey metadata reads

The native security reader exposes only reviewed authentication features,
password-sign-in configured state, TOTP state and unused recovery-code count,
and bounded owner-scoped passkey metadata. Enrollment material, credential ids,
public keys, password hashes, OTPs and recovery-code values are omitted. Source
UI feature and available-method rules are shared with the native reader.

Cold review verified step-up routes remain mounted independently of MFA. MFA
off therefore leaves password/OAuth reauthentication methods available while
TOTP/passkey state is explicitly unavailable. Current-session freshness is
unknown without a trusted transport context; available methods never supply
approval proof. Actor/operator checks precede queries and returned data.
Passkey pages use creation time plus UUID for tied dates, refuse foreign/deleted
cursors and continue after the last item actually visible under token projection.
Shared SQL sessions are used sequentially, with bounded page queries and aggregate
counts rather than per-passkey queries. Future public schema fields require review.

Evidence: 357 current application/auth/size/coupling unit checks, one PostgreSQL
owner/tied-date/foreign-cursor/secret-omission case and strict MyPy. Existing source
feature/demo/step-up assertions remain unchanged; fixtures now patch the shared
owner seam. Six-language parity and scoped diff hygiene pass. The source auth
router size ratchet shrinks from its previous cap; no threshold increased.
No frontend business behavior, model call, provider call or secure mutation was
introduced. This closes the authentication-state read slice, registering one
identity. Device-session state, export state and all secure management actions
remain separate work; security-auth UI coverage is not declared complete.

### Lot 4 — Account export state and retention

The native reader and existing UI now share the owner-scoped latest-job query,
deterministic creation-date/UUID ordering and archive availability rule. A saved
done status remains a saved fact; availability separately requires an aware,
future retention deadline and an existing file. No archive path/content, new job,
download, audit increment or reauthentication material reaches the read tool.
Fresh account and application-capability checks precede and follow reads.

Cold review found that the source download route did not actually enforce its
declared retention window. It now refuses expired/missing deadlines before audit
or commit. The UI consumes the same checked availability, explains an unavailable
archive and withholds its link. Current reads fail closed on filesystem errors;
availability is an observation, and the download route checks again when used.
Source export creation keeps its step-up, rate limit and unique-job race handling.
An injected startup port avoids a measured agents/export-builder import cycle;
failed owner restart and shutdown withdraw the old binding.

The review also reproduced obsolete-account export links, delayed confirmation
and late mutation callbacks. Account-scoped reads and keyed dialog lifetimes now
hide old data and refuse obsolete actions before POST, including A-to-B-to-A.
The shared step-up guard cancels parked work on unmount, refuses stale verification
callbacks and avoids replacing an existing challenge. Busy controls retain keyboard
focus through aria-disabled and a handler guard; the action row wraps on phones.
No background polling was implemented or claimed in this read slice.

Evidence: 380 application/export/startup/size/coupling unit checks; four final
export reader checks including mid-read operator revocation; two PostgreSQL
owner/retention/tied-date checks; 30 frontend checks using actual account-query and
step-up hooks plus existing UI assertions. Strict MyPy on nine source files, clean
host TypeScript, scoped ESLint under max complexity 14, six-locale parity and diff
hygiene pass. Full frontend ratchets pass at CC 42/max 52, hooks 31 across 26 files,
and accessibility zero; no threshold was raised. Docker became temporarily
unavailable, then recovered before the final PostgreSQL qualification. Host static
ratchets required normal child-process access; their exact reruns passed.

This closes only the export-state read slice, registering one identity (28 total).
Assistant export requests/download handoffs and session/device secure flows remain
open. Hermetic browser, real-device and overall feature qualification are not
claimed by these targeted checks.

### Lot 4 — Connected device/session state

The native session reader shares the UI's reviewed device metadata projection and
owner-scoped attestation-name query. It reads only opaque display ids, coarse
browser/OS/IP metadata, authentication tags and timestamps. Native current identity
is explicitly unknown (null/false): there is no trusted transport-session bridge yet.
Raw cookies, step-up times/proofs, FCM credentials and attestation ids stay internal.
The names query selects only id/name and only the native page's candidate ids,
scoped by account; a foreign attestation reference cannot disclose its name.

Cold review reproduced six source defects/edge cases before repair: an indexed
foreign session was trusted, malformed JSON shapes/dates raised, and mixed legacy
naive/aware timestamps broke sorting. Listed payloads now recheck their stored owner,
skip invalid rows without logging a raw session id and normalize legacy UTC dates.
Source UI and revocation lookups reuse this owner check. Native output explicitly
marks omitted invalid/mismatched metadata as incomplete; a genuinely expired Redis
key is normal absence. This distinction prevents an uncertain list being announced
as exhaustive. Presentation order uses date plus display id for ties; unknown,
foreign or vanished cursors require restarting, and collisions fail closed.

Native input refuses credentials/claimed current context, bounds page sizes and
uses the last actually visible display id after token-budget truncation. Indexed
work is separately capped before payload reads and rechecked after index growth;
oversized indices return a finite constraint error. Existing direct UI list/revoke
behavior retains its unbounded index contract. Redis/SQL errors are finite failures,
and fresh account/operator checks run before reads and before serving the result.
Post-read account deactivation was simulated through an independent SQL session.

Evidence: 398 current application/session/source/size/coupling unit checks, two real
PostgreSQL/Redis cases covering page/UI parity, corrupt foreign index, foreign
attestation, secret omission and concurrent deactivation; strict MyPy on nine source
files, Ruff/Black, six-locale parity, official complexity measurement and diff hygiene.
The source list's IO and batch decoding were separated by responsibility; all new
functions remain below the existing complexity boundary, with no raised baseline.
No frontend business change, model/provider call or session mutation tool was added.

This closes the session-state read slice, registering one identity (29 total).
Assistant revocation, trusted current-origin identity and secure reauthentication
handoffs remain open; source UI revocation does not constitute their implementation.

### Lot 4 — Saved phone identity state

The new phone reader and existing UI share the complete reviewed identity
projection: the declared number, verification and pending state, context consent,
domain switches, saved/effective call mode and the source Live-availability reason.
The native result distinguishes an absent number from unreadable saved ciphertext;
verification refers to a readable line. E.164 format and source mode vocabulary are
checked, and future source schema fields/modes require explicit projection review.
No credentials, code, ciphertext, webhook settings or internal callback URL cross
the injected read port. Source verification errors carry finite public categories.

Cold review found the existing pending-status helper could delete a code bound to
an old number. Its new cleanup=false path makes native consultation strictly
read-only; the old UI/confirmation default retains its existing invalidation rules.
Real Redis evidence preserves the code across number changes and corrupted-number
reads. The reader never starts a call, retries a verification, increments attempts
or spends a provider quota. Fresh application and telephony switches plus account
authority are checked before source access and before serving the result. Failed
owner restart/shutdown withdraw old bindings. A section-name mismatch was caught
against the actual settings token and fixed before qualification.

Evidence: 374 current application/phone/source/startup/size/coupling unit checks,
five final reader checks including both mid-read switch revocations, and one
PostgreSQL/Redis identity/mode/code-preservation case. Strict MyPy on nine source
files, Ruff/Black, six-locale parity, official complexity measurement and scoped
diff hygiene pass. No quality baseline was raised. Source identity services retain
their existing constant-number user/connector queries; no row-wise query loop or
provider request was added. There is no new frontend business behavior.

This closes only the phone-identity read slice and registers one identity (30 total).
Call history/usage, confirmed identity/context changes, verification and credential
flows remain open. Existing source owner-call behavior is not an implementation of
the new confirmed application flows. Browser/real-call qualification is not claimed.

### Lot 4 — Phone history preparation: owner-scoped recorded usage

The source calls UI now conditions its batched token-summary lookup on the account
whose calls it lists. The shared repository supports that explicit owner condition;
legacy administrative/internal multi-owner callers retain their existing default.
No bill is created, no provider is contacted and no row-wise query is introduced.
A real PostgreSQL test supplies a foreign run id plus an owned one and proves only
the owned summary returns. The existing Live/direct usage-sum assertions remain and
now also assert the owner passed to the batch reader.

Evidence: 24 source/router/size/coupling unit checks, one PostgreSQL case, strict
MyPy on two source files and scoped diff hygiene. The intended RED was the missing
owner-parameter contract; an earlier fixture error was corrected against the real
model's unique run id, nullable conversation and computed billed-cost property.
No threshold was raised. This closes the owner-fence prerequisite only, not the
history tool. Source historical delegated-run discovery and retention-dependent
usage completeness still require analysis before exposing history through LIA.

### Lot 4 — Retained phone history read

The source UI and native reader now share one owner-conditioned projection and
one batched recorded-usage lookup. Native pages use creation time plus UUID to
resolve ties, refuse foreign/deleted cursors and adjust continuation after the
model's item-budget projection. Public schema and nested structured-data/usage
fields are guarded against unreviewed additions. Encrypted numbers and webhook
material are excluded. No provider, synthesis, call, write or purge is performed.

Cold review preserved the source's sole-active-conversation rule after checking
the unique account conversation constraint. Recorded consumption remains explicitly
partial when associations have been purged; absent usage is not proof of free
execution or a vendor invoice. Duplicate delegation stamps cannot double-charge
one run. Fresh account/application/telephony authority is checked before access
and before returning data. Failed restart and shutdown withdraw the read binding.
Older source tests were adapted to the extracted owner without changing their
privacy and cost assertions; they now also assert the acting owner.

Evidence: 754 current application/telephony/startup/size/coupling unit checks pass
with one existing flag-gated route skip; two PostgreSQL checks cover actual native
and source parity, date ties, paging, owner billing, private-field omission and
foreign cursors. Strict MyPy on eight source files, Ruff/Black, six-locale parity,
official complexity measurement and scoped diff hygiene pass. No ratchet was
raised. This closes only the history reader, registering identity 31. Secure
identity actions and the remaining implementation lots are still open; no browser,
real call, provider billing, deployment or complete application parity is claimed.

### Lot 4 — Confirmed phone context, domains and mode

The existing UI and the assistant compose one locked source command for all three
non-secret preferences. Full validation precedes changes; one commit prevents the
old multi-field route's partial-save failure. Exact state comparison also covers
number ciphertext and verification time without disclosing either in proposals.
Source request null-as-omission remains supported; native deltas refuse coercion,
explicit null, empty/unknown fields and identity/verification actions. Domain
vocabulary is published from the existing shared declaration. Number, code,
credential and actual-call actions remain outside this slice.

Cold review verified every execution consumer: mode/context applies to future
owner calls, while disabled domains are refused at the next phone/direct-browser
lookup, including current sessions. Browser setup declarations refresh on start
or wake. Six-language previews and the actual tool schema explain that boundary
and the source policy for future domains. Snapshot hashes stay out of the preview,
editor prompt and execution result. Source writes recheck native capability after
lock acquisition; changed consent/number/verification yields a new preview.
An explicit clear materializes obsolete stored domains rather than reporting a
false no-op. Failed owner restart/shutdown withdraw the binding.

Actual frontend review reproduced two additional races: a native reread unmounted
the dirty form, and an older response could erase a manual save. Shared account
query/state/lifetime owners now hide old account data and callbacks, while one
per-account queue orders reads and writes. Populated forms remain mounted during
refresh; code-expiry responses cannot cross A-B-A lifetimes. Original translated
refusals survive an unsuccessful recovery read, and privacy diagnostics omit
payloads. Addressed invalidation reads the phone interface without a profile GET.

Evidence: 780 application/telephony/startup/size/coupling checks pass with one
existing flag-gated skip; ten PostgreSQL/Redis checks cover actual native
confirmation/edit/no-op/conflicts and owned identity/history. Forty-three frontend
checks, strict MyPy on ten source files, clean non-incremental TSC, scoped ESLint,
six-locale parity and diff hygiene pass. Official frontend ratchets remain at
42 complexity hotspots (max 52), 31 strict-hook violations and zero a11y violations;
every new function stays below the existing complexity boundary. No ratchet was
raised. This closes the non-secret phone preference slice (identity 32), not lot 4
or the overall delivery. Secure interaction/WAITING, automation, administration,
device acknowledgements and remaining lots still require implementation.

### Lot 4 prerequisite — waiting receipts and command expiry, cold review

The initial handoff is a settled, encrypted effect receipt, never evidence that
the awaiting business action completed. Source notary inspection ruled out
rewriting WAITING into success: settled rows are covered by the chain. A later
authorized completion must create its own effect. Mutable command state owns
interaction expiry and preserves any already committed server values when a
device acknowledgement is lost. No secure consumer or resume endpoint is
exposed by this prerequisite.

Adversarial tests reproduced and fixed receipt identity substitution, extending
the approval deadline, ambiguous pending-plus-error/no-op results, and reporting
a secure action already committed before its reauthentication. Generic claim
cannot reexecute WAITING. Expiry uses an owner, phase and encrypted-result CAS;
malformed stored receipts refuse before cached execution. The deadline is bound
to the original approval. Historical notarized handoff receipts remain readable
after expiry. Pending results skip completed-context writes and are counted
separately by the batch dispatcher, business/tool/effect metrics, chat result
renderer and keyboard-accessible journal filter, in every locale. The performed
action summary excludes them.

Evidence: expanded application/effects/renderer/metrics checks produced 1,405
passes and one global file-size failure in concurrent, unrelated
`journals/consolidation_service.py`; its cap was preserved. The final focused
run passes 476 checks after adversarial corrections. Thirteen actual PostgreSQL
command/receipt lifecycle checks pass; forty PostgreSQL checks including the
deep notary verification pass. Sixty frontend checks, strict MyPy on fourteen
source files, non-incremental TSC, Ruff and six-locale parity pass. All official
frontend ratchets pass without raising baselines (CC 42, hooks 31, a11y zero).
Legacy backend complexity hotspots were measured separately; new or changed
application functions remain within the existing boundary. This closes the
receipt/expiry prerequisite only. Operation-bound session proof, status/resume
consumers and secure browser interactions remain the next implementation slice.

### Lot 4 prerequisite — trusted transport session reads, cold review

Authenticated ordinary and resumed HTTP chat calls now pass a live, typed session
reader through the streaming service, graph builder and tool runtime. The model
has no session/origin input. Raw cookies remain inside its server-side closure;
the context excludes the origin from its representation. Automated and
mismatched-actor runs withdraw the reader. Actual LangGraph checkpoints and
LangChain serialization tests verify that credentials never enter state or
tracing. A guard covers every authenticated HTTP stream call, including future
additions. A command-bound check re-reads session ownership, opaque binding and
current step-up time; a prior observation is never permission for a later action.

Source inspection and failing tests exposed a shared authentication race:
read/whole-payload SET could recreate a revoked session without expiry or erase
a concurrent step-up. Source activity/step-up now change one field atomically,
preserving the existing owner, other fields and fixed TTL. Source and native
freshness use one predicate and refuse foreign owners, future/naive dates and
lost writes. Session diagnostics expose opaque display ids rather than bearer
cookies. A returned verification horizon is conservative relative to its write.

Session/security tools use their own injected runtime and publish current-device
and fresh/stale facts only after a live transport read; other origins stay
explicitly unknown. Operator and actor authority are rechecked after that last
read. Independent PostgreSQL sessions prove that revocation during the read
withholds the whole projection. No credential ceremony, secure completion
endpoint, passkey mutation or verification call is exposed by this slice.

Evidence: 666 application/context/auth/coupling checks pass, as do thirteen
actual PostgreSQL/Redis origin and source-read checks. The final 88-check cold
run includes real graph privacy, tool injection, HTTP forwarding guard, source
auth and streaming/voice/HITL characterization; all pass. Strict MyPy on eighteen
source files and Ruff pass. New functions remain below the complexity boundary;
the three touched streaming modules remain below their frozen size caps. The
previous unrelated journal-size failure remains an independent global finding.
Frontend code did not change after the already-green waiting journal gates.
This closes live transport reads only; durable operation binding, current-command
status/resume, secure browser handlers and remaining lots are still open.

### Lot 4 prerequisite — declared phone-number owner, cold review

The HTTP number setter/clearer now delegates to a shared locked owner with exact
number/verification comparison, encrypted storage, semantic no-op and truthful
write receipts. Re-entering the same canonical number preserves verification;
a changed or cleared number loses it. Clearing repairs unreadable ciphertext
and orphan verification stamps. Missing, foreign, inactive and deleted actors
are refused after the row lock. Stored invalid plaintext cannot become a
verified dial target. National-number normalization remains the existing source
policy; this prerequisite makes no call and exposes no native number tool yet.

Adversarial verification reproduced stale-line authorization, expiry/replacement
during a lock wait, deletion of a new code by an old status read, and charging a
replacement code's counter. Verification now compares the freshly locked number
before atomically consuming its exact Redis record. Attempt registration and
stale cleanup are bound to that record too; they cannot debit or delete its
replacement. A database failure after consumption remains a refused verification
requiring a new code, never permission to replay an old code.

Evidence: 474 expanded telephony/application/coupling checks pass; one inherited
telephony-disabled wiring skip is reported separately. Eleven real disposable
PostgreSQL/Redis checks pass, including independent sessions blocked on the
actual user lock, one-time code consumption, expiry/replacement and the atomic
attempt/cleanup races. The first SQL attempt used an unauthenticated Redis URL
and failed; rerunning with the repository's authenticated test fixtures passes.
Strict MyPy on six source modules, scoped Ruff and source complexity measurement
pass. No owned file-size reduction is eligible; no baseline is raised. This
closes the source prerequisite only. Native number preparation, exact HITL,
registration/editing/projection/UI invalidation and later secure verification
interactions remain open.

### Lot 4 — declared phone-number native action, cold review

The reviewed number operation is registered in the shared capability/catalogue
identities and both execution modes. A strict set/clear request shares the
existing UI bounds and normalization. Preparation makes no write or call;
the canonical number and verification consequence are shown before exact HITL.
The encrypted command retains the number/verification comparison snapshot.
The editor accepts only a new declaration or clear request, replaces the pending
command atomically and never offers its actor, structural fields or digest to
the model. A future UI number-schema addition requires explicit coverage review.

Fresh operator/telephony authority and active account ownership are rechecked
after the actual user-row lock. Changed number or verification, cancellation
and capability withdrawal refuse execution. The same canonical number keeps
its ciphertext/verification and emits no invalidation. Other phone preferences
remain intact. Public receipts, multilingual previews and editor prompts omit
comparison material. Corrupt before-values refuse the whole card; clearing an
unreadable record visibly distinguishes its previous and resulting states.

The existing addressed account query/queue synchronizes confirmed changes.
Native refresh preserves an unsent focused number; account lifetimes reject old
callbacks, and a reread queues after an in-flight manual write. No verification
call or secure code reaches the assistant in this slice.

Evidence: final application/registry/startup/coupling cold run passes 416 checks.
The preceding expanded source/application run passes 863 checks, with one
inherited disabled-telephony skip and the same unrelated journal file-size
failure. Eleven real PostgreSQL native checks pass, including the actual editor,
exact confirmations, cancel/no-op/stale states and two independent-session
operator-withdrawal races; the combined earlier consent regression run passes
eighteen. Forty-one frontend checks, strict MyPy on twelve modules plus the final
renderer recheck, TSC, scoped Ruff/ESLint and six-locale parity pass. Complexity
and shrink-only size instruments show no raised baseline. This closes number
declaration/clearing only: there are now 33 application tools. Secure verification,
account actions, durable browser interactions, administration and the remaining
original lots are still open.

### Lot 4 prerequisite — durable transport binding and current status, cold review

An additive nullable column stores an encrypted actor/command/operation/digest/
session binding. It stores no cookie, authentication method or step-up permission.
Every use rereads the live session. Different transports, corrupt/unbound data,
changed identity/content or an extended approval horizon are refused. A bound
pending revision must retain its original live transport and atomically update
its encrypted comparison data; legacy unbound commands remain supported by their
existing execution paths. The new binding is opt-in for browser interactions;
ordinary setting tools have no new transport requirement.

A typed HTTP reader returns current phase/deadline and public receipts only.
Ownership, current operator/dependent capabilities and administrative authority
are checked again after the final session lookup. Expired pending/waiting
observations expose no live interaction and retain partial commit truth. Work
already claimed remains in progress until its actual receipt is known; the
reader does not pretend to cancel it at the approval deadline. Observation
writes no command state. Responses are no-store; dependency faults are finite
503 responses with no private diagnostic. Cookie names follow current settings.

Evidence: final application/coupling run passes 411 checks. Twenty-one focused
transport/status/HTTP checks pass. Seven final PostgreSQL/Redis migration and
authority checks pass, including legacy-record preservation, both historical
base/additive schema replays and current-role withdrawal during session reads;
the preceding integration run passes seventeen including waiting/number flows.
Strict MyPy on five modules, scoped Ruff and complexity/size instruments pass
without raising a baseline. One additive Alembic head remains. The developer or
production database has not been migrated by this qualification.

This closes the backend persistence/read prerequisite only. Browser consumers,
completion/resume claims, executable secure/device handlers and their application
operations remain open; no new secure action is offered and the tool count is
unchanged. This helper is session-bound; precise tab/device addressing will be
added for device-specific operations.

### Lot 4 prerequisite — browser command observation, cold review

The browser parses a finite status/receipt contract before accepting data. The
query reuses the existing API abort/refresh owner and account-lifetime guards,
with an additional command lifetime. Late responses and old callbacks cannot
cross account or command A-to-B-to-A transitions. Malformed or transient reads
preserve the last accepted card; authoritative denial withdraws its cached data
and keeps it hidden while retrying. Invalid command identifiers make no request.
The browser sends neither an actor selector nor credentials in the request data.
Observation remains data, never permission to dispatch an action.

Evidence: ten actual hook/protocol tests pass, including late responses,
same-account command changes, denied/retry behavior and incoherent secure/device
receipts. Non-incremental TSC and scoped strict ESLint pass. All official frontend
ratchets pass without raising a baseline (CC 42, hooks 31, a11y zero). No secure
form, completion handler or application interaction card is connected yet;
those depend on the explicit resume/execution policy in the next slice.

### Lot 4 prerequisite — fenced continuation claim, cold review

The continuation authenticates the owned immutable command, current operation,
live originating session and applicable recent step-up before any return,
including an already-running result. Review caught an early phase return that
skipped session authorization; a real PostgreSQL/Redis regression reproduced
it before the correction. The owned command row is locked before final
authority checks, so a capability withdrawal during a SQL lock wait is honored.
The claim preserves the waiting receipt, rotates the claim token and commits
before a future handler may act. An old caller cannot close the resumed command.
An in-progress observation keeps partial committed facts in `prior_outcome`
without offering the old interaction again. Approval expiry does not falsely
declare an already-running effect cancelled or complete.

Evidence: 426 application/core unit checks pass; 20 PostgreSQL/Redis regression
checks pass, followed by 11 focused checks including simultaneous independent
workers, actor withdrawal during the live read, capability withdrawal during
the actual command-row wait, and corrupted receipt/digest/token refusal. The
strict backend check passes on four source modules; scoped Ruff, cold frontend
typecheck and strict ESLint pass. Eleven frontend protocol/hook checks pass;
the official frontend complexity ratchet remains unchanged. No threshold was
raised. This is the claim/status prerequisite only: no continuation HTTP route,
secure handler, device acknowledgement or connected interaction card is yet
delivered. A future effect must have its own immutable ledger event referencing
the original exact approval; the original waiting effect must remain unchanged.

### Lot 4 prerequisite — bound proposal/executor authority, cold review

Before adding the first bound secure action, the proposal and confirmed
executor paths now reread its original live session too. Eight regressions
first failed against missing, other and revoked sessions, and operator
withdrawal inside the origin read. The correction uses the transport context,
never an intent field, and rechecks capability, current account and applicable
admin authority after the asynchronous session lookup. Legacy unbound normal
preference drafts retain their existing contract. Bound checks precede cached
effect-result access through the existing authorized executor wrapper.

Evidence: 14 real PostgreSQL/Redis boundary cases pass, including admin
downgrade and inactive account during the lookup; the combined origin/native
phone HITL regression is 29 passing checks. The 426 application/core units,
strict MyPy for the touched owner, Ruff and owned complexity checks pass.
No business action occurs in proposal validation, and every refused command
remains pending without a claim token. No frontend changes in this slice;
the prior frontend qualification remains applicable. No ratchet was raised.

### Lot 4 prerequisite — source session revocation, cold review

The shared Redis primitive validates every selected live owner and index entry
before deleting anything. It removes only the frozen selection, preserves any
session created later and tolerates expired targets without resurrecting them.
Where applicable, current-session presence, exact current step-up timestamp,
freshness and the approval deadline are checked inside that same mutation.
No raw session id, cookie, credential or proof is returned or logged. A lost
Redis acknowledgement remains an unknown completion for the future adapter;
it must not trigger an automatic replay.

Cold review found that the existing UI revoke-others path could still operate
after its current session or fresh proof was withdrawn. Two real Redis cases
reproduced that defect, then passed after both UI revocation entry points
delegated to the shared primitive. Invalid owner/index/malformed target states
refuse the whole selection, without a hidden partial revocation. Existing
fleet tests now assert the resolved identities handed to that owner, rather
than a particular old transport method. The stale activity-touch test was
aligned with the already-existing atomic field writer, preserving its rate,
TTL and metadata expectations with an additional real Redis oracle.

Evidence: 688 auth/session/application units pass; 23 combined source/session
Redis regressions pass before the final adversarial additions, and 14 final
Redis checks pass. Strict MyPy on both source modules, scoped Ruff, owned
complexity and the coupling-cycle gate pass. The global SLOC gate retains the
known unrelated journal owner failure; it is neither a new session violation
nor waived. No cap was raised, and shrink-only recalculation found no eligible
owned cap reduction. Native revocation tools/secure handoff are not connected
yet. The caller still owns fresh account/capability authority and exact HITL.

### Lot 4 slice — one owned browser-session revocation, cold review

The native action selects an owned opaque display id through the same session
metadata projection as the UI. Preparation writes only its pending command,
with an encrypted original-browser binding. The existing exact-HITL dispatcher
reauthorizes before its effect gate, locks the fresh actor before the command,
and delegates to the shared Redis selection primitive with the actual approval
deadline. Target identity/creation time and current-session identity are checked;
volatile last-seen data does not create a false conflict. A disappeared target
is an explicitly acknowledged no-op; cancelling or a withdrawn capability
never claims the effect. Revoking the current server session is stated as able
to interrupt delivery; no browser logout acknowledgement is fabricated.

The native editor exposes only the selectable display id, rereads its metadata
and replaces the exact digest through the original live origin. The confirmation
identifies the device, public id and creation date in every locale, without a
cookie, proof or raw JSON field names. A lost Redis acknowledgement after a
real revocation produces COMPLETION_UNKNOWN and keeps the unique claim; the
failed receipt cannot announce success or automatically replay the action.
The addressed SSE hint carries only identities/field names and refreshes the
owned sessions query through existing account-lifetime/resource hooks.

Adversarial review of the touched UI found old-account list data, confirmation
state and parked reauthentication that survived an account change. Tests first
reproduced each case, then passed with shared account state and an opt-in scoped
step-up guard. Old callbacks cannot issue HTTP or resume a parked operation,
including A-to-B-to-A; unscoped existing callers preserve their contract. Busy
state and notifications cannot migrate to the next account. Existing section,
dialog and card templates provide the layout; no separate UI styling was added.

Evidence: 735 application/auth/registry/coupling unit checks pass, 20 real
PostgreSQL/Redis source/HITL/editor/ACK checks pass, and an additional independent
worker test observes an actual pg_stat_activity Lock before an operator turns
the persisted switch off and prevents Redis mutation. Strict MyPy on 14 source
owners, scoped Ruff, owned complexity and six-locale parity pass. The frontend
has 59 passing hook/dialog/security checks, cold non-incremental TSC, scoped
ESLint and all three official ratchets passing without raised caps. The final
global SLOC gate also passes; previously reported unrelated journal failures
were repaired concurrently and are no longer claimed as current failures.
There are now 34 registered application tools. No physical-browser, live
provider or production evidence is claimed; the secure revoke-others flow,
continuation HTTP handler and the remaining original lots are still open.

### Lot 4 prerequisite — exact persisted approval for continuation, cold review

The browser continuation now validates the original immutable waiting effect,
not only the mutable command phase. Actor, executor, policy, draft-critique
reference, original key, schema, call/content digests and the encrypted receipt
must agree exactly. Missing, duplicated, malformed, truncated or mismatched
authority is refused. The receipt is compared with the command's prior outcome;
neither a different interaction nor different partial-completion facts pass.

The command and the new effect claim commit together before any external work.
The new event carries the same exact approval and originating run/thread, with
an idempotency key referencing the immutable handoff event. It is not a retry
of a failed action. Two independent PostgreSQL workers produce one winner;
write failures before and after insertion roll both fences back. A lost commit
acknowledgement cannot automatically grant another attempt. Authority is read
again after ledger I/O. Normal authorization still precedes repeated status
access. The original waiting event is never rewritten as completed.

Cold review covered cross-account access, late authority withdrawal, expiry,
receipt/call mismatch, duplicate originating threads, raw credential exposure,
bounded lookup and shared ledger ownership. Seventeen real PostgreSQL cases
cover authority tampering and deep notarized-chain verification; fifteen real
PostgreSQL/Redis checks cover independent races, rollback and prior regressions.
The application/registry/coupling/global-size unit selection passes 465 checks.
Strict MyPy on both owners, Ruff and the repository complexity instrument pass;
no baseline was raised and no eligible owned size reduction was found.
This closes the approval/claim prerequisite only. Actual secure handlers,
HTTP continuation, browser interaction and the remaining original lots remain.

### Lot 4 prerequisite — frozen other-session revocation, cold review

The auth owner now resolves the originating live session once and builds the
other-session selection from a bounded, complete owned index. Public display
identities and aware creation timestamps identify the selected rows; raw
cookies and step-up stamps stay local. Incomplete metadata, duplicate targets,
unknown/current targets and malformed identities are refused. Both native
single-session and fleet resolution share the same authenticated owner seam.

Execution locks and refreshes the account, checks the original current display
identity and immutable target identities, then calls the existing atomic Redis
primitive with fresh step-up and the approval deadline. Targets that expired
are acknowledged no-ops; sessions created after the preview are not included.
A capability withdrawal or account deactivation during the final callback is
rechecked before the mutation. Withdrawn proof is also rejected inside Redis.
Lost Redis acknowledgements retain the existing unknown-completion contract.

Cold review covered empty selections, partial expiry, owner/index corruption,
original-session rotation, mutable last-seen metadata, fresh proof withdrawal,
new-session preservation, one bounded metadata query rather than N+1 lookups,
and existing single-session regressions. The combined PostgreSQL/Redis source
selection passes 33 checks. Two additional schema defects (invalid displayed
identity and naive creation time) were reproduced red and corrected. Auth,
application, coupling and global size checks pass; strict MyPy on three owners,
Ruff and owned complexity pass. No quality cap increased. Native tool exposure
and its secure browser continuation remain the next slice.

### Lot 4 prerequisite — approved secure handoff, cold review

The secure-handoff operation kind is now accepted by canonical approval
validation only with an encrypted originating-session binding. Its approved
execution produces an explicit secure waiting receipt and no business effect,
state invalidation or authentication proof in the model context. The real
effect repository records that immutable handoff under the exact draft critique.
Normal preference drafts and the secure family use one canonical envelope
builder; a future unsupported schema version refuses preparation rather than
silently writing the old version.

Cold review reproduced two withdrawals during command claim: the initial
implementation still requested handoff after the operator disabled the family
or the account became inactive. Both cases now reauthorize after claiming and
close as failed, with no session deletion. The executor separates application,
outcome classification and fenced completion without adding complexity or
changing existing partial-write receipts. Unbound secure drafts fail before
an effect can even be claimed.

Evidence: five real PostgreSQL/Redis handoff cases use the real exact-approval
ledger; the combined handoff/single-session HITL/editor selection passes 14
checks. Application, native registry, coupling and global size checks pass 467
tests. Strict MyPy on six owners, Ruff and owned complexity pass; no cap was
raised and no eligible size reduction was found. This family is deliberately
not registered or offered yet: completion dispatch, HTTP, localized preview,
browser interaction and tool registration must be delivered together next.

### Lot 4 prerequisite — atomic continuation settlement, cold review

Completion now validates the two matching owned fences, exact executor,
approval reference and call/content digests, then closes the mutable command
and the new effect event in one transaction. Wrong/stale tokens and tokens
mixed from two otherwise valid records cannot settle either row. A failure
after an actual write rolls the transaction back; unresolved state stays
unresolved and cannot authorize replay. Failed outcomes retain explicit
partial-commit facts. Recording a returned result is independent of subsequently
withdrawn permissions; serving it still uses the existing fresh authorization.

The original immutable waiting event is not touched. Repository completion
keeps its default committed contract for existing callers and offers explicit
transaction ownership to this paired writer. Cold review checked conditional
close failures, duplicate settlement, cancellation/exception rollback, private
payloads, and mixed-record attribution. Six real settlement cases and the
handoff/waiting regressions pass the final 16-case PostgreSQL/Redis selection;
the preceding combined claim/settlement selection passed 18 cases. The final
application/registry/coupling/global-size selection passes 467 checks. Strict
MyPy on both owners, Ruff and owned complexity pass; no quality cap increased.
Actual secure execution, HTTP continuation, browser controls and the new tool
exposure are still outstanding.

### Lot 4 prerequisite — real secure continuation dispatch, cold review

The finite secure dispatcher now executes the frozen other-session selection
under the original approval and current originating session. It records actual
removed/approved counts, distinguishes an already-expired selection from a
failed attempt, and preserves sessions created after preparation. Repeated
requests observe the persisted result; a lost Redis acknowledgement becomes
COMPLETION_UNKNOWN, with no raw diagnostics and no automatic replay. Claims
and completed outcomes use the existing effect metrics and original attribution.

Cold review reproduced a downgrade in a secure operation's receipt: declaring
it as a device interaction could bypass step-up in the generic claim seam.
The operation catalogue now governs the requirement, and an inconsistent
receipt is rejected. A combined 29-case PostgreSQL/Redis selection covers this
fix and the previous exact-approval/concurrency regressions.

Cancellation after a Redis effect also initially left the continuation open.
It now records an explicit unknown outcome, completes settlement through the
existing bounded cancellation shield and propagates cancellation. The writer
owns a separate SQL-session lifecycle, so cancelling a request cannot close a
session still used by its completion task. Nine real PostgreSQL/Redis checks
cover the actual secure flow, lost ACK, cancellation, proof/ownership/capability
refusals and a real independently owned writer cancelled during settlement.
Application/registry/coupling/global-size checks pass 467 tests; strict MyPy
on four affected owners, Ruff and owned complexity pass. No cap increased.

This closes the service prerequisite only. No secure POST route, browser card
or public tool registration is claimed. Before exposure, the count/consequence
preview must remain bounded for prompts while the full canonical selection
remains intact for approval and persistence. Empirical source inspection shows
DraftService provides explicit id/type structured data (used before registry
fallback by ReAct), but its textual summary is built from the detailed preview;
the new preview must therefore be explicitly bounded rather than assumed free.

### Secure continuation HTTP boundary — cold review

The POST route takes only the command UUID in its path and an empty optional
body. Its principal and originating cookie come from the existing authenticated
session dependency and the actual request; actor/proof fields are refused.
The existing step-up challenge shape is preserved for the browser guard.
Finite no-store 503 responses distinguish unavailable dependencies from an
unknown completion, without exposing provider diagnostics or implying a retry.

Seven ASGI boundary cases pass. The actual continuation selection now runs
through both the service and HTTP transports: 16 PostgreSQL/Redis cases pass,
including repeated observations, proof withdrawal, other-origin rejection,
missing approval, operator disable, expired targets, lost ACK and cancellation.
All 474 application/registry/coupling/global-size checks pass (one Windows
pytest-cache warning). Ruff/Black pass. Native MyPy passed with an isolated
cache after its shared-cache binary crashed; the installed Python sources of
the same version independently passed too. No threshold increased, no live
database migration, no browser assurance claimed. The route is integrated in
the existing API router; secure tool exposure awaits preview and browser work.

### Lot 4 slice — other-session secure tool and browser completion, cold review

The native registered tool now freezes the complete owned selection before HITL.
Its localized preview stays bounded at four lines even with a large fleet;
the full selection remains in the exact approved command. Editing refreshes
the selection under the original session and requires a new approval. Read-only
operations cannot acquire an action preview through the generic renderer.

Only owned UUID references travel through the existing completion/archive
metadata. Every card rereads current authorization and command state. The native
step-up dialog keeps credentials outside chat, and account/command lifetimes
fence parked challenges and late responses. Uncertain responses offer observation
without automatic mutation replay. Cold review covered catalogue/startup parity,
private projections, immutable approvals, focus, expired commands, changed actors,
operator withdrawal and independently owned SQL completion.

Validation: 24 real PostgreSQL/Redis scenarios across service, HTTP and independent
HTTP writer transports pass; the writer tests use actual commits so another
connection observes the request. Five draft-edit integration cases and 515
application/registry/architecture checks pass. Nine focused frontend cases and
the complete frontend lint/type/accessibility/hooks/complexity gate pass.
Three hermetic Chromium journeys on an isolated production bundle cover desktop,
320 px, native password step-up, keyboard focus, axe, reload, and lost response
followed by observation without another POST. Strict isolated E2E typing passes.
The test servers are closed; the existing development server is preserved.
The backend complexity cap was tightened with the shrink-only ratchet.

This closes this slice, not the whole security/automation lot. No live database
migration, paid provider probe or physical-device qualification is claimed.

### Lot 4 prerequisite — shared account-export queue writer, cold review

The source endpoint delegates its existing queue rules to a shared domain
command. Its pre-check and unique-index race loser retain the same 400 contract.
Confirmed callers may bind the job identity, provide current authorization
checks before and after the inflight query, and obtain a commit receipt before
refresh/projection. The source endpoint retains its existing step-up and rate
limit dependencies. This extraction exposes no new assistant action yet.

Cold review checked duplicate queueing, transaction ownership, post-commit
projection failure, feature withdrawal, paths, metrics and source behavior.
The 67 export/source unit checks and four real PostgreSQL export/write/read
checks pass. The first broader unit run hit the sandbox's temporary-directory
permission; rerunning with an owned temporary path passes. Strict MyPy and Ruff
pass. No exporter, archive content, retention or download behavior is changed.

### User-tools slice — full-account export request, cold review

The native export request now prepares exact full-account confirmation, then
waits for secure participation by the originating browser. The shared source
writer retains the existing per-account request budget and unique active-job
constraint. It locks current account authority, rechecks policy after the lock,
and rereads live step-up/expiry before insertion. The job identity is bound to
the command; repeated continuation reads its durable result. The registered
export gateway carries the command, preserving the existing domain boundary.

The browser uses the existing step-up dialog, strict command parsing and account
lifetimes. Six-language copy distinguishes a requested export from a ready
archive, and preserves a committed request when later projection fails. The
owned export section refreshes through the existing resource invalidation seam.
The bounded preview describes personal-data scope and asynchronous preparation;
the editor receives an empty refresh request and no credentials or actor.

Cold review found two defects before closure: a direct source import introduced
a domain cycle, corrected through the existing injected gateway; draft refresh
omitted its originating session, reproduced by a real SQL test and corrected.
Three edit and six actual tool/HITL/continuation scenarios pass, including
concurrent active jobs and projection failure after commit. The preceding mixed
40-case integration selection passed 39 cases; its remaining conflict-code
assertion was corrected by the final six-scenario replay. Application/registry/
architecture checks pass 496 cases; the final preview/schema/source selection
passes 16. Frontend tests cover secure requests, partial outcomes and owned
settings refresh. Strict MyPy, Ruff, six-locale parity and backend complexity pass.

Four hermetic Chromium production-bundle journeys pass: desktop, 320 px,
lost response without replay, and the export request with native password form,
keyboard focus, axe and archived reload. The mobile export capture was inspected.
Full frontend ESLint, accessibility, hooks and complexity gates pass; the final
fresh nonincremental type check passes after concurrent test typing was corrected.
The complexity baseline is tightened through the official update script.
Only the dedicated test server was stopped and its generated type includes removed.

This closes request/status handling only. The native archive-download handoff
remains in the user-tools lot. No real provider call, physical-device test,
production deployment or live migration is claimed. Administrative tools remain
deferred until all user tools are delivered and the requested pause has occurred.

### Routine-state source prerequisite — cold review

The shared service now accepts a desired enabled state. An unchanged state
leaves the recurrence clock and error counters intact; re-enabling a running
routine preserves the scheduler's executing reservation. The existing UI toggle
uses the same writer. Four RED tests reproduced the missing contract; 67
service/clock/tool checks and seven real PostgreSQL clock/state checks pass.
Strict MyPy, Ruff and the complexity ratchet pass. The assistant toggle's
confirmation conversion and native application coverage remain to implement.

### Routine enabled state — cold review

The native desired-state tool and the legacy toggle now prepare the same
durable application proposal. The compatibility toggle resolves its opposite
state only during preparation; execution never toggles again. Both callable
identities are withdrawn by the application-tools platform capability. The
legacy catalogue reports a pending draft rather than an already changed state.

Configuration identity includes the source create fields, timezone and creation
instant; execution counters and scheduler bookkeeping are deliberately excluded.
An owned row lock and current actor lock protect the comparison and source write.
Authority and expiry are checked again after source I/O, before commit; a
withdrawn capability rolls back the source update. Deleted or reconfigured
routines return a stale-state conflict. Unchanged desired state is a verified
no-op; executing reservations survive an enable or pause.

The four-line preview is localized in six languages, names the routine and
before/after state, explains ongoing execution and potential future LLM costs,
and hides the configuration digest. Editing refreshes the owned snapshot and
replaces its pending approval digest. Result projection hides comparison data.
Committed changes invalidate both the owned list and week queries. Queries and
parked mutation callbacks belong to the account lifetime.

Verification: 492 application/automation/architecture unit checks, 16 source
and real-tool HITL PostgreSQL scenarios, two real edit scenarios, and two
deleted-target scenarios pass. Frontend query/invalidation coverage passes 42
checks. MyPy, Ruff, nonincremental TypeScript, scoped ESLint, six-language key
parity and both complexity ratchets pass without raising baselines. Cold review
corrected late capability withdrawal, legacy output metadata and deleted-target
classification. No paid call or physical-device qualification is claimed.

This closes routine enable/pause only. Full routine reads and Studio CRUD are
next in the non-administrator lot; administrator tools remain deferred.

### Full routine reads — cold review

The native reader exposes Studio settings and the computed current week using
the source DTOs, including recurrence/condition settings, approval/execution
mode, clock metadata and run outcomes. The source's excluded condition-fact
ledger stays excluded. The UI and native reader share one week serializer.
No background execution, provider request or database mutation is performed.

Pages use the owned primary key in stable order with a look-ahead row. Selected
week reads filter the source routine query; the existing UI keeps its ordering.
Returned rows, total available, source truncation and continuation are explicit.
The public tool projection puts rows at the shared item-budget seam. When the
model result budget cuts a page, the existing cursor projector now carries the
last actually visible routine id. Thus a cut preserves whole rows and can be
continued without omitting the undisplayed rows. The legacy listing is also
withdrawn by the platform switch and rechecks current authority around its read.

Cold review corrected nested result budgeting and added real continuation and
foreign-account probes. Eleven native/legacy/read/ownership PostgreSQL scenarios
and seven source clock scenarios pass; 573 application/source/wrapper/coupling
unit checks pass. Strict MyPy on nine owners, Ruff, Black, locale parity and the
backend complexity ratchet pass without widening a baseline. The existing week
HTTP contract is covered by its unchanged controller tests. No paid or physical
device probe is claimed. Native Studio CRUD remains the next user-tools slice.

### Studio routine creation — cold review

The native creation contract inherits the Studio settings and tightens unknown
fields, nested conditions and the approval boolean. It supports both clocks,
future-trigger approval and execution mode; account timezone is resolved before
preview. The full instruction/configuration and future-cost/approval mandate
are shown before a write. Editing refreshes the proposal and invalidates its
previous approval digest; it cannot choose ownership, timezone or target id.
Creation never invokes the routine immediately.

The existing source writer accepts the command's deterministic creation id.
A reproduced PostgreSQL race previously consumed the same final slot twice;
the UI and native writer now reserve the owner row while counting and inserting.
The source deadline/timezone validator is shared by preview and creation.
Fresh actor/capability checks surround the native writer, including after its
flush, before commit. A changed timezone conflicts; a spent slot is a finite
constraint refusal. An uncertain commit reports COMPLETION_UNKNOWN with no
automatic replay. Its stable target id permits subsequent observation.

Legacy time-only creation remains compatible and now obeys the same platform
switch at proposal and execution. All three legacy automation identities are
withdrawn by that switch. Native creation uses the existing application command,
approval, effect, result and owned-resource invalidation contracts.

Verification: 528 application/automation/source/architecture unit checks pass,
including strict schema and six-language preview/editor checks. Fourteen real
creation/confirmation/legacy/quota-race PostgreSQL scenarios, two edit scenarios
and two lost-commit-acknowledgement simulations pass; the source clock regression
also passes. Strict MyPy on twelve owners plus the final uncertain-commit writer,
Ruff, Black, translation parity and the backend complexity ratchet pass. Review
corrected source quota concurrency, legacy switch bypass and uncertain completion.
No provider execution, physical-device test or full-lot completion is claimed.
Update/delete/manual execution and the remaining user tools are still pending.

### Routine removal — cold review

The native deletion freezes the owned routine configuration and uses the
source deletion/cascade after exact approval. A changed or missing target is
a stale-state conflict. The preview explains permanent history deletion and
the fact that an already launched run may finish and keep its costs; it hides
the private comparison digest. Editing rereads the target and replaces approval.
Results expose the removed id/title only; owned routine queries are invalidated.

Owner/target locking, current capability/actor/deadline and final commit handling
are shared with the enabled-state writer. The state regression passed after
this extraction. Unknown commit acknowledgement remains non-replayable.
The SQL cascade and rollback after operator withdrawal are tested with real
routine/run rows. Seven removal/confirmation/source cases and twenty state
cases pass together; two real edit cases pass. Application/registry/coupling
and global size checks pass 497 cases; strict MyPy on eleven owners, Ruff,
Black, locale parity and the complexity ratchet pass without relaxing caps.
No running provider job was invoked or physical device qualified. Update and
manual execution remain the next user-tools slices.

### Routine configuration update — cold review

The native edit freezes the sparse requested changes and the complete resulting
Studio configuration, timezone and enabled state. The source clock rule is used
both for preview and write. Giving a completed routine a future clock may revive
it; an explicit pause is preserved and the confirmation shows that consequence.
Renaming and no-op edits preserve the pending clock. Switching clock kinds drops
the other kind's settings and changing watched facts clears the private ledger.

Execution locks the owner and exact routine, checks the current configuration
and recomputed result, and rechecks actor/capability/expiry after source writes.
A withdrawn capability rolls back the edit. Editing a proposal refreshes its
source comparison and replaces the approval; comparison data cannot be supplied
through the editor. Preview and result exclude the private comparison digest.
The existing account-scoped Studio invalidation is reused.

Verification: 709 application/source/global-size unit checks and 42 real
PostgreSQL update/HITL/editor/state/source-clock cases pass. Strict MyPy passes
on eleven owners and the final rendering change; Ruff, Black, six-language
parity and the complexity ratchet pass without increasing a cap. The rendering
dispatch was simplified after the added branch reached the complexity threshold.
No paid execution or physical-device qualification is claimed. Manual execution
and the remaining non-administrative tools are still pending; administration
remains reserved for the second delivery lot after the requested pause.

### Manual routine reservation — source prerequisite cold review

The UI now uses a shared owned-row reservation service instead of a read followed
by an unlocked status write. The same row lock serializes a native launcher with
manual UI requests and the scheduler. Two real concurrent sessions produce one
reservation and one conflict; foreign and missing targets are hidden. The worker
also explicitly checks that the routine belongs to the account whose quota and
conversation it uses; its adversarial unit test failed before that correction.

Verification: two PostgreSQL scenarios and 239 focused source/worker/router unit
checks pass. Strict MyPy on the four source owners passes after typing the SQL
result; Ruff, Black and the complexity ratchet pass. A broader router-contract
selection also exposed five unrelated MCP/run-lock/HITL mock failures, recorded
in the qualification log; those are not reported as green or silently weakened.
The native launch tool and deferred-worker exact authorization are not yet
implemented at this prerequisite boundary. No model/provider run was performed.

### Deferred manual authorization — cold review

Each reservation has a nullable opaque token, assigned by manual launches and
scheduler claims and cleared by settlement/recovery. Cancellation compares that
token: a late job cannot release a newer run. The additive migration was executed
both ways on PostgreSQL without altering legacy routine data. No development or
production migration was run. The private token is absent from public DTOs.

The deferred policy waits for the current chat lease within the approval deadline
without holding a SQL session. The source worker accepts an optional exact guard
before source work, after condition reads and before inference. The guard rereads
ownership/configuration/reservation/actor/capability and cancels only its own
reservation on refusal. Inference holds no authorization transaction. Existing
scheduler/UI quota, condition and approval paths remain authoritative.

Eleven real reservation/policy/DDL PostgreSQL scenarios and 252 source/worker/
policy/global-size units pass; 35 final worker/policy checks pass after simplifying
complexity. MyPy passes five owners and the final worker. Ruff, Black and the
complexity ratchet pass without raising caps. No paid run was performed. The
native launch remains to be registered; accepted work must not be called completed.

### Native manual routine trigger — cold review

The registered tool selects one owned routine and shows its full saved Studio
instruction/configuration/timezone. Preparation reserves nothing. Exact HITL
locks the owner/target, revalidates the configuration and writes one source
reservation identified by the command. Only acknowledged commit launches the
deferred worker; lost acknowledgement is not replayed. Enqueue failure after
commit reports post-commit failure and preserves the truthful reservation.

The worker waits for the confirming chat lease, then uses the guarded source
executor. Conditions, approval notifications, pending questions, retry/cost
accounting and usage ceilings keep their existing semantics. The receipt and
six-language result text explicitly say the request is recorded, with
execution_completed=false; the actual result is read from Studio/week history.
The source account-scoped polling and command invalidation are reused.
Editing refreshes the saved instruction and replaces approval; it cannot inject
a new instruction or comparison data. Private digests/tokens stay out of preview.

Adversarial review reproduced expiry during the final authority read, then
added a final deadline check. The regression now passes. Verification: 744 broad
application/source/worker/global-size units, thirteen focused final contract/
deadline checks, twenty final real PostgreSQL policy/native HITL/editor/worker
scenarios, and the earlier four reservation/DDL scenarios pass. The real worker
simulation records one successful manual run, refuses changed instructions, and
generates nothing on quota refusal; only generation/notification are substituted.
MyPy passes twelve owners plus the final policy; Ruff, Black, translation parity,
single Alembic head and complexity ratchet pass without relaxing a cap. No paid
provider run, physical-device qualification or full non-admin completion is
claimed. Reminders and the remaining user surfaces continue next.

### Reminder management read — cold review

The native reader uses the management DTO extracted from the source router;
the router still imports and serves that same DTO. It includes the recurrence,
localized schedule and future occurrences, and excludes the private original
message. Stable owned-id pages include a look-ahead item and pending count.
Foreign ids are hidden and a processing reminder is busy, rather than returned
as a pending item. It never claims to provide already-sent notification history.

Native and legacy reads check fresh application capability and account before
and after source I/O. The legacy discovery alias follows the platform switch;
its manifest now explicitly states the compact source page is not exhaustive.
Adversarial budget verification caught a stale returned-count/truncation envelope
after item projection. The shared resource-cursor seam now states the number
actually shown, marks the cut and continues after the last delivered id.

Six real PostgreSQL read/ownership/operator-withdrawal cases, 644 source/
application/registry/wrapper/architecture/size unit checks and 27 final projection
regressions pass. Strict MyPy passes ten owners plus the final cursor change;
Ruff, Black, translation parity and complexity ratchet pass without changing
caps. Existing mock-only legacy-card fixtures explicitly allow the fresh access
boundary, while the real database cases enforce it. Create/update/delete and
legacy direct-creation conversion remain the next slice; no full-lot completion
or administrator implementation is claimed.

## Reminder source arming and scheduler concurrency — cold review, 2026-10-07

Reviewed the service, repository, ownership fixtures and real PostgreSQL scheduler tests before native reminder writes. Creation and confirmation now share `resolve_reminder_creation`: account-zone conversion preserves seconds, recurrence derives its next instant and enforces the existing reminder limits. Source past-trigger acceptance is preserved and its misleading grace-period comment corrected. Creation optionally accepts a stable command identity without changing ordinary UI UUID defaults.

Source update/delete refresh the owned row with `FOR UPDATE` and `populate_existing`, sharing the scheduler's row lock. The adversarial case preloaded a pending row, committed a scheduler claim in another connection, then attempted an edit/delete: both originally mutated a stale object (RED), both now refuse PROCESSING (GREEN). Foreign ownership remains indistinguishable from absence. No scheduler network/model work is added under these locks. The listing documentation now accurately describes two READ COMMITTED observations rather than promising a single snapshot.

Evidence: 13 real PostgreSQL tests (7 source scheduler/identity, 6 native/legacy read boundary), 76 source/SLOC unit checks; MyPy two source files, Ruff/Black pass. Official backend CC remains 292 functions above its threshold, within the unchanged ratchet. Existing pytest cache Win183 warning persists. No live database migration or paid provider call.

## Native reminder creation and reminder refresh — cold review, 2026-10-08

Reviewed every creation schema, source adapter, manifest/alias, registry, executor, command/editor serializer, localized preview, result projection and invalidation consumer. The source writer remains the business owner. The exact account timezone and first UTC instant are approved; changing the account, flag, timezone, clock or schema refuses execution. No reminder row exists before HITL. Creation uses the command UUID and never retries an uncertain commit. The user's original wording stays out of execution reports. The nested recurrence contracts reject undeclared fields; source-field guard tests require explicit review when creation or recurrence models evolve.

The legacy temporal grammar is preserved but its direct write is removed: `create_reminder_tool` now prepares the same native confirmation. Its declared mutation policy and published output/reference paths describe a draft. Parser tests retain their temporal oracles at the proposal boundary; real PostgreSQL tests prove the permission, confirmation and write boundary. Old raw exception text is no longer relayed from that creation adapter.

Adversarial findings corrected during this slice: (1) a first trigger crossing during source I/O was committed despite the approved time elapsing; the final post-I/O check now refuses it, proven RED/GREEN; (2) a missing reminder field in the shared invalidation emitter caused a post-commit failure, caught by the real HITL test and fixed; (3) full/default versus sparse canonical JSON made a constructed preview inconsistent; preparation and the test now use the same `exclude_unset` contract; (4) the existing invalidation maximum omitted routine fields, now included alongside reminder fields without raising any quality ratchet.

`useReminders` now rereads addressed changes and isolates account data and parked callbacks before/after awaits. Today Briefing isolates both queries and refresh markers by account lifetime; a reminder event rereads only the always-live cards endpoint, with no synthesis or refresh POST. Source reminder notification code was checked: its LLM generation remains behind the existing usage-limit check and recorded billing path. Confirmation copy in all six languages explains that future notifications can consume accounted LLM tokens; no additional model invocation is introduced by preparation or invalidation.

Validation: 652 targeted backend units including source management, temporal grammar, manifest-reference contracts, private editor/preview checks in six languages, SLOC and coupling guards; 28 distinct real PostgreSQL cases (15 creation/HITL/authority/clock/editor/lost-ACK cases and 13 source-claim/read cases); final creation-only rerun 15 passed after canonical serialization adjustment. 43 frontend cases across seven files pass. Strict MyPy 13 application files plus the tool adapter; Ruff/Black; i18n parity pass. Official backend CC remains within its existing baseline. Final `task lint:frontend` succeeds: ESLint, accessibility, React-hooks, complexity and full non-incremental TypeScript. An earlier standalone global TSC failed on a concurrently incomplete foreign avatar module; the final official gate passes after that concurrent source changed, with no avatar edits here. Frontend ratchets remain accessibility 0, hooks 31 and complexity 42/max50, unchanged.

No browser/device journey or paid provider call was performed for reminder creation; browser validation is grouped with the complete reminder CRUD flow. No live migration, commit, push or deployment. Creation is closed; reminder editing/deletion and legacy cancellation conversion remain the next slice. The overall non-administrator lot remains incomplete, and administrator implementation has not begun.

## Native reminder deletion and archived-card binding — cold review, 2026-10-08

Reviewed source cancellation, row locking, ownership, immutable snapshot, proposal/legacy aliases, exact native confirmation, editor, result projection, six-language preview and resource invalidation. Cancellation deletes the pending source row and all remaining occurrences; it never recalls an already delivered notification. Source processing, changed content/schedule, disappeared rows or withdrawn capability refuse execution. Native and legacy entries only propose. Historical REMINDER_DELETE drafts lack the full comparison contract and return SCHEMA_CHANGED with no effect; they require a fresh proposal.

Adversarial card review found the generic APPLICATION_ACTION shape would lose the old reminder-card binding. A strictly typed private archive selection now travels inside the encrypted reminder snapshot, is hidden from the preview/editor/result and is reloaded through the existing owned archive resolver before editing or execution. An archived card cannot silently change targets. Card context is always restored. Only the source read transaction is held during archive validation; no business write locks or model/provider calls are added there.

Evidence: 20 distinct real PostgreSQL cases across removal (7), native/legacy confirmation and switch/lost-ACK (7), archived-card execution/editor binding (6). The complete real HITL route rejects missing approval, performs the effect once and emits reminders invalidation only after known success; source disable after delete rolls back, actual committed-but-lost ACK returns COMPLETION_UNKNOWN. 579 application/card/registry/SLOC/coupling units pass, including six-language private preview checks. Strict MyPy five final source owners plus ten source files from the preceding check; Ruff/Black pass. Backend CC remains 292/max78 with unchanged caps. The normal pytest cache Win183 warning remains. Two initial test failures were fixture issues: UTC JSON uses Z, and the retarget test must choose another existing owned reminder to exercise binding rather than absence; corrected with the same behavioral oracles.

No new LLM invocation, secret exposure, state key, schema migration, frontend component or dependency. Existing account-scoped reminder refresh handles deletion. Browser qualification is grouped with complete reminder CRUD. This slice is closed; native reminder update is next. The overall non-administrator lot remains open. The user explicitly excluded new password/MFA/passkey/recovery/telephone-verification workflows; administrator work remains deferred until the agreed pause.

## Reminder source edit preview — cold review, 2026-10-08

Source update now resolves the entire requested public configuration before mutating the ORM row. Creation and edit share one private arming resolver, retaining UTC seconds, account-zone conversion, recurrence ceilings and the existing repeating-versus-single rule. Content-only edits retain the stored timezone, exact trigger and original recurrence JSON. Source behavior still accepts historical past single triggers and gives recurrence precedence for legacy dual-clock payloads; the native boundary will refuse those ambiguous inputs. An invalid schedule no longer leaves partially replaced content in the session. No model call, new lock or stored schema is introduced.

Reviewed nominal/content-only/single/recurring paths, due-clock calculation, pending scheduler locks, source router contracts and the private-data boundary. Four new pure/source failure tests pass; 71 reminder units and 29 real PostgreSQL source-claim/creation/removal regressions pass. After the final preserve-content-only adjustment, the 25 directly affected preview/management tests pass. Strict MyPy, Ruff and Black pass; CC remains 292/max78, unchanged. The existing pytest cache warning remains. This prerequisite is closed; the native exact-confirmed sparse update slice begins next.

## Native reminder edit — cold review, 2026-10-08

Reviewed the strict sparse source-derived delta, typed complete before/after configuration, source owner locks, native proposal/registry/manifest, executor/editor, private projection, localized preview and reminder invalidation. Content-only edits preserve the stored zone and exact trigger. A schedule change uses the authenticated account timezone and freezes the source's actual first occurrence. Source/current timezone, configuration or scheduler-state drift refuses execution. Native input rejects empty/null/extra/coerced text, dual clocks and a past first occurrence. Repeating reminders move through their full recurrence. Existing settings become explicit no-ops under exact confirmation.

Execution recomputes the source preview under refreshed owned row locks, verifies the source write equals the approved complete result and rechecks authority, expiry and the future first trigger after source I/O. A late clock or disabled capability rolls back; an actual committed write with a lost ACK returns COMPLETION_UNKNOWN without automatic replay or a success invalidation. Editing reparses only id plus sparse changes, replaces the saved command digest and invalidates prior approval. Comparison snapshots and original wording never enter editor prompts or result reports. All six preview languages show complete before/after content, UTC trigger, recurrence and stored timezone, with existing future-notification LLM accounting/quotas explained. No new model invocation or LangGraph state key.

Adversarial finding: Pydantic accepted numeric timestamps despite the published explicit date contract. Two RED inputs reproduced this conversion; the native edit boundary now requires a string date or datetime (17 final schema/private preview cases pass). Source creation/update rules remain shared, rather than reimplemented by the tool.

Evidence: complete reminder read/create/edit/delete PostgreSQL suite 54 passed before the final numeric input guard/no-op addition; final edit-only rerun 14 passed (source race, processing, timezone, crossed recurrence clock, content-only preservation/no-op, real HITL missing approval, source disable, actual lost ACK, post-I/O clock, command revision and injected setting). 716 application/source/parser/card/manifest/registry/SLOC/coupling units passed; final 17 schema/preview cases pass. Strict MyPy 15 owners plus final schema; Ruff all 23 touched source/tests and Black pass. i18n parity six locales and CC292/max78 remain unchanged; no ratchet raised. The established pytest cache Win183 warning remains. Existing account-scoped frontend refresh already consumes reminder events; only six progress strings were added. No additional browser/device run is claimed here; grouped browser and transport qualification remains part of the overall non-administrator lot. This business slice is closed; export download is next. Administrator implementation has not started and the excluded account-security workflows remain excluded.

## Declared browser interaction family — cold review, 2026-10-08

The existing DEVICE kind is now accepted by the native draft builder, canonical validator and preview/editor seam. One derived spec property determines secure versus device receipt; a receipt cannot downgrade a secure operation or replace a device operation with another proof kind. Both require the original encrypted session binding before exact confirmed execution. The original immutable approval, atomic continuation claim and settlement are unchanged. No device operation is registered yet and no new action is exposed by this prerequisite.

Four targeted contracts demonstrated three initial RED failures, now pass. 561 application/size/coupling units and 35 PostgreSQL/Redis approval/handoff/settlement cases pass. The actual confirmed dispatcher is exercised for both declared kinds across missing session binding, operator/account withdrawal during claim, preserved archive metadata and deliberately mismatched proof receipts. Existing secure actions retain mandatory fresh step-up; device interaction does not invent one. Strict MyPy seven owners, Ruff/Black and CC292/max78 pass with unchanged ratchets. No new model call, secret in receipt or state key. This small prerequisite is closed; exact export archive selection/streaming and browser control are next.

## Export archive selection and source reader — cold review, 2026-10-08

The existing owner-scoped download lookup is now shared and refreshes/locks the source row before UI audit updates. Ordinary UI downloads retain their authenticated FileResponse and filename; no new step-up is imposed. The source gateway now exposes an immutable archive snapshot and an owned bounded reader for the upcoming exact confirmed browser action. No path or archive bytes enter the snapshot; only metadata and a private comparison digest do. Actor then archive lock order matches the confirmed writer pattern. Fresh callbacks, source feature, actor, approval/retention deadlines and file identity are checked before audit commit. Every refused, cancelled or uncertain attempt closes the opened file. The reader runs bounded blocking reads on anyio's existing declared runtime and waits for each read before cancellation; the eventual HTTP response must own its final close.

Counter-checks corrected two false negatives before native integration: completed archives with legacy nullable completion/size metadata remain downloadable, using actual descriptor size; changing the configured storage root does not invalidate a job whose source-owned retained path still exists. No model can supply a path. A changed source path or file identity requires fresh confirmation. An observed Windows failure showed path stat and fstat had different ctime values (96 mismatches in 100 controlled probes); both preparation and initiation now use fstat from the opened descriptor, preserving the comparison rather than weakening it. Two initial unchanged-file integration failures are now green.

Validation: final 13 actual PostgreSQL cases across 11 download/ownership/retention/replacement/path drift/legacy/storage migration/partial read/withdrawal/lost-ACK cases and 2 export-read regressions. Actual committed-but-lost ACK closes the reader and refuses automatic replay. Windows file replacement after early close/withdrawal proves handles are released. 76 export/boot/SLOC/coupling units pass; preceding source UI-only 64 pass. Strict MyPy six owners and final five owners, Ruff/Black and CC292/max78 pass with unchanged ratchets. Existing cache Win183 warning remains. No dependency, production migration, model invocation or browser transfer is added by this source slice. Native tool, original-browser download endpoint, response lifetime and accessible control remain the next slice; no export-download completion is claimed yet.

## Native account-export download — cold review, 2026-10-08

Reviewed the public typed tool, immutable owned archive proposal, bounded source reader, real exact-HITL ledger, original-session continuation, single-use claim/settlement, HTTP response lifetime, editor, registry/manifests, six-language preview/copy and browser control. Preparation neither reads archive bytes nor increments the audit counter. The user selects only an owned job id; archive metadata, comparison identity and retention come from the source. The editor rereads that source and replaces the approval digest while retaining command identity and original session. Input refuses paths, URLs, digests and actor proofs. The public preview excludes the private comparison digest. No new model invocation, state key or dependency is introduced.

The source rechecks current actor, capability, session, archive identity and deadlines before recording one initiated request. No new step-up is imposed on downloads; other existing secure operations retain their source requirement. The response owns the file until success, partial transfer, cancellation or header/send failure. Initiation is reported separately from bytes received or a file saved on the device. A committed audit with lost settlement closes the reader and blocks replay; the immutable original HITL receipt is not overwritten. Browser refresh observes the authoritative result rather than automatically initiating again.

Two adversarial findings were reproduced and corrected. The custom response class broke FastAPI OpenAPI generation; the route now declares the standard streaming response while returning its owned reader response. A plain download anchor navigated away from chat on a JSON/503 error. A same-origin hidden frame now contains that navigation, with downloads allowed and scripts/top navigation forbidden; the actual browser sends the controlled HTTP-only SameSite=Lax session cookie. The link remains keyboard-accessible, blocks duplicate activation and expires locally even if status observation fails. Existing backend/ frontend guards and thresholds were not weakened.

Evidence: 12 final actual PostgreSQL/Redis cases exercise the public tool, real HITL, absent approval, other session, both switches, archive drift, transfer/send failure, lost settlement, editor replacement/injection/origin and continuation-cancellation regression. The preceding preparation suite has 4 passes and the source reader/read regression suite 13. The final backend unit run has 639 passes plus 29 native registry smoke passes, covering HTTP/OpenAPI/private dependency errors, six-language preview/editor and size/coupling gates. Strict MyPy 14 owners and final 3 changed owners, Ruff/Black and CC292/max78 pass. Frontend 15 component/interaction tests, the full lint/a11y/hooks/CC/nonincremental-TypeScript gate, and final E2E strict types pass. Three hermetic Chromium journeys cover desktop, 320px, exact confirmation, native download, actual cookie transmission, keyboard duplicate refusal, reload, truthful completion copy, error containment, axe and viewport containment; the 320px screenshot was inspected. Frontend ratchets remain a11y0/hooks31/CC42/max50. The first browser error-containment run was RED and the same final scenarios are GREEN.

The shared development container was externally stopped during a rebuild (exit0, not OOM); it was not restarted. Qualification completed in a separate local container without external networking, with a successful production bundle. Build-added tsconfig entries were removed without disturbing other changes. Existing pytest-cache Win183 warnings remain. No production, paid-provider, physical-device, Firefox/WebKit or live migration qualification is claimed. This download slice is closed; the non-administrator lot remains incomplete and administrator implementation has not started. The user's excluded password/MFA/passkey/recovery/telephone-verification workflows remain excluded.

## Shared memory management projection — cold review, 2026-10-08

The existing UI projection and source retention-settings snapshot are extracted into the memories domain for upcoming explicit management reads. Router-local names remain compatible aliases; list, detail, create/update and exports share the same converter. One demonstrated bug is corrected: explicit importance0 now remains0 instead of being replaced by the default0.7. Null legacy importance still receives the existing default. Retention classification, procedural protection and display vocabulary remain source-owned. Embeddings and optional biometric storage remain outside this displayed projection. No access, usage counter, embedding, model call, consent or write is triggered by conversion.

The zero-value contract was RED against the original router, then GREEN. 139 memory/schema/retention/supersession/size/coupling unit tests pass, followed by 2 final projection tests. An actual PostgreSQL HTTP test exercises list, owned detail and JSON export through FastAPI and confirms identical projections and zero usage writes even with automatic memory use disabled, matching the current explicit-management UI policy. Strict MyPy both owners, Ruff/Black and CC292/max78 pass; no threshold is raised. Existing pytest cache warning remains. Reviewed initialization, legacy fallbacks, same observation-time/policy snapshot, source ownership and absence of extra query/compute work. This projection prerequisite is closed; bounded native management reads and later confirmed memory mutations remain to implement.

## Native memory management read — cold review, 2026-10-08

The new get_lia_memories_tool reads the source's active owned management fields, one id or a strict category/page selection. It uses the shared UI converter and retention policy. Explicit management remains available when automatic recall is off, exactly as the current UI endpoints do; the fresh setting is reported, not changed. The tool is excluded from initiative and its manifest distinguishes this explicit management purpose from semantic recall. It does not generate embeddings, use a model, increment usage or change memory. Stored content remains data under the existing untrusted-content wrapper. Actor ids and arbitrary queries are not offered to the model.

Source rows, complete category counts and cursor anchor are read in one SQL snapshot. Counts remain available on an empty page and cover the full active set beyond the UI's historical list cap. Newest-first order matches the UI, with an explicit id tie-break. An owned invalidated anchor can continue a page without resurfacing that old fact; an unknown or removed anchor refuses and requires a new first page. A selected invalidated id refuses. Global capability and fresh active actor are checked before and after source I/O; the automatic-recall setting is projected after the latter lookup. The query refreshes cached ORM display fields and defers embeddings/biometric storage to avoid unnecessary allocation. No per-item query or new context/state key.

Adversarial RED cases demonstrated stale ORM content and an initial ordering that could not answer the latest-memory request economically. Both are corrected and exercised with actual PostgreSQL, including equal creation timestamps. Token-budget truncation now updates returned_count, truncated and next_cursor to the last memory actually shown, reusing the existing application cursor seam; the original reminder budget test stays green. Schema selection rejects coercion, unbounded limits, actor injection and mixed id/page filters. The operation, native names, manifests and six-language progress vocabulary are registered together; no threshold is raised.

Evidence: final 15 PostgreSQL cases pass after the typed SQL literal and private-column deferral, covering 205 memories across pages, exact aggregates, categories, selected ids, foreign accounts, invalidated facts/anchors, unknown cursors, inactive/disabled actors, post-I/O withdrawal, fresh opt-out, stale ORM and newest-first ties. 741 application/memory/registry/size/coupling unit tests pass before the final SQL-only refinements; earlier 40 direct contract/budget/native-registry cases pass. Strict MyPy six owners and the final query owner, Ruff/Black, i18n parity and CC292/max78 pass. Existing pytest-cache Win183 warning remains. No new UI flow or browser behavior is introduced by the six progress strings; no additional browser, paid-provider, production or physical-device qualification is claimed. This read slice is closed; memory pin/create/edit/delete and other non-administrator families remain open. Administrator implementation and the excluded account-security workflows remain untouched.

## Memory maintenance protection prerequisite — cold review, 2026-10-08

Automatic cleanup now deletes only the still-active, unpinned, unprotected owned candidate whose scoring inputs and source revision still match. A late pin, correction, use or procedural-category change withdraws deletion. Counters distinguish withdrawn candidates and failed deletes from actual purges. Content previews and raw database error strings were removed from this deletion log. The existing retention formula and invalidated-trail policy are unchanged.

Consolidation locks both selected rows in stable id order, checks fresh ownership, active state, pin/protection and selection inputs, and supersedes only an unchanged loser. No embeddings or biometric columns are loaded by this recheck. Importantly, fresh comparison rows are typed column projections, not refreshed candidate objects: an adversarial test proved that refreshing an object for one refused pair could conceal its correction when another selected pair reused it. The same test now passes; refused and failed pairs do not count as successful merges. Same-id and cross-account pairs refuse before SQL. The automatic extractor already holds the user's consent lock before retrieving memories; the manual pin command will use that same user-before-memory order.

Evidence: cleanup was RED on four late changes, consolidation was RED on four late changes, and the repeated-pair scenario was separately RED. The final combined run has 163 passes, including 12 actual PostgreSQL maintenance cases and existing memory/selection/retention/size/coupling units. Strict MyPy four owners, Ruff/Black and CC292/max78 pass without raised thresholds. A cleanup decomposition restores its complexity below the threshold. No new dependency, model call, consent change, production operation or browser flow. The source schedulers' existing distributed-lock lifetime is outside this bounded write-protection change; concurrent execution cannot bypass the fresh guarded commands. This prerequisite is closed. The actual native pin action remains to implement, and the overall non-administrator lot is still open.

## Shared manual memory pin prerequisite — cold review, 2026-10-08

The existing HTTP pin route now takes the user's write/consent lock before locking a fresh active owned memory. This order matches automatic extraction; consolidation and cleanup hold only memory rows and never invert that order. Deferred private columns avoid loading vectors or biometrics. A shared readonly lookup provides the same active ownership predicate for upcoming proposals. Manual management remains available with automatic recall disabled. A replaced memory cannot be pinned through a stale UI id.

The original UI path acknowledged a cached False-to-False unpin while the actual row remained pinned: the real HTTP/database test reproduced that defect and is now green. The invalidated-row test fixture was corrected to assert FastAPI's actual HTTP404 rather than expecting its handled exception to escape ASGI. Three final PostgreSQL HTTP cases pass, including the existing shared list/detail/export projection. Strict MyPy both owners and Ruff/Black pass; the source-lock version also passed CC292/max78. No new UI, embedding, model invocation or dependency. Reviewed fresh account withdrawal, owner predicates, inactive rows, transaction ownership and preserved automatic-use opt-out. This source prerequisite is closed; native exact-HITL pin is next.

## Native memory pin — cold review, 2026-10-08

The set_lia_memory_pin_tool accepts only an active owned id and a strict desired boolean. Its source-derived immutable proposal displays the exact fact and both pin states. The private comparison digest and source snapshot are excluded from editor prompts and public completion. Editing rereads the current source, retains command identity and replaces its saved approval digest; structural/actor/snapshot injection refuses. The action participates in the native identity, operation, catalogue, exact-HITL executor, editor, localized preview, public result and addressed memory-invalidation registries. It is excluded from initiative. No new graph state, embedding, model invocation, rate-limit seam or dependency is introduced.

Execution uses the shared user-before-memory lock, checks fresh account/capability/deadline before and after source writes, compares the confirmed fact and source revision, and reports only acknowledged completion. An already matching state still requires HITL and completes as an explicit no-op without a write or invalidation. A corrected, superseded or removed fact requires new confirmation. Both pin directions preserve automatic-memory opt-out. The maintenance prerequisite protects confirmed pins from late cleanup/consolidation; procedural category protection remains after unpinning. A lost commit acknowledgement reports unknown completion and the single-use command cannot be replayed.

The existing memory hook now reuses the shared account query/lifetime and resource invalidation. Retired account data and callbacks cannot reach the new account. A reread preserves loaded content and focus rather than replacing it with initial loading; the selected category remains in its query. It receives values only by authenticated reread, never from an SSE payload. These three frontend cases were RED before wiring and are GREEN; the reminder hook remains a regression control. No new responsive markup or secure-account form is introduced.

Evidence: 11 final PostgreSQL execution cases pass for exact confirmation, pin/unpin, no-op, corrected/invalidated rows, capability/account withdrawal, expiry, post-write withdrawal/deadline, lost commit acknowledgement and replay refusal. Three final PostgreSQL editor cases pass for refreshed content/digest, injection refusal and disabled capability. The editor fixture was repaired to provide the real draft id required by matches_command; the production signature was preserved. The broad backend run has 744 passes after public-result decomposition, covering six-language/private preview/editor contracts, existing application/memory contracts and SLOC/coupling guards. Strict MyPy 16 owners, Ruff/Black 18 files, i18n parity and CC292/max78 pass. Five memory/reminder frontend integration tests and the full official frontend lint/a11y/hooks/CC/nonincremental-TypeScript gate pass with unchanged thresholds. The public result decomposition keeps reminder contracts green and avoids raising the CC cap. No paid-provider, full Pipeline/ReAct conversation, new browser/device or production qualification is claimed by this bounded slice; the planned overall non-administrator qualification remains open. This pin slice is closed. Native memory creation/edit/deletion and remaining non-administrator families remain open; administrator work and excluded security workflows have not started.

## Shared memory creation contract — cold review, 2026-10-08

UI creation now delegates its complete existing MemoryCreate configuration through one typed service mapping. The source service accepts an optional internal identity for future single-use native commands; ordinary UI creation still receives a generated identity. Initial procedural pinning is owned by one source predicate, distinct from protection after explicit unpinning. Existing extraction callers and defaults remain compatible. A schema-to-command guard refuses a future UI field that the shared mapping would silently omit. No model-selected actor, identity, pin, vector or biometric value is exposed by that UI contract.

The mapping guard was RED before the method existed. The combined memory/SLOC/coupling/source run has 142 passes, including two PostgreSQL persistence cases with deterministic identity, zero importance, procedural/personal pin defaults, char count and simulated missing vectors. A final three-case PostgreSQL run additionally exercises actual HTTP UI creation with its generated identity and disabled automatic recall. Strict MyPy three owners, Ruff/Black and CC292/max78 pass without relaxed thresholds. No paid probe or UI redesign. This prerequisite is closed; the native creation proposal, quota checks, post-approval embedding preparation and guarded write remain next.

## Native explicit memory creation — cold review, 2026-10-08

The create_lia_memory_tool inherits all source UI creation fields and constraints with strict scalar values and no actor/id/pin/vector/biometric injection. Preparation performs no provider call or memory write. Exact HITL freezes full values and the deterministic command/creation identity. Procedural initial pinning uses the source predicate. The editor receives only editable source configuration, retains identity, replaces the saved approval digest and performs no paid work. Six-language previews show the complete fields, initial pin and source embedding-cost/degraded-storage policy. Automatic recall opt-out remains unchanged.

After approval, each logical content/topic vector preparation checks fresh capability, active actor, deadline and the shared user/instance spend guard. The helper is declared in the existing chokepoint registry. Provider rate shaping and bounded retries remain source-owned; no fresh-per-retry application guard is claimed. Existing conversation tracking takes priority; fallback embedding attribution is scoped to the actor/command and restored even on quota refusal or cancellation. Prepared vectors are ephemeral and have no paid fallback under the user's write lock. PostgreSQL NOWAIT probes from another transaction prove provider work holds no user lock. Before insertion, fresh authority is checked under the user lock; manual creation increments the extraction revision so an earlier prepared automatic batch cannot undo it. Lost commit acknowledgement reports unknown completion; the deterministic id supports observation, and replay starts no additional provider work.

Adversarial review covered strict inherited vocabulary, future-field omission guard, all default fields, both pin defaults, quota withdrawal between logical calls, capability withdrawal, provider-unavailable storage, lock order, scoped attribution cleanup, source revision fencing, single-use commit uncertainty, editor identity injection and private metadata. The preview fixture initially omitted defaults which production preparation explicitly expands; it was aligned with that actual path rather than weakening canonical approval validation. The editor dispatch was decomposed to preserve the complexity threshold; tuple membership preserves strict MyPy typing.

Evidence: final 26 targeted cases pass, comprising 8 PostgreSQL creation/editor cases, 2 cancellation/quota attribution units and 16 strict/six-language preview/editor contracts. These include zero paid work before confirmation, exact persisted identity, no replayed spend, post-first-call withdrawals, zero importance and disabled automatic recall. The source prerequisite's 3 HTTP/persistence cases and the preceding 11 pin execution regressions also pass. The final broad backend run has 787 passes across application/memory/embedding tracking/chokepoints/core/SLOC/coupling contracts before the two final scope units. Strict MyPy 18 owners, Ruff/Black 21 production/test files plus final 4 tests, CC292/max78 and six-language parity pass without raised thresholds. Frontend changes are progress copy only; no new browser markup, device, paid provider, production or full conversation qualification is claimed. This creation slice is closed. Memory editing/deletion and the remaining non-administrator families remain open; administrator work and excluded account-security workflows remain untouched.

## Memory operational timestamp amendment and shared edit prerequisite — cold review, 2026-10-08

An actual source increment_usage after preparation reproduced a false STALE_STATE for pin confirmation. The comparison now excludes only operational updated_at; id, creation identity, pin and the full editable configuration digest remain exact. A schema-to-digest guard refuses future UI settings omitted from that digest. The retained serialized timestamp preserves pending-command compatibility. Corrected and invalidated rows still refuse; automatic use may advance without invalidating an unchanged fact. Final PostgreSQL pin/editor and source/preview contracts: 34 passed. Strict MyPy three production owners passed; Ruff import correction applied without policy weakening.

The pure sparse memory edit preview preserves explicit zero/empty-string values and existing source null-as-omitted semantics without mutation or provider work. The UI update route delegates to one typed source mapping, preserving its existing validation and service behavior. A future-field guard covers both the complete projection and write mapping. Native edits will validate a complete constrained configuration; a legacy malformed stored configuration is refused rather than silently rewritten. No UI lock semantics, security workflow, graph state, dependency or prompt behavior is changed by this prerequisite. Cold review checked operational-vs-config conflict detection, all six source fields, identity/private exclusion and backward-compatible command serialization. This prerequisite is closed; native editing remains to implement and qualify.

## Native memory editing — cold review, 2026-10-08

The strict sparse edit inherits every source UI field and constraint. Full source configuration before/after, exact saved fact identity and unchanged pin are confirmed; editor prompts receive only id and editable deltas. Null/empty-request/private injection refuses; zero and source clear strings remain meaningful. Editing a pending proposal rereads the corrected fact, retains command identity and replaces the saved approval digest without paid work. No-op still requires HITL but writes nothing and publishes no invalidation.

Both pre-spend and user-before-memory locked checks refuse a changed, superseded or removed fact. Operational recall timestamps do not create false conflicts. Text/topic edits reuse quota-checked, accounted source vector preparation before write locks; metadata-only edits do not invoke providers. Fresh capability, actor and expiry are rechecked before commit. Manual changed edits invalidate earlier prepared extraction batches while preserving automatic recall opt-out and private columns. No paid fallback occurs under a lock. Unknown commit acknowledgement never claims completion and replay cannot repeat writes or spend.

Final evidence: 50 targeted cases pass (12 PostgreSQL update scenarios, 3 editor scenarios, creation/pin regression cases and 17 strict/localized/private contracts). Separate broad application/memory/chokepoint/SLOC/coupling suite: 786 passed. Strict MyPy 15 owners plus the two extracted rendering owners, Ruff/Black 19 files, CC292/max78 and six-language parity pass. The previous branch ladder was converted to a typed homogeneous dispatch table to prevent complexity growth. Cohesive memory previews were extracted because the global source-size guard caught 618 over its 600 cap; no cap was raised. The disabled editor fixture was corrected to assert the established AuthorizationError and CAPABILITY_DISABLED code, preserving production refusal behavior. Cold review checked all schema/draft/catalogue/editor/result/invalidation paths, lock ordering, cost scope, no-op, stale state and transaction uncertainty. No paid provider, production, new device/browser or complete Pipeline/ReAct conversation qualification is claimed. This native editing slice is closed; memory deletion/bulk/export/provenance and other non-administrator families remain open.

## Native individual memory erasure — cold review, 2026-10-08

The delete_lia_memory_tool selects only an active owned id, then freezes the source fact, category, pin and configuration digest. Exact HITL is mandatory even for a pinned procedural instruction; explicit erasure follows the source manual deletion semantics. A missing, foreign or already superseded selection yields the same NOT_FOUND response without a proposal or identity leak. A correction/supersession after preparation refuses STALE_STATE; automatic usage alone does not invalidate an unchanged fact. Preview, editor and public completion exclude private comparison data; completion returns only the deleted identity rather than repeating the erased content.

The command acquires user-before-memory locks, rechecks current capability/account/deadline around the source deletion, and increments the durable extraction revision in the same transaction. Tests with automatic recall enabled show that the old extraction revision can no longer authorize a write, without changing the recall preference. The source hard deletion and its foreign-key cleanup are reused; a separate survivor remains. No embedding or LLM call is needed. Late withdrawal/expiry rolls back; lost commit acknowledgement reports unknown completion and single-use replay refuses.

All four memory proposal editors now share a cohesive typed owner and preserve the original draft-editing database seam, current-source reread, retained identity and replacement approval digest. This extraction was required by the source-size guard (612 over the 600 cap), and no cap was raised. Missing/foreign/invalidated fixture assertions were aligned to UnifiedToolOutput.error_code rather than treating its text error as an object; actual refusal behavior was preserved.

Evidence: final 46 targeted cases pass, including 12 PostgreSQL deletion/ownership cases, 6 shared update/delete editor cases, prior pin/create editor and update regressions, and 11 strict/six-language/private erasure contracts. Broad application/memory/SLOC/coupling suite: 778 passed. Strict MyPy 16 owners plus the two shared-editor owners, Ruff/Black 19 files, unchanged CC292/max78 and six-language parity pass. Cold review checked source ownership, pin override, user-row order, revision fence, canonical deletion preview, provider abstention, rollback/unknown truth and editor injection. No production, paid-provider, new browser/device or full Pipeline/ReAct conversation qualification is claimed. This individual-erasure slice is closed; bulk erasure, export/provenance and the other non-administrator families remain open.

## Native global memory erasure — cold review, 2026-10-08

The global erasure tool uses the source preserve_pinned option and includes superseded historical rows, as the existing GDPR route does. Confirmation carries exact selected/preserved/category/pin/procedural/history counts and a private comparison digest, without saved facts, vectors, biometrics or a growing list of identities. Source rows are streamed in stable UUID order with bounded batches and private columns deferred; operational usage timestamps do not change the target identity. Both preservation directions and an empty no-op still require exact HITL. Unpinned procedural instructions are eligible for explicit erasure; preserving pinned rows is never silently extended into another policy.

Execution holds the source user lock before stable memory row locks, compares the complete confirmed scope, delegates to the existing source delete_all_for_user, verifies the actual removed count, and fences earlier extraction batches. New facts, corrections and changed pins before execution refuse; late capability/deadline withdrawal and a wrong removed count roll back. Unknown commit acknowledgement does not claim completion. No model or embedding call is needed, and automatic recall remains unchanged. The compact preview/editor/result participates in every native registry and addressed frontend memory invalidation.

A concurrency probe initially reused the SAVEPOINT fixture's same underlying connection, so it could not prove independent transactions. It was replaced by committed disposable actors and AsyncEngine-backed sessions on distinct PostgreSQL backend PIDs. A positive control first proves NOWAIT refusal with SQLSTATE55P03 while the parent holds the lock. The actual bulk probe then observes the parent's PID in pg_blocking_pids for a concurrent FK insertion. That insertion waits until erasure commits, then succeeds and survives. Two additional real-connection tests prove approved creation/edit embedding preparation holds no user lock. These supersede the earlier shared-connection NOWAIT claims in the creation/edit reviews; those previous probes alone were insufficient evidence. Source behavior was already correct, and no permission/locking policy was weakened.

Evidence: final 35 targeted cases pass: 12 PostgreSQL global scenarios, 3 independent-transaction controls/probes, 9 update/delete/global editor cases and 11 strict/localized/bounded-preview units. Each populated global scenario uses 205 owned rows, including history and pins, plus foreign data. Separate broad application/memory/SLOC/coupling run: 789 passed. Strict MyPy 18 owners, Ruff/Black 21 files, unchanged CC292/max78 and six-language parity pass. Cold review checked streaming lifetime/cancellation, full scope identity, all source setting digest coverage, lock order, phantom insertion, no paid work, no-op, exact count, replay and transaction uncertainty. No production, paid-provider, physical-device, new browser or full Pipeline/ReAct conversation qualification is claimed. This global-erasure slice is closed; memory export/provenance and other non-administrator families remain open.

## Shared provenance source ownership prerequisite — cold review, 2026-10-08

Three actual PostgreSQL RED cases reproduced foreign-message disclosure from a malformed legacy reference: a foreign conversation, a message belonging to another conversation, and a soft-deleted conversation. The shared resolver now joins only a currently owned, non-deleted conversation and only a message belonging to that resolved conversation. A foreign/deleted conversation becomes dated, sourceless and textless; a mismatched message supplies no excerpt. The reference's ownership predicate, stable ordering, live excerpt bound, capture dates and existing physical-deletion tombstones remain. One indexed query still resolves the trail, without N+1 reads or copying sources. Existing declared WHOLE_RECORD message scope remains unchanged; it cannot bypass source ownership or a deleted conversation.

Final source/provenance database/route/isolation suite: 20 passed. Size/coupling guards: 12 passed. Strict MyPy, Ruff/Black and CC292/max78 pass. Cold review covered both reference and live-source ownership, message membership, soft/physical deletion, nullable joins, retained dates, source excerpt bounds and effects on journal/interest readers sharing the resolver. No new writer, dependency, model call, native tool or UI is introduced by this prerequisite. It is closed; native memory provenance reading remains next.

## Native memory provenance read — cold review, 2026-10-08

The explicit read selects one owned identity and reuses the UI's MemoryRepository ownership lookup, shared live provenance resolver and ProvenanceResponse. Owned superseded facts remain readable as in the UI. The source prerequisite prevents foreign/deleted conversation text and foreign conversation links, and mismatched messages supply no quote. Current account and global capability are checked before and after the read, including withdrawal during resolution. Automatic recall disabled remains compatible with explicit management reading; no memory, preference or usage counter changes. The catalogue distinguishes observed provenance from proof of truth, publishes the retained-trail bound and treats excerpts as untrusted data. No model/embedding call or command state is introduced.

Strict identity selection refuses actor/source/quote/limit injection; runtime/store stays injected and absent from the model schema. Malformed selection is INVALID_INPUT; malformed stored response is INVALID_RESPONSE_FORMAT. The latter distinction had a behavioral RED after repairing the test's missing required runtime store, then became GREEN with split validation boundaries. Finite errors never expose source content. Operation/name/manifest/catalogue registration and six-language progress copy are complete.

Evidence: final 26 targeted cases pass: 7 PostgreSQL native/UI-parity cases, 13 shared-source database cases and 6 strict/private/error-boundary units. Broad application/memory/SLOC/coupling suite: 795 passed. Strict MyPy seven owners, Ruff/Black nine files, CC292/max78 and six-language parity pass. Cold review checked own/historical selection, current source membership, soft/physical deletion, quotes-as-data, role/capability withdrawal, error granularity, unchanged opt-out/usage and source reuse. No new browser UI, paid provider, production or full Pipeline/ReAct conversation qualification is claimed. This provenance slice is closed. The memory-specific browser export is grouped with the planned device/download bridge qualification; it remains open and the whole non-administrator lot is not complete.

## Shared interest management projection — cold review, 2026-10-08

The existing InterestResponse declared subject but the UI converter never populated it. A source-field completeness guard reproduced the omission, then became green when the converter was extracted into a shared source read owner with the explicit subject value. UI routes retain their existing helper names through imported aliases, preserving callers and fixtures. Weight still delegates to InterestRepository.calculate_effective_weight with the source setting; an optional shared observation clock supports consistent future pages without duplicating Bayesian/decay rules. Interest settings use their source DTO's attribute projection, so future declared settings are not silently omitted.

The interest/SLOC/coupling suite has 296 passes, strict MyPy both owners and Ruff/Black pass. No new provider/model invocation, preference write, paid computation, UI markup or business-setting rule is introduced. Cold review covered complete DTO fields, zero signal counts, subject/private-vector boundaries, source weight defaults and alias compatibility. This prerequisite is closed; native complete-count interest reading and actions remain open.

## Native interest management read — cold review, 2026-10-08

One SQL snapshot returns complete owned category/status counts, matching-filter totals and a bounded stable created-at/UUID page. It defers private embeddings and refreshes ORM state. Explicit management reading works with automatic interests disabled and performs no discovery, feedback, preference, usage or provider writes. Source projection and weight policy are shared with the UI; one observation clock is returned with the user's notification timezone. Foreign/missing anchors refuse, empty/end pages retain truthful counts, and token-budget projection continues after the last actually shown item.

Current capability/account checks bracket the read; late withdrawal refuses and late preference changes are freshly projected. The closed request schema refuses actor injection, ambiguous selection and coerced limits. Catalogue, operation, native identity and six-language progress declarations are registered. Adversarial review checked ownership in every aggregate/page/anchor, single-statement consistency, stable ties, cancellation-free bounded materialization, source weighting, private-field exclusion and continuation after truncation. Final targeted suite: 24 passed, including 14 PostgreSQL scenarios. Broad application/interest/size/coupling suite: 958 passed. Strict MyPy seven owners, Ruff, unchanged CC292/max78 and six-language parity pass. A broad run initially used an incorrect size-test path and was rerun successfully with the verified path. No production, paid provider or new browser/whole-conversation qualification is claimed. This read slice is closed; interest actions and the remaining non-administrator families are open.

## Native interest notification settings — cold review, 2026-10-08

All five source settings are inherited with the API's limits, strict values, nonempty sparse intent and explicit-null refusal. Future source additions enter the inherited schema but fail the reviewed field/invalidation/label guard until classified. Source UI and native execution share a fresh user-row write, exact field comparison, verified no-op and commit receipt. UI optional null now means omitted rather than attempting a write into non-null columns. Overnight windows remain supported; no new cross-field business rule was invented. Saving delivery preferences does not promise a scheduler delivery.

Every native action is durable, exact HITL. Preparation writes no preference and invokes no provider. The source write checks current capability/account/deadline under the user lock before changes and after flush. Late withdrawal rolls back, unrelated font edits survive, selected-field edits refuse, no-op emits no invalidation, and lost commit acknowledgement returns unknown completion without automatic replay. A cold-review timezone scenario first failed: changing the account timezone silently changed a confirmed hour's meaning. Execution now compares the stored, approval-bound timezone for hour changes and the card shows that timezone. Edits reread source state, retain command identity and replace the approval digest; identity/unreviewed-field injection is refused.

Interest UI queries now use the existing account-lifetime/resource synchronization owners for both list and settings. All seven existing mutation callbacks refuse retired account lifetimes before sending and after awaiting a result. Confirmed changes reread both resources, preserve loaded data and the active category filter, and do not accept foreign-account hints. No new markup or device permission workflow is introduced. The home-location tail of the generic preference dispatcher was extracted into a closed typed helper after the complexity guard detected CC15; no cap was raised.

Evidence: final combined interest reading/settings suite has 61 passes, including 33 PostgreSQL scenarios. Settings-only coverage includes 13 confirmation/failure/clock cases, three editor/injection cases and three source-UI sparse/fresh cases. Two real frontend hook suites have 10 passes. Broad application/interest/size/coupling suite: 976 passed. Strict MyPy 16 owners plus three final correction owners, Ruff/Black, CC292/max78, six-language parity and the official full frontend gate (a11y0, hooks31, CC42/max50, non-incremental TypeScript) pass. No independent-transaction concurrency, new browser, paid provider, production or full Pipeline/ReAct conversation evidence is claimed by this settings slice. It is closed; interest CRUD/feedback/history/provenance and other non-administrator families remain open.

## Native manual interest creation — cold review, 2026-10-08

The native request inherits both source creation fields and their limits, with strict values and finite category parsing. Source defaults are expanded before approval. A server-minted stable identity is retained through edits and used by the repository; the existing UI now shares the same typed field mapping. Source initial signals/status and best-effort embedding behavior are preserved. Field/schema/mapping guards refuse silent omission of future API fields. Topics are data in the shared confirmation serializer; the editor receives configuration only, never a minted identity or private embedding.

No interest write or provider call happens before exact HITL. Execution checks duplicates before spending, scopes source embedding attribution to the acting account and command, asks both usage ceilings, restores the previous context on success/cancellation/refusal, then locks the current user and checks the topic again. Fresh capability/account/deadline fences bracket the source write; quota, expired approval, late disable and duplicate refuse. Commit uncertainty returns unknown completion, and single-use replay does not buy another embedding or write. One distinct-connection PostgreSQL probe first demonstrates NOWAIT failure with SQLSTATE55P03 under a real parent lock, then proves successful NOWAIT from a different backend PID during actual approved embedding preparation.

Adversarial review covered generated identity, same-category source uniqueness, source defaults, null-vector storage, paid-before-lock ordering, quota ownership, cancellation, rollback/unknown truth, editor injection, private fields, complete localized preview and addressed invalidation. The shared editor's routine projections were extracted cohesively when adding the interest branch reached CC15; no cap was raised. Final targeted suite: 34 passed, including 12 PostgreSQL scenarios (seven confirmation/degraded cases, three editor cases, source UI creation and one real independent-connection probe). Broad application/interest/accounting/size/coupling suite: 1034 passed. Strict MyPy24, Ruff/Black26, CC292/max78 and six-language parity pass. The existing frontend account-scoped interest invalidation is reused; no new markup, paid-provider, browser, production or full conversation qualification is claimed.

Source clarification: user.interests_enabled governs proactive notifications; automatic learning is governed by the platform interests capability and currently has no per-account interest-learning consent column. It must not be substituted into the extraction-consent map. The existing automatic action applier has no durable revision fence and performs source embeddings inside its write batch. Before destructive/editing native interest operations, the remaining integration must prevent an older extraction batch from undoing confirmed management and keep paid preparation outside its write locks. Manual creation's native path is closed; that cross-writer prerequisite and the remaining interest/non-administrator operations are open.

## Native interest explanation and provenance — cold review, 2026-10-08

One owned identity returns the UI's explanation coefficients/signals/status/dates and bounded live provenance. A shared pure explanation builder delegates to the real repository weight policies at one observation clock; UI routes use it too. The source selector scopes the SQL by owner and identity, refreshes ORM facts and defers private embeddings. Provenance reuses the previously hardened shared resolver, preserving dated textless tombstones for deleted sources. Current account/global capability checks bracket the complete read; explicit management does not alter signals or notification preferences, discover topics, call a model or buy embeddings. Quotes remain untrusted observations and neither weights nor references are presented as proof of truth or lifetime completeness.

The request refuses actor/source/quote/vector injection; source corruption is INVALID_RESPONSE_FORMAT rather than a bad-user-input error. Native identity, operation, manifest/binding and six-language progress are complete. Existing source arithmetic fixtures mocked the old repository.get_by_id seam; they were adapted to the ownership-filtered scalar query with assertions on both bound identities, retaining real arithmetic. PostgreSQL verifies foreign/unknown refusal through both the UI and native path. Final targeted suite: 27 passed, including six PostgreSQL cases plus source explanation/weight regressions and six closed-contract units. Broad application/interest/size/coupling suite: 1004 passed. Strict MyPy10, Ruff/Black, CC292/max78 and six-language parity pass. Review checked owner predicates, stale identity maps, source clocks/formula, provenance deletion/privacy, finite errors, no writes/spend and source reuse. No new markup/browser, production or full conversation qualification is claimed. This details-read slice is closed; history and remaining interest/non-administrator operations are open.

## Interest history source ownership prerequisite — cold review, 2026-10-08

A real PostgreSQL RED reproduced disclosure of a foreign interest topic through an owned notification's malformed legacy relationship, including a relationship already present in the ORM identity map. History now eager-loads only an interest owned by the same account, refreshes loaded facts, selects only the topic/identity on that relationship and defers the notification's private content embedding. The actually delivered owned message remains readable; missing/foreign targets produce a null topic, and foreign notifications remain excluded. Created-at ties now have a stable UUID tiebreaker. No write, API response-field change, provider call or N+1 loader is added.

Final 24 source/route/size/coupling cases pass, including four PostgreSQL foreign/own/absent/fresh scenarios and eight existing route contracts. Strict MyPy, Ruff/Black and CC292/max78 pass. Cold review checked owner predicates in both parent and relationship loading, preloaded foreign ORM state, null relationships, current content, narrow column loading and stable ordering. The source UI count and page remain separate reads; no single-snapshot claim is made for that legacy route. This prerequisite is closed; native single-snapshot history reading is next.

## Native interest notification history — cold review, 2026-10-08

The explicit audit reader returns the source delivered-message/date/provider/feedback/topic fields, complete owned totals and a bounded stable created-at/UUID page. Count, page and owner-filtered topic join share one SQL snapshot; the UI and native query share the source count statement. No embedding, hash, run identifier or private interest field is selected for the model. Missing historical content and absent/foreign topics remain null. Foreign/missing cursors refuse; empty and final pages retain the full count. The token projection continues after the last actually shown notification.

Current capability/account checks bracket the query, including late withdrawal. No notification, feedback, preference, discovery or provider write occurs. Future source history fields are covered by a projection guard; request coercion, actor injection and offset/cursor mixing refuse. Operation, native name, manifest/binding, budget cursor metadata and six-language progress are complete. Review inspected every owner predicate, nullable join, tuple anchor, bounded result, source-count reuse, private-column selection, stable ties, finite errors and untrusted text boundary.

Final targeted suite: 30 passed, including ten native PostgreSQL page/privacy/late-rights cases, four source ownership/freshness cases, eight route regressions and eight strict/projection/cursor units. Broad application/interest/size/coupling suite: 1012 passed. Strict MyPy12, Ruff/Black, CC292/max78 and six-language parity pass. No new markup/browser, paid provider, production or full conversation evidence is claimed. This audit read is closed; cross-writer fencing and interest editing/deletion/feedback/reactivation/export, plus the other non-administrator families, remain open.

## Automatic interest writer revision prerequisite — cold review, 2026-10-08

PostgreSQL RED reproduced writes from an old run, a run superseded during its model call and an inactive account. The automatic writer now captures the frozen run's actor/revision before analysis, prepares distinct topic embeddings outside write transactions, and compares the current active account revision under the user lock before the entire storage batch. Late learning-capability withdrawal rolls back the batch. Paid analysis remains accounted even when its data is refused. Notification enablement is deliberately not learning consent: the source has no such account field. Shared manual creation now advances the same revision in its own locked transaction.

Preparation delegates to the real best-effort embedding helper, enforces both usage ceilings, attributes actor/session/conversation/run and restores the previous context on success, quota refusal and cancellation. Deduplication and insert reuse one prepared result. A missing prepared topic cannot fall back to a paid provider under a lock. Fresh candidate loads retain all statuses, the existing blocked/dormant policy and deletion cap. Independent PostgreSQL connections are reserved explicitly, backend PIDs differ and a positive NOWAIT/55P03 control precedes the proof that manual creation during embedding survives while the automatic batch refuses.

Review checked lock order, active-account/current-revision predicates, withdrawal rollback, no provider calls under storage locks, accounting on refused output, cancellation, cache replay, blocked deduplication, unknown identities and preserved source policy. The source batch still has its prior per-action exception behavior; a database-aborted transaction cannot commit and the public background path returns zero rather than claim stored rows. No new learning consent, admin tool or database migration was introduced. Twenty-three PostgreSQL scenarios and 318 source/usage/size/coupling units pass; strict MyPy6, Ruff/Black and CC292/max78 pass. Source orchestration/storage were separated when the existing frozen-size guard redded, with no raised cap. This prerequisite is closed; native interest edit/delete/feedback/reactivate/export remain open.

## Native interest editing — cold review, 2026-10-08

One owned source identity accepts a strictly typed sparse delta for every source UI edit field: topic, category and positive/negative signals. Inherited source constraints refuse null, bool/string coercion and private/actor/comparison injection; zero negative signals remains valid. A complete source configuration plus status/derived subject is assembled before confirmation and compared before spending and again under account-then-interest locks. Independent last-notified activity does not make the proposed configuration stale. A competing signal/status change or a target deleted during embedding refuses explicitly as stale; actor/capability/expiry fences are reused at each execution boundary.

Shared source preview and manual-write owners now serve UI and native edits. The UI's optional null means omitted; no-op leaves signals, vectors, subject and extraction revision unchanged. A renamed topic resets the derived subject and replaces its old-topic vector, including clearing that vector when best-effort regeneration fails. The confirmation shows source values and subject before/after. A real PostgreSQL regression proves this fix; a distinct-PID/NOWAIT control proves actual approved preparation holds no user write lock. Actual changes advance the durable extraction revision inside the locked transaction; provider preparation retains existing quota/accounting/cancellation owners.

The durable native flow proves no provider/write before exact HITL and no repeated effect on replay. Draft editing rereads source facts, retains the command identity, changes the sealed payload and refuses actor/comparison injection without spending or writing. Operation, native name, manifest/binding, result projection, addressed frontend resource invalidation and six-language progress/preview copy are complete. A source-field mapping guard forces future UI edit fields into both shared preview and write mappings.

Final evidence: 18 PostgreSQL cases (exact edits, no-op, signals-only preservation, UI null/rename paths, stale facts, quota, late disable, disappeared target, unknown commit, exact-HITL/replay, three editor cases and two independent creation/edit lock probes); 1037 broad application/interest/size/coupling units; strict MyPy12 plus two adjusted owners, Ruff/Black, CC292/max78 and six-language parity pass. Review inspected ownership SQL, fresh identity maps, lock order, source uniqueness, vector/subject invalidation, sparse/full schema boundaries, sealed authority, error truth, untrusted text and no-op accounting. No source cap was raised. No new markup/browser, paid provider, production or full conversation evidence is claimed. This edit slice is closed; deletion/feedback/reactivation/export and the other non-administrator families remain open.

## Native interest individual deletion — cold review, 2026-10-08

An owned active/blocked/dormant interest is shown as a complete source fact before exact HITL, then rechecked under account-then-interest locks before the shared UI/native hard deletion. Actual deletion advances the extraction revision in the same transaction. Foreign ownership, competing signal changes and late native-capability withdrawal refuse; commit uncertainty remains unknown and the durable command cannot be replayed. No provider, vector preparation or usage write occurs. Operation/native/manifest/binding, sealed editing, result projection, resource invalidation and six-language preview/progress are complete.

Two source/UX defects were reproduced and fixed during review. ORM delete-orphan cascaded delivered notifications despite their existing SET NULL FK and documented nullable-interest policy; it could also delete a malformed legacy link belonging to another account. Passive database deletion now preserves both histories and tombstones only the reference, without loading the whole relationship. PostgreSQL proves owned and foreign bodies survive and the owned history excludes foreign rows. The history hook now uses the existing account-scoped query and resource-sync owners, so a confirmed change refreshes its topic, an account switch hides retired data/callbacks, and a closed panel performs no background fetch. Two frontend REDs reproduced stale history/account data; 18 hook/render regressions pass after repair.

The existing manual feedback writer now acquires the account lock before its interest lock and dependent presence FK write, uses the current actor preferences and invalidates old extraction runs. A distinct PostgreSQL observer with positive NOWAIT/55P03 control verifies the parent lock at that boundary; the original source path failed this proof. Existing feedback/audit/card behavior remains covered. Its error path retains the immutable owner before rollback so expired ORM identity cannot mask the source error.

Compatibility correction to the editing slice: an automatically learned one-character topic can exist under the source read/storage contract. Validating that existing fact as a new edit prevented UI rename, signals-only edits and deletion proposals (three actual PostgreSQL REDs). Complete observed configurations now use source read semantics; strict inherited constraints still apply to every proposed sparse delta. A startup field-coverage guard and source annotation/mapping tests force future source edit fields into the shared fact and write mappings. The confirmation remains complete and frozen; schema changes invalidate older in-flight drafts rather than silently reinterpreting them.

Final combined management evidence: 29 PostgreSQL cases including legacy facts, edits/deletions, UI retention/foreign references, actual HITL/replay, editors and independent feedback locking; 1048 broad application/interest/size/coupling units; strict MyPy9 on the adjusted fact/source owners plus the previously checked native surfaces; Ruff/Black; CC292/max78; six-language parity; official frontend lint/a11y/hooks/CC/nonincremental tsc; 18 frontend hook/render regressions. Review inspected source retention intent against both ORM and physical FK behavior, current ownership/identity maps, lock order, CAS, late rollback, legacy constraints, dependency failures and addressed UX refresh. No cap was raised. No paid provider, production, new browser/mobile markup or full conversation evidence is claimed. This individual deletion slice is closed; global deletion, feedback/reactivation/export and the remaining non-administrator families are open.

## Native interest global deletion — cold review, 2026-10-08

The explicit all-owned scope streams every status in stable identity order with bounded allocations, deferring private vectors. Confirmation exposes complete category/status counts and retention consequences; the comparison digest remains private and no topic list is sent to the model. Execution locks the current account and selected rows, compares every approved source configuration, delegates to the UI's shared deletion owner, checks the actual deleted count and advances extraction revision in the same transaction. Changed membership or configuration refuses; operational notification dates do not invalidate the configuration. Empty scope is a verified no-op, late capability withdrawal rolls back, and commit uncertainty does not allow replay.

Review covered completeness beyond the UI page cap, owner predicates, stable lock order, legacy categories/statuses represented only as bounded unknown counts, retained notification bodies, cancellation cleanup of streamed results, exact scope/schema/editor guards and resource invalidation. An independent PostgreSQL probe with distinct backend PIDs and positive NOWAIT control proves an incoming foreign-key insert waits on the account lock; after the approved deletion commits, the genuinely later new interest survives. The UI uses the shared owner even when native tools are disabled.

Final evidence: 13 PostgreSQL cases including a 603-interest scope, concurrent insertion, stale configuration, late disable, empty scope, unknown commit and the actual durable HITL/replay flow; 1065 broad application/interest/size/coupling units; strict MyPy13; Ruff/Black; unchanged CC292/max78; six-language parity. No cap was raised. No paid provider, production, new browser/mobile markup or full Pipeline/ReAct conversation qualification is claimed. This global deletion slice is closed; feedback/reactivation/export and the other non-administrator families remain open.

## Interest feedback audit target prerequisite — cold review, 2026-10-08

A real PostgreSQL RED through the existing UI handler showed that an owned run identifier from another owned interest attributed a verdict to the wrong notification. The audit writer now requires the selected interest identity in addition to account and run identity; the UI supplies its actual selected identity. Missing, deleted, foreign or mismatched links update no audit row. The existing interest-level feedback and archived-card scope remain unchanged; the source path still never guesses an audit notification. The same test verifies the valid target still records its verdict and timestamp.

Review inspected the complete call graph, required rather than optional target scope, all three SQL predicates, nullable historical links, source card behavior and unchanged lock order. Fourteen PostgreSQL source/HITL/deletion regressions, 299 interest/size/coupling units, strict MyPy on both source owners, Ruff/Black and unchanged CC292/max78 pass. No cap was raised, no provider or new UI workflow is introduced. This source prerequisite is closed; the native feedback action itself remains open.

## Native interest feedback — cold review, 2026-10-08

Exactly one owned interest or notification identity selects the source verdict. Notification selection resolves its owned, live interest and private run linkage internally; null or foreign legacy relationships refuse. The shared source policy adds the existing positive/negative signal increments or blocks the interest, with complete before/after configuration/status/subject, notification identity and expiry shown before mandatory confirmation. Current source facts and notification feedback are compared again under account -> interest -> notification locks. Sparse editor authority contains identities/verdict only, retains the command identity and replaces its sealed payload; comparison, actor and private-run injection refuse. Metrics follow confirmed commits, commit uncertainty remains unknown and replay cannot repeat an effect. No model/embedding/provider call is introduced by feedback itself.

Ruling: retain both existing UI scopes explicitly. A notification verdict updates its exact audit and matching archived card; an interest-level verdict marks all associated archived cards answered without guessing an audit notification. The confirmation and catalogue state that breadth. PostgreSQL proves two notifications/cards remain independent under notification scope, then both cards follow the entity scope while audit verdicts remain attributable. Shared source effects preserve habits-gated human presence and extraction revision invalidation; late native disable after effects rolls back durable signals and revision.

Cold review found that the delivered-notification writer used a different lock order. A real PostgreSQL RED with positive NOWAIT control demonstrated its missing parent lock at audit insertion. Paid embedding preparation now precedes all management locks; distinct backend PIDs and NOWAIT/55P03 prove account-first insertion. A delivered owned body keeps a null target after deletion or a malformed foreign target, without updating the foreign interest. The protocol feedback writer also checks current actor/target ownership and advances extraction revision. Notification identity tests were adapted to the current owned selector while retaining their identity/content assertions.

Two frontend REDs demonstrated missing native-change refresh and publication of an old account's in-flight page to a new account. The existing conversation-sync controller now subscribes to owned interest changes, retires in-flight reads on account changes and reuses its coalesced authenticated newest-page merge. Streaming, selected text, menus, pagination and historical-view deferral retain their existing rules; this adds no per-card request or new markup. Newest-page metadata changes include the feedback state; older historical pages follow the existing deferred sync policy. Moving identity resolution into the wrapper preserves the chat page's frozen complexity cap.

Final evidence: 26 combined PostgreSQL cases plus four delivery/protocol probes (one overlapping case), 1078 broad application/interest/size/coupling units, strict MyPy13 plus three final adjusted owners, 55 real frontend hook/controller/merge cases, the official frontend lint/a11y/hooks/CC/nonincremental TypeScript gate, Ruff/Black and six-language parity pass. Backend CC decreased to 291 qualifying functions/max78; the canonical shrink-only ratchet records that gain. No cap was raised. Review covered all owner predicates, source scopes, stale/absent targets, lock order, legacy links, exact HITL, edit sealing, rollback/unknown truth, source field coverage, untrusted text, paid-work separation and account-scoped UI refresh. No paid provider, production, physical-device, new browser or full Pipeline/ReAct conversation qualification is claimed. This feedback slice is closed; reactivation/export and the other non-administrator families remain open.

## Native interest reactivation and cold-start correction — cold review, 2026-10-08

One owned dormant identity prepares a complete source reset after mandatory confirmation. Active/blocked rows refuse. Source initial signal constants, active status, cleared notification/dormancy dates and last-mentioned refreshed at actual execution time reuse the UI repository policy; topic/category/subject/vector stay intact. Complete affected facts are compared under account-then-interest locks. Competing signals or delivery dates, a disappeared target and foreign ownership refuse; late native disable after flush rolls back the reset/revision, and lost commit acknowledgement remains unknown. UI and native paths now share the fresh owned write and extraction revision fence. Immutable owner identity survives rollback in the route's error path.

Ruling: the execution clock is not the preparation clock. Confirmation states that last-mentioned will be refreshed at execution, rather than displaying an invented future timestamp. One canonical projection check serves rendering and execution; six initial preview REDs caught the shared renderer's assumption that after always equals the full intent. The result reports the refresh, without pretending to know the stored timestamp before execution. A source-assignment coverage guard forces every future reset field into the complete confirmation. Editors accept identity only and reprepare fresh facts with the same single-use command.

Cold-start correction to prior memory/interest slices: direct imports in the unit process had masked missing modules in the real startup list. A fresh interpreter RED found the memory and interest native identities absent, including the new lifecycle action. The source startup list now imports all three modules. A bounded fresh-process guard compares every declared native identity with the actually loaded registry; the complete catalogue parity guard also passes. This is current startup evidence, stronger than the earlier in-process registration claims. No production deployment is implied.

Final evidence: 26 combined cases (24 PostgreSQL, two route-guard units) covering reset/stale/withdrawal/foreign/disappeared/unknown truth, five real durable HITL/replay flows and nine source-refresh/editor cases; 1092 broad application/interest/cold-start/catalogue/size/coupling units; strict MyPy12 plus three canonical-projection owners; Ruff/Black; six-language parity; unchanged backend CC291/max78. Existing owned interest/history and deferred conversation resource synchronization are reused, with no new markup or per-card HTTP request. Review checked complete reset semantics, clock truth, source ownership/identity maps, lock order, withdrawal rollback, extraction revision, no paid work, sealed editing, honest public results and actual cold reachability. No cap was raised. No paid provider, production, physical-device, new browser or full Pipeline/ReAct conversation qualification is claimed. This reactivation slice is closed; interest exports, device-bound downloads and the other non-administrator families remain open.
# Export prerequisites — complete interests and spreadsheet-safe CSV

Cold review found that the UI export used the display-list ceiling. A real PostgreSQL regression beyond that ceiling failed before correction. The export now uses the existing complete owned cursor, excludes private vectors and projects the same ten public fields through one typed source owner and one observation clock. All statuses and the foreign-account exclusion are exercised. CSV text beginning with spreadsheet formula markers or leading control characters is escaped; numeric negative values remain unchanged. JSON retains the original text.

Validation: the new completeness regression and seven CSV security cases failed before correction; all 23 export cases and 318 source/CSV/file-size cases pass afterward. MyPy passes the three changed source owners; complexity stays within the existing shrink-only baseline. No provider calls or production data. The native download will spool its output to avoid accumulating a full export in the model or a transfer buffer.

## Native interest export — closed after inline cold review

`export_lia_interests_tool` is reachable in the real cold-start catalogue. CSV/JSON format is the only model-controlled input. The complete owned scope, count and source observation time are sealed behind a private comparison; no topic list, vector, local path or session material enters its preview/editor. Natural weight decay uses the displayed observation clock. A changed/new/deleted interest needs fresh approval. All saved statuses are included beyond displayed pages; this does not enable notifications or mutate learning.

The existing exact durable HITL and original-session continuation now serve a bounded temporary attachment. Claim and settlement remain single-use; a requested download never attests that a file was saved. The shared account-export size ceiling bounds output, with a small spool and finite chunks. Source cursor and disk-operation ownership are explicit. Cold-review REDs caught immediate file closure during a cancelled real disk write and an unclosed source iterator on size failure; both are fixed and tested. The UI interest export now uses the same bounded file/projection instead of collecting the entire collection in a response list. Its JSON envelope and ten public item fields remain compatible; JSON also carries an attachment header.

Evidence: 28 real PostgreSQL cases for native exports/editing and existing archive-download regressions, plus the final 24 cases after bounded UI export integration; complete scope includes 603 rows, foreign data stays excluded, before-approval/other-session/changed/new/deleted/late-withdrawal/oversize/cut-transfer/replay/editor-injection scenarios pass. The broader unit sweep passed 1137 cases before the final count-envelope refinement; its new bounded-envelope regression and touched flows pass afterward. Strict MyPy, Ruff/Black, backend complexity 291/max78 and six-language parity pass. The official frontend gate passes all ratchets and a non-incremental typecheck; English/French accessible-name tests pass.

A current production bundle built inside Docker qualifies six hermetic Chromium journeys: account and interest exports, each desktop, 320px and failed transfer. Keyboard activation, HTTP-only cookie transport, no pre-approval download, exactly one request, correct attachment filename, reload persistence, zero scoped axe violations and no horizontal overflow pass. The runner also passes its transport guard and E2E typecheck. No external API, paid provider, production migration, physical device, Firefox/WebKit or full Pipeline/ReAct conversation qualification is claimed. Other non-administrator families, including the memory-specific export, remain open; the administrative lot has not started.


## Native memory export — closed after inline cold review

The memory UI and `export_lia_memories_tool` reuse the same complete current-memory projection and bounded transient file. The old UI export ceiling was reproduced on a real PostgreSQL collection beyond that ceiling, then removed through the source cursor. Superseded historical rows stay excluded, matching the management active set. CSV keeps its twelve source columns; JSON keeps the existing display fields and observation-time retention classification. Importance zero, pinning and usage values are preserved. Private vectors are deferred and stored biometric context is never projected; JSON retains the source null field. No retrieval counter, learning preference, provider or embedding call is introduced.

Both native exports now share a finite typed source table, their source account lock, exact original-session continuation and file ownership. Format alone is editable. A source edit, invalidation, new row or schema/column change invalidates its private comparison. A real empty-collection RED proved that adding a column could reuse an old approval; the digest now binds the export format and projection contract even without rows. Future display-schema growth is also guarded in CI. No arbitrary collection, account, path, URL or client proof is accepted.

Evidence: 139 source-memory/file cases, 47 combined source/confirmation/editor/six-language contract cases, 1276 broad application/source/cold-start/size/coupling units, then 20 real PostgreSQL cases after the projection-contract correction and 28 focused final guards. Strict MyPy of the eight changed source owners and the final three contract owners passes; Ruff/Black, backend CC291/max78 and six-language parity pass. The official frontend gate passes its ratchets and non-incremental typecheck; the current-memory card's accessible name and management link pass.

A fresh Docker production bundle qualifies nine hermetic Chromium journeys: account, interest and memory downloads, each desktop, 320px and failed transfer. Exact prior confirmation, original browser cookie, keyboard activation, one request, filename, reload persistence, scoped axe and horizontal reflow pass; E2E typecheck and transport tests pass. The two temporary proof servers were stopped after verifying their recorded PID, process and isolated port. Development services remain running. No production, paid-provider, physical-device, Firefox/WebKit or complete Pipeline/ReAct conversation qualification is claimed. This export slice is closed; other non-administrator personal-management families remain open, and no administrative lot has started.

## Native commitments — closed after inline cold review

The commitment reader reuses the source public response fields and reads a bounded stable page plus the complete filtered owned total in one data statement. A foreign/deleted cursor refuses without exposing its conversation reference. Both the native switch and source capability, including the active actor, are checked before and after the read. Status filters and tied creation times are exercised beyond the old display ceiling.

The two native actions correct wording/advisory deadlines and close as done or dismissed through the existing conditional source transitions. Complete affected identity, meaning and lifecycle are sealed in the exact mandatory confirmation. Notification counters and their incidental update clock do not invalidate meaning; a source edit, closed/expired record or ownership change does. Explicit timezones, normalized source wording, cleared deadlines, no-op truth, expiry, withdrawn permissions, rollback and unknown commit acknowledgements are covered. Native closure metrics emit only after successful commit. No promise is fulfilled, reminder created, follow-up sent, provider called or source conversation reference exposed. Relancer remains the existing chat-prefill affordance for the later device bridge.

Actual raw Pipeline coroutine payloads exposed a missing dictionary-validation path; the RED now passes with server-selected input models. The real durable effects ledger returns its recorded result on a repeated identical confirmation without executing the source transition again; the regression asserts that behavior directly. Edited proposals replace the old comparison and require the new exact approval. Public before/after previews and authority-free editors are tested in all six languages. Future source correction fields, closure actions and public snapshot fields fail explicit coverage guards until reviewed.

The existing management hook now scopes data and optimistic overrides to the authenticated account lifetime, subscribes to the addressed resource hint and releases local overrides after an authoritative reread. RED tests reproduced private rows during account changes, obsolete callbacks and a late failed UI request restoring a superseded correction; all are fixed. The React dependency warning and backend complexity growth were removed rather than increasing caps.

Evidence: 41 PostgreSQL cases across source actions, read withdrawal, native HITL/edit/replay and independent writer-lock probes, followed by four targeted clock/no-op/rollback cases; 28 localized/authority/source-contract units; 888 broader application/source/cold-start/catalogue/size/coupling units; ten frontend synchronization/helper cases. Independent PostgreSQL control and NOWAIT/lock-timeout probes prove the user-before-record lock order fences source UI writers. Strict MyPy of eight new owners and the two final projection owners passes. Official frontend lint/ratchets/non-incremental TypeScript and six-language parity pass; backend CC291/max78 remains unchanged. No new browser markup was introduced. No production, provider, physical-device or full Pipeline/ReAct conversation qualification is claimed. This slice is closed; the other non-administrator families remain open and administration has not begun.

## Native learned-habit overview — closed after inline cold review

The habit overview reads the stored profile, published source thresholds/heatmaps, activity streaks, all saved statuses and advisory recurrence candidates. No profile is created and no learning, presence ping, recompute or provider call runs. A bounded kind/key/id page and complete owned count share one data statement. Candidate exclusion uses all owned keys, including blocked tombstones beyond the returned page; full private rows/payloads are not accumulated for that exclusion. Candidate overflow/provenance and the source best-effort advisory fallback remain explicit.

The UI and native reader share the extracted source profile/overview projection. The read-only source collection is covariant while retaining the same JSON array wire shape; native payloads are strictly JSON. Source public fields grow through inheritance and field-selection guards. The source deployment ceiling remains enforced, but the operator learning switch and the user's learning preference do not deny consultation of retained records, matching the source record-versus-act rule. Both active actor and native availability are checked after the observation.

Evidence: ten real PostgreSQL cases for complete pages over 103 records, empty scope, foreign cursor, native withdrawal, actor/deployment withdrawal, disabled personal learning and disabled operator learning, plus complete blocked-key candidate exclusion; seven strict input/public-projection guards; 1160 application/habits/cold-start/catalogue/size/coupling units. Strict MyPy passes five new owners, Ruff/Black and six-language parity pass, backend complexity stays CC291/max78. No frontend layout changed. No production, provider, physical-device or full conversational-mode qualification is claimed. This overview slice is closed; habit explanation and confirmed management actions remain open, along with the other non-administrator families.

## Native habit explanation — closed after inline cold review

The UI and native explanation now share one owned source reader. It publishes the actual kind-specific detector thresholds and source payload/signals/status, with real advisory recurrence dates only for recurring-request habits. Window explanations read no recurrence ledger; missing/unavailable dates are never fabricated as conversation references or evidence of absence. The existing source repository refreshes its identity map on owned reads, preventing an older in-session ORM instance from replacing current persisted facts. No learning, presence, recompute, provider or persistence write is introduced.

The native input is identity-only, payloads remain typed JSON and both the native switch and active actor are checked around the observation. Source public fields are inherited; explicit guards reject invented evidence/authority and require detector review when a new habit kind appears. The actual read adapters share finite error handling and accept raw Pipeline dictionaries as well as validated ReAct inputs. All six progress translations are present.

Evidence: twelve source/native PostgreSQL cases after owner extraction, then five owned/missing/foreign/raw-native explanation cases plus eleven schema guards; 1167 broader application/habits/source-API/cold-start/catalogue/size/coupling units. Strict MyPy of five changed owners, Ruff/Black, six-language parity and unchanged backend CC291/max78 pass. Source API tests now patch the extracted source reader, preserving their real HTTP ownership/threshold/date assertions. No frontend markup changed. No production, provider, physical-device or full conversation qualification is claimed. Habit explanation is closed; confirmed habit management and the remaining non-administrator families are still open.

## Native habit learning preference — closed after inline cold review

The normal settings API and native action share the source account-locked preference command. Mandatory exact approval changes only future learning. Retained habits, blocked tombstones, profile and evidence are preserved; an analysis already begun may finish. A source preference change invalidates approval, a confirmed unchanged value is a no-op, and native availability/active ownership/expiry are checked again before commit. The editor accepts only the source preference and replaces the approval digest. No recompute, provider or new security workflow is introduced.

Evidence: eight PostgreSQL preference scenarios including both failed and actually committed lost acknowledgements, three durable HITL/editor flows, twelve strict/localized guards, 1183 broader units and 41 frontend cases. Strict MyPy, owned ESLint, non-incremental TypeScript, six-language parity and unchanged backend CC291/max78 pass. A fresh Docker production bundle passes the three existing habits-panel Chromium journeys, including exact pause write and 320px containment; its transport guard passes. The global frontend complexity gate remains blocked by the concurrent AssistantAvatar.tsx growth, and the global E2E typecheck by the concurrent selected-chat-avatar.spec.ts imports/readonly deletions. Those files were not changed for this slice; the scoped browser run is reported separately, not as a complete global gate. The temporary server was stopped after verifying its recorded PID, parent and exact launch path; development services remain running. Build-only tsconfig additions were removed precisely. No production, paid provider, physical-device or complete conversational-mode qualification is claimed. This preference slice is closed; individual habit management and remaining non-administrator families continue.

## Native individual habit management — closed after inline cold review

The two native actions pause/resume/block and delete one learned habit through the same source command as the normal UI. Full public identity, evidence, signals, observation and lifecycle are sealed in the mandatory confirmation. Edited identity/status obtains fresh facts and replaces the exact approval digest; unknown/foreign/deleted/changed rows refuse. Pausing retains learning evidence, blocking keeps the anti-relearning tombstone, resuming lifts it, and deleting permits relearning. Existing profile, activity, advisory ledger and learning switches are not erased or changed. An offer already in flight may finish. Unchanged status is an explicit confirmed no-op.

Four real PostgreSQL REDs exposed stale detector refresh/demotion/light-touch overwriting or deleting a newer block/pause. Refresh now reloads under a row lock; demotion and light touch use conditional database writes. The sync reports the actual upsert result. A further independent RED proved the detector could take a child lock before an exclusive account lock; its affected writes now take a compatible parent key-share lock first, so a later FK-backed insertion cannot reverse the native parent-then-child order. Source UI writers share the same command and remain usable when native tools are off.

Evidence: thirteen real PostgreSQL transition/refusal/expiry/withdrawal/no-op/lost-ack cases; six durable native HITL/editor/replay flows; three actual source-route ownership/control cases; four stale-detector cases and two independent PostgreSQL lock probes with positive controls, NOWAIT and lock timeouts; nineteen strict/source-growth/six-language confirmation/editor guards. The broader review passes 1356 application/habits/catalogue/startup/size/coupling/complexity units; final affected source/locking/recompute sweep passes 32 cases. Forty-four frontend synchronization/panel tests, owned ESLint, non-incremental TypeScript, strict MyPy of eight native and four source owners, Ruff/Black and six-language parity pass. Both new complexity violations were decomposed; backend CC291/max78 is unchanged and no cap was raised. The existing addressed habit-resource reread covers status and removal without new markup or per-card HTTP requests. Previously documented concurrent global frontend/E2E gate failures remain separate. No production, paid provider, new browser/physical-device or complete Pipeline/ReAct conversation qualification is claimed. Individual management is closed; full forgetting, explicit recompute and the remaining non-administrator families continue. Administration has not started.

## Native full habit forgetting — closed after inline cold review

Full forgetting shares the normal UI's source command: all owned habit rows including blocks, the rhythm profile and durable activity rollup are erased, then the source recurrence/presence cleanup runs. Complete PostgreSQL scope and every source column are fingerprinted through bounded cursors; only localized counts and retained-history effects appear in the preview/editor. New/changed/profile/rollup records require fresh approval. No arbitrary owner, Redis key or approval proof is accepted. Future source columns change even an empty scope's comparison. Conversations/outcomes/feedback and learning settings are retained, so later learning or explicit recompute may reconstruct habits.

PostgreSQL completion and advisory cleanup are reported independently. A new server-owned typed observed-values receipt prevents a forecast from replacing the actual result, including post-commit failure and ledger-settlement failure. If Redis cleanup fails, the native result remains failed/committed with explicit unconfirmed cleanup, and the addressed refresh still runs. The source UI also returns that signal. A frontend RED reproduced false success on failed/absent cleanup attestation; the hook now validates the response through the CSP-safe Zod wrapper and shows a localized partial warning. A second RED reproduced an absent retry button after persistent rows disappeared; complete forgetting stays available for temporary-only state. Both advisory scopes are attempted independently if one fails. Revocation after the SQL commit refuses the later cleanup without denying the committed erasure.

An independent PostgreSQL RED found that recompute could seed advisory data before its owner fence. The entire source recompute now takes its compatible parent lock before seed/sync/profile writes, preserving parent-before-child order with full erasure. Actual source recompute integration and its two presence-only fixtures are qualified; no provider is called.

Evidence: seven real PostgreSQL cases over 203 saved rows/two cursor pages, foreign exclusion, stale/new scope, failed/actually committed lost acknowledgements and late revocation; four actual native durable HITL/editor/partial-result flows; three independent lock probes; four advisory failure simulations; eleven authority/localized/private-digest guards and two observed-receipt REDs; 31 combined source/fence/HTTP cases, then 53 source/recompute/contract/cold-start cases. The broader review passes 1214 application/habits/size/coupling/cold-start units. Forty-eight frontend synchronization/panel tests, owned ESLint, non-incremental TypeScript, strict MyPy of eight owners, Ruff/Black and six-language parity pass. Backend CC291/max78 remains unchanged; no threshold was raised.

The existing Docker dev server returned socket hang up before app/styles loaded, so its five attempted browser journeys are infrastructure failures, not passes. A fresh isolated production bundle built in that same Docker environment then passes all five hermetic Chromium journeys, including explicit confirmation/no prior write, partial warning followed by exact retry, desktop/320px containment and the original pause/read journeys. The transport guard passes. The identified temporary server was stopped and only the two mechanical build includes were removed. Earlier concurrent global frontend-complexity/E2E-typecheck blockers remain separately documented. No paid provider, production, physical-device, other browser or complete Pipeline/ReAct conversation qualification is claimed. Full forgetting is closed; explicit recompute and the other non-administrator families remain open. Administration has not begun.

## Native manual habit recompute — closed after inline cold review

The native action and normal UI share an account-locked source manual recompute with force enabled. It evaluates current retained human activity/history and advisory recurrence evidence after mandatory exact approval, without predicting a learned verdict. The user's automatic-learning preference is preserved; explicit manual recompute remains available with that preference off, matching the actual UI. The operator HABITS act capability remains required. Effective timezone/preference changes require fresh approval; actor/native/capability/expiry checks run before work and before commit. Temporary evidence seeding is separate from SQL and is stated as such, so failure never promises total rollback. The actual source outcome and public profile travel through the observed-values receipt.

A real PostgreSQL RED reproduced an old ORM rhythm profile after a raw upsert; the shared profile reader now repopulates persisted facts. A duplicate test was removed after the source-reader regression moved to its own focused file. No new detector, provider, model call, automation, presence ping or security workflow is introduced. The editor exposes only the current-account request and refreshes approval facts; preview scope and progress are localized in all six languages, with no invented resulting windows.

Evidence: eight actual PostgreSQL source scenarios (computed, empty, disabled automatic learning, changed timezone, operator/deployment off, late native withdrawal and both lost-ack dispositions) plus the cached-profile RED; three durable native HITL/editor/no-approval flows; eleven authority/source-output/localized-editor guards; 23 source HTTP/cold-start cases. The broader review passes 1229 application/habits/cold-start/size/coupling units. Strict MyPy of seven final source/native owners, Ruff/Black, six-language parity and unchanged backend CC291/max78 pass; no cap was raised. The existing habits resource hint and frontend reread are reused; no new layout was introduced. The preceding bundle's five hermetic panel journeys remain the UI geometry evidence, not a claim of full conversational-mode coverage. No paid provider, production, physical device or complete Pipeline/ReAct conversation qualification is claimed. Manual recompute is closed; the remaining non-administrator families continue and administration has not started.


## Public personality observation — closed after inline cold review

The native public selector reuses PersonalityService and inherits both public UI contracts. Available choices retain source ordering and translation fallback, complete visible count and bounded output pages. Stored personality_id and effective personality remain distinct, including a retained deactivated selection or the default. No administrative prompts, traits, translations or source jobs are exposed. Changing/resetting personality already belongs to the existing exactly confirmed preference command; no competing action was introduced. Fresh native availability and owner preferences are checked before and after observation, with stale language/selection refusing the result. Future public schema fields enrich the reader through inheritance.

A reproduced dependency-failure RED found broad exception handling that silently treated a failed database read as a removed choice. Source fallback now catches only ResourceNotFoundError; database failures propagate as unavailable while removed-choice fallback remains intact. Source list_active retains its existing full public catalogue fetch and selectin translations (no N+1); model output is bounded. This slice adds no provider call, persisted state, UI layout or device action.

Evidence: six disposable PostgreSQL catalogue/current-selection/ownership/cursor/revocation/stale-language cases, six strict/source-field guards, two dependency-failure/fallback cases, existing selection and cold-start checks (ten targeted units), 1234 broader application/habits/cold-start units, strict MyPy of four owners and CC291/max78 unchanged. Source public DTOs, SQL filters, translation fallback, private-field exclusion and registry/startup composition were reviewed inline. No production, paid-provider, browser or full conversational-mode qualification is claimed. The remaining non-administrator families continue; administration has not started.

## Observed psyche settings, state, expression and history — closed after inline cold review

The native reader inherits every public state/expression/history field, replacing loose JSON annotations with JsonValue. Missing state and expression remain explicit null without calling get_or_create_state, summary generation or commit. Existing observations remain visible when the personal engine preference is off; fresh native and source platform authority fence both observation boundaries. Private appraisal and narrative are excluded. UI state/expression share one source compiler; source history and the new bounded reader share filters and deterministic created_at/id ordering. The history page and complete filtered total share one SQL statement, with cursor ownership/filter checks and an explicit as_of window for continuation. The legacy trait_snapshot name is explained as actual dynamic history rather than invented trait evolution.

Cold review covered private-field projection, operator revocation, personal preference changes, null observations, fixed-memory output, source-derived filters, equal-date pagination, no model/presence/materialization side effects, and registry/startup reachability. A forward-reference construction failure was reproduced and removed through explicit source ActiveEmotionResponse typing; a tuple inference error was fixed with its precise variadic type, without casts or ignores.

Evidence: seven real PostgreSQL ownership/absence/filtered-time/empty/future-window/refusal scenarios and nine strict/source-field guards (16 targeted passes), 1141 application/psyche/cold-start non-regression units, strict MyPy of six owners, Ruff, six-language parity and CC291/max78 pass without threshold increases. No new layout or paid call was added; no production, browser, physical-device or full conversational-mode pass is claimed. Confirmed psyche writes and the other non-administrator families follow. Administration has not started.

## Confirmed personal psyche settings — closed after inline cold review

Four sparse source preferences (enable, display avatar, sensitivity and stability) now share the UI command, current owner lock, exact approved-field comparison and last-moment native/source authority and expiry checks. Explicit null, empty patches, coercions and out-of-range sliders are rejected; the model schema publishes the same non-null 0–100 contract. Unchanged values are verified no-ops; lost commit acknowledgement remains unknown, including when PostgreSQL actually committed. The durable editor rereads comparison facts and replaces approval. Only personal settings change; no reset, history removal, personality change or provider call belongs to this command. Source background analyses already started may finish.

The addressed psyche hint carries field names only; owned authenticated queries reread settings and update the existing avatar store. Frontend REDs reproduced missing native refresh, cross-account data/obsolete callbacks, an obsolete mutation overriding newer source values, same-account panel mount losing live mood, and false success for absent API acknowledgement. Account-aware source reads, current-lifetime callback fences, explicit store ownership and authoritative rereads resolve these cases. A passive GET state option preserves the legacy default while the normal frontend opts out of implicit state creation; an absent state remains null. Existing layout, controls and six-language labels are reused.

Cold review covered source wire compatibility, fresh inactive-owner refusal, rollback expiry/revocation, sparse zero/false values, unknown completion, mandatory HITL/editor replacement, metadata-only sync, ownership, current live mood, absence of unconfirmed materialization, private data and prompt projection. The growing composition registry crossed its 600 logical-SLOC ceiling: existing telephony declarations were extracted verbatim into their family spec with the original registration order, instead of raising the ratchet. Strict forward/null typing was corrected without ignores/casts. No frozen threshold increased; unrelated concurrent frontend complexity improvements were not captured into this lot's baseline.

Evidence: 37 combined disposable PostgreSQL/source-route/read/transaction/HITL/contract cases; 32 frontend panel/store/resource/SSE tests; 1178 broader application/psyche/cold-start/size/coupling/complexity units; strict MyPy of eight owners then three affected registry/router owners; affected Ruff/Black, owned ESLint, non-incremental frontend TypeScript, six-language parity and backend CC291/max78 pass. The current frontend CC ratchet also passes (earlier concurrent failure has changed); no new layout or browser/full conversational-mode/paid-provider/production/physical-device pass is claimed. The remaining non-administrator families continue; administration has not started.

## Confirmed psyche resets — closed after inline cold review

One mandatory exact-confirmation action covers the source soft/full/purge levels. Actual writes and previews share the extracted pure source transition. Soft resets mood, active emotions, appraisal and drives; full also resets relationship, efficacy and narrative while preserving stored traits; purge removes state and all owned history. Settings/conversations remain, and later or already-started interactions can reconstruct data. Soft/full append one source reset snapshot when state exists; absent state is a verified no-op. The previously misleading source schema/router descriptions were corrected.

Every state/history column, complete owned scope and the source transition are fingerprinted through bounded, finally-closed cursors; new rows/private changes or a changed baseline refuse old approval. Only public source deltas/counts are rendered. The editor accepts the source level alone and replaces approval; future source levels/fields fail closed pending reviewed effects. Observed post-flush effects and history counts populate the server-owned receipt instead of predicted values; expiry/native/source authority is checked again, and both actually committed and uncommitted lost acknowledgements remain unknown.

Adversarial REDs reproduced zero traits being treated as missing, a stale ORM personality concealing an administrative baseline change, inverse owner/child lock ordering, stale state after purge, missing history invalidation and a manual refresh accepting another account's response. Zero values and the precise trait reader now preserve source truth/freshness. Source state/history writes take compatible parent key-share before dirty flush; an independent PostgreSQL positive control/NOWAIT/lock-timeout probe confirms the boundary. Native hints reread passive state/settings and open history; authoritative null clears observed state while preserving owner/preferences. Manual state refresh also refuses obsolete owners and opts out of initialization. No model call or new layout was introduced.

Evidence: 28 combined disposable PostgreSQL reset/baseline/foreign-scope/lost-ack/HITL/editor/independent-lock/contract cases, including 203 history rows across cursor pages; 58 frontend account/state/history/store/panel/SSE cases; 1190 application/psyche/cold-start/size/coupling/complexity units; strict MyPy of twelve owners, affected Ruff/Black, owned ESLint (exit 0), non-incremental TypeScript (exit 0), six-language parity and backend/frontend complexity gates pass without cap increases. No production, paid-provider, browser/physical-device or complete conversational-mode qualification is claimed. The paid source summary and other non-administrator families remain; administration has not started.

## Journal management observations — closed after inline cold review

The bounded native reader shares the management API's settings, last observed cost, active-only character usage, active theme counters and canonical themes. Complete filtered entry counts include archived records unless a status is requested; stable created_at/id cursors are owned and bound to the same filters. Page, count and cursor validation share one SQL observation. Public source fields evolve together through schema inheritance, excluding embeddings and private extraction references. Personal journal-off preserves management records; fresh deployment/operator native and journal authority fences both observation boundaries. No injection bookkeeping, embedding, extraction, consolidation, portrait compilation or provider call occurs.

Cold review verified source-route compatibility, absent and personal-off records, equal-date pagination beyond one page, active counters distinct from filtered totals, foreign/other-filter cursors, late persisted operator revocation, strict input bounds, public source inheritance and startup wiring. Existing source theme warnings and helper imports remain compatible through aliases. No layout was added, and no ratchet ceiling was raised.

Evidence: 20 targeted disposable PostgreSQL/source-theme/input-contract cases, 1506 application/journal/size/coupling/complexity units, strict MyPy of six owners, affected Ruff/Black and six-language parity pass. Earlier fresh-start qualification is retained; full conversational modes, paid providers, production and physical devices are not claimed. Portrait and confirmed journal actions follow; administration has not started.

## Current source-authorized journal portrait — closed after inline cold review

The source UI and native reader share the portrait projection and existing lineage predicate. Missing, personally disabled, unversioned, changed-revision or changed-source portraits expose null fields; retained stored prose is not misreported as deleted. No regeneration, model call or source content collection occurs. Public portrait and source publication provenance remain observations, marked untrusted. Native authority is refreshed around both projections and at completion; changed observations refuse rather than combining different versions.

Evidence: six real PostgreSQL current/stale-source/stale-revision/consent/missing/late-revocation scenarios plus a fresh-interpreter native startup test (seven targeted passes), 1506 broader application/journal/ratchet units, strict MyPy of four owners, affected Ruff/Black and six-language parity pass. Cold review covered source route behavior, cached ORM refresh, absence semantics, lineage reuse and tool visibility. No new layout, raised ceiling, paid-provider or complete conversational-mode qualification is claimed. Confirmed journal settings follow; administration remains outside this lot.

## Confirmed journal preferences — closed after inline cold review

All seven sparse source preferences use one UI/native owner-locked command. Exact approved fields are compared freshly; current active usage is checked under the settlement lock before lowering total storage. Source extraction revisions and portrait invalidation rules remain unchanged. Personal disable keeps entries; budgets affect future work, and enabling history/consolidation does not start a model call. Empty/null UI legacy requests remain omitted/no-op, while native empty/null/coercion/extra authority is refused. New source fields fail the reviewed confirmation/invalidation field guard until explicitly covered. Durable edits replace approval; expiry, late operator withdrawal and lost commit acknowledgement retain honest outcomes and observed values.

The journals hint has field names only and rereads owned entries/settings/portrait. Actual frontend REDs reproduced absent native refresh, old-account callbacks and a stale portrait surviving a failed native reread. Account-query lifetime fences, immediate portrait invalidation and strict native refresh resolve them. Existing manual portrait-refresh transport behavior and source-cache tests remain; no layout was changed. Every mutation callback now refuses obsolete owners. The shared account query exposes the source's verified-refresh result behind the same current-lifetime fence.

Cold review also found the extracted command crossing the complexity boundary and route unit fixtures still mocking its old location. Storage validation and observed acknowledgement were decomposed; fixtures now assert the real fresh repository lock seam, with real PostgreSQL evidence retained. No cap increased. All seven approval labels and effects render in six languages.

Evidence: twelve final disposable PostgreSQL transaction/HITL/editor scenarios (including actual committed and uncommitted lost acknowledgements), fourteen native source-bound/approval-language guards, eleven existing source lifecycle units, a fresh-interpreter tool startup test, 1520 broader application/journal/structure/complexity units and 62 frontend account/source/transport/resource tests pass. Strict MyPy of eight owners then six final owners, affected Ruff/Black, owned ESLint, non-incremental TypeScript, six-language parity and backend/frontend complexity gates pass. Unrelated concurrent baseline improvements were not captured. No production, paid-provider, physical-device or complete conversational-mode qualification is claimed. Remaining journal lifecycle actions and other non-administrator families continue; administration has not started.

## Confirmed individual and complete journal removal — closed after inline cold review

One mandatory-confirmation tool requires an explicit entry UUID or explicit null for every owned active/archived entry. Complete owned entry/evidence scope and portrait/revision facts are streamed under bounded cursors; table/column identities and every stored value bind private comparison, while approval carries counts or complete individual public facts. New rows, private edits, changed source portrait and revoked/expired authority refuse older approval. UI and native removal share owner-first locking, source deletion, attached evidence cascades, portrait invalidation and observed postconditions before commit. A source service returning without the promised deletion is refused. Empty bulk scope still follows the source's portrait invalidation, rather than inventing a no-op. Lost acknowledgements remain unknown even when PostgreSQL committed.

The editor reduces private scope to the explicit public selector and replaces approval after a fresh read. Six-language effect notes, exact before/after facts and expiry appear in the source preview; private digests never enter it or the editor prompt. One addressed journals hint rereads existing account-scoped sources. No provider or new layout was introduced.

Adversarial review reproduced a real vector-fingerprint false negative after changing a middle element while preserving its SQL timestamp: default numpy display elides that element. Vector columns now hash PostgreSQL's complete canonical text. A first passing probe had only detected updated_at; the immediate counter-probe preserved it and proved the hole before correction. Attached evidence assertions now read PostgreSQL rather than stale identity-map objects. The generic preview composition crossed its logical-SLOC ceiling: existing cohesive reminder previews were extracted verbatim into reminder_rendering, without changing their behavior or raising a cap. Existing source contracts and cold-start wiring pass.

Evidence: eleven real PostgreSQL complete/individual/foreign/new-row/private-text/private-vector/expiry/late-withdrawal/missing-effect/lost-ack cases, three durable tool/HITL/editor flows, nine strict/six-language/private-context guards and a fresh-start tool test (24 targeted passes), 1529 broader application/journal/structure/complexity units, strict MyPy of eight owners then five final owners, affected Ruff/Black and six-language parity pass. No production, paid-provider, physical-device or complete conversational-mode pass is claimed. Remaining non-administrator journal actions continue; administration has not started.

## Confirmed manual journal creation — closed after inline cold review

The complete source manual configuration and server identity are approved before any provider work. UI and native creation share one source command. Manual content now follows the public API/form's absolute limit; the previous route implicitly used the lower automatic-service default and could reject schema-valid form content. Automatic extraction limits remain unchanged. Native search hints are bounded to the source's documented small keyword list and database item width, and future source fields require deliberate effect coverage. Observed stored configuration, source, identity and character count are verified before commit; the source starts manual/active evidence values and invalidates portrait without regeneration.

The existing source Gemini embedding path is called outside owner locks. Fresh account/capability/expiry checks and the shared account/instance quota guard run before every source call. The source platform-cost context names the owner and stable command run, and restores any parent context on completion/error; degraded source vectors remain permitted. This paid door is declared in the existing chokepoint registry. Lost acknowledgements remain unknown, including an actual committed transaction. No paid provider was called during qualification.

Durable edits accept public configuration alone, retain server identity, reread authorization and replace approval. Complete escaped configuration, embedding-cost/degradation note and expiry render in six languages; exact current-account hints reread the existing journals UI. Cold review covered no-confirmation/no-cost, edited content, late withdrawal between vectors, quota withdrawal, provider-error context cleanup, source bounds, default normalization, identity/observed effects, startup and non-regression. A typed editor-local collision and a fixture that omitted the factory's explicit default normalization were corrected without weakening validation.

Evidence: five disposable PostgreSQL creation/revocation/expiry/actual-lost-ack scenarios, three real durable HITL/editor flows, an independent PostgreSQL positive-control/NOWAIT proof that provider work holds no owner lock, four cost-context/quota simulations, twelve input/complete-approval language guards, shared usage-chokepoint policy and a fresh-start tool test (45 targeted passes); 1564 broader application/journal/quota/structure/complexity units; strict MyPy of nine implementation owners and nine final owners with a corrected editor-owner recheck; affected Ruff/Black and six-language parity pass. Existing account-scoped frontend requires no new layout. No production, physical-device, paid-provider or full conversational-mode pass is claimed. Manual editing and remaining non-administrator surfaces continue; administration has not started.

## Journal exposure bookkeeping compatibility — closed after inline cold review

Cross-checking the real planner/response journal-context path showed that consultation can asynchronously increment injection_count/last_injected_at and the automatic updated_at stamp between proposal and confirmation. A real repository simulation reproduced a false STALE_STATE on an otherwise unchanged deletion. The private scope now compares semantic stored columns and complete evidence/scope identity, excluding exactly these exposure/timestamp fields; public preview metadata remains the observation originally shown. Content, vectors, evidence, private traces, new rows and portrait/revision changes still refuse stale approval. SQLAlchemy RowMapping is projected by declared column names, without casts or ignores.

Evidence: fifteen actual PostgreSQL deletion/HITL/editor cases, including the formerly false bookkeeping conflict and the preserved-stamp vector counter-probe, pass; thirty-two preview/structure/coupling/complexity guards, strict MyPy of both owners and affected Ruff/Black pass. This qualifies the existing removal lot for normal journal-context accounting; it does not claim a full model-driven Pipeline/ReAct or paid-provider run.

## Confirmed manual journal editing — closed after inline cold review

Sparse title/content/mood/hints/confidence/level changes use one source UI/native command. The approval projector calls the existing evidence/revision helpers and a newly extracted pure confidence policy that the source recorded-write wrapper also uses. Changed content/level renews the rule revision and retires its current validation; old event provenance remains versioned. Requested high confidence can be clamped to medium and existing contradictions can force low; title/hint edits preserve current evidence. No proof or outcome is fabricated. The effective public source values, without predicted update/exposure stamps, appear in six-language before/after approval. Null/empty edits and oversized hint lists are refused in both runtime and the model-facing schema; [] clears hints. New source edit fields require deliberate transition/approval coverage.

Fresh semantic snapshots are checked before paid work and again under owner/entry locks. Source provider preparation shares the accounted, per-call quota path from creation and remains outside locks. Effective no-ops spend nothing and return observed public records. Projection changes, source edits, authority withdrawal or expiry refuse old approval. Post-flush stored public values must equal the approved effective transition, and lost acknowledgements remain unknown even after a real commit. The existing form/public content limit now also governs manual editing; automatic limits remain untouched.

Durable edits accept only the owned selector and sparse changes, reread source facts and replace approval; private full-row/evidence digests and predictions are excluded from the editor prompt. One metadata-only journals hint refreshes the existing owned interface. Cold review added snapshot/projection coherence checks and observed no-op receipts, corrected a source-inference assumption about contradictions from the actual clamp code, and verified source metric/log behavior is retained while preview is pure.

Evidence: twelve disposable PostgreSQL edit/contradiction/no-op/concurrent/private-scope/exposure/expiry/withdrawal/actual-lost-ack scenarios, three real durable HITL/editor flows, two independent PostgreSQL positive-control/NOWAIT proofs for create/update provider preparation, eleven input/schema/private-context/six-language guards (28 combined passes), then fifteen final transaction/flow rechecks; 1575 broader application/journal/quota/structure/complexity units; strict MyPy of ten final owners, affected Ruff/Black and six-language parity pass with no raised caps. Prior current-account frontend/transport validation is retained; no new layout, paid-provider, production, physical-device or complete conversational-mode run is claimed. Journal export/consolidation/feedback and other non-administrator families continue; administration has not started.


## Confirmed whole-journal export — closed after inline cold review

The existing UI export silently truncated at its 10000-entry display limit. A disposable PostgreSQL RED reproduced 10000 returned rows out of 10003; the shared source export now streams public DTO fields in bounded database batches and uses the existing transient/spooled CSV/JSON response. Active and archived owned entries are complete, foreign records and private vectors are excluded, CSV cells are spreadsheet-safe, and newer public fields inherit the source DTO with a deliberate vocabulary guard. JSON keeps the original entries/portrait envelope and preserves the raw stored portrait provenance, including old unversioned shapes and personally disabled learning. It does not confuse portability with the current authorized portrait read.

The native tool creates a small count/format/time preview and private complete-source digest; no file content, journal prose, portrait, embeddings, generation, retrieval or usage changes enter the proposal. JSON portrait metadata participates in the comparison; CSV exports entries alone. Original-session exact durable HITL, expiry, fresh native/journal capability, active account, source owner locking, whole-row comparison and single-use continuation guard the transfer. Changed/new entries or a changed exported portrait refuse stale approval. Format edits reuse the existing format-only editor/re-observation. The completion reports a browser request, never proof that the user saved a file. Existing memory/interest digests and export envelopes retain their behavior.

The existing chat attachment/card pattern now handles journals through one finite shared operation/title map, with six-language scope notes and progress/download labels. Cold review corrected a lossy assumption: the current typed publication provenance DTO could reject or omit legacy stored provenance; portability instead uses a strict JSON-valued stored-portrait schema. Source database cursors, transient files and canceled writes retain deterministic closure. No provider call or new layout was introduced.

Evidence: 65 targeted PostgreSQL/durable HITL/export/privacy/future-schema/file-bound/cancellation/cold-start checks pass, including 10003 entries in JSON and CSV and existing memory/interest flows; 1571 broader application/journal/export/structure/complexity units; 19 frontend component tests; strict MyPy of eleven owners, affected Ruff/Black/ESLint, clean nonincremental TypeScript, six-locale parity and both complexity ratchets pass without relaxed caps. Three real Chromium Docker production-output journeys cover keyboard confirmation, authenticated single-use download, failed transfer without replay, accessibility and reflow at 1280/320 px. The isolated build required production NODE_ENV; generated config additions were removed and the proof server/container returned to their original stopped state. No paid provider, physical-device, production or full conversational-mode validation is claimed. Remaining non-admin families continue; administration has not started.


## Journal-entry provenance read — closed after inline cold review

An owned UUID selects the source management UI's existing live provenance resolver and DTO. Both active and archived observations remain explicitly readable with personal learning off; fresh native/journal operator authority and active-account ownership are checked before and after resolution. Unknown and foreign entries have the same refusal. Deleted or foreign conversation sources retain only dated textless tombstones without foreign links. Origin/evidence/contradiction are observations, never invented proof; the published retained-history bound is not described as lifetime completeness. Excerpts remain untrusted external data through the existing result projection. No injection, embeddings, provider, consolidation, usage or preference write occurs.

The implementation, reviewed manifest, operation registry and cold-start tool loader are wired with six-language progress copy. Strict entry-only input refuses account/source/URL overrides. Cold review verified actual source membership joins, deleted-conversation filtering and source retention semantics instead of inventing a new provenance format.

Evidence: nine disposable PostgreSQL journal cases (live, deleted source, archived entry, foreign/unknown entry, initial/late native withdrawal, source capability disabled and foreign-source tombstone), seven existing memory provenance cases and cold-start reachability pass; five adversarial input cases and 1991 broader application/journal/shared/structure/complexity units pass. Strict MyPy of four owners, Ruff/Black, six-locale parity and unchanged backend complexity ratchet pass. No UI layout, paid-provider or new full conversational-mode run is claimed. Consolidation/feedback and other non-administrator families remain; administration has not started.


## Confirmed paid journal consolidation — closed after inline cold review

The native action confirms the current-account maintenance request, all-owned corpus comparison/counts and current source configuration; it does not invent the model's future edits. The source workflow reviews active entries, honors history consent/current authorized portrait sources, applies its lease/timeout/validation/independent portrait review, and owns actual model/embedding accounting and publication. Source prose and private full-corpus/source digests are absent from approval/editor text. Six-language notes disclose possible create/edit/merge/delete effects, portrait generation, platform costs/quotas and failures that may already have spent tokens. Editing re-observes and replaces the durable proposal.

Ephemeral typed caller controls attach to source claim/snapshot, each embedding and final settlement boundaries. Current native/journal capability, active account, personal journal consent, exact source scope and expiry are rechecked before work; final authority is checked after source flush but before commit. Embedding owner matches accounting context and each paid embedding passes the shared quota door. Withdrawals are outside the source embedding degradation catch, so denial cannot quietly turn into an authorized write without vectors. Background/UI callers without native controls retain their source behavior. Verified committed source outcomes produce one metadata-only owner-addressed journal refresh, including source no-op maintenance that still spends tokens and advances its watermark.

Lost settlement acknowledgement yields COMPLETION_UNKNOWN; a real committed deletion is explicitly observed under that outcome and is never assumed absent or replayable. Cold review corrected two misleading test seams: fault injection at the earlier read-only preparation commit did not prove a lost EFFECT commit, and the existing source fixture mocked away embedding preparation. Tests now inject at actual settlement and exercise real between-call controls. A PostgreSQL RED also proved consolidation discarded the caller's embedding context; a small typed restore seam now returns the exact parent object, including future fields. Existing token-accounting tests remain green. A native callback holder keeps individual function complexity bounded; existing canonical validators use a finite dispatch map. The unchanged pure layout delta helper was extracted to retain the file-size cap, preserving its old import alias and all existing behavior.

Evidence: 64 combined disposable PostgreSQL native/source cases (source publication/lifecycle suite plus no-op, quota, busy, stale/expired/withdrawn approvals, real lost acknowledgement, between-embedding withdrawal, parent context and actual durable HITL/edited proposal), 1607 broader application/journal/quota/embedding/structure/complexity units, ten private-editor/six-language/input guards and two scoped-control guards pass; 50 frontend journal/event/transport/account-switch tests pass. Strict MyPy of fourteen owners and five final owners, affected Ruff/Black and six-locale parity pass. Structure/coupling and both existing complexity baselines remain enforced without raised caps; the final targeted checks revalidate the extracted helper and restored context. No new layout, paid provider, physical-device, production or complete conversational-mode run is claimed. Portrait feedback and other non-administrator families remain; administration has not started.

## Confirmed portrait feedback — closed after inline cold review

The complete comment and selected excerpt are validated together against the source entry bound, displayed before consent, and saved as the source L0 correction without fabricated evidence. UI and native callers share the source correction projection and classified creation transaction. Actual zero-evidence confidence remains source-clamped to medium. Embedding authority/quota boundaries, fixed command UUID, owner-first scope validation and verified creation acknowledgement remain shared with manual creation. The macro then delegates to the guarded source consolidation against the post-correction scope, retaining the ORIGINAL approval deadline and no second hidden consent. Saved feedback and generated maintenance have separate observed outcomes; provider failure, concurrent change or expired remaining authority keeps a verified saved correction without claiming a new portrait.

Cold review preserves evidence-event counts across correction creation and retains a known source maintenance acknowledgement if later cleanup fails. Unknown maintenance remains explicitly unknown and cannot erase the known saved correction or justify automatic replay. Private comparison digests are absent from approval/editor text; six-language notes disclose the complete correction, platform costs, history consent and partial outcomes. One addressed journals hint reuses the existing owned refresh. The moved source projection is guarded at its real producer; the source effect-commit guard now requires the settlement helper rather than accepting an unrelated preparation commit.

Evidence: nine disposable PostgreSQL phase/HITL/editor cases (including source provider failure, change between saved correction and maintenance, and original deadline expiry), 1614 broader application/journal/quota/structure units, 54 targeted source/native regressions and 16 final public-input/six-language/partial-result/source-projection units pass. Strict MyPy of eleven owners and the final outcome owner, Ruff/Black, six-language parity and 23 final size/coupling/complexity guards pass without raised caps. Earlier source manual-creation/embedding-boundary regressions remain included. No paid provider, new layout, physical-device, production or full conversational-mode qualification is claimed. Other non-administrator families continue; administration has not started.

## Confirmed paid companion psyche summary — closed after inline cold review

Existing psyche observation remains free of summary generation and lazy initialization. The separate native action confirms current settings/language and whether source state exists, then delegates prose and fallback to the source psyche_summary slot, prompt and known-attempt settlement. No diagnosis or saved narrative is inferred. Full stored state/personality/input comparison stays private and never enters the editor or approval. The server re-observes source data, current native/deployment/active-account authority, expiry and quotas before work and at the model boundary. Source automatic state initialization is performed only after consent in an owner-first short transaction; its observed scope is captured BEFORE its commit, preventing adoption of a concurrent post-commit change. Actual provider work retains no owner lock. A late withdrawal or changed state suppresses generated prose while retaining source-owned spend accounting.

The narrowly optional source callback sits outside the fallback catch: authorization/quota refusal cannot become a successful template response. Source UI callers keep their original call shape and behavior. Paid model failure retains the existing source template fallback. Lost initialization acknowledgements remain unknown even when the created row actually exists; no provider is started in either acknowledged-unknown case. Partial initialization remains separately observable. Cold review exposed a shared executor defect: ResourceConflictError dropped an acknowledged first-phase receipt. A RED-to-green guard now preserves only committed actual values and committed status on a second-phase conflict, covering both summary initialization and saved journal feedback. Fixed-scope editor requests share a finite typed dispatch to retain the existing complexity ceiling; no cap increased.

Evidence: 25 final disposable PostgreSQL summary/feedback/HITL/editor/independent-lock cases, 55 targeted source/native/captured-billing regressions, eleven public-input/six-language editor guards, a source refusal/fallback boundary guard, a provider-reported token settlement test and 1458 broader application/psyche/quota/structure/complexity units pass. The independent-lock probe verifies distinct backend PIDs and a positive NOWAIT blocking control. Source reported tokens settle once on the caller session. Seventeen frontend account/psyche/transport tests pass without paid refresh. Strict MyPy of seven owners, nine wired owners and two final changed owners, affected Ruff/Black and six-language parity pass. Actual paid provider, physical-device, production and full conversational-mode runs remain unexercised. Other non-administrator families continue; administration has not started.

## Owned health sample and ingestion-token observations — closed after inline cold review

Two read tools complement existing health-agent summaries. Raw rows reuse the source UI's owned kind/inclusive-start/exclusive-end predicate and DTO. Both measurements and token metadata carry exact counts, bounded pages, timestamp/UUID ordering and owned/window/as_of-bound cursors. Later-created rows are excluded; existing source values and token lifecycle metadata remain explicitly mutable. Source offset listing retains its contract with a deterministic tie-breaker. Foreign, deleted or filtered cursors refuse continuation. Deployment/native/active-account authority is refreshed before and after reads. Actual health values additionally require the existing assistant-health consent; token metadata remains readable without that consent and never returns raw tokens or hashes. Public DTOs and kind-parity guards govern future additions. No model or mutation was added. Six-language progress, operations, manifests and cold-start loading are wired.

Evidence: 23 disposable PostgreSQL native/source/real-tool cases pass, including ingestion/aggregation endpoints, consent and late withdrawal, ownership, tied sample timestamps, all 103 token rows including revoked metadata, and malformed requests. Twenty-two initial targeted page/contract/startup checks and 1460 broader application/health/structure/complexity units pass. Strict MyPy of eight owners, Ruff/Black, six-locale parity and unchanged size/coupling/complexity gates pass. No new layout or paid-provider/device/production/full-mode claim. Native chart aggregates and health actions continue; administration has not started.

## Exact owned health chart aggregates — closed after inline cold review

The chart observer returns the existing UI response, defaults, UTC calendar buckets, empty gaps, per-kind/legacy fields and complete-window weighted averages. PostgreSQL computes grouped sufficient statistics in one owned window query; application memory holds only bounded buckets, never raw measurement history. A published source constant bounds bucket count and excessive requests fail before the statistics query, with coarser period/narrower window guidance and no silent truncation. Existing healthcare-agent summaries and UI implementation remain unchanged. Native/deployment/active-account/data-consent gates run before and after reads. Source DTOs, kind registry, bucket helpers and legacy-field projection remain authoritative. Six-language progress and exact manifest/operation/tool identities are wired.

Evidence: five exact UI parity cases over 3003 stored mixed measurements, 17 final disposable PostgreSQL observation/real-tool cases (including non-UTC SQL session, source gaps/weighted averages, empty window, initial/late withdrawal and excessive tool input), 19 targeted source calendar/startup/bounds checks and 1466 broader application/health/structure/complexity units pass. The parity test forbids the source raw-history materialization method. Strict MyPy of three calculation owners then seven wired owners, Ruff/Black, six-locale parity and unchanged complexity/file-size/coupling gates pass. No new frontend layout, paid provider, physical-device, production or full conversational-mode claim. Health mutations and other non-administrator families continue; administration has not started.

## Confirmed complete health sample erasure — closed after inline cold review

The explicit source kind or explicit null for every kind binds the complete owned sample corpus, including rows beyond UI/native pages. Private comparison streams all stored columns; approval/editor text contains only kind and exact per-kind counts. UI and native erasure share owner-first locking, source deletion, exact affected-count/remaining-row verification and acknowledged commit. Changed private values with preserved timestamps, new rows, expiry and withdrawn authority refuse older consent. Writers acquire a compatible active-owner fence before sample UPSERT, serializing ingestion without holding locks for paid work. Baseline/chart rollups query remaining raw records; learned memories/journals and still-active ingestion tokens remain separate, disclosed effects. Lost acknowledgements stay unknown, including an actually committed erasure. Source UI authority is refreshed under its owner lock.

A metadata-only owner-addressed health resource hint reuses authenticated source queries. The health hook now isolates account lifetimes, hides obsolete metrics while a confirmed refresh fails, ignores foreign hints and suppresses late-account raw-token responses. Existing UI folds/forms stay mounted while loading is announced. Duplicate identical authority checks encountered in the live-preference editor were removed, retaining all original effects and file-size ceilings. Six-language exact scope/cost-free erasure notes and progress, registry/startup/editor/executor/preview/event contracts are wired.

Evidence: eight initial complete-scope PostgreSQL cases, 32 source/native/HITL/editor/ingestion/rollup cases, 15 final lost-ack/late-withdrawal/independent-lock cases, 40 approval/registry/structure guards and 1476 broader application/health/structure/complexity units pass. Independent connections have distinct PIDs, a positive NOWAIT control and real ingestion lock timeout, followed by successful post-erasure ingestion. Seventeen frontend owner/template/transport tests pass; owned ESLint and strict MyPy of sixteen owners plus the final source owner pass, with six-locale parity. Backend caps remain unchanged. The requested full frontend gate was executed but is blocked by concurrent avatar additions: complexity in eyes/smiley/sphere-gpu.ts and spirit/__tests__/webp-envelope.ts; separate non-incremental TypeScript reports only eyes/__tests__/smiley-sphere-depth.test.ts mock incompatibilities. Those unrelated files/baselines were preserved. No new layout, paid provider, device, production or complete-mode claim. Health ingestion-token actions and other non-administrator families remain; administration has not started.

## Confirmed health ingestion-token revocation — closed after inline cold review

Exact owned source token metadata identifies the irrevocable action. Private full identity comparison includes the hash without revealing it; incidental use dates are excluded and revocation state is compared separately. Changed identities, labels/status, withdrawn authority and expired consent refuse stale proposals. Source and native commands share a fresh active-owner management fence. Ingestion rechecks the pre-authenticated token under its compatible owner fence before writing, so revocation serializes the authority decision as well as sample updates. Existing measurements remain. Actual source effects and unchanged identity are verified before commit; lost acknowledgements remain unknown even after real revocation. Source already-revoked tokens are observed no-ops. Exact HITL/edit/replay, six-language notes/progress and owned health refresh remain wired.

The UI secret lifetime is now tied to the existing account-lifetime object. Two RED cases reproduced a displayed secret returning after an account switch and a late creation response crossing an account switch/return; both now pass without a second authentication subsystem. Cold review consolidated destructive source owner checks and extracted finite native family declarations to keep registry size and complexity within unchanged ceilings. No threshold increased.

Evidence: 35 passing final PostgreSQL source/native/ingestion/rollup cases before correcting a replay-test entry boundary, sixteen final real HITL/edit/replay/independent-lock/erasure cases, two source inactive/deleted-owner cases, 1483 broader functional units and forty final source-contract/startup/size/coupling/complexity gates pass. Independent ingestion uses distinct backend PIDs, positive NOWAIT control, real lock timeouts before revocation and denied pre-authentication afterward. Retargeted source effects have a RED-to-green postcondition guard; actual committed and uncommitted lost-ack cases are covered. Ten frontend template/account-isolation cases, owned ESLint, non-incremental TypeScript, strict MyPy of fourteen wired owners and six final source/registry owners, formatting and six-locale parity pass. Full frontend quality gate is being rechecked against concurrent work. No paid provider, physical-device, production or full conversational-mode qualification is claimed. Other non-administrator families continue; administration has not started.
## Browser-only health ingestion-token issuance — functional slice validated, qualification finishing

Creation accepts the existing source optional label and bounds, with no actor, secret or proof input. The exact native draft creates nothing. Its authenticated originating browser explicitly continues under the original durable HITL receipt; command/effect fences are claimed before issuance, and source owner/session/native/deployment/deadline checks run at write and delivery. Source issuance keeps its cryptographic generator and hash storage, adds only an optional stable internal row identity, and verifies actual source metadata/hash plus approved label before acknowledgement. Registers, status, SSE, drafts and history receive only source public metadata. The raw token is returned once through a strict no-store/no-cache authenticated POST response and retained only in current-account component state. Lost SQL acknowledgements and lost settlement cannot recover/replay the secret. Acknowledged creation survives separate failed delivery as public metadata. Existing measurements/tokens stay untouched.

The existing account-lifetime/query/resource mechanisms isolate late responses and A-to-B-to-A transitions; close returns keyboard focus, missing clipboard capability is handled, and malformed responses refuse display. Six-language approval effects/progress reuse current UI text for the browser card. An edited label must repin the browser binding; the real edit test exposed this omission and its correction now passes. Dedicated health editors share the existing dispatcher without exceeding file-size ceilings. The health settings secret state was extracted to its small owner hook to restore the existing per-file complexity ceiling. No caps increased; concurrent frontend ratchet edits were preserved.

Evidence so far: six initial real tool/HITL/origin/replay PostgreSQL cases, 25 source/native/issuance/ingestion cases, seven final flow cases plus the corrected edit case, five source conditional/lost-ACK cases and five strict private HTTP boundary units pass. Forty-one final source-contract/cold-start/size/coupling/complexity gates and 1502 broader application/health units pass. Thirty-four affected frontend template/interaction/secret/keyboard cases, strict MyPy of fourteen owners, the full frontend gate including non-incremental TypeScript, six-language parity and formatting pass. A fresh isolated production build qualifies three actual Chromium HITL/keyboard/accessibility/reload/once-only journeys at desktop and 320px, including a lost response. Initial browser failures were proof-server asset-placement errors; actual assets were corrected and verified before the passing rerun. The global E2E package typecheck was run and is blocked by concurrent selected-chat-avatar/source-import typing; those files remain untouched. Physical devices, paid providers, production and full conversational modes remain unexercised.

The full frontend coverage run found 26 older fixture failures across useMemories and InterestsSettings: they omitted the authenticated account/onSuccess lifecycle now required by owned reads. Those fixtures now exercise the real owner guard rather than replacing it; 39 fixture/actual-ownership tests pass and a full coverage rerun is in progress. Administration has not started.
Final issuance qualification: the full frontend gate passed on the current snapshot. The corrected historical account fixtures and real ownership suite pass (39 tests), with ESLint/type checking clean. Full frontend coverage was rerun: 11941 tests pass and the only two failures are concurrent eyes/volume physical-prop-writer laurel/Smiley assertions; those foreign files are unchanged by this work, and no coverage percentage/pass is claimed from the failed run. The three corrected fresh-build Chromium health journeys pass, the isolated Node proof server is closed, and its build-only TypeScript includes were removed while retaining pre-existing includes. The issuance slice is closed after inline cold review; broader non-administrator coverage continues. The full E2E typecheck remains separately blocked by the concurrent avatar/source-import changes noted above.
## Relationship controls read — closed after inline cold review

The native read projects the exact source 360-degree scope/default interpretation, owned daily-debrief preference and fresh platform availability. It fetches no provider data, generates no debrief, writes nothing and adds no model call. Empty selections remain empty. Oversized persisted option arrays refuse to bound tool context. Active account/native availability are refreshed after the platform read; dependency failure is not described as a disabled feature. Cold review verified public-only projection, no actor input, late withdrawal and real tool registration.

Evidence: nine PostgreSQL cases and two contract/dependency units pass after repairing the actual-tool fixture's missing runtime store; the earlier run also passed all 24 startup/size/coupling/complexity guards. Strict MyPy of the three source owners, Black/Ruff and six-language parity pass. No threshold changed. The confirmed modification slice follows; administration has not started.
## Confirmed relationship preferences — closed after inline cold review

The Relations UI and native commands share a sparse source owner-lock transaction. Native approval covers only the selected top-level preferences; overview scope replacements expand their source defaults before the exact preview/editor/intent. Empty arrays exclude sources. The raw saved scope (including unsaved null) is compared under the lock, and unreadable/unbounded stored shapes refuse before being copied to the draft. Enabling the personal debrief does not override the platform switch or invoke a provider. Fresh account/native/deadline fences precede the write and commit. SQL lost acknowledgements produce an unknown outcome without replay. Source UI remains usable with native tools disabled; vanished/inactive owners now refuse instead of acknowledging an unstored choice.

The existing account query/state/resource hooks hide obsolete account data, cancel old callbacks, reread confirmed native changes and reject late manual responses after native refresh. Functional account-state updates retain queued independent edits without adding a second lifetime system. The original favorite refresh remains asynchronous so an acknowledged write is not mislabeled failed when its later read fails. Six-language exact previews/editor contracts and finite evolution guards cover source preference/scope additions.

Evidence: 28 initial update/real-HITL/editor/contract cases pass, four real GUI/independent-PID/NOWAIT/timeout cases pass in the broader run, and 62 final replay/source-fixture/startup/size/coupling/complexity cases pass. The broad run had 1514 passes plus three old source fixtures, corrected and verified in the final source suite. Thirty-four frontend affected-consumer tests pass; the final Relations/shared-state subset passes 29. Strict MyPy of nine source/execution owners, the full frontend gate including non-incremental TypeScript and six-language parity pass. No ceiling increased; concurrent foreign ratchet changes remain intact. No paid debrief, physical-device or full conversational-mode qualification is claimed. Administration has not started.
## Local relationship cards — closed after inline cold review

A bounded native read reuses the source overview/detail service, name folding, merges, exact totals, favorite/peer flags and source message visibility. Optional name selects the local card; no provider request, synthesis or write occurs. The saved daily-debrief switch is refreshed from current authority. Scope controls stay a separate tool. Limits and offset continuations traverse only what the source UI currently exposes; totals/truncation remain explicit when a source UI cap prevents more data. Pages are live observations, not an uncapped frozen export. Alias lists are bounded with their own exact total. The existing best-effort peer bridge is named as such, so missing observations are never proof of absence. Active/native access is checked after source aggregation, and data is passed as untrusted source content.

Evidence: four real-tool PostgreSQL scenarios (owned/foreign cards, local details, 53 aliases, exact five commitments, real continuation and late native/account withdrawal) and nine invalid-selector units pass. All 24 startup/size/coupling/complexity guards pass on the final source implementation. Final strict MyPy of four owners, formatting and six-language parity pass. The continuation fixture initially omitted imports removed earlier by Ruff; corrected imports and the actual SQL-backed pages pass. No thresholds changed, new frontend layout, provider or paid-model validation is claimed. Favorites and identity management follow as actions with mandatory confirmation; administration has not started.
## Confirmed relationship favorites — closed after inline cold review

The favorite tool selects a displayed name and explicit boolean only; preparation changes nothing. Durable exact HITL, edited retargeting and recorded replay reuse the native command/effect infrastructure. The source snapshots only the relevant resolved identity and star records into a private digest, with public before/after name/state in the preview, outcome and safe editor. An unrelated favorite does not invalidate approval. Unstarring a grouped card now removes stars on merged spellings through a source SQL subquery, retaining data/groupings/debriefs. This closes a real GUI defect reproduced RED. Source UI favorites, merges and splits serialize on the same active account lock as native commands, preventing their identity decision from interleaving. Stale grouping, expiry, late native withdrawal and uncertain SQL acknowledgement refuse or remain unknown; acknowledged replay executes no second source write and emits no second hint.

Cold review additionally exercised retained ORM facts across distinct real connections. Without explicit refreshing, a changed grouping reached the source postcondition rather than the initial stale comparison; populate_existing on both source lists now detects the change before attempting the write. A malformed non-flat selected grouping refuses. Finite relation editors were extracted to retain the existing file-size ceiling. No cap increased; foreign ratchet changes stay intact.

Evidence: 1553 final broader application/Relations/real-HITL/SQL-authority/contract/startup/size/coupling/complexity tests pass, plus two final real cache/unrelated-scope cases. Four independent writer probes use distinct PIDs, positive NOWAIT controls and actual lock timeouts for star/unstar/merge/split. The earlier 420-test scoped suite passes; older in-memory source fixtures were updated to expose the actual owner-lock query rather than bypass it. Strict MyPy of twelve source/native/editor owners, formatting and six-language parity pass. Existing addressed frontend resource sync from the previous Relations slice is reused; no new layout or paid model is introduced. Physical-device and full Pipeline/ReAct qualification remain later. Identity merge/split actions follow; administration has not started.
## Confirmed relationship grouping — closed after inline cold review

Explicit merge/split proposals reuse the Relations source semantics: selected aliased spelling reassignment, path compression and a single-alias split. Preparation writes nothing. Private scope comparisons pin relevant aliases and complete affected stored-debrief rows; public previews and safe editors expose only names, grouping and invalidation counts. Durable HITL, edited targets and replay use existing command/effect fences. Source and native writes share the active-owner transaction; expired/revoked/stale proposals refuse before commit, unknown acknowledgements remain unknown, and source postconditions prevent false success. Reassigning an existing alias now invalidates the previous canonical debrief too, a GUI defect reproduced before correction. Debrief identity resolution takes the same owner lock for its short claim only, committed before provider/model work, preventing identity decisions during grouping. No new synthesis is triggered.

The local detail rereads native Relations hints and hides obsolete account data. A real HTTP-hook test reproduced the missing refresh before correction; the person-switch simulation retains the real hooks and now declares its authenticated fixture. Relevant six-language previews/editor privacy, no-op preservation, source postconditions, stale debriefs, authority and acknowledged/unacknowledged SQL failures pass. Cold review checked source transaction ownership, no provider work under locks, no private proofs in model/editor/public results, registry startup and unchanged unrelated resources. Cohesive source-effect and relation-editor helpers remove the two new complexity hotspots without increasing caps.

Evidence: 39 final native/real HITL/boundary/contract/complexity checks and 1543 broader application/Relations/independent debrief-lock/startup/size/coupling checks pass; the earlier source-debrief fence suite passes 65. Seventy-six frontend affected-hook/panel/person-switch simulations pass. Strict MyPy of eight source owners, Black/Ruff, six-language parity and the full frontend lint/a11y/hooks/complexity/non-incremental TypeScript gate pass. The initial MyPy process stopped on Windows; the isolated non-incremental rerun passed. Foreign ratchet improvements remain untouched. No paid provider, physical device, production or full Pipeline/ReAct qualification is claimed. Administration has not started.
## Stored relationship debrief read — closed after inline cold review

The native read reuses RelationDebriefService.read and its source projection, grouping and exact statuses. It exposes only the existing body, original generation dates, requested/unavailable sections, nullable recorded usage and rebuild eligibility, plus a separate observation timestamp. Reading never builds, refreshes providers or adds spend. Source input is an explicit strict displayed name without actor/force. Fresh personal/platform/native/account guards suppress a body after withdrawal. Unreadable source versions retain the source absent status; oversized output refuses rather than silently shortening the synthesis. The output inherits the source DTO so future source fields enrich it directly. Tool text remains untrusted through the common wrapper.

Evidence: the missing-tool RED is followed by 18 real PostgreSQL/startup/size/coupling checks and 30 final source-state/privacy/late-withdrawal/bounded-data/query-contract/complexity checks passing. Strict MyPy of five wired owners, formatting and six-language parity pass. Cold review checked owner-bound canonical lookup, preserved previous bodies on failed builds, null versus zero usage, fresh access after reading, no paid entrypoint and actual cold registration. No new frontend layout or provider/model invocation was needed. Administration has not started.
## Confirmed relationship debrief generation — closed after inline cold review

The explicit name/force proposal pins the owned canonical grouping, saved bounded scope, language/local day, relevant user inputs and complete current debrief digest. Preparation performs no claim, provider read or synthesis. Exact HITL, edited names and durable replay reuse existing native command/effect ownership. Source claim and publication transactions remain short; actor/native/platform/personal/deadline/scope guards precede claim, external work, paid invocation and settlement. Optional source caller controls restore on exit and ordinary GUI builds retain their path. The source conditional claim, cooldown, unchanged-evidence shortcut, configured model and captured success/failure spend accounting are reused. Native requests share the GUI's actual daily Redis bucket and account/instance usage ceilings. Cancellation releases only its owned claim without exposing previous words or discarding paid accounting. Lost claim/settlement acknowledgements remain unknown and are never described as generated success.

Cold review found that background settlements need the child-row comparison fence too: exact comparison now locks the relevant row before source claim. Separate real-PID/NOWAIT/timeout controls verify that fence and prove that account/child locks are free during controlled model work. An initial proof fixture was not visible to other connections; its positive control rejected it, and the corrected proof uses genuinely committed disposable actors. Final publication compares the source-returned DTO to the actual owned row, bounds the payload and distinguishes new synthesis, verified unchanged evidence and reused stored words. Forged source success without a stored result is refused. Existing generation dates/recorded usage remain provenance rather than a new-spend claim. Source prompt clarifies that evidence is untrusted data and a suggested action is never an executed action. Future source build options require reviewed input/confirmation mapping at boot.

The existing UI debrief hook now isolates owner/person callbacks, hides old-account data and rereads native relation hints without purchasing a new automatic build. Late manual replies cannot overwrite native rereads. Its original absent-only once-per-person behavior remains, including React Strict Mode; source fixtures now declare authenticated owner/onSuccess rather than bypassing guards. A cancellable microtask removes synchronous effect-state mutation. Relation preview declarations were extracted cohesively to retain the size ceiling; no cap increased.

Evidence: 74 final debrief/source/HITL/authority/bounds/startup/structural gates pass, 31 final postcondition/disposition/HITL/independent-transaction/complexity cases pass, and the corrected real-transaction/source simulation suite passes 15. The broad run passes 1582 other application/Relations cases; its single rejected proof fixture is corrected and validated in the real-transaction suite. The preceding 91-case source/preview suite passes; source billing/prompt contracts pass 51 and the dedicated captured-spend suite passes eight. Eighty affected frontend hook/panel/person-switch tests pass, with 26 final real-hook/late-response/Strict-Mode cases. Strict MyPy passes thirteen wired owners and the final two-boundary/one-release-module checks; six-language parity, formatting, the full frontend gate and clean non-incremental TypeScript pass. The final startup/evolution/source-contract suite passes fourteen. No paid provider, physical-device, production or full Pipeline/ReAct qualification is claimed. Non-administrator provider context and remaining families continue; administration has not started.
## Provider relationship context read — closed after inline cold review

The native read delegates owned contact/mail/event cards to RelationContextService without forced refresh. Source cache provenance, per-section statuses, windows and address counts are retained, with no invented totals or synthesis. Strict unique section selection and inherited public DTO provide source parity and a boot guard detects new provider sections. The real UI Redis bucket is shared; native Redis failure refuses rather than bypassing quota. Fresh account/native guards run before quota, immediately after waiting, and after provider work. Oversized UTF-8 output refuses without silently dropping data. The existing frontend hides old-account context and refuses obsolete account/person callbacks.

Evidence: 144 source/native/startup/size/coupling/complexity checks pass; the final withdrawal and selector regression suite passes 12. Fifty-two affected frontend simulations, strict MyPy of four owners, Black/Ruff, six-language parity and the full frontend lint/a11y/hooks/complexity/non-incremental TypeScript gate pass. Cold review reproduced withdrawal while waiting on quota and now proves no provider invocation in that case. No ceiling was increased; foreign working-tree changes remain preserved. Forced refresh follows as a separate mandatory-confirmation action. No paid provider, physical device, production or full conversational-mode qualification is claimed. Administration has not started.
## Confirmed provider relationship refresh — closed after inline cold review

An explicit displayed name and nonempty unique provider-section selection prepare an exact mandatory HITL action. Preparation performs no provider request. Approval uses RelationContextService.build with refresh and sections set to the approved selection, shares the real UI Redis bucket, releases the short native transaction before external work, and rechecks fresh account/native/deadline authority after quota waiting and after work. Partial source statuses are retained as outcomes of the attempt, never generalized into provider success or exact totals. Timeouts are unknown; durable command/effect replay never repeats provider work. The safe editor exposes only public name/selection and edits require renewed confirmation. Source build-option evolution requires reviewed mapping. Six-language previews explain external quotas, partial availability and the absence of synthesis.

Cold review checked source cache best-effort persistence, contact address dependencies, no debrief or paid model, strict source selection, output bounds, owner-bound execution, and no source locks held over external work. The existing frontend rereads the normal cache endpoint on a native Relations hint; a late manual forced response cannot replace that reread. Two real-hook failures reproduced the missing synchronization before the correction. No new layout or ceiling increase was needed; concurrent ratchet improvements remain intact.

Evidence: 29 initial source/HITL/startup/size/coupling checks and 22 preview/editor/complexity checks pass; the final affected backend/source/structural suite passes 167. Forty-nine existing/actual frontend hook simulations, six-language parity and the full frontend lint/a11y/hooks/complexity/non-incremental TypeScript gate pass. Strict MyPy passes all seven changed owners with imported diagnostics separated. The original shared SQLite cache caused a native MyPy crash (also reproduced on the prior contract in Linux); a fresh task cache removes it. The full imported check reports two unrelated existing no-any-return findings in domains/habits/recurrence_sync.py; these foreign changes were preserved, not waived in repository configuration. Source provider behavior is simulated, without physical-device, paid-provider, production or complete Pipeline/ReAct qualification. Administration has not started.
## Owned peer-settings UI reads — closed after inline cold review

One finite-section native read exposes current discovery/address consents, accepted connection cards with both share directions and consented address, incoming/outgoing requests with incoming-only notes, own blocks, the bounded transparency log, and paginated delivered relay text from the account's own side. Public source DTOs are reused directly. Page bounds, observed totals, continuation and the unknown full-history count of the source-limited access log are explicit. Its source API limit is now one shared constant. No search, external provider, model, notification or mutation is performed. Fresh actor/native/Peers authority precedes and follows reads; late deactivation suppresses results. Existing compact peer listing, granted data reads and confirmed relay sending remain reusable distinct capabilities.

Cold review reproduced eight share SQL reads for eight accepted cards. The source service now loads authorized cards' shares once and preserves both directions; GUI and native paths benefit together. Stable ID tie-breakers make equal-timestamp pages deterministic. A second real test reproduced an accepted SQL row serialized as pending because a retained ORM pair was stale; pending/accepted source lists now populate existing objects explicitly. Ownership, masked versus consented addresses, incoming-only notes, sent/received private text and retained nulls are checked against disposable SQL. No new frontend layout is needed for a read; six-language progress labels are in parity.

Evidence: the broader source/native suite passes 249; final startup/size/coupling/complexity/source/contract checks pass 112. Five late/pre-access cases pass; the final real native/source suite passes 78, including actual one-query/both-directions shares, stable message continuations, retained-null/private-text exclusions and refreshed ORM facts. Strict MyPy passes all six read/source owners, Black/Ruff and six-language parity pass. The initial six failures were an inactive Peers test fixture; the corrected fixture explicitly enables the capability and retains dedicated disable tests. No ceiling increased. No paid, physical-device, production or full conversational-mode qualification is claimed. Confirmed consent changes follow; administration has not started.
## Confirmed peer visibility consents — closed after inline cold review

Sparse strict discovery_enabled/email_visible proposals read only the selected source account columns. Their independent audiences and exact before/after values are shown with six-language notes; omission preserves the other consent. No discovery search, invitation, relay message or lifecycle notification occurs. Actual HITL, edited reconfirmation and durable replay use existing commands/effects. Execution acquires the existing fresh active-user preference lock, compares exactly the selected approved values, invokes the PeersService source setters, rechecks native/account/Peers/deadline authority and verifies the persisted in-transaction postcondition before commit. No-op leaves the other consent intact. SQL ACK loss stays unknown, including a commit that actually happened. A false source success is refused; late withdrawal after flush rolls the write back. Source input/output option evolution requires reviewed mapping; planner schema rejects the same null/coercion/unknown shapes as runtime.

The existing Connections hook now uses account-owned queries, refuses obsolete write/search callbacks, hides old-account cards/consents and rereads the five source endpoints on addressed native Peers hints. This adds no layout. Real hook tests reproduced the missing refresh and old-account data exposure before correction. Native hints carry field names and account/resource identities only, never setting values. The public editor schema stays sparse. Cohesive shared consent projection removes a CC hotspot; family editor composition keeps the central dispatcher below its existing file-size cap. No cap increased or foreign baseline rewritten.

Evidence: 58 final flow/preview/registry/state/startup/size/coupling/complexity cases pass, with 14 final real write/HITL/postcondition/withdrawal/ACK scenarios passing. The broader native-contract/real Peer/refresh-flow suite passes 1241. Sixty-three hook/component tests, six-language parity and the full frontend lint/a11y/hooks/complexity/non-incremental TypeScript gate pass. Strict MyPy passes eight changed owners with the isolated task cache and imported diagnostics separated. Black/Ruff pass. The initial ratchets caught central-dispatch size and execution complexity; both are corrected structurally. No paid provider, physical-device, production or complete Pipeline/ReAct qualification is claimed. Administration has not started.
## Exact discoverable peer search — closed after inline cold review

A separate bounded native read reuses PeersService.search_discoverable, its exact source name/address branch, folded comparison, opted-in/active/named population, self exclusion, mutual neutral blocks and permitted relationship annotation. Returned source DTOs contain opaque peer IDs and masked hints, never raw addresses or administrative account data. Homonyms stay separate candidates; a displayed name is not authenticated identity. Limits and stable ID continuation bound model output and state live observation semantics. The query inherits the source input bounds under strict native validation; new source filters require explicit reviewed mapping. No invitation, notification, model, provider or consent write occurs.

The genuine anti-enumeration Redis key/window is shared with the UI; each page is charged. Native dependency failure refuses. Native/account/Peers access is checked before quota, immediately after quota waiting and after the source lookup. Cold review verifies that withdrawal while acquiring the budget prevents the source scan, withdrawal after the lookup suppresses all data, and rejected Redis access cannot bypass enumeration protection. Existing source search behavior is reused without a second identity heuristic.

Evidence: 45 initial SQL/source/startup/structural checks pass, the extended source/late-access/contract set passes 55, and the final inherited-schema/native/structural review passes 38. Strict MyPy passes four owners, Black/Ruff and six-language progress parity pass. No ceiling was raised or new frontend layout introduced. No physical-device, paid-provider, production or complete Pipeline/ReAct qualification is claimed. Confirmed invitations follow; administration has not started.
## Confirmed peer invitations — closed after inline cold review

Explicit selected discoverable peer ID and optional literal note prepare an inert exact HITL proposal. Public name/masked-hint/pair-state previews state that a crossing incoming request ACCEPTS the pair, while an existing outgoing pending request changes nothing and ignores a newly requested note. New/revived pending requests use the approved note. Relevant target identity/consent and complete pair-row comparison are privately digested; neither raw address nor proof reaches the preview/editor/outcome. Source eligibility, neutral mutual blocking, decline cooldown and conditional claim semantics are reused. Target/state changes require renewed approval; target withdrawal is neutral, invalid stored source statuses refuse. New source options/states require reviewed mapping.

Canonical account-parent locks now serialize the source GUI request and native comparison even for an absent pair row, in deterministic UUID order for crossing requests. Selected existing rows are compared under their own lock too. Source target/pair reads explicitly refresh retained ORM state. Execution rechecks account/native/Peers/deadline authority, invokes the source request verb without a state-changing redispatch, verifies its actual row/status, then commits. Notifications are attempted only after acknowledged commit and free parent locks. Source notification failure leaves a saved invitation intact; pre-commit withdrawal rolls back; before/after-commit lost ACKs remain unknown and send no unacknowledged notice. Actual HITL, amended notes and replay reuse the durable effect/command gate and emit one addressed resource hint. Private editor input, source false-success and name/state changes are covered. Cohesive target/comparison helpers and people-family preview/editor composition preserve existing size/complexity caps.

Evidence: 68 initial native/source cases and 114 reviewed flow/source/preview/startup/structural cases pass; the final broader native/Peers SQL/source suite passes 1468. Nineteen final real invitation/HITL/edit/replay/target/ACK/postcondition/fence cases pass. Two independently committed SQL probes use distinct PIDs and positive NOWAIT controls, prove GUI creation waits on the canonical fence, and verify the saved row plus unlocked parents during notification. The first broad run skipped nine SQL cases during a transient Docker endpoint failure; they were explicitly rerun on the verified local endpoint, first all nine and finally nineteen passing, never counted as success from skips. Strict MyPy passes ten owners plus three final projection owners, Black/Ruff and six-language parity pass. The account-owned existing Connections resource sync is reused; no new layout or cap increase. No actual peer notification, paid provider, physical-device, production or full Pipeline/ReAct qualification is claimed. Incoming accept/decline and remaining nonadmin actions follow; administration has not started.
## Incoming peer accept/decline — closed after inline cold review

A strict connection ID and explicit accept boolean produce an inert HITL proposal for an owned incoming pending request. Source public identity, masked hint and literal incoming note are pinned alongside the complete private pair digest. Outgoing and foreign requests refuse. Canonical sorted account locks and the selected row lock protect comparison and the source conditional transition; the persisted status and returned identity are verified before commit. Account/native/Peers/deadline checks surround execution. Edited decisions reread the source and require renewed confirmation. Replay serves the durable receipt without a second transition, notification or resource hint. Source notices run after acknowledged commit and released parent locks; failed notices remain reported as failed attempts after a successful save. Unknown commit acknowledgements never claim success or send notices.

Adversarial verification covers changed notes, concurrent source replies, already-declined state, foreign/requester identity, false source success, native/Peers withdrawal, late withdrawal after flush, expiry, before/after-commit lost ACK and notification failure. The incoming note remains literal in preview IR, is escaped by the actual HTML renderer in all six locales, and never enters the edit prompt. Two real independently committed PostgreSQL probes with distinct PIDs and positive NOWAIT controls verify the source writer is blocked by the native row fence and notifications observe the accepted committed row with unlocked account parents. Exact request/edit/replay HITL uses the actual draft executor, emits one addressed peers hint and performs no real outbound delivery.

Evidence: 28 response/real-HITL/preview cases pass, 34 independent transaction and structural/state cases pass, and 32 registry/manifest/draft-round-trip cases pass. Strict MyPy passes ten changed owners with an isolated fresh cache; Black/Ruff pass. Existing source-owned frontend refresh is reused; no new layout or baseline increase. No production, paid-provider, physical-device or full Pipeline/ReAct qualification is claimed. Remaining nonadmin Connections actions follow; administration has not started.
## Confirmed own-domain shares — closed after inline cold review

One explicit accepted connection ID, source domain and required level (or explicit null to revoke) prepare an inert exact HITL proposal. Source calendar availability/details and task titles are the single validation matrix; its reviewed public description and source-input/enum guards fail on undeclared additions. Current pair, public name/masked hint and the selected own-domain share are pinned; complete stored pair/share facts stay privately digested. Other domains and the peer's reverse-direction grants are independent. Same-level execution is an acknowledged no-op without a state hint. Source setter and persisted level postcondition are reused. Expiry, native/Peers withdrawal, late withdrawal after source write, false source success and before/after-commit lost acknowledgements refuse or report unknown honestly. Edits reread source state, reconfirm, and durable replay makes no second write/hint. No provider data fetch, lifecycle notification, message, paid model call or administrative operation is added.

Cold review empirically reproduced a GUI race: creation waited on the native pair lock through its FK, but updating or deleting an existing share bypassed that lock. Source set_share now acquires a refreshed pair FOR UPDATE before ownership/status validation and any child write. The source repository exposes this optional lock, refreshes retained identities and reuses it for fresh transition reads. Three independently committed PostgreSQL probes with distinct PIDs and positive lock controls now prove create/update/delete serialization. Actual consent tests retain reverse-direction shares, detect selected-share changes and allow unrelated reverse-direction changes. All six previews escape hostile identity via the actual HTML renderer, keep private proof out of the card, and give the editor only public target/domain/level. Six older read manifests now explicitly declare read mutation policy; the boot completeness test had exposed their missing declaration when their declared category was system.

Evidence: 210 reviewed share/HITL/source/registry/size/cycle cases pass, the broader native/Peers unit suite passes 1402, and 86 real source Peers/Workboard plus invitation/response/share PostgreSQL cases pass. Strict MyPy passes twelve changed owners, Black/Ruff and six-language progress parity pass. Global complexity remains within its shrink-only baseline (291 over threshold, max 78); no ceiling was raised. Two real frontend account-owned refresh tests pass, using the existing Connections resource hint and layout. Source notifier/provider/physical-device/production/full Pipeline/ReAct qualification is not claimed. Nonadmin severance/block/image operations remain; administration has not started.
## Confirmed connection severance — implemented and cold-reviewed; browser qualification remains open

An explicit accepted connection ID prepares an inert exact proposal including source public identity/masked hint and both directions of current grants. Complete pair and share rows are privately digested. Pending/outside-account pairs refuse. A changed pair or either share direction requires renewed approval. Execution retains the source conditional removal, revokes all shares, verifies the actual removed row and zero remaining shares, then acknowledges commit. The existing source Workboard adapter attempts to return work held between the pair in both directions, with its SAVEPOINT rollback on failure. The approval explicitly covers work shared at execution, including a ticket created after preparation; it never exposes private peer ticket content or promises a frozen ticket count. Positive own release counts come from the actual source event; absence is unknown, not an invented zero. Release failure preserves severance and leaves the tickets intact. Lifecycle notices to both sides are attempted only after saving. Lost before/after-commit acknowledgements remain unknown without notices. Edited targets reread and reconfirm; durable replay makes one write, notice attempt and addressed state hint.

Cold review reproduced another real PostgreSQL defect in the initial native path: a notice SQL error could leave the already-saved command's session aborted. A shared notify_saved_peer_action helper now owns a separate session/transaction for post-ACK notices, reused by invitations, responses and removals. The real division-by-zero SQL probe goes from red to green and the earlier independent notification/fence tests remain green. The source dispatcher may commit its archive before delivery without affecting the command owner. No real notice was delivered during verification.

Severance publishes peers, relations and workboard hints. Workboard now subscribes to its addressed resource, uses the shared account lifetime, immediately hides previous-account rows and refuses retained callbacks, and ignores late old-account reads/writes. A native refresh received during dragging or an outstanding write is retained and flushed when that gesture/write ends, preserving optimistic rows. Existing layouts, keyboard controls, responsive templates and ordinary polling remain in use.

Evidence: 42 final SQL/HITL/edit/replay/source/manifest/structural cases pass, including two independently committed probes with distinct PIDs and positive lock controls for source removal blocking and notice visibility after commit/free parent locks. A 32-case invitation/response/removal notification-regression set passes. The broader native/Peers/structural/CC unit suite passes 1420, including seven six-locale input/actual-HTML/private-editor contracts. Forty frontend Workboard/Connections/Relations hook cases pass. Strict MyPy passes thirteen owners, Black/Ruff, six-language progress parity, frontend lint/types/hooks/a11y/complexity gates and backend complexity hold. No cap was increased; unrelated baseline improvements remain owned by their concurrent changes.

Qualification limitation, explicitly open: the three existing Chromium Workboard journeys (desktop modification and two mobile cases) were attempted on an isolated dev server with intercepted APIs. All fail before hydration with an HTTP locale-redirection loop, reproduced on IPv4 and localhost. This does not count as a passing browser or mobile runtime proof. The proof server was stopped and its generated tsconfig includes removed while preserving other pre-existing entries; the generated next-env proof imports were removed. These browser journeys must be replayed during final global runtime qualification. Production, paid-provider, physical-device and full Pipeline/ReAct qualification are not claimed. Remaining nonadmin features continue; administration has not started.
## Confirmed directional blocks — closed after inline cold review

An explicit peer ID from owned Connections requests/connections/blocks and a strict blocked boolean prepare an inert exact proposal. Arbitrary opted-in accounts outside these visible source lists refuse neutrally; discovery consent is not an account-directory grant. Source public name/masked hint, own directional block, complete pair and both sharing directions are privately pinned. Blocking silently severs pending/accepted pairs and both grants, using source Workboard best-effort return policy for accepted pairs. Unblocking only lifts the caller's block; it never lifts the other person's block or restores a connection or grants. A separate private sharing digest verifies unchanged grants after unblocking, so simulated forbidden restoration refuses before commit. Same state without a live pair to sever is an acknowledged no-op. Notifications remain absent by source contract and a nonempty source event queue refuses.

Native/account/Peers/deadline checks surround sorted account locks and exact source pair/own-block comparison. Present own block rows are locked as well, protecting the GUI DELETE path; absent insertion is fenced by account parents/FKs. Source verbs and persisted block/pair/share postconditions are reused. Edits reread/reconfirm, replay makes one change and addressed hint, expired/withdrawn/false-source states roll back, and lost acknowledgements remain unknown. Active severance invalidates peers/relations/workboard; other directional-block changes refresh peers alone. No private work contents or invented release counts are emitted. The existing source field set has an addition guard. Six-language notes and progress are wired; literal hostile identity is escaped by the actual HTML card and never reaches the editor with private proofs.

Evidence: five initial real SQL cases pass; 28 initial SQL/HITL/registry/structural cases pass; the expanded boundary/HITL set passes 19, then 30 including six-locale contracts and forbidden-grant restoration. Final independent fence/native/source Workboard review passes 39. Two independently committed PostgreSQL probes have distinct PIDs and positive lock controls, and prove GUI block creation and own-block deletion wait on native fences. The broader native/Peers/structural/CC suite passes 1430, strict MyPy passes ten owners, Black/Ruff and six-language parity pass. New/touched native functions remain below the CC limit and size/cycle ratchets pass; no ceiling was raised. Existing account-owned frontend refresh is reused. The prior severance browser locale-loop qualification remains open for final runtime work; no browser/physical-device/paid-provider/production/full Pipeline/ReAct pass is claimed here. Nonadmin image sharing and remaining interface coverage continue; administration has not started.
### Lot 114 — Partage confirmé d’une image générée (implémenté, revu)

- Réutilisation du parcours `peers/image_share.py` : contrôles d’appartenance, connexion acceptée sans blocage, image générée active, copie physique, galerie, registre de partages et quotas journaliers sérialisés. `find_generated_files_tool` fournit déjà les identifiants des fichiers ; aucun second moteur de recherche créé.
- Nouvelle opération `peer_image.share` et tool `share_lia_peer_image_tool` : préparation sans copie ; identité réelle, commentaire littéral et image sélectionnée affichés ; empreinte privée de la paire, de toute la ligne pièce jointe et des octets. Registres natifs/manifests/imports/exécution/édition/prévisualisation/invalidation/progress raccordés, `draft` obligatoire, hors initiatives et réservé au compte courant.
- Factorisation des cinq propositions Connexions antérieures et de la nouvelle dans `peer_tool_preparation.py`, avec paramètres génériques stricts et maintien des sessions injectables. Les règles métier demeurent dans leurs préparateurs. Le parcours natif utilise son registre d’effets : il ne crée pas une seconde action synthétique de clic via `recorded_action`.
- Revue inline à froid : comptes et paire dans l’ordre canonique, pièce jointe verrouillée, comparaison avant copie et avant sauvegarde ; contrôles actuels capacité native/Peers/compte/deadline ; vérification SQL des véritables lignes copie et partage, du destinataire, métadonnées, chemin confiné, expiry et octets copiés. Pas de réseau avant commit. La notification reprend le service source après ACK et les verrous sont alors libérés.
- Correctifs issus de la revue : commit ambigu ou annulé conserve le fichier qui peut appartenir à une galerie déjà sauvegardée ; statut `COMPLETION_UNKNOWN`, aucune livraison ni répétition automatique. Une copie annulée attend son worker disque avant de nettoyer. Refus après copie et avant commit retire le fichier. Les chemins sortant du stockage sont refusés. Le statut Attachment source est une constante str, pas une enum : erreur détectée par tests SQL et MyPy, corrigée sans assouplissement.
- TDD initial : échec de collecte attendu pour le module natif absent (`peer-image-red.log`). Premier nominal/source : 27 succès. Vrais flux HITL/édition/replay et régression des cinq anciens outils plus smoke registry : 60 succès. Revue SQL/source/quota/cancel/privacité : 46 succès ; dernières vérifications après corrections finales : 27 succès (`peer-image-closed.log`), dont transactions indépendantes avec PIDs distincts, contrôle positif NOWAIT et attente effective d’un delete d’image/blocage ; lecteur de notification voit la copie engagée et les comptes déverrouillés.
- Tests natifs/Peers/tailles/cycles : 1427 succès. MyPy strict 15 fichiers puis les trois propriétaires modifiés en dernier : succès ; notes de sections MyPy inutilisées préexistantes. Black/Ruff : succès. Backend CC : aucune nouvelle fonction >=15, agrégat 291/max78 inchangé ; parité six locales : succès. Dialogues source frontend : 16 succès (premier lancement sandbox EPERM avant tests, relance autorisée locale réussie).
- Pas de modèle appelé par le partage ; coûts LLM restent ceux des tours de proposition/réponse existants. Commentaire et titre échappés par le vrai renderer HTML en six langues ; les empreintes/chemins n’entrent pas dans le prompt d’édition. Aucun nouveau layout mobile.
- Limites explicites : livraison externe remplacée par un résultat contrôlé dans ces tests ; parcours application Pipeline/ReAct, navigateur et appareils réels restent à la qualification finale. En absence d’ACK, le résultat reste indéterminé et la copie potentielle est conservée : aucun succès fictif ni cleanup destructeur déduit de l’erreur réseau. La qualification navigateur du lot 112 reste ouverte (boucle locale de redirections, voir son journal).
### Lot 115 — Lecture native du Workboard (implémentée, revue)

- `workboard_ui.read` / `get_lia_workboard_tool` complète les lecteurs compacts existants par les DTO de l’interface : résumé/caps/coûts/tokens/runs, tableau filtré et totaux exacts, besoins d’intervention, ligne de ticket, enfants, commentaires et événements paginés séparément. Aucun write ni modèle.
- Réutilisation des enums, DTO, predicates d’accès, filtres et services Workboard. `limit<=50`, ordres source terminés par UUID, continuations explicites ; le résumé reprend les caps d’instance réels. Les pages sont des observations vivantes, pas un export figé. Historiques séparés pour ne pas charger tous les commentaires/événements ; refus intégral d’un payload dépassant la borne, sans couper un contenu.
- Pré/post contrôles natifs, compte et Workboard ; relecture de visibilité de la page ou du ticket parent après fetch. Une réaffectation qui retire l’accès avant projection est refusée. Freshness `populate_existing` sur les lectures traversées : test SQL d’une ligne déjà présente en identity-map puis modifiée directement.
- Revue inline à froid : droits propres/assignés du service source, neutralité des ids étrangers, filtres sans wildcard involontaire (`100% _literal_`), date avec timezone explicite, paramètres incompatibles refusés, texte tiers conservé littéralement et soumis au wrapper external-content habituel ; pas de nouveau contexte persistant. Raccords allowlist/opération/manifest/import/progress avec capacité WORKBOARD et read/initiative-off.
- Factorisation source : `detail_queries.py` porte les trois collections ordonnées et leur frontière commune de pagination/fraîcheur. Les méthodes publiques du repository gardent leurs signatures compatibles et leurs défauts non paginés pour l’UI actuelle. Le premier ajout avait dépassé le plafond (611/600) ; l’extraction a corrigé la cause, sans relever ni exclure le ratchet.
- TDD module absent RED ; 11 premiers tests SQL GREEN. Revue repository/service, contrats et smoke tool registry : 77 succès. Dernier replay après factorisation, guards de taille et cas native-tool/oversize/retrait d’accès : 50 succès (`workboard-read-closed.log`). MyPy strict : six propriétaires sans erreur. Black/Ruff, CC 291/max78 et parité six locales : succès. Les notes MyPy de sections inutilisées sont préexistantes.
- Aucun changement de layout. Les flows navigateur/Pipeline/ReAct restent à la qualification globale ; les écritures Workboard existantes sont encore à convertir en confirmation systématique, et la possibilité qu’un commentaire réponde à une action en attente reste à traiter dans le lot d’écriture.
### Lot 116 — Création Workboard confirmée (implémentée, revue)

- Le tool existant `create_ticket_tool` conserve ses paramètres usuels et expose aussi `WorkboardCreateInput`, dérivé du DTO source complet. Il prépare désormais `workboard_ticket.create` sans créer de ticket avant confirmation. Aucun second créateur concurrent ; enregistrement par le domaine Workboard, inventaire natif commun et tests de parité.
- Réutilisation de la validation métier source, des réglages de caps, des résolutions exactes de parent/connexion, des dates locales historiques et du registre APPLICATION_ACTION. Prévisualisation et édition en six langues ; la carte précise que l’affectation à LIA peut lancer ultérieurement du travail soumis aux coûts/quotas habituels. Les empreintes privées ne sont jamais proposées au modèle d’édition.
- Fence partagée entre source GUI et exécution native : comptes ordonnés, paire et parent. Relecture fraîche des capacités, compte, pair actif, parent et limites ; comparaison du contexte confirmé. Identifiant déterministe de commande ; vérification SQL du véritable ticket et de chaque champ demandé avant commit. Aucun réseau avant ACK. Commit ambigu ou annulé : COMPLETION_UNKNOWN et aucun succès ni retry automatique.
- Revue adversariale inline : parent étranger neutre, retrait de connexion/capacité, parent modifié, pair inactif/supprimé, payload mélangeant deux formes, dates naïves du DTO complet, booléens coercibles, retour source mensonger et sauvegarde dont l’ACK est perdu. Contrôle de concurrence PostgreSQL indépendant avec PIDs distincts et contrôle positif NOWAIT ; la création source attend effectivement le fence natif.
- TDD : module absent RED puis sept premiers SQL GREEN. Les tests existants supposant une création immédiate ont été adaptés à la préparation et vérifient explicitement que `create` ne s’exécute pas avant confirmation. Vrais flux HITL, modification, refus et replay : 44 succès. Revue étendue : 74 succès ; régression source : 123 succès. Le premier guard de taille refusait le catalogue à 605/600 : extraction cohérente du manifeste de création, sans hausse du plafond ; guards et contrats : 58 succès. Registres/état/checkpoint/smoke : 72 succès. Dernier contrôle des dépendances et anciens tools : 46 succès (`workboard-create-closed.log`). Comptages de campagnes chevauchants, non additionnés.
- MyPy strict : onze propriétaires puis neuf modules de composition sans erreur ; Black/Ruff passent. CC agrégé 291/max78 inchangé, aucune nouvelle fonction >=15 ; parité des six locales réussie. Pas de nouveau layout ; le refresh Workboard existant est réutilisé. Aucun appel de modèle dans la création elle-même.
- Qualification navigateur/Pipeline/ReAct encore à faire globalement, dont le problème local de redirection mentionné au lot 112. Les autres écritures Workboard restent à convertir ; administrations non commencées.
### Lot 117 — Libellés identifiables du registre d’actions (implémenté, revu)

- Les actions natives étaient déjà enregistrées par l’exécuteur `draft:application_action`, mais leur libellé restait générique. Il porte maintenant le nom lisible de la capacité réellement déclarée, via `APPLICATION_OPERATIONS` et le même humaniseur que les confirmations. L’identifiant stable d’opération est conservé dans les valeurs chiffrées ; aucun catalogue supplémentaire de tools ni donnée d’intention n’est recopié.
- Revue à froid : les titres natifs source sont génériques, donc un premier ciblage par titre n’identifiait pas réellement l’opération. Correction avant fermeture : nom de capacité issu de la déclaration existante. Les anciens payloads, opérations inconnues/lectures et formes invalides restent sur le libellé historique ; aucune entrée existante réécrite. Valeur bornée par le réglage source. Pas de titre, brief, before/after, chemin ou preuve privée dans le libellé.
- TDD : trois échecs attendus avant ajout, puis neuf premiers cas réussis. Test de couverture de toutes les mutations de la registry : tout nouvel enregistrement bénéficie automatiquement du libellé. Nouvelle clé traduite côté backend et frontend en six langues, avec parité des placeholders. Premier contrôle étendu : 56 succès ; contrôle final après correctif de revue : 58 succès (`application-effect-label-closed.log`).
- PostgreSQL jetable : production `claim_request_for` en modes Pipeline et ReAct, attribution au run réel, libellé chiffré lisible via le reader commun, fermeture et replay produisant une seule ligne. Il s’agit des deux modes du registre, pas de deux conversations LLM réelles. Rejeu du waiting-effect source inclus dans la campagne antérieure à 13 succès.
- Affichage frontend existant : huit tests passent, aucun layout changé. MyPy propriétaire passe ; Black/Ruff, CC 291/max78 inchangé et parité six locales passent. Les noms de capacités restent humanisés selon la convention source existante ; les phrases qui les entourent suivent la langue du lecteur. Les effets sans ACK gardent leurs statuts existants : ce changement ne crée aucune réussite métier.
### Lot 118 — Commentaires Workboard confirmés et reprise Docker dev (implémenté, revu)

- Le tool existant `comment_ticket_tool` prépare désormais `workboard_ticket.comment` sans commentaire ni approbation avant confirmation. Le DTO hérite de `CommentCreate` ; résolution source exacte d’id/titre, corpus public courant, digest privé de la ligne complète. Source `clean_comment`, `validate_answer` et `comment_answer` sont partagés : pas de lexique natif concurrent ni de limite de runs inventée.
- Une réponse du propriétaire sur un ticket `confirming` porte la conséquence du service source : approbation du draft stocké et retour à LIA, refus/clôture, modification/abandon du draft ancien et nouveau run. L’aperçu réutilise le renderer source, single ou batch. Il s’agit de l’aperçu que l’UI source sait produire, avec ses conventions existantes ; aucune promesse nouvelle de rendu intégral des paramètres tiers. La confirmation précise coûts/quotas des runs ultérieurs ; le commentaire lui-même appelle zéro modèle/réseau. Un commentaire de pair n’expose pas l’action privée du propriétaire et n’y répond pas.
- Fence commun GUI/native : comptes acteur/propriétaire ordonnés, relecture visible puis ticket FOR UPDATE. Source refusera une délégation croisée impossible avant insertion. Commentaire natif identifié par la commande, sans modifier le défaut GUI. Les postconditions relisent la vraie ligne et la vraie réponse pending, empêchent changements de champs étrangers et faux retours source ; pas de notification sur un transfert à LIA. Commit perdu/annulé : COMPLETION_UNKNOWN, jamais retry automatique ni succès.
- Préparation factorisée des six tools Connexions et du commentaire dans `native_tool_preparation.py`, avec maintien de l’ancien export public. Édition change le texte sur le même ticket/commande et reconfirme. Manifeste/opération/allowlist/exécution/renderer/éditeur/refresh/progress existant raccordés ; policy draft, initiative-off. Le planner ne réclame pas un second HITL : `hitl_required=False` dans le manifeste, le draft exécuté exige bien sa confirmation. La borne de commentaire est publiée aussi dans le schéma réellement donné à ReAct (`tool_call_schema`).
- TDD initial module absent RED. Premiers retours ont détecté le paramètre manquant dans `add_comment` ; extension source compatible et correction. Régression SQL/service/ancien tool/registry : 80 succès. Revue SQL/HITL/edit/replay, faux retours et perte/annulation ACK, six langues/privacité, concurrence indépendante positive NOWAIT/différents PIDs : 66 succès. Contrôle final étendu : 138 succès et un test de schéma erroné (`args_schema` inclut le runtime BaseStore) ; corrigé pour lire le vrai `tool_call_schema`, campagne contrats/imports/boot suivante : 49 succès. Aucun test métier retiré. MyPy final douze propriétaires sans erreur. Black/Ruff passent ; CC revenu à 291/max78 par extraction de vérification, sans hausse de plafond ; tailles/cycles passent dans la campagne étendue et parité six locales passe.
- Incident réel 2026-10-09 Docker dev `/auth/features` : régression de ce lot, confirmée par logs. Ruff avait supprimé l’alias renommé non explicitement exporté ; il bloquait les tools Connexions puis le registre/graph. Après correction `__all__`, le guard de boot a aussi refusé le nouveau commentaire mal déclaré `draft` + `hitl_required=True`. Correction du manifeste avant reprise. Contrôles d’import/export et du guard réel ajoutés, 41 puis 13 succès de reprise. Ne pas assimiler la panne actuelle aux incidents historiques sans leurs logs.
- Qualification effective Docker après correction : API `healthy`, `/health` et `/api/v1/auth/features` HTTP 200 ; URL exacte du web `https://192.168.0.29.nip.io:8000` HTTP 200 et CORS autorisant `https://192.168.0.29.nip.io:3000`. Les sondes HTTPS utilisent le certificat local autosigné (`curl -k`) ; aucun test de confiance TLS d’appareil physique annoncé. Le proxy relatif web testé isolément répond 500, mais le frontend courant utilise l’URL API directe précitée ; ce chemin alternatif n’a pas été déclaré réparé ni masqué.
- Le chargement complet des tools et les guards réels de démarrage, après formatage, font désormais partie de chaque fermeture de lot. Pas de layout modifié. Les tours LLM applicatifs Pipeline/ReAct et les parcours navigateur restent à la qualification finale ; les autres écritures Workboard et l’inventaire utilisateur restant continuent. Administration non commencée.
### Lot 119 — Suppression Workboard confirmée et fermeture du contournement historique (implémentée, revue)

- Le tool existant `delete_ticket_tool` prépare `workboard_ticket.delete` dans APPLICATION_ACTION, sans suppression avant accord. La proposition affiche chaque ticket du sous-arbre source, titres, statuts, commentaires/historique, runs actifs et actions en attente. Digest privé des lignes complètes ; données bornées, aucun contenu pending dans l’édition. Une modification du périmètre impose une nouvelle proposition sur le même ticket, jamais un changement silencieux de cible.
- Réutilisation du service de suppression source, de la confirmation, de l’exécution, du registre d’actions et du refresh Workboard communs. Compte propriétaire exclusivement ; gardes natives/Workboard/deadline fraîches avant préparation, après fence et avant commit. Source GUI et native partagent le fence comptes/ticket ; enfants verrouillés en ordre UUID. Vérification SQL de la suppression exacte des tickets, commentaires et événements, et du total propriétaire : un faux retour ou une suppression supplémentaire est refusé et annulé.
- Revue adversariale inline : cartes historiques TICKET_DELETE sans empreinte ni commande ne peuvent prouver le nouveau consentement. Leur lecteur enregistré retourne STALE_STATE sans mutation ; demander une nouvelle proposition. TDD a reproduit la suppression par l’ancien exécuteur sur PostgreSQL jetable avant sa correction. Pas de migration inventant un consentement après coup.
- Perte ou annulation de l’ACK du commit : COMPLETION_UNKNOWN, receipt non engagé, aucun retry automatique ; tests prouvent que la suppression peut néanmoins avoir été sauvegardée. La carte précise en six langues qu’une suppression n’annule pas une action déjà en vol. Pas de modèle ni de notification externe ajoutés.
- Incidence Docker dev pendant intégration : doublons d’import et de mots-clés i18n corrigés ; pas de faute masquée par une relance frontend. Black/Ruff passent avant exécution des tests ; chargement réel des tools et guards de boot passent après formatage. API effectivement healthy et /api/v1/auth/features HTTP 200 sur l’URL frontend configurée, CORS attendu. Pas de preuve appareil/TLS physique ou navigateur annoncée.
- Validation : 49 premiers tests flux/source/anciens tools passent ; campagne adversariale initiale 104 succès et six erreurs de fixtures relisant des attributs ORM expirés après rollback. IDs capturés avant rollback, sans assouplir les assertions SQL ; campagne finale 123 succès (`workboard-delete-closed.log`), incluant HITL sans consentement/refresh/replay/retarget, droits owner/holder/id étranger, désactivation globale et Workboard, expiry/tampering, nouveaux enfants/commentaires, faux source/extra delete, ACK perdu/annulé, six langues et privacité, taille/cycles et imports/boot. Trois simulations indépendantes GUI suppression enfant/commentaire enfant/création enfant attendent le fence natif avec PIDs distincts, contrôle positif NOWAIT et SQLSTATE 55P03.
- Régression services source Workboard : 72 succès (`workboard-delete-source-regression.log`). MyPy strict douze propriétaires sans erreur ; notes de sections inutilisées préexistantes. CC 291/max78 inchangé, aucun nouveau hotspot ; Black/Ruff et parité six langues passent. Aucun plafond relevé ni périmètre exclu. Qualification globale navigateur/Pipeline/ReAct encore ouverte ; autres modifications Workboard à convertir, administrations non commencées.
### Lot 120 — Modifications Workboard, déplacements et demandes de run confirmés (implémenté, revu)

- Le tool existant `update_ticket_tool` prépare désormais `workboard_ticket.update` sous APPLICATION_ACTION. Il conserve les arguments usuels et expose le DTO source complet, exclusif avec ces arguments : mots, priorité, statut, dates et effacement explicite, affectation, suivi propre, mode, déplacement avec position, demande de run. Même agent propriétaire, manifests et registres existants ; policy draft, initiative-off, aucun second HITL planner. Exécution et refresh Workboard communs, registre d’actions identifiant l’opération.
- Prévision fondée sur le vrai service dans un savepoint PostgreSQL intégralement annulé : aucun ticket/historique modifié durablement, aucune notification envoyée. Pas de second moteur de règles métier. Source produit le résultat et les événements prévus ; empreintes privées de toute la ligne, des colonnes affectées, des connexions/prérequis et de la note propriétaire. Comparaison avant écriture, vraie ligne SQL et vrai historique comparés après écriture, y compris les rangs affectés. Horloges générées par l’acte exclues de l’égalité prédictive ; aucun horaire de modification futur présenté comme un fait sauvegardé.
- Une mise à disposition de LIA décrit du travail futur soumis aux quotas/coûts habituels, jamais un run déjà achevé. L’aperçu montre le pending source du propriétaire, la note et son classement source, approbation/refus/amendement ou abandon lors du changement de colonne. Pas de pending privé du propriétaire exposé au titulaire. Les preuves privées et événements attendus n’entrent pas dans le prompt d’édition ; l’édition reconfirme le même ticket. Html littéral échappé en six langues.
- Notifications d’affectation factorisées en snapshots source typés. Native collecte puis dispatch après ACK, sur une session distincte ; un échec SQL de notification ne peut empoisonner la mutation engagée. Avant envoi, le destinataire doit être actif et toujours titulaire ; révocation/restitution avant dispatch ne divulgue rien. Le chemin GUI par défaut conserve son dispatch existant, décrit honnêtement. Commit perdu/annulé : COMPLETION_UNKNOWN, pas de receipt ni de notification/retry présumé.
- Fence unique comptes ordonnés, paires et ticket visible, exposé par le repository pour tous les writes source. L’ancien nom commentaire est un export explicite vers la même fonction : supprime l’acquisition tardive d’un compte pair après un verrou propriétaire et son risque de deadlock. Tests indépendants update/move/comment/delete et anciens lots rejoués ; PIDs distincts, contrôle positif NOWAIT et SQLSTATE 55P03. Préparation/exécution relisent capabilities/compte/deadline, prospective identité non connectée/inactive neutre ; un titulaire ne réécrit pas les mots du propriétaire. Un propriétaire peut restituer un ticket à son propre compte même si Peers est arrêté.
- Factorisations : parsing legacy noms/dates partagé avec création ; projection sûre des quatre requêtes Workboard extraite de prompts.py après détection 611/600, sans hausse du plafond. Le builder Source TicketUpdate corrige une anomalie GUI vérifiée : assignee_user_id:null explicite, envoyé par « rendre le ticket », était ignoré. Normalisation commune vers assignee=me ; les champs absents restent inchangés et l’édition omet leurs nulls. TDD PostgreSQL deux échecs avant correction, puis sept cas owner/holder/null/capacité passent.
- Revue inline à froid et corrections : déclaration ParameterSchema est une dataclass, pas un modèle Pydantic ; l’usage de model_copy refusé par le boot a été remplacé par dataclasses.replace. Imports/guard réel 42 succès après correction. Les fixtures source stubaient le SQL au mauvais niveau et les destinataires avec des namespaces incomplets ; repository conservé comme port et vrais modèles transitoires User/Ticket dans les TU. Oracles métier préservés, aucune nouvelle ignore ni réduction de seuil. Les trois anciens tests de mutation immédiate ont été remplacés par les vrais parcours SQL/HITL démontrant omission des champs, run après confirmation et absence de double mutation ; le test du helper mort _optional, miroir d’implémentation, a été retiré avec le helper.
- Validations : source/boot initial 102 succès ; noyau initial six SQL ; intégration et guards 121 succès après correction du boot et de taille ; adversarial/pending/HITL 23 succès ; frontières notices/SQL et contrats stricts/six langues 22 succès ; anciens contrats unitaires 131 succès ; anciennes fences/natif/tailles/cycles 71 succès ; null partagé et flux 154 succès. Campagne de fermeture actuelle 1980 succès (`workboard-update-closed.log`), couvrant tous les TU application/workboard et SQL source+nouveaux flux+gardes. Comptages chevauchants non additionnés. MyPy strict vingt propriétaires sans erreur, notes de sections inutilisées préexistantes ; Black/Ruff, CC 291/max78 inchangé et parité six langues passent.
- Docker dev qualifié de nouveau : API healthy, URL API réelle de /api/v1/auth/features HTTP 200 avec Origin frontend ; sondes curl -k sur certificat local. Rechargements automatiques ont interrompu des requêtes pendant l’intégration ; aucune panne masquée par une modification de useAuthFeatures ni un succès navigateur/appareil annoncé. Parcours applicatifs LLM Pipeline/ReAct et navigateur/mobile restent à la qualification globale. Administration non commencée, inventaire nonadmin restant continue ; vérifier aussi les lecteurs compacts Workboard sous la désactivation générale.
### Lot 121 — Anciens lecteurs Workboard et révocation actuelle (implémenté, revu)

- `get_ticket_tool` et `list_tickets_tool` rejoignent les alias du bouton APPLICATION_TOOLS ; les six tools Workboard sont désormais dans son inventaire. Les lecteurs compacts utilisent la même autorité fraîche native/Workboard/compte avant et après lecture. Aucun registre ni payload métier n'est publié si cette autorité est retirée.
- Revue adversariale inline : les anciens lecteurs pouvaient restituer un ticket dont l'affectation venait d'être retirée après fetch. Deux simulations PostgreSQL d'un vrai titulaire pair ont reproduit la fuite avant correction ; les deux simulations de compte désactivé passaient déjà. Relecture neutre du ticket ou COUNT de visibilité sur tous les ids de la page avant publication, sans N+1.
- Factorisation des lectures Source dans `detail_queries` : détail frais et COUNT partagent le predicate existant ; le lecteur natif du lot 115 réutilise le même port. Le repository reste sous son plafond, sans hausse ni exclusion. Contrats CURRENT/LIST, filtres et totaux Source conservés.
- TDD global initial : cinq échecs et deux succès ; TDD révocation : deux échecs et deux succès. Fermeture après factorisation : 126 succès (`workboard-read-closed-121.log`), incluant SQL natif/ancien/Source, anciens contrats, vrais imports et guards de démarrage, discovery, tailles et cycles. MyPy strict cinq propriétaires sans erreur ; Black/Ruff passent. CC 291/max78 inchangé ; aucun ratchet relevé.
- Docker dev réel : API healthy, `/api/v1/auth/features` HTTP 200 sur localhost et sur l'URL nip.io configurée, CORS avec credentials pour l'origine web. Un probe pendant le rechargement avait expiré ; le contrôle suivant a réussi. Certificat local testé avec curl -k : pas une preuve de confiance TLS sur l'appareil ni un test du navigateur.
- Les qualifications applicatives globales et l'inventaire utilisateur restant se poursuivent ; aucune action administrateur commencée.

### Lot 122 — Lecture des espaces de connaissance (implémenté, revu)

- `knowledge_spaces.read` / `get_lia_knowledge_spaces_tool` lit cinq sections finies de l'UI source : espaces, métadonnées d'un espace précis, documents, dossiers Drive liés et labels Gmail liés. DTO source conservés (activation, kind géré, statuts, compteurs, dates, embeddings/tokens/coûts). Espaces désactivés inclus ; espaces étrangers/système refusés même pour un administrateur utilisant ce lecteur personnel.
- Requêtes Source `rag_spaces/ui_queries` bornées, paginées séparément, ordre terminé par UUID, total global exact et continuation explicite. La page des espaces et toutes ses statistiques utilisent deux SELECT quelle que soit sa longueur : contrôle SQL instrumenté avec treize espaces. Le lecteur ne réplique aucun créateur, upload, indexation ou synchronisation. Aucun appel de fournisseur/modèle ni accès aux corps de documents.
- Autorité fraîche native/RAG/compte avant et après fetch ; COUNT des parents observés après lecture pour refuser une propriété révoquée, même si l'identity-map contient encore l'ancienne ligne. Page dépassant la borne UTF-8 refusée intégralement, jamais coupée. Paramètres stricts, inconnus/sections incompatibles/valeurs booléennes-coercibles refusés. Pas de nouvel état persistant ni registre de données privé.
- Revue adversariale : les diagnostics bruts source contiennent parfois str(exception) et peuvent donc transporter secrets fournisseur ou chemins internes. Trois tests SQL ont reproduit leur divulgation avant protection ; la projection native masque error_message et annonce technical_diagnostics_withheld, conserve status/error_code et laisse les données SQL support intactes. Les noms/descriptions passent dans le wrapper external-content standard ; test sur le vrai tool enregistré.
- Registres opération/manifest/import/allowlist et progress six langues raccordés, initiative-off et read. La sous-capacité RAG passe par required_capabilities et la discovery native existante, sans double déclaration de tool dans le registre général : les guards existants refusent cette duplication. Tests de discovery/leaf concordants pour enabled, arrêt native, arrêt RAG et compte inactif. Guard explicite des champs des quatre DTO source : une nouvelle exposition exige une revue.
- TDD initial module absent RED ; dix premiers SQL GREEN. Trois tests de diagnostic RED puis GREEN. Contrats Source et guards intermédiaires : 141 succès. Fermeture actuelle : 85 succès (`space-read-final-122.log`), incluant droits/fraîcheur/pagination/diagnostics, vrai tool/discovery/imports, taille/cycles et capacité. Comptages non additionnés. MyPy strict neuf propriétaires sans erreur (`space-read-closed-mypy-122.log`), Black/Ruff, CC 291/max78 et parité six langues passent ; aucun ratchet relevé.
- API Docker dev healthy et /auth/features HTTP 200 sur localhost après raccordement. Pas de nouvelle UI ni de qualification physique du navigateur. Les mutations d'espaces, les autres surfaces utilisateur restantes et la qualification globale se poursuivent. Administration non commencée.

### Lot 123 — Création d'espace confirmée (implémenté, revu)

- `knowledge_space.create` / `create_lia_knowledge_space_tool` prépare un APPLICATION_ACTION durable pour un espace personnel vide et actif. Le DTO hérite des deux champs Source RAGSpaceCreate ; le schema de requête identique est offert aux deux modes. Native/RAG/compte fraîchement vérifiés, quota et nom unique relus. Scope avant/après exact, quota courant et compte après création ; aucune création, document, indexation ou fournisseur avant confirmation.
- Source RAGSpaceService expose sa normalisation/validation de création commune et une insertion non engagée avec id déterministe de commande. GUI et native prennent le même verrou User pour serialiser le quota. GUI conserve le commit par défaut ; native vérifie la vraie ligne, les champs, l'espace vide/actif, le compte et le nombre exact d'insertions puis engage. Les gauges Source sont publiées après ACK. ACK perdu ou annulé : COMPLETION_UNKNOWN sans receipt présumé ni retry automatique.
- Normalisation Source du nom avant vérification des longueurs : les noms entièrement blancs ou d'un seul caractère normalisé sont rejetés par l'API et le tool. La description conserve le comportement Source. Les TU Source continuent de vérifier les règles métier et stubbent le nouveau port de verrou ; sa réalité est éprouvée sur PostgreSQL indépendant, PIDs distincts, contrôle positif NOWAIT et SQLSTATE 55P03.
- Registres opération/manifest/allowlist/import/exécution/édition/canonical/notes/champs/ressources raccordés ; previews et progrès six langues. Le vrai dispatcher HITL refuse l'absence de confirmation, édite la même commande et rejoue sans deuxième espace ni deuxième entrée AgentEffect. Une seule notification SSE de ressource spaces. L'édition ne voit que nom/descriptif : aucun compteur, actor_id ni command_id.
- Frontend : la liste, le détail et l'indicateur d'espaces actifs réutilisent les queries à durée de vie propriétaire et le refresh partagé. Anciennes données/callbacks rejetés au changement de compte ; invalidation étrangère ignorée, détail sans sélection non rafraîchi, ancienne identité de détail masquée. Les mutations Source gardent leurs updates optimistes ; un refresh de liste ne remet pas loading au premier chargement ni ne démonte l'écran pendant l'édition.
- Revue inline : résultat Source absent ou champ erroné refusés et rollback ; quota devenu obsolète et arrêt de capacité refusés ; deux formes d'ACK ambigu éprouvées. La première fixture HITL ouvrait le registre d'effets hors de sa transaction contrôlée : raccord du get_db_context à la même base jetable, sans affaiblir l'oracle. Un ajout à la projection d'édition portait une fonction existante à CC15 et créait une collision de variable typée ; composition management_editor_inputs corrige les causes, CC291/max78 rétabli sans hausse de ratchet. Aucun nouveau cycle ni cap de taille dépassé.
- TDD module absent RED, cinq noyaux SQL et anciens contrats Source : 65 succès. Flux HITL/fence : cinq succès après réparation de fixture. Contrats stricts/six langues/tailles/cycles : 25 succès. Fermeture Source+native+lectures+guards : 167 succès (`space-create-closed-123.log`), puis treize contrats après StrictInt sur les observations. Front TDD deux échecs, puis dix succès ; fermeture Source/SSE/compte/refresh trente succès (`space-create-front-closed-123.log`). TypeScript non-incrémental et ESLint passent. MyPy strict dix-neuf propriétaires sans erreur (`space-create-closed-mypy-123.log`), Black/Ruff et parité six langues passent. Comptages chevauchants non additionnés.
- Incident Docker requalifié : API healthy et HTTP200 localhost/nip.io. Lecture rejouée dans l'onglet Chrome réel, section Authentification forte chargée et aucun échec /auth/features capturé ; logs serveur du même contrôle HTTP200. Aucun réglage de sécurité changé, onglet remis sur les réglages initiaux. Une navigation directe d'un onglet de diagnostic vers l'API avait été bloquée par le client ; aucune protection navigateur contournée. Cela ne vaut pas qualification mobile ou confirmation de toutes les plateformes.
- Les autres mutations d'espaces/document/sources et surfaces utilisateur restantes ainsi que la qualification globale se poursuivent ; aucune administration commencée.

### Lot 124 — Modification et activation d'espace confirmées (implémenté, revu)

- `knowledge_space.update` / `update_lia_knowledge_space_tool` regroupe le nom, le descriptif et l'état actif souhaité d'un espace personnel exact. Héritage du DTO Source RAGSpaceUpdate, strict bool pour l'activation ; null signifie omis, vide/blanc efface le descriptif. Les espaces personnels gérés restent renommables et activables ; aucune identité système ou étrangère exposée.
- Source GUI et native partagent le verrou compte actif puis espace propriétaire. L'écriture source peut différer le commit et ses gauges ; native compare le snapshot complet privé avant écriture, puis la ligne résultante entière, avec seule exception de l'horodatage automatique updated_at. Aucun état technique privé n'entre dans le prompt d'édition. Aucun fournisseur, document ou index modifié.
- Opérations, manifestes, allowlist, exécuteur, éditeur, canonical, notes et ressource spaces raccordés. Une édition conserve la cible et la commande ; les requêtes front du lot 123 réutilisent le même événement. Copies et progrès dans six langues, sans nouvelle UI.
- Revue adversariale inline : un faux résultat Source, un champ hors consentement, un snapshot modifié et une capacité coupée sont refusés. Le test du champ created_at non approuvé était RED avant renforcement de la postcondition. ACK perdu/annulé après commit réel produit COMPLETION_UNKNOWN sans receipt de réussite ni retry automatique. État identique : no-op sans appel au writer Source. Identités système/étrangère refusées.
- Premier socle Source et noyau : 66 succès ; campagne complète Source+HITL+fences+contrats : 93 succès. Fermeture avec les cas de revue et gardes de registres/imports à froid/tailles/cycles : 69 succès (`space-update-closed-124.log`). Comptages chevauchants non additionnés. GUI rename/toggle/delete indépendants bloqués sur le fence native, PIDs distincts, contrôle positif et SQLSTATE 55P03. Le vrai dispatcher HITL exige la confirmation, édite la même cible et rejoue sans deuxième AgentEffect ni deuxième refresh SSE.
- MyPy strict dix-huit propriétaires sans erreur (`space-update-mypy-closed-124.log`), Black/Ruff, parité six langues et CC291/max78 passent. Aucun plafond relevé ; aucun gain de dette mesuré nécessitant une nouvelle baseline. API Docker healthy et /auth/features HTTP200 sur localhost et nip.io après les écritures ; une sonde pendant le reload était indisponible puis les deux lectures ont réussi. Qualification globale navigateur/mobile et parcours LLM encore à réaliser. Administration non commencée.

### Lot 125 — Suppression d'espace personnel confirmée (implémenté, revu)

- `knowledge_space.delete` / `delete_lia_knowledge_space_tool` nomme l'espace, tous les documents, le nombre de chunks et les liens Drive/Gmail locaux dans une confirmation APPLICATION_ACTION. Espaces système/étrangers exclus ; les espaces gérés meetings/bookmarks conservent la protection Source. Les originaux Drive et les messages Gmail restent. Indexation/synchronisation active : refus BUSY avant les verrous enfants et nouvelle demande après sa fin.
- Snapshot privé complet de cinq tables hashé en streaming, une ligne à la fois, jamais transmis aux prompts ; preview entière bornée, sans coupure. Native/RAG/compte frais avant préparation et avant commit. Verrou compte/espace puis sources/documents ; relecture après fences. Aucun verrou chunk avant contrôle de l'état désormais verrouillé, pour ne pas inverser l'ordre d'un worker d'indexation. Vérification SQL de la vraie disparition de la racine et de chaque cascade, avec compte exact des autres espaces.
- Source GUI et native partagent la suppression en base, commit différable et effets après ACK. Nettoyage du répertoire exact hors boucle async, après commit seulement ; liens symboliques et redirections de type junction refusés. Un nettoyage échoué/annulé est explicitement file_cleanup_pending, sans perdre la suppression déjà engagée ni relancer le writer. ACK perdu/annulé au commit : COMPLETION_UNKNOWN, fichiers conservés, aucun receipt présumé. L'upload GUI prend le fence propriétaire avant toute lecture du fichier/écriture disque et sérialise son quota.
- Frontière commune prepare_native_tool renforcée pour produire des refus finis sur CommandRejected et erreurs Source, avec code de dépendance pour les erreurs serveur. Aucun diagnostic Source brut, secret ou chemin retourné. Registres opération/manifest/allowlist/exécution/édition/canonical/notes/champs et ressource spaces raccordés ; copies et progrès six langues. Édition garde la cible et la commande ; vrai HITL/registre AgentEffect/replay/SSE éprouvés, sans doublon.
- TDD absence du module RED puis 68 succès Source+noyau ; cinq flux HITL. Campagne complète : 91 succès (`space-delete-complete-125.log`). Revue froide anciens tools/fences de qualité/imports : 50 succès (`space-delete-cold-125.log`). Fermeture avec création/modification et cas de revue : 51 succès (`space-delete-closed-125.log`). Annulation de nettoyage ajoutée RED puis cinq succès ciblés (`space-delete-cleanup-last-125.log`). Comptages chevauchants non additionnés. Deux sessions PostgreSQL distinctes, contrôle positif et SQLSTATE 55P03 sur le vrai claim d'indexation et le vrai upload GUI. Symlink réel et comportement junction simulé sur ce même répertoire lié réussissent ici, aucun skip.
- MyPy strict treize propriétaires sans erreur puis dernier noyau sans erreur ; Black/Ruff, six langues, CC291/max78, tailles/cycles et gardes de mutation-policy passent, sans plafond relevé ni baseline artificielle. Docker révèle les reloads causés par les écritures Source, aucun nouvel échec d'import ; une fois stabilisé API healthy et /auth/features HTTP200 sur nip.io. Les autres actions de documents/sources, surfaces utilisateur restantes et qualification globale se poursuivent. Administration non commencée.

### Lot 126 — Catalogue de documents du composeur (implémenté, revu)

- Extension du reader existant get_lia_knowledge_spaces_tool avec la section attachable_documents, sans nouvel outil. Documents prêts de tous les espaces personnels, actifs ou inactifs ; nom/activation de l'espace, métadonnées publiques, recherche de nom q et pagination avec total exact. Aucune attache ni effet déclenché, aucun document brut/path/secret transmis, aucun fournisseur appelé.
- DTO et projection déplacés dans document_catalogue, partagés avec GET /rag-spaces/documents ; réexports publics du router préservés, limites API existantes conservées. La requête Source exclut explicitement les espaces système, même en cas de propriétaire incohérent, et rafraîchit document et parent depuis SQL. Le reader garde ses fences Native/RAG/compte, son contrôle final des propriétaires et sa borne de réponse entière.
- TDD deux cas RED avant extension, puis 45 succès Source/reader/contrats ; fermeture 58 succès (`space-catalogue-closed-126.log`) avec SourceOwner système incohérent, recherche % littérale, noms/activation relus depuis SQL, gardes DTO nouveaux champs/paramètres/tailles/cycles et anciens contrats. Sept imports/policy à froid réussissent (`space-catalogue-cold-126.log`). Comptages non additionnés.
- Une branche ajoutée portait la complexité à 292 fonctions au seuil ; extraction cohérente des quatre lectures d'espace exact rétablit CC291/max78. Aucun relèvement de ratchet, aucun gain de dette artificiellement déclaré. MyPy six propriétaires puis trois après découpage sans erreur ; Black/Ruff passent. API Docker healthy et /auth/features HTTP200 sur nip.io après stabilisation. Les actions de documents/sources et les autres surfaces utilisateur se poursuivent ; administration non commencée.

### Lot 127 — Téléchargement confirmé d'un document (implémenté, revu)

- `knowledge_document.download` / `download_lia_knowledge_document_tool` prépare une confirmation avec deux vrais ids propriétaires. Métadonnées et identité du descripteur Source scellées ; aucun octet ni chemin de stockage dans le prompt. Le navigateur d'origine demande ensuite un transfert unique avec les fences Native/RAG/compte/session/expiration. Les comparaisons privées restent hors preview et éditeur. Aucun fournisseur ni indexation déclenché.
- Primitive LocalFileRead partagée : ouverture d'un fichier régulier, lecture bornée et fermeture à travers annulations/IO en attente. Copie temporaire bornée créée après approbation, identité vérifiée pendant copie ; les octets de la réponse restent stables si l'original est réécrit ensuite. Source reprend ses règles de propriété/chemin et ajoute des snapshots frais. Fichier absent, propriétaire étranger et chemin corrompu sont des refus finis. StoredFileResponse force attachment/no-store/nosniff, nom UTF-8 encodé, MIME contrôlé et fermeture sur chaque sortie ASGI.
- Continuation utilise le même claim/settlement et registre d'effets que les exports. Confirmation seule laisse WAITING sans transfert. Le résultat dit download_requested et save_confirmed=false, y compris sur déconnexion du client ; un replay ne crée pas d'effet supplémentaire. Édition reobserve la même cible et conserve la commande. Opération, manifeste, allowlist, outil, édition/canonical/notes et endpoint raccordés ; les notes et progrès sont dans six langues.
- Factorisation HTTP des trois portes de téléchargement ; refus métier CommandRejected classé avant son parent ValueError, erreurs de dépendance/validation assainies et no-store. TDD quatre défauts sur six cas existants, puis neuf refus réussis. La préparation native commune capture automatiquement l'origine pour les seuls specs déclarant une interaction : le nouveau flow avait prouvé SESSION_UNAVAILABLE, corrigé sans imposer de liaison de navigateur aux simples actions.
- Front : une déclaration associe titre et endpoint, carte/règles de durée de vie compte/protection du deuxième clic réutilisées. Un op non déclaré n'obtient pas de lien. Le document passe par document-download ; les exports existants gardent leur endpoint. TDD un défaut puis dix tests réussis ; ESLint et TypeScript non-incrémental passent (`document-download-tsc-127.log`). Aucun nouveau layout ni preuve physique mobile revendiquée.
- TDD module absent puis deux noyaux SQL réussis. Primitive IO trois RED puis trois succès, dont fuite de descripteur et source modifiée. Flux complet sept scénarios : confirmation manquante, autre session, deux capacités arrêtées, fichier changé, octets figés et client déconnecté. Le test initial attendait OSError alors que Starlette le transforme en ClientDisconnect : oracle aligné sur le framework réel, sans changer le comportement. Campagne Source+actions existantes+contrats : 42 succès (`document-download-complete-127.log`), fermeture SQL/ASGI/anciens endpoints/six langues/IO : 46 succès (`document-download-closed-127.log`). Dix-neuf imports/policy/tailles/cycles réussissent (`document-download-cold-127.log`). Comptages non additionnés.
- MyPy strict quatorze propriétaires sans erreur (`document-download-mypy-closed-127.log`), Black/Ruff, parité six langues, CC291/max78 et diff-check passent ; aucun plafond relevé. API Docker healthy et /auth/features HTTP200 sur nip.io après les écritures. Les archives/actions de documents/sources et surfaces utilisateur restantes se poursuivent. Qualification globale LLM/navigateur/mobile encore ouverte ; administration non commencée.

### Lot 128 — Archives ZIP de documents avec confirmation et continuation partagée (implémenté, revu)

- `knowledge_documents.archive` / `download_lia_knowledge_archive_tool` sélectionne des ids réels d’un seul espace personnel, dans la borne batch source. La proposition nomme chaque original, le membre ZIP réellement utilisé, sa taille et son absence éventuelle. Aucune lecture du contenu ni création de ZIP avant accord ; identités de fichiers et empreintes complètes des lignes restent privées. Consentement entier borné, jamais tronqué ; aucune indexation, aucun modèle/provider ni dépense nouvelle sur cette action locale.
- Lecture source constante : deux requêtes SQL, même avec plusieurs documents, mêmes règles owner/non-system et identité ORM rafraîchie. ZIP après confirmation depuis des descripteurs vérifiés puis copies locales figées et bornées ; fichiers absents listés dans `_missing.txt`. Les données manquantes apparues ou les métadonnées modifiées depuis la proposition exigent une nouvelle confirmation. La mémoire et le disque suivent la borne source ; copies spoulées, chunks bornés et compression hors boucle pour les données volumineuses.
- Correctif source partagé GUI/native : noms d’entrées plats et portables, séparateurs/chemins/contrôles/ADS Windows retirés, noms réservés protégés, unicité insensible à la casse et nom du bilan réservé. Les premiers tests non escaladés Windows n’avaient pas terminé avant le correctif ; contrôle comparatif de l’algorithme original dans un processus isolé : sept échecs et deux succès, puis les neuf réussissent avec le correctif. Aucun retour du source Docker à l’algorithme vulnérable pour cette preuve.
- Factorisation du téléchargement individuel et ZIP dans `stored_download_service.py` : même claim HITL, session originale, gardes fraîches, expiration, commit et journal d’actions. Routes HTTP et carte responsive existantes réutilisées ; endpoint ZIP dédié, usage unique, no-store/nosniff, libellés six langues. Le résultat dit téléchargement demandé, jamais fichier reçu/enregistré. Perte/annulation d’ACK : COMPLETION_UNKNOWN, sans retry ni seconde action.
- Revue à froid : fermeture multiple interrompue reproduite RED, puis `AsyncExitStack` ferme tous les descripteurs même si un autre close est annulé. Test d’édition réelle a trouvé l’origine omise lors du remplacement de commande (individuel et ZIP) ; origine désormais transmise, même commande/cible, consentement actualisé et retarget refusé. Une simulation d’ACK perdait chaque commit, y compris le règlement ; corrigée pour perdre un seul ACK, sans changer l’oracle métier.
- Nouveau garde : toute mutation RAG/Workboard déclarée doit posséder son éditeur sûr et son modèle de dispatch. Le fichier de prompts dépassait son plafond de trois SLOC ; modèles regroupés dans les helpers existants, dispatch commun, sans plafond relevé. Contrats d’édition Workboard/espaces/documents revalidés. CC291/max78, tailles/cycles, Ruff/Black, parité six langues et diff-check passent. Aucun gain de ratchet inventé ni dette exclue.
- Validation : premiers 54 backend/11 frontend réussis ; contrôle consolidé source/flux/HTTP/ZIP/IO : 112 succès (`document-archive-closed-128.log`). Dernière revue après correctifs d’édition/fermeture et extraction : 132 succès (`document-archive-final-128.log`), incluant refus sans accord, session différente, désactivation, fichier modifié, missing devenu présent, propriétaire étranger/system, taille excessive, écriture interrompue, déconnexion, ACK perdu/annulé, édition/replay et privacité six langues. MyPy treize propriétaires et deltas de revue sans erreur ; ESLint et tsc non incrémental passent. Les campagnes se recouvrent, leurs nombres ne s’additionnent pas.
- Incident Docker signalé à 08:31 UTC revérifié sur les logs conservés : échec réel d’import `prepare_peer_tool`, corrigé au lot118. Nouvelle vérification du parcours Chrome Réglages > Authentification forte : chargé, aucune nouvelle erreur `/auth/features`, réponses API200 corrélées. Treize tests auth/import/policy passent. Après les derniers changements de ce lot : API healthy, endpoint exact nip.io HTTP200. La sonde curl utilise le certificat local autosigné ; la preuve de navigateur ne contourne aucun interstitiel. Aucun réglage de sécurité modifié.
- Qualification globale LLM Pipeline/ReAct, navigateur de téléchargement/mobile et autres actions documents/sources/utilisateur restent ouvertes. Administration non commencée, pause conservée avant ce second périmètre.

### Lot 129 — Port source de suppression documentaire transactionnelle (implémenté, revu)

- `RAGSpaceService.delete_document` accepte désormais le même mode interne `commit=False` que les espaces : suppression des chunks et de la ligne dans la transaction du caller, sans commit, fichier supprimé, compteur publié ni log de réussite avant ACK. Le défaut GUI et les refus source owner/space/bookmark sont conservés. Ce socle prépare le raccordement HITL documents ; il ne constitue pas encore le tool de suppression.
- TDD sur PostgreSQL jetable : TypeError attendu avant ajout du paramètre ; puis vrai document et vrai chunk supprimés dans la transaction, fichiers conservés, documents/chunks voisins intacts, rollback restaurant les deux lignes. Contrôle des deux repositories : aucun commit caché dans leurs méthodes de suppression.
- Revue à froid proportionnée : aucun flag ni champ de requête HTTP/LLM ajouté, aucun droit nouveau, aucun provider/LLM ou traitement de fichier en mode différé. Le caller reste responsable du fence, du périmètre exact, des postconditions, de l’ACK, de la fermeture du registre et du nettoyage physique ultérieur. Aucun succès natif annoncé à ce stade.
- Validation initiale source + guard de taille : 101 succès ; après renforcement du scénario réel chunks/voisins/rollback : 92 succès (`document-delete-boundary-closed-129.log`), campagnes recouvrantes. MyPy propriétaire, Black/Ruff et diff-check passent ; CC291/max78 et plafond de taille inchangés. API Docker healthy et endpoint exact `/auth/features` nip.io HTTP200 après modification. Aucun frontend, schéma persistant ou plafond de ratchet changé.

### Lot 130 — Suppression confirmée de documents sélectionnés (implémenté, revu)

- `knowledge_documents.delete` / `delete_lia_knowledge_documents_tool` couvre une sélection exacte d'identités réelles dans un espace personnel, avec le plafond Source. Aperçu entier : espace, chaque nom/statut/origine/taille et compte exact des fragments. Consentement obligatoire dans les deux modes ; préparation sans effet. Espaces système/étrangers et projections de réponses conservées refusés ; traitement ou synchronisation liés en cours refusés BUSY. La sélection doit être entièrement admissible ; les exclusions sont traitées en lecture avant un nouveau projet, jamais supprimées silencieusement de l'accord. Supprimer une projection Drive/Gmail/réunion ne délie aucune source et peut être suivi d'une recréation par synchronisation.
- Témoins privés de toutes les colonnes documents/fragments, streaming borné par ligne, identité des fichiers ouverts et compte de voisinage : jamais transmis au modèle d'édition ni aux cartes. Relecture fraîche sous verrous compte/espace/sources/documents et droits/capacités/délai revérifiés avant commit. Source supprime lignes/fragments, postcondition vérifie la disparition exacte et le compte des voisins. ACK perdu/annulé : COMPLETION_UNKNOWN, aucun nettoyage anticipé ni succès ou retry inventé. Après ACK, nettoyage des seuls anciens fichiers, chemins sortants et fichiers modifiés refusés ; échec/annulation annoncé file_cleanup_pending sans répéter les effets SQL. Fichier déjà absent admis.
- Revue adversariale inline : le premier vrai flux HITL a révélé un événement changed_fields vide après suppression réussie. Enum raccordée au schéma strict et au publisher ; garde général de tous les champs ACTION dans le registre, avec l'unique projection journal_configuration -> journal_entry vérifiée dans la source. Confirmation/édition conserve la même sélection et commande ; retargeting refusé. Replay : un seul AgentEffect et un seul refresh SSE spaces. Ce garde complète le garde de dispatch d'édition sûre du lot128.
- Revue performance : boucle Source par document remplacée par un port transactionnel Source groupé, règle de projection protégée factorisée avec la suppression GUI individuelle. Deux lectures et deux suppressions SQL quel que soit le lot ; test réel pour un et dix documents, rollback et refus avant toute écriture. Test rouge méthode absente avant implémentation. Le SAVEPOINT de la fixture est compté séparément des quatre requêtes métier. Parcours GUI existants conservés. Aucun provider/LLM ou indexation appelé, aucun remboursement d'usage passé.
- Tests réels PostgreSQL jetable : suppression de deux documents/fragments et conservation des voisins, renommage/chunk/fichier modifié, bookmark/system/id étranger/source d'un autre espace, processing/reindexing/sync, missing, nettoyage échoué/annulé, ACK perdu/annulé. Contrôle indépendant des claims d'indexation et uploads GUI : PIDs distincts, verrou effectivement bloquant, SQLSTATE 55P03 et contrôle positif. Contrats en six langues : données littérales échappées, consentement complet, contexte privé absent, plafond et extra fields refusés.
- Validation : première campagne 42 succès puis 84 ; fermeture après port Source groupé et revue : 199 succès (`document-delete-closed-130.log`), plus 8 contrats/imports à froid après simplification des copies (`document-delete-cold-130.log`). Campagnes recouvrantes, nombres non additionnés. MyPy neuf propriétaires puis cinq du delta Source sans erreur ; Black/Ruff, tailles/cycles, CC291/max78 et parité six langues passent. Aucun plafond ni baseline relevé, aucun gain de dette inventé. API Docker healthy et /auth/features nip.io HTTP200 après raccordement ; contrôles globaux LLM/navigateur/mobile restent ouverts. Administration non commencée.
### Lot 131 — Port Source de déplacement documentaire différable (implémenté, revu)

- La relocalisation interne document/fragments est désormais publiée sous `relocate_document_rows`, avec commit=False : le caller conserve sa transaction et la responsabilité des contrôles, fences, ACK et transfert physique. Son défaut commit=True préserve le déplacement GUI et son retour compensatoire après erreur de renommage. `document_move_refusal` publie la règle Source existante pour la réutiliser dans le prochain tool ; aucun nouveau droit ou comportement utilisateur.
- Test rouge AttributeError avant ajout du port, puis PostgreSQL jetable : document et chunk changent réellement de space_id dans la transaction, le fichier original reste intact et la destination absente ; rollback restaure les deux lignes. Revue à froid : repositories update/move_to_space ne committent pas, seuls les appels GUI conservent le commit par défaut ; aucune autre référence à l'ancien nom interne dans la base. Pas de nouveau flag HTTP/LLM, provider ou traitement de fichier.
- Validation : 41 tests Source/transaction/taille réussis (`document-move-source-closed-131.log`), MyPy du propriétaire sans erreur, Ruff/Black et CC291/max78. Plafonds inchangés. Le tool de déplacement n'est pas encore raccordé ; cette frontière sert sa confirmation exacte, elle ne constitue pas une livraison fonctionnelle complète. Qualification globale et administration toujours en attente.
### Lot 132 — Fichiers préparés pour déplacement confirmé (implémenté, revu)

- `document_move_files` prépare une copie exclusive de destination à partir du descriptor Source figé après consentement, avec le spool borné et le worker de transfert déjà utilisés pour les téléchargements. L'original reste présent ; le futur caller retire la copie seulement après rollback connu et conserve les deux fichiers sur ACK SQL indéterminé. Aucun renommage, overwrite, Source provider ou écriture SQL à ce stade. Cette préparation ne constitue pas encore le tool de déplacement.
- Noms stockés littéraux exclusivement, chemins sortants/liens/redirections et collisions refusés ; taille Source/descriptor/copie vérifiée. Missing déjà observé conservé, missing devenu présent ou fichier modifié refusé. Rollback compare le fichier précis, jamais un remplacement. Seules des copies neuves et exclusivement ouvertes peuvent être nettoyées sur erreur de flush, avec identité de creation issue du vrai fd ; le chemin est de nouveau contrôlé et le helper Source de suppression recoupe son témoin complet avant unlink.
- TDD et revue inline : module absent avant ajout ; erreur de flush simulée RED révélant un fichier incomplet laissé, puis correction. Une vraie copie bloquée dans un worker est annulée : la destination reste ouverte jusqu'à sa fin, puis ferme et disparaît ; l'original reste intact. Windows peut finaliser les timestamps au close du writer : témoin stable lu après fermeture et encore rattaché à l'inode créé. Le test de remplacement utilise un vrai os.replace, plutôt qu'une réécriture de même taille pouvant garder les timestamps sur Windows. La preuve est l'identité métadonnée et le copy Source contrôlé ; les writers applicatifs sont à clôturer par les fences du prochain lot, ce n'est pas une promesse de résistance à un acteur OS qui falsifierait les fichiers et timestamps.
- Validation finale : 25 succès Source/fichiers (`document-move-files-closed-132.log`), MyPy deux propriétaires sans erreur, Ruff/Black et CC291/max78. La première campagne groupée de ratchets a subi une access violation de l'interpréteur Windows lors du scan AST de taille ; elle n'est pas comptée comme réussie. Replay isolé complet tailles/cycles : 12 succès (`document-move-files-ratchets-132.log`). Plafonds inchangés. Docker API healthy et /auth/features nip.io HTTP200 revérifiés ; qualification globale et administration restent ouvertes.
### Lot 133 — Déplacement confirmé de documents et writer GUI protégé (implémenté, revu)

- `knowledge_documents.move` / `move_lia_knowledge_documents_tool` propose un déplacement exact entre espaces personnels distincts. Aperçu complet : documents, source/cible et activation, fragments, capacité et fichiers absents. Identités source/documents figées ; changer la destination par édition reconstruit le projet, réautorise et exige un nouvel accord. Aucun fichier/fragment déplacé avant accord ; espaces système/étrangers, projections gérées, documents non terminaux, réindexation/pins, capacité insuffisante et collisions refusés. Cible inactive : les documents sortent de la recherche active de LIA.
- Source de vérité réutilisée : refus `document_move_refusal`, témoins complets document/chunks du lot130, noms/ownership source et port de relocalisation131. Les seuls changements de postcondition admis sont space_id et updated_at automatique ; SQL normalisé privé avant/après, censuses exacts des deux parents, propriétés et capacités recoupées. Verrous compte puis espaces triés puis documents ; contexte privé jamais dans l'éditeur ou la carte. La préparation locale utilise le spool/worker132 et de la place disque pour les octets sélectionnés ; aucun provider/LLM/indexation ni remboursement d'usage passé.
- Copies exclusives préparées avant l'écriture SQL. Erreur avant commit : rollback confirmé et copies retirées ; Source reste disponible. ACK perdu/annulé : COMPLETION_UNKNOWN, originaux et destinations conservés, aucun replay automatique. ACK obtenu : données et destination vérifiées, puis nettoyage de l'original exact ; échec/annulation de nettoyage déclaré en attente. Fichier déjà absent : l'index se déplace sans inventer de fichier.
- Revue à froid : writer GUI déplacé sous le même fence actif compte/espaces/document, capacité fraîche et copie exclusive avant commit. L'ancien commit avant renommage laissait une fenêtre de fichier absent et permettait une mutation concurrente de voisin/capacité. Une vraie connexion GUI est désormais bloquée au commit native (PIDs distincts, SQLSTATE 55P03) ; contrôle positif du même writer sans fence dans les deux sens. Le test RED initial a aussi atteint MissingGreenlet avec expire_on_commit=True après une mutation GUI non bloquée ; la connexion de concurrence utilise la durée de vie Source prévue et les identités de nettoyage sont capturées avant commit. Caractérisation GUI renforcée : destination et original disponibles au commit, disque plein sans changement SQL, done/skipped inchangés ; fixture de taille payload corrigée à sa taille réelle, assertions de compensation remplacées par conservation sans mutation. Ancien helper de renommage inutilisé supprimé.
- Tous les raccords : opération, manifeste, allowlist, exécuteur, canonical/note, éditeur sûr, champ d'événement typé et six langues. HITL réel : refus sans confirmation, édition, retarget des documents refusé et replay avec un AgentEffect et un événement spaces. Lecteurs front board/active/detail déjà abonnés : 12 tests de compte/refresh/SSE passent. Aucun nouveau composant ou changement de layout.
- TDD : module natif absent avant les tests, premiers quatre cas de commit puis vrais chunks ; changements de source/chunks, copie échouée/annulée, nettoyage différé, ACK perdu/annulé, managed/system/id inconnu/pending/reindex/pin/capacité/collision. Contrats privés et échappement littéral dans six langues. Fermeture consolidée : 129 succès (`document-move-closed-133.log`), le premier delta owner/space a terminé son interpréteur au setup mail sans résultat final, il ne compte pas comme succès ; son replay complet avec code retour explicite : 12 succès, pytest_exit=0 (`document-move-delta-replay-133.log`) ; campagnes recouvrantes, non additionnées. Gardes source/événement/tailles/cycles : 34 succès ; huit propriétaires MyPy puis delta deux sans erreur. CC292 observé et refusé : exécution décomposée, CC291/max78 rétabli sans plafond relevé. Ruff/Black, parité et diff-check passent.
- Docker dev API healthy et /auth/features nip.io HTTP200 après raccordement. Les tests exercent le vrai dispatcher/ledger/SQL, pas les échanges LLM Pipeline/ReAct ni un parcours mobile complet : cette qualification globale reste ouverte. Administration non commencée, pause entre les deux périmètres conservée.
### Lot 134 — Port Source d’upload transactionnel et ACK incertain (implémenté, revu)

- `RAGSpaceService.upload_document` accepte désormais commit=False et une identité de document interne optionnelle. Validation Source, fence compte/espace, types/extensions/tailles et écriture du fichier restent communs ; l’état est PENDING durable. Le caller différé possède vérification/ACK, nettoyage après rollback confirmé, telemetry et lancement de traitement. Aucun champ HTTP ou LLM ajouté, aucun appel fournisseur/embedding ou nouveau tool natif encore livré.
- TDD sur PostgreSQL jetable : paramètre commit inconnu avant ajout ; second RED reproduisant un fichier supprimé alors que la ligne avait réellement committé. La phase tentative de commit est désormais distinguée de la création SQL. Après ACK perdu ou annulé, le fichier est conservé ; seul un échec de création suivi de rollback connu peut retirer l’orphan neuf. Le commit GUI normal conserve son comportement et les refus Source. Les constantes de compteur existantes ne sont pas remaniées dans ce port.
- Revue inline : absence de commit dans le repository create, aucune publication ni traitement en mode différé ; identité choisie réelle conservée, rollback supprimant la ligne mais gardant les bytes jusqu’à la décision du caller. Valeur inconnue du commit jamais inférée de l’exception, pas de compensation destructive ni retry. Le writer async du fichier et le parcours navigateur/confirmation sont les prochaines étapes ; ce port n’est pas l’upload LIA complet.
- Validation initiale : 62 succès ; fermeture renforcée identité/rollback/ACK perdu/annulé/source/taille : 72 succès, pytest_exit=0 (`document-upload-source-closed-134.log`). MyPy propriétaire sans erreur, Ruff/Black, CC291/max78 et diff-check passent ; plafonds inchangés. Docker API healthy et /auth/features nip.io HTTP200 après changement. Administration non commencée ; qualification globale et les autres fonctionnalités restent ouvertes.
### Lot 135 — Préparation navigateur de l’import (implémentée, revue ; parcours complet ouvert)

- Choix LLM fermé à space_id : nom, chemin hôte, URL, bytes et base64 refusés. Préparation réservée au compte actif et à sa session navigateur d’origine ; droits natifs/RAG frais avant et après lecture. Destination personnelle non système, y compris inactive ; capacité réelle, types MIME et taille Source, activation et nom littéral dans le périmètre public. Témoin privé de toute la ligne espace, absent de la projection navigateur ; aucun fichier, répertoire, fournisseur, embedding ou job avant consentement.
- TDD : le test de contexte surdimensionné échouait ; validation de modèle à 64 000 bytes ajoutée, y compris au round-trip JSON persistant. Revue inline ownership/inconnus/système, capacité pleine et changement du parent. Aucun raccord au catalogue/tool tant que le endpoint et la confirmation locale du fichier ne sont pas livrés : ce lot ne constitue pas un import utilisable et n’annonce pas une indexation réussie.
- Dernière campagne : 22 succès, pytest_exit=0, incluant 13 scénarios de préparation/contrat et 9 gardes du ratchet de taille (document-upload-prepare-final-135.log). MyPy : trois propriétaires sans erreur (document-upload-mypy-final-135.log). Ruff/Black et CC291/max78 passent, aucun plafond relevé. Aucun front modifié ; sessions de test Redis effacées, PostgreSQL jetable. Parcours complet d’import, validation LLM/browser/mobile et autres fonctionnalités restent ouverts. Administration non commencée, pause maintenue.
### Lot 136 — Écriture Source annulable sans fichier partiel orphelin (implémentée, revue)

- TDD réel : disque écrivant partiellement puis levant OSError et annulation pendant le thread reproduisent deux échecs avant correction. Le worker unique est désormais protégé par shield ; l’erreur attend ce même worker avant suppression du nouveau fichier, grâce au mécanisme partagé de nettoyage résistant aux annulations. Une écriture courte est refusée. Pas de SQL, publication ou job si l’écriture échoue ; aucune modification de la conservation après ACK SQL incertain du lot134.
- Revue adversariale : double annulation pendant le worker, fermeture/fin du thread avant nettoyage, absence de recréation tardive, mémoire limitée par les contraintes Source déjà en place et I/O hors event loop. En cas de répétitions au-delà de la grâce existante, la tâche de nettoyage conserve le registre partagé de background tasks. Un échec du disque/nettoyage reste une erreur, jamais une réussite ou un retry automatique. Deux vieilles fixtures filesystem entièrement MagicMock remplacées par de vrais fichiers temporaires et vérification des bytes ; contrat MIME et Source conservé. Aucun changement de modèle/route/front/provider.
- Validation : 75 succès Source/transactions/ratchet de taille, pytest_exit=0 (document-upload-worker-closed-136.log), puis trois scénarios à froid incluant double annulation passent (document-upload-worker-cold-136.log). MyPy des deux propriétaires sans erreur ; Ruff/Black et CC291/max78 passent. API Docker dev healthy, /auth/features nip.io HTTP200. Le tool natif et la confirmation locale du fichier restent à raccorder ; chantier non administrateur encore ouvert, administration non commencée.
### Lot 137 — Port d’acceptation du fichier confirmé dans le navigateur (implémenté, revu ; raccordement ouvert)

- Port interne pour le futur caller de continuation : la vérification/claim du HITL original appartient à ce caller et n’est pas encore raccordée. Le port exige consentement local explicite, acteur identique, aperçu canonique et destination/capacités/témoin parent encore identiques. Refus avant lecture du multipart si consentement absent, acteur incorrect, expiration ou périmètre changé. Une seule entrée file de type UploadFile ; toutes les autres formes sont refusées, ressources multipart fermées dans tous les cas.
- Transaction de lecture terminée avant attente du body ; après parsing, fences Source compte actif/espace puis nouvelle comparaison du périmètre, Source upload différé avec document_id=command_id. Autorité et expiration recoupées après écriture avant commit. Échec précommit : rollback puis nettoyage du fichier neuf exact. ACK perdu/annulé : COMPLETION_UNKNOWN, bytes conservés, aucun receipt committed ou retry automatique. Reçu positif : import accepté et indexation en attente, jamais traité avec succès ; la projection de préparation annonce l’indexation et le coût fournisseur possible, sans tarif ou nombre de tokens inventé.
- TDD : module absent avant écriture ; simulations sur PostgreSQL jetable : nominal, consentement absent, destination changée, deux fichiers, acteur incorrect, expiration avant/puis pendant le transfert/après écriture, révocation après écriture, ACK perdu/annulé. Revue à froid : l’assertion sur la vraie session confirme qu’aucune transaction SQL attend le multipart. Le check d’autorité de ce port est injecté, il n’équivaut pas à une qualification du caller HITL réel. Aucune requête provider/indexation lancée par ce port.
- Validation : 39 succès couvrant acceptation/préparation/contrat/worker et ratchet de taille, pytest_exit=0 (document-upload-execution-final-137.log). Contre-vérification des onze scénarios avec transaction libérée : 11 succès, pytest_exit=0 (document-upload-execution-cold-137.log), campagne recouvrante non additionnée. MyPy deux propriétaires sans erreur ; Ruff/Black et CC291/max78 passent. Docker API healthy et /auth/features nip.io HTTP200. Opération non enregistrée/non exposée tant que continuation serveur, traitement durable, proxy, carte navigateur, éditeur, registre d’actions et langues ne sont pas raccordés ensemble. Chantier non administrateur et qualification globale ouverts ; administration non commencée.

### Slice 138 — Native local-document import (implemented and reviewed; global qualification remains open)

- Wired `knowledge_document.upload` / `upload_lia_knowledge_document_tool` through the native catalogue, operation and action declarations, safe amendment dispatch, six-language preview, original-browser continuation, typed resource invalidation, bounded RAG proxy and accessible chat card. The model selects an owned destination only. The durable original HITL approval precedes browser selection; choosing a file stays local until an explicit confirmation of filename, size and destination. No bytes or storage path enter the model context.
- Inline review covered the new continuation, parser, manifest, editor, i18n table, all registry/handoff/state consumers, shared worker/router/reaper changes, frontend hook/schema/card/deadline/polling/proxy and their tests. SQL ownership/parent fences, expiry, current capability switches, one-use consent and commit uncertainty retain the preceding ports. No automatic replay or destructive compensation follows an unknown SQL acknowledgement. Acceptance states pending indexing, never a completed embedding. The shared Source processing path retains cost attribution, provider quotas and rate limits.
- Review findings fixed: a durable launcher arriving after another launcher/reaper had claimed or completed the document could re-embed it; GUI/native/reaper launchers now require the existing PENDING claim while manual reindex/Drive paths retain their own entry contract. The backend multipart parser now counts actual received bytes before spooling and rejects an oversized declared body before reading. Both valid oversized multipart cases failed before the guard and pass after it. Accessible file naming and three frontend complexity regressions were corrected by splitting destination, local-file confirmation, secure-card rendering and admitted forwarding responsibilities. Localized copy follows the application register.
- Verification: 111 backend cases pass (`document-upload-backend-final-138.log`), including real disposable PostgreSQL/Redis original-HITL continuations, refusals, lost/cancelled SQL acknowledgements, source job claims and processing behavior. Another 20 boundary/size/cycle guards pass (`document-upload-registry-guards-138.log`). Frontend: 78 tests across the five relevant files pass (49 interaction/polling tests plus 29 proxy tests). Full `task lint:frontend` passes, including clean non-incremental host TypeScript, a11y, React-hooks and complexity. Backend MyPy, Ruff/Black and CC291/max78 pass. Shrink-only frontend baselines were updated after measured improvements; no ceiling was raised.
- Three Chromium journeys pass on a fresh isolated build in Docker dev: desktop, 320px mobile and an upload response lost after acceptance (`document-upload-browser-keyboard-138.log`). They scan the chooser and completed card with axe, confirm once at the keyboard, preserve focus, check the result without resubmission and survive reload. A separate pointer probe with the default floating companion found that its overlay can cover the check button on mobile; that cross-cutting interaction remains for global UX qualification. The keyboard proof is not a claim that this pointer interaction was resolved. The e2e package-wide typecheck also encounters concurrent avatar-spec imports/aliases; this new spec and its fixture graph typecheck successfully without changing those files.
- Docker API remains healthy and the originally reported `/auth/features` nip.io endpoint returns HTTP200. The new tool loads in the real `src.main` import order (`document-upload-docker-import-138.log`); a standalone registry-first probe exposed an autoload ordering diagnostic, which is not counted as a clean universal cold-import proof. The isolated proof server was removed after testing. Runtime-mode-labelled backend tests do not invoke a real LLM. Remaining nonadministrator families, whole-assistant/token-cost qualification and the consolidated documentation are still open. Administration has not started. No commit or push.

### Slice 139 — Owned Drive/Gmail source picker reads (implemented and reviewed)

- Added one read-only native operation/tool, `knowledge_source_options.read` / `get_lia_knowledge_source_options_tool`, with explicit Drive and Gmail sections. It reuses the existing provider picker services rather than changing the metadata-only, provider-free knowledge-space reader. Personal inactive spaces remain selectable; nonexistent/foreign/system spaces, inactive accounts and disabled native/RAG/source-kind capabilities fail before any provider call. Authority and ownership are checked again after the read.
- Model input contains an owned space and a bounded page only. Drive uses a real folder id and an opaque provider continuation; arbitrary query expressions and offset paging are refused. Gmail uses the Source user-label filter/sort, an exact observed total and live offset paging. Drive total stays unknown. Public Drive fields match the picker, extra provider fields/credentials are discarded, output is limited by the shared page/byte bounds, and an overfull provider page fails rather than losing entries. Provider metadata reads consume the Source API quota/consultation path; no LLM, embedding, import, link or sync is performed.
- Source ownership/credential read transactions now finish before Drive/Gmail network waits. Drive's optional page bound preserves the GUI default while permitting a smaller native page. Provider clients close on success/refusal/failure. The wrapper returns finite timeout/dependency/invalid-response codes without provider diagnostics, and errors never become an empty catalogue. Catalogue/core identities, schema, availability and all six progress labels are wired together.
- Inline cold review covered every new reader/schema/spec/tool/test and the touched Source service, catalogue, native operation, identity and translation declarations. Verification: 50 native/Drive tests pass (`source-options-cold-139.log`), plus 38 Source Gmail/space-contract/size/cycle tests (`source-options-source-guards-139.log`). This includes real disposable PostgreSQL authority/ownership, no transaction while a mocked provider waits, limits, late disablement, raw-secret filtering and real tool-wrapper failures. MyPy six owners, Ruff/Black, i18n parity and unchanged CC291/max78 pass. API Docker is healthy, `/auth/features` nip.io returns HTTP200 and the new operation loads through `src.main` (`source-options-docker-139.log`). No paid or live provider call, new UI journey, commit or push. Source link/unlink/sync actions and global nonadministrator qualification remain open; administration has not begun.

### Slice 140 — Retain-only Source unlink transaction ports (implemented and reviewed; native action wiring remains open)

- Drive/Gmail unlink services accept a keyword-only `commit=False` for keeping documents: references become null and the exact source is deleted in the caller's transaction. Repositories still do not commit. The caller can roll back both changes. This deferred path publishes no success log or source gauge before the caller's known commit. Ordinary GUI calls retain the existing default. Deferred destructive unlink is refused before any write/file action; its safe combined deletion path remains a separate pending requirement.
- TDD: all four real PostgreSQL cases failed on the missing port before implementation. After implementation they verify source/reference restoration on rollback, retention of document/chunk rows and bytes at the actual Source storage path, refusal of deferred deletion and no premature gauge decrement. Cold review strengthened the initial file fixture, which had placed its file outside the Source path and therefore was not a valid oracle for destructive behavior. No provider, embedding, publication, memory or new UI path is introduced.
- Verification: 34 cases pass (`source-unlink-port-cold-140.log`), including the four strengthened integration cases and the existing Drive/Gmail service suites. MyPy two Source owners, Ruff/Black, diff-check and unchanged CC291/max78 pass. API Docker healthy and `/auth/features` nip.io HTTP200. The next slice must add exact scope/authority/expiry/CAS fences, HITL execution, typed invalidation, amendment and localized action registration before this becomes a usable native source-removal tool. No administration, commit or push.

### Slice 141 — Confirmed source unlink with document retention (implemented and reviewed)

- Wired `knowledge_source.unlink` / `unlink_lia_knowledge_source_tool` through the native operation/catalogue, exact draft executor, safe editor, six-language preview/progress, automatic named action labels and typed spaces invalidation. Input is an owned space/source id and Drive/mail kind only. Content deletion cannot be requested through this tool. Existing sources can be removed even when their sync feature is disabled; inactive personal spaces remain supported. No provider, download, embedding or new security workflow is introduced.
- Approval captures public source identity/name/status/document count and private complete source/parent witnesses. A streamed, ordered document identity witness holds a bounded buffer without cutting the scan. Execution refreshes account/capabilities/expiry, locks owner/space/source in the established order, compares the whole scope, calls the Source retain-only port and verifies source absence, cleared references and unchanged document identities before commit. Incoherent foreign/null-owner document references and running/unknown sync lifecycles fail closed. Public destination must equal the requested destination by model construction. Private witnesses do not enter preview/editor context; amendments retain command id and original origin and require fresh approval.
- Known commit alone sets the receipt and source gauge; lost/cancelled acknowledgement reports COMPLETION_UNKNOWN without replay or file deletion. The shared confirmed executor publishes one addressed spaces event. Inline review covered every new schema/scope/executor/spec/editor/tool/i18n/test plus every touched registry/rendering/state/translation consumer. Postconditions and telemetry were factored before the complexity check. A replay simulation initially expected ALREADY_CLAIMED while bypassing the approval proof; the real boundary correctly raises CONFIRMATION_MISSING. The simulation now exercises and asserts that actual refusal.
- Verification: 31 distinct operation/real draft-HITL/contract cases pass (16 scenarios in `source-unlink-adversarial-141.log`, eight runtime-mode/approval cases and seven preview/schema/action-label cases in `source-unlink-flow-final-141.log`), plus 12 size/cycle guards. These use disposable PostgreSQL and the actual Source ports; mode-labelled tests invoke no LLM. MyPy seven owners, Ruff/Black, i18n, diff-check and unchanged CC291/max78 pass. API Docker healthy, `/auth/features` nip.io HTTP200 and the tool loads through `src.main` (`source-unlink-docker-141.log`). No new frontend interaction beyond the existing HITL templates; full browser/assistant/token-cost qualification remains open. Link, sync/preflight and destructive source removal still remain, along with the other nonadministrator families. No administration, commit or push.

### Slice 142 — Source Drive preflight query and transaction boundary (implemented and reviewed)

- The existing preflight releases its ownership/source/credential transaction before the bounded Drive walk. It then reads current space capacity and supported-file currentness in two space-scoped document queries instead of one lookup per file. An ambiguous stored Drive identity still fails explicitly, preserving the single-item lookup contract. Tree bounds, classification predicates, quota exclusions and the existing GUI threshold remain Source-owned.
- TDD exposed both per-file lookups and capacity read before the remote wait; their focused tests failed before correction. Cold inline review covered Source/repository changes and all fixtures, including client closure on errors and duplicate identity handling. The real SQL probe redirects consultation persistence to its disposable database; the initial probe's unrelated FK audit error was corrected in the fixture and is absent from the final run. No real provider, download, embedding or model call occurred.
- Verification: 43 unit/size/coupling cases pass (`drive-preflight-final-142.log`), plus two real PostgreSQL cases proving constant document-query count, no transaction during provider calls and refusal of ambiguous identities (`drive-preflight-sql-final-142.log`). MyPy two owners, Ruff/Black, scoped diff-check and unchanged CC291/max78 pass. Docker API healthy and `/auth/features` nip.io HTTP200. Native preflight exposure and source link/sync actions remain pending; global nonadministrator qualification remains open. No administration, commit or push.

### Slice 143 — Native Drive preflight observation (implemented and reviewed)

- Extended the existing source-options read tool with `drive_preflight`, reusing the Source response and classifier rather than adding a tool family. The model must name an existing owned space/source; picker navigation and injected account identities are refused. The exact source account, parent, folder identity and display name are checked around the bounded walk. Disappearance, identity changes, revoked account or current switches withhold the observation. No import, mutation, reservation, synchronization, embedding or new UI interaction occurs.
- The tool schema, manifest and returned explanation publish truncation floors, unreadable-folder coverage, provider quota consumption and the distinction between the Source GUI threshold and mandatory native HITL. Private provider diagnostics remain withheld. Cold review covered schema, reader, manifest, real decorated tool and all tests. A provider timeout wrapped by Source as an unreadable root correctly remains DEPENDENCY_ERROR; the outer native deadline retains TIMEOUT. The test oracle was corrected to the real Source contract, without weakening either refusal. All consultation persistence in these probes targets disposable PostgreSQL.
- Verification: 43 picker/preflight/contract cases pass (`source-preflight-final-143.log`), including ten real Source scenarios through the decorated native tool and currentness checks, plus 12 size/coupling guards. MyPy four owners, Ruff/Black and unchanged CC291/max78 pass. The new contract imports through `src.main` in Docker, API healthy and `/auth/features` nip.io HTTP200. No real provider/LLM or new browser journey exercised. Native source linkage/sync and global nonadministrator qualification remain pending. No administration, commit or push.

### Slice 144 — Source link inspection and deferred SQL ports (implemented and reviewed)

- Drive/Gmail now share immutable server observations between provider inspection and source creation. Preparation applies the existing ownership, kind switch, source quota, duplicate and Drive tree-overlap rules, snapshots all relevant Drive roots and releases SQL before every metadata/ancestor call. Native preparation requires a real provider name and refuses mismatched metadata identities. The existing GUI keeps its Drive display-name choice and Gmail provider-name/fallback behavior.
- Both Source link methods accept a scoped inspected observation and `commit=False`; this path makes no provider call or commit and publishes no success gauge. It locks the current account/owned parent and repeats current switches, ownership, quota, uniqueness and Drive-root checks before inserting. A deferred call without prior inspection is refused. Caller rollback removes the inserted source. This provides the Source seam for a future mandatory native draft; no native link operation is exposed yet.
- Cold review found an actual stale-ORM hole in the final Drive-root check. A controlled SQL update without identity-map synchronization reproduced a false acceptance; fresh Source root reads now use populate_existing, and the exact reproduction refuses the stale write. Fixtures mute the installed consultation collector only in fake-id unit services; real integration consultation writes use disposable PostgreSQL. A healthy Docker status during reload did not imply the endpoint was already serving; after reload settled, the original HTTPS `/auth/features` returned 200. No import failure was observed.
- Verification: 13 real SQL boundary cases pass (`source-link-port-sql-final-144.log`), plus 30 existing Source unit cases and 12 size/coupling guards (`source-link-port-unit-cold-144.log`), with no audit errors in the final logs. MyPy four Source owners, Ruff/Black, scoped diff-check and unchanged CC291/max78 pass. No real provider/model, embedding or browser journey exercised. Native source-link registration, approval, exact selection and action labels are the next slice. Global nonadministrator qualification remains open; no administration, commit or push.

### Slice 145 — Native confirmed standing source link (implemented and reviewed)

- Wired `knowledge_source.link` / `link_lia_knowledge_source_tool` through native discovery, operation/action registries, canonical preview, request-only editor/amendment, six-language copy/progress and typed spaces invalidation. Only real owned destination/kind/provider ids enter the request. Gmail system-label identities, URLs, actor/name overrides and immediate-sync parameters are refused. Provider names are re-read, not supplied by the model. The public approval states standing automatic tracking, later provider quota/embedding costs, active-space/capability conditions and no immediate import/indexing.
- Execution refreshes provider metadata without SQL locks, refreshes account/switch/expiry, locks the owned parent, compares exact name/parent/capacity and uses the Source deferred port. Exact one idle source and unchanged parent are verified before commit. Lost/cancelled SQL acknowledgement produces COMPLETION_UNKNOWN, no committed receipt, gauge or automatic replay. Known commit publishes one addressed spaces event. Amendments retain command identity and original origin and re-read the provider. Cold inline review covered all new files, registry/render/editor/state/language consumers and tests. A Python exception syntax error was corrected immediately before successful qualification; test expectations were aligned with the actual AuthorizationError boundary. Capacity filled during the provider wait now returns a finite constraint refusal.
- Verification: 24 direct scenarios pass (`source-link-adversarial-final-145.log`), including provider-name/parent/expiry changes, capacity changes, revocation and disabling during reads, and real committed-but-lost/cancelled acknowledgements. Eight actual decorated-tool/original-HITL cases pass in both mode contexts (`source-link-flow-green-145.log`; that earlier run also contains the original 16 direct scenarios, not added twice). Eleven contract/preview/action-label cases plus 12 size/coupling guards pass (`source-link-contract-green-145.log`). MyPy seven owners, Ruff/Black, i18n parity, scoped diff-check and unchanged CC291/max78 pass. The operation loads through `src.main` in Docker; after reload settled, API healthy and original `/auth/features` HTTP200. No real provider/LLM or new browser journey exercised. Manual synchronization, destructive source unlink and global nonadministrator qualification remain open. No administration, commit or push.

### Slice 146 — Incomplete source listings cannot infer content removal (implemented and reviewed)

- Four targeted reproductions proved that a bounded/unreadable Drive tree or capped Gmail listing caused the existing workers to delete indexed documents they had not observed. The sweep now removes absent content only after a complete census. Drive retains all previously known routing folders on a partial walk, keeping the root first. Partial runs release the lease, retain the last successful sync timestamp, expose ERROR with an explicit incomplete-listing explanation and publish an error/partial outcome rather than a completed one.
- Gmail listing now returns unique bounded identities plus a completeness verdict. Provider page overflow, remaining continuation and page exhaustion remain partial; reaching the exact configured thread limit on a terminal page is complete. Malformed identities fail before a deletion verdict. Partial mail runs keep the previous history anchor and counts; background and push fallback callers consume the verdict, so neither reports a partial full sync as completed/resynced. No provider/token/embedding path is replaced.
- Cold review covered the tree/listing boundaries, sweep, source updates, job status/telemetry and both mail callers. Unit fixtures isolate installed consultation persistence for fake ids while the dedicated consultation contract still installs its own collector. The first enlarged Drive module exceeded the global size ceiling; completion data was extracted into a typed Source helper, retaining behavior and bringing it below the ceiling without raising any cap. Ordered routing-folder retention was strengthened in its regression assertion.
- Verification: 32 Source unit cases plus 12 size/coupling guards pass (`sync-incomplete-final-146.log`), including all four initial failing reproductions, exact-limit/duplicate/malformed listing and push-outcome cases. MyPy three Source owners, Ruff/Black, scoped diff-check and unchanged CC291/max78 pass. No paid provider/model or real browser exercised. Native synchronization is still not exposed: deferred claim and worker ownership boundaries require the next slice. Destructive source removal and global nonadministrator qualification remain open; no administration, commit or push.

### Slice 147 — Deferred source-sync claims and owner-specific renewal (implemented and reviewed)

- Both Source services can acquire the existing SYNCING job in the caller transaction with an explicit validated worker id; this deferred path never commits. A rollback restores the old source status/owner. Existing GUI calls keep their committed default. Missing worker identity is refused before SQL. Source/document worker length now uses one shared constant matching the unchanged database schema; no migration or column change occurs.
- Owner-specific source renewal requires the same owner, SYNCING state and a currently live lease. It cannot revive an expired claim or renew after another owner took over. Owner paths use PostgreSQL wall-clock time for lease stamps/comparisons so a transaction's old start time cannot revive a stale lease. Existing callers without the new owner argument retain their current behavior; worker propagation and guarded effects remain necessary before a native sync tool can be exposed.
- TDD: eight initial SQL cases failed before the port existed. Cold review added takeover by another owner, invalid identities, missing identity before SQL and the schema-length/wall-clock corrections. Verification: 22 real SQL cases pass (`sync-claim-sql-cold-147.log`: ten boundary scenarios plus 12 existing job-repository cases); 45 Source/contract/schema unit cases plus 12 size/coupling guards pass (`sync-claim-unit-final-147.log`). MyPy four Source owners, Ruff/Black, scoped diff-check and unchanged CC291/max78 pass. Docker API healthy and original `/auth/features` HTTPS200. No network provider/model, embedding or new browser journey. Native sync remains pending with worker ownership/effect safety, along with destructive source removal and global nonadministrator qualification. No administration, commit or push.

### Slice 148 — Ephemeral native worker authority fence (implemented and reviewed; propagation pending)

- Added a typed immutable coroutine-local source worker scope and a balanced context manager. It is not LangGraph state or persistent memory. Fresh SQL acquires the active/nondeleted account, exact owned nonsystem parent and exact SYNCING source/owner/live wall-clock lease in that order. Expiry, takeover, account revocation, system conversion or parent ownership change refuses the fence. A different nested source cannot replace the current scope; all exits restore context. Legacy work without a scope performs no extra authority query.
- TDD first failed on the missing module. Initial SQL qualification exposed use of the account's Python is_deleted property as a SQL column; it was corrected to the actual deleted_at column, confirmed by both SQL and MyPy. Cold review added nonsystem/parent-ownership cases and no-scope/nested-context invariants. This helper is deliberately not yet used by effects; the next slice must propagate it through worker entry, heartbeat, document writes/deletions and source completion before native synchronization is exposed.
- Verification: 12 real SQL authority/lease scenarios pass (`source-worker-guard-final-148.log`), plus two context unit cases and 12 size/coupling guards (`source-worker-guard-unit-148.log`). MyPy one owner, Ruff/Black and unchanged CC291/max78 pass. Docker API healthy and original `/auth/features` HTTPS200. No provider/model/embedding/browser exercised. Native synchronization, destructive unlink and global nonadministrator qualification remain open; no administration, commit or push.

### Slice 149 — Source worker mutation fences (implemented and reviewed; worker propagation pending)

- Source repository updates and shared synced-document creation/deletion now consume the native scope when present. The source/kind, account, parent and live owned lease are checked before SQL/source completion or file effects; creation checks again after file I/O and removes only its newly minted file if the lease expired meanwhile. Document mutations refuse a different owner/parent or linked source. Legacy unscoped behavior is preserved. Scope entry/heartbeat/worker propagation and safe replacement/deletion ACK ordering remain pending before exposing native synchronization.
- Six initial SQL/file reproductions failed before implementation; after fencing, old bytes and rows remain intact and no new file/source completion occurs. Cold review added expiry during the actual new-file write: both kinds refuse and remove the new file while retaining old bytes. The final SQL run includes these eight effect scenarios and the 12 authority cases, all passing (`source-worker-effects-cold-149.log`). Another 34 Source/context unit cases plus 12 size/coupling guards pass (`source-worker-effects-unit-149.log`); unchanged CC291/max78 passes. MyPy three owners and Ruff/Black pass; Docker API healthy and original `/auth/features` HTTPS200. No provider/model/embedding/browser exercised. Safe document replacement and SQL-acknowledgement/file-deletion ordering still require work before native synchronization can be exposed. No administration, commit or push.

### Slice 150 — Native synced-document deletion retains bytes until SQL ACK (implemented and reviewed)

- Native-scoped synced-document deletion uses a Source helper that snapshots the actual stored regular file's identity, validates the live worker fence, deletes row/chunks, rechecks the fence and commits before physical cleanup. Known acknowledgement alone invokes the existing exact-file post-ACK cleanup port; a missing or changed file is never substituted. Failed, lost or cancelled SQL acknowledgement preserves old bytes and propagates the failure. Legacy unscoped Source deletion remains unchanged; no new native tool is exposed yet.
- All four initial real SQL/actual-file cases failed because the old path removed bytes before calling commit. The corrected cases pass (`source-native-delete-green-150.log`): successful deletion sees old bytes at the acknowledgement and cleans afterward; failure before commit restores rows and bytes; real committed-but-lost/cancelled acknowledgement leaves bytes retained with rows absent. Cold review covered capture before ORM deletion, descriptor closure, both fence checks, unknown-ACK propagation and reused cleanup identity checks. Worker entry/heartbeat propagation and safe content replacement remain pending.
- Verification: four SQL/file cases pass, plus 32 existing Source unit cases and 12 size/coupling guards (`source-native-delete-unit-150.log`). MyPy two owners, Ruff/Black and unchanged CC291/max78 pass. No provider/model/embedding/browser exercised. Native synchronization, destructive source unlink and global nonadministrator qualification remain open; no administration, commit or push.

### Slice 151 — Drive replacement download precedes discarding the old version (implemented and reviewed)

- The shared Drive ingest previously discarded an indexed changed file before downloading its replacement. Failed or empty downloads now retain that document. New files still face the existing document quota before provider I/O; replacing an existing document does not need an extra quota slot, matching the preflight classifier. The read transaction still ends before download. The later old-row/new-row replacement itself is not yet atomic and remains a separate pending native safety requirement.
- Two regression cases failed before the order correction and pass afterward, along with ten existing Drive tree/completion cases (`drive-replacement-download-green-151.log`). Cold review checked unchanged-file skipping, new-file quota admission, network transaction release and the explicit remaining replacement-commit gap. Twelve size/coupling guards pass (`drive-replacement-guards-151.log`); MyPy one owner, Ruff/Black and unchanged CC291/max78 pass. No paid provider/model or browser exercised. Native worker entry/heartbeat propagation, atomic replacement, synchronization exposure, destructive source unlink and global nonadministrator qualification remain open. No administration, commit or push.

### Slice 152 — Atomic native replacement and acknowledgement-safe cleanup (implemented and reviewed)

- Under an owned native worker scope, Drive and mail ingestion replace the old chunks/row with the new PENDING row in one transaction. The old file remains until known SQL acknowledgement; failed insertion cleans only the newly minted file, while an unknown or cancelled commit preserves both files without compensation or replay. A fresh locked document read refuses changed or actively processing versions. Scope parameters are checked before reading the old file. Legacy unscoped ingestion keeps its existing path.
- Cold review covered actor/parent/source identity, active processing, stale ORM data, rollback, descriptor closure, atomic row swap and commit uncertainty. Eighteen real SQL/file scenarios pass (`source-native-replace-cold-152.log`), covering six replacement outcomes, four deletion acknowledgements and eight mutation fences. Another 34 Source cases plus 12 size/coupling guards pass (`source-native-replace-unit-152.log`). MyPy three owners, Ruff/Black and unchanged CC291/max78 pass. No paid provider/model/browser exercised. Worker entry and periodic owner renewal must still be connected before exposing native synchronization. Destructive source unlink and global nonadministrator qualification remain open; no administration, commit or push.

### Slice 153 — Native worker entry, periodic source renewal and Source reuse (implemented and reviewed)

- The native launcher carries a typed unique source claim into the existing Drive/Gmail workers. Entry validates source/kind/account/parent before provider access. Source heartbeats derive the exact native owner, refuse different targets and abort on false renewal. Fresh platform/knowledge/source switches and account/parent/source SQL fences are checked again at renewals and effects. Provider calls and native extraction/embedding batches renew on independent short-lived sessions; failed renewal cancels and joins the call, and cancellation joins both tasks without leaking context. Legacy callers retain their unscoped behavior.
- Shared bounded document processing now serves both full-sync workers; the public Drive metric alias remains explicit. Native ingest/deletion failures propagate rather than continuing after uncertain effects. Processing refuses another source document and fences chunk/error writes. Cold review covered scope propagation through child coroutines, provider transaction release, fresh disabling, cancellation, initial refusal, wrong heartbeat identities, metrics, partial listings and safe file/row handling. Two fixture/alias mismatches, typed factory arguments and a complexity regression were repaired without raising a gate.
- Verification: 124 targeted Source/processing/contract/size/coupling cases pass (`source-worker-ack-final-153.log`); eight real worker-entry SQL cases pass (`source-worker-entry-sql-final-153.log`) and the other 30 SQL mutation/authority/acknowledgement cases pass in `source-worker-sql-153.log`. Ruff/Black and unchanged CC291/max78 pass; original Docker `/auth/features` HTTPS200 after reload stabilized. No paid provider/model/browser exercised. Cold review identifies two remaining requirements before native sync exposure: document-job owner renewal/completion fencing and preserving native ownership through reaper recovery. Those form the next slice. Destructive source unlink and global nonadministrator qualification remain open; no administration, commit or push.

### Slice 154 — Independent document ownership and fresh recovery claims (implemented and reviewed)

- Native indexing uses a unique document worker identity. The document's exact owner/parent/source, PROCESSING state and live wall-clock lease are locked before completion, chunk publication, failure or renewal. Slow native extraction/embedding calls renew both source and document claims on separate short-lived sessions. An expired/taken-over document cannot be revived by the legacy heartbeat. All permanent-error paths now carry the document identity. Legacy indexing remains unchanged.
- Source recovery atomically rechecks SYNCING plus expiry before mutation; a refreshed/completed source is skipped. The native recovery port additionally requires distinct validated expected/replacement owner tokens and uses wall-clock time. Both legacy source reapers consume the skipped outcome, so a stale scan never launches work. Native recovery routing remains pending before synchronization exposure: an abandoned native operation must not be replayed through an unscoped legacy worker.
- TDD: document guard import initially failed and all eight fresh-recovery scenarios failed before their port existed. Cold review added the actual indexing pipeline: six real SQL/file/controlled-embedding cases cover success, document expiry/takeover, source takeover, hot disabling and cancellation, preserving bytes and refusing chunk/status publication after authority loss. MyPy found a renewal callback/task name collision; it was fixed and two direct slow-call renewal/cancellation tests now prove both renewals keep running and are joined.
- Verification: 34 SQL ownership/recovery/existing-job/indexing cases pass (`source-job-fences-green-154.log`) plus six actual native processing cases (`source-processing-cold-154.log`). One hundred unit/processing/reaper/contract/size/coupling cases pass (`source-job-fences-unit-cold-154.log`); Ruff/Black and unchanged CC291/max78 pass. No paid provider/model or browser exercised. Native synchronization exposure, native recovery routing, destructive unlink and global nonadministrator qualification remain open. No administration, commit or push.

### Slice 155 — Interrupted native work requires renewed consent (implemented and reviewed)

- The native source/document worker prefixes are explicit Source contracts. An abandoned native source is atomically closed ERROR together with its remaining PENDING/PROCESSING documents; bytes and completed content remain. An expired native document owner is closed ERROR by a conditional update, never re-embedded by the legacy reaper. A queued document belonging to a native source waits for that source's closure. Renewed/completed/taken-over jobs are skipped. Native provider failures are terminal rather than requeued for unscoped automatic retry; a new action requires fresh HITL. Legacy Source jobs retain their recovery behavior.
- TDD first reproduced four unsafe native re-drives. Cold review added missing document leases, stale document-owner snapshots, genuine source renewals/completions, provider failure and actual file retention. A separate SQL reproduction showed native pruning could delete a newly processing document; native deletion now shares the fresh locked replacement guard and refuses that state before deleting rows or bytes. This preserves the original atomic/unknown-ACK deletion cases.
- Verification: 24 SQL/file/actual controlled-indexing cases pass (`native-source-abandon-final-155.log`), including five deletion boundaries, 12 abandonment cases and seven native processing cases. One hundred existing unit/processing/reaper/contract/size/coupling cases pass (`native-source-abandon-unit-155.log`). MyPy four Source owners plus the deletion owner, Ruff/Black and unchanged CC291/max78 pass; Docker original `/auth/features` HTTPS200. No paid provider/model/browser exercised. The next slice exposes the guarded Source sync through native approval, receipts, editors and all action/tool registries. Destructive unlink and global nonadministrator qualification remain open. No administration, commit or push.

### Slice 156 — Native manual synchronization, original HITL and bounded Source jobs (implemented and reviewed)

- Added `knowledge_source.sync` / `sync_lia_knowledge_source_tool` through the existing native tool preparation, durable command, original approval, execution, editing, rendering, catalogue/capability/action identity and typed spaces-invalidation contracts. Local preparation captures an owned idle source, parent/document witnesses, exact provider identity and Source bounds. Active source/document work refuses. Execution locks account/parent/source, rechecks canonical approval/state/limits/expiry/switches, makes the Source deferred claim and validates its fresh SQL postconditions. Only known acknowledgement launches the original Source workers; an uncertain/cancelled acknowledgement produces no replay or launch. The receipt states acceptance, never completed indexing.
- Six-language preview and progress copy discloses replacement/removal scope, provider quotas, embedding costs, asynchronous status and fresh confirmation after interruption. Private state remains outside model editing and public HTML; names stay escaped. Exact provider identity and the smaller of approved/current item/file/document/chunk bounds travel into the ephemeral worker scope. Provider changes refuse before access; capacity/file bounds refuse before file creation. Native fatal handling now atomically closes remaining queued/native-processing work so it cannot fall into an unscoped retry; legacy error handling is preserved and factored.
- TDD first failed on missing native sync; the initial typed selection exposed a subclass/base-model round-trip mismatch, corrected by constructing the reused Source snapshot with its declared base request. Cold worker tests reproduced missing provider/budget propagation. SQL boolean guards were typed explicitly, and added capacity/error logic was extracted without increasing size/complexity caps.
- Verification: 47 direct/actual original-HITL/worker/abandonment/capacity SQL cases pass (`source-sync-native-final-156.log`), including both mode contexts and kinds, refusal before approval, lost/cancelled commit, exact addressed SSE, provider changes and effective smaller bounds. 139 Source/processing/contract/size/coupling cases pass (`source-sync-native-unit-cold-156.log`), including six localized HTML/editor/action/serialization contracts. MyPy twelve owners plus four final changed owners, Ruff/Black, i18n parity, scoped diff-check and unchanged CC291/max78 pass. Docker cold `src.main` loads the registered tool and original `/auth/features` returns HTTPS200. No paid provider/model or new browser journey exercised. Source completion/retry semantics still need a focused check before global qualification; destructive source unlink and other nonadministrator surfaces remain open. No administration, commit or push.

### Slice 157 — Native source completion agrees with persisted ready documents (implemented and reviewed)

- A version stamp alone no longer calls an errored document unchanged: the shared Drive/preflight and mail predicates also require READY, so a new approved sync retries errored versions. Native Drive completion computes ready/retained counts from owned source rows in one SQL aggregate; repeated sync keeps the actual ready count, and missing/failed indexing refuses COMPLETED. Partial runs keep the last successful timestamp and publish current retained-document counts. Native Gmail likewise completes only with a complete listing and the expected ready count; failure retains the history anchor and publishes the actual ready count. Legacy completion defaults remain unchanged.
- TDD reproduced all three Drive inconsistencies on the real worker: repeat-sync count zero, skipped errored version and premature completion after indexing failure. Six actual Drive/Gmail SQL/file/controlled-processing cases now cover unchanged ready content, an approved retry of an unchanged errored version and failed indexing. The unit fixture representing an indexed mail document now declares its actual READY lifecycle. The Gmail finish decision was extracted after the complexity gate caught its added branches; no cap was raised.
- Verification: 24 real SQL/worker/original-HITL cases pass (`native-sync-completion-sql-cold-157.log`), including those six completion cases, ten entry cases and eight original approval cases. Forty-eight Source unit/size/coupling cases pass (`native-sync-completion-unit-cold-157.log`). MyPy four owners, Ruff/Black, scoped diff-check and unchanged CC291/max78 pass; original Docker `/auth/features` HTTPS200. No paid provider/model/browser exercised. Destructive source unlink and the remaining nonadministrator inventory/global qualification are next. No administration, commit or push.

### Slice 158 — Confirmed source removal with exact indexed-document destruction (implemented and reviewed)

- Added `knowledge_source.delete` / `delete_lia_knowledge_source_tool` through native preparation, durable original HITL, execution, request-only editing, public rendering, catalogue/capability/action identity and typed spaces invalidation. The separate retain-only unlink remains available. Whole-source destruction composes existing bounded document/chunk/file witnesses, refuses busy/foreign/system/oversized selections and locks the current account, parent, source and documents. Document/chunk/source rows disappear in one transaction; exact physical cleanup begins only after known commit acknowledgement. Unknown/cancelled commits preserve bytes and never replay. Failed post-commit cleanup is explicitly reported. No provider originals or unrelated documents are removed.
- Cold review reproduced a same-account chunk pointing into another space: the shared deletion guard now checks both denormalized owner and space before consent. Added actual SQL cases for empty sources, vector chunks, foreign/system chunks, oversized witnesses and two document batches, plus expiry, disabled tools, revoked account, busy source, rollback, lost/cancelled acknowledgement and pending cleanup. Both runtime modes and source kinds exercise the original tool/approval executor with an actual indexed document and file. Six-language copy, escaped names, private editor/HTML boundaries and complete round-trip/action identity were checked.
- Verification: 52 real SQL/file/original-HITL and existing document-deletion cases pass (`source-delete-sql-final2-158.log`); 60 unit/registry/size/coupling contracts pass (`source-delete-unit-final-158.log`). Strict MyPy seven owners, scoped Ruff/Black/diff-check, unchanged CC291/max78 and i18n parity pass. Docker cold `src.main` loads the new operation; original `/auth/features` returns HTTPS200. No paid provider/model or new browser journey exercised. Remaining nonadministrator surfaces and global qualification continue; no administration, commit or push.

### Slice 159 — Actual generated-gallery UI read and real native tool bootstrap (implemented and reviewed)

- Added `generated_gallery.read` / `get_lia_generated_gallery_tool`, complementing the existing card-producing generated-file lookup. The native reader and original UI route share one domain projection and the same declared family/page/search bounds. It returns the actual filtered page, total bytes/count, account-wide keep quotas, expiry/kept metadata and honest live continuation, including expired rows the sweep has not removed. Strict aware date/filter inputs, account/native checks before/after, fresh returned ownership and whole-payload refusal protect the boundary. Stored paths, bytes, upload/foreign rows and credentials never enter the model. No mutation, provider/model call, card creation or quota consumption occurs.
- Cold bootstrap verification exposed missing imports for all five newly separated Source tool modules: catalogue declarations alone had not proved executor availability. A focused test failed at the actual bootstrap; all five Source modules and the gallery module are now explicitly loaded there. The original catalogue-to-registry parity test also passes. This corrects the reachability gap in the earlier Source slices; their narrower SQL/native executor proofs remain valid.
- Verification: 33 actual PostgreSQL/UI/tool/filter/expiry/authority/continuation cases pass (`gallery-read-sql-final-159.log`); 44 strict-input/actual-bootstrap/catalogue/registry/size/coupling cases pass (`gallery-unit-final-159.log`). Strict MyPy six owners, scoped Ruff/Black, unchanged CC291/max78 and six-language parity pass. Docker cold bootstrap resolves every Source tool and the gallery tool; original `/auth/features` returns HTTPS200. No paid provider/model or new browser journey exercised. Confirmed gallery retention/deletion/download and remaining nonadministrator families/global qualification continue; no administration, commit or push.

### Slice 160 — Existing generated-file retention joins a native transaction (implemented and reviewed)

- The existing keep/release commands accept an explicit deferred commit while retaining their original committing defaults for UI callers. Both commands now share the exported account advisory lock before any selected row lock; native callers can check the whole approved effect before their single commit, without lock-order inversion. A keep-limit refusal leaves rollback to the caller in deferred mode. Existing exact quotas, idempotent keep semantics, skipped ids and fresh release TTL remain unchanged; no bytes are touched.
- TDD first failed both rollback cases on the missing deferred port. Fifteen real PostgreSQL existing/deferred/quota/rollback/sweep/concurrency cases pass (`gallery-keep-port-green-160.log`), including the existing last-slot and keep-versus-sweep races. Thirty-one unit/size/coupling cases pass (`gallery-keep-port-unit-160.log`). Strict MyPy of the owner, Ruff/Black and unchanged CC291/max78 pass. Native retention tool/HITL and addressed frontend refresh follow next; no administration, commit or push.

### Slice 161 — Confirmed generated-file keep/release and owned gallery refresh (implemented and reviewed)

- Added `generated_assets.retention.update` / `update_lia_generated_asset_retention_tool` through native preparation, durable original HITL, execution, request-only editing, six-language public rendering, catalogue/capability/action identity and the typed `generated_assets` invalidation resource. Consent names every file and current expiry, requested retention, before/after keep usage, ceilings and fresh release TTL. Metadata witnesses exclude extracted document bodies and have a boot completeness guard against public schema growth. Selection limits are shared with the original API schemas. Known exceeded capacity refuses preparation. Execution locks account, quota advisory scope and exact generated rows in consistent order, rechecks selection/authority/expiry/quotas/TTL and verifies all results before one SQL commit. Lost/cancelled acknowledgement has no successful receipt or automatic replay. Mixed selections preserve already requested states; release does not immediately delete files.
- The gallery hook reuses the existing account-lifetime query and addressed resource refresh. A new account hides old rows/quotas and resets paging; foreign invalidations do nothing. A failed initial read now exposes its error rather than an endless loader. Source-family editor projection and gallery page defaults were extracted after the complexity gates found new hotspots; neither backend nor frontend caps were raised. Browser fixtures now carry complete source DTOs and actual page byte totals.
- Verification: the combined 44 SQL/HITL/rollback/quota/sweep/concurrency cases pass (`asset-retention-sql-final-161.log`), followed by all 13 boundary/mixed/no-op cases (`asset-retention-boundaries-final-161.log`, including two added cases). 108 broader and 72 final unit/registry/Source-editor/wire-shape/size/coupling cases pass. Strict MyPy nine owners plus five final owners, scoped Ruff/Black/diff-check, CC291/max78, six-language parity, complete `task lint:frontend` and clean nonincremental TSC pass; front ratchets stay a11y0, hooks30 and CC42/max50. Thirty-nine final frontend cases pass (`gallery-front-closure-161.log`). Five hermetic Chromium gallery journeys pass, including 320px containment and real selected delete payloads; no paid provider/model or real account was used. Docker bootstrap resolves the retention tool and original `/auth/features` returns HTTPS200. The proof container and only its generated tsconfig entries are removed. Gallery deletion/download and remaining nonadministrator families/global qualification continue; no administration, commit or push.

### Slice 162 — Deferred generated-file deletion and fresh repository identities (implemented and reviewed)

- The original generated-batch deletion accepts an explicit deferred commit. Its existing UI default still commits, cleans files and records metrics. Deferred execution flushes the row removals while leaving files and metrics untouched, so a native command can verify and commit its exact approved deletion first. No early physical cleanup or caller transaction commit occurs.
- Cold review reproduced an identity-map false negative: a row refreshed in SQL from upload to generated was still classified from its old ORM instance. The shared owned-batch query now refreshes existing instances, preserving the actual owner filter and existing generated-only selection rules. The retention input also receives a boot parity guard against the original UI request fields, so a future parameter addition cannot silently disappear from the native tool.
- Verification: 15 PostgreSQL deferred/rollback/old-ORM/existing quota/sweep/concurrency cases pass (`generated-delete-port-cold-162.log`); 31 unit/size/coupling cases pass (`generated-delete-port-unit-final-162.log`). Strict MyPy two owners, scoped Ruff/Black and unchanged CC291/max78 pass. Native destructive gallery consent and identity-sealed physical cleanup follow next. No administration, commit or push.

### Slice 163 — Confirmed gallery deletion with sealed files (implemented and reviewed)

- Added `generated_assets.delete` / `delete_lia_generated_assets_tool` through the native catalogue, original durable HITL, request-only editing, six-language consent and typed addressed gallery refresh. The shared generated selection schema and metadata reader serve retention and deletion, with boot parity guards against public API growth and no extracted text in witnesses. Exact owner/generated ids, metadata and descriptor identities are rechecked under account/row locks. A single alias-reference query refuses ambiguous shared paths. SQL deletion is verified before one commit; only known acknowledgement permits physical cleanup. Lost/cancelled acknowledgement preserves bytes and does not replay. Changed files after acknowledgement are retained with an explicit cleanup-pending result. Missing physical files may have their gallery rows removed.
- Cold verification: 35 real PostgreSQL original HITL/deletion/retention cases pass (`asset-delete-sql-cold-163.log`); ten extra mixed-owner/upload/missing/unsafe/shared-path/size/disabled/revoked/expired/absent-file boundaries pass (`asset-delete-boundaries-final-163.log`). Fifty-seven contract/registry/size/cycle tests pass (`asset-delete-unit-final-163.log`), including private-witness exclusion, escaping and full serialization in six languages. Strict MyPy twelve owners, scoped Ruff/Black and unchanged CC291/max78 pass. Actual Docker startup resolves the tool and the original auth-features HTTPS handler returns 200. No paid model/provider, administrative tool, commit or push. Gallery download follows next.

### Slice 164 — Confirmed generated-file download in the original browser (implemented and reviewed)

- Added `generated_asset.download` / `download_lia_generated_asset_tool`, original DEVICE continuation, request-only same-artifact editing, six-language consent, command endpoint and the existing accessible browser download card. Owned generated READY metadata and the exact opened file identity/size are rechecked; missing/upload/foreign/stale files refuse. Approved bytes are frozen in the existing bounded disk-backed reader. Transfer is single-use and session-bound; no file content/path enters the model and `save_confirmed` remains false. Existing gallery files remain downloadable when uploads, generation or RAG are disabled. The shared transfer reads capabilities from its trusted operation declaration instead of hardcoding RAG; original source-document/ZIP constraints remain.
- Private file witnesses are shared between deletion and download. Cold review reproduced cancellation during threaded open; the shared asynchronous open now closes a descriptor that arrives after cancellation, proven by a controlled delayed-open test. No unjoined file task is intentionally abandoned by the normal cancellation path.
- Verification: final 38 PostgreSQL/Redis/ASGI cases pass (`asset-download-sql-final-164.log`: both runtime contexts, original durable HITL, refusal, other session, stale files, disconnected send, lost/cancelled acknowledgement, edit refresh/retarget, eight snapshot boundaries and shared deletion). The earlier combined run also passed all 22 original source-document/ZIP transfer cases; its one new stale-file assertion mismatch was repaired and passes in the final suite. Seventy-seven unit/contract/catalogue/size/cycle cases pass, strict MyPy thirteen owners passes, twelve frontend download-card tests pass, scoped ESLint and clean Docker TypeScript pass. Six-language parity and CC291/max78 remain green. Actual Docker bootstrap resolves the new tool and auth-features returns HTTPS200. No paid provider/model, administration, commit or push. Saved-answer management and remaining nonadministrator families follow.

### Slice 165 — Saved-answer UI read with complete content continuation (implemented and reviewed)

- Added `saved_answers.read` / `get_lia_saved_answers_tool`, shared real UI projection, exact literal-filtered totals, stable paging, derived indexing state and existing answer/index costs. Long copied answers and requests have typed explicit character windows, full lengths and continuation offsets, under a bounded UTF-8 result size; a partial window is never presented as the entire answer. Saved copies remain readable after conversation deletion and when keeping new answers is disabled. Actor/switch/returned owner rows are checked again after fetching. No indexing, new model/provider call or spending occurs.
- Cold SQL review reproduced foreign projection and turn-cost leakage through inconsistent stored references. Shared batched document/cost readers now match both identity and account before exposing those values. The coupling gate detected a new agents/bookmarks cycle: the existing pure HTML detector was moved unchanged to core and publicly re-exported, removing the dependency rather than widening the ratchet. Existing route fixtures now patch the actual shared projection owner; the state route retains its own service fixture.
- Verification: 28 real PostgreSQL UI parity/literal paging/foreign links/authority recheck/large multibyte answer/historical copy cases pass (`bookmark-read-sql-cold-165.log`); 158 unit/domain/schema/catalogue/size/cycle/TTS/notification cases pass (`bookmark-read-unit-final2-165.log`). Strict MyPy eight owners plus three pure-detection consumers, Ruff/Black, six-language parity and CC291/max78 pass. Actual Docker bootstrap resolves the tool and auth-features returns HTTPS200. Confirmed saved-answer keep/removal and the remaining nonadministrator families continue; no administration, commit or push.

### Slice 166 — Deferred saved-answer keep and account quota serialization (implemented and reviewed)

- Existing `BookmarkService.keep` accepts an explicit deferred commit, keeping its original UI default. Deferred execution stages the owned visible assistant answer and its request only; the caller owns the transaction and post-ack indexing, with no early log announcing a keep and no job before known commit. Deferred integrity failure propagates without rolling back the caller's transaction. Existing direct UI idempotence, quota refusal and duplicate-click recovery remain. An account advisory lock precedes the count/message checks so simultaneous keeps cannot spend the same last slot. Owned bookmark reads refresh existing ORM instances.
- TDD reproduced both missing deferred support and a real two-connection quota overflow. After correction, 19 real PostgreSQL rollback/two-session/historical-copy cases pass (`bookmark-keep-port-green-166.log`), and 87 domain/unit/size/cycle cases pass (`bookmark-keep-port-unit-166.log`). Strict MyPy two owners, scoped Ruff/Black and unchanged CC291/max78 pass. Original UI behaviour remains covered; native exact consent and execution follow next. No administration, commit or push.

### Slice 167 — Exact confirmed saved-answer copy execution (business core implemented and reviewed)

- The native keep seals the complete copied answer/request privately while consent names the archived message, original date, literal excerpts, full character counts and before/after quota. The original visible/proactive/request-copy builder is shared with UI keeps. Execution serializes the quota owner, locks the actor and existing copy or owned conversation/assistant/preceding visible request, rechecks authority/expiry/source/quota, stages through the deferred existing service and verifies the exact copied digest/count before one commit. Only known acknowledgement permits indexing enqueue. An enqueue failure preserves the committed copy and reports indexing pending for the existing reconciliation lifecycle; no completed index is claimed. Existing copies are no-ops and are not reindexed, including at the cap.
- Verification: 17 real PostgreSQL native/deferred/race/source/request/authority/expiry/quota/lost/cancelled-ack/visibility/100k-character/idempotence cases pass (`bookmark-keep-native-cold-167.log`), plus two capability-off/post-ack-enqueue-failure cases (`bookmark-keep-native-postack-167.log`). Seventy-eight shared-domain/cycle cases pass. Strict MyPy six owners plus final executor/repository, scoped Ruff/Black and final CC291/max78 pass; the initial new executor hotspot was decomposed without widening the ratchet. Original tool/HITL/editor/action-register/six-language/frontend wiring follows as the next slice. No administrative work, commit or push.

### Slice 168 — Original HITL, action registers and owned saved-answer refresh (implemented and reviewed)

- Added `keep_lia_saved_answer_tool` through the native catalogue/capability identities, original durable HITL execution, request-only editing, exact six-language consent and the typed `saved_answer_to_keep` action/invalidation field. Literal preview excerpts are escaped; private full-copy digests never enter editor prompts. Gallery editor projections are shared rather than extending the central branch chain. Consent explicitly covers complete copying, quota, preserved existing copies and potential token/quota spend by ordinary indexing after known commit.
- The saved-answer hook now reuses the existing account-lifetime query and addressed generated-assets refresh. Old-account rows/capacity are hidden while a new request is pending; unavailable accounts do not query, foreign events do nothing, and a failed initial read does not produce an endless loader. The shared refresh port accepts a stable default when a view has no local override to release; existing override behaviour stays covered.
- Verification: four original actual-tool/HITL confirm/refuse cases pass in Pipeline/ReAct runtime contexts (`bookmark-keep-wiring-green-168.log`), including exact owned event and no unapproved replay. Sixty-nine schema/catalogue/serialization/six-language/editor/size/cycle cases pass; nine strict MyPy owners pass. Nineteen saved-answer list/account cases and eleven final shared refresh/gallery cases pass. Scoped ESLint and final clean Docker TypeScript pass. Front ratchets stay CC42/max50, hooks30 and a11y0; backend stays CC291/max78 and six-language parity passes. Actual Docker bootstrap resolves the keep tool and auth-features returns HTTPS200. No paid provider/model was exercised. Natural last-answer selection, saved-copy removal and remaining nonadministrator qualification continue. No administration, commit or push.

### Slice 169 — Natural latest archived-answer selection, frozen before consent (implemented and reviewed)

- A native keep may omit `message_id` to select the actual latest visible archived assistant answer in the account's active conversation. The read uses the existing visible-only predicate, actor filter, nondeleted conversation and deterministic timestamp/id ordering. Hidden runs, user rows and other accounts are excluded. No archive id is invented, and a not-yet-archived current draft is explicitly unsupported. A strictly resolved UUID request is stored in the approval witness: a later answer never retargets an approved copy. Explicit-id API/UI keep semantics remain unchanged; the same-field API growth guard remains.
- Verification: 23 actual PostgreSQL latest/deleted/late-arrival/HITL/authority/ack/visibility/large-copy cases pass (`bookmark-latest-green-169.log`); 31 contract/catalogue/message-reader/cycle cases pass (`bookmark-latest-unit-169.log`). Strict MyPy four owners, scoped Ruff/Black and unchanged CC291/max78 pass. Native saved-answer deletion follows. No administration, commit or push.

### Slice 170 — Deferred saved-copy removal and exact owned projection guard (implemented and reviewed)

- Original UI removal retains its committing default. The deferred port stages and flushes the bookmark/projection deletion, returns the file path and leaves commit, physical cleanup and success reporting to its caller. The shared guard locks parent then document and rejects foreign parents/documents, wrong source types, foreign/system/wrong-space chunks and projections referenced by another bookmark. Cold SQL tests reproduced both cross-account projection deletion and shared-projection deletion before correction.
- Verification: 100 real PostgreSQL/shared-domain cases pass (`bookmark-remove-final-170.log`), including rollback with untouched bytes and all eight adversarial projection cases. Strict MyPy three owners, scoped Ruff/Black and unchanged CC291/max78 pass. Native exact consent/execution follows. No administration, commit or push.

### Slice 171 — Confirmed saved-copy/projection deletion with exact post-ACK cleanup (implemented and reviewed)

- Added `saved_answer.delete` / `delete_lia_saved_answer_tool` through original durable HITL, request-only amendment, canonical rendering, six-language consent/progress, catalogue and action identities. Consent names the full copy by bounded literal excerpts/character counts and its projection/chunks; full copied text and projection state are privately sealed. Existing copies remain removable with new bookmarking/indexing disabled. Ordered account/advisory/parent/document/chunk/bookmark locks precede re-observation and the existing deferred removal. All rows are verified absent before one commit. Only known acknowledgement permits exact-file cleanup; lost/cancelled acknowledgement preserves bytes and never replays. Failed cleanup or post-ACK replacement is reported as pending. The original conversation answer is preserved.
- Cold review covers changed stored copy/projection/chunk/file, authority and expiry; a 170k-character copy with real indexed chunks; no-projection copies; and foreign/shared projections. A shared-file alias is now refused by the domain guard. Original-HITL integration caught an incorrectly addressed profile refresh: the action now emits the exact `generated_assets` invalidation and `saved_answer_to_delete` field.
- Verification: 51 SQL/actual-tool Pipeline-ReAct confirm-refuse/contract/registry/size/cycle cases pass (`bookmark-delete-final-171.log`); 44 shared-file/domain cases pass (`bookmark-delete-shared-file-171.log`). Strict MyPy nine owners plus final two, scoped Ruff/Black, unchanged CC291/max78 and six-language parity pass. Docker cold bootstrap resolves the actual tool and the original auth-features path returns HTTPS200. No paid provider/model or new browser journey exercised. Automatic-indexing account fencing and remaining nonadministrator surfaces continue. No administration, commit or push.

### Slice 172 — Live authority/quota fences for durable saved-answer indexing (implemented and reviewed)

- TDD reproduced automatic projection starting for an unavailable account and actual embedding/publication for disabled/deleted accounts or disabled bookmarking/RAG. The existing projector now refuses unavailable accounts before creating any projection. The durable pipeline recognizes bookmark source rows directly, so recovery gets the same guard without transient context or new domain cycles. Fresh capability/account/parent/document checks precede claim, each paid batch and chunk publication; per-batch quota uses the existing platform/account spend verdict. Locks are released before provider work. Claims use unique bookmark worker identities; expired/replaced claims refuse and an old worker cannot settle a new holder. A stopped owned projection becomes terminal ERROR without deleting its file; failed settling is logged without raising into the caller.
- Verification: 130 actual PostgreSQL/durable/native-source and domain/unit/size/cycle cases pass (`bookmark-worker-cold-172.log`), including controlled provider-time revocation, takeover and quota refusal. No external paid provider was invoked. Strict MyPy three owners plus final two, unchanged CC291/max78 and scoped formatting pass. An in-flight provider call can already have billed usage; this guard prevents subsequent batches and publication, not a claim that paid work is refundable or remotely cancelled. No administration, commit or push.

### Slice 173 — Actual email-share options and owned deterministic recipient suggestions (implemented and reviewed)

- Added `email_share.read` / `get_lia_email_share_options_tool`. It reuses original route selection/options, contact availability, deterministic matching, directory/cache bounds and consultation filing. Actual relay/connected-mailbox/unavailable states, reconnect notice and all published limits reach the tool. Recipient lookup is offered only where the UI permits free recipients and shares its existing per-account rate-limit key/configuration. Read transactions end before connector lookup; active account/native/email capability is refreshed afterward. Credentials, sending and model calls are absent.
- Verification: 116 SQL/original email-domain/registry/size/cycle cases pass (`email-share-read-cold-173.log`), including relay restriction, shared rate refusal and revocation during lookup. Strict MyPy four owners, scoped Ruff/Black, unchanged CC291/max78 and six-language parity pass. Actual Docker bootstrap resolves the reader. Confirmed sending and remaining nonadministrator surfaces continue; no administration, commit or push.

### Slice 174 — Exact confirmed email sharing, original action register and single-attempt transport (implemented and reviewed)

- Added `email_share.send` / `send_lia_email_share_tool` through original durable HITL, canonical six-language consent/progress, request-only amendment, catalogue/action identities and owned addressed refresh. The original envelope validators are shared by UI and native inputs; native attachment choices are exact owned generated-file, saved-copy or visible archived-answer ids, never invented copied Markdown or uploads. Complete request/answer exports use the existing localized kept-answer renderer; preview excerpts do not truncate bytes. Consent seals actual deduplicated recipients, sender route, literal subject/message, filename/size and full private source/file/route witnesses. Source rows/parent/account are freshly locked and re-observed; generated bytes are frozen from the approved descriptor. Preflight commit acknowledgement must be certain before sending and no transaction spans the provider. Acknowledged sending is explicitly distinct from recipient delivery; unknown/cancelled acknowledgement is never replayed.
- UI and native paths now import one shared send/suggestion limiter declaration. The actual original email service files the action under `EMAIL_SHARE_CAPABILITY`. Cold review found implicit provider retries capable of repeating an ambiguous send: a native-only single-attempt port now reaches Gmail metadata/upload, Outlook and Apple SMTP while preserving existing clients' default behaviour. Native mailbox opening also refuses a changed provider. The durable original command claim independently prevents subsequent execution replay.
- Verification: 202 actual PostgreSQL/tool Pipeline-ReAct confirm-refuse/original action-sink/schema/provider/domain/registry/size/cycle cases pass (`email-share-send-final-174.log`), followed by two visible-versus-hidden archived-answer cases (`email-share-archived-174.log`). Covered copy/route/file/metadata changes, account revocation, early/late lost preflight acknowledgement, cancellation, remote uncertainty, frozen bytes after replacement and one transport attempt. Strict MyPy five initial, ten final owners and six transport owners, scoped Ruff/Black/diff-check, unchanged CC291/max78 and six-language parity pass. Docker cold bootstrap resolves the sender and original auth-features returns HTTPS200. No real email, paid model or provider call occurred. Saved-answer downloads, remaining nonadministrator families and global qualification continue. No administration, commit or push.

### Slice 175 — Original-browser complete saved-answer download and shared Markdown export (implemented and reviewed)

- Added `saved_answer.download` / `download_lia_saved_answer_tool` through original mandatory HITL, origin-bound one-use device continuation, authenticated no-store attachment endpoint, request-only same-copy editing, canonical six-language consent/progress and original download card. Full copied request/answer/date are rendered by the existing localized kept-answer renderer, now shared with native email by one domain export builder. Only excerpts/filename/size enter consent; complete copy/export digests remain private. Existing copies stay exportable when new bookmarking/indexing is off. Changed copy/format, expired/revoked authority, another browser and replay refuse. Shared transfer reports download requested separately from reception/saving and handles lost/cancelled commit without replay.
- The same file-descriptor transfer owner can create a frozen export from bytes and closes delayed temporary files after cancellation. Cold full-flow testing caught an invalid charset-bearing MIME value accepted by core-only tests: the response now receives the valid MIME type and supplies encoding through its standard response path. The response retains approved bytes after the stored copy changes and closes on every tested ASGI exit.
- Verification: 29 actual SQL/tool/original-HITL Pipeline-ReAct/device/ASGI/cancellation cases pass (`bookmark-download-flow-final-175.log`); 35 broader shared-export/email/registry/size/cycle cases and 23 final schema/checkpoint/editor/catalogue/size/cycle cases pass. Thirteen Docker frontend card cases, scoped ESLint and clean nonincremental TypeScript pass. Strict MyPy six initial/eight final owners, unchanged CC291/max78, six-language parity and scoped diff-check pass. Actual Docker bootstrap resolves the tool. No paid provider/model or new browser journey was exercised. Personal skills/plugins/MCP/sandbox, meetings and global qualification continue; no administrative work, commit or push.

### Slice 176 — Personal skill gallery read (implemented and reviewed)

- Native `skill_settings.read` shares the original UI metadata merger and account/system shadow visibility. Exact-scope cache lookup exposes public metadata only; instructions, scripts, filesystem paths and other account scopes remain excluded. Strict page bounds and a byte ceiling constrain model context; the UI/native field-completeness guard forces review when the projection grows. Both native availability and skill capability/account are refreshed around observation. System scope is an available system skill, not administrative authority.
- TDD collection failed before implementation; 591 original skills/domain/registry cases pass (11 POSIX-only cases skipped on Windows). Twenty-five fresh SQL/shadow/revocation/schema/catalogue/size/cycle cases pass (`skill-read-cold-176.log`), strict MyPy five owners and unchanged CC291/max78 pass. No mutation, paid provider or administration. Original router alias remains compatible. No commit or push.

### Slice 177 — Explicit personal skill activation with original HITL (implemented and reviewed)

- Native `skill_settings.update` accepts exact visible id plus a strict boolean, never an inversion or global activation. Original UI toggles share a newly locked exact-state port; hidden system/shadowed/foreign skills refuse. Consent compares complete public metadata/state under fresh actor/skill/state locks; same value is a confirmed no-op. Expiry, current capability and account are checked before commit; unknown/cancelled acknowledgement never sets a success receipt. Original durable confirmation prevents unapproved/repeated execution. Request-only editing retains the selected id and rebuilds current witnesses.
- The action is declared in native/manifest/bootstrap/effect identities and the strict changed-field/resource registry (`skills`). Six-language consent is literal and HTML-escaped; metadata is not editable. Frontend uses the existing account-lifetime query and resource subscription, retaining library revisions: a previous account disappears during the next read, foreign invalidations do nothing, and refreshed data is not cleared after success.
- Verification: 42 SQL/visibility/original-confirmation/ratchet cases plus 36 final expiry/lost-cancel-ack/checkpoint/editor/i18n cases pass; 34 Docker frontend cases, clean TypeScript and scoped ESLint pass. Strict MyPy eight owners, unchanged CC291/max78, six-language parity and scoped diff-check pass. Actual Docker bootstrap resolves reader/action; auth-features HTTPS200. No skill execution, provider/model, administration, commit or push.

### Slice 178 — Complete skill ZIP in the original confirmed browser (implemented and reviewed)

- Native `skill_settings.download` observes exact account-visible skill id/public metadata and seals the complete archive digest privately. Instructions and paths never enter consent or native read results. Original UI and native transfers share one bounded deterministic ZIP builder, using the existing import file/decompressed-byte limits. Scope/path/symlink/junction/nonregular/member/growth refusals apply before and during reads; POSIX opens each path component without following links. Path inode identifies the opened resource; its own descriptor version checks mutation before/after read. No file handle is abandoned; compression runs off the event loop. The existing one-use confirmed browser transfer supplies frozen bytes, certain commit acknowledgment and ASGI cleanup; unknown/cancelled results cannot replay, and request is distinct from receipt/save.
- Shared read metadata observation now belongs to the reader module rather than depending on skill-write semantics. Request-only amendments cannot retarget. Original tool/capability/catalogue/editor/browser endpoint/card and six-language consent are wired without a new transfer framework.
- Verification: 52 final PostgreSQL/full original HITL Pipeline-ReAct/browser/ack/copy/visibility/ZIP/size/cycle cases pass (`skill-download-final-178.log`); six archive cases run on Windows and real Linux Docker, including link insertion after enumeration. Eighteen Docker frontend cases, clean TypeScript, scoped ESLint, six-language parity, strict MyPy ten initial owners and unchanged CC291/max78 pass. Actual Docker bootstrap resolves download. No provider/model/skill execution, administration, commit or push. Larger nonadministrator scope remains in progress.

### Slice 179 — Original skill download visibility (implemented and reviewed)

- TDD proved the original named download served a disabled system skill from cache. It now resolves through the original account gallery's database visibility/shadow rules and exact cache scope; current visibility is checked again after off-loop compression. Joined skill/state reads refresh the session identity map, preventing obsolete public metadata from surviving a repeated read. Administrator download still follows its own original endpoint.
- Verification: 23 actual PostgreSQL/original UI/owned shadow/native read and original off-loop archive cases pass (`skill-download-visibility-final-179.log`), including controlled disabling during compression. Scoped Ruff passes. No new administrator capability, provider, commit or push. Nonadministrator scope continues.

### Slice 180 — Original skill library reads with typed bounded windows (implemented and reviewed)

- Added `skill_library.read` for original search, immutable-commit previews/folder choice, owned installations/update status and owned update preview. One strict discriminated request describes the four read kinds; original service/SSRF/source/cache/audit/account lookup remain authoritative. The UI and native reader share one actual rate-limiter declaration. Read transactions end before networking; current native/skill/library capability and account are checked afterward. Every original list is independently windowed, with exact totals/continuation. Audit block and commit verdicts remain explicit; a schema-growth guard fails when a new UI list lacks a declared native window. Returned third-party source words are untrusted; no install/update/provider/model action occurs.
- Cold architecture review exposed a new library/agent cycle caused by the existing library HTTP client importing agent-local URL hardening. The same validator/pinned transport now belongs to infrastructure; the historical agent API and DNS seam remain via a thin compatibility facade. Library test fakes now target the shared owner. No validation/redirect/credential/DNS-rebinding policy was relaxed, and the cycle baseline was not widened.
- Verification: 288 SSRF/web-fetch/library/native-window/size/cycle cases pass (`skill-library-read-cold-final-180.log`), plus nine actual PostgreSQL/native authority/rate and original real-import/update cases with existing fake hub. Five native-reader and three shared-validator MyPy owners, unchanged CC291/max78, six-language parity and scoped diff-check pass. Initial Docker bootstrap resolves the reader; final bootstrap follows shared-validator movement. No live external service, paid provider, administration, commit or push. Installing/updating/deleting/importing personal skills and plugins/MCP/meetings and global qualification remain in progress.

### Slice 181 — Deferred owned skill removal port (implemented and reviewed)

- Added one observed/staged/cleanup port for a personal skill. Public gallery metadata and complete private archive/directory witnesses are rechecked before staged row removal; foreign accounts, inconsistent foreign states and plugin-owned components refuse. Database staging never unlinks files; rollback retains bytes. Post-commit cleanup obtains the same owner lock as every skill import, checks that no replacement registration exists, verifies directory/content identity and confines recursive removal to the resolved configured account tree. Changed/reinstalled directories remain untouched; an already-absent directory can settle normally. This is a shared port, not yet the native deletion tool.
- Original import finalization now acquires the account lock before quota/conflict validation and live swap, preventing a new import during post-commit cleanup. Existing fake sessions were completed with asynchronous execute; no oracle weakened.
- Verification: 60 actual PostgreSQL/shared-library import and existing import-unit cases pass (`skill-removal-final-181.log`); 19 additional owner/state/rollback/size/cycle cases pass. Strict MyPy three initial owners, unchanged CC291/max78 and scoped formatting pass; final optional-absence witness typing follows. Native/original UI deletion wiring, exact consent and lost-ack flow tests are next. No administration, commit or push.

### Slice 182 — Exact personal skill deletion and shared original UI boundary (implemented and reviewed)

- Added `skill_settings.delete` / `delete_lia_skill_tool` through original mandatory HITL, native/catalogue/bootstrap/action identities, request-only same-id editing, six-language literal consent and strict `skills` changed-field/resource registry. Consent shows current public metadata and whether files exist; complete directory/archive witnesses remain private. Fresh account/capability/owner/metadata/file observations and expiry precede staged row deletion. Unknown/cancelled commit acknowledges nothing and retains bytes. Post-commit cleanup refuses replacements and changed files; actual file/cache pending flags survive failures. Original menu deletion now reuses the same staging/known-ack/cleanup port, fixing the empirically reproduced premature unlink on lost commit acknowledgment.
- Skill editor inputs were factored into their own composition module when the shared dispatcher reached its ratchet. A multline import left during extraction was corrected immediately; imports and consent tests were replayed, the API restarted and original auth-features returned HTTPS200. No caps were raised.
- Verification: 35 actual PostgreSQL/native-original UI/confirmation Pipeline-ReAct/owner/expiry/ack/cleanup/cache/size/cycle cases pass (`skill-delete-cold-182.log`); 41 final checkpoint/private-witness/editor/HTML/i18n/registry cases pass (`skill-delete-contract-182.log`), plus 19 editor/library contracts after factoring. Strict MyPy nine owners, unchanged CC291/max78 and six-language parity pass. Actual Docker bootstrap resolves deletion. No provider/model/administration, commit or push. Personal skill install/update/file/URL/proposal import, plugins, personal MCP/sandbox, meetings and global qualification continue.

### Slice 183 — Skill import commit acknowledgement integrity (implemented and reviewed)

- TDD reproduced both fresh import and replacement restoring/removing live files after PostgreSQL had committed but its acknowledgement was lost. One typed import-commit port now distinguishes an explicit integrity rejection (safe rollback) from attempted-commit uncertainty/cancellation. Pre-commit failures retain their original restoration behavior; unknown acknowledgement preserves the newly installed bytes and raises a stable completion-unknown exception, without a success claim or automatic retry. Native install/update can now map this outcome without claiming rollback.
- Verification: 68 actual PostgreSQL/fresh-replacement/lost-cancelled-ack/original library import and existing import-unit/size/cycle cases pass (`skill-import-ack-final-183.log`), including original validation and lost-race restoration oracles. Unchanged CC291/max78 passes; strict import-port/service typing follows. No actual external source/model was contacted, no administration, commit or push. Library installation/update tooling is next.

### Slice 184 — Original library immutable previews and import fences (implemented and reviewed)

- Added a shared preview at the exact requested commit, optional owned-lock pre-swap and final pre-commit checks, and a synchronous known-commit receipt before cache reload. Existing UI callers keep the original behavior. Native checks can refuse before any live write or restore the prior package on explicit pre-commit refusal; lost commit acknowledgement never invokes the success hook. Install/update compare the original complete preview when supplied.
- Verification: 74 PostgreSQL/original library/import/lost-ack/cache-failure/size/coupling cases pass (`skill-library-fences-cold-184.log`); strict MyPy three shared owners and scoped Ruff pass, unchanged CC291/max78. Cold review covered authority timing, transaction/network separation, exact commit selection, file restoration and unknown acknowledgements. No administration, actual external source/model, commit or push. Native installation/update wiring follows.

### Slice 185 — Native personal library installation and updates (implemented and reviewed)

- Added original HITL tools `install_lia_library_skill_tool` / `update_lia_library_skill_tool`, exact immutable source/commit requests, complete original public preview/changed-file metadata, strict private old-source/archive witnesses, request-only same-source editing, six-language consent, bootstrap/catalogue/native operation identities and `skills` changed-field registry. Original UI library reads now refresh only their owner and hide prior-account installations; the shared account-query hook accepts original query parameters/revisions.
- Native writes re-use original SSRF/audit/name/quota/provenance/import/rate-limit ports. Read transactions end before HTTP. Shared owner and skill locks protect exact old state before swap; fresh authority/expiry are checked again before commit. Unknown acknowledgements cannot report success; known commits report pending cache refresh on propagation failure. Cold TDD caught and corrected two original refusal translations: a final expiration was mistaken for a name conflict, and authorization revoked during import was mistaken for an invalid skill. Pre-commit cancellation restores old files; registration identity races retain their original conflict behavior.
- Verification: 81 import/original-regression/consent/checkpoint cases pass, followed by 43 final actual PostgreSQL/late-revocation/HITL Pipeline-ReAct/shared-library/size/coupling cases (`skill-library-native-reviewed-185.log`). Sixteen Docker frontend cases, clean nonincremental TypeScript, scoped ESLint, strict MyPy ten owners plus two changed fence owners, unchanged CC291/max78, six-language parity and scoped diff-check pass. Actual Docker imports resolve both tools; original auth-features returns HTTPS200. No full LLM graph/paid provider or actual remote library was exercised; no administration, commit or push. File/URL imports and original generated-skill proposal qualification remain.

### Slice 186 — Read-only original upload validation and shared URL limiter (implemented and reviewed)

- Extracted the original safe parsed-skill UI projection and per-account URL limiter without changing their semantics. The original upload staging, validation, package integrity, provenance/name-conflict and quota checks now expose a read-only strict package preview with complete relative file metadata; no instructions, file contents or temporary/live paths escape. Upload imports accept the same pre-swap/final-commit/known-commit boundaries already proved for library imports. UI aliases preserve existing callers.
- Verification: 97 actual PostgreSQL/package-preview/original upload/URL-fetch/endpoint/SSRF/metadata/size/coupling cases pass (`skill-upload-preview-cold-186.log`), plus the strict metadata-growth/checkpoint guard. A fixture was corrected to use the actual declared-resources heading read by the original validator. Strict MyPy four owners, scoped Ruff/diff-check and unchanged CC291/max78 pass; these files remain within the global size ceiling, so no cap needs weakening or increasing. Cold review covered original validation parity, read-only staging cleanup, body/path exclusion and unchanged shared rate-key/fail-open policy. Native URL/file wiring follows; no remote provider/source, administration, commit or push.

### Slice 187 — Native exact personal skill URL imports (implemented and reviewed)

- Added `import_lia_skill_url_tool` / `skill_url.import` through original mandatory HITL, exact-source same-target request-only editing, original action/catalogue/bootstrap identities, six-language consent and addressed `skills` changed fields. Original bounded HTTPS/pinned-DNS/SSRF/no-redirect/deadline fetch and shared URL limiter are reused. Complete original public package/file metadata is displayed; raw package bytes and complete old local state are represented only by private digests. Remote byte changes or owned-file/source/state changes require fresh approval; replacements require an explicit compatible owned skill id. Shared owner/skill locks and fresh account/capability/expiry checks precede swap and commit; unknown acknowledgement never reports success, known commits report pending cache refresh. Shared absent-target checks now also refuse account-directory links before library installation.
- Verification: 62 final actual PostgreSQL/URL/library/HITL Pipeline-ReAct/request-schema/private-witness/checkpoint/i18n/size/coupling cases pass (`skill-url-native-cold-187.log`), including compatible owned replacement, changed remote/local content, feature refusal, lost ACK and cache failure. Original Windows newline normalization was reflected in the success oracle without changing import semantics. Strict MyPy seven owners, scoped Ruff/diff-check, unchanged CC291/max78 and six-language parity pass. Actual Docker bootstrap resolves the URL tool; auth-features returns HTTPS200. Existing frontend `skills` subscription serves the action; no extra UI component was introduced. No full LLM graph, actual remote source/provider, administration, commit or push. Browser file import and original generated-skill proposal qualification remain.

### Slice 188 — Original-browser personal skill file imports (implemented and reviewed)

- Added `import_lia_skill_file_tool` / `skill_file.upload` with original mandatory HITL followed by explicit local file consent on the originating authenticated browser. The model receives no local bytes/path/instructions. An optional owned compatible replacement freezes public metadata and a private whole-file witness; identity, metadata and witness cannot separate in a serialized selection. Original compressed/unpacked/member/integrity/quota/provenance checks apply. Fresh authority, exact old state, expiry and the one-use approval claim precede multipart parsing and live writes. A per-operation body ceiling reuses the original bounded multipart parser and closes upload files on every exercised outcome.
- URL and file imports now share one original package write/commit boundary. Document and skill browser uploads share one account/command transport and accessible file-confirmation control while keeping their original endpoints. Choosing a file sends nothing; keyboard confirmation sends once; account changes abort/retire local material; deadlines and uncertainty prevent replay. Six-language cards/progress labels display the exact replacement, real limits and actual cache-refresh state. Known saved-package evidence survives a later upload-cleanup failure; unknown SQL acknowledgement preserves bytes without success or replay. Cold review covered ownership/provenance, whole-package replacement, retained callbacks, focus, finite errors, private context, bounded memory and post-commit truth.
- Verification: 58 final actual PostgreSQL/Redis/original-HITL Pipeline-ReAct/file/new-and-replacement/foreign-and-managed-target/changed-local-state/oversize/late-revocation/invalid-package/lost-ACK/cache-and-cleanup/strict-checkpoint/size/coupling cases pass (`skill-file-closed-188.log`); original URL and multipart regression cases also pass. Twenty-five Docker frontend upload/interaction cases pass; the pre-existing interaction suite emits act warnings. Clean nonincremental host and Docker TypeScript, scoped ESLint/Ruff, strict MyPy twelve owners plus final changed-boundary passes, six-language parity, unchanged CC291/max78 and scoped diff-check pass. No quality cap was raised. An endpoint insertion initially broke a neighboring exception chain, was corrected immediately, and actual Docker bootstrap then resolved the file tool with original auth-features HTTPS200. Replacement fixtures were corrected to use the original dictionary return and original managed-provenance policy. No full LLM graph/paid provider/actual remote source or mobile browser was exercised, no administration, commit or push. Existing chat proposals, plugins, personal MCP/sandbox, meetings and global qualification continue.

### Slice 189 — Original chat-skill asset restoration and disk-worker lifetime (implemented and reviewed)

- Actual PostgreSQL/disk tests reproduced partial new packages surviving a failed binary-asset carryover, and rollback/staging cleanup finishing while a cancelled filesystem worker could still write. Carryover now belongs to the original pre-commit restoration boundary. Live swap, asset carryover and rollback finish their single owned worker before cancellation releases the owner's lock or temporary package; repeated cancellation does not launch another disk write. Swap cancellation propagates inside the restoration boundary. Original known/unknown SQL commit behavior is preserved.
- Verification: 68 original proposal/import/actual PostgreSQL cases pass (`skill-chat-final-189.log`); 57 native file/URL/size/coupling regressions pass (`skill-chat-boundary-reviewed-189.log`), followed by four final actual disk/error/repeated-cancellation cases after decomposition (`skill-chat-cancel-final-189.log`). Strict MyPy two owners, scoped Ruff/diff-check and unchanged CC291/max78 pass. The original proposal click remains the sole installer and its existing action recorder records a successful install once. No quality cap was raised; no provider/model, administration, commit or push. Original proposal capability/account/unknown-outcome integration, plugins, personal MCP/sandbox, meetings and global qualification remain.

### Slice 190 — Existing chat proposals join management availability and account lifetimes (implemented and reviewed)

- Reused `import_user_skill` as a declared application-tool alias rather than creating another generator. Preparation, the original manual install click, owner-locked pre-swap and final pre-commit recheck current account/application/skills availability; original chat-generation opt-in and package rules remain. The package import exposes the same optional fences/known-commit port as file/library imports. The request read transaction ends before Redis lookup/claim. Authorization refusals return finite model codes without diagnostic payloads. Existing proposal reads/retained install callbacks/private files and local card state now follow account lifetimes; a late result cannot update another account or its skills revision.
- Verification: 54 original/native-catalogue/size/coupling cases pass (`skill-proposal-reviewed-190.log`), followed by 36 final actual PostgreSQL/Redis/menu-ceiling/prepare-click-late-revocation/request-transaction/original-proposal/tool-refusal cases (`skill-proposal-final-190.log`). Twelve Docker frontend card/account/private-file/retained-callback cases pass, clean nonincremental host and Docker TypeScript, scoped ESLint/Ruff, strict MyPy three owners, unchanged CC291/max78 and diff-check pass. Original unit fake sessions were completed with the real asynchronous session interface and fence arguments. Actual Docker bootstrap resolves the alias and auth-features returns HTTPS200. Existing API-refusal simulations log their expected errors. No provider/model, administration, commit or push. Original proposal attempted-commit uncertainty still requires qualification; plugins, personal MCP/sandbox, meetings and global qualification follow.

### Slice 191 — Original proposal durable attempt and uncertain completion (implemented and reviewed)

- A Redis compare-and-set stores the one-use attempt before import and retains the original expiry. Only that attempt may settle it. Unknown SQL acknowledgement retains an explicit unknown state and prevents another import; an interrupted attempt also refuses replay. Known commit evidence survives later cache or Redis failure, records the action truthfully and reports cache refresh pending. Pre-commit refusals restore pending state. The card scopes uncertainty to the account/proposal and offers a read-only result check; an unclassified network failure never offers another install. Private attempt identifiers do not enter public responses. Review narrowed exception handling so process-exit exceptions are not swallowed.
- Verification: real PostgreSQL/Redis concurrent-claim, late authority, expiry and lost-commit-ACK tests passed among 67 green cases; the remaining serialization field guard was updated to test all four states with nondefault private fields. The final 55 unit/serialization/commit-cache-cancellation/settlement-loss/size/cycle cases pass (`skill-proposal-final-191.log`). Eighteen Docker frontend cases, clean host and Docker TypeScript, scoped ESLint/Ruff, strict MyPy five owners, six-locale parity and unchanged CC291/max78 pass. Actual Docker bootstrap resolves the original alias and `/auth/features` returns HTTPS200 (`skill-proposal-bootstrap-191.log`). No full model/provider or mobile browser proof, administration, commit or push. Plugins, personal MCP/sandbox, meetings and global qualification continue.

### Slice 192 — Shared personal plugin settings projection and native read (implemented and reviewed)

- Added `get_lia_plugins_tool` / `plugin.read` to native operation, manifest, management switch and actual bootstrap registries. The original settings endpoint shares a three-query projection instead of querying both component tables per plugin. Every query filters the account explicitly, including malformed cross-account provenance links. Strict bounded pages retain exact totals, continuation and original public fields; manifest, endpoints, credentials and package instructions are never selected. Instance plugin availability and fresh active account/application authority are rechecked. Six-language progress labels and an explicit public-schema growth guard prevent silent new-field exposure.
- Verification: 24 real PostgreSQL/owner/malformed-provenance/paging/revocation/schema/size/cycle cases (`plugin-read-cold-192.log`) and 20 original-route/catalogue/bound-tool-contract cases (`plugin-read-parity-192.log`) pass. Strict MyPy five owners, scoped Ruff, six-locale parity, unchanged CC291/max78 and scoped diff-check pass. Actual Docker bootstrap resolves the new tool and `/auth/features` returns HTTPS200. Cold review covered SQL statement count, actor injection, private-field selection and both-mode catalogue parity. No browser/model/provider, administration, commit or push. Plugin actions and remaining personal domains follow.

### Slice 193 — Complete plugin group ownership before original uninstall (implemented and reviewed)

- The original group uninstall now loads and locks the complete plugin/skill/server group under the same account lock used by skill imports. It checks the plugin account, every skill and server owner, system-skill exclusion and foreign skill-state links before disk, pool or row deletion. Malformed provenance cannot make an owned plugin delete another account's component. Missing/foreign plugins retain the original nondisclosing not-found contract. The same typed group port will provide exact native confirmation.
- Verification: 31 actual PostgreSQL/owned-and-foreign-group/original-plugin-import/update/uninstall/router cases pass (`plugin-group-cold-193.log`). Strict MyPy two owners, scoped Ruff, unchanged CC291/max78 and size/cycle guards pass. Cold review verified lock ordering, identity-map refresh, complete-group checking before the first effect and the original import path after extraction. Disk/commit failure handling and native confirmation follow in the next slice; this slice does not claim that uninstall completion is yet fully qualified. No administration, commit or push.

### Slice 194 — Original plugin removal commit truth and reversible file quarantine (implemented and reviewed)

- The original uninstall delegates to one group-removal port. Whole owned directories are renamed into account-local `.lia-removal` staging before one row commit; confirmed pre-commit rejection restores them, including cancellation during rollback. Failed or unacknowledged commits preserve recoverable staged bytes and cannot report success. Known commits precede bounded file/pool/cache cleanup and retain explicit pending flags. Staging is explicitly excluded from the original skill loader, preventing retained removed skills from reappearing. Every filesystem target is an absolute checked descendant of the same account; linked paths and replaced directory identities refuse, restoration never overwrites a new directory. Existing bounded worker-lifetime handling is reused. Optional owner-locked preparation/final-commit/known-commit hooks support the forthcoming native approval.
- Cold review found the existing MCP disconnect helper swallowed transport errors; an opt-in strict path now reports real cleanup failures while preserving old callers. Verification: 51 real PostgreSQL/commit-loss/authority/group/file-and-pool-and-cache-failure/staging-discovery/size/cycle cases (`plugin-removal-reviewed-194.log`) and 40 MCP-contract/strict-transport/cancelled-rollback/path-containment cases (`plugin-removal-mcp-194.log`) pass. Strict MyPy four owners, scoped Ruff and unchanged CC291/max78 pass. One auth probe during dev reload returned no connection; the subsequent actual Docker container probe was healthy and the original HTTPS `/auth/features` returned 200. Native exact confirmation follows; no administration, commit or push.

### Slice 195 — Native exact complete plugin removal through original HITL (implemented and reviewed)

- Added `delete_lia_plugin_tool` / `plugin.delete` to native/action/catalogue/bootstrap/switch/canonical/editor/field registries with six-language consent and progress labels. Original human confirmation displays the complete owned plugin and skill/server names. Private complete plugin/skill/MCP rows and bounded full no-link file trees are sealed; instructions, credentials and local paths never enter the draft. Group/owner locks, fresh authority and expiry precede reversible staging and commit. A final witness rechecks the moved files before commit, catching a change during staging and restoring the recoverable changed bytes. Unknown ACK cannot claim success or replay; known receipts report actual file/pool/cache pending flags. Group resource fanout is shared with existing peer removal, keeping complexity unchanged. Plugin list reads and retained mutation callbacks follow account lifetimes and the original menu subscribes to owned plugin changes.
- Cold verification: 35 non-flow native/schema/tree/budget/size/cycle cases passed in `plugin-delete-final-195.log`; its four original-HITL failures exposed incorrect preparer keyword names and were corrected against the real signature, followed by eight green flow/contract cases (`plugin-delete-flow-195.log`). Thirteen final actual PostgreSQL/change-during-staging/authority/lost-ACK/Pipeline-ReAct/refusal-to-replay cases pass (`plugin-delete-late-fence-195.log`). Eighteen Docker frontend original-menu/account/SSE cases, clean host and Docker TypeScript, scoped ESLint/Ruff, strict MyPy eight owners plus final three/one/two boundary passes, six-locale parity and unchanged CC291/max78 pass. A detected reverse domain import was removed instead of widening the cycle baseline; Windows path/descriptor timestamp differences were corrected using the original archive's identity checks. Actual Docker bootstrap resolves the tool and `/auth/features` returns HTTPS200. These are original executor/context simulations, not full model-driven graph/provider/mobile proof. Personal MCP menu subscription and transient dialog account scope follow with UI integration; plugin imports and remaining domains still remain. No administration, commit or push.

### Slice 196 — Original plugin/MCP menu refresh, credential-form lifetime and scoped feedback (implemented and reviewed)

- The original personal MCP reader now uses the same account-owned query port as plugins and subscribes to `user_mcp`, completing the plugin group's three-menu fanout. All eight original MCP writes/probes/OAuth/description handlers pass through one retained-callback/result guard; an old account cannot initiate a request or redirect the current browser. Plugin/MCP temporary form, credential, report, dialog and test state use the existing account-lifetime state primitive, including return to the same account. Shared scoped Sonner feedback retires late private notices. Original plugin rows stay mounted on refresh, with busy announcements and keyboard-preserving controls/handler guards. The original typed MCP test fixture is shared across legacy and actual-query scope tests.
- Verification: first reproduced two plugin dialog/focus failures and three MCP account/fanout/retained-write failures, then 73 Docker original settings/form/credential/OAuth/mutation/account/A-to-B-to-A/scoped-feedback cases passed (`plugin-mcp-ui-reviewed-196.log`). Clean final nonincremental host and Docker TypeScript, complete scoped ESLint with no warnings, unchanged frontend CC42/max50, hooks30/25 and a11y0 ratchets, and scoped diff-check pass. Reactive account-state setter dependencies were explicitly fixed using the TypeScript AST, without suppressing lint. Cold review covered credential-form reset, late callbacks/results/notices, list focus and exact owned group resource routing. No browser/mobile/model/provider proof, administration, commit or push. Plugin imports and remaining personal domains/global qualification continue.

### Slice 197 — Original read-only plugin package preview with secret-free scope (implemented and reviewed)

- Added one read-only package-preview port using the original bounded ZIP stage, manifest validation, component discovery/frontmatter identities, MCP validation and exact original script-extension discovery. It exposes complete relative file metadata, public plugin identity, incoming skill names, transport/support taxonomy and endpoint host only. Header values, endpoint query/userinfo, extension secrets, command contents, skill instructions and local staging paths are excluded. Source and projection schema-growth guards require explicit review when package/transport fields evolve. Existing bounded worker completion keeps private staging alive through repeated cancellation, then cleans it without any database write, network probe or model invocation.
- Verification: 110 original package/manifest/transport/security/preview cases pass (`plugin-preview-cold-197.log`), 15 preview/size/cycle cases (`plugin-preview-reviewed-197.log`), and five final private-data/source-growth/repeated-cancellation cases (`plugin-preview-final-197.log`). Strict MyPy one owner, scoped Ruff and unchanged CC291/max78 pass. Cold review corrected conservative script detection to use the original loader's allowed extensions and checked empty/unsupported transport handling and staging lifetime. Native file/URL import and original multi-component write/commit fences follow; no administration, commit or push.

### Slice 198 — Original plugin root commit preserves acknowledged and recoverable versions (implemented and reviewed)

- Replaced the original delete-before-rename root swap with a shared bounded-worker commit port. Unique account-local incoming/predecessor slots replace the shared temporary name; every absolute target is checked for account containment and links. Definite pre-commit/SQL-integrity refusal restores the predecessor or removes an uncommitted fresh root. Unknown acknowledgement retains the live new version and recoverable predecessor. Known commit precedes predecessor cleanup; replacement identities refuse destructive cleanup, and failures return a truthful pending flag surfaced by the original import report/dialog in six languages. The obsolete static swap was removed after confirming no caller remained. Worker lifetime and cancellation-safe restoration reuse the original shared disk boundary.
- Verification: 40 original root/import/preview/size/cycle cases (`plugin-root-cold-198.log`), 26 actual PostgreSQL/original-service/ack-loss/refusal cases (`plugin-root-db-198.log`), ten final fresh/replacement/root-identity cases (`plugin-root-identity-198.log`) and eight Docker original report/settings cases pass. Strict MyPy three owners, clean host and Docker TypeScript, scoped ESLint/Ruff, unchanged CC291/max78, six-language parity and scoped diff-check pass. Actual Docker service import and `/auth/features` return HTTPS200. Cold review caught and fixed the fresh-root rollback case and registered private incoming identities before copy so partial copy cleanup stays scoped. This qualifies the package ROOT commit, not all per-component commits or dropped-component cleanup: those still need the next fences before exposing native imports. No administration, commit or push.

### Slice 199 — Original plugin update refuses foreign component groups before writes (implemented and reviewed)

- Reused the complete typed group ownership validator before updating the plugin row, importing components or removing dropped members. Malformed cross-account skill/server provenance fails before any live mutation. Original unit fixtures mock the shared group port; PostgreSQL cases exercise its real checks.
- Verification: both database regressions failed on the previous implementation, including a changed plugin version and deleted skill before refusal. All 20 original-import/database cases now pass (plugin-update-scope-green-199.log), with 12 size/cycle guards, strict MyPy and scoped Ruff/Black. Cold review checked placement before every component write and reuse of foreign skill-state/system-skill guards. No administration, commit or push. Endpoint validation and component commit fences remain for the import lot.

### Slice 200 — Plugin endpoint updates reuse original MCP SSRF and reconnection checks (implemented and reviewed)

- Removed the direct endpoint-update bypass. Existing plugin servers use the original ownership/endpoint-validation/pool-invalidation service before refreshing package headers; credentials remain untouched. Rejected endpoint updates retain previous endpoint and headers and are reported as skipped using the original component taxonomy.
- Verification: both actual PostgreSQL cases first failed because the SSRF validator was never called. All 20 database/original-import cases now pass (plugin-endpoint-green-200.log); strict MyPy, scoped Ruff/Black and unchanged CC291/max78 pass. Cold review checked refusal before header writes, credential preservation, existing-name conflicts and successful reconnect invalidation. No remote connection, administration, commit or push.

### Slice 201 — Dropped skill files follow the package commit (implemented and reviewed)

- Reused the uninstall port's checked account-local moves for components dropped by an update. Live bytes move outside the skill scanner before deletion; definite failure restores them, unknown commit acknowledgement retains them, and known commit permits cleanup. Cleanup failure is reported through the existing file-cleanup flag. Relative paths are normalized before movement, and partial-stage refusal restores already moved members.
- Verification: the previous implementation failed both refused-commit and lost-ACK file-retention cases. The original import/root/guard suite had 35 passing cases; its fixture-only failure was corrected by persisting the seed before simulating rollback. All 21 final real PostgreSQL/five-outcome/root/path cases pass (plugin-dropped-reviewed-201.log), with strict MyPy three owners, scoped Ruff/Black and unchanged CC291/max78. Cold review checked retained bytes stay outside discovery and identity-based restoration never overwrites a replacement. No administration, commit or push.

### Slice 202 — Native import fences reuse original per-skill and root commits (implemented and reviewed)

- Added optional typed hooks before the first write, before every live skill swap/commit and after each acknowledged skill/root commit. Native callers can stop immediately on revocation and retain an accurate receipt for already durable components. Authorization failures propagate instead of being converted into skipped skill reports; ordinary invalid-skill resilience is preserved.
- Verification: all three initial/successive-skill/root-refusal database cases first failed on the absent hook API. They now pass (plugin-hooks-reviewed-202.log), including one committed first skill followed by refused second skill. The original/guard run had 32 green cases; its ORM-expired fixture read was corrected using the captured owner ID. Strict MyPy two owners and scoped Ruff/Black pass. Cold review checked no root receipt on refusal and retained per-component commit semantics. No administration, commit or push.

### Slice 203 — Private package workers finish before cancellation cleanup (implemented and reviewed)

- Generalized the already bounded disk completion primitive to return one typed result. Original plugin ZIP staging, manifest/component/frontmatter reads and package preview reuse it; repeated cancellation cannot free staging while a filesystem worker is still using it. Preview's duplicate closure was removed.
- Verification: reproduced premature cleanup during cancellation on the old import path. All 36 cancellation/original-import/preview/size/cycle cases now pass (plugin-stage-reviewed-203.log), with strict MyPy four owners and scoped Ruff/Black. Cold review checked the same worker runs once and cancellation propagates before installation starts. Slice 202 callbacks were decomposed into their typed hook owner, and CC291/max78 passes (plugin-hooks-cc-reviewed-202.log); its three final database guard cases pass. No administration, commit or push. Native plugin imports follow.

### Slice 204 — Native personal plugin URL import with original HITL and complete commit truth (implemented and reviewed)

- Added import_lia_plugin_url_tool / plugin_url.import to native, bootstrap, action, editor, rendering, field and three-menu refresh registries. Public HTTPS sources reuse the original SSRF/no-redirect/size/deadline fetch and shared account rate bucket. Public package previews never include executable content, headers or credentials. Optional replacement requires the exact owned plugin ID and name; source bytes and complete previous group/files are sealed and revalidated.
- Original component writes now have fresh guards after MCP DNS validation, exact locked-row CAS and recorded expected writes. Unprocessed skill files, plugin metadata, staged predecessor roots and dropped-file quarantines are checked before the final commit. Relevant fresh Skills/MCP gates cover both incoming and removed components. Per-skill known commits produce an explicit partial receipt; unknown remaining commits cannot replay. A confirmed root commit followed by an observer failure never restores already deleted live skill files and retains a truthful committed/pending-cleanup receipt.
- Verification: 18 initial native/read/delete/hook database cases pass; the four original Pipeline/ReAct confirmed/unconfirmed wrapper flows pass. The reviewed 27-case suite covers actual independent-transaction MCP edits, partial refusal, late staging edits, source/owner checks, field and size/cycle guards (plugin-url-reviewed-204.log). Fifteen final native scenarios/flows pass (plugin-url-final-204.log); 71 original service/HITL/contracts regressions, 22 observer/root/retention cases and eight final known/unknown/partial-receipt scenarios pass. Red probes reproduced the DNS-update bypass, both late file edits and post-commit restoration defect before fixing them. Strict MyPy nine owners plus final three-owner checks, scoped Ruff/Black, unchanged CC291/max78 and six-locale parity pass. Ten Docker frontend refresh cases pass. Actual final Docker bootstrap resolves the new tool and auth/features returns HTTPS200 (plugin-url-final-bootstrap-204.log). These are original wrapper/executor/context simulations, not a full model/provider/mobile browser proof. Local plugin file upload, remaining personal domains and global qualification remain. No administration, commit or push.

### Slice 205 — One typed native plugin package write port (implemented and reviewed)

- Extracted the URL handler's write/receipt/error logic into install_plugin_package with a frozen byte-private write contract and strict shared state. Source-specific authorization is injected while the central port always rechecks plugin/account and relevant component capabilities, expiry, ownership, CAS and staged-file witnesses. The value-field vocabulary permits only the reviewed URL and browser-file families. No fake URL or duplicated installation pipeline is needed for local files.
- Verification: all 34 existing native URL/component/independent-concurrency/staging/confirmation/receipt/field/size/cycle cases pass (plugin-package-shared-205.log), with strict MyPy six owners, scoped Ruff/Black and unchanged CC291/max78. Cold review verified URL enablement remains enforced by the caller at every write and no source check can bypass the central capability or ownership fences. Browser-file transport and UI are the next lot. No administration, commit or push.

### Slice 206 — Native personal plugin browser-file import (implemented and reviewed)

- Added import_lia_plugin_file_tool / plugin_file.upload to the native, bootstrap, action, editor, rendering, field, secure browser handoff and three-menu refresh registries. Mandatory original HITL precedes explicit browser ZIP selection/confirmation; file bytes stay outside model arguments. The URL and file sources share the typed package installation port, while file upload reuses the existing skill upload claim/settlement service. Exact replacement name/owned group, originating session, current authority, extension, compressed/decompressed size, expiry and private-state witnesses are checked before effects.
- Shared original plugin report details render translated component outcomes in both settings and chat. Strict schemas declare every original report field; private debug detail is removed from native receipts. Account switching retires selected files, acknowledged uploads clear the file input, uncertain results cannot replay, and successful receipts refresh only the owning account's plugins/skills/MCP menus. Oversized package metadata fails before writes.
- Verification: 73 shared backend cases pass, followed by six final valid/wrong-name/wrong-extension cases in both orchestration modes with actual SQL/root assertions. All 27 affected Docker frontend cases pass. Strict MyPy, scoped Ruff/Black/ESLint, clean host and Docker TypeScript, six-locale parity, unchanged backend/frontend complexity and hooks ratchets, zero a11y violations and scoped diff checks pass. Docker bootstrap resolves the file tool and auth/features returns HTTPS200. Cold review checked lost acknowledgements, refused consent, late edits, foreign sessions, post-commit observer/form-close truth, receipt privacy, worker lifetime and no hidden network probe. These are real database/Redis and wrapper/executor simulations; complete model/provider/browser/mobile qualification remains. No administration, staging, commit or push.

### Slice 207 — Native personal MCP metadata and shared original projection (implemented and reviewed)

- Added get_lia_personal_mcp_servers_tool / personal_mcp.read to native, action, catalogue and bootstrap registries. Both modes read current owned servers, authentication/status, switches, timeout, HITL override, plugin provenance, credential-presence metadata and paged cached tool names/descriptions/titles. Private endpoint paths/query strings, raw errors and cached input schemas stay outside the native result; the manifest states these limitations. Server and tool pagination are bounded, the complete output has a byte ceiling, and one SQL snapshot/predicate owns the exact total and stable page.
- Extracted the original HTTP response projection instead of duplicating it, restoring its missing plugin_id. The native owner skips private cached schema validation and pages before constructing tool models. Following the existing shared-MCP pattern, startup injects a typed metadata port and shutdown clears it; missing binding fails closed and a failed connection pool does not remove read-only metadata. Field and enum growth guards require explicit review of future UI additions.
- Verification: initial absent-native-port test failed; all 60 actual PostgreSQL/native-wrapper/contract/original-schema/size/cycle cases pass, followed by three contract/lifetime cases. Both execution-mode contexts cover disabled authority, oversized output, malformed private cached schema and empty pages. Strict MyPy nine owners, scoped Ruff/Black, unchanged CC291/max78, six-language parity and scoped diff checks pass. Cold review removed an agents/user_mcp runtime cycle without widening its ratchet, bounded cached-tool construction and checked origin-free reads expose no connection or mutation. Docker bootstrap resolves the new tool. Global model/browser/mobile qualification and MCP mutations remain. No administration, staging, commit or push.

### Slice 208 — Explicit confirmed personal MCP activation (implemented and reviewed)

- Added set_lia_personal_mcp_server_enabled_tool / personal_mcp.state.update to native/action/catalogue/bootstrap, canonical rendering, amendment, executor, field and owned MCP refresh registries. Original HITL shows a concrete desired enabled boolean. A typed injected owner seals all SQL columns, checks exact ownership and full-row CAS under account/server locks, then reuses the original switch/pool service with an explicit target and fresh pre-write guard. Existing UI inversion remains compatible. Matching state is a confirmed no-op; disabling disconnects, enabling does not connect or authorize. Private endpoints/credentials and the row hash do not appear in before/after previews.
- Final receipt review reproduced two stale-observation preview failures: mutation previews previously carried pre-write timestamps as if they were resulting metadata. One typed target builder now limits both consent and receipt to exact identity/host/plugin provenance and the enabled value, while retaining the full sealed row internally. It also reduces draft context volume.
- The final reduced-target suite passes all 26 cases (personal-mcp-state-target-reviewed-208.log), with strict MyPy two changed owners and scoped Ruff/Black/diff checks. No old observation timestamp is asserted as a post-write fact.
- Verification: absent-owner tests failed before implementation. All 89 native read/state/contract/original-service/size/cycle cases pass; the final 26-case consent/expiry/replay suite adds expiry after pool await, repeated confirmed execution, tampered preview, late revocation, private-field changes and lost ACK precisely after mutation. Actual SQL state and addressed SSE refresh are asserted in both execution-mode contexts. Strict MyPy ten owners, scoped Ruff/Black, unchanged CC291/max78, six-locale parity and scoped diff checks pass. Thirteen Docker MCP-menu/SSE tests pass; the existing first account-switch hook test emits React act warnings, retained for global frontend qualification. Docker bootstrap resolves the state tool. Cold review removed a draft/pre-execution-HITL contradiction to preserve one confirmation, checked no false success on uncertain commit and kept the original connection owner. Full model/browser/mobile qualification and remaining personal MCP actions follow. No administration, staging, commit or push.

### Slice 209 — Confirmed non-secret personal MCP settings (implemented and reviewed)

- Added update_lia_personal_mcp_server_settings_tool / personal_mcp.settings.update to native/action/catalogue/bootstrap, amendment/canonical/executor/field and owned MCP refresh registries. The existing form's name, description, timeout and iterative-mode fields use a strict non-empty patch and original bounds/uniqueness validators. Only description may be cleared; blank names are refused like the form. Endpoint/authentication fields stay in the secure family, and the API-only HITL override is explicitly excluded. API and actual FormState field partitions are guarded against future additions.
- The original update service runs under the same complete owned-row CAS. Activation and settings now share one typed account-lock/current-authority/expiry/commit/receipt boundary. Previews state only exact identity and affected settings, avoiding old observation timestamps. Missing settings-owner binding refuses before HITL. Existing encrypted credentials and endpoint remain byte-for-byte unchanged, no connection or model call occurs, and confirmed no-ops emit no refresh.
- Corrected the original description-clear false positive: undefined omitted the HTTP field and did not clear SQL state. The existing form now sends the API's explicit null; its old test was corrected and failed before the fix. Four encrypted-bearer update/clear database cases confirm credential preservation. The inherited automation-alias policy test still expected immediate reversible inversion; its owner pin now reflects this task's mandatory draft/HITL policy, with explicit pins for the three new MCP tools.
- Verification: initial absent-owner tests and whitespace-name/description-clear probes failed. All 39 settings/activation/contract cases pass; the final 76-case settings/owner-policy/HITL suite adds missing-owner refusal and complete actual catalogue checks. All 59 affected Docker frontend cases pass. Strict MyPy eleven owners plus final two-owner check, scoped Ruff/Black, clean host/Docker TypeScript, full task lint:frontend, six-language parity, unchanged backend/frontend/hook/a11y ratchets and scoped diff checks pass. Docker bootstrap resolves the settings tool and auth/features returns HTTPS200. Cold review traced the original pool's timeout fingerprint, checked patches preserve encrypted credentials, and maintained one confirmation without broadening field access. Full coverage/model/browser/mobile qualification and remaining personal MCP actions follow. No administration, staging, commit or push.

### Slice 210 — Confirmed standalone personal MCP server deletion (implemented and reviewed)

- Added delete_lia_personal_mcp_server_tool / personal_mcp.delete to native/action/catalogue/bootstrap, amendment/canonical/executor/field and owned MCP refresh registries. Exact identity uses the original standalone deletion service under the shared full-row CAS and confirmed commit boundary. Plugin provenance refuses during preparation and remains enforced by the original service; no allow_plugin_owned or cross-account field exists in model input. A fresh callback after pool disconnection prevents a late revoked write. Only a known SQL commit produces the deletion receipt and refresh.
- Verification: initial absent-owner test failed. All 100 actual PostgreSQL/Redis deletion/activation/settings/original-service/size/cycle cases pass. The final 67-case deletion/contract/actual-catalogue suite adds refusal of amendment retargeting, repeated confirmation without a second disconnect, and finite lost-ACK output. Both mode contexts assert selected-row deletion, survivor-row preservation, foreign/plugin refusal, private-state conflict, late revocation, missing confirmation and lost ACK precisely after SQL deletion. Strict MyPy ten owners, scoped Ruff/Black/diff checks, unchanged CC291/max78 and six-language parity pass. Thirteen Docker MCP-menu/SSE tests now pass without the previous act warnings after synchronizing the account-switch test; clean host/Docker TypeScript and scoped ESLint pass. Actual Docker bootstrap resolves the deletion tool. Cold review checked the original pool's bounded cache removal, default plugin guard, private metadata exclusion and reuse of the shared receipt/expiry/actor boundary. Full coverage/model/browser/mobile qualification and remaining personal MCP actions follow. No administration, staging, commit or push.

### Slice 211 — Original MCP description prompt is bounded and treats metadata as external (implemented and reviewed)

- Reused the original description generation/quota/spend/fallback path. A cohesive prompt owner samples bounded public name/description excerpts, uses the existing external-content wrapper, states omissions and retains the trusted authentication scope outside that frame. The configured mcp_description slot reserves its output and system prompt before admitting input; a cached tokenizer plus conservative UTF-8 ceiling prevents growth across different providers. Too-small windows or a sample admitting no tool use the deterministic fallback before constructing/calling a provider. Generated and deterministic descriptions respect the original form's maximum length.
- The versioned prompt explicitly treats names/descriptions as data and forbids inferring unshown capabilities. Actual billing continues using the original provider usage/capture/pricing path, including paid failures; the conservative admission estimate does not replace billed token counts. No new model, provider retry, quota bypass or account/instance budget is introduced.
- Verification: initial tests reproduced an unbounded multilingual prompt, metadata escaping its frame and a paid call despite a too-small configured window. Further red probes covered an empty admitted sample and tokenizer-independent UTF-8 ceiling. All 64 bounded-prompt/original-generation/billing/service/size/cycle cases pass, with strict MyPy two owners, scoped Ruff/Black/diff checks and unchanged CC291/max78. Cold review checked header/frame/omission overhead is counted, provider construction follows budget validation, ignored schemas/credentials never enter the prompt, fallback is bounded and original account billing remains intact. Native regeneration/connection/OAuth/secure form actions and global qualification remain. No administration, staging, commit or push.

### Slice 212 — Native personal MCP description regeneration (implemented and reviewed)

- Registered regenerate_lia_personal_mcp_description_tool / personal_mcp.description.regenerate across native/bootstrap/action/catalogue/editor/canonical/field and user_mcp refresh registries, with six-language progress and consent. Preparation performs no generation. Original HITL is the sole confirmation; the preview states platform LLM spend, quota/fallback and overwrite behavior. Account security and administrator servers remain excluded.
- Reused the original accounted description service through typed owner callbacks. Release the read transaction before provider/accounting; acquire fresh actor/server authority and full-row CAS only afterwards, immediately before writing. A later revocation, expiry or concurrent modification refuses persistence, while already incurred provider spend remains accounted. Result validation follows the original bounded description contract.
- Cold review reproduced an observer failure returning the request instead of the saved description after an acknowledged commit. The shared commit boundary now records observed result values immediately upon commit acknowledgment, preserving accurate receipts and refresh behavior. Independent SQL sessions verify provider execution holds no actor row lock that could block accounting writes.
- Verification: 110 initial native/state/settings/delete/service/guard regressions pass; final 69 flow/billing/contract/actual-mutation-policy cases pass (personal-mcp-description-native-final-212.log). Strict MyPy eleven owners, scoped Ruff/Black, unchanged CC291/max78 and six-locale parity pass. Docker bootstrap resolves the actual tool. These are controlled original wrapper/executor/database flows, without a real paid provider or full model/mobile browser run. Connection/OAuth/secure form actions, meetings and global qualification remain. No administration, staging, commit or push.

### Slice 213 — Original MCP connection test exposes safe confirmation hooks (implemented and reviewed)

- Added optional typed pre-connection and pre-write guards to the existing test service. Both successful discovery and failed-connection status updates pass the fresh write guard outside the broad network-error handler; authority refusals propagate. Existing UI callers remain compatible.
- Cold review reproduced a confirmed probe swallowing a storage error. Native guarded callers now propagate persistence failures so the original executor can roll back without claiming a durable discovery result; UI callers retain their sanitized failure response. Original descriptions, embedding owner, MCP pool and accounting remain reused.
- Verification: three missing-hook cases first failed; the additional persistence-error oracle failed before its fix. All 38 hook/original-service cases pass, as did the initial 55 original generation/prompt regressions. Strict MyPy the service, scoped Ruff/Black and unchanged CC291/max78 pass. Native connection action follows; no real server, paid call, administration, staging, commit or push.

### Slice 214 — Native personal MCP connection test and accounted auxiliary embeddings (implemented and reviewed)

- Registered test_lia_personal_mcp_connection_tool / personal_mcp.connection.test in native/bootstrap/action/catalogue/editor/canonical/field and user_mcp refresh registries. Its sole original HITL explains endpoint contact, discovery, optional read_me, missing-description generation and embeddings. Existing OAuth may refresh tokens; changed stored authentication requires fresh consent before discovery persistence. Preparation never contacts a server. Failed connection_success is explicit and separate from acknowledged status persistence; raw errors, endpoint secrets and cached schemas remain private.
- Reused the original bounded ephemeral MCP client, pool/cooldown, accounted description/fallback and embedding provider. Release the read transaction before network/provider work; fresh actor/expiry and complete owned-row CAS guard both successful and failed status writes. URL policy is revalidated before contact; review reproduced and fixed a concurrent endpoint edit during the DNS await. Refusals clear the pending pool entry. Receipt values are observed stored values, including previous cached tools retained after a failed probe.
- The shared original embedding path now checks account/instance spend and usage limits, bounds public metadata, attributes provider usage to the actual account and restores the previous context on success/failure. Registered its paid chokepoint in the existing guard. No new provider/retry/rate bucket and no schema/credentials enter embedding inputs. Original client credential refresh remains in its owner.
- Verification: 82 initial native/description/state/settings/delete cases pass; 95 reviewed connection, independent-session lifetime, registry, embedding, original service and structural/quota-guard cases pass. Final 81 probe/lifetime/contract/embedding/actual-mutation-policy cases pass (personal-mcp-probe-replay-final-214.log), including failed retained cache and repeated confirmation without new network work. Forty original MCP frontend form/refresh tests pass in Docker. Strict MyPy eleven owners, scoped Ruff/Black/diff checks, unchanged CC291/max78, six-locale parity and actual Docker bootstrap pass. Controlled original wrapper/executor/database flows were exercised; no real MCP server/paid provider or complete model/mobile browser proof. OAuth/secure form actions, meetings and global qualification remain. No administration, staging, commit or push.

### Slice 215 — Native personal MCP OAuth token disconnect (implemented and reviewed)

- Registered disconnect_lia_personal_mcp_oauth_tool / personal_mcp.oauth.disconnect across native/bootstrap/action/catalogue/editor/canonical/field and user_mcp refresh registries, with six-language consent/progress. The sole original HITL selects an owned OAuth server and explains local token removal, retained client credentials and auth_required status. Provider-wide revocation, authorization and administrator shared servers remain outside this operation. No secret enters public preview, receipt or tool arguments.
- Reused the original token purge and pool invalidation behind a typed writer and complete owned-row CAS. Fresh actor/capability/expiry checks bracket the write and the common acknowledged-commit receipt; a late refusal rolls back pending credentials. Cold review reproduced unreadable ciphertext being erased while promising client preservation: native withdrawal now refuses before writing. Review also reproduced swallowed pool-invalidation failure: guarded callers require invalidation success before commit, while existing UI callers retain their previous behavior.
- Verification: 111 initial owner/flow/service/policy/structural cases and 135 reviewed neighboring MCP regressions pass. Final 118 withdrawal/contract/service/mutation-policy/size/cycle cases pass (personal-mcp-oauth-final-215.log), including both mode contexts, unconfirmed refusal, non-OAuth refusal, changed private credentials, late revocation, corrupt ciphertext, failed invalidation and repeated confirmation without another disconnect. Strict MyPy eleven owners plus the final two changed owners, scoped Ruff/Black/diff, unchanged CC291/max78 and six-locale parity pass. Typing found duplicate exact declarations; these were removed without changing unrelated code. Actual Docker bootstrap resolves the tool. No real provider or complete browser/mobile run was performed. Authorization/secure forms, meetings and global qualification remain. No administration, staging, commit or push.

### Slice 216 — Original OAuth initiation has one typed shared owner (implemented and reviewed)

- Extracted the original personal OAuth initiation into domains/user_mcp/authorization.py; the existing route delegates to it. Preserved ownership, issuer binding, scopes, flow handler/client lifetime, discovered-metadata caching and response contract. Optional typed guards run before network and before metadata persistence/delivery, outside the broad network exception handler, preparing browser continuations without duplicating OAuth logic.
- Private stored-client validation is strict and fails with a generic owner error, without embedding credentials in validation diagnostics. Provider failures log their type only and retain the original sanitized bad-gateway response. No credential is added to agent context, action registers or public status.
- Verification: initial missing-owner tests failed. All 99 shared-owner/original callback/flow/service/size/cycle cases pass, with 11 final direct owner/route cases including malformed private configuration and provider-error privacy. Updated the original wiring fixture to patch the extracted owner; the actual route remains exercised. Strict MyPy two owners, scoped Ruff/Black/diff and unchanged CC291/max78 pass. Router/service have no frozen size entry to reduce. Native secure configuration/authorization, meetings and global qualification remain. No actual provider, administration, staging, commit or push.

### Slice 217 — All personal MCP creators share a serial final quota/name check (implemented and reviewed)

- Reproduced two original concurrent creation failures against independent SQL sessions: exceeding the per-account server limit and returning a raw unique-constraint error for duplicate names. The original repository now locks the owning user after DNS validation; all callers repeat the same current quota/name checks under that lock immediately before insertion. Early checks remain fast refusals. UI, plugin imports and upcoming secure native forms reuse one owner and constraint implementation.
- Cold review checked lock ordering, rollback release, current settings at final validation, owner scoping and that network validation precedes the lock. The barrier in the real concurrency simulation also fails if a future change acquires the owner lock before DNS.
- Verification: both initial races failed on the old path; all 48 concurrency/original-service/size/cycle cases pass (personal-mcp-creation-concurrency-green-217.log). Strict MyPy two owners, scoped Ruff/Black/diff and unchanged CC291/max78 pass. No schema migration, provider call, administration, staging, commit or push. Native secure configuration/authorization, meetings and global qualification remain.

### Slice 218 — Approved private MCP configuration backend (implemented and reviewed)

- Registered configure_lia_personal_mcp_server_tool / personal_mcp.configuration throughout native/bootstrap/action/catalogue/editor/canonical/refresh registries and six-language consent/progress. The agent selects only an owned server identifier or creation; private endpoint/authentication values come from the originating live browser after the original sole HITL. The private POST uses no-store responses and the existing rate bucket. API-only hitl_required remains excluded; growth guards compare the original API and form field policy.
- Reused original typed create/update models, endpoint validation, serial creation quotas, encryption and complete owned-row CAS. Fresh actor/capability/session/expiry checks bracket network validation and persistence. Only a sanitized saved receipt enters command status; it explicitly does not claim a tested connection. No credentials, full endpoint URL or submitted body reaches the assistant, ledger or event history.
- Cold review checks unknown commit acknowledgments and unavailable post-commit settlement: neither grants automatic replay. A known database save followed by unavailable settlement remains fenced. The shared commit owner supplies observed public values, and the private route returns sanitized completion uncertainty.
- Verification: 86 boundary/structural/policy cases and ten neighboring private-route cases pass. Final 34 configuration/settlement/route cases pass (personal-mcp-private-final-218.log), including twenty controlled browser-session/database scenarios; two API/form/registration contract cases pass. Strict MyPy eleven initial owners and four final API owners, unchanged CC291/max78 and six-language parity pass. Actual Docker bootstrap resolves the tool. These are controlled service/wrapper/executor/database flows; chat form, complete HTTP/browser/mobile and real provider proof remain. No administration, staging, commit or push.

### Slice 219 — Original MCP form has one reusable field and payload owner (implemented and reviewed)

- Extracted the original settings controls into MCPServerFormFields and cohesive MCPAuthenticationFields; both use unique control identities. MCP server defaults, edit projection, validation and differential create/update payloads now belong to mcp-server-form.ts. The original settings view uses these owners; no duplicated private chat form or credential comparison is introduced. Blank credentials retain stored values and an explicit null clears the description.
- Cold review removes credentials belonging to an unselected authentication scheme from submitted payloads. Original loading buttons retain keyboard focus while duplicate clicks are guarded. New-file complexity initially failed; authentication rendering and differential authentication comparison were decomposed until every new function stayed below the hotspot threshold. The existing settings file shrank from three hotspots/max45 to two/max21; the measured global count fell to 41/max50 and its baseline was tightened accordingly. API/form growth guards now inspect the extracted actual field declaration.
- Verification: the initial shared-component import failed before implementation. All 43 shared/original form/list/refresh tests pass in Docker (mcp-form-final-219.log), plus three final strictly typed fixture tests and five API/form policy cases. Cold Docker TypeScript and final scoped ESLint pass. The full frontend gate passed its accessibility and hooks checks and identified the new complexity issue; the subsequent measured global Docker complexity gate passes after decomposition. No new native action, paid provider, administration, staging, commit or push. The private chat card follows.

### Slice 220 — Chat private MCP form and malformed-input privacy (implemented and reviewed)

- Wired the original-browser MCP command into chat through a typed private-card registry. Its modal reuses the original settings fields, validation and differential payload owner. No private read occurs before opening the approved form; creation performs no read. The existing owned-server DTO is projected locally, discarding cached schemas/diagnostics. Explicit Save is the sole sender. Fresh command/account lifetime, deadline, aborted reads, canceled submissions and single-use uncertainty retire local credentials; transient command-status read failures preserve local edits. Known completion refreshes user_mcp, restores keyboard focus and states that connection testing remains separate. Five dedicated messages have six-language parity.
- Cold review reproduced malformed HTTP body validation reflecting credentials before handler entry. A cohesive private APIRoute now emits only INVALID_INPUT with no-store/no-cache for that path, retaining bounded validation metrics; authorization errors are also no-store. Original create/update service validation and fresh approved continuation remain reused. Review also closed the original connection logger's raw provider exception text: it logs the error type only, while its sanitized public failure contract stays unchanged. Both privacy oracles failed before their fixes.
- New callback complexity and the growing chat dispatch were decomposed without raising any ratchet. New-file CC is below the hotspot threshold; strict hooks and scoped ESLint pass. Backend CC291/max78 and frontend baseline41/max50 remain unchanged after the previous tightening. Temporary proof-only TypeScript includes were removed without modifying older entries.
- Verification: 25 final shared-form/chat/dispatcher cases pass (mcp-private-dispatch-final-220.log), including expiry during a hung write, account change, read retry, mismatched receipt and no automatic replay. Nineteen private-route/neighbor/size/cycle cases and 39 original connection-service/privacy cases pass; strict MyPy two private API owners, cold Docker frontend types, scoped Ruff/Black and six-language parity pass. A fresh production bundle built successfully. All three Chromium journeys pass at 1280px/320px, including lost response, actual UI HITL, keyboard Save/focus, axe, horizontal containment and reload without secrets/replay (mcp-private-browser-final-220.log). The first desktop attempt raced server startup; replay followed an explicit HTTP200 readiness check.
- E2E compilation of this new spec and its actual fixtures passes under the existing strict options. Whole-E2E typechecking currently fails in selected-chat-avatar.spec.ts importing the application hook without its alias configuration; it is recorded for global qualification, not counted as passing here. Browser APIs were hermetically mocked, while original backend continuation/database paths were exercised in slice218. OAuth authorization, meetings and global qualification remain. No administrator tools, staging, commit or push.

### Slice 221 — Shared OAuth flow fails closed for application command correlations (implemented and reviewed)

- Added an opaque application command identifier to the original one-use encrypted OAuth state only for explicitly linked flows. The identifier grants no authority: a typed, fresh caller guard is mandatory before initiating discovery, publishing state, exchanging the code, after token-endpoint DNS validation and before returning encrypted tokens. The handler retains the correlation for the upcoming private completion bridge. Ordinary UI/native-shell flows retain their existing state and behavior; an application-linked callback invoked through the old unguarded route refuses before token exchange. No native authorization tool is offered yet.
- Cold review checks missing/malformed correlation, lost current permission during DNS/token network waits and late state publication refusal. Corrected a test setup that originally exited on missing callback configuration rather than the intended guard; the configured legacy success control now proves the network boundary is exercised. The original callback logger also leaked provider exception text: its privacy oracle failed before removing the raw message, preserving sanitized error redirects.
- Verification: 73 initial flow/owner/callback/size/cycle cases pass; reviewed neighbor coverage passes, and the final 63 OAuth flow/owner/callback cases pass (mcp-oauth-application-final-221.log), including successful linked and legacy token paths and a revocation after token issuance. Strict MyPy three owners, scoped Ruff/Black/diff and unchanged CC291/max78 pass. No real provider/token exchange, native authorization registration, administration, staging, commit or push. The originating-browser completion bridge, native action/card and controlled integration remain next; meetings and global qualification remain afterward.

### Slice 222 — Shared owned OAuth credentials persistence (implemented and reviewed)

- The existing OAuth callback and the upcoming approved continuation share one repository payload and public diagnostic owner. Added an instance service entry that performs the original ownership check and optional fresh pre-write guard under the caller's transaction; it neither commits nor opens a competing session. The historical static callback retains its own auto-committing session and existing contract.
- Cold review covers foreign ownership refusal before any guard/write, late authority refusal, exact active-state persistence, unchanged secret-free diagnostics and the original callback's session boundary. Native complete-row CAS and pool lifetime fencing remain the responsibility of the forthcoming approved writer; this facade alone is not an authorization implementation.
- Verification: both initial instance-owner cases failed before implementation. All 55 initial owner/original-service/callback/size/cycle cases pass; final neighboring owner/service/callback verification passes (mcp-oauth-credentials-owner-final-222.log). Strict MyPy two owners, scoped Ruff/Black and unchanged CC291/max78 pass. No real provider, native authorization tool, administration, staging, commit or push. Browser continuation/integration, meetings and global qualification remain.

### Slice 223 — Native personal MCP OAuth backend (implemented and reviewed)

- Registered authorize_lia_personal_mcp_server_tool / personal_mcp.oauth_authorize across the native/action/catalogue/editor/canonical/refresh registries with six-language consent. The exact sole original HITL opens a browser continuation; initiation privately returns the provider URL. Encrypted short-lived claim, metadata and credentials retain no fabricated browser authority. Callback guards freshly validate both durable approval fences, actual source-session survival, account/capability/expiry and the full owned row. Only the original authenticated browser can finalize once under both locked fences and the original owned writer. Provider return stages tokens; it neither persists a connection nor claims one. Denial/failure closes the original continuation where the correlation can be verified.
- Cold review found two concrete indirect gaps and repaired them: metadata necessary for later OAuth refresh must survive privately until the same final save; a delayed old client must not overwrite a newer authorization/disconnection or receive credentials for a changed endpoint. Refresh persistence now compares original owner/configuration/token witnesses under the actual row lock and shares the existing token writer. Invalid grants also use that guard. Provider exceptions log types only. Discovery waits hold neither row locks nor SQL transactions; the real integration simulator asserts that boundary.
- Verification: the initial linked-owner tests failed before implementation. Final 112 OAuth/refresh/original/contract/size/cycle tests pass (oauth-back-unit-final-223.log); 26 actual PostgreSQL/Redis scenarios pass (oauth-back-integration-final-223.log), including lost commit acknowledgment and unavailable settlement. After transaction-release tightening, all fourteen native continuation cases pass again (oauth-no-network-transaction-223.log). Thirty-one original auth/factory/retired-client tests pass. Strict MyPy all 26 owners, scoped Ruff/Black and unchanged CC291/max78 pass. Actual Docker bootstrap resolves the new tool. Provider traffic is controlled, not a real grant; full graph/browser qualification remains. No administrator tools, staging, commit or push. The chat card and callback return UX follow in slice224, then meetings and global qualification.

### Slice 224 — OAuth chat card and provider return (implemented and reviewed)

- Added the native OAuth card to the existing private-interaction dispatcher. Explicit provider opening and original-browser completion are separate once-only requests. The private URL is validated before the original safe-navigation/native-shell owner receives it and never rendered, logged, or published to action data. Resuming commands reconstruct only their safe prior selection. Account changes/expiry abort transport and discard stale callbacks. Lost responses permit observation only; a verified HTTP409 OAUTH_PENDING permits another explicit completion check before any token has been consumed. Coherent saved receipts retain success across a later status-read failure and refresh the owned MCP views.
- Callback staging returns desktop browsers to chat. The original native MCP deep-link still lands on its existing settings route, where a validated opaque pending command marker navigates to a fixed local chat path. Provider return is informational, separate from a saved authorization or tested connection. Six-language action/consent/progress copy is registered. Cold review checks URL schemes, wrong command/server receipts, pending-error status, duplicate clicks, focus retention, late account callbacks, expiry, and all original callback redirects. No arbitrary redirect target comes from query data.
- Verification: the initial card import failed before implementation; final 44 frontend card/dispatch/private-form/return tests pass (oauth-front-reviewed-224.log). Twenty-five callback/native/size/cycle cases pass (oauth-return-final-224.log). Cold frontend types and strict scoped lint pass, six-language parity passes, and the frontend ratchet remains 41/max50 across forty files. The new E2E spec and its actual fixtures compile under strict existing options. A fresh production bundle succeeds; all three Chromium journeys pass at 1280px/320px, including original UI HITL, provider redirect/return, keyboard completion, axe, horizontal containment, lost response, reload and no double save (oauth-browser-224.log). APIs/provider were controlled; real SQL/session/approval paths were exercised in slice223, not a paid real grant or full graph here. Proof readiness required HTTP200 after startup; proof container/server are removed/stopped, port3020 closed, temporary tsconfig includes removed and ordinary Next types regenerated. No administrator tools, staging, commit or push. Meetings and global qualification remain; whole-E2E alias issue recorded in slice220 remains for that qualification.

### Slice 225 — Future meeting preferences (implemented and reviewed)

- Registered the current-owner read and exact HITL update in the native operation/tool/catalogue registries, executor, safe amendment inputs, canonical preview, startup/shutdown and addressed state-change vocabulary. Five existing preference fields are covered; the original retention ceiling remains readonly. Sparse proposals preserve unrequested fields, show the original retention clamp and retain a complete sealed CAS witness. No recording, transcription, model call or email is started.
- Reproduced the original first-write race with two independent PostgreSQL transactions: one original UI write failed on the unique owner constraint. Both UI and native writes now serialize on the active owner's row; template deletion takes that same lock before clearing its default reference. Preference reads refresh the identity map. Fresh capability, actor, expiry, preference values and ceiling are checked before commit. Lost commit acknowledgment cannot claim success or authorize replay.
- The original settings hook now reuses account lifetime/query/state and addressed-resource synchronization. Obsolete save callbacks are refused before sending a request; late replies cannot populate another account. Local edits belong to their account, survive refresh and remain mounted while known preferences are reread. Six-language confirmation/progress copy is complete. A schema/engine guard requires new original fields to gain native coverage.
- Cold review: checked full replacement parity, locking order, built-in/owned default-template resolution, clamping, strict input types, no-op effects, fresh switch refusal, uncertain commit receipts and account ownership. Verification: 42 focused unit/original-template/size/cycle cases pass; eight real PostgreSQL confirmation/concurrency cases pass; eighteen frontend account/refresh cases pass. Strict MyPy seventeen native sources, frontend cold types, scoped lint, six-locale parity, backend CC291/max78 and frontend CC41/max50 pass without relaxing ratchets. Docker bootstrap resolves both tools. Full graph/browser qualification and remaining meeting operations follow. No administrator tools, staging, commit or push.

### Slice 226 — Owned meeting and template reads (implemented and reviewed)

- Registered both readonly tools in the operation, catalogue, tool and boot/shutdown owners. Reads reuse the original UI services for exact newest-first totals, active recording/interruption, detail metadata/costs, minutes, encrypted transcripts, captured template and localized builtin/owned template library. Full detail and list fields are explicitly classified and guarded against new unreviewed fields. Raw audio/storage paths, credential ciphertext and provider diagnostic messages are excluded.
- Large private content is explicitly paged as JSON fragments with character offsets, exact full length and a stable digest. Continuing a changed source refuses the old revision. The same treatment covers a template's instructions. Native pages are then measured with the house tokenizer under the existing ReAct result ceiling/window predicate, conservatively used in both modes. Dense Unicode and special-token spellings are counted as literal data; no Latin fallback. Text is shortened with a coherent continuation; lists retain whole items and their original totals. An impossible metadata budget refuses the read rather than returning broken JSON. Actual provider billing remains in the existing LLM accountant; these reads call no model.
- Cold review removed a redundant active-meeting query, preserved the original derived-count owner, sanitized corrupt-cipher and source-error handling, checked current actor/capability before and after reads, and verified foreign meeting/template refusals. Verification: forty combined focused/neighbor/size/cycle cases passed; the final sixteen read/budget/boot/field-growth checks pass after classification tightening. Eighteen real PostgreSQL read/preference cases pass, including encrypted transcripts, withheld diagnostics, corrupt ciphertext, live pagination and owner isolation. Strict MyPy eight read sources, scoped Ruff/Black, unchanged backend CC291/max78, six-language parity and actual Docker tool resolution pass. No admin tools, staging, commit or push.
- Docker dev auth incident qualification: actual configured LAN origins match the host addresses and CORS. A real isolated browser loads the real login UI and receives both /auth/features requests with HTTP200 and no transport failure (auth-features-real-dev-226-v2.log). The first probe missed an already-arrived response; capture was corrected before navigation. The Linux proof browser does not exercise Windows CA trust. Source reload briefly makes the API unavailable; the public features hook currently has no recovery from an initial failed read. That measurable recovery gap is handled next; the original incident is not claimed universally resolved by this positive probe.

### Slice 227 — Recover public auth availability after a transient outage (implemented and reviewed)

- Reproduced the missing recovery in two initially failing frontend tests. The existing /auth/features GET now uses a small public-read recovery hook: six bounded backoff attempts for network failures/timeouts or HTTP502/503/504, then event-driven recovery on network return, focus or mobile visibility. Disabled flags are retained as real data. HTTP400/401/403/429/500 refusals do not trigger recovery. Scheduled work and listeners are cleaned up on unmount; simultaneous events share one in-flight read. No mutation or security-account tool was added.
- Cold review checked retry reset across pending/error states, persistent outages, duplicate event requests, obsolete query lifetimes, disabled data, strict real AuthFeatures fixtures and browser-specific transport error messages. Fifty-one recovery/request/auth-neighbor tests pass; the twelve final typed-contract scenarios also pass. Scoped strict lint, cold frontend types and unchanged CC41/max50 pass. Actual Docker-dev login receives HTTP200; a separate same-page browser simulation aborts both initial feature reads and then observes a real HTTP200 automatically without navigation/reload (auth-features-real-recovery-227.log). The disposable browser bypasses its absent Windows CA trust only; it proves transport/recovery, not installation of a trusted CA. Proof containers are removed by --rm. Historical outage cause beyond observed development-worker restart is not asserted. No administrator tools, staging, commit or push. Return to meeting template mutations and remaining first-lot qualification.

### Slice 228 — Original template write integrity (implemented and reviewed)

- Reproduced three original-path failures on independent PostgreSQL transactions before fixing them: two simultaneous creations both exceeded a cap of one; duplicating a maximum-length name failed on VARCHAR(120); a held identity-map source was copied after another session had changed it, producing obsolete name/sections. Creation, replacement and deletion now share the existing active-owner lock. Template list/detail reads refresh loaded rows, so resolution and copied-name selection observe the actual source.
- The original copied-name rule keeps its distinguishing counter while reserving suffix space within the mapped storage bound. It checks the existing name set once and uses no per-candidate SQL. Builtins retain their early readonly refusal, and default-reference clearing shares the same owner lock as preference replacement. API DTOs and public route signatures remain unchanged.
- Cold review checked lock order, real independent-session visibility, quota enforcement, copied-content freshness, maximum-length names, builtin behavior and adjacent preferences/reads. Twenty-one real PostgreSQL cases and twenty-seven original-unit/size/cycle cases pass; strict MyPy of the modified service, scoped Ruff/Black and unchanged CC291/max78 pass. No native template mutation tool is claimed yet: the corrected original owner is now ready for that integration. No administrator tools, staging, commit or push.

### Slice 229 — Confirmed personal meeting template CRUD (implemented and reviewed)

- Registered creation/copy, sparse replacement and deletion in the native operation, catalogue, tool, executor, amendment, canonical-preview, state-change and boot/shutdown owners. Every mutation uses the original HITL and original serial PostgreSQL writer. Creation seals the actual resolved copied content/name and current quota; replacement preserves unrequested fields; deletion includes the selected definition and any default-reference reset. Complete section instructions are literal data, never assistant instructions. Safe committed receipts identify the saved reference without copying instructions into action results.
- Cold review caught and removed a new agents/meetings runtime cycle by extracting the unchanged public DTOs into core and injecting the original writer through a typed port. All seven public JSON schemas match the pre-extraction schemas exactly. Disabled/failed restarts withdraw old ports. Fresh full-state checks refuse intervening edits/default changes; no-op writes emit no refresh; uncertain commit acknowledgments retain the once-only fence. A PostgreSQL simulation commits a creation then loses its acknowledgment: no success, no refresh and no second row on a repeated confirmation.
- Verification: sixty focused unit/preview/neighbor/boot/size/cycle cases and twelve native PostgreSQL cases pass; three original independent-transaction cases also passed in the preceding combined run. Eighteen preview cases cover all three actions in six languages, twelve long Unicode sections, HTML escaping, full checkpoint equality and sparse editor inputs without private witnesses. Thirteen original/account/refresh frontend hook cases pass after restoring the historical fixtures' authenticated owner. Strict MyPy fourteen sources plus three final registry/lifecycle sources, cold frontend types, scoped Ruff/Black, six-language parity and CC291/max78 pass. An added conditional refresh branch was decomposed without raising ratchets. Actual Docker bootstrap resolves all three names. Full graph/browser journeys and remaining meeting actions are still unqualified. No administrator tools, staging, commit or push.

### Slice 230 — Meeting template screen account lifetime (implemented and reviewed)

- Reproduced three failures before correction: a private unsaved form survived an A/B/A account switch, a delayed template load populated the next account's screen, and refreshing a known library unmounted its controls. The manager now mounts one complete screen lifetime per authenticated account. All its children, selection, form, preview and confirmation dialog reset together; obsolete callbacks are refused before writes and ignored before local publication. Feedback reuses the shared account-scoped toast owner. Populated refresh stays mounted with aria-busy.
- Cold review added the late save acknowledgment case and checked both the post-confirmation and pre-submit guards. Twenty real component/form/library/preview cases pass, including a save initiated by A that finishes after B arrives without a private preview or success/error toast. Scoped strict lint, cold frontend types and unchanged frontend CC41/max50 across forty files pass. No administrator tools, staging, commit or push. Native meeting limits and other original meeting lifecycle/report actions remain.

### Slice 231 — Read enforced recording limits (implemented and reviewed)

- Extended the existing owned meetings read with an explicit unpaginated limits view. It delegates to the original MeetingService.limits owner: segment cadence, maximum segment seconds/bytes, maximum recording minutes and silence prompt minutes. No meeting is created and no engine/model/recording starts. The original token budget and fresh application/meetings/actor checks still apply; no administrator setting can be written. The manifest documents units and semantics.
- The two initial contract tests failed before implementation. Cold review verifies exact original field parity with an explicit classification guard, refusal of identifiers/offsets for this view, no database commit, and unchanged paged private content behavior. Twenty-eight unit/budget/size/cycle cases and twelve real PostgreSQL read cases pass; strict MyPy five sources, scoped Ruff/Black and unchanged CC291/max78 pass. No administrator tools, staging, commit or push. Remaining meeting mutations and global qualification remain open.

### Slice 232 — Original transcript purge confirmation seam (implemented and reviewed)

- The original transcript purge now rereads and locks the owned meeting before checking its allowed status. Its optional typed confirmation validates a fresh witness before SQL and rechecks consent before commit. The witness binds identity, displayed title/status/stage, transcript presence/deletion time and a ciphertext digest; source words, raw audio and ciphertext never enter the public selection. Native no-op preserves an already absent transcript. The original HTTP interface still returns the original fresh meeting.
- Factored known commit acknowledgment into one shared typed helper, reused by templates and this purge. Lost/cancelled acknowledgments produce no success receipt. The original repository retains its default immediate-commit behavior; the service uses its deferred option for the final fresh gate. Owner-filtered meeting reads refresh loaded identities. The injected transcript port is ready for native wiring; no native tool is claimed in this slice.
- Cold review verifies changed-state refusal before SQL, late consent refusal with real rollback, minutes preservation, no-op timestamps, lost acknowledgment after an actual commit and cancellation. Sixteen unit/size/cycle cases and twenty-nine PostgreSQL purge/template/read cases pass. Strict MyPy eight sources, scoped Ruff/Black and unchanged CC291/max78 pass. No administrator tools, staging, commit or push.

### Slice 233 — Native exact HITL transcript deletion (implemented and reviewed)

- Registered the user-owned purge in operations, tools, catalogue, executor, canonical preview, sparse amendment, state-change vocabulary and startup/shutdown. Read/execute share the original ownership/status refusal through one service method. The source witness is encrypted in the command and binds the exact ciphertext revision; public previews/editing expose only the selected meeting and concrete purge scope. Six-language consent states that minutes, their document projection and retained audio remain and can contain transcript-derived passages. A receipt never claims erasure of those other surfaces or launches processing/email.
- Cold review covers strict forged-field refusal, six-language escaped preview, full checkpoint equality, hidden witnesses, changed ciphertext, missing transcript no-op, fresh capability refusal, uncertain actual commit, repeated confirmed execution, foreign ownership, live-status refusal and disabled/failed startup. Seven final native PostgreSQL cases and five original-owner cases pass; eighteen initial unit/size/cycle cases and twenty-three final preview/boot/addressed-state cases pass. Strict MyPy eleven sources, scoped Ruff/Black, six-language parity and unchanged CC291/max78 pass. Actual Docker bootstrap resolves the tool. The new meetings resource is declared frontend/backend; original screen consumption follows in slice234. Full Pipeline/ReAct/browser qualification is still open. No administrator tools, staging, commit or push.

### Slice 234 — Native meeting refresh and complete screen ownership (implemented and reviewed)

- List/detail hooks consume the addressed meetings resource through the existing synchronization owner. Rereads never send mutations; known data survives network failure. Values, totals, loading/action state and callbacks belong to their account and exact selected view; an obsolete mutation is refused before transport and late results cannot replace another account/meeting. Existing API calls and pagination/polling contracts are reused. The original page mounts one full account/meeting lifetime for local drafts, selections and dialogs.
- Cold review reproduced and fixed stopped polling after two successive network failures, a false successful-email toast after a locally refused write, resumed old-account confirmation and late error feedback. The original action coordinator now uses the shared account lifetime/toast owners, checks after consent and before navigation/publication, and retains drafts on refused saves. Eleven hook cases, three action-feedback cases and a real rendered page A/B/A private-draft scenario pass. The final combined six-file suite has twenty-seven passing scenarios. The initial Suspense fixture mounted through synchronous act and never resolved; its mount was corrected to awaited asynchronous act, without weakening the scenario. The detail fixture is shared rather than duplicated.
- Scoped strict lint, cold frontend types and frontend CC41/max50 across forty files pass. No administrator tools, staging, commit or push. Full graph/browser qualification, remaining report/lifecycle/download/email/recorder operations and first-lot final gates remain open.

### Slice 235 — Canonical template identity and legacy default clearing (implemented and reviewed)

- Two real PostgreSQL tests reproduced that an accepted uppercase UUID spelling was saved verbatim and failed to reset when its template was deleted. Default preference writes, reads, native request/state values and template-delete witnesses now share one core spelling normalizer. Authorization remains with the original template resolver. Clearing checks the indexed owner's one preference case-insensitively so existing stored spellings are also reset. The native preview includes the reset and emits both affected resources.
- Cold review covers new and legacy values, full native deletion consent, untouched unrelated fields, normal/builtin references and pending proposals' fresh state refusal. Twenty-one initial PostgreSQL preference/template cases and fifteen final identity/template cases pass. Forty-eight unit/preview/size/cycle cases pass; strict MyPy seven sources, scoped Ruff/Black and unchanged CC291/max78 pass. No migration, administrator tools, staging, commit or push. Remaining report/lifecycle actions and global first-lot qualification remain.

### Slice 236 — Original generated-report restoration owner (implemented and reviewed)

- Added an optional fresh typed confirmation to the original generated-version restore. It locks/rereads the selected owned meeting, validates its original report schema, seals complete raw current/generated revisions with a digest, preserves the location and checks consent before SQL/commit. No-op follows the original raw report-equality predicate. Lost acknowledgments cannot claim success. The repository's deferred commit is optional and preserves its original default behavior. A known saved restore retains its original indexing follow-up even if its post-commit reread fails; no-op/unknown acknowledgment does not schedule that job. Indexing completion is never claimed by the write receipt.
- Cold review found the growing meetings service exceeding the file-size cap. Extracted its coherent original patch/restore/transcript commands into minutes_commands, keeping public methods/signatures as delegates; no cap was raised. The original partial patch behavior is unchanged here and needs atomic validation with its native update integration. This port is prepared but a native report restoration tool is not claimed yet; its upcoming proposal must bind the complete version while keeping report-sized text out of model prompts.
- Six final PostgreSQL restoration cases cover current/generated edits, no-op, late refusal/rollback and lost acknowledgment; the final combined restore/transcript/native-purge run has eighteen passing cases. Five follow-up/cancellation unit cases and twelve final size/cycle cases pass. Strict MyPy six sources, scoped Ruff/Black and unchanged CC291/max78 pass. No administrator tools, staging, commit or push. Native report restoration/update, other lifecycle operations and global qualification remain open.

### Slice 237 — Native whole generated-report restoration (implemented and reviewed)

- Registered restore_lia_meeting_report_tool in the core/native catalogues, original HITL executor, canonical rendering, sparse amendment, addressed meetings invalidation and startup/shutdown. The sealed witness binds full raw current/generated versions while prompts contain only explicit summary metadata: titles, exact counts and at most twelve headings. Six-language consent says that the entire current report is replaced, report text is not displayed, source audio/transcript/location remain, and original background indexing may incur its usual cost without being reported complete. An ongoing original processing job can subsequently publish another version.
- Cold review checks full source-byte changes despite identical metadata, unknown-field/authority forgery, escaped literal rendering, checkpoint round-trip, hidden witnesses, no-op, fresh capability denial, foreign ownership, uncertain commit and replay refusal. It also fixes a restoration regression: invalid current content may be repaired from a valid generated version, with current_valid=false and the opaque raw digest retained; an invalid generated source is refused before any write. Startup withdraws stale owners before disabled/failed initialization. Original document indexing is mocked in these tests; no paid embedding or synthesis is run.
- Final combined suite has forty-four passing cases, including nine native PostgreSQL cases and six original-owner cases. Strict MyPy eleven sources, scoped Ruff/Black, size/cycle guards, six-language parity and unchanged CC291/max78 pass. Actual Docker bootstrap resolves the registered tool. The effect ledger is a controlled test double; full Pipeline/ReAct graph and browser validation are still open. No administrator tools, staging, commit or push. Original partial-report atomicity/native update, other lifecycle operations and first-lot final gates remain open.

### Slice 238 — Original partial-report atomicity and concurrent edits (implemented and reviewed)

- Four valid PostgreSQL scenarios reproduced an original template change committed before a refused report edit, missing refusal for explicit empty participant/section replacements on a report-less meeting, and lost fields across two independent sparse editing transactions. The original patch now takes a fresh meeting row lock, validates all report changes before writing the template, and commits the combination once. Template selection uses the same owner-first lock order as template deletion. Optional deferred template writes preserve the repository's original default behavior.
- Cold review covers the existing processing/template status refusals, template-only writes, sparse list clearing, full combined edits, rollback before commit, row-lock ordering and two independent transactions preserving both changed fields. The initial test data used an unknown built-in and omitted the mandatory participant label; corrected to actual source contracts before recording the four RED reproductions. Six final PostgreSQL scenarios pass; the twenty-case patch/original-service run and thirty-three-case restore regression run pass. Strict MyPy three sources, scoped Ruff/Black, twelve size/cycle guards and unchanged CC291/max78 pass. No administrator tools, staging, commit or push. Native report update and remaining nonadmin operations/global qualification remain open.

### Slice 239 — Native original sparse report editing (implemented and reviewed)

- Registered update_lia_meeting_report_tool in all operation/tool/executor/edit/preview/state/lifecycle registries. The original five-field DTO and nested report models moved verbatim to core with compatible domain re-exports; native inputs inherit the original constraints, reject ignored null values and unknown nested fields, and field-growth guards force review. The original UI and native writer share the same complete merge validation. Literal before/after data includes only selected fields; a private digest binds the complete source. Confirmed edits preserve other original fields, list replacements are explicit, and no-op skips SQL. Commit acknowledgment, fresh capability/actor checks and original indexing follow-up use the established owners.
- Cold review covers Unicode/HTML literal previews in six languages, checkpoint equality, hidden witnesses, changed unrequested body, selected-template instruction changes, template status refusal, duplicate section refusal, ownership, no-op, unknown acknowledgment, replay and original atomic/concurrent editing. It corrected misleading template copy: only the reference/name is stored; instructions shown are the definition at confirmation, and later template edits may affect the future job. The source job's current-reference resolution was inspected. Oversized entire-list replacements are refused without truncation under the existing native token/slot allowance and UTF-8 scope bound; the manifest directs that case to the application. This is a current limitation, not claimed complete large-report editing coverage.
- The final preview/boot/size/cycle/original/native suite has forty-six passing cases; twelve final native PostgreSQL scenarios pass, including selecting a template on a recording without minutes. Earlier combined report/restore qualification has sixty-six passing cases and the shared-merge regression run has forty-five. Initial fixture failures concerned original schema defaults and the source template-update signature; fixtures now use the exact originals. Strict MyPy fourteen sources plus five changed sources after factorization pass; scoped Ruff/Black, six-language parity and unchanged CC291/max78 pass. The complexity gate caught a new CC16 function; shared validation removed it without raising a cap. Actual Docker resolves both report tools. Full graph/browser and first-lot final gates remain open. No administrator tools, staging, commit or push.

### Slice 240 — Read original generated minutes before restoration (implemented and reviewed)

- Added generated_report to the existing owned meeting reader, with an explicit generated-version marker, original report validation, shared Unicode fragments, revision digest, token/window allowance and byte bound. Current report and generated report remain distinct observations. This launches no restoration, provider request, indexing, email or recording. Missing generated content is explicitly unavailable; foreign meetings use the original indistinguishable 404 owner rule.
- Cold review covers missing/invalid generated content, sanitized failures without raw malformed text, separate edited/generated versions, lossless continuation, changed-source refusal and foreign ownership. One PostgreSQL RED reproduced the unavailable view. The final combined unit/PostgreSQL suite has thirty-one passing scenarios; twelve size/cycle guards, strict MyPy three sources, scoped Ruff/Black and unchanged CC291/max78 pass. No administrator tools, staging, commit or push. Remaining meeting delivery/lifecycle/deletion/device actions and global first-lot qualification remain open.

### Slice 241 — Confirmed current-minutes PDF transfer (implemented and reviewed)

- Registered download_lia_meeting_pdf_tool in the native operation/tool/edit/preview/lifecycle registries and reused the original authenticated, origin-bound, single-use browser transfer. Consent identifies the complete current report, filename, language and exact counts; a private digest binds dated headers and full report content. Rendering occurs after original HITL confirmation and fresh ownership/capability checks. Frozen bytes survive later source edits. The result states download_requested, never that the user saved or read the document. No synthesis, email or indexing is launched.
- Cold review detached PDF content from ORM objects before the original CPU renderer runs in a thread, with event-loop and request-task header tests. Real browser verification reproduced a portrait covering confirmation at 320 px; the existing chat stacking context now rises only while a decision or transfer awaits user interaction. No forced clicks, hidden portrait or avatar behavior changes were used. Desktop success, 320 px success and transfer failure pass with keyboard, accessibility and containment checks. The owned temporary HTTP proof server was stopped and only its generated type configuration changes were restored.
- Final backend qualification has forty-three passing cases, including twenty PostgreSQL/original-HITL/real-effect-ledger cases across both execution-mode contexts. This is not full graph proof. Thirty-three front tests and three browser journeys pass. Strict MyPy ten sources and three changed sources, cold front TypeScript, scoped lint/format, six-language parity, size/cycle guards and unchanged complexity ratchets pass. Actual Docker bootstrap resolves the tool and the original renderer produces PDF bytes. No administrator tools, staging, commit or push. Email, remaining lifecycle/deletion/device actions and first-lot global qualification remain open.

### Slice 242 — Confirmed original minutes email (implemented and reviewed)

- Registered email_lia_meeting_report_tool across native/tool/executor/amendment/preview/state/lifecycle declarations. The only model request is an owned ready meeting id. Literal consent shows the account recipient, platform sender, subject, language, counts and previous send date; the entire current HTML/plain-text body and dated headers are privately sealed without exposing them in prompts. The original renderer, SMTP service and send-date writer are reused, with owner-first locking and fresh capability/expiry checks immediately before sending. A distinct new confirmation can intentionally resend; the same claimed action never does.
- Cold review distinguishes known SMTP acknowledgment from recipient receipt and from subsequent database metadata persistence. Lost acknowledgment, cancellation and false SMTP result refuse automatic replay; an acknowledged send retains its truthful receipt when metadata fails. The existing SMTP worker now has a finite socket timeout and logs only error type at ERROR. Actual PostgreSQL/Redis tests reproduced and fixed a missing addressed state field and a generic quota refusal: native email consumes the existing account email-share window and returns RATE_LIMIT_EXCEEDED without sending. No real email, synthesis or embedding is performed.
- Six initial source-contract REDs, one SMTP timeout RED and state/quota integration REDs precede their implementations/fixes. The original-delivery/email regression run has ninety-two passing cases; the final native/preview/boot/size/cycle run has sixty, including thirty-two original-HITL/real-ledger/PostgreSQL scenarios across both mode contexts. Full Pipeline/ReAct graphs are still unexercised. Strict MyPy eleven sources plus four reviewed sources, scoped Ruff/Black, six-language parity and unchanged complexity ceilings pass. Actual Docker bootstrap resolves the tool. No administrator tools, staging, commit or push. Remaining meeting lifecycle/deletion/device actions and first-lot final qualification remain open.

### Slice 243 — Original guarded retry and audio transaction integrity (implemented and reviewed)

- The original retry now accepts optional typed consent, locks the owner before the meeting, binds the complete row and streamed owned audio content, checks state and capability before SQL/commit, and publishes a receipt only on known commit acknowledgment. A refused status transition is now a refusal rather than a reported success. The original repository retains its default commit behavior; the service requests one deferred transaction. The prepared gateway launches the original durable processing worker only after a known saved requeue, even if its subsequent read fails. It never reports processing complete. Native tool wiring is the next slice.
- Cold review reproduced stop committing while an accepted last segment was still writing. Segment acceptance and stop now share a fresh meeting row lock. A repeated-cancellation test reproduced the disk thread outliving its caller; the atomic segment writer now waits for that one physical effect before propagating cancellation, so ordinary request cancellation does not release the new row lock during the write. This does not establish hard-kill behavior across workers. Audio witnessing streams bounded blocks in a worker, refuses foreign paths/symlinks and detects same-size content changes and files changed during reading. No audio/report content reaches the model.
- Eight original retry REDs, one two-transaction stop/upload RED and one repeated-cancellation RED precede the changes. Final qualification has forty-six passing source/audio/size/cycle cases, including nine PostgreSQL scenarios and the independent upload/stop transactions. Strict MyPy seven sources plus two worker sources and scoped Ruff/Black pass. The complexity gate found a new CC hotspot; cohesive path discovery and per-file witnessing removed it, restoring the unchanged CC291/max78 ceilings. No native retry availability, paid processing, administrator tools, staging, commit or push is claimed. Native retry, other lifecycle/deletion/device actions and global qualification remain open.

### Slice 244 — Native acknowledged meeting-processing retry (implemented and reviewed)

- Registered retry_lia_meeting_tool in all operation/tool/executor/amendment/preview/state/lifecycle declarations. Only the owned stopped/failed meeting id is requested. Full private row/audio witnesses bind the proposal; metadata includes actual audio counts/bytes, current preferences, transcript availability, account address and retention deadline. Six-language consent states transcription/synthesis/indexing costs, quotas, possible replacement, notification, automatic email and audio purge. Later worker configuration/template reads are explicitly stated; no frozen future settings, final price or completed processing is promised. Existing durable processing and accounting are reused.
- Cold review exercises missing consent, foreign/live resources, same-size audio edits, changed report data, disabled capabilities, unknown commit acknowledgment, acknowledged commit followed by read failure, fresh amended consent, addressed SSE and terminal replay. The original worker launcher is mocked, so these simulations make no paid provider call. The real effect ledger, original HITL and PostgreSQL run in both mode contexts; full graphs remain unexercised. The amendment prompt excludes private witnesses, literal previews are escaped, checkpoint round-trips hold, and strict request/snapshot-growth guards protect authority and privacy. Boot first withdraws a previous owner before disable/failure.
- Seven initial native registration/preview REDs precede the integration. The combined native/PostgreSQL/size/cycle run has forty-three passing cases, with twenty-two original-HITL/real-ledger scenarios; eleven final preview/growth/boot cases pass. Strict type checking found a reused variable with two different snapshot types; distinct semantic variable names correct it and the changed editor passes. Scoped Ruff/Black, six-language parity and unchanged CC291/max78 pass; actual Docker resolves the tool. No administrator tools, staging, commit or push. Regeneration/reformatting, deletion/device actions and global first-lot qualification remain open.

### Slice 245 — Original quota-controlled fenced regeneration (implemented and reviewed)

- Original regeneration claims one unique owner before paid preparation, checks the account's existing usage allowance before template/model work, and renews that owner with independent short database sessions while the model runs. Failure and publication require the same live token and database-clock lifetime. Expiry/reaper clearing invalidates the old token; a late worker cannot overwrite or clear a newer rebuild. Cancellation closes only its own live generation and preserves cancellation. Original captured-failure accounting is retained; indexing follows only an acknowledged publication. Existing columns suffice; no migration or new provider is introduced.
- Cold review composes the coherent regeneration transitions into the original repository through a typed mixin, keeping source size bounded. Publication/failure require owner and lifetime arguments; an unsafe owner-less default is removed. Authority/quota/template preparation is separate from paid execution. The existing remote-transcription helper remains unchanged, avoiding a change to its separate audio-spend path. Legacy queued rows without heartbeats still expire from their original timestamp. ADR-259 records the stronger owner/quota contract.
- Two PostgreSQL quota/fencing REDs and three heartbeat REDs precede the guards. Final source/regeneration/transcription/reformat/reaper/size/cycle qualification has fifty-seven passing cases. Four controlled independent-worker scenarios cover success, duplicate launch, stale ownership and cancellation; no real model/indexing is invoked. Strict MyPy six original targets and two final changed targets, scoped Ruff/Black and unchanged CC291/max78 pass. Type checking caught bare returns after preparation extraction; explicit optional returns correct them. Native regeneration/reformat tools are not available yet. No administrator tools, staging, commit or push. Native lifecycle integration, deletion/device actions and global first-lot qualification remain open.

### Slice 246 — Original exact-confirmed regeneration transaction (implemented and reviewed)

- The existing regeneration queue now accepts an optional typed confirmation. It locks the account before the owned meeting, seals the complete source/transcript and current template definition, verifies consent before SQL and before commit, and launches the original fenced worker only after an acknowledged commit. The original UI default remains compatible. The public scope identifies the entire replacement while keeping transcript/report bodies and private witnesses out of prompts; invalid current minutes can be rebuilt from a valid retained transcript.
- Cold review verifies that original template writes share the account mutex, and covers changed report/transcript/location/template instructions, busy or missing-transcript state, late refusal and lost commit acknowledgment. Known queue acceptance remains distinct from completed processing/indexing. Nine final real PostgreSQL cases and forty-seven associated source/worker/size/cycle tests pass. Strict MyPy six sources and unchanged complexity ratchets pass. Native registration remains the next slice. No administrator tools, staging, commit or push.

### Slice 247 — Native confirmed full-minutes regeneration (implemented and reviewed)

- Registered regenerate_lia_meeting_report_tool in native operations, manifests, execution, amendments, previews, publication, startup/shutdown and six-language progress/consent copy. It starts only the original owned transcript rebuild, preserves exact source consent and reports queued synthesis/indexing as incomplete. Costs, account quotas, manual-edit replacement and later template/runtime resolution are explicit. The entire-consent context limit is shared with report editing; oversized consent is refused, never truncated.
- Cold review found and reproduced rejection of a repairable invalid current report; snapshot inspection now tolerates only its schema failure and exposes current_valid=false without raw malformed content. It also caught the publication module crossing its size cap. Original typed resource vocabulary/mappings moved into a coherent shared module; compatibility imports remain, and no cap was raised. Native confirmation/checkpoint/literal preview/privacy/growth guards and original-HITL/real-ledger flows cover both mode contexts, foreign/live/missing transcript, changed source, disabled capabilities, amendment, lost acknowledgment, post-commit read failure and terminal replay. These contexts are not full graphs, and no paid worker is invoked.
- Eleven initial unit REDs and the real-flow/size REDs precede corrections. Final combined qualification has seventy-five passing cases, including twenty-six native PostgreSQL scenarios and nine source-transaction cases; thirty original registry/publication regressions pass. Strict MyPy ten initial and three final changed sources, scoped Ruff/Black, six-language parity and unchanged CC291/max78 pass. Docker dev resolves the tool. No administrator tools, staging, commit or push. Reformatting, deletion/device actions and global first-lot qualification remain open.

### Slice 248 — Original exact-confirmed reformat transactions (implemented and reviewed)

- The original replace/new reformat owner accepts an optional exact confirmation under the account/meeting mutex, validates the complete source and selected template before writing and before commit, and exposes a known receipt distinct from synthesis/indexing completion. New minutes use a preallocated destination, reuse the retained transcript and original derivation rules, and carry no audio or transcription charge. Native launch ownership waits for a known commit; the original UI keeps its signatures and launcher behavior. The public DTO moves verbatim to core with a compatible domain re-export; generation inspection is reused rather than duplicated.
- Cold review covers template/transcript changes, late refusal and lost acknowledgment for both modes, including real rollback of a derived INSERT. It retains the original alternative allowing new minutes during a source synthesis while refusing an in-place replacement. No new migration, quota bypass, provider or raised limit is introduced. Ten initial PostgreSQL REDs precede implementation; twenty-six original/source/generation regressions pass, twelve final source scenarios pass, and twelve size/cycle guards pass. Strict MyPy eight sources, scoped Ruff/Black and unchanged CC291/max78 pass. Native registration follows separately. No administrator tools, staging, commit or push.

### Slice 249 — Native original reformat in place or as new minutes (implemented and reviewed)

- Registered reformat_lia_meeting_report_tool in every native operation/manifest/execute/amend/preview/publication/lifecycle registry with six-language consent/progress copy. Input inherits the original template/mode constraints, canonically resolves template UUID spelling and never accepts an account or destination override. Complete consent identifies selected instructions, source summary, mode and preallocated destination. Amendments re-observe the source and require renewed consent. The shared whole-consent budget refuses oversize without truncation; original fenced workers, platform costs and quotas remain the execution authority.
- Cold review verifies separate destination identity, unchanged source for new minutes, ownership of a selected template, source/template changes, disabled tools, no confirmation, amendment, lost acknowledgment and terminal replay. Private witnesses stay out of HTML/edit prompts and exact scope survives checkpoints. Thirty-two real PostgreSQL/original-HITL/real-ledger scenarios cover both mode contexts and both original output modes; they make no paid worker call and are not full graph proof. Fifteen initial REDs precede registration. Fifty-nine final preview/boot/registry/publication/size/cycle tests pass. Strict MyPy nine sources, scoped Ruff/Black, six-language parity and unchanged CC291/max78 pass; Docker dev resolves the tool. No administrator tools, staging, commit or push. Meeting deletion/device commands and global first-lot qualification remain open.

### Slice 250 — Original atomic meeting deletion and coordinated indexing (implemented and reviewed)

- Meeting deletion holds the account/meeting mutex, removes its projection/chunks and meeting row in one transaction, and cleans files only after commit acknowledgment. It reuses the existing caller-owned RAG deletion and exact-file cleanup rules. Projection ownership and meeting source type are checked before file inspection. The coherent deletion owner is extracted from MeetingService. Reindexing now holds the same fences through the shared document/projection-reference commit and rereads the meeting after first-use space creation; an independent deletion cannot leave a newly created orphan document.
- Cold review reproduced the original projection commit escaping a refused meeting deletion, the indexing/delete race, a same-root directory junction redirecting audio deletion, repeated cancellation returning while disk cleanup still ran, the retention reaper marking failed cleanup as purged, and a misbound uploaded projection being deleted. The storage completion owner is now shared by writes and cleanup, exact directory identity is checked before removal, and the reaper marks only successful cleanup. Indexing errors log their type without report bodies. Original UI and worker behavior remains covered; no paid embedding call is made in simulations.
- Final source/worker/cleanup/size/cycle qualification has forty-six passing cases; nineteen final projection/transaction/concurrency/original-guard cases pass after the last ownership review. Strict MyPy four initial sources and two final pairs, scoped Ruff/Black and unchanged CC291/max78 pass. Relevant meeting modules have no frozen size cap to lower, and no baseline is raised. Native deletion registration and device recording commands remain open, as do full graphs and first-lot global qualification. No administrator tools, staging, commit or push.

### Slice 251 — Exact-confirmed whole-meeting deletion source port (implemented and reviewed)

- The original atomic deletion accepts typed exact confirmation, checks the entire meeting/owned directory/projection before SQL and authority again before commit, and publishes an acknowledgment only after a known commit. Cleanup completion is a separate observed fact; a refused or interrupted cleanup never becomes a claimed complete deletion of files. Derived minutes remain independent records and the scope exposes their retained count. Live capture uses the separate device flow; active processing leases remain refused by the original SQL transition.
- Cold review reproduced missing/invalid encrypted transcripts blocking deletion, actual normalized audio being omitted when its stored reference was missing, and a cached projection hiding a later SQL modification. Deletion now observes transcript presence without decrypting data being removed, seals every regular file in the exact owned directory through the shared streaming witness, and rereads/locks projection rows with populate_existing. Private bodies, paths and digests remain outside public scope. Unknown commit acknowledgment preserves files and never grants replay. Typing caught optional receipt values being indexed; replacing the complete known result fixes it without a cast or ignore.
- Six initial source REDs, three invalid-source REDs and one cached-projection RED precede corrections. Final confirmation/original-retry/projection/indexing/guard qualification has forty-nine passing cases; strict MyPy's six-source run identified one corrected issue, the two final changed sources pass, and scoped Ruff/Black plus unchanged CC291/max78 pass. Native tool registration is the next slice. No administrator tools, staging, commit or push.

### Slice 252 — Native whole-meeting deletion with original HITL (implemented and reviewed)

- Registered delete_lia_meeting_tool in native operations/manifests, execution, pending amendments, canonical previews, state publication, startup/shutdown and six-language consent/progress copy. The exact original whole-meeting source and owned file directory are sealed. Derived minutes remain independent and retain their data; physical cleanup is requested, and its observed completion remains distinct from database deletion. A removed projection invalidates both meetings and spaces. Input cannot accept an account/path or widen deletion to derived minutes. Private witnesses never reach previews or amendment prompts.
- Cold review covers no human confirmation, foreign/live records, capability removal, report/audio changes, refreshed amended consent, unknown commit acknowledgment, failed cleanup, preserved derived rows and their cleared foreign key, addressed SSE and terminal replay. Distinct editor variables avoid reusing the template deletion's type. Boot withdraws old owners before disable/failure. Twenty-two real PostgreSQL/original-HITL/real-ledger cases across both mode contexts and eleven initial-unit/boot cases pass; they are not full graph proof. Eight initial REDs precede registration. Fifty-three final preview/boot/registry/publication/size/cycle cases pass; strict MyPy eight sources, scoped Ruff/Black, six-language parity and unchanged CC291/max78 pass. Docker dev resolves the tool. No administrator tools, staging, commit or push. Device recording commands, screen-parity review and first-lot global qualification remain open.

### Slice 253 — Recorder deletion failures remain observable (implemented and reviewed)

- Two behavioral REDs reproduce the original controller clearing its recording despite a refused deletion: an explicit discard and automatic cleanup after a no-audio stop. Both now use the same original discard owner. Capture and upload/poll resources are released; a refused or unacknowledged deletion retains the meeting identifier, interrupted recovery and the granular error. Only an acknowledged deletion clears the recording. No automatic replay is introduced. Unknown transport failure has translated guidance in all six languages.
- Cold review verifies that retained recovery cannot start a replacement recording, successful explicit retry clears state, the microphone is released on both refusal paths and normal stop/discard/format controls remain covered. The banner fixture now supplies the account required by the real template hook. Thirty-nine controlled Docker-dev controller/control/banner cases pass. Scoped formatting and ESLint, clean nonincremental host TypeScript, six-language parity and unchanged frontend CC41/max50 pass. No frozen controller complexity entry was weakened. This is source lifecycle evidence, not native recording-command or whole-graph proof. Device commands, screen parity and global first-lot qualification remain open. No administrator tools, staging, commit or push.

### Slice 254 — Full frontend qualification and coherent account fixtures (implemented and reviewed)

- The official first coverage run executes the entire frontend suite and identifies seven failing legacy fixtures. Settings, skill gallery/library and meeting list/detail/template fixtures now supply their controlled account to the real account-bound consumers. The template first-load fixture carries no already loaded templates. The pagination-only gallery suite uses the current owned-query boundary and a complete strictly typed payload, including sharing/retention metadata; its separate real-query suite still checks foreign resource events, account changes, signed-out callers and failed initial reads. No business assertion or coverage threshold is removed or relaxed.
- Cold review checks every failing file, preserves original user-facing assertions and confirms that real query/account-lifetime tests remain exercised. Seventy-seven targeted screen cases and fourteen gallery/pagination/account cases pass. Scoped formatting/ESLint, clean nonincremental host TypeScript and whitespace checks pass. The final official task test:frontend:coverage succeeds: all frontend tests and configured global/scoped coverage floors pass. The measured report is retained under the task's local qualification logs. This proves frontend qualification of the current tree, not native device-command completion, physical media output or the full assistant graphs. The inline device bridge, semantic screen parity and whole Pipeline/ReAct qualification remain open. No administrator tools, staging, commit or push.
- The measured Istanbul report justifies raising the global coverage ratchets according to the existing floor(measured minus two points) rule. All four new floors are independently checked against that exact full-suite report; scoped floors and complexity ceilings are unchanged. The settings parity observation confirms that device-only sections still need their bridge and that several UI tokens use different registry grouping names, so section-name equality alone cannot prove semantic coverage. A direct registry-first Docker import also emits a conditional DevOps import-cycle error while returning the registry; this observation does not reproduce the previously validated main-first startup and remains an explicit boot-order qualification item.

### Slice 255 — Document-addressed transport and optional origin binding (implemented and reviewed)

- Chat SSE and command requests share a canonical in-memory document UUID. Ordinary queries, including auth/features, gain no header. CORS explicitly admits the header. The authenticated cookie and live session remain authority; a device address grants none. Only explicitly addressed device commands bind the document; existing secure/file handoffs preserve session semantics. Amendments preserve the original binding and wrong/missing document claims are refused before reading the session.
- Cold review caught an unnecessary absent-header keyword breaking existing session adapter consumers; the command router retains their original call shape. The final application/core/middleware/size/cycle qualification passes, as do seven real PostgreSQL/original-session cases, targeted final route tests, frontend transport tests, clean TypeScript, strict MyPy and scoped Ruff/Black. Actual main-first Docker bootstrap resolves the existing meeting deletion tool. This is transport and authority evidence, not native device execution or full graph completion. Global frontend qualification predates this slice and must run again after the remaining behavioral changes. No administrator tools, staging, commit or push.

### Slice 256 — Recorder callbacks cannot outlive their owner (implemented and reviewed)

- Three behavioral REDs reproduce a disposed recorder creating a meeting after location resolves, opening capture after a late start response, and retaining a microphone granted after disposal. The original controller now fences asynchronous capture and reconciliation with its lifetime. Late acquired tracks and wake locks are released; a source finishing its own opening is stopped again. An accepted server start remains for the original reconciliation flow, with no unsolicited deletion or replay. Processing observation uses its own generation so stopped polling cannot notify or reschedule through a late response.
- Cold review adds late-source, foreign-account reconciliation and late-processing response simulations; the late-source RED identifies and fixes incomplete resource release. All original controller and six additional cases pass under controlled Docker dependencies. Scoped formatting/ESLint, clean nonincremental TypeScript and unchanged frontend complexity ratchets pass. These checks use simulated microphone/network owners and do not prove physical device behavior or native tool availability. No administrator tools, staging, commit or push.

### Slice 257 — Native recorder handoff and mobile action access (implemented and reviewed)

- The native read/control tools address the current authenticated browser document and reuse the original recorder controller. Capture, paid processing and destructive changes retain exact confirmation. The original session, document, current account, capability, command and effect fences apply before claiming and again before device execution; a lost claim response never automatically replays. A device acknowledgement reports a device observation, not completed transcription or minutes generation.
- Twelve real PostgreSQL/Redis flow cases pass. Three real-browser journeys pass at desktop and 320px: approved discard at both widths and a lost claim response with manual inspection on mobile. Cold review reproduced a floating-companion stacking conflict, fixed by the existing application-action priority attribute, and checked keyboard/pointer access, reflow and axe with the companion visible. These browser cases control API responses and do not prove physical microphone capture or a paid provider. The final icon addition is covered by frontend gates, not by a subsequent production rebuild. The earlier full frontend coverage run retains one unrelated voice-flattening timing failure; its isolated coverage replay passes. No coverage floor was weakened.
- This completes the recorder bridge. Other local controls, remaining saved-media parity, a semantic guard for complete UI coverage and a full compiled assistant graph remain separate nonadministrator follow-through. No administrator implementation, staging, commit or push.

### Slice 258 — Reviewed reversible settings and authoritative UI vocabulary (implemented and reviewed)

- One fail-closed policy determines the outer effect policy and native execution decision from the actual sparse patch. Personalization, layout and reviewed assistant, habit, journal, interest, Heartbeat and companion-display preferences apply through the original source writers and CAS receipts without creating a confirmation. Reads never request confirmation. Mixed sensitive patches, consent for remote speech/location/health, personal psyche-engine consent, retention changes, resource creation/edit/delete, capture, external delivery and execution permissions retain confirmation. Unknown operations or fields require confirmation by default.
- The shared preparer preserves source validation, ownership and capability checks. Reversible calls use the original effect ledger; replay checks fresh account/capability authority before serving a stored result. The executor rechecks authority after claim, uses the original source write, and publishes the existing preference invalidation. Post-commit failures preserve the actual committed state and instruct inspection before retrying. There is no invented approval, arbitrary dispatcher, new provider call or new LLM spend path.
- A packaged catalogue is generated from the actual native schemas and all six UI locales. Exact visible labels, including Sage and Sauge, normalize to the actual value forest. Answers receive localized labels and canonical values separately. Native assistant normalization preserves the original HTTP schema exactly. Boolean readings use the source common yes/no labels. Shared read enrichment adds vocabulary to native settings/preference containers without breaking malformed legacy display data. Provider-dependent choices remain with their existing runtime metadata owners.
- Semantic ratchets compare the packaged catalogue with current schemas/translations, require a vocabulary for every static personalization/assistant enum and require review when writable personalization fields grow. Reversible writer manifests publish the committed result. Cold review checked mixed patches, inactive accounts, disabled capability, replay, alias ambiguity, language fallback, malformed values, CAS conflicts, source-write failure and partial commit. Twenty real preference/legacy-consent flow cases, ten real feature-switch cases across both execution modes and thirteen old pending-confirmation compatibility cases pass. These exercise registered tools and real PostgreSQL/Redis, not a full compiled LLM graph.
- The current ApplicationSettings additions measure 48 response-prompt and 53 ReAct-prompt tokens with the existing o200k counter; the complete static French choice projection measures 489 tokens. These are tokenizer measurements, not provider billing estimates. Existing result budgets, quota enforcement and token accounting remain the authority. Strict MyPy passes for thirteen changed sources using a fresh scoped cache after the old Windows cache caused an access violation. Complexity ceilings remain unchanged; Ruff and source size/coupling guards pass.

### Slice 259 — Confirmation answer identity and Docker dev proxy (implemented and reviewed)

- Two independent behavioral REDs identify duplicate complete response messages in the SSE converter and an archived assistant row arriving before the live stream's done metadata. The backend emits a complete response identity once; the chat reducer reconciles only the archived row carrying the same message identity. Equal text under different identities remains visible, and an ambiguous missing stream target is not collapsed. The converter's full SSE simulations and immutable reducer tests cover both repetition and distinct answers.
- The application/effect/streaming unit scope passes 1,983 cases; the additional converter and size/coupling scope passes nineteen. The final proxy/chat frontend scope passes 229 cases, with the recorder/controller/dispatcher scope also previously qualified. The focused static-vocabulary and alias guard replay passes seventeen cases. Frontend lint, accessibility/hooks/complexity ratchets and nonincremental TypeScript all pass after the final changes. These counts describe their exact test scopes, not aggregate coverage.
- A real Docker probe found that the proxy chose a legacy HTTP alias for an HTTPS-only API. After fixing canonical upstream precedence, Next.js's actual HTTPS worker still replaced the inherited CA setting with an absent certificate-authority argument. The Docker dev command now passes the shared certificate as its HTTPS CA, and the web configuration preserves TLS verification rather than disabling it globally. Protocol/TLS tests reproduce both defects before correction. The API and the recreated web proxy now return 200 for auth/features. Only the web dev service was recreated; no production service was changed.
- The technical living map now claims the new infrastructure ports in their actual authentication, API, phone and meetings bricks. Generated maps and the unstaged documentation preview pass. No administrator tools, staging, commit or push. Complete device/provider validation and the remaining broader nonadministrator scope above are not claimed by these corrections.

### Slice 260 — Cold adversarial review of authority and display contracts

- Behavioral REDs show that distinct operations could register the same native tool name and that reversible access mapped operator-disabled and unavailable-storage reasons to FORBIDDEN. The registry now rejects both operation and tool collisions before changing either index, and provides one constant-time tool lookup. Gate policy and replay authorization use that same lookup. Reversible refusals reuse the existing finite public error mapper; database diagnostics remain excluded from the output. Existing account/capability checks and source CAS are retained.
- Another RED demonstrates that a translated label could invalidate a valid canonical transport value. Exact canonical identifiers now remain stable while genuinely ambiguous aliases are rejected. The input is normalized once per field instead of once per candidate. Main/assistant schema fingerprints and actual six-language UI labels remain authoritative.
- The shared read renderer previously borrowed account-language options for a same-named transcription field. Its RED now passes: static vocabulary enrichment is bound to the registered account/assistant read operations. Other domains keep their original data and only universal Boolean labels. Provider/domain-dependent options must come from their own metadata; this review does not claim those vocabularies have all been implemented.
- Source inspection of VoiceModeSettings, useVoiceMode and the wake-word owner establishes that applying a hands-free preference can acquire the microphone. The centralized policy now requires confirmation for enabling it, including a mixed patch, and allows immediate disabling. Both gate classification and preparation read this value-aware rule; the manifest describes the distinction. Sensitive remote speech, location/health, retention, capture and destructive actions keep their existing fences.

### Slice 261 — Bootstrap availability, diagnostic privacy and reducer simplification

- Fresh-interpreter qualification reproduces a cycle through the memory route and the eager conditional DevOps tool registration. The fix defers only that facade's tool registration until its symbol is requested or the existing explicit registry loader loads it. The original memory package and all its exports/routes are retained. Cold tests now also assert that collecting native manifests, loading the real registry and requesting the facade all resolve the same actual tool without preloading src.main. No new administrator tool or action is introduced.
- The two tool-import failure gateways exposed exception text and traceback locals. Separate REDs cover each gateway. They now record only module/family and exception type, preserving the failure counter. The explicit registry loader still aborts outside production; its exception message and chain exclude the private source diagnostic. Production retains its observed-and-counted degraded behavior. Windows subprocess readers explicitly decode their UTF-8 children, so an encoding failure cannot hide the real startup result.
- The complete frontend run identifies an unreachable reducer guard: its only caller has already found the stream and applied the archived identity. Removing that guard and its redundant list scan restores the strict reducer coverage without adding artificial tests or changing thresholds. Identity-based deduplication, distinct equal-text answers and ambiguous completion behavior remain covered.

### Slice 262 — Qualification, ratchets and remaining evidence limits

- The official complete frontend coverage command passes all 12,372 cases. Its measured statements/branches/functions/lines are 86.64/80.65/84.27/88.14 percent. The established measured-minus-two ratchet leaves global floors unchanged; reducers retain their independent full-coverage floors. Frontend lint, accessibility/hooks/complexity and nonincremental TypeScript pass. No baseline was relaxed.
- The transverse backend scope passes 3,450 cases. Later focused replays cover the final native boundaries and effect gate (1,952 cases), the actual import/privacy/registry and size/cycle boundaries (54 cases), and the microphone policy plus direct feature writes (49 mixed unit/integration cases). The interest/preferences integration replay passes 45 real PostgreSQL/Redis cases, including both execution modes and normal/overnight notification windows. These scopes overlap and must not be summed as unique tests.
- A broader application integration attempt passes 534 cases before stopping at three obsolete mandatory-confirmation expectations for newly reversible interest settings. Those fixtures now exercise original preparation/persistence as already-issued pending confirmations; their exact consent, CAS, conflict, expiry, revoked rights and partial-write assertions remain. Current native direct writes are tested separately. The entire broad integration campaign was not rerun to completion, so it is not reported green.
- Strict MyPy passes the reviewed common contracts, and source lint and unchanged complexity ceilings pass. New collision, finite-error, canonical-value, microphone-direction and domain-vocabulary tests extend the behavioral ratchets. Docker dev returns 200 on both API and web auth/features after the bootstrap changes. Tests use controlled data; no paid model, production write, commit, staging or push was performed.
- The final domain-vocabulary change briefly exceeded the existing complexity ratchet. Extracting the validated source-value projection into a small pure helper restores the original ceiling (291 hotspots, maximum 78), without changing a baseline. Its final 39 behavioral cases, strict typing, source lint and the 12 size/cycle guard cases pass.
- Honest scope: these checks strengthen the implemented code, but do not prove physical capture, provider billing or a full original compiled assistant turn with real model decisions. The wider unfinished nonadministrator UI/media work remains described in slice 257; administrator work remains a separate later lot. No claim of universal UI coverage or absolute perfection follows from this review.

### Slice 263 — Reported global unit failures and complete-tree qualification

- The user's external backup report identifies 47 reproducible failures plus one recovered case. The earlier scoped checks did not establish a green complete tree; the earlier final wording was too broad. This pass preserves the user's phase-2 corrections, performs no staging/commit/push and uses the exact reported modules as its starting oracle.
- Production fixes remove empty handlers, use the central declared/stored-language resolvers, generate Chinese vocabulary under its backend-canonical key, retain optional-field metadata at the top of annotations, use the peer status enum, publish the complete activity status vocabulary, restore the email protocol's explicit single-attempt option and correct French punctuation. Both SSRF readers now import the same infrastructure policy objects and IP predicate; the drift guard checks shared ownership as well as behavior. The directly imported pydantic-core distribution is declared and all lockfiles are compiled with the repository's pinned uv writer, without changing dependency versions.
- Router, routine, meeting, RAG and skill fixtures now exercise their actual boundaries: concrete HTTP cookies/headers, fresh authority reads, OAuth's shared owner, regeneration's worker lease, account/template/skill locks and owned-space update reads. The original 403 system-space protection assertions remain intact. Ready-state evidence is required for unchanged Drive content. Reminder creation remains pending even when its proposed content matches the request. Library doubles name the actual before/after-commit hooks explicitly.
- The demonstrator already enables application tools in both templates. Its edge now forwards the authenticated owned-command continuation family, with each route explicitly recorded in the public census; existing per-family ceilings and ownership/session checks still apply. No administrator tool is introduced.
- The semantic annotation floor is retained by exposing actual saved textual preference fields, including their parent container. Personalization manifests move into their own cohesive catalogue; the original registration facade retains its public exports and stays under the file-size ceiling. A separate behavioral RED exposes a real committed reversible change still reported as pending: only a registered native application outcome with literal successful commit markers and a valid typed outcome can close it. A draft, malformed/unacknowledged result or foreign native action cannot. No execution authorization is inferred from that reporting verdict.
- Fresh qualification: the complete official fast backend suite reports **40,861 passed, 31 skipped and exactly three failures**, all the previously identified index-based documentation guards. There are no remaining runtime/unit failures from the reported 47. The full affected modules pass **590 cases sequentially**; semantic/catalogue/cold-import/size/cycle checks pass **454 cases**; disposable PostgreSQL reversible settings pass **28 cases** in both execution modes. These scopes overlap and are not summed.
- All complete-tree static gates pass when the documented unstaged preview replaces only the index-based documentation audit: backend Ruff/Black and MyPy over 3,231 source files, frontend lint/nonincremental TypeScript and its accessibility/hooks/complexity ratchets, i18n, documentation preview, MyPy debt, observability, cycles, complexity, hygiene, lockfiles, CI parity, wake and dependency tooling. File-size ratchets lock the current tree's measured gains by lowering four caps and removing two unnecessary exemptions, without raising a ceiling. Docker dev API and web auth/features both return 200. This is not a staged/clean-clone verdict, a full integration campaign, physical-device proof or a paid-model turn.

### Slice 264 — CI integration isolation, catalogue contracts and browser qualification

- This pass starts from the user's external PR298 report and its agents/E2E supplement. All work remains inline in the existing checkout; no staging, commit, branch operation or push is performed.
- Tests which genuinely need independent committed connections now register their account identifiers before committing and release precisely those accounts in a finally-owned scope. The cleanup exercises PostgreSQL foreign-key cascades, preserves an unrelated account and runs after a controlled post-commit failure. It does not replace reserved test addresses to hide serialization errors. A per-test integration observation compares committed account identifiers before setup and after fixture teardown; it names a leaking producer without deleting its evidence or weakening repository count assertions.
- Plugin removal tests patch the real move-preparation boundary. Reversible layout tests exercise the actual native execution ledger and effect scope, including an intervening UI write in both execution modes. Drive preload cases use the canonical processing-status vocabulary and require READY evidence before reporting unchanged content. RAG recovery tests use fresh worker sessions and durable seeds, with explicit account ownership.
- Application catalogue outputs derive from the canonical public projection models or the genuine pending draft shape. They expose neither a fabricated execution result nor a private execution witness. Response-node characterization accepts the intentionally declared journal state keys and checks the MessagesState declaration. The complete agents suite passes; manifest identity and existing registration ownership remain intact.
- Browser mocks serve the shared companion context, read-only psyche queries and the canonical fresh-connector request. Companion tests observe the current native portrait and GPU projection rather than obsolete image/transform markup. Menu tests retain real wheel gestures, viewport containment, selected-text readability and actionable controls. Default floating-companion placement avoids interactive controls with bounded candidate search and throttled DOM observations; explicit positioning remains user-owned. Observer, timer and animation-frame lifetimes are covered. The new placement coverage floor is scoped; no existing floor or complexity ceiling is raised to accommodate code.
- A physical module-resolution check found the Docker renderer using an older transitive KaTeX despite its direct dependency and checked-in override being current. A frozen workspace dependency installation corrected the Docker dependency volume without changing a manifest or lockfile. The browser proof uses a fresh standalone production build on a dedicated port, leaving the development web service available.
- Verified scopes at this checkpoint: the official sequential backend unit/coverage task passes 40,896 cases, with 31 capability skips and 9 deselections; backend coverage is 78.12%, above the enforced floor but without the former two-point margin. The complete agents suite passes 1,132 cases. The complete frontend coverage task passes 12,382 cases and all global/scoped floors; the subsequent placement-hook refactor passes its 89 relevant behavioral cases and the full frontend lint/type/ratchet task. These scopes overlap and are not summed.
- During qualification, complete integration and E2E campaigns exposed failures missed by scoped checks. The initial complete integration replay found residual account-count failures; targeted producer/consumer replays pass, so an explicit per-test ownership observation is used to localize any remaining order-dependent leak. A subsequent run passed 1,237 cases before the development services restarted and Redis disconnected. The contemporaneous browser run was also interrupted; seven affected browser scenarios pass after service recovery. Interrupted campaigns are not reported as complete-suite successes. Windows evidence does not establish Linux-only capability paths, physical capture, a paid-provider turn or remote CI acceptance.
- The subsequent complete browser campaign finishes with 528 passes and one stale shortcut mock. The picker mock now persists the exact PUT list into the same user object read by both GET and auth refresh. Five dock journeys pass, including one write, the authenticated reread and both named links. The final complete browser replay uses that corrected mock with retries disabled.
- The strict MyPy launch crashes natively on the existing local cache without reporting a typing error. The same configuration with a fresh cache passes all 3,232 source files; replacing only the verified local cache also makes the exact Task launcher pass. No typing rule, source annotation, dependency or exemption is loosened for this runtime repair.
- Final browser qualification: the complete production-build campaign passes all 529 Chromium E2E/accessibility scenarios with retries disabled; its transport checks and E2E TypeScript pass in the same run. The final post-refactor frontend coverage task passes all 12,382 cases and all floors (86.67% statements, 80.68% branches, 84.29% functions, 88.16% lines). The complete Task lint passes after the local MyPy cache repair. Temporary proof-dist includes are removed while pre-existing includes and comments are preserved; canonical Next type generation and clean nonincremental TypeScript pass afterward. The dedicated proof server and only its generated builds are released after the successful browser campaign.
- Docker development smoke after the service restart: both the direct API and the web proxy return 200 on auth/features over their configured HTTPS endpoints, with the shared development certificate trusted and TLS verification retained. The documentation preview also passes. These are public endpoint availability checks, not authenticated action or paid-provider evidence.
- The guarded complete integration replay localizes eighteen committed-account leaks in nine additional test modules. These tests borrow an account factory from another module, so a direct UserFactory-text scan missed their independent commits. PostgreSQL creation timestamps identify the actual producers. All now register their account UUID before commit under the shared finally-owned cleanup; MCP, meeting, template and preference children follow real FK cascades. Count, pagination, lock-lifetime, quota, stale-consent and duplicate-worker assertions remain unchanged. The corrected producers followed by the affected repositories, transactions and user routes pass 86 cases sequentially on Testcontainers, with no broad delete.
- Final official backend integration qualification: task test:backend:integration exits 0. Its first collection passes all 4,615 selected cases, with 7 intended deselections and no teardown errors. Its second collection passes 4 cases; the two skips explicitly require POSIX rlimits/privilege drop and cannot run on this Windows host. TEST_DATABASE_URL remains unset, the preflight selects Testcontainers, and the committed-account guard stays active. No remaining count, pagination or user-response failures occur. The complete Task lint is green after these test-fixture corrections. All reported local test blockers are cleared; remote CI and POSIX-only execution are not represented as exercised here. The measured backend coverage still has only its small margin above the unchanged floor.
