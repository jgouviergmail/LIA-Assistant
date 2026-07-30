/**
 * The dashboard's five destinations, in one place (A2, extended by R01).
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

/** A destination of the dashboard shell. */
export interface DashboardDestination {
  /** Path suffix appended to the localized `/dashboard` root ('' = the root). */
  segment: '' | 'chat' | 'relations' | 'settings' | 'faq';
  /** i18n key of the visible label. */
  labelKey: string;
}

/** Display order, shared by the desktop nav and the mobile menu. */
export const DASHBOARD_DESTINATIONS: readonly DashboardDestination[] = [
  { segment: '', labelKey: 'navigation.dashboard' },
  { segment: 'chat', labelKey: 'navigation.chat' },
  { segment: 'relations', labelKey: 'navigation.relations' },
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
