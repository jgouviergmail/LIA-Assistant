# ADR-342 — Opt-in runtime avatar preference campaigns

**Status:** Accepted — implemented and qualified locally; production activation is separate.
**Date:** 2026-10-12
**Scope:** Web runtime configuration and browser-local avatar display preferences.

**Related:** [ADR-294](ADR-294-A-Face-That-Never-Plays-The-Same-Twice.md) and
the [avatar guide](../technical/SPIRIT_AVATAR.md).

## Context

Avatar appearance is a device display preference in `lia_eyes_widget_prefs`.
It is not a `users` database column. Existing installations must preserve saved
choices, while an operator can explicitly introduce BIP for existing visitors
of one deployment. A universal storage migration would reset other operators'
preferences. A build-time public variable would bind the campaign to an image.

## Decision

1. `AVATAR_STYLE_ROLLOUT_ID` is a non-secret, server-only web runtime option,
   empty by default. The production Compose web service forwards it explicitly.
   It is absent from backend Settings and the installer wizard. No hostname or
   production preset is encoded in application code.
2. `GET /api/runtime-ui` reads this option on each request and exposes only
   `{ avatarStyleRolloutId: null | string }`, with `Cache-Control: no-store`.
   Invalid or empty identifiers disable the campaign. The identifier is bounded
   and uses letters, digits, dot, underscore, colon and hyphen.
3. The authenticated application avatar host uses the common anonymous,
   same-origin JSON transport. Its effect defers the request to a microtask,
   aborts on unmount, and ignores late responses. The public landing does not
   initiate a campaign. Network/configuration/storage failures retain preferences.
4. The persisted browser store holds `appliedAvatarStyleRolloutId`. A new
   identifier changes only `style` to `bip` and that marker in one write.
   Visibility, size and both surface positions remain intact. Subsequent choices
   survive remounts and later requests for the same campaign. Manual display reset
   retains the marker. Existing versioned and unversioned records remain readable;
   no universal persistence-version migration is needed.
5. Before applying, the hook rehydrates the latest synchronous localStorage
   record. Web Locks serialize concurrent campaign application across tabs of
   this origin. Storage events refresh open authenticated tabs without writing
   back or replaying the campaign. Without Web Locks, the latest synchronous
   re-read protects delayed responses and normal tab changes; simultaneous
   cross-process first writes have no transactional lock guarantee.
6. Each distinct identifier names a new, explicit campaign. Operators must not
   reuse a retired identifier or rotate it on every release. Clearing the option
   stops future application; it does not restore an earlier avatar choice.

## Consequences and limits

The campaign applies on the next authenticated visit of each browser origin,
including existing visitors. It cannot mutate offline devices, another browser,
or a database account avatar. Clearing browser storage removes the marker.
Multiple accounts sharing that origin also share this device preference.
Other deployments remain inactive unless their operator sets an identifier.

The option is intentionally public configuration. No credential, user identity,
provider configuration or mutable administrator operation is exposed by the route.
Disabling it is an operational choice, not a rollback of user preferences.

## Qualification and sources

Behavioral tests cover persistence after manual choices, preservation of display
fields, legacy records, explicit later campaigns, malformed identifiers,
request failure, StrictMode, abort/late responses, delayed cross-tab response,
storage-event synchronization and locked application. A deployment contract test
checks empty examples and runtime web-only wiring.

- [Store](../../apps/web/src/stores/eyesWidgetStore.ts)
- [Lifecycle hook](../../apps/web/src/hooks/useAvatarStyleRollout.ts)
- [Runtime route](../../apps/web/src/app/api/runtime-ui/route.ts)
- [Hook tests](../../apps/web/src/hooks/__tests__/useAvatarStyleRollout.test.tsx)
- [Deployment contract](../../apps/api/tests/unit/test_avatar_style_rollout_contract.py)

These are local source/runtime-unit checks. Real-browser multitab qualification
and an operator's actual production activation must be reported separately.
