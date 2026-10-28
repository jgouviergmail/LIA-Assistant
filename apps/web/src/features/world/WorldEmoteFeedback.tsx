'use client';
import { useEffect, useState } from 'react';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { EmoteFeedback } from './useWorldSession';

export const EMOTE_FEEDBACK_MS = 4000;
/** A refused gesture is said once and withdrawn; a repeated refusal is said again. */
export function WorldEmoteFeedback({
  lng,
  feedback,
}: {
  lng: Language;
  feedback?: EmoteFeedback | null;
}) {
  const { t } = useTranslation(lng);
  const [expired, setExpired] = useState<EmoteFeedback | null>(null);
  useEffect(() => {
    if (!feedback) return;
    const timer = setTimeout(() => setExpired(feedback), EMOTE_FEEDBACK_MS);
    return () => clearTimeout(timer);
  }, [feedback]);
  const shown = feedback && feedback !== expired ? feedback : null;
  return (
    <div role="status" data-world-emote-feedback={shown?.result}>
      {shown && (
        <p key={shown.serial} className="world-pose-feedback border bg-background text-sm">
          {t('world.emotes.' + shown.result)}
        </p>
      )}
    </div>
  );
}
