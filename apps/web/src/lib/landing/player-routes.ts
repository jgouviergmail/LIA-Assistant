/**
 * Where the persistent landing player lives (ADR-330 amendment): on the public
 * pages, by a declared list. The sign-in group, the dashboard and the two
 * routes that are neither public nor private stop it. A route named on
 * neither list is a stop — and a test demands that every route under
 * `app/[lng]` be named on one, so a page added later chooses in writing.
 *
 * The default language is served WITHOUT its prefix (`/` is the French
 * landing, `/blog` its blog; `/en/blog` the English one — measured on dev,
 * where `usePathname()` answered `/` and the first classifier read a stop),
 * so the route is the first segment unless that segment is a language.
 */

import { languages } from '@/i18n/settings';

/** The second path segment (after the language) of each public page; `''` is the landing. */
export const PUBLIC_PLAYER_ROUTES: readonly string[] = [
  '',
  'blog',
  'changelog',
  'demo',
  'faq',
  'how',
  'maps',
  'more',
  'privacy',
  'story',
  'terms',
  'why',
];

/** The routes where the player stops and leaves the DOM. */
export const PLAYER_STOP_ROUTES: readonly string[] = [
  'account-inactive',
  'dashboard',
  'share',
  'forgot-password',
  'login',
  'native-auth',
  'oauth-callback',
  'register',
  'registration-success',
  'reset-password',
  'verify-email',
];

export type PlayerRouteKind = 'public' | 'stop';

/** What a pathname means for the player: its route segment, after the language when there is one. */
export function playerRouteKind(pathname: string): PlayerRouteKind {
  const path = pathname.split(/[?#]/, 1)[0] ?? '';
  const [first = '', ...rest] = path.split('/').filter(Boolean);
  const route = (languages as readonly string[]).includes(first) ? (rest[0] ?? '') : first;
  return PUBLIC_PLAYER_ROUTES.includes(route) ? 'public' : 'stop';
}
