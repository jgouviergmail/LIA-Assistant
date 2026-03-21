import { type Metadata } from 'next';
import { initI18next, validateLanguage } from '@/i18n';
import { languages, fallbackLng, LOCALE_MAP } from '@/i18n/settings';
import type { Language } from '@/i18n/settings';
import { SoftwareApplicationJsonLd, HowToJsonLd } from '@/components/seo/JsonLd';
import { AuthRedirect } from '@/components/landing/AuthRedirect';
import { LandingHeader } from '@/components/landing/LandingHeader';
import { HeroSection } from '@/components/landing/HeroSection';
import { HowItWorksSection } from '@/components/landing/HowItWorksSection';
import { FeaturesSection } from '@/components/landing/FeaturesSection';
import { ScreenshotsSection } from '@/components/landing/ScreenshotsSection';
import { ArchitectureDiagram } from '@/components/landing/ArchitectureDiagram';
import { PresentationSection } from '@/components/landing/PresentationSection';
import { UseCasesSection } from '@/components/landing/UseCasesSection';
import { StatsSection } from '@/components/landing/StatsSection';
import { SecuritySection } from '@/components/landing/SecuritySection';
import { TechSection } from '@/components/landing/TechSection';
import { BlogPreviewSection } from '@/components/landing/BlogPreviewSection';
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

      {/* SEO: HowTo structured data for "How it works" section */}
      <HowToJsonLd
        name={t('landing.how_it_works.title')}
        description={t('landing.how_it_works.subtitle')}
        steps={[
          {
            name: t('landing.how_it_works.step1.title'),
            text: t('landing.how_it_works.step1.description'),
          },
          {
            name: t('landing.how_it_works.step2.title'),
            text: t('landing.how_it_works.step2.description'),
          },
          {
            name: t('landing.how_it_works.step3.title'),
            text: t('landing.how_it_works.step3.description'),
          },
          {
            name: t('landing.how_it_works.step4.title'),
            text: t('landing.how_it_works.step4.description'),
          },
        ]}
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
          <ScreenshotsSection />
          <FeaturesSection lng={lng} />
          <ArchitectureDiagram />
          <PresentationSection />
          <UseCasesSection lng={lng} />
          <StatsSection />
          <SecuritySection lng={lng} />
          <TechSection lng={lng} />
          <BlogPreviewSection lng={lng} />
          <CtaSection lng={lng} />
        </main>

        <LandingFooter lng={lng} />
      </div>
    </>
  );
}
