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
 * A capability with no section (document generation: the instance offers it or
 * it does not, there is nothing for a reader to configure) is simply absent;
 * both lookups answer `null` rather than guessing. The backend guard
 * `test_capability_coverage_guard.py` reads this file and fails when a
 * capability ships without either a pairing here or a written exemption.
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
  images: 'image-generation',
  interests: 'interests',
  routines: 'scheduled-actions',
  relations: 'open-loops',
  habits: 'habits',
  peers: 'peer-connections',
  channels: 'channels',
  telephony: 'telephony-calls',
  spaces: 'rag-spaces',
  journals: 'journals',
  skills: 'skills',
  plugins: 'plugins',
  mcp_servers: 'mcp-servers',
  meetings: 'meetings',
};

/** The derived reverse: settings section → the capability it governs. */
export const SECTION_CAPABILITY: Readonly<Partial<Record<SettingsSectionToken, string>>> =
  Object.fromEntries(
    Object.entries(CAPABILITY_SECTION).map(([capability, token]) => [token, capability])
  );

/**
 * The section that configures a capability.
 *
 * @param capability - A `capabilities.nodes.*` key.
 * @returns Its settings token, or null when the capability has no section.
 */
export function sectionOfCapability(capability: string): SettingsSectionToken | null {
  return CAPABILITY_SECTION[capability] ?? null;
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
