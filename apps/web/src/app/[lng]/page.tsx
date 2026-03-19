import { type Metadata } from 'next';
import { initI18next, validateLanguage } from '@/i18n';
import { languages, fallbackLng, LOCALE_MAP } from '@/i18n/settings';
import type { Language } from '@/i18n/settings';
import { SoftwareApplicationJsonLd } from '@/components/seo/JsonLd';
import { AuthRedirect } from '@/components/landing/AuthRedirect';
import { LandingHeader } from '@/components/landing/LandingHeader';
import { HeroSection } from '@/components/landing/HeroSection';
import { HowItWorksSection } from '@/components/landing/HowItWorksSection';
import { FeaturesSection } from '@/components/landing/FeaturesSection';
import { ScreenshotsSection } from '@/components/landing/ScreenshotsSection';
import { ArchitectureDiagram } from '@/components/landing/ArchitectureDiagram';
import { UseCasesSection } from '@/components/landing/UseCasesSection';
import { StatsSection } from '@/components/landing/StatsSection';
import { SecuritySection } from '@/components/landing/SecuritySection';
import { TechSection } from '@/components/landing/TechSection';
import { CtaSection } from '@/components/landing/CtaSection';
import { LandingFooter } from '@/components/landing/LandingFooter';

interface HomePageProps {
  params: Promise<{ lng: string }>;
}

const BASE_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://lia.jeyswork.com';

function buildLangUrl(path: string, lng: Language): string {
  return lng === fallbackLng ? `${BASE_URL}${path}` : `${BASE_URL}/${lng}${path}`;
}

export async function generateMetadata({ params }: HomePageProps): Promise<Metadata> {
  const { lng: lngParam } = await params;
  const lng = validateLanguage(lngParam);
  const { t } = await initI18next(lng);

  const title = t('landing.meta.title');
  const description = t('landing.meta.description');
  const canonicalUrl = buildLangUrl('/', lng);

  // Build hreflang alternates for all supported languages
  const langAlternates: Record<string, string> = {};
  for (const l of languages) {
    langAlternates[l] = buildLangUrl('/', l);
  }
  langAlternates['x-default'] = buildLangUrl('/', fallbackLng);

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
      images: [{ url: '/Title.png', width: 2125, height: 1193, alt: title }],
    },
    twitter: {
      title,
      description,
      images: ['/Title.png'],
    },
  };
}

export default async function HomePage({ params }: HomePageProps) {
  const { lng: lngParam } = await params;
  const lng = validateLanguage(lngParam);
  const { t } = await initI18next(lng);

  return (
    <>
      {/* SEO: SoftwareApplication structured data */}
      <SoftwareApplicationJsonLd
        lng={lng}
        title={t('landing.meta.title')}
        description={t('landing.meta.description')}
      />

      {/* Redirect authenticated users to dashboard */}
      <AuthRedirect lng={lng} />

      <div className="landing-page">
        {/* Skip to content */}
        <a
          href="#features"
          className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-[100] focus:px-4 focus:py-2 focus:bg-primary focus:text-primary-foreground focus:rounded-md"
        >
          {t('landing.nav.features')}
        </a>

        <LandingHeader lng={lng} />

        <main>
          <HeroSection lng={lng} />
          <HowItWorksSection lng={lng} />
          <FeaturesSection lng={lng} />
          <ScreenshotsSection />
          <ArchitectureDiagram />
          <UseCasesSection lng={lng} />
          <StatsSection />
          <SecuritySection lng={lng} />
          <TechSection lng={lng} />
          <CtaSection lng={lng} />
        </main>

        <LandingFooter lng={lng} />
      </div>
    </>
  );
}
