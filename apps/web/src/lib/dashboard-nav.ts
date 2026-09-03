/**
 * The dashboard's destinations, in one place (A2, extended by R01).
 *
 * Below `lg` (raised from `md` by R01 — five destinations clip in fr/de/es/it
 * between 768 and 1024 px) the header's `<nav>` is hidden, and nothing once
 * replaced it: a phone user could reach the dashboard (through the logo) and
 * no other page at all. The way back existed only by typing a URL.
 *
 * This table is what both surfaces render: the desktop `<nav>` and the mobile
 * menu the logo opens. Two lists would drift, and the one that drifted would be
 * the mobile one — the one nobody looks at on a large screen.
 *
 * R01 (2026-07): `spaces` joined the table because the chat indicator used
 * to render nothing without spaces. Superseded (2026-07-30): the indicator
 * now always renders, so the slot goes to `relations` — the personal CRM,
 * which had NO navigation home at all (settings search and a briefing
 * shortcut were its only doors). Spaces stays one click away in the chat.
 */

/** Instance feature flags a destination may depend on (`useAppConfig().features`). */
export interface DestinationFeatures {
  meetings_enabled?: boolean;
}

/** A destination of the dashboard shell. */
export interface DashboardDestination {
  /** Path suffix appended to the localized `/dashboard` root ('' = the root). */
  segment: '' | 'chat' | 'relations' | 'meetings' | 'notifications' | 'settings' | 'faq';
  /** i18n key of the visible label. */
  labelKey: string;
  /**
   * Instance flag the destination needs. Absent = always offered. A gated
   * destination whose flag is off is not a dead link, it does not exist:
   * both renderers read the table through `visibleDestinations`.
   */
  feature?: keyof DestinationFeatures;
}

/**
 * Display order, shared by the desktop nav and the mobile menu.
 *
 * 2026-08-03: `notifications` joins the table, to the right of `relations` —
 * what LIA sends the reader was scattered across four settings sections
 * (device notifications, proactivity, interests, channels) with no single
 * place answering "what reached me, and what is coming?".
 *
 * 2026-09-03 (ADR-258): `meetings` joins between `relations` and
 * `notifications` — the recordings and their minutes had a page, a settings
 * section and a slash command, but no door in the header. SEVEN labels is the
 * widest this row has ever been; the renderer keeps labels from `xl`, and the
 * header paid for the seventh elsewhere: the language control shows its flag
 * alone at every width (the popup names the languages) and the personality
 * title waits for `2xl`. The label is deliberately SHORT in every locale.
 */
export const DASHBOARD_DESTINATIONS: readonly DashboardDestination[] = [
  { segment: '', labelKey: 'navigation.dashboard' },
  { segment: 'chat', labelKey: 'navigation.chat' },
  { segment: 'relations', labelKey: 'navigation.relations' },
  { segment: 'meetings', labelKey: 'navigation.meetings', feature: 'meetings_enabled' },
  { segment: 'notifications', labelKey: 'navigation.notifications' },
  { segment: 'settings', labelKey: 'navigation.settings' },
  { segment: 'faq', labelKey: 'navigation.faq' },
];

/**
 * The destinations this instance offers.
 *
 * Args:
 *   features: The instance flags (`useAppConfig().features`), possibly not
 *     loaded yet — an unknown flag reads as OFF, so a gated destination never
 *     flashes in before the configuration answers.
 *
 * Returns:
 *   The table, in order, without the gated destinations whose flag is off.
 */
export function visibleDestinations(
  features: DestinationFeatures | null | undefined
): readonly DashboardDestination[] {
  return DASHBOARD_DESTINATIONS.filter(
    destination => destination.feature === undefined || features?.[destination.feature] === true
  );
}

/**
 * Route of a destination, before localization.
 *
 * Args:
 *   segment: The destination's segment.
 *
 * Returns:
 *   `/dashboard` for the root, `/dashboard/<segment>` otherwise.
 */
export function destinationPath(segment: DashboardDestination['segment']): string {
  return segment ? `/dashboard/${segment}` : '/dashboard';
}

// Deliberately NO active-state helper here: the layout already owns
// `isActiveRoute`, which handles nested routes (`/dashboard/settings/x` still
// highlights Settings). A second implementation would be the one that drifts.
