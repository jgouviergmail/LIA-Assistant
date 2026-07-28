/**
 * Body of the /more public page: hero (title, derived counter, WCAG 2.2.2
 * pause toggle), six numbered moment sections of animated attention cards,
 * the "craft in numbers" band (LANDING_STATS — maintained numbers only) and
 * the shared landing CTA.
 *
 * Client component on the PublicFAQContent pattern (useTranslation); the
 * server page.tsx owns metadata, JsonLd, header and footer.
 */

'use client';

import Link from 'next/link';
import { useTranslation } from 'react-i18next';

import { LANDING_STATS } from '@/components/landing/constants';
import { AnimatedCounter } from '@/components/landing/AnimatedCounter';
import { FadeInOnScroll } from '@/components/landing/FadeInOnScroll';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';

import { AnimationPauseToggle, MoreAnimationProvider } from './animation-context';
import { CARD_ICONS, MORE_CARD_KEYS, MORE_SECTIONS } from './more-data';
import { MoreCard } from './MoreCard';
import { SCENE_REGISTRY } from './scene-registry';

const CRAFT_TILES = [
  { key: 'tests', target: LANDING_STATS.tests, suffix: '+' },
  { key: 'languages', target: LANDING_STATS.uiLanguages, suffix: '' },
  { key: 'releases', target: LANDING_STATS.releases, suffix: '' },
] as const;

export function MoreContent({ lng }: { lng: string }) {
  const { t } = useTranslation();
  const total = MORE_CARD_KEYS.length;
  const registerHref = buildLocalizedPath('/register', lng as Language);

  return (
    <MoreAnimationProvider>
      {/* Hero */}
      <div className="mx-auto max-w-3xl px-4 text-center sm:px-6">
        <h1 className="text-3xl font-bold tracking-tight mobile:text-4xl">
          {t('more.hero.title')}
        </h1>
        <p className="mt-3 text-lg leading-relaxed text-muted-foreground">
          {t('more.hero.subtitle')}
        </p>
        <p data-testid="more-hero-figure" className="mt-6 text-5xl font-bold text-primary">
          <AnimatedCounter target={total} />
        </p>
        <p className="mt-2 text-sm text-muted-foreground">{t('more.hero.counter', { total })}</p>
        <div className="mt-5">
          <AnimationPauseToggle />
        </div>
      </div>

      {/* Moment sections */}
      {MORE_SECTIONS.map(section => (
        <section
          key={section.id}
          id={`more-${section.id}`}
          aria-labelledby={`more-${section.id}-title`}
          className={cn(
            'landing-section mt-12 py-12',
            section.tinted && 'border-y border-border/60 bg-card'
          )}
        >
          <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
            <FadeInOnScroll className="min-w-0">
              <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-primary">
                {section.num}
              </p>
              <h2
                id={`more-${section.id}-title`}
                className="mt-1.5 text-2xl font-bold tracking-tight mobile:text-3xl"
              >
                {t(`more.sections.${section.key}.title`)}
              </h2>
              <p className="mt-2 max-w-[60ch] text-muted-foreground">
                {t(`more.sections.${section.key}.intro`)}
              </p>
            </FadeInOnScroll>
            {/* role="list" restores list semantics that Safari/VoiceOver strip
                from list-style:none ULs — the page preaches a11y care. */}
            <ul
              role="list"
              className="mt-8 grid list-none grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3"
            >
              {section.cards.map((cardKey, i) => (
                <MoreCard
                  key={cardKey}
                  cardKey={cardKey}
                  icon={CARD_ICONS[cardKey]}
                  scene={SCENE_REGISTRY[cardKey]}
                  t={t}
                  delay={i * 60}
                />
              ))}
            </ul>
          </div>
        </section>
      ))}

      {/* Craft band */}
      <section
        id="more-craft"
        aria-labelledby="more-craft-title"
        className="landing-section mt-12 py-12"
      >
        <div className="mx-auto max-w-4xl px-4 text-center sm:px-6">
          <h2 id="more-craft-title" className="text-2xl font-bold tracking-tight mobile:text-3xl">
            {t('more.craft.title')}
          </h2>
          <p className="mx-auto mt-2 max-w-[60ch] text-muted-foreground">{t('more.craft.intro')}</p>
          <div className="mt-8 grid grid-cols-1 gap-6 sm:grid-cols-3">
            {CRAFT_TILES.map(({ key, target, suffix }) => (
              <div key={key} className="rounded-xl border border-border bg-background p-6">
                <p className="text-3xl font-bold text-primary">
                  <AnimatedCounter target={target} suffix={suffix} />
                </p>
                <p className="mt-1 text-sm text-muted-foreground">{t(`more.craft.${key}`)}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA — same block as the FAQ page */}
      <div className="mx-auto max-w-4xl px-4 sm:px-6">
        <div className="mt-8 rounded-2xl border border-primary/20 bg-primary/5 p-8 text-center">
          <h2 className="mb-3 text-2xl font-semibold">{t('landing.cta.title')}</h2>
          <p className="mb-6 text-muted-foreground">{t('landing.cta.subtitle')}</p>
          <Link
            href={registerHref}
            className="inline-flex items-center rounded-lg bg-primary px-6 py-3 font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            {t('landing.cta.button')}
          </Link>
        </div>
      </div>
    </MoreAnimationProvider>
  );
}
