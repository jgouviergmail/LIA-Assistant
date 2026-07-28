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
      {/* Scene pastilles + schedule controls */}
      <div
        role="group"
        aria-label={t('landing.chat_mockup.demo_scenes_aria')}
        className="flex flex-wrap items-center justify-center gap-2"
      >
        {SCENARIOS.map(s => (
          <button
            key={s.id}
            type="button"
            aria-pressed={scenario.id === s.id}
            onClick={() => controls.select(s.id)}
            className={cn(
              'whitespace-nowrap rounded-full border px-3 py-1 text-xs font-medium transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40',
              scenario.id === s.id
                ? 'border-primary/50 bg-primary/10 text-primary'
                : 'border-border/60 bg-background/60 text-muted-foreground hover:text-foreground hover:border-border'
            )}
          >
            {t(`landing.chat_mockup.${s.chipKey}`)}
          </button>
        ))}
        {!reducedMotion && (
          <>
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
          </>
        )}
      </div>

      {/* Discreet per-scene progress line (decorative — the pressed pastille
          is the accessible position indicator). */}
      {!reducedMotion && (
        <div aria-hidden="true" className="mx-auto h-0.5 w-40 overflow-hidden rounded-full bg-border/50">
          <div
            className="h-full rounded-full bg-primary/70 transition-[width] duration-300"
            style={{ width: `${Math.round(controls.progress * 100)}%` }}
          />
        </div>
      )}

      {/* The mockup itself — one decorative image, same as the landing hero. */}
      <div
        className="relative"
        role="img"
        aria-label={t('landing.chat_mockup.aria')}
      >
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
