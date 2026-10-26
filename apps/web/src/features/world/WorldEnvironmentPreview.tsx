'use client';
import { createContext, useContext, useState, type ReactNode } from 'react';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { Atmosphere } from './atmosphere';

type Phase = 'auto' | 'noon' | 'night';
const PreviewPhase = createContext<Phase>('auto');
/** Cosmetic control mounted only by the explicitly enabled development preview. */
export function WorldEnvironmentPreview({ lng, children }: { lng: Language; children: ReactNode }) {
  const { t } = useTranslation(lng);
  const [phase, setPhase] = useState<Phase>('auto');
  return (
    <PreviewPhase.Provider value={phase}>
      <label className="mb-2 flex shrink-0 flex-wrap items-center gap-2 rounded-lg border bg-background px-3 py-2 text-xs">
        <span>{t('world.preview_lighting.label')}</span>
        <select
          className="min-h-9 rounded-md border bg-background px-2"
          value={phase}
          onChange={e => {
            const value = e.target.value;
            if (value === 'auto' || value === 'noon' || value === 'night') setPhase(value);
          }}
        >
          <option value="auto">{t('world.preview_lighting.auto')}</option>
          <option value="noon">{t('world.preview_lighting.day')}</option>
          <option value="night">{t('world.preview_lighting.night')}</option>
        </select>
      </label>
      {children}
    </PreviewPhase.Provider>
  );
}
export function usePreviewAtmosphere(native: Atmosphere): Atmosphere {
  const phase = useContext(PreviewPhase);
  return phase === 'auto' ? native : { ...native, phase };
}
