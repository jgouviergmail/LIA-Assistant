/**
 * Which settings section governs which capability — declared once, read both ways.
 *
 * Two surfaces need this pairing, in opposite directions:
 *
 *   - the capability constellation asks *"where do I set this up?"* and turns
 *     a dormant star into the ONE next step it exists to offer;
 *   - the settings overview asks *"what does this section currently hold?"*
 *     and puts the answer on the section's card.
 *
 * Two hand-written tables would eventually disagree about the same pair — the
 * class of drift this repo keeps paying for — so the reverse direction is
 * derived, never typed twice.
 *
 * A capability no section configures is simply absent; both lookups answer
 * `null` rather than guessing. (Document generation was that case until the
 * « Documents » section gave the reader its illustration and animation
 * choices, 2026-11-13.) The backend guard
 * `test_capability_coverage_guard.py` reads this file and fails when a
 * capability ships without either a pairing here or a written exemption.
 *
 * A capability whose place is a PAGE of the application rather than a section
 * of the settings says so in `CAPABILITY_PAGE`: the constellation then sends
 * the reader there, never to the settings root.
 */

import type { SettingsSectionToken } from '@/lib/settings-sections';

/**
 * Capability node key → the settings section that configures it.
 *
 * Keys are the `capabilities.nodes.*` identifiers the `/capabilities` payload
 * carries; the map is injective (see the sibling test), because the reverse
 * lookup has to name exactly one capability per card.
 */
export const CAPABILITY_SECTION: Readonly<Record<string, SettingsSectionToken>> = {
  connectors: 'connectors',
  memory: 'memories',
  personality: 'personality',
  voice: 'voice-mode',
  proactivity: 'heartbeat',
  proactive_discussions: 'proactive-discussions',
  images: 'image-generation',
  // How the documents LIA creates are illustrated and animated.
  documents: 'documents',
  interests: 'interests',
  routines: 'scheduled-actions',
  // The node that counts open loops points at the section that holds them.
  // It was keyed « relations » and pointed here, so « Relationships » sent a
  // reader to their unfinished threads.
  open_loops: 'open-loops',
  reminders: 'reminders',
  generated_files: 'generated-assets',
  habits: 'habits',
  peers: 'peer-connections',
  channels: 'channels',
  telephony: 'telephony-calls',
  live: 'live-mode',
  avatar: 'avatar',
  radio: 'radio',
  spaces: 'rag-spaces',
  journals: 'journals',
  skills: 'skills',
  plugins: 'plugins',
  mcp_servers: 'mcp-servers',
  meetings: 'meetings',
  sms: 'sms',
};

/** The derived reverse: settings section → the capability it governs. */
export const SECTION_CAPABILITY: Readonly<Partial<Record<SettingsSectionToken, string>>> =
  Object.fromEntries(
    Object.entries(CAPABILITY_SECTION).map(([capability, token]) => [token, capability])
  );

/**
 * Capabilities that land on a TAB of a section another capability already
 * owns. Kept OUT of `CAPABILITY_SECTION` on purpose: that table is a bijection
 * (one section, one status on its overview card), and the kept answers share
 * the generated-files section with the files — the card keeps the files'
 * status, the node keeps its own destination (ADR-282).
 */
export const CAPABILITY_SECTION_TAB: Readonly<
  Record<string, { readonly token: SettingsSectionToken; readonly tab: string }>
> = {
  bookmarks: { token: 'generated-assets', tab: 'bookmarks' },
};

/**
 * Capability node key → the dashboard page it lives on, when no settings
 * section configures it.
 *
 * The relations are set up where they are read: ADR-269 put the debrief's
 * switch on the Relations page. The workboard had a settings section, the
 * board's only door besides a notification, until the owner made the board a
 * destination of the header (2026-11-11) and that section went. Both stars
 * lead to the page itself — and every page named here is a destination the
 * header offers (`lib/dashboard-nav.ts`), which the sibling test holds.
 */
export const CAPABILITY_PAGE: Readonly<Record<string, string>> = {
  relations: '/dashboard/relations',
  workboard: '/dashboard/workboard',
};

/**
 * The page a capability lives on, when it has no settings section.
 *
 * @param capability - A `capabilities.nodes.*` key.
 * @returns Its route under the localized root, or null.
 */
export function pageOfCapability(capability: string): string | null {
  return CAPABILITY_PAGE[capability] ?? null;
}

/**
 * The section that configures a capability.
 *
 * @param capability - A `capabilities.nodes.*` key.
 * @returns Its settings token, or null when the capability has no section.
 */
export function sectionOfCapability(capability: string): SettingsSectionToken | null {
  return CAPABILITY_SECTION[capability] ?? CAPABILITY_SECTION_TAB[capability]?.token ?? null;
}

/**
 * The tab of that section the capability lands on, when it shares the section.
 *
 * @param capability - A `capabilities.nodes.*` key.
 * @returns The tab key, or null when the capability owns its whole section.
 */
export function tabOfCapability(capability: string): string | null {
  return CAPABILITY_SECTION_TAB[capability]?.tab ?? null;
}

/**
 * The capability a settings section governs.
 *
 * @param token - A settings section token.
 * @returns Its capability key, or null when the section holds no capability
 *   the map tracks (a display preference, an export, an admin panel).
 */
export function capabilityOfSection(token: SettingsSectionToken): string | null {
  return SECTION_CAPABILITY[token] ?? null;
}
