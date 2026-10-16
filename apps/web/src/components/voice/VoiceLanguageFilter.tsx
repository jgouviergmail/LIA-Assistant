'use client';

/**
 * « Only voices in <language> » — the one switch every voice picker shares
 * (ADR-345 amendment 2026-10-14): the administrator's voice slots, the radio's
 * roles and LIA's voices in the voice mode. The language is the reader's, named
 * in their own language.
 */
import { useId } from 'react';

import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { languageName } from '@/lib/language-name';

export function VoiceLanguageFilter({
  lng,
  only,
  onOnlyChange,
}: {
  lng: Language;
  only: boolean;
  onOnlyChange: (only: boolean) => void;
}) {
  const { t } = useTranslation(lng);
  const id = useId();
  return (
    <div className="flex items-center justify-between gap-3">
      <Label htmlFor={id} className="text-sm font-normal">
        {t('settings.voice_language_filter.only_language', { language: languageName(lng, lng) })}
      </Label>
      <Switch id={id} checked={only} onCheckedChange={onOnlyChange} />
    </div>
  );
}
