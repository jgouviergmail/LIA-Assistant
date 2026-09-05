/**
 * Deep-linkable settings sections (W2, master-detail since the shell rework).
 *
 * This table is the single source of truth for the settings surface:
 * `?section=` deep links resolve through it, the master-detail shell renders
 * its rail and overview FROM it (order included), and the pane mounts the
 * component `SETTINGS_SECTION_REGISTRY` associates with each token. The
 * checklist and the dashboard cards consume it to build their hrefs.
 *
 * Each entry maps a stable URL token to:
 *   - the TAB the section belongs to (a rail block; `administration` renders
 *     for superusers only);
 *   - the `value` of the target `<SettingsSection>` — the pane polls the
 *     `#settings-section-<value>` anchor to detect a section that renders
 *     nothing.
 *
 * The values are not free-form: they must match the `value` prop of the
 * corresponding component, and a test asserts exactly that against the source.
 */

/** Rail blocks of the settings page. `administration` is superuser-only. */
export type SettingsTab = 'preferences' | 'features' | 'administration';

export interface SettingsSectionTarget {
  /** Rail block the section belongs to. */
  tab: SettingsTab;
  /** `value` of the target `<SettingsSection>` — its DOM anchor id suffix. */
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
 * The table covers every section of every tab, administration included
 * (phase 2 of ADR-172). Admin entries are filtered per-user by the `superuser`
 * gate in `settings-search.ts` — the table itself stays user-agnostic, like
 * the rest of the deep-link surface.
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
  // The location cascade (ADR-219: live > remembered > home) — a standalone
  // section since 2026-08: the data lives on the user, not on the Google
  // Places connector card it used to be nested under.
  location: {
    tab: 'preferences',
    accordionValue: 'location',
    declaredIn: 'components/settings/LocationSettings.tsx',
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
  'eyes-style': {
    tab: 'preferences',
    accordionValue: 'eyes-style',
    declaredIn: 'components/settings/EyesStyleSettings.tsx',
  },
  'display-mode': {
    tab: 'preferences',
    accordionValue: 'display-mode',
    declaredIn: 'components/settings/CardsDisplaySettings.tsx',
  },
  // Renders nothing where `navigator.vibrate` is absent (desktop, iOS Safari),
  // so a deep link can legitimately resolve to an absent section — same as the
  // other capability-gated entries here.
  haptics: {
    tab: 'preferences',
    accordionValue: 'haptics',
    declaredIn: 'components/settings/HapticsSettings.tsx',
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
  // Commitments moved out of Preferences (2026-08-02): a ledger of what people
  // owe each other is a capability, not a display preference. Kept immediately
  // after `interests`, which is the order the Features tab renders.
  'open-loops': {
    tab: 'features',
    accordionValue: 'open-loops',
    declaredIn: 'components/settings/OpenLoopsSection.tsx',
  },
  // Learned habits (ADR-214): a capability like open-loops, self-gated on the
  // instance flag `features.habits_enabled`.
  habits: {
    tab: 'features',
    accordionValue: 'habits',
    declaredIn: 'components/settings/HabitsSettings.tsx',
  },
  // Renders nothing when the instance flag `features.peers_enabled` is off
  // (self-gating, OpenLoopsSection precedent) — a deep link then legitimately
  // resolves to an absent section, like the other capability-gated entries.
  'peer-connections': {
    tab: 'features',
    accordionValue: 'peer-connections',
    declaredIn: 'components/settings/PeerConnectionsSettings.tsx',
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
  plugins: {
    tab: 'features',
    accordionValue: 'plugins',
    declaredIn: 'components/settings/PluginsSettings.tsx',
  },
  // The two MCP sections moved here from Preferences › Connections (2026-08-18):
  // a server that hands the assistant new tools EXTENDS it, where a connector
  // links a personal account. They sit right after `plugins`, which installs
  // skills and MCP servers together. The tokens are URL surface and unchanged.
  'admin-mcp-servers': {
    tab: 'features',
    accordionValue: 'admin-mcp-servers',
    declaredIn: 'components/settings/AdminMCPServersSettings.tsx',
  },
  'mcp-servers': {
    tab: 'features',
    accordionValue: 'mcp-servers',
    declaredIn: 'components/settings/MCPServersSettings.tsx',
  },
  'rag-spaces': {
    tab: 'features',
    accordionValue: 'rag-spaces',
    declaredIn: 'components/spaces/SpacesSettingsSection.tsx',
  },
  // Meeting recording & minutes (ADR-258). Self-gated on the instance flag
  // `features.meetings_enabled` (OpenLoopsSection precedent): a deep link
  // may legitimately resolve to an absent section.
  meetings: {
    tab: 'features',
    accordionValue: 'meetings',
    declaredIn: 'components/settings/MeetingsSettings.tsx',
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

  // ---- Administration tab (superusers only — phase 2 of ADR-172)
  // Deep links and search cover the admin surface like any other: a
  // non-superuser never sees these entries (gate `superuser` in the search
  // meta), and a deep link resolves through the same `?section=` mechanism.
  'admin-users': {
    tab: 'administration',
    accordionValue: 'admin-users',
    declaredIn: 'components/settings/AdminUsersSection.tsx',
  },
  'admin-usage-limits': {
    tab: 'administration',
    accordionValue: 'admin-usage-limits',
    declaredIn: 'components/settings/AdminUsageLimitsSection.tsx',
  },
  // Same runtime-valued component as `user-consumption-export`, rendered
  // through the thin `AdminConsumptionExportSection` wrapper — which is what
  // the administration panel mounts, so the tab check points at the wrapper
  // while the value literal lives in the wrapped component.
  'admin-consumption-export': {
    tab: 'administration',
    accordionValue: 'admin-consumption-export',
    declaredIn: 'components/settings/AdminConsumptionExportSection.tsx',
  },
  'admin-broadcast': {
    tab: 'administration',
    accordionValue: 'admin-broadcast',
    declaredIn: 'components/settings/AdminBroadcastSection.tsx',
  },
  'admin-connectors': {
    tab: 'administration',
    accordionValue: 'admin-connectors',
    declaredIn: 'components/settings/AdminConnectorsSection.tsx',
  },
  'admin-llm-pricing': {
    tab: 'administration',
    accordionValue: 'admin-llm-pricing',
    declaredIn: 'components/settings/AdminLLMPricingSection.tsx',
  },
  'admin-google-api-pricing': {
    tab: 'administration',
    accordionValue: 'admin-google-api-pricing',
    declaredIn: 'components/settings/AdminGoogleApiPricingSection.tsx',
  },
  'admin-image-pricing': {
    tab: 'administration',
    accordionValue: 'admin-image-pricing',
    declaredIn: 'components/settings/AdminImagePricingSection.tsx',
  },
  'admin-llm-config': {
    tab: 'administration',
    accordionValue: 'admin-llm-config',
    declaredIn: 'components/settings/AdminLLMConfigSection.tsx',
  },
  'admin-personalities': {
    tab: 'administration',
    accordionValue: 'admin-personalities',
    declaredIn: 'components/settings/AdminPersonalitiesSection.tsx',
  },
  'admin-skills': {
    tab: 'administration',
    accordionValue: 'admin-skills',
    declaredIn: 'components/settings/AdminSkillsSection.tsx',
  },
  // Historic value — predates the `admin-` prefix convention; a rename would
  // break bookmarked links, so it stays (tokens are URL surface: add, never
  // rename).
  'rag-spaces-admin': {
    tab: 'administration',
    accordionValue: 'rag-spaces-admin',
    declaredIn: 'components/settings/AdminRAGSpacesSection.tsx',
  },
  'admin-capabilities': {
    tab: 'administration',
    accordionValue: 'admin-capabilities',
    declaredIn: 'components/settings/AdminCapabilitiesSection.tsx',
  },
  'admin-public-demo-link': {
    tab: 'administration',
    accordionValue: 'admin-public-demo-link',
    declaredIn: 'components/settings/AdminPublicDemoLinkSection.tsx',
  },
  'admin-registers': {
    tab: 'administration',
    accordionValue: 'admin-registers',
    declaredIn: 'components/settings/AdminRegistersSection.tsx',
  },
  'admin-diagnostics': {
    tab: 'administration',
    accordionValue: 'admin-diagnostics',
    declaredIn: 'components/settings/AdminDiagnosticsSection.tsx',
  },
  // Same historic naming note as `rag-spaces-admin`.
  'debug-settings': {
    tab: 'administration',
    accordionValue: 'debug-settings',
    declaredIn: 'components/settings/AdminDebugSettingsSection.tsx',
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
