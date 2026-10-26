# World touch follow-up — cold review

The accepted V1 remains one world, five admitted accounts, private native LIA
operations and direct human text. This follow-up changes the HUD, not authority,
billing, translation prompts, persistence or rendering algorithms. Main and the
parallel worktree have not been modified.

## Findings and decisions

- Portrait: the full-width strip wrapped Leave onto a line of its own. Use a
  compact two-column dock, preserve DOM/tab order and every action, and keep
  native theme colours and focus treatment.
- Capability: the previous width-only rule removed walking controls on a wide
  touch device. Hide the pad only for a wide primary fine/hover pointer; verify
  rotation with a touch-capable browser context.
- Short landscape: camera controls covered the minimap. Use one camera row and
  a compact heading; the current place remains available through its named native
  action. The title inherits the app's text size, including enlarged text.
- Unread messages: the inline badge could exceed a narrow action button. Keep
  it within that button on phones and describe the unchanged action name with
  a localized, owner-scoped `useId` description. The existing protocol bounds the
  mailbox; this change creates no new public projection or network request.
- Held targets: native button animation and Tailwind's individual scale reduced
  a walking target below its full size. A real held-pointer check caught this.
  The production CSS optimizer combines equal-priority `transform:none; scale:1`
  into `transform:scale(1)`, leaving the other active scale effective. A protected
  individual-scale reset preserves both declarations. The rule is confined to
  world controls; native colours, selected states and focus rings remain intact.
- Measurement: reuse the existing browser CSS-pixel rounding helper for subpixel
  used values; a real undersized target still fails. No threshold is lowered.

## Verification boundaries

The new hermetic matrix exercises touch capability, rotation, tablet layout,
normal and enlarged type, the full mailbox counter, geometry/hit testing, held
movement, preserved accessible names/descriptions and axe checks. API/provider
isolation remains enabled. Native SQL/Redis journeys separately cover delivery,
retry, lost acknowledgments, scope fencing, owner changes, home editing,
functions, notification cleanup and five-plus-one admission.

The native conversation test now reads the unread description rather than an
obsolete badge selector. After account reload it checks the actual supported
locale used by that tab: two tabs share the locale cookie. Neither privacy nor
message-content assertions were removed. Older social fixtures use the shared
entry helper on optimized builds and assert that their development-only preview
route is unavailable there.

Windows dependency resolution through the shared D: junction lost `zod/v4`
(and later `zod`). No installation or repair was made through that junction.
Linux gates use the existing read-only dependency volumes. The strict E2E check
uses the existing pinned Playwright types in an isolated snapshot. Vitest's
runner config loader avoids writing its temporary bundle into read-only
node_modules. Missing backend corpus files were supplied to that snapshot;
the failing contracts and four initially skipped source-symmetry checks were
replayed, preserving their assertions.

The last usable preview stayed up throughout qualification. Automatic approval
review rejected building in the stable qualification container; the build was
performed in the isolated candidate instead. A fixed native-proof loopback
origin reaches that candidate without changing the stable frontend, backend
configuration, quotas or origin allowlist.

## Acceptance

Final counts, hashes, commands, captures and performance samples are recorded in
[the evidence](assets/world-v1-f9/evidence.json). Earlier unsuccessful runs remain
in the local ignored work directory; they are not counted as passes. Physical
Pi/phone thermals, battery and GPU behavior, real supplier translation fidelity
and owner approval of final art remain separate acceptance steps.

The published preview was also checked after promotion. Its old development
build returned a JSON-metadata error; a fresh dist restored authenticated entry,
touch scene and zoom with the same qualified source digest. The old cache was
retained. A further native check on the published origin confirmed Spanish /
English reciprocal delivery using the fixture's authorized phrases, and explicit
original display for unsupported fixture text. A first same-language verifier
was rejected because these two validation accounts have different configured
languages; it was not a missing-delivery result. No production translator was
changed to accommodate the demonstration. For free text in this local preview,
use separate browser profiles with visitors 1 and 7 (both French).

The frontend run emitted existing negative-path API diagnostics and React act
warnings; none were suppressed. All measured ratchets retain their floors.
The Windows shared-dependency issue remains separate from the passing equivalent
Linux frontend checks and the passing canonical host backend/cross-cutting gates.

A final canonical Windows `task lint` retry, after zod became resolvable again,
confirmed another missing shared dependency (`es-iterator-helpers/Iterator.from`).
This remains an environment limitation, not a passing root-command claim.
