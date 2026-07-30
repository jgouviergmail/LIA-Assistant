'use client';

/**
 * "A day with LIA", cosmos edition: the signature pinned scene. The visitor's
 * scroll advances the active profile's day horizontally — steps light up as
 * the day progresses (the scroll IS the day). Profiles remain the existing
 * accessible Tabs; content reuses the exact `landing.day.*` keys.
 *
 * Mobile and reduced-motion render the untouched classic `DayTimeline`
 * (vertical, complete) — no pin, no motion, zero content loss.
 */

import { useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { DayTimeline, PROFILES, STOPS } from '../editorial/DayTimeline';
import { Tabs } from '../editorial/Tabs';
import { GhostWord } from './GhostWord';
import { GlowCard } from './GlowCard';
import { PinnedScene } from './PinnedScene';
import { useMediaFlag } from './useCosmosScroll';

const MOBILE_QUERY = '(max-width: 880px)';
const REDUCED_QUERY = '(prefers-reduced-motion: reduce)';
const STEP_LIT_EPSILON = 0.02;
const STEP_FOCUS_BAND = 0.18;

function DayTrack({ profile }: { profile: (typeof PROFILES)[number] }) {
  const { t } = useTranslation();
  return (
    <div className="cosmos-track-clip">
      <div className="cosmos-track">
        {STOPS.map(stop => (
          <GlowCard key={stop} className="cosmos-step">
            <time>{t(`landing.day.${profile}.${stop}_time`)}</time>
            <p>{t(`landing.day.${profile}.${stop}_text`)}</p>
          </GlowCard>
        ))}
      </div>
    </div>
  );
}

export function CosmosDay() {
  const { t } = useTranslation();
  const stageRef = useRef<HTMLDivElement>(null);
  const isMobile = useMediaFlag(MOBILE_QUERY);
  const isReduced = useMediaFlag(REDUCED_QUERY);
  const isStatic = isMobile || isReduced;

  // Imperative per-frame updates (no React state at scroll frequency): the
  // track offset budget and each step's lit/focus classes.
  const handleProgress = useCallback((progress: number) => {
    const stage = stageRef.current;
    if (!stage) return;

    stage.querySelectorAll<HTMLElement>('.cosmos-track').forEach(track => {
      const clip = track.parentElement;
      if (!clip) return;
      const max = Math.max(0, track.scrollWidth - clip.clientWidth);
      track.style.setProperty('--track-max', `${max}px`);
    });

    const viewportCenter = window.innerWidth / 2;
    stage.querySelectorAll<HTMLElement>('[role="tabpanel"]').forEach(panel => {
      const steps = panel.querySelectorAll<HTMLElement>('.cosmos-step');
      steps.forEach((step, index) => {
        step.classList.toggle('lit', progress >= index / steps.length - STEP_LIT_EPSILON);
        const rect = step.getBoundingClientRect();
        const distance = Math.abs(rect.left + rect.width / 2 - viewportCenter) / window.innerWidth;
        step.classList.toggle('focus', distance < STEP_FOCUS_BAND);
      });
    });
  }, []);

  if (isStatic) {
    return <DayTimeline />;
  }

  return (
    <section id="day" aria-labelledby="day-title" className="landing-section scroll-mt-24">
      <PinnedScene heights={3.2} onProgress={handleProgress}>
        <GhostWord wordKey="landing.cosmos.ghost.day" direction={-1} />
        <div ref={stageRef} className="relative z-10 mx-auto w-full max-w-6xl px-4 sm:px-6 lg:px-8">
          <div className="text-center">
            <h2 id="day-title" className="text-3xl font-bold tracking-tight mobile:text-4xl">
              {t('landing.day.title')}
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">{t('landing.cosmos.day_hint')}</p>
          </div>
          <Tabs
            className="mt-8"
            label={t('landing.day.tabs_label')}
            items={PROFILES.map(profile => ({
              id: profile,
              label: t(`landing.day.tab_${profile}`),
              content: <DayTrack profile={profile} />,
            }))}
          />
          <div className="cosmos-progress" aria-hidden="true">
            <i />
          </div>
        </div>
      </PinnedScene>
    </section>
  );
}
