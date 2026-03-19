import type { MetadataRoute } from 'next';
import { languages, fallbackLng } from '@/i18n/settings';
import type { Language } from '@/i18n/settings';

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
 * Only public pages are included:
 * - Landing page (/)
 * - Auth pages (/login, /register)
 * - Public FAQ (/faq)
 *
 * Each page has alternates for all 6 supported languages.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  const publicPages = [
    { path: '/', changeFrequency: 'weekly' as const, priority: 1.0 },
    { path: '/faq', changeFrequency: 'monthly' as const, priority: 0.7 },
    { path: '/login', changeFrequency: 'monthly' as const, priority: 0.3 },
    { path: '/register', changeFrequency: 'monthly' as const, priority: 0.3 },
  ];

  return publicPages.map(({ path, changeFrequency, priority }) => ({
    url: buildUrl(path, fallbackLng),
    lastModified: new Date(),
    changeFrequency,
    priority,
    alternates: {
      languages: buildAlternates(path),
    },
  }));
}
