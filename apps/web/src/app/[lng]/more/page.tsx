import { type Metadata } from 'next';

import { BreadcrumbJsonLd } from '@/components/seo/JsonLd';
import { LandingHeader } from '@/components/landing/LandingHeader';
import { MoreContent } from '@/components/landing/more/MoreContent';
import { PublicFooter } from '@/components/layout/PublicFooter';
import { CosmicBackdrop } from '@/components/landing/cosmic/CosmicBackdrop';
import { CosmosDarkFirst } from '@/components/landing/cosmic/CosmosDarkFirst';
import { CosmosThemeDefault } from '@/components/landing/cosmic/CosmosThemeDefault';
import { initI18next, validateLanguage } from '@/i18n';
import { fallbackLng, languages, LOCALE_MAP } from '@/i18n/settings';
import type { Language } from '@/i18n/settings';

const BASE_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://lia.jeyswork.com';

function buildLangUrl(path: string, lng: Language): string {
  return lng === fallbackLng ? `${BASE_URL}${path}` : `${BASE_URL}/${lng}${path}`;
}

interface MorePageProps {
  params: Promise<{ lng: string }>;
}

export async function generateMetadata({ params }: MorePageProps): Promise<Metadata> {
  const { lng: lngParam } = await params;
  const lng = validateLanguage(lngParam);
  const { t } = await initI18next(lng);

  const title = t('more.meta.title');
  const description = t('more.meta.description');
  const canonicalUrl = buildLangUrl('/more', lng);

  const langAlternates: Record<string, string> = {};
  for (const l of languages) {
    langAlternates[l] = buildLangUrl('/more', l);
  }
  langAlternates['x-default'] = buildLangUrl('/more', fallbackLng);

  return {
    title,
    description,
    alternates: {
      canonical: canonicalUrl,
      languages: langAlternates,
    },
    openGraph: {
      title,
      description,
      url: canonicalUrl,
      locale: LOCALE_MAP[lng],
      alternateLocale: languages.filter(l => l !== lng).map(l => LOCALE_MAP[l]),
      type: 'website',
      images: [{ url: `${BASE_URL}/Title.png`, width: 2125, height: 1193, alt: title }],
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
      images: [`${BASE_URL}/Title.png`],
    },
  };
}

export default async function MorePage({ params }: MorePageProps) {
  const { lng: lngParam } = await params;
  const lng = validateLanguage(lngParam);
  const { t } = await initI18next(lng);

  return (
    <>
      <BreadcrumbJsonLd
        items={[
          { name: 'LIA', url: buildLangUrl('/', lng) },
          { name: t('more.meta.title'), url: buildLangUrl('/more', lng) },
        ]}
      />

      <div className="landing-page cosmos min-h-screen">
        <CosmosDarkFirst />
        <CosmicBackdrop />
        <CosmosThemeDefault />
        {/* Header — same as landing page (fixed top, transparent until scroll) */}
        <LandingHeader lng={lng} />

        {/* pt-24 offsets the fixed header height (h-16 = 64 px) */}
        <main className="pt-24 pb-12">
          <MoreContent lng={lng} />
        </main>

        <PublicFooter lng={lng} />
      </div>
    </>
  );
}
