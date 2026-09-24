/**
 * Metadata of the `/maps` pages: canonical URL, one alternate per language
 * (plus `x-default`), Open Graph and Twitter — the shape every public reading
 * page of the site declares, written once for the section's four pages.
 */

import type { Metadata } from 'next';

import { fallbackLng, languages, LOCALE_MAP, type Language } from '@/i18n/settings';
import { getSiteOrigin, localizedUrl } from '@/lib/site-origin';

/** An absolute URL of a page of the site in one language. */
export function siteUrl(path: string, lng: Language): string {
  return localizedUrl(getSiteOrigin(), path, lng);
}

export function mapsMetadata(
  lng: Language,
  path: string,
  title: string,
  description: string
): Metadata {
  const canonical = siteUrl(path, lng);
  const alternates: Record<string, string> = {};
  for (const l of languages) alternates[l] = siteUrl(path, l);
  alternates['x-default'] = siteUrl(path, fallbackLng);
  return {
    title,
    description,
    alternates: { canonical, languages: alternates },
    openGraph: {
      title,
      description,
      url: canonical,
      locale: LOCALE_MAP[lng],
      alternateLocale: languages.filter(l => l !== lng).map(l => LOCALE_MAP[l]),
      type: 'website',
      images: [{ url: '/Title.png', width: 2125, height: 1193, alt: title }],
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
      images: ['/Title.png'],
    },
  };
}
