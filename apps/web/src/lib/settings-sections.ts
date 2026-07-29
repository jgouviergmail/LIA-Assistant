/**
 * Deep-linkable settings sections (W2).
 *
 * The settings page stacks ~30 collapsed accordion sections across two or three
 * tabs. Arriving there without a target means scanning them by hand — and that
 * is exactly what happened: `?section=` only ever understood two values
 * (`connectors` and `journals`), while the getting-started checklist pointed
 * SIX of its seven items at the bare `/dashboard/settings`. "Choose a
 * personality" landed the user at the top of a page of closed accordions.
 *
 * This table is the single source of truth for the link targets. The page
 * consumes it to pick the tab, expand the accordion item and scroll to it; the
 * checklist and the dashboard cards consume it to build their hrefs.
 *
 * Each entry maps a stable URL token to:
 *   - the TAB that holds the section (superusers get a third, admin tab);
 *   - the accordion `value` of the target `<SettingsSection>`.
 *
 * The accordion values are not free-form: they must match the `value` prop of
 * the corresponding component, and a test asserts exactly that against the
 * source — a renamed section would otherwise leave a link quietly landing on
 * the right tab with nothing expanded.
 */

/** Tabs of the settings page. `administration` exists for superusers only. */
export type SettingsTab = 'preferences' | 'features' | 'administration';

export interface SettingsSectionTarget {
  /** Tab to activate. */
  tab: SettingsTab;
  /** Accordion `value` of the section to expand. */
  accordionValue: string;
  /** Component that declares that value — checked by the sibling test. */
  declaredIn: string;
}

/**
 * URL token → where it lives.
 *
 * Tokens are part of the app's URL surface: renaming one breaks existing links
 * (the checklist, the briefing cards, anything a user bookmarked). Add rather
 * than rename.
 *
 * ORDER IS PAGE ORDER, and it is load-bearing: the settings search uses it to
 * break score ties, so two equally-scored results are listed in the order the
 * reader would meet them by scrolling. Keep a new entry next to the component
 * it describes in `settings/page.tsx`.
 *
 * The table covers every USER-facing section of both tabs (30). The thirteen
 * `administration`-tab sections are deliberately absent, and that absence is
 * enumerated — not implied — in the shrink-only allowlist of
 * `__tests__/settings-sections-coverage.test.ts`.
 */
// `satisfies`, not an annotation: `Readonly<Record<string, …>>` would erode
// `keyof typeof` to plain `string`, and `SettingsSectionToken` — the type four
// call sites rely on to catch a typo'd deep link at compile time — would accept
// any string at all. `satisfies` validates every VALUE against the shape while
// keeping the literal keys. Verified: with the annotation,
// `const t: SettingsSectionToken = 'does-not-exist'` compiled cleanly.
export const SETTINGS_SECTIONS = {
  // ---- Preferences tab / Personalization
  language: {
    tab: 'preferences',
    accordionValue: 'language',
    declaredIn: 'components/settings/LanguageSettings.tsx',
  },
  timezone: {
    tab: 'preferences',
    accordionValue: 'timezone',
    declaredIn: 'components/settings/TimezoneSelector.tsx',
  },
  theme: {
    tab: 'preferences',
    accordionValue: 'theme',
    declaredIn: 'components/theme-selector.tsx',
  },
  font: {
    tab: 'preferences',
    accordionValue: 'font',
    declaredIn: 'components/settings/FontSettings.tsx',
  },
  'display-mode': {
    tab: 'preferences',
    accordionValue: 'display-mode',
    declaredIn: 'components/settings/CardsDisplaySettings.tsx',
  },
  'briefing-grid': {
    tab: 'preferences',
    accordionValue: 'briefing-grid',
    declaredIn: 'components/settings/BriefingGridSettings.tsx',
  },
  'chat-shortcuts': {
    tab: 'preferences',
    accordionValue: 'chat-shortcuts',
    declaredIn: 'components/settings/ChatShortcutsSettings.tsx',
  },
  'open-loops': {
    tab: 'preferences',
    accordionValue: 'open-loops',
    declaredIn: 'components/settings/OpenLoopsSection.tsx',
  },

  // ---- Preferences tab / Notifications & Communication
  notifications: {
    tab: 'preferences',
    accordionValue: 'notifications',
    declaredIn: 'components/settings/NotificationSettings.tsx',
  },
  channels: {
    tab: 'preferences',
    accordionValue: 'channels',
    declaredIn: 'components/settings/ChannelSettings.tsx',
  },

  // ---- Preferences tab / Security
  'security-auth': {
    tab: 'preferences',
    accordionValue: 'security-auth',
    declaredIn: 'components/settings/SecuritySettings.tsx',
  },
  'security-devices': {
    tab: 'preferences',
    accordionValue: 'security-devices',
    declaredIn: 'components/settings/DeviceSessionsSettings.tsx',
  },
  'security-export': {
    tab: 'preferences',
    accordionValue: 'security-export',
    declaredIn: 'components/settings/AccountExportSettings.tsx',
  },

  // ---- Preferences tab / Voice & Media
  'voice-mode': {
    tab: 'preferences',
    accordionValue: 'voice-mode',
    declaredIn: 'components/settings/VoiceModeSettings.tsx',
  },
  'image-generation': {
    tab: 'preferences',
    accordionValue: 'image-generation',
    declaredIn: 'components/settings/ImageGenerationSettings.tsx',
  },

  // ---- Preferences tab / Connections & Integrations
  connectors: {
    tab: 'preferences',
    accordionValue: 'connectors',
    declaredIn: 'components/settings/UserConnectorsSection.tsx',
  },
  // A6. Renders nothing when telephony is off or no call was ever placed, so a
  // deep link can legitimately resolve to an absent section — same as the other
  // capability-gated entries here.
  'telephony-calls': {
    tab: 'preferences',
    accordionValue: 'telephony-calls',
    declaredIn: 'components/settings/TelephonyCallsSection.tsx',
  },
  'admin-mcp-servers': {
    tab: 'preferences',
    accordionValue: 'admin-mcp-servers',
    declaredIn: 'components/settings/AdminMCPServersSettings.tsx',
  },
  'mcp-servers': {
    tab: 'preferences',
    accordionValue: 'mcp-servers',
    declaredIn: 'components/settings/MCPServersSettings.tsx',
  },
  // Rendered by the NON-superuser layout only: a superuser gets the richer
  // `debug-settings` section in the administration tab instead.
  'debug-panel': {
    tab: 'preferences',
    accordionValue: 'debug-panel',
    declaredIn: 'components/settings/UserDebugSettings.tsx',
  },

  // ---- Features tab
  personality: {
    tab: 'features',
    accordionValue: 'personality',
    declaredIn: 'components/settings/PersonalitySettings.tsx',
  },
  psyche: {
    tab: 'features',
    accordionValue: 'psyche',
    declaredIn: 'components/settings/PsycheSettings.tsx',
  },
  memories: {
    tab: 'features',
    accordionValue: 'memories',
    declaredIn: 'components/settings/MemorySettings.tsx',
  },
  interests: {
    tab: 'features',
    accordionValue: 'interests',
    declaredIn: 'components/settings/InterestsSettings.tsx',
  },
  heartbeat: {
    tab: 'features',
    accordionValue: 'heartbeat',
    declaredIn: 'components/settings/HeartbeatSettings.tsx',
  },
  'scheduled-actions': {
    tab: 'features',
    accordionValue: 'scheduled-actions',
    declaredIn: 'components/settings/ScheduledActionsSettings.tsx',
  },
  journals: {
    tab: 'features',
    accordionValue: 'journals',
    declaredIn: 'components/settings/JournalsSettings.tsx',
  },
  'health-metrics': {
    tab: 'features',
    accordionValue: 'health_metrics',
    declaredIn: 'components/settings/HealthMetricsSettings.tsx',
  },
  skills: {
    tab: 'features',
    accordionValue: 'skills',
    declaredIn: 'components/settings/SkillsSettings.tsx',
  },
  'rag-spaces': {
    tab: 'features',
    accordionValue: 'rag-spaces',
    declaredIn: 'components/spaces/SpacesSettingsSection.tsx',
  },
  // The component serves both the user and the admin export from one file and
  // therefore picks its accordion value at runtime (`mode`), which is why the
  // sibling test checks this one against a quoted literal instead of the
  // `value="…"` prop form.
  'user-consumption-export': {
    tab: 'features',
    accordionValue: 'user-consumption-export',
    declaredIn: 'components/settings/ConsumptionExportSection.tsx',
  },
} satisfies Readonly<Record<string, SettingsSectionTarget>>;

export type SettingsSectionToken = keyof typeof SETTINGS_SECTIONS;

/**
 * Narrow a raw string to a known token.
 *
 * A type guard rather than a cast: the token comes from the query string, so
 * the check has to exist at runtime anyway — writing it as a predicate lets the
 * compiler share the conclusion instead of being told to trust one.
 *
 * Args:
 *   token: Any string, typically a `?section=` value.
 *
 * Returns:
 *   True when `SETTINGS_SECTIONS` declares it as an OWN property.
 */
export function isSettingsSectionToken(token: string): token is SettingsSectionToken {
  // `Object.hasOwn`, not a bare index: a plain lookup would resolve inherited
  // keys — `?section=constructor` returns `Object.prototype.constructor`, a
  // truthy value whose `.tab` is undefined.
  return Object.hasOwn(SETTINGS_SECTIONS, token);
}

/**
 * Build a deep link to a settings section.
 *
 * Args:
 *   lng: Short locale segment, e.g. `fr`.
 *   token: A key of `SETTINGS_SECTIONS`.
 *
 * Returns:
 *   The localized href, `?section=` included.
 */
export function settingsSectionHref(lng: string, token: SettingsSectionToken): string {
  return `/${lng}/dashboard/settings?section=${String(token)}`;
}
