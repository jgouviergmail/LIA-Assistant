import Link from 'next/link';
import { initI18next } from '@/i18n';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ChevronDown, Github } from 'lucide-react';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import type { Language } from '@/i18n/settings';
import { HeroBackground } from './HeroBackground';
import { LANDING_STATS } from './constants';
import { APP_VERSION, LAST_UPDATED } from '@/lib/version';

const GITHUB_REPO_URL = 'https://github.com/jgouviergmail/LIA-Assistant';

interface HeroSectionProps {
  lng: string;
}

export async function HeroSection({ lng }: HeroSectionProps) {
  const { t } = await initI18next(lng);
  const registerHref = buildLocalizedPath('/register', lng as Language);
  const localeMap: Record<string, string> = {
    fr: 'fr-FR', en: 'en-US', de: 'de-DE', es: 'es-ES', it: 'it-IT', zh: 'zh-CN',
  };
  const formattedDate = new Date(LAST_UPDATED).toLocaleDateString(
    localeMap[lng] || 'en-US',
    { year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' },
  );

  return (
    <section className="relative min-h-screen flex items-center overflow-hidden">
      {/* Background image — theme & gender aware, click to toggle */}
      <HeroBackground />

      <div className="relative z-10 w-full max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-20 text-center">
        {/* Version + last updated */}
        <p className="text-sm text-muted-foreground mb-4">
          v{APP_VERSION} · {t('landing.footer.last_updated', { date: formattedDate })}
        </p>

        {/* Badges */}
        <div className="flex items-center gap-3 justify-center mb-6">
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
              <Github className="w-3.5 h-3.5" />
              {t('landing.hero.badge_opensource')}
            </Badge>
          </a>
          <Badge variant="secondary">{t('landing.hero.badge')}</Badge>
        </div>

        {/* Tagline */}
        <h1 className="text-5xl mobile:text-6xl lg:text-7xl font-bold tracking-tight leading-[1.1] mb-6">
          <span className="block">{t('landing.hero.title_line1')}</span>
          <span className="block">
            {t('landing.hero.title_line2_before')}
            <span className="text-gradient-brand">{t('landing.hero.title_line2_highlight')}</span>
            {t('landing.hero.title_line2_after')}
          </span>
          <span className="block">{t('landing.hero.title_line3')}</span>
        </h1>

        {/* Subtitle */}
        <p className="text-lg mobile:text-xl font-bold text-foreground/90 dark:text-foreground/95 max-w-3xl mx-auto leading-relaxed mb-4">
          {t('landing.hero.subtitle_top')}
        </p>
        <p className="text-lg mobile:text-xl text-foreground/70 dark:text-foreground/80 max-w-3xl mx-auto leading-relaxed mb-8">
          {t('landing.hero.subtitle_line1')}
          <br />
          {t('landing.hero.subtitle_line2')}
          <br />
          {t('landing.hero.subtitle_line3')}
        </p>

        {/* Intro paragraph — SEO-rich factual description */}
        <p className="text-base text-muted-foreground max-w-3xl mx-auto leading-relaxed mb-8">
          {t('landing.hero.intro_paragraph')}
        </p>

        {/* CTAs */}
        <div className="flex flex-col sm:flex-row gap-3 justify-center mb-8">
          <Button asChild variant="outline" size="lg" className="text-base px-8">
            <a href="#features">{t('landing.hero.cta_secondary')}</a>
          </Button>
          <Button asChild size="lg" className="text-base px-8">
            <Link href={registerHref}>{t('landing.hero.cta_primary')}</Link>
          </Button>
          <Button asChild variant="outline" size="lg" className="text-base px-8 gap-2">
            <a href={GITHUB_REPO_URL} target="_blank" rel="noopener noreferrer">
              <Github className="w-5 h-5" />
              {t('landing.hero.cta_github')}
            </a>
          </Button>
        </div>

        {/* Trust badges */}
        <div className="flex flex-wrap items-center gap-4 justify-center text-sm text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <span className="font-semibold text-foreground">{LANDING_STATS.agents}+</span>{' '}
            {t('landing.hero.trust_agents')}
          </span>
          <span className="w-px h-4 bg-border" />
          <span className="flex items-center gap-1.5">
            <span className="font-semibold text-foreground">{LANDING_STATS.providers}</span>{' '}
            {t('landing.hero.trust_providers')}
          </span>
          <span className="w-px h-4 bg-border" />
          <span className="flex items-center gap-1.5">
            <span className="font-semibold text-foreground">{LANDING_STATS.voiceLanguages}+</span>{' '}
            {t('landing.hero.trust_voices')}
          </span>
          <span className="w-px h-4 bg-border hidden sm:block" />
          <span className="hidden sm:flex items-center gap-1.5">
            {t('landing.hero.trust_gdpr')}
          </span>
        </div>
      </div>

      {/* Scroll chevron */}
      <a
        href="#how-it-works"
        className="absolute bottom-8 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 text-muted-foreground hover:text-foreground transition-colors"
        aria-label={t('landing.hero.scroll_hint')}
      >
        <span className="text-xs">{t('landing.hero.scroll_hint')}</span>
        <ChevronDown className="w-5 h-5 animate-bounce-scroll" />
      </a>
    </section>
  );
}
