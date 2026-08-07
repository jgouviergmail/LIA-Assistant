import type { MetadataRoute } from 'next';

import { getSiteOrigin } from '@/lib/site-origin';

// Evaluated per request so the generic prebuilt image serves the runtime
// APP_URL_SERVER origin (B03) instead of a build-time hostname.
export const dynamic = 'force-dynamic';

/**
 * Dynamic robots.txt generation
 *
 * Strategy:
 * - Allow traditional search engines (Googlebot, Bingbot) on public pages
 * - Allow AI search bots (OAI-SearchBot, Claude-SearchBot, PerplexityBot) for GEO visibility
 * - Allow user-triggered AI fetches (ChatGPT-User, Claude-User)
 * - Block AI training crawlers (GPTBot, ClaudeBot, Google-Extended, CCBot, Bytespider)
 * - Block all bots from authenticated areas (/dashboard, /api)
 */
export default function robots(): MetadataRoute.Robots {
  const locales = ['fr', 'en', 'de', 'es', 'it', 'zh'];
  const basePublicPaths = [
    '/login',
    '/register',
    '/faq',
    '/why',
    '/how',
    '/story',
    '/blog',
    '/blog/*',
    '/privacy',
    '/terms',
  ];

  const publicPaths = [
    '/',
    ...basePublicPaths,
    ...locales.flatMap(lng => [`/${lng}`, ...basePublicPaths.map(p => `/${lng}${p}`)]),
  ];

  const baseBlockedPaths = ['/dashboard', '/dashboard/*', '/account-inactive'];

  const blockedPaths = [
    ...baseBlockedPaths,
    '/api/*',
    '/_next/*',
    ...locales.flatMap(lng => baseBlockedPaths.map(p => `/${lng}${p}`)),
  ];

  const origin = getSiteOrigin();
  return {
    rules: [
      // --- AI Training Crawlers: BLOCK everything ---
      {
        userAgent: 'GPTBot',
        disallow: ['/'],
      },
      {
        userAgent: 'ClaudeBot',
        disallow: ['/'],
      },
      {
        userAgent: 'Google-Extended',
        disallow: ['/'],
      },
      {
        userAgent: 'CCBot',
        disallow: ['/'],
      },
      {
        userAgent: 'Bytespider',
        disallow: ['/'],
      },
      {
        userAgent: 'anthropic-ai',
        disallow: ['/'],
      },

      // --- AI Search Bots: ALLOW public pages ---
      {
        userAgent: 'OAI-SearchBot',
        allow: publicPaths,
        disallow: blockedPaths,
      },
      {
        userAgent: 'ChatGPT-User',
        allow: publicPaths,
        disallow: blockedPaths,
      },
      {
        userAgent: 'Claude-SearchBot',
        allow: publicPaths,
        disallow: blockedPaths,
      },
      {
        userAgent: 'Claude-User',
        allow: publicPaths,
        disallow: blockedPaths,
      },
      {
        userAgent: 'PerplexityBot',
        allow: publicPaths,
        disallow: blockedPaths,
      },

      // --- Default: Allow public, block authenticated areas ---
      {
        userAgent: '*',
        allow: publicPaths,
        disallow: blockedPaths,
      },
    ],
    // robots.txt requires an absolute sitemap URL; without a configured
    // origin the line is honestly omitted rather than invented.
    ...(origin ? { sitemap: `${origin}/sitemap.xml` } : {}),
  };
}
