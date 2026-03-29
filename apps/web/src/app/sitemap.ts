import type { MetadataRoute } from 'next';
import { languages, fallbackLng } from '@/i18n/settings';
import type { Language } from '@/i18n/settings';
import { BLOG_ARTICLES } from '@/data/blog-articles';

const BASE_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://lia.jeyswork.com';

/**
 * Build the full URL for a given path and language.
 * French (default) has no prefix, other languages are prefixed.
 */
function buildUrl(path: string, lng: Language): string {
  const prefix = lng === fallbackLng ? '' : `/${lng}`;
  return `${BASE_URL}${prefix}${path}`;
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
 * Public pages and blog articles are included.
 * Each page has alternates for all 6 supported languages.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  const publicPages = [
    { path: '/', changeFrequency: 'weekly' as const, priority: 1.0 },
    { path: '/blog', changeFrequency: 'weekly' as const, priority: 0.8 },
    { path: '/faq', changeFrequency: 'monthly' as const, priority: 0.7 },
    { path: '/privacy', changeFrequency: 'yearly' as const, priority: 0.5 },
    { path: '/terms', changeFrequency: 'yearly' as const, priority: 0.5 },
    { path: '/login', changeFrequency: 'monthly' as const, priority: 0.3 },
    { path: '/register', changeFrequency: 'monthly' as const, priority: 0.3 },
  ];

  const staticEntries = publicPages.map(({ path, changeFrequency, priority }) => ({
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
