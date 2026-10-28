'use client';
import type { PublicGesture } from './emote-presentation';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
/** One translated sentence per gesture ("Léa waves"), never a label pasted after a colon. */
export function WorldEmoteAnnouncements({
  lng,
  gestures = [],
}: {
  lng: Language;
  gestures?: readonly PublicGesture[];
}) {
  const { t } = useTranslation(lng);
  return (
    <div className="sr-only" role="status" aria-live="polite" aria-atomic="false">
      {gestures.map(event => (
        <p
          key={event.id + ':' + event.serial}
          data-world-emote={event.kind}
          data-world-emote-actor={event.id}
        >
          {t('world.emotes.announcements.' + event.kind, { alias: event.alias })}
        </p>
      ))}
    </div>
  );
}
