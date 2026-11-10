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
runtime working. Manual header cycling exits automatic mode.

Evidence lives in the theme schedule unit tests, provider lifecycle tests,
`apps/api/tests/integration/test_user_theme_schedule.py` and
`apps/web/e2e/smoke/settings-automatic-theme.spec.ts`. The browser journey runs
against intercepted APIs, covers a narrow viewport, a clock boundary, paired
editing, reload and leaving automatic mode. It makes no model or provider call.
