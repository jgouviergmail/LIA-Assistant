import type { MetadataRoute } from 'next';
import { languages, fallbackLng } from '@/i18n/settings';
import type { Language } from '@/i18n/settings';
import { BLOG_ARTICLES } from '@/data/blog-articles';
import { PUBLIC_PAGES } from '@/lib/public-pages';
import { getSiteOrigin, localizedUrl } from '@/lib/site-origin';

// Evaluated per request so the generic prebuilt image serves the runtime
// APP_URL_SERVER origin (B03) instead of a build-time hostname.
export const dynamic = 'force-dynamic';

/**
 * Build the full URL for a given path and language.
 * French (default) has no prefix, other languages are prefixed.
 */
function buildUrl(path: string, lng: Language): string {
  // The caller returns an empty sitemap when no origin is configured, so
  // origin is non-null here; passing the path verbatim preserves the exact
  // historical URL shape (home keeps its trailing slash).
  return localizedUrl(getSiteOrigin(), path, lng);
}

/**
 * Build hreflang alternates for a given path across all supported languages.
 */
function buildAlternates(path: string): Record<string, string> {
  const alternates: Record<string, string> = {};
  for (const lng of languages) {
    alternates[lng] = buildUrl(path, lng);
  }
  // x-default points to the default language (French, no prefix)
  alternates['x-default'] = buildUrl(path, fallbackLng);
  return alternates;
}

/**
 * Dynamic sitemap generation with multilingual hreflang support.
 *
 * Public pages and blog articles are included. The page list is the shared
 * declaration (`lib/public-pages.ts`) that robots.txt reads too — a second copy
 * here is how `/more` and `/demo` ended up sitemapped but never allowed.
 * Each page has alternates for all 6 supported languages.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  if (getSiteOrigin() === null) {
    // Generic image without a configured origin: a sitemap of relative URLs
    // would be invalid — serve an honest empty one instead.
    return [];
  }
  const staticEntries = PUBLIC_PAGES.map(({ path, changeFrequency, priority }) => ({
    url: buildUrl(path, fallbackLng),
    lastModified: new Date(),
    changeFrequency,
    priority,
    alternates: {
      languages: buildAlternates(path),
    },
  }));

  // Blog article entries
  const blogEntries = BLOG_ARTICLES.map(article => ({
    url: buildUrl(`/blog/${article.slug}`, fallbackLng),
    lastModified: new Date(article.date),
    changeFrequency: 'monthly' as const,
    priority: 0.6,
    alternates: {
      languages: buildAlternates(`/blog/${article.slug}`),
    },
  }));

  return [...staticEntries, ...blogEntries];
}
