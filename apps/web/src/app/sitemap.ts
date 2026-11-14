import type { MetadataRoute } from 'next';
import { languages } from '@/i18n/settings';
import { BLOG_ARTICLES } from '@/data/blog-articles';
import { languageAlternates, siteUrl } from '@/lib/public-page-metadata';
import { PUBLIC_PAGES } from '@/lib/public-pages';
import { getSiteOrigin } from '@/lib/site-origin';
import { LAST_UPDATED } from '@/lib/version';

// Evaluated per request so the generic prebuilt image serves the runtime
// APP_URL_SERVER origin (B03) instead of a build-time hostname.
export const dynamic = 'force-dynamic';

/**
 * The day of the release this build ships, at midnight UTC.
 *
 * The release stamp carries no zone: read as a day it can never name an instant
 * later than the moment a crawler reads it.
 */
function releaseDay(): Date {
  return new Date(LAST_UPDATED.slice(0, 10));
}

/** The day an article was last revised, else the day it was published. */
function articleDay(article: (typeof BLOG_ARTICLES)[number]): Date {
  return new Date(article.updated ?? article.date);
}

/**
 * Dynamic sitemap generation with multilingual hreflang support.
 *
 * Public pages and blog articles are included. The page list is the shared
 * declaration (`lib/public-pages.ts`) that robots.txt reads too — a second copy
 * here is how `/more` and `/demo` ended up sitemapped but never allowed.
 *
 * Two rules search engines publish for a multilingual sitemap are held here:
 * - EVERY language version is an entry of its own, and each entry lists the
 *   whole set of alternates, itself included (`x-default` too). A version that
 *   only appears as someone else's alternate is not an announced URL.
 * - `lastModified` is a claim, read only as long as it is true: a page that
 *   follows the release takes the release's day, an article takes its own
 *   revision day, and a page with no known date states none. It is never the
 *   moment the sitemap was asked for.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  if (getSiteOrigin() === null) {
    // Generic image without a configured origin: a sitemap of relative URLs
    // would be invalid — serve an honest empty one instead.
    return [];
  }
  const release = releaseDay();
  const newestArticle = new Date(
    Math.max(...BLOG_ARTICLES.map(article => articleDay(article).getTime()))
  );

  const staticEntries = PUBLIC_PAGES.flatMap(
    ({ path, changeFrequency, priority, lastModified }) => {
      const modified =
        lastModified === 'release'
          ? release
          : lastModified === 'articles'
            ? newestArticle
            : undefined;
      const alternates = { languages: languageAlternates(path) };
      return languages.map(lng => ({
        url: siteUrl(path, lng),
        ...(modified ? { lastModified: modified } : {}),
        changeFrequency,
        priority,
        alternates,
      }));
    }
  );

  const blogEntries = BLOG_ARTICLES.flatMap(article => {
    const path = `/blog/${article.slug}`;
    const alternates = { languages: languageAlternates(path) };
    return languages.map(lng => ({
      url: siteUrl(path, lng),
      lastModified: articleDay(article),
      changeFrequency: 'monthly' as const,
      priority: 0.6,
      alternates,
    }));
  });

  return [...staticEntries, ...blogEntries];
}
