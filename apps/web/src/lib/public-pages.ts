/**
 * The public pages of the site, as ONE list.
 *
 * `sitemap.ts` and `robots.ts` both need to know what is public, and both used
 * to carry their own hand-typed copy. The copies drifted, as copies do: `/more`
 * and `/demo` were announced in the sitemap while no robots rule ever named
 * them, and adding `/changelog` meant remembering two files. A second
 * hand-maintained list is how a page ships and is never declared — so there is
 * one list, and `__tests__/public-pages.test.ts` checks it against the
 * filesystem so a new page cannot stay silently undeclared.
 *
 * This is the SEO declaration only. Two neighbouring lists answer different
 * questions and must not be merged into it:
 *  - `PUBLIC_ROUTE_SEGMENTS` (`api-client.ts`) answers "may an anonymous
 *    visitor stay here on a 401?" — true for token-bearing pages like
 *    `/reset-password`, which must never be indexed;
 *  - `PUBLIC_FAQ_SECTIONS` and friends answer what a given page renders.
 */

/** How often a page's content is expected to change, in sitemap vocabulary. */
export type ChangeFrequency = 'weekly' | 'monthly' | 'yearly';

/** One indexable public page. */
export interface PublicPage {
  /** Unlocalized path, always absolute (`/faq`, `/` for the home). */
  readonly path: string;
  /** Sitemap `changefreq` hint. */
  readonly changeFrequency: ChangeFrequency;
  /** Sitemap `priority`, 0 to 1. */
  readonly priority: number;
}

/**
 * Every indexable public page, in sitemap order.
 *
 * `/changelog` is `weekly` like the blog and the home: it gains an entry at
 * every release, which is precisely the rhythm a crawler should expect.
 */
export const PUBLIC_PAGES: readonly PublicPage[] = [
  { path: '/', changeFrequency: 'weekly', priority: 1.0 },
  { path: '/blog', changeFrequency: 'weekly', priority: 0.8 },
  { path: '/faq', changeFrequency: 'monthly', priority: 0.7 },
  { path: '/changelog', changeFrequency: 'weekly', priority: 0.6 },
  { path: '/more', changeFrequency: 'monthly', priority: 0.7 },
  { path: '/demo', changeFrequency: 'monthly', priority: 0.5 },
  { path: '/why', changeFrequency: 'monthly', priority: 0.7 },
  { path: '/how', changeFrequency: 'monthly', priority: 0.7 },
  { path: '/story', changeFrequency: 'monthly', priority: 0.7 },
  { path: '/privacy', changeFrequency: 'yearly', priority: 0.5 },
  { path: '/terms', changeFrequency: 'yearly', priority: 0.5 },
  { path: '/login', changeFrequency: 'monthly', priority: 0.3 },
  { path: '/register', changeFrequency: 'monthly', priority: 0.3 },
];

/**
 * Routes deliberately kept out of the indexable set, and why.
 *
 * The reason is not decoration: it is what makes the completeness guard a
 * decision rather than a rubber stamp. A route landing here without one fails
 * the guard.
 */
export const NON_INDEXED_SEGMENTS: Readonly<Record<string, string>> = {
  dashboard: 'authenticated area — blocked for every crawler',
  'account-inactive': 'authenticated lifecycle state, meaningless without a session',
  'registration-success': 'transient confirmation reached only after a POST',
  'forgot-password': 'account-recovery entry point, no content to rank',
  'reset-password': 'token-bearing URL — indexing one would publish the token',
  'verify-email': 'token-bearing URL — indexing one would publish the token',
  'oauth-callback': 'transient provider redirect, never a destination',
  'native-auth': 'code-bearing deep-link landing for the shells — indexing one would publish the code',
  share: 'PWA share-target receiver, redirects immediately',
};

/** Sitemap paths, home excluded — the shape robots.txt lists. */
export function indexablePathsWithoutHome(): string[] {
  return PUBLIC_PAGES.filter(page => page.path !== '/').map(page => page.path);
}
