# Display preferences

Decision record: [ADR-377](../architecture/ADR-377-The-Account-Chooses-How-The-Interface-Is-Drawn.md).

The account persists the display intent through `UserUpdate`. The allowed values
are published by `VALID_THEMES` in `apps/api/src/domains/shared/schemas.py`; the
assistant's preference schema and the UI use that same vocabulary. The numeric
schedule bounds and defaults live in `apps/api/src/core/constants.py`.

Automatic mode stores two distinct minutes of the civil day, interpreted in the
account timezone. Light occupies the half-open interval from its start to the
absolute-black start; an interval may cross midnight. The browser compares civil
time directly, so missing or repeated daylight-saving times follow that day's
clock. The profile service merges partial changes under a fresh row lock before
validation. Database constraints protect writes which bypass the API.

`ThemeModeProvider` is mounted once below authentication. It owns the clock,
account synchronization and serialized, coalesced writes. Consumers call
`useThemeMode`; they create neither a timer nor a persistence queue. A clock tick
changes only rendering, never the profile. Focus, visibility and page restoration
re-evaluate immediately. Retained callbacks from another account or a removed
provider are inert; pending requests are aborted and stale results cannot update
the new account. A failed choice stays local, is explicitly reported, and can be
retried. Later explicit writes carry still-unsaved schedule changes too.

`next-themes` continues to render only its native light/dark/system vocabulary.
Absolute black refines `.dark` with `data-oled`; automatic intent stays separate.
The pre-paint script serializes the same pure `automaticThemeAt` resolver used at
runtime, validates cached data, and supplies the resolved value before
`next-themes` reads it. Device storage is optional: failure leaves the authenticated
runtime working. For an account the header's circle enters automatic after OLED
and leaves it for light ([ADR-243](../architecture/ADR-243-OLED-Display-Mode-Refinement.md),
amendment 2026-11-12).

A press is drawn by its reveal alone (ADR-243, follow-up 2026-11-14). The provider's
drawing function keeps one identity, so the account is redrawn when the ACCOUNT
changes and never because the theme just changed locally — `next-themes` hands out
a new `setTheme` at every theme change. The automatic clock starts, and the save is
read back, on a page already drawn: either one drawing first leaves the reveal
nothing to unfold.

Evidence lives in the theme schedule unit tests, provider lifecycle tests, the walk
of the circle on the real provider
(`apps/web/src/components/__tests__/theme-cycle-walk.test.tsx`),
`apps/api/tests/integration/test_user_theme_schedule.py`,
`apps/web/e2e/smoke/settings-automatic-theme.spec.ts` and
`apps/web/e2e/smoke/theme-cycle.spec.ts`. The browser journeys run against
intercepted APIs; the first covers a narrow viewport, a clock boundary, paired
editing, reload and leaving automatic mode, the second every press of the circle and
what its reveal photographs. They make no model or provider call.
