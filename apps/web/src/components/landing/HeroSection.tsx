import Link from 'next/link';
import { initI18next } from '@/i18n';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ChevronDown, ShieldCheck } from 'lucide-react';
import { GithubIcon } from '@/components/icons/GithubIcon';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import type { Language } from '@/i18n/settings';
import { ChatMockup } from './ChatMockup';
import { LANDING_STATS } from './constants';
import { APP_VERSION, LAST_UPDATED } from '@/lib/version';

const HERO_DATE_LOCALES: Record<string, string> = {
  fr: 'fr-FR',
  en: 'en-US',
  de: 'de-DE',
  es: 'es-ES',
  it: 'it-IT',
  zh: 'zh-CN',
};

const GITHUB_REPO_URL = 'https://github.com/jgouviergmail/LIA-Assistant';

interface HeroSectionProps {
  lng: string;
}

export async function HeroSection({ lng }: HeroSectionProps) {
  const { t } = await initI18next(lng);
  const registerHref = buildLocalizedPath('/register', lng as Language);

  // Freshness signal: the project ships continuously — show it.
  const formattedDate = new Date(LAST_UPDATED).toLocaleDateString(
    HERO_DATE_LOCALES[lng] || 'en-US',
    { year: 'numeric', month: 'long', day: 'numeric' }
  );

  const trustItems = [
    { value: `${LANDING_STATS.agents}+`, label: t('landing.hero.trust_agents') },
    { value: `${LANDING_STATS.providers}`, label: t('landing.hero.trust_providers') },
    { value: `${LANDING_STATS.voiceLanguages}+`, label: t('landing.hero.trust_voices') },
  ];

  return (
    <section className="relative min-h-screen flex items-center overflow-hidden">
      {/* Ambient background — soft brand glows + radial fade, dark-mode aware */}
      <div className="absolute inset-0 -z-10" aria-hidden="true">
        <div className="absolute -top-32 -left-32 w-[36rem] h-[36rem] rounded-full bg-primary/15 blur-3xl" />
        <div className="absolute top-1/3 -right-40 w-[32rem] h-[32rem] rounded-full bg-violet-500/10 blur-3xl" />
        <div className="absolute bottom-0 left-1/4 w-[28rem] h-[20rem] rounded-full bg-cyan-500/10 blur-3xl" />
        <div className="absolute inset-x-0 bottom-0 h-32 bg-gradient-to-t from-background to-transparent" />
      </div>

      <div className="relative z-10 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-28 pb-20">
        <div className="grid lg:grid-cols-[1.05fr_0.95fr] gap-12 lg:gap-16 items-center">
          {/* Copy column */}
          <div className="text-center lg:text-left">
            {/* Badges */}
            <div className="flex items-center gap-3 justify-center lg:justify-start mb-6">
              <Badge
                pulse
                variant="destructive"
                className="bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/30"
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

            {/* Tagline */}
            <h1 className="text-5xl mobile:text-6xl lg:text-7xl font-bold tracking-tight leading-[1.08] mb-6">
              <span className="block">{t('landing.hero.title_line1')}</span>
              <span className="block">
                {t('landing.hero.title_line2_before')}
                <span className="text-gradient-brand">
                  {t('landing.hero.title_line2_highlight')}
                </span>
                {t('landing.hero.title_line2_after')}
              </span>
              <span className="block">{t('landing.hero.title_line3')}</span>
            </h1>

            {/* Subtitle — whitespace-pre-line renders the sentence break (\n)
                in subtitle_top; sizes tuned so each sentence holds one line
                on desktop */}
            <p className="text-base mobile:text-lg font-semibold text-foreground/90 max-w-2xl mx-auto lg:mx-0 leading-relaxed mb-3 whitespace-pre-line">
              {t('landing.hero.subtitle_top')}
            </p>
            <p className="text-sm mobile:text-base text-foreground/70 max-w-2xl mx-auto lg:mx-0 leading-relaxed mb-8">
              {t('landing.hero.subtitle_line1')}
              <br />
              {t('landing.hero.subtitle_line2')}
              <br />
              {t('landing.hero.subtitle_line3')}
            </p>

            {/* CTAs */}
            <div className="flex flex-col sm:flex-row gap-3 justify-center lg:justify-start mb-8">
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

            {/* Trust badges */}
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 justify-center lg:justify-start text-sm text-muted-foreground">
              {trustItems.map(({ value, label }) => (
                <span key={label} className="flex items-center gap-1.5">
                  <span className="font-semibold text-foreground">{value}</span> {label}
                </span>
              ))}
              <span className="flex items-center gap-1.5">
                <ShieldCheck className="w-4 h-4 text-primary" aria-hidden="true" />
                {t('landing.hero.trust_gdpr')}
              </span>
            </div>
          </div>

          {/* Live conversation column */}
          <div className="w-full">
            <ChatMockup />
          </div>
        </div>
      </div>

      {/* Scroll chevron */}
      <a
        href="#proof"
        className="absolute bottom-6 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 text-muted-foreground hover:text-foreground transition-colors"
        aria-label={t('landing.hero.scroll_hint')}
      >
        <span className="text-xs">{t('landing.hero.scroll_hint')}</span>
        <ChevronDown className="w-5 h-5 animate-bounce-scroll" />
      </a>
    </section>
  );
}
