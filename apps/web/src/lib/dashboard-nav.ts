/**
 * The dashboard's four destinations, in one place (A2).
 *
 * Below `md` the header's `<nav>` is hidden, and nothing replaced it: a phone
 * user could reach the dashboard (through the logo) and no other page at all —
 * no chat, no settings, no help. The way back existed only by typing a URL.
 *
 * This table is what both surfaces render: the desktop `<nav>` and the mobile
 * menu the logo opens. Two lists would drift, and the one that drifted would be
 * the mobile one — the one nobody looks at on a large screen.
 */

/** A destination of the dashboard shell. */
export interface DashboardDestination {
  /** Path suffix appended to the localized `/dashboard` root ('' = the root). */
  segment: '' | 'chat' | 'settings' | 'faq';
  /** i18n key of the visible label. */
  labelKey: string;
}

/** Display order, shared by the desktop nav and the mobile menu. */
export const DASHBOARD_DESTINATIONS: readonly DashboardDestination[] = [
  { segment: '', labelKey: 'navigation.dashboard' },
  { segment: 'chat', labelKey: 'navigation.chat' },
  { segment: 'settings', labelKey: 'navigation.settings' },
  { segment: 'faq', labelKey: 'navigation.faq' },
];

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
