'use client';

import { useTranslation } from 'react-i18next';
import { FadeInOnScroll } from '../FadeInOnScroll';
import { Tabs } from './Tabs';

/**
 * "A day with LIA." — replaces the four persona cards with four complete
 * hour-by-hour days, one per profile (tabs). Richer than the cards it
 * replaces (16 lived scenes instead of 4 paragraphs) and every scene maps to
 * a shipped feature.
 */

export const PROFILES = ['freelance', 'family', 'dev', 'admin'] as const;
export const STOPS = ['s1', 's2', 's3', 's4'] as const;

function Day({ profile }: { profile: (typeof PROFILES)[number] }) {
  const { t } = useTranslation();
  return (
    <ol className="relative grid list-none gap-8 pt-2 md:grid-cols-4 md:gap-0">
      <span
        aria-hidden="true"
        className="absolute left-[7px] top-2 h-full w-px bg-border md:left-[6%] md:right-[6%] md:top-[9px] md:h-px md:w-auto"
      />
      {STOPS.map(stop => (
        <li key={stop} className="relative pl-7 md:px-5 md:pl-5">
          <span
            aria-hidden="true"
            className="absolute left-0 top-1 block h-4 w-4 rounded-full border-[3px] border-background bg-primary md:relative md:left-auto md:top-auto md:mb-3"
          />
          <p className="text-xl font-extrabold tabular-nums">
            {t(`landing.day.${profile}.${stop}_time`)}
          </p>
          <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
            {t(`landing.day.${profile}.${stop}_text`)}
          </p>
        </li>
      ))}
    </ol>
  );
}

export function DayTimeline() {
  const { t } = useTranslation();

  return (
    <section id="day" aria-labelledby="day-title" className="landing-section scroll-mt-24 py-24">
      <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
        <FadeInOnScroll>
          <h2
            id="day-title"
            className="text-center text-3xl font-bold tracking-tight mobile:text-4xl"
          >
            {t('landing.day.title')}
          </h2>
          <Tabs
            className="mt-8"
            label={t('landing.day.tabs_label')}
            items={PROFILES.map(profile => ({
              id: profile,
              label: t(`landing.day.tab_${profile}`),
              content: <Day profile={profile} />,
            }))}
          />
        </FadeInOnScroll>
      </div>
    </section>
  );
}
