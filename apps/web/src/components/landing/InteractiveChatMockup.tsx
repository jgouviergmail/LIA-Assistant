'use client';

import Link from 'next/link';
import { ChevronDown, Lightbulb, Pause, Play, RotateCcw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import type { Language } from '@/i18n/settings';
import { ProductScene } from './demo/ProductScene';
import { PRODUCT_DEMO_KEY, PRODUCT_SCENES } from './demo/scenes';
import { SCENE_TONES } from './demo/scene-tones';
import { useProductDemo } from './demo/useProductDemo';

interface InteractiveChatMockupProps {
  lng: string;
  /** The hero supplies its own CTA; the dedicated demo page keeps this one. */
  withCta?: boolean;
}

export function InteractiveChatMockup({ lng, withCta = true }: InteractiveChatMockupProps) {
  const { t } = useTranslation();
  const { ref, sceneId, phase, reducedMotion, paused, select, replay, togglePause } =
    useProductDemo();
  return (
    <div ref={ref} className="mx-auto w-full min-w-0 max-w-lg space-y-3">
      <div
        role="group"
        aria-label={t(`${PRODUCT_DEMO_KEY}.choose_scene`)}
        className="grid grid-cols-3 gap-1.5"
      >
        {PRODUCT_SCENES.map(scene => {
          const Icon = scene.icon;
          const tone = SCENE_TONES[scene.id];
          return (
            <button
              key={scene.id}
              type="button"
              aria-pressed={sceneId === scene.id}
              onClick={() => select(scene.id)}
              className={cn(
                'flex min-h-10 min-w-0 items-center justify-center gap-1.5 rounded-lg border px-2 py-1.5 text-px-11 font-medium leading-tight transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary',
                sceneId === scene.id
                  ? cn(tone.border, tone.surface, tone.text)
                  : 'border-border bg-background/70 text-muted-foreground hover:text-foreground'
              )}
            >
              <Icon className="h-3.5 w-3.5 shrink-0 text-primary" aria-hidden="true" />
              <span>{t(`${PRODUCT_DEMO_KEY}.scenes.${scene.id}.title`)}</span>
            </button>
          );
        })}
      </div>
      <div className="flex min-h-7 items-center justify-between gap-2">
        <ol
          aria-label={t(`${PRODUCT_DEMO_KEY}.steps`)}
          className="flex gap-2 text-px-10 sm:gap-3 sm:text-px-11"
        >
          {['request', 'context', 'result'].map((step, i) => (
            <li
              key={step}
              aria-current={phase === i ? 'step' : undefined}
              className={cn(
                'flex items-center gap-1.5',
                phase >= i ? 'text-foreground' : 'text-muted-foreground'
              )}
            >
              <span
                aria-hidden="true"
                className={cn(
                  'h-1.5 w-1.5 rounded-full',
                  phase >= i ? SCENE_TONES[sceneId].fill : 'bg-border'
                )}
              />
              {t(`${PRODUCT_DEMO_KEY}.steps_${step}`)}
            </li>
          ))}
        </ol>
        {!reducedMotion && (
          <div className="flex shrink-0 items-center gap-1">
            <button
              type="button"
              onClick={togglePause}
              aria-label={t(`${PRODUCT_DEMO_KEY}.${paused ? 'play' : 'pause'}`)}
              className="rounded-md p-1.5 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            >
              {paused ? (
                <Play className="h-3.5 w-3.5" aria-hidden="true" />
              ) : (
                <Pause className="h-3.5 w-3.5" aria-hidden="true" />
              )}
            </button>
            <button
              type="button"
              onClick={replay}
              aria-label={t(`${PRODUCT_DEMO_KEY}.replay`)}
              className="rounded-md p-1.5 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            >
              <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          </div>
        )}
      </div>
      <ProductScene sceneId={sceneId} phase={phase} />
      <details className="group rounded-lg border border-border bg-background/60">
        <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2.5 text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary [&::-webkit-details-marker]:hidden">
          <Lightbulb className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
          {t(`${PRODUCT_DEMO_KEY}.difference`)}
          <ChevronDown
            className="ml-auto h-3.5 w-3.5 shrink-0 transition-transform group-open:rotate-180"
            aria-hidden="true"
          />
        </summary>
        <p className="px-3 pb-3 text-xs leading-relaxed text-muted-foreground">
          {t(`${PRODUCT_DEMO_KEY}.scenes.${sceneId}.difference`)}
        </p>
      </details>
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
