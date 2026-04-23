import { type Metadata } from 'next';
import { initI18next, validateLanguage } from '@/i18n';
import { languages, fallbackLng, LOCALE_MAP } from '@/i18n/settings';
import type { Language } from '@/i18n/settings';
import { BreadcrumbJsonLd } from '@/components/seo/JsonLd';
import { LandingHeader } from '@/components/landing/LandingHeader';
import { WhyContent } from '@/components/guides/WhyContent';
import { PublicFooter } from '@/components/layout/PublicFooter';

const BASE_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://lia.jeyswork.com';

function buildLangUrl(path: string, lng: Language): string {
  return lng === fallbackLng ? `${BASE_URL}${path}` : `${BASE_URL}/${lng}${path}`;
}

interface WhyPageProps {
  params: Promise<{ lng: string }>;
}

export async function generateMetadata({ params }: WhyPageProps): Promise<Metadata> {
  const { lng: lngParam } = await params;
  const lng = validateLanguage(lngParam);
  const { t } = await initI18next(lng);

  const title = t('why.meta.title');
  const description = t('why.meta.description');
  const canonicalUrl = buildLangUrl('/why', lng);

  const langAlternates: Record<string, string> = {};
  for (const l of languages) {
    langAlternates[l] = buildLangUrl('/why', l);
  }
  langAlternates['x-default'] = buildLangUrl('/why', fallbackLng);

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

export default async function WhyPage({ params }: WhyPageProps) {
  const { lng: lngParam } = await params;
  const lng = validateLanguage(lngParam);
  const { t } = await initI18next(lng);

  return (
    <>
      <BreadcrumbJsonLd
        items={[
          { name: 'LIA', url: buildLangUrl('/', lng) },
          { name: t('why.breadcrumb'), url: buildLangUrl('/why', lng) },
        ]}
      />

      <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
        {/* Header — same as landing page (fixed top, transparent until scroll) */}
        <LandingHeader lng={lng} />

        {/* pt-24 offsets the fixed header height (h-16 = 64 px) */}
        <main className="px-4 sm:px-6 lg:px-8 pt-24 pb-12">
          {/* Hero */}
          <div className="max-w-3xl mx-auto mb-12 text-center">
            <h1 className="text-3xl sm:text-4xl font-bold tracking-tight mb-4">
              {t('why.hero.title')}
            </h1>
            <p className="text-lg text-muted-foreground leading-relaxed">
              {t('why.hero.subtitle')}
            </p>
          </div>

          {/* Content */}
          <WhyContent lng={lng} />
        </main>

        <PublicFooter lng={lng} />
      </div>
    </>
  );
}
