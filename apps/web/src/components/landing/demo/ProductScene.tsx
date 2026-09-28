'use client';

import { Check, ChevronRight, FileText, LockKeyhole, Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { SCENE_TONES } from './scene-tones';
import {
  PRODUCT_DEMO_KEY,
  productScene,
  type ProductSceneId,
  type ProductScenePhase,
} from './scenes';

interface ProductSceneProps {
  sceneId: ProductSceneId;
  /** Omit for a completed illustration; the player reveals the same scene in three beats. */
  phase?: ProductScenePhase;
  className?: string;
}

export function ProductResult({ sceneId }: { sceneId: ProductSceneId }) {
  const { t } = useTranslation();
  const key = `${PRODUCT_DEMO_KEY}.scenes.${sceneId}`;
  const tone = SCENE_TONES[sceneId];

  if (sceneId === 'day') {
    return (
      <div className="space-y-3">
        <div className="flex h-8 items-center justify-center gap-1" aria-hidden="true">
          {[8, 16, 24, 12, 28, 19, 32, 22, 14, 26, 32, 18, 10, 24, 16, 8].map((height, i) => (
            <span key={i} className={cn('w-1.5 rounded-full', tone.fill)} style={{ height }} />
          ))}
        </div>
        <ol className="space-y-2">
          {[1, 2, 3].map(n => (
            <li key={n} className="flex items-center gap-2 text-xs leading-snug">
              <span
                className={cn('h-1.5 w-1.5 shrink-0 rounded-full', tone.fill)}
                aria-hidden="true"
              />
              {t(`${key}.result_${n}`)}
            </li>
          ))}
        </ol>
      </div>
    );
  }

  if (sceneId === 'watch') {
    return (
      <div className="space-y-3">
        <div
          className={cn(
            'flex items-center gap-2 rounded-lg p-2 text-xs leading-snug',
            tone.surface
          )}
        >
          <Check className={cn('h-4 w-4 shrink-0', tone.text)} aria-hidden="true" />
          {t(`${key}.result_1`)}
        </div>
        <p className={cn('border-l-2 pl-3 text-sm leading-snug', tone.border)}>
          {t(`${key}.result_2`)}
        </p>
        <p className="text-xs leading-snug text-muted-foreground">{t(`${key}.result_3`)}</p>
      </div>
    );
  }

  if (sceneId === 'call' || sceneId === 'relay') {
    return (
      <div className="space-y-3">
        <div
          className={cn(
            'grid grid-cols-[1fr_auto_1fr] items-center gap-2 rounded-lg p-3',
            tone.surface
          )}
        >
          <p className="text-sm font-semibold leading-snug">{t(`${key}.result_1`)}</p>
          <ChevronRight className={cn('h-4 w-4', tone.text)} aria-hidden="true" />
          <p className="text-right text-sm font-semibold leading-snug">{t(`${key}.result_2`)}</p>
        </div>
        <p className="text-xs leading-relaxed">{t(`${key}.result_3`)}</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className={cn('grid grid-cols-2 divide-x divide-border rounded-lg py-3', tone.surface)}>
        {[1, 2].map(n => (
          <div key={n} className="px-3">
            <p className="text-xs font-semibold leading-snug">{t(`${key}.result_${n}`)}</p>
            <span className="mt-1.5 block text-[10px] leading-snug text-muted-foreground">
              {t(`${key}.evidence_${n}`)}
            </span>
          </div>
        ))}
      </div>
      <div className="flex items-start gap-2 text-xs leading-relaxed">
        <FileText className={cn('mt-0.5 h-4 w-4 shrink-0', tone.text)} aria-hidden="true" />
        <span>{t(`${key}.result_3`)}</span>
      </div>
    </div>
  );
}

/** A readable product illustration, shared by the hero player and the chapters. */
export function ProductScene({ sceneId, phase = 2, className }: ProductSceneProps) {
  const { t } = useTranslation();
  const scene = productScene(sceneId);
  const Icon = scene.icon;
  const key = `${PRODUCT_DEMO_KEY}.scenes.${scene.id}`;
  const tone = SCENE_TONES[sceneId];

  return (
    <div
      className={cn(
        'relative flex min-h-[550px] min-w-0 flex-col rounded-2xl border border-border bg-card text-left shadow-lg [overflow-wrap:anywhere] sm:min-h-[510px]',
        className
      )}
    >
      <div className="flex min-h-12 items-center gap-2 border-b border-border px-4 py-3">
        <Icon className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        <p className="text-sm font-semibold">{t(`${key}.title`)}</p>
        <span className="ml-auto shrink-0 text-[10px] text-muted-foreground">
          {t(`${PRODUCT_DEMO_KEY}.example`)}
        </span>
      </div>
      <div className="flex flex-1 flex-col gap-4 p-4">
        <div className="ml-5 rounded-2xl rounded-tr-sm bg-primary/10 px-3.5 py-3">
          <p className="text-sm leading-relaxed">{t(`${key}.request`)}</p>
        </div>
        <div
          aria-hidden={phase < 1}
          style={{ visibility: phase < 1 ? 'hidden' : undefined }}
          className={cn(
            'space-y-2 transition-opacity duration-500 motion-reduce:transition-none',
            phase < 1 && 'opacity-0'
          )}
        >
          <p className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
            <Sparkles className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
            {t(`${PRODUCT_DEMO_KEY}.context`)}
          </p>
          <div className="grid grid-cols-3 gap-1.5">
            {scene.sources.map((source, i) => (
              <div
                key={source}
                className="min-w-0 rounded-lg border border-border bg-background px-2 py-2"
              >
                <span className="block text-[10px] font-semibold leading-snug text-primary">
                  {t(`${PRODUCT_DEMO_KEY}.sources.${source}`)}
                </span>
                <span className="mt-1 block text-[11px] leading-snug">
                  {t(`${key}.source_${i + 1}`)}
                </span>
              </div>
            ))}
          </div>
        </div>
        <div
          aria-hidden={phase < 2}
          style={{ visibility: phase < 2 ? 'hidden' : undefined }}
          className={cn(
            'flex-1 space-y-3 rounded-xl border bg-background p-3 transition-opacity duration-500 motion-reduce:transition-none',
            tone.border,
            phase < 2 && 'opacity-0'
          )}
        >
          <p
            className={cn('flex items-center gap-2 text-sm font-semibold leading-snug', tone.text)}
          >
            <Check className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
            {t(`${key}.result_title`)}
          </p>
          <ProductResult sceneId={sceneId} />
          <div className="flex items-start gap-1.5 border-t border-border pt-2 text-[10px] leading-relaxed text-muted-foreground">
            <LockKeyhole className="mt-0.5 h-3 w-3 shrink-0 text-primary" aria-hidden="true" />
            <span>{t(`${key}.guardrail`)}</span>
          </div>
        </div>
      </div>
      <p className="border-t border-border px-4 py-2 text-[10px] leading-snug text-muted-foreground">
        {t(`${PRODUCT_DEMO_KEY}.illustrative`)}
      </p>
    </div>
  );
}
