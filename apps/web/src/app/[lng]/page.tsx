import { type Metadata } from 'next';
import { initI18next, validateLanguage } from '@/i18n';
import { languages, fallbackLng, LOCALE_MAP } from '@/i18n/settings';
import type { Language } from '@/i18n/settings';
import { SoftwareApplicationJsonLd, HowToJsonLd } from '@/components/seo/JsonLd';
import { AuthRedirect } from '@/components/landing/AuthRedirect';
import { TrackView } from '@/components/telemetry/TelemetryBootstrap';
import { LandingHeader } from '@/components/landing/LandingHeader';
import { EditorialChapters } from '@/components/landing/editorial/EditorialChapters';
import { PromiseSection } from '@/components/landing/editorial/PromiseSection';
import { LandingVideoSection } from '@/components/landing/video/LandingVideoSection';
import { BasicsBand } from '@/components/landing/editorial/BasicsBand';
import { TransparencySection } from '@/components/landing/editorial/TransparencySection';
import { GallerySection } from '@/components/landing/editorial/GallerySection';
import { ChapterRail } from '@/components/landing/editorial/ChapterRail';
import { UseCasesSection } from '@/components/landing/UseCasesSection';
import { TechSection } from '@/components/landing/TechSection';
import { BlogPreviewSection } from '@/components/landing/BlogPreviewSection';
import { ChangelogSection } from '@/components/landing/ChangelogSection';
import { LandingFooter } from '@/components/landing/LandingFooter';
import { LandingEyes } from '@/components/landing/LandingEyes';
import { AttentionBackdrop } from '@/components/landing/cosmic/AttentionBackdrop';
import { CosmicBackdrop } from '@/components/landing/cosmic/CosmicBackdrop';
import { CosmosDarkFirst } from '@/components/landing/cosmic/CosmosDarkFirst';
import { CosmosDay } from '@/components/landing/cosmic/CosmosDay';
import { CosmosFinale } from '@/components/landing/cosmic/CosmosFinale';
import { CosmosHero } from '@/components/landing/cosmic/CosmosHero';
import { CosmosThemeDefault } from '@/components/landing/cosmic/CosmosThemeDefault';
import { GhostWord } from '@/components/landing/cosmic/GhostWord';
import { ScrollScrub } from '@/components/landing/cosmic/ScrollScrub';
import { getSiteOrigin, localizedUrl } from '@/lib/site-origin';

interface HomePageProps {
  params: Promise<{ lng: string }>;
}

function buildLangUrl(path: string, lng: Language): string {
  return localizedUrl(getSiteOrigin(), path, lng);
}

export async function generateMetadata({ params }: HomePageProps): Promise<Metadata> {
  const { lng: lngParam } = await params;
  const lng = validateLanguage(lngParam);
  const { t } = await initI18next(lng);

  const title = t('landing.meta.title');
  const description = t('landing.meta.description');
  const canonicalUrl = buildLangUrl('/', lng);
  const socialImage = getSiteOrigin()?.concat('/Title.png');

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
      images: socialImage
        ? [{ url: socialImage, width: 2125, height: 1193, alt: title }]
        : undefined,
    },
    twitter: {
      title,
      description,
      images: socialImage ? [socialImage] : undefined,
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

      {/* Product funnel (ADR-178 Phase 4, anonymous allowed) — inert unless enabled */}
      <TrackView event="landing_view" />

      <div className="landing-page cosmos cosmos-attention cosmos-home">
        <CosmosDarkFirst />
        <CosmicBackdrop />
        {/* Animated « attention + latent space » layer, landing only. */}
        <AttentionBackdrop />
        <CosmosThemeDefault />

        {/* Skip to content */}
        <a
          href="#features"
          className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-[100] focus:px-4 focus:py-2 focus:bg-primary focus:text-primary-foreground focus:rounded-md"
        >
          {t('landing.nav.features')}
        </a>

        <LandingHeader lng={lng} />
        <ChapterRail />

        {/* Editorial narrative (ADR: the page speaks the product's language),
            worn by the cosmos identity: content reused verbatim, the `.cosmos`
            scope + the cosmos compositions provide the skin. */}
        <main>
          <CosmosHero lng={lng} />
          {/* Operator-hosted video (ADR-330): mounts only when the running
              server names a media directory — nothing of it is in the build. */}
          <LandingVideoSection lng={lng} />
          <PromiseSection lng={lng} />
          <UseCasesSection lng={lng} />
          <EditorialChapters lng={lng} ghosts />
          <BasicsBand lng={lng} />
          <TransparencySection
            lng={lng}
            ghost={<GhostWord wordKey="landing.cosmos.ghost.transparency" direction={1} />}
          />
          <CosmosDay />
          <GallerySection />
          <TechSection lng={lng} />
          <ChangelogSection lng={lng} />
          <BlogPreviewSection lng={lng} />
          <CosmosFinale lng={lng} />
        </main>

        {/* Scroll-scrub drivers: each writes its section's --sp so the cosmos
            skin can choreograph the tiles in sync with the scroll (one distinct
            pattern per section — rise, 3D flip, lift, pop, execution trace). */}
        <ScrollScrub targetId="transparency" />
        <ScrollScrub targetId="gallery" />
        <ScrollScrub targetId="changelog" />

        <LandingFooter lng={lng} />

        {/* LIA's eyes: fixed to the viewport, draggable, on their own
            position slot (ADR-240, landing surface). */}
        <LandingEyes />
      </div>
    </>
  );
}
