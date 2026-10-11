'use client';

import { Check, ChevronRight, FileText } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { SCENE_TONES } from './scene-tones';
import { PRODUCT_DEMO_KEY, type ProductSceneId } from './scenes';

export function ClassicProductResult({ sceneId }: { sceneId: ProductSceneId }) {
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
            <span className="mt-1.5 block text-px-10 leading-snug text-muted-foreground">
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
