import { type Metadata } from 'next';
import { initI18next, validateLanguage } from '@/i18n';
import { AuthRedirect } from '@/components/landing/AuthRedirect';
import { LandingHeader } from '@/components/landing/LandingHeader';
import { HeroSection } from '@/components/landing/HeroSection';
import { HowItWorksSection } from '@/components/landing/HowItWorksSection';
import { FeaturesSection } from '@/components/landing/FeaturesSection';
import { UseCasesSection } from '@/components/landing/UseCasesSection';
import { StatsSection } from '@/components/landing/StatsSection';
import { SecuritySection } from '@/components/landing/SecuritySection';
import { TechSection } from '@/components/landing/TechSection';
import { ArchitectureDiagram } from '@/components/landing/ArchitectureDiagram';
import { CtaSection } from '@/components/landing/CtaSection';
import { LandingFooter } from '@/components/landing/LandingFooter';

interface HomePageProps {
  params: Promise<{ lng: string }>;
}

export async function generateMetadata({ params }: HomePageProps): Promise<Metadata> {
  const { lng: lngParam } = await params;
  const lng = validateLanguage(lngParam);
  const { t } = await initI18next(lng);

  const title = t('landing.meta.title');
  const description = t('landing.meta.description');

  return {
    title,
    description,
    openGraph: {
      title,
      description,
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
      {/* Redirect authenticated users to dashboard */}
      <AuthRedirect lng={lng} />

      <div className="landing-page">
        {/* Skip to content */}
        <a href="#features" className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-[100] focus:px-4 focus:py-2 focus:bg-primary focus:text-primary-foreground focus:rounded-md">
          {t('landing.nav.features')}
        </a>

        <LandingHeader lng={lng} />

        <main>
          <HeroSection lng={lng} />
          <HowItWorksSection lng={lng} />
          <FeaturesSection lng={lng} />
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
