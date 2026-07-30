/**
 * The landing hero — SAME content contract as the retired `HeroSection` (same
 * i18n keys, badges, stats, links, interactive chat mockup) reskinned with
 * the validated identity: orchestrated entrance, signature gradient on the
 * title highlight, and the feature planetarium orbiting the chat mockup.
 */

import Link from 'next/link';
import { initI18next } from '@/i18n';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ChevronDown, ShieldCheck } from 'lucide-react';
import { GithubIcon } from '@/components/icons/GithubIcon';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import type { Language } from '@/i18n/settings';
import { InteractiveChatMockup } from '../InteractiveChatMockup';
import { LANDING_STATS } from '../constants';
import { APP_VERSION, LAST_UPDATED } from '@/lib/version';
import { Planetarium } from './Planetarium';
import { TrustStat } from './TrustStat';

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
  mockup: 400,
} as const;

/** Inline entrance delay — pair with the `cosmos-rise` class. */
function rise(delayMs: number): { style: React.CSSProperties } {
  return { style: { animationDelay: `${delayMs}ms` } };
}

export async function CosmosHero({ lng }: { lng: string }) {
  const { t } = await initI18next(lng);
  const registerHref = buildLocalizedPath('/register', lng as Language);

  const formattedDate = new Date(LAST_UPDATED).toLocaleDateString(
    HERO_DATE_LOCALES[lng] || 'en-US',
    { year: 'numeric', month: 'long', day: 'numeric' }
  );

  const trustItems = [
    { value: LANDING_STATS.agents, suffix: '+', label: t('landing.hero.trust_agents') },
    { value: LANDING_STATS.providers, suffix: '', label: t('landing.hero.trust_providers') },
    { value: LANDING_STATS.voiceLanguages, suffix: '+', label: t('landing.hero.trust_voices') },
  ];

  return (
    <section className="relative min-h-screen flex items-center overflow-clip">
      <div className="relative z-10 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-28 pb-20">
        <div className="grid lg:grid-cols-[1.05fr_0.95fr] gap-12 lg:gap-16 items-center">
          {/* Copy column — min-w-0 so no child's intrinsic width can widen the
              grid track past the viewport on mobile */}
          <div className="min-w-0 text-center lg:text-left">
            <div
              {...rise(RISE_DELAYS.badges)}
              className="cosmos-rise flex flex-wrap items-center gap-3 justify-center lg:justify-start mb-6"
            >
              {/* dark:text-red-300: the badge base variant paints an OPAQUE
                  dark:bg-red-900 pill — red-400 on it is 3.48:1 (fails AA),
                  red-300 measures ≈5.3:1. */}
              <Badge
                pulse
                variant="destructive"
                className="bg-red-500/10 text-red-600 dark:text-red-300 border-red-500/30"
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
              <span className="text-xs text-muted-foreground whitespace-nowrap">
                v{APP_VERSION} · {t('landing.footer.last_updated', { date: formattedDate })}
              </span>
            </div>

            <h1
              {...rise(RISE_DELAYS.title)}
              className="cosmos-rise text-4xl sm:text-5xl mobile:text-6xl lg:text-7xl font-extrabold tracking-tight leading-[1.08] mb-6"
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
              className="cosmos-rise text-base mobile:text-lg font-semibold text-foreground/90 max-w-2xl mx-auto lg:mx-0 leading-relaxed mb-3 whitespace-normal mobile:whitespace-pre-line"
            >
              {t('landing.hero.subtitle_top')}
            </p>
            <p
              {...rise(RISE_DELAYS.sub)}
              className="cosmos-rise text-sm mobile:text-base text-foreground/80 max-w-2xl mx-auto lg:mx-0 leading-relaxed mb-8"
            >
              {t('landing.hero.subtitle_line1')} <br className="hidden mobile:inline" />
              {t('landing.hero.subtitle_line2')} <br className="hidden mobile:inline" />
              {t('landing.hero.subtitle_line3')}
            </p>

            <div
              {...rise(RISE_DELAYS.cta)}
              className="cosmos-rise flex flex-col sm:flex-row gap-3 justify-center lg:justify-start mb-8"
            >
              <Button asChild size="lg" className="text-base px-8">
                <Link href={registerHref}>{t('landing.hero.cta_primary')}</Link>
              </Button>
              <Button asChild variant="outline" size="lg" className="text-base px-8 gap-2">
                <a href={GITHUB_REPO_URL} target="_blank" rel="noopener noreferrer">
                  <GithubIcon className="w-5 h-5" />
                  {t('landing.hero.cta_github')}
                </a>
              </Button>
            </div>

            <div
              {...rise(RISE_DELAYS.trust)}
              className="cosmos-rise flex flex-wrap items-center gap-x-4 gap-y-2 justify-center lg:justify-start text-sm text-muted-foreground"
            >
              {trustItems.map(({ value, suffix, label }) => (
                <TrustStat key={label} value={value} suffix={suffix} label={label} locale={lng} />
              ))}
              <span className="flex items-center gap-1.5">
                <ShieldCheck className="w-4 h-4 text-primary" aria-hidden="true" />
                {t('landing.hero.trust_gdpr')}
              </span>
            </div>
          </div>

          {/* The planetarium: LIA's chat at the center, her features in orbit.
              min-w-0 on the orbit-zone grid item: without it a single
              unbreakable line inside a mockup act sets the implicit track's
              min-content and silently widens the hero past a phone viewport
              (the historical hero-overflow mechanism, one level up). */}
          <div {...rise(RISE_DELAYS.mockup)} className="cosmos-rise w-full min-w-0">
            <div className="cosmos-orbit-zone">
              <Planetarium />
              <div className="relative z-10 w-full min-w-0">
                <InteractiveChatMockup lng={lng} withCta={false} />
              </div>
            </div>
          </div>
        </div>
      </div>

      <a
        href="#features"
        className="absolute bottom-6 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 text-muted-foreground hover:text-foreground transition-colors"
        aria-label={t('landing.hero.scroll_hint')}
      >
        <span className="text-xs">{t('landing.hero.scroll_hint')}</span>
        <ChevronDown className="w-5 h-5 animate-bounce-scroll" />
      </a>
    </section>
  );
}
