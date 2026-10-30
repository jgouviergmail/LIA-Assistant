import type { MetadataRoute } from 'next';

import { languages } from '@/i18n/settings';
import { indexablePathsWithoutHome } from '@/lib/public-pages';
import { getSiteOrigin } from '@/lib/site-origin';

// Evaluated per request so the generic prebuilt image serves the runtime
// APP_URL_SERVER origin (B03) instead of a build-time hostname.
export const dynamic = 'force-dynamic';

/**
 * Dynamic robots.txt generation
 *
 * Strategy — ONE group, the same rules for every crawler, AI bots included
 * (search, user-triggered fetches and training alike):
 * - Allow the public pages, read from the shared declaration the sitemap uses
 *   (`lib/public-pages.ts`) so a page can never be announced to crawlers and
 *   left out of the allow-list
 * - Block the authenticated areas (/dashboard, /api)
 * - Never block `/_next/*`: it holds the JS, CSS, fonts and optimized images a
 *   crawler needs to render the public pages, and nothing private
 */
export default function robots(): MetadataRoute.Robots {
  const locales = languages;
  // The shared declaration, plus the one wildcard a sitemap cannot express:
  // blog articles are enumerated there, but robots needs the whole subtree.
  const basePublicPaths = [...indexablePathsWithoutHome(), '/blog/*'];

  const publicPaths = [
    '/',
    ...basePublicPaths,
    ...locales.flatMap(lng => [`/${lng}`, ...basePublicPaths.map(p => `/${lng}${p}`)]),
  ];

  const baseBlockedPaths = ['/dashboard', '/dashboard/*', '/account-inactive'];

  const blockedPaths = [
    ...baseBlockedPaths,
    '/api/*',
    ...locales.flatMap(lng => baseBlockedPaths.map(p => `/${lng}${p}`)),
  ];

  const origin = getSiteOrigin();
  return {
    // A named group would make its crawler ignore this one (RFC 9309), so a
    // per-bot group is only ever written to give that bot DIFFERENT rules.
    rules: [{ userAgent: '*', allow: publicPaths, disallow: blockedPaths }],
    // robots.txt requires an absolute sitemap URL; without a configured
    // origin the line is honestly omitted rather than invented.
    ...(origin ? { sitemap: `${origin}/sitemap.xml` } : {}),
  };
}
