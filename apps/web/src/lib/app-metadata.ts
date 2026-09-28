/**
 * App-level metadata factory (UXR Lot 9, A6) — extracted from the `[lng]`
 * layout so the SEO-preservation guard can unit-test it (the layout itself
 * drags next/font, untestable under vitest).
 *
 * Per-locale: the PWA manifest link (`/manifest-{lng}.json` — localized lang,
 * start_url, shortcuts, share_target). The apple touch icon is a real PNG
 * (iOS ignores SVG touch icons — installs were silently degraded). Every
 * other field is byte-preserved from the historical static export.
 */

import type { Metadata } from 'next';

import type { Language } from '@/i18n/settings';
import { getSiteOrigin } from '@/lib/site-origin';

export function buildAppMetadata(lng: Language): Metadata {
  const origin = getSiteOrigin();
  return {
    // No configured origin (generic prebuilt image, B03) → no metadataBase.
    // Omit social images too: Next otherwise resolves their relative paths
    // against localhost:3000 during the build and publishes broken OG URLs.
    ...(origin ? { metadataBase: new URL(origin) } : {}),
    title: 'LIA - Votre assistant personnel',
    description: "Votre assistant personnel intelligent pour la productivité et l'assistance",
    icons: {
      icon: [{ url: '/icon.svg', type: 'image/svg+xml' }],
      apple: [{ url: '/apple-touch-icon.png', sizes: '180x180', type: 'image/png' }],
    },
    manifest: `/manifest-${lng}.json`,
    openGraph: {
      type: 'website',
      siteName: 'LIA',
      images: origin
        ? [
            {
              url: `${origin}/Title.png`,
              width: 2125,
              height: 1193,
              alt: 'LIA — Assistant IA personnel intelligent',
              type: 'image/png',
            },
          ]
        : undefined,
    },
    twitter: {
      card: 'summary_large_image',
      images: origin ? [`${origin}/Title.png`] : undefined,
    },
  };
}
