import { type Metadata } from 'next';
import { initI18next, validateLanguage } from '@/i18n';
import { InteractiveChatMockup } from '@/components/landing/InteractiveChatMockup';
import { LiveDemoInvitation } from '@/components/showroom/LiveDemoInvitation';
import { GuidedShowroom } from '@/components/showroom/GuidedShowroom';
import { TrackView } from '@/components/telemetry/TelemetryBootstrap';
import { CosmicBackdrop } from '@/components/landing/cosmic/CosmicBackdrop';
import { CosmosDarkFirst } from '@/components/landing/cosmic/CosmosDarkFirst';
import { CosmosThemeDefault } from '@/components/landing/cosmic/CosmosThemeDefault';
import { MotionToggle } from '@/components/landing/cosmic/MotionToggle';
import { Planetarium } from '@/components/landing/cosmic/Planetarium';
import { LANDING_PLANETARIUM_ENABLED } from '@/components/landing/constants';
import { getPublicShowroomVariant } from '@/lib/showroom-config';
import { publicPageMetadata } from '@/lib/public-page-metadata';

/**
 * Shareable product demonstration: the same six contextual scenes as the
 * landing, with selection, pause/replay and a closing CTA. A selected scene
 * reveals its request, useful context and concrete result, then stays available
 * to read. Engineering explanations remain opt-in; reduced motion shows the
 * complete scene immediately. The configured guided showroom stays independent.
 */
interface DemoPageProps {
  params: Promise<{ lng: string }>;
}

export async function generateMetadata({ params }: DemoPageProps): Promise<Metadata> {
  const { lng: lngParam } = await params;
  const lng = validateLanguage(lngParam);
  const { t } = await initI18next(lng);

  return publicPageMetadata(
    lng,
    '/demo',
    t('landing.product_demo.meta_title'),
    t('landing.product_demo.meta_description')
  );
}

export default async function DemoPage({ params }: DemoPageProps) {
  const { lng: lngParam } = await params;
  const lng = validateLanguage(lngParam);
  const variant = getPublicShowroomVariant();

  return (
    <div className="landing-page cosmos">
      <CosmosDarkFirst />
      <CosmicBackdrop />
      <CosmosThemeDefault />
      {/* The page has no header: the background's pause control (WCAG 2.2.2)
          stands alone in the corner, above the content. */}
      <div className="fixed right-3 top-3 z-50">
        <MotionToggle />
      </div>
      <main className="relative flex min-h-screen items-center justify-center overflow-clip px-4 py-10">
        {variant === 'guided' ? (
          /* Guided missions (public-web-showroom program). No TrackView on
             purpose: they post through the ordinary credentialed route and
             emit their own credential-less showroom funnel. The planetarium
             stays legacy-only — decorative orbits around an interactive HITL
             flow would be noise, not identity.

             Stacked, never side by side: the page's <main> is a centered flex
             row, so two children sit next to each other and the invitation
             ends up competing with the missions instead of introducing them.
             The column also keeps the guided showroom centered on its own
             when the invitation renders nothing. */
          <div className="flex w-full flex-col items-center gap-12 sm:gap-16">
            {/* The live demonstrator, when an operator switched its link on.
                Above the guided missions on purpose: a visitor chooses
                between the two here, and the block states every limitation
                before offering the link. Renders nothing when off. */}
            <LiveDemoInvitation lng={lng} />
            <GuidedShowroom lng={lng} />
          </div>
        ) : (
          <>
            {/* Product funnel (ADR-178 Phase 4, anonymous allowed) — inert unless enabled */}
            <TrackView event="demo_started" />
            {/* The same illustrative product scenes used by the landing and
                its chapters, with visitor-controlled playback. */}
            <div
              className={
                LANDING_PLANETARIUM_ENABLED
                  ? 'cosmos-orbit-zone w-full'
                  : 'grid w-full place-items-center'
              }
            >
              {LANDING_PLANETARIUM_ENABLED && <Planetarium />}
              {/* min-w-0/max-w-full: a long translated line must never widen
                  the centered grid track past a phone viewport. */}
              <div className="relative z-10 w-full min-w-0 max-w-md">
                <InteractiveChatMockup lng={lng} />
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
