/**
 * Where a screen was reached FROM (owner, 2026-09-10).
 *
 * Several doors lead to the meetings pages — the header, the phone menu, a
 * minutes card in the chat, a recorder toast, the settings section, a slash
 * command — and the list had no way back at all, while the detail and the
 * template library always returned to the list whatever opened them.
 *
 * Three decisions, and the second is a security one:
 *
 * - **The browser's history is not the answer.** It dies on a reload, it is
 *   empty when the page was opened from a notification, and after deleting a
 *   meeting it points at a page that no longer exists.
 * - **The origin travels as a TOKEN, never as a URL.** A `?back=<url>` is an
 *   open redirect the moment somebody types one; a token is looked up in a
 *   closed table and anything unrecognised falls back to the chat.
 * - **The vocabulary is the dashboard's own destination table.** It is not a
 *   second list to maintain, a token that is not a real screen cannot exist,
 *   and the word a back button shows is the very word the header shows for
 *   that screen — one label, two surfaces.
 *
 * The dashboard root is spelled `dashboard` on the wire rather than as the
 * empty string the table uses: an empty `?from=` is indistinguishable from no
 * origin at all.
 */

import { DASHBOARD_DESTINATIONS, destinationPath } from '@/lib/dashboard-nav';
import type { DashboardDestination } from '@/lib/dashboard-nav';

/** What the dashboard root is called on the wire. */
const ROOT_TOKEN = 'dashboard';

/** Where a reader goes when no origin travelled, or when one made no sense. */
const FALLBACK: DashboardDestination['segment'] = 'chat';

/** A resolved way back: where it goes, and the word it shows. */
export interface BackDestination {
  /** Unlocalized route — the caller's own router adds the language prefix. */
  href: string;
  /** i18n key of the visible label, the header's own word for that screen. */
  labelKey: string;
}

function destinationOf(segment: string): DashboardDestination | undefined {
  return DASHBOARD_DESTINATIONS.find(candidate => candidate.segment === segment);
}

/**
 * The destination token of the screen a path belongs to.
 *
 * A nested route answers its DESTINATION (`/dashboard/settings/x` is
 * "settings"), because that is the screen the reader would say they were on.
 *
 * @param pathname - The current path, language prefix included.
 * @returns The token, `''` for the dashboard root, or null when the path is
 *   not one of the dashboard's declared destinations.
 */
export function originFromPathname(pathname: string | null | undefined): string | null {
  if (!pathname) return null;
  const match = /\/dashboard(?:\/([^/?#]+))?/.exec(pathname);
  if (!match) return null;
  const segment = match[1] ?? '';
  return destinationOf(segment) ? segment : null;
}

/**
 * Where a back button goes, and what it says.
 *
 * @param token - The `?from=` value, if any.
 * @returns The resolved destination; the chat for a missing or unrecognised
 *   token, so a back button always leads somewhere real.
 */
export function backDestination(token: string | null | undefined): BackDestination {
  const segment = token === ROOT_TOKEN ? '' : (token ?? FALLBACK);
  const destination = destinationOf(segment) ?? destinationOf(FALLBACK);
  // The table always holds the fallback; the assertion is for the type only.
  const resolved = destination as DashboardDestination;
  return { href: destinationPath(resolved.segment), labelKey: resolved.labelKey };
}

/**
 * Stamp a route with the screen the reader is leaving.
 *
 * @param route - The unlocalized destination route.
 * @param origin - The current screen's token, from :func:`originFromPathname`.
 * @returns The route, with `?from=` when an origin is worth carrying — never
 *   when the origin IS the destination, since coming back to where you
 *   already are is not a way back.
 */
export function withOrigin(route: string, origin: string | null | undefined): string {
  if (origin === null || origin === undefined) return route;
  const [path] = route.split('?');
  if (path === destinationPath(origin as DashboardDestination['segment'])) return route;
  const separator = route.includes('?') ? '&' : '?';
  return `${route}${separator}from=${origin === '' ? ROOT_TOKEN : encodeURIComponent(origin)}`;
}
