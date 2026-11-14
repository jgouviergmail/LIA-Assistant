/**
 * Metadata of an indexable public page: canonical URL, one alternate per
 * language (plus `x-default`), Open Graph and Twitter.
 *
 * One shape for the pages `lib/public-pages.ts` declares, so a page cannot
 * announce a canonical without its alternates, or a share card without its
 * image. Search engines read the alternates as a set: every language version
 * names itself and all the others, with absolute URLs, and `x-default` names
 * the version served when no language matches.
 */

import type { Metadata } from 'next';

import { fallbackLng, languages, LOCALE_MAP, type Language } from '@/i18n/settings';
import { getSiteOrigin, localizedUrl } from '@/lib/site-origin';

/** Pixel size of the shared social image (`public/Title.png`). */
const SOCIAL_IMAGE = { path: '/Title.png', width: 2125, height: 1193 } as const;

/** The URL of a page of the site in one language; relative when no origin is configured. */
export function siteUrl(path: string, lng: Language): string {
  return localizedUrl(getSiteOrigin(), path, lng);
}

/** Every language version of a path, keyed by language, plus `x-default`. */
export function languageAlternates(path: string): Record<string, string> {
  const alternates: Record<string, string> = {};
  for (const lng of languages) alternates[lng] = siteUrl(path, lng);
  alternates['x-default'] = siteUrl(path, fallbackLng);
  return alternates;
}

/**
 * Build the metadata of one public page.
 *
 * Args:
 *   lng: The language the page is rendered in.
 *   path: The unlocalized path of the page (`/faq`), `/` for the home.
 *   title: The translated document title.
 *   description: The translated description.
 *
 * Returns:
 *   The metadata Next renders into the document head. Social images are
 *   omitted when no origin is configured: a relative one would be resolved
 *   against the build host and published broken.
 */
export function publicPageMetadata(
  lng: Language,
  path: string,
  title: string,
  description: string
): Metadata {
  const canonical = siteUrl(path, lng);
  const socialImage = getSiteOrigin()?.concat(SOCIAL_IMAGE.path);
  return {
    title,
    description,
    alternates: { canonical, languages: languageAlternates(path) },
    openGraph: {
      title,
      description,
      url: canonical,
      siteName: 'LIA',
      locale: LOCALE_MAP[lng],
      alternateLocale: languages.filter(l => l !== lng).map(l => LOCALE_MAP[l]),
      type: 'website',
      images: socialImage
        ? [{ url: socialImage, width: SOCIAL_IMAGE.width, height: SOCIAL_IMAGE.height, alt: title }]
        : undefined,
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
      images: socialImage ? [socialImage] : undefined,
    },
  };
}
