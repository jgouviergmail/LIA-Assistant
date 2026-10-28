/**
 * The centered homepage promise, followed by the functional constellation.
 * The map uses the same localized data as the living documentation; the
 * guided-demo link retains its deployment switch.
 */

import Link from 'next/link';
import { initI18next } from '@/i18n';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ChevronDown, PlayCircle, ShieldCheck, Users, MapPin } from 'lucide-react';
import { GithubIcon } from '@/components/icons/GithubIcon';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import { getPublicShowroomVariant } from '@/lib/showroom-config';
import type { Language } from '@/i18n/settings';
import { mapsData } from '@/lib/maps/data';
import { buildBrickMap } from '@/lib/maps/model';
import { APP_VERSION, LAST_UPDATED } from '@/lib/version';
import { LandingConstellation } from './LandingConstellation';
import { PresentationButton } from '../video/PresentationButton';

const HERO_DATE_LOCALES: Record<string, string> = {
  fr: 'fr-FR',
  en: 'en-US',
  de: 'de-DE',
  es: 'es-ES',
  it: 'it-IT',
  zh: 'zh-CN',
};

const GITHUB_REPO_URL = 'https://github.com/jgouviergmail/LIA-Assistant';

/** Orchestrated entrance delays (ms) — badges → title → copy → CTA → stats. */
const RISE_DELAYS = {
  badges: 0,
  title: 120,
  lede: 450,
  sub: 550,
  cta: 650,
  trust: 780,
} as const;

/** Inline entrance delay — pair with the `cosmos-rise` class. */
function rise(delayMs: number): { style: React.CSSProperties } {
  return { style: { animationDelay: `${delayMs}ms` } };
}

interface CosmosHeroProps {
  lng: Language;
}

export async function CosmosHero({ lng }: CosmosHeroProps) {
  const { t } = await initI18next(lng);
  const map = buildBrickMap(mapsData(lng), 'functional');
  // The demo CTA exists ONLY when the guided mission is the /demo experience:
  // under `legacy` that page is a passive mockup, so advertising it as a demo
  // would overpromise. Build-time value — no runtime branch on the public page.
  const showsGuidedDemo = getPublicShowroomVariant() === 'guided';
  const demoHref = buildLocalizedPath('/demo', lng);

  // LAST_UPDATED is an editorial Paris wall-clock stamp, not a UTC instant.
  // Pin the formatter to UTC so SSR and hydration render the same date and hour.
  const formattedDate = new Date(`${LAST_UPDATED}Z`).toLocaleString(
    HERO_DATE_LOCALES[lng] || 'en-US',
    {
      timeZone: 'UTC',
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }
  );

  const trustItems = [
    { icon: MapPin, label: t('landing.hero.proof_origin') },
    { icon: Users, label: t('landing.hero.proof_accounts') },
    { icon: ShieldCheck, label: t('landing.hero.proof_control') },
  ];

  return (
    <section className="relative min-h-screen flex items-center overflow-clip">
      <div className="lm-functional-frame relative z-10 pt-24 lg:pt-28 pb-24">
        <div className="flex min-w-0 flex-col items-center gap-6">
          <div className="w-full min-w-0 max-w-4xl text-center">
            <div
              {...rise(RISE_DELAYS.badges)}
              className="cosmos-rise flex flex-wrap items-center gap-3 justify-center mb-3 sm:mb-6"
            >
              {/* dark:text-red-300: the badge base variant paints an OPAQUE
                  dark:bg-red-900 pill — red-400 on it is 3.48:1 (fails AA),
                  red-300 measures ≈5.3:1. Light: red-800, because the pill is
                  only a 10 % tint over the nebula's glow — red-700 measured
                  4.18:1 there (2026-10-03), red-800 computes to ≈5.2:1. */}
              <Badge
                pulse
                variant="destructive"
                className="bg-red-500/10 text-red-800 dark:text-red-300 border-red-500/30"
              >
                {t('landing.hero.badge_beta')}
              </Badge>
              <a href={GITHUB_REPO_URL} target="_blank" rel="noopener noreferrer">
                <Badge
                  variant="outline"
                  className="gap-1.5 cursor-pointer hover:bg-muted/50 transition-colors"
                >
                  <GithubIcon className="w-3.5 h-3.5" />
                  {t('landing.hero.badge_opensource')}
                </Badge>
              </a>
              <span className="hidden text-xs text-muted-foreground whitespace-nowrap sm:inline">
                v{APP_VERSION} · {t('landing.footer.last_updated', { date: formattedDate })}
              </span>
            </div>

            <h1
              {...rise(RISE_DELAYS.title)}
              className="cosmos-rise cosmos-hero-title text-3xl mobile:text-4xl sm:text-5xl xl:text-6xl font-extrabold tracking-tight leading-[1.08] mb-4 sm:mb-6"
            >
              <span className="block">{t('landing.hero.title_line1')}</span>
              <span className="block">
                {t('landing.hero.title_line2_before')}
                <span className="cosmos-grad-text">{t('landing.hero.title_line2_highlight')}</span>
                {t('landing.hero.title_line2_after')}
              </span>
              <span className="block">{t('landing.hero.title_line3')}</span>
            </h1>

            <p
              {...rise(RISE_DELAYS.lede)}
              className="cosmos-rise text-base mobile:text-lg font-semibold text-foreground/90 max-w-2xl mx-auto leading-relaxed mb-3"
            >
              {t('landing.hero.subtitle_top')}
            </p>
            <p
              {...rise(RISE_DELAYS.sub)}
              className="cosmos-rise text-sm mobile:text-base text-foreground/80 max-w-2xl mx-auto leading-relaxed"
            >
              {t('landing.hero.home_value')}
            </p>
          </div>

          <div className="w-full min-w-0 max-w-3xl text-center">
            <div
              {...rise(RISE_DELAYS.cta)}
              className="cosmos-rise flex flex-col sm:flex-row sm:flex-wrap gap-3 justify-center mb-3"
            >
              <PresentationButton label={t('landing.hero.home_cta_presentation')} />
              {showsGuidedDemo && (
                <Button asChild variant="outline" size="lg" className="text-base px-5 gap-2">
                  <Link href={demoHref} data-testid="hero-cta-demo">
                    <PlayCircle className="w-5 h-5" aria-hidden="true" />
                    {t('landing.hero.home_cta_demo')}
                  </Link>
                </Button>
              )}
            </div>

            <a
              href={GITHUB_REPO_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="mb-3 inline-flex min-h-11 items-center gap-2 rounded-sm text-sm font-medium text-primary underline underline-offset-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <GithubIcon className="size-4" aria-hidden="true" />
              {t('landing.hero.home_code_link')}
            </a>

            <p className="mb-5 text-xs leading-5 text-muted-foreground">
              {t('landing.hero.home_access_note')}
            </p>

            <div
              {...rise(RISE_DELAYS.trust)}
              className="cosmos-rise flex flex-col items-center justify-center gap-3 text-sm text-muted-foreground sm:flex-row sm:flex-wrap sm:gap-x-4 sm:gap-y-2"
            >
              {trustItems.map(({ icon: Icon, label }) => (
                <span
                  key={label}
                  className="flex max-w-full items-center justify-center gap-1.5 text-center leading-relaxed"
                >
                  <Icon className="w-4 h-4 shrink-0 text-primary" aria-hidden="true" />
                  {label}
                </span>
              ))}
            </div>
          </div>

          <LandingConstellation map={map} lng={lng} />
        </div>
      </div>

      <a
        href="#gallery"
        className="absolute bottom-6 left-1/2 -translate-x-1/2 flex min-h-11 flex-col items-center gap-2 rounded-md px-3 text-muted-foreground hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-label={t('landing.hero.scroll_hint')}
      >
        <span className="text-xs">{t('landing.hero.scroll_hint')}</span>
        <ChevronDown className="w-5 h-5 animate-bounce-scroll" />
      </a>
    </section>
  );
}
