import { type Metadata } from 'next';
import { initI18next, validateLanguage } from '@/i18n';
import { SoftwareApplicationJsonLd } from '@/components/seo/JsonLd';
import { AuthRedirect } from '@/components/landing/AuthRedirect';
import { TrackView } from '@/components/telemetry/TelemetryBootstrap';
import { LandingHeader } from '@/components/landing/LandingHeader';
import { EditorialChapters } from '@/components/landing/editorial/EditorialChapters';
import { PromiseSection } from '@/components/landing/editorial/PromiseSection';
import { PersonalContextSection } from '@/components/landing/editorial/PersonalContextSection';
import { PlatformSection } from '@/components/landing/editorial/PlatformSection';
import { LandingVideoSection } from '@/components/landing/video/LandingVideoSection';
import { BasicsBand } from '@/components/landing/editorial/BasicsBand';
import { TransparencySection } from '@/components/landing/editorial/TransparencySection';
import { GallerySection } from '@/components/landing/editorial/GallerySection';
import { ChapterRail } from '@/components/landing/editorial/ChapterRail';
import { TechSection } from '@/components/landing/TechSection';
import { BlogPreviewSection } from '@/components/landing/BlogPreviewSection';
import { ChangelogSection } from '@/components/landing/ChangelogSection';
import { LandingFooter } from '@/components/landing/LandingFooter';
import { LandingEyes } from '@/components/landing/LandingEyes';
import { AttentionBackdrop } from '@/components/landing/cosmic/AttentionBackdrop';
import { CosmicBackdrop } from '@/components/landing/cosmic/CosmicBackdrop';
import { CosmosDay } from '@/components/landing/cosmic/CosmosDay';
import { CosmosFinale } from '@/components/landing/cosmic/CosmosFinale';
import { CosmosHero } from '@/components/landing/cosmic/CosmosHero';
import { GhostWord } from '@/components/landing/cosmic/GhostWord';
import { ScrollScrub } from '@/components/landing/cosmic/ScrollScrub';
import { publicPageMetadata } from '@/lib/public-page-metadata';

interface HomePageProps {
  params: Promise<{ lng: string }>;
}

export async function generateMetadata({ params }: HomePageProps): Promise<Metadata> {
  const { lng: lngParam } = await params;
  const lng = validateLanguage(lngParam);
  const { t } = await initI18next(lng);

  return publicPageMetadata(
    lng,
    '/',
    t('landing.home_meta.title'),
    t('landing.home_meta.description')
  );
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
        title={t('landing.home_meta.title')}
        description={t('landing.home_meta.description')}
      />

      {/* Redirect authenticated users to dashboard */}
      <AuthRedirect lng={lng} />

      {/* Product funnel (ADR-178 Phase 4, anonymous allowed) — inert unless enabled */}
      <TrackView event="landing_view" />

      <div className="landing-page cosmos cosmos-attention cosmos-home">
        <CosmicBackdrop />
        {/* Animated « attention + latent space » layer, landing only. */}
        <AttentionBackdrop />

        {/* Skip to content */}
        <a
          href="#features"
          className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-[100] focus:px-4 focus:py-2 focus:bg-primary focus:text-primary-foreground focus:rounded-md"
        >
          {t('landing.nav.features')}
        </a>

        <LandingHeader lng={lng} home />
        <ChapterRail />

        {/* Editorial narrative (ADR: the page speaks the product's language),
            worn by the cosmos identity: content reused verbatim, the `.cosmos`
            scope + the cosmos compositions provide the skin. */}
        <main>
          <CosmosHero lng={lng} />
          {/* Operator-hosted video (ADR-330): mounts only when the running
              server names a media directory — nothing of it is in the build. */}
          <LandingVideoSection lng={lng} />
          <GallerySection />
          <PromiseSection lng={lng} />
          <PersonalContextSection lng={lng} />
          <EditorialChapters lng={lng} ghosts />
          <BasicsBand lng={lng} />
          <TransparencySection
            lng={lng}
            ghost={<GhostWord wordKey="landing.cosmos.ghost.transparency" direction={1} />}
          />
          <CosmosDay />
          <PlatformSection lng={lng} />
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
