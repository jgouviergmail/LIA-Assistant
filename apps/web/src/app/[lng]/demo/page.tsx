import { type Metadata } from 'next';
import { initI18next, validateLanguage } from '@/i18n';
import { languages, fallbackLng, LOCALE_MAP } from '@/i18n/settings';
import type { Language } from '@/i18n/settings';
import { InteractiveChatMockup } from '@/components/landing/InteractiveChatMockup';
import { LiveDemoInvitation } from '@/components/showroom/LiveDemoInvitation';
import { GuidedShowroom } from '@/components/showroom/GuidedShowroom';
import { TrackView } from '@/components/telemetry/TelemetryBootstrap';
import { CosmicBackdrop } from '@/components/landing/cosmic/CosmicBackdrop';
import { CosmosDarkFirst } from '@/components/landing/cosmic/CosmosDarkFirst';
import { CosmosThemeDefault } from '@/components/landing/cosmic/CosmosThemeDefault';
import { Planetarium } from '@/components/landing/cosmic/Planetarium';
import { getPublicShowroomVariant } from '@/lib/showroom-config';
import { getSiteOrigin, localizedUrl } from '@/lib/site-origin';

/**
 * Standalone URL for the hero conversation animation, made to be shared on
 * social networks and embedded in publications: no header, no footer, no auth
 * redirect — the four-act mockup at the center of the cosmos planetarium,
 * made INTERACTIVE here (UX P12): scene pastilles, pause/replay, progress and
 * a closing CTA. The auto loop is preserved until the visitor interacts.
 * Localized like every route (the mockup aria text doubles as the page
 * description).
 */


function buildLangUrl(path: string, lng: Language): string {
  return localizedUrl(getSiteOrigin(), path, lng);
}

interface DemoPageProps {
  params: Promise<{ lng: string }>;
}

export async function generateMetadata({ params }: DemoPageProps): Promise<Metadata> {
  const { lng: lngParam } = await params;
  const lng = validateLanguage(lngParam);
  const { t } = await initI18next(lng);

  const title = t('landing.meta.title');
  const description = t('landing.chat_mockup.aria');
  const canonicalUrl = buildLangUrl('/demo', lng);

  const langAlternates: Record<string, string> = {};
  for (const l of languages) {
    langAlternates[l] = buildLangUrl('/demo', l);
  }
  langAlternates['x-default'] = buildLangUrl('/demo', fallbackLng);

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

export default async function DemoPage({ params }: DemoPageProps) {
  const { lng: lngParam } = await params;
  const lng = validateLanguage(lngParam);
  const variant = getPublicShowroomVariant();

  return (
    <div className="landing-page cosmos">
      <CosmosDarkFirst />
      <CosmicBackdrop />
      <CosmosThemeDefault />
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
            {/* The real four-act mockup at the center of the planetarium — LIA's
                feature families in orbit around the live conversation. */}
            <div className="cosmos-orbit-zone w-full">
              <Planetarium />
              {/* min-w-0/max-w-full: an unbreakable mockup line must never widen
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
