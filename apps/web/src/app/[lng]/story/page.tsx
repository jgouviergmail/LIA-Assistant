import { type Metadata } from 'next';
import { initI18next, validateLanguage } from '@/i18n';
import { languages, fallbackLng, LOCALE_MAP } from '@/i18n/settings';
import type { Language } from '@/i18n/settings';
import { BreadcrumbJsonLd } from '@/components/seo/JsonLd';
import { LandingHeader } from '@/components/landing/LandingHeader';
import { StoryContent } from '@/components/guides/StoryContent';
import { PublicFooter } from '@/components/layout/PublicFooter';
import { CosmicBackdrop } from '@/components/landing/cosmic/CosmicBackdrop';
import { CosmosDarkFirst } from '@/components/landing/cosmic/CosmosDarkFirst';
import { CosmosThemeDefault } from '@/components/landing/cosmic/CosmosThemeDefault';
import { getSiteOrigin, localizedUrl } from '@/lib/site-origin';


function buildLangUrl(path: string, lng: Language): string {
  return localizedUrl(getSiteOrigin(), path, lng);
}

interface StoryPageProps {
  params: Promise<{ lng: string }>;
}

export async function generateMetadata({ params }: StoryPageProps): Promise<Metadata> {
  const { lng: lngParam } = await params;
  const lng = validateLanguage(lngParam);
  const { t } = await initI18next(lng);

  const title = t('story.meta.title');
  const description = t('story.meta.description');
  const canonicalUrl = buildLangUrl('/story', lng);

  const langAlternates: Record<string, string> = {};
  for (const l of languages) {
    langAlternates[l] = buildLangUrl('/story', l);
  }
  langAlternates['x-default'] = buildLangUrl('/story', fallbackLng);

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

export default async function StoryPage({ params }: StoryPageProps) {
  const { lng: lngParam } = await params;
  const lng = validateLanguage(lngParam);
  const { t } = await initI18next(lng);

  return (
    <>
      <BreadcrumbJsonLd
        items={[
          { name: 'LIA', url: buildLangUrl('/', lng) },
          { name: t('story.breadcrumb'), url: buildLangUrl('/story', lng) },
        ]}
      />

      <div className="landing-page cosmos cosmos-calm min-h-screen">
        <CosmosDarkFirst />
        <CosmicBackdrop />
        <CosmosThemeDefault />
        {/* Header — same as landing page (fixed top, transparent until scroll) */}
        <LandingHeader lng={lng} />

        {/* pt-24 offsets the fixed header height (h-16 = 64 px) */}
        <main className="px-4 sm:px-6 lg:px-8 pt-24 pb-12">
          {/* Hero */}
          <div className="max-w-3xl mx-auto mb-12 text-center">
            <h1 className="text-3xl sm:text-4xl font-bold tracking-tight mb-4">
              {t('story.hero.title')}
            </h1>
            <p className="text-lg text-muted-foreground leading-relaxed">
              {t('story.hero.subtitle')}
            </p>
          </div>

          {/* Content */}
          <StoryContent lng={lng} />
        </main>

        <PublicFooter lng={lng} />
      </div>
    </>
  );
}
