'use client';

import Link from 'next/link';
import { Pause, Play, RotateCcw } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import type { Language } from '@/i18n/settings';
import { MockupStage } from './mockup/MockupStage';
import { SCENARIOS } from './mockup/scenarios';
import { useMockupTimeline } from './mockup/useMockupTimeline';

interface InteractiveChatMockupProps {
  /** Short locale segment (e.g. `fr`) for the localized CTA href. */
  lng: string;
  /**
   * Closing CTA under the mockup (default true — the /demo page). The landing
   * hero passes false: its own primary CTA sits right beside the mockup, and
   * two identical "join the beta" buttons a few pixels apart read as a bug.
   */
  withCta?: boolean;
}

/**
 * The /demo page mockup (UX P12): the exact same four-act animation as the
 * landing hero, wrapped with real controls — scene pastilles, pause/replay, a
 * discreet progress line and a closing CTA. The auto loop keeps cycling until
 * the first interaction; a selected scene plays once and freezes on its
 * resolution frame.
 *
 * A11y: the mockup itself stays ONE decorative `role="img"` (its inner
 * chrome is fake), so every real control lives OUTSIDE that element. Under
 * `prefers-reduced-motion` the pastilles swap static resolution frames and
 * the pause/replay controls disappear (there is nothing to pause).
 */
export function InteractiveChatMockup({ lng, withCta = true }: InteractiveChatMockupProps) {
  const { t } = useTranslation();
  const { scenario, reached, fading, reducedMotion, controls } = useMockupTimeline({
    interactive: true,
  });

  return (
    <div className="w-full max-w-md mx-auto space-y-4">
      {/* The four acts — ALWAYS one line.
          `flex-nowrap` is the requirement, not a preference: the hero aligns
          this row optically with the badge/date line of its left column
          (`lg:-translate-y-[91px]` in CosmosHero, measured in-browser), and a
          row that wraps moves everything under it, so the two columns stop
          reading as starting at the same height.
          They did not fit: four chips plus two control buttons shared one
          `flex-wrap` container inside `max-w-md` (448px), and the German
          labels alone measure ~468px. `overflow-x-auto` is the safety net for
          the locales that still exceed the width — one scrollable line beats
          two stacked ones, and it also keeps an unbreakable label from
          widening the hero past a phone viewport, which is the exact
          mechanism `min-w-0` exists to stop one level up.
          The scrollbar is hidden and the row bleeds to the viewport edges
          below `sm` so a cut-off chip still reads as "there is more". */}
      <div
        role="group"
        aria-label={t('landing.chat_mockup.demo_scenes_aria')}
        className={cn(
          '-mx-4 flex flex-nowrap items-center gap-1.5 overflow-x-auto px-4',
          'sm:mx-0 sm:justify-center sm:px-0',
          '[scrollbar-width:none] [&::-webkit-scrollbar]:hidden'
        )}
      >
        {SCENARIOS.map(s => (
          <button
            key={s.id}
            type="button"
            aria-pressed={scenario.id === s.id}
            onClick={() => controls.select(s.id)}
            className={cn(
              // `shrink-0`: without it flex compresses the chips instead of
              // scrolling, and the labels truncate mid-word.
              'shrink-0 whitespace-nowrap rounded-full border px-2.5 py-1 text-xs font-medium transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40',
              scenario.id === s.id
                ? 'border-primary/50 bg-primary/10 text-primary'
                : 'border-border/60 bg-background/60 text-muted-foreground hover:text-foreground hover:border-border'
            )}
          >
            {t(`landing.chat_mockup.${s.chipKey}`)}
          </button>
        ))}
      </div>

      {/* Schedule controls — ALWAYS the line below the acts, never mixed into
          their row: they are chrome about the animation, not one of its four
          chapters, and sharing a wrapping container is what let a control end
          up beside a chip on one width and under it on the next. */}
      {!reducedMotion && (
        <div className="flex items-center justify-center gap-2">
          <button
            type="button"
            onClick={controls.togglePause}
            aria-label={t(
              controls.paused ? 'landing.chat_mockup.demo_play' : 'landing.chat_mockup.demo_pause'
            )}
            className="rounded-full border border-border/60 bg-background/60 p-1.5 text-muted-foreground transition-colors hover:text-foreground hover:border-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
          >
            {controls.paused ? <Play className="h-3.5 w-3.5" /> : <Pause className="h-3.5 w-3.5" />}
          </button>
          <button
            type="button"
            onClick={controls.replay}
            aria-label={t('landing.chat_mockup.demo_replay')}
            className="rounded-full border border-border/60 bg-background/60 p-1.5 text-muted-foreground transition-colors hover:text-foreground hover:border-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {/* Discreet per-scene progress line (decorative — the pressed pastille
          is the accessible position indicator). */}
      {!reducedMotion && (
        <div
          aria-hidden="true"
          className="mx-auto h-0.5 w-40 overflow-hidden rounded-full bg-border/50"
        >
          <div
            className="h-full rounded-full bg-primary/70 transition-[width] duration-300"
            style={{ width: `${Math.round(controls.progress * 100)}%` }}
          />
        </div>
      )}

      {/* The mockup itself — one decorative image, same as the landing hero. */}
      <div className="relative" role="img" aria-label={t('landing.chat_mockup.aria')}>
        <div
          className="absolute -inset-6 rounded-[2rem] bg-gradient-to-br from-primary/25 via-violet-500/15 to-transparent blur-2xl"
          aria-hidden="true"
        />
        <MockupStage
          scenario={scenario}
          reached={reached}
          fading={fading}
          reducedMotion={reducedMotion}
        />
      </div>

      {/* Closing CTA — the same journey as the landing hero. */}
      {withCta && (
        <div className="pt-2 text-center">
          <Button asChild size="lg" className="px-8">
            <Link href={buildLocalizedPath('/register', lng as Language)}>
              {t('landing.hero.cta_primary')}
            </Link>
          </Button>
        </div>
      )}
    </div>
  );
}
