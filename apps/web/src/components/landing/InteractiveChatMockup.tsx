'use client';

import Link from 'next/link';
import { ChevronDown, Lightbulb, Pause, Play, RotateCcw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import type { Language } from '@/i18n/settings';
import { ProductScene } from './demo/ProductScene';
import {
  HOME_PRODUCT_DEMO_KEY,
  PRODUCT_DEMO_KEY,
  PRODUCT_SCENES,
  type ProductScenePhase,
} from './demo/scenes';
import { SCENE_TONES } from './demo/scene-tones';
import { useProductDemo } from './demo/useProductDemo';

interface InteractiveChatMockupProps {
  lng: string;
  /** The hero supplies its own CTA; the dedicated demo page keeps this one. */
  withCta?: boolean;
  /** Homepage-only improvements; the dedicated demo retains its presentation. */
  home?: boolean;
}

export function InteractiveChatMockup({
  lng,
  withCta = true,
  home = false,
}: InteractiveChatMockupProps) {
  const { t } = useTranslation();
  const demoKey = home ? HOME_PRODUCT_DEMO_KEY : PRODUCT_DEMO_KEY;
  const { ref, sceneId, phase, reducedMotion, paused, select, selectPhase, replay, togglePause } =
    useProductDemo({ manual: home });
  return (
    <div ref={ref} className="mx-auto w-full min-w-0 max-w-lg space-y-3">
      <div
        role="group"
        aria-label={t(`${demoKey}.choose_scene`)}
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
                'flex min-w-0 items-center justify-center gap-1.5 rounded-lg border px-2 py-1.5 text-px-11 font-medium leading-tight transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary',
                home ? 'min-h-11' : 'min-h-10',
                sceneId === scene.id
                  ? cn(tone.border, tone.surface, tone.text)
                  : 'border-border bg-background/70 text-muted-foreground hover:text-foreground'
              )}
            >
              <Icon className="h-3.5 w-3.5 shrink-0 text-primary" aria-hidden="true" />
              <span>{t(`${demoKey}.scenes.${scene.id}.title`)}</span>
            </button>
          );
        })}
      </div>
      {home && (
        <p className="text-xs leading-5 text-muted-foreground">{t(`${demoKey}.explore_hint`)}</p>
      )}
      <div className="flex min-h-7 items-center justify-between gap-2">
        <ol
          aria-label={t(`${demoKey}.steps`)}
          className={
            home
              ? 'grid w-full grid-cols-3 gap-1.5'
              : 'flex gap-2 text-px-10 sm:gap-3 sm:text-px-11'
          }
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
              {!home && (
                <span
                  aria-hidden="true"
                  className={cn(
                    'cosmos-demo-step-dot h-1.5 w-1.5 rounded-full',
                    phase >= i ? SCENE_TONES[sceneId].fill : 'bg-border'
                  )}
                />
              )}
              {home ? (
                <button
                  type="button"
                  aria-pressed={phase === i}
                  onClick={() => selectPhase(i as ProductScenePhase)}
                  className={cn(
                    'min-h-11 w-full rounded-lg border px-2 py-2 text-xs font-medium leading-5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary',
                    phase === i
                      ? 'border-primary/40 bg-primary/10 text-foreground'
                      : 'border-border bg-background/70 text-muted-foreground hover:text-foreground'
                  )}
                >
                  {t(`${demoKey}.steps_${step}`)}
                </button>
              ) : (
                t(`${demoKey}.steps_${step}`)
              )}
            </li>
          ))}
        </ol>
        {!home && !reducedMotion && (
          <div className="flex shrink-0 items-center gap-1">
            <button
              type="button"
              onClick={togglePause}
              aria-label={t(`${demoKey}.${paused ? 'play' : 'pause'}`)}
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
              aria-label={t(`${demoKey}.replay`)}
              className="rounded-md p-1.5 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            >
              <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          </div>
        )}
      </div>
      <ProductScene key={home ? sceneId : undefined} sceneId={sceneId} phase={phase} home={home} />
      {home ? (
        <aside className="rounded-xl border border-border bg-background/70 px-4 py-3">
          <p className="flex items-center gap-2 text-xs font-semibold">
            <Lightbulb className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
            {t(`${demoKey}.difference`)}
          </p>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
            {t(`${demoKey}.scenes.${sceneId}.difference`)}
          </p>
        </aside>
      ) : (
        <details className="group rounded-lg border border-border bg-background/60">
          <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2.5 text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary [&::-webkit-details-marker]:hidden">
            <Lightbulb className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
            {t(`${demoKey}.difference`)}
            <ChevronDown
              className="ml-auto h-3.5 w-3.5 shrink-0 transition-transform group-open:rotate-180"
              aria-hidden="true"
            />
          </summary>
          <p className="px-3 pb-3 text-xs leading-relaxed text-muted-foreground">
            {t(`${demoKey}.scenes.${sceneId}.difference`)}
          </p>
        </details>
      )}
      {withCta && (
        <div className="pt-2 text-center">
          <Button asChild size="lg" className="px-8">
            <Link href={buildLocalizedPath('/register', lng as Language)}>
              {t(home ? 'landing.hero.home_cta_primary' : 'landing.hero.cta_primary')}
            </Link>
          </Button>
        </div>
      )}
    </div>
  );
}
