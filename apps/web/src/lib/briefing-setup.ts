/**
 * Cards that are not configured yet (W7) — naming the silence.
 *
 * ## The defect
 *
 * `BriefingCard` returns `null` on `status === 'not_configured'`, and SEVEN of
 * the nine cards can reach that status: weather, agenda, mails, birthdays,
 * health, tasks and documents each raise `ConnectorNotConfiguredError` when
 * their source is missing (`apps/api/src/domains/briefing/fetchers.py`). Only
 * `reminders` and `for_you` always resolve — and both are empty for a new
 * account.
 *
 * So the very first screen after signing up renders two empty cards and seven
 * invisible holes: no card, no message, no path to the settings. The existing
 * fallback in `TodayBriefing` only covers the case where the user HID every
 * card themselves (`sections.length === 0`), which is a different situation.
 *
 * ## What this module does
 *
 * It answers, purely: among the cards the user actually wants to see, which
 * ones are waiting for a configuration, and where does each one get configured.
 * The rendering is one discreet line — never seven promotional cards, which
 * would be worse than the silence, and unaffordable on mobile.
 *
 * Hidden cards are deliberately excluded: asking someone to connect a card they
 * chose to hide would be noise, not help.
 */

import { BRIEFING_SECTION_NAMES, type BriefingSection, type CardsBundle } from '@/types/briefing';
import { type SettingsSectionToken } from '@/lib/settings-sections';

/**
 * Where each card gets configured.
 *
 * Verified against the fetchers, one raise site at a time:
 *  - weather      → per-user OpenWeatherMap API key + a usable location
 *  - agenda/mails/birthdays/tasks/documents → the corresponding connector
 *  - health       → the `health-metrics` toggle (or the server-side flag)
 *  - reminders/for_you → local tables, never `not_configured`, hence `null`
 *
 * `null` means "this card cannot report a missing configuration", NOT "we do
 * not know where to send the user" — the completeness test pins the difference.
 */
export const SECTION_SETTINGS_TARGET: Readonly<
  Record<BriefingSection, SettingsSectionToken | null>
> = {
  weather: 'connectors',
  agenda: 'connectors',
  mails: 'connectors',
  birthdays: 'connectors',
  tasks: 'connectors',
  documents: 'connectors',
  health: 'health-metrics',
  reminders: null,
  for_you: null,
};

/** A card the user wants to see but that has no data source yet. */
export interface UnconfiguredCard {
  section: BriefingSection;
  /** Settings section to deep-link to, when one exists. */
  target: SettingsSectionToken | null;
}

/**
 * List the visible cards that report a missing configuration.
 *
 * Args:
 *   cards: The bundle returned by `/briefing/cards`.
 *   visible: The sections the user actually displays, in preference order.
 *
 * Returns:
 *   One entry per unconfigured card, in the order the grid uses. Empty when
 *   everything is configured — the caller then renders nothing at all.
 */
export function unconfiguredCards(
  cards: CardsBundle | undefined,
  visible: readonly BriefingSection[]
): UnconfiguredCard[] {
  if (!cards) return [];
  return visible
    .filter(section => cards[section]?.status === 'not_configured')
    .map(section => ({ section, target: SECTION_SETTINGS_TARGET[section] }));
}

/** Completeness guard: the table must cover every declared section. */
export function assertSettingsTargetCompleteness(): void {
  const missing = BRIEFING_SECTION_NAMES.filter(section => !(section in SECTION_SETTINGS_TARGET));
  if (missing.length > 0) {
    throw new Error(`SECTION_SETTINGS_TARGET is missing: ${missing.join(', ')}`);
  }
}
