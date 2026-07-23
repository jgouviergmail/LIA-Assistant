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

export function buildAppMetadata(lng: Language): Metadata {
  return {
    metadataBase: new URL(process.env.NEXT_PUBLIC_APP_URL || 'https://lia.jeyswork.com'),
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
      images: [
        {
          url: '/Title.png',
          width: 2125,
          height: 1193,
          alt: 'LIA — Assistant IA personnel intelligent',
          type: 'image/png',
        },
      ],
    },
    twitter: {
      card: 'summary_large_image',
      images: ['/Title.png'],
    },
  };
}
