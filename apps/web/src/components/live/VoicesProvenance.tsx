'use client';

/**
 * Where the voice list comes from (ADR-299): measured 2026-09-18, the
 * provider offers no listing endpoint and silently accepts an unknown name,
 * so the form offers its PUBLISHED list and says so — dated, with its source.
 * Renders nothing for a list a provider discovered live.
 */
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { formatDate } from '@/lib/format';
import type { LiveVoicesResponse } from '@/lib/live/types';

/** Where the voice list comes from: the provider's published list, dated, with its source. */
export function VoicesProvenance({
  lng,
  voices,
}: {
  lng: Language;
  voices: LiveVoicesResponse | undefined;
}) {
  const { t } = useTranslation(lng);
  if (!voices || voices.provenance !== 'published') return null;
  const date = voices.published_at
    ? formatDate(new Date(`${voices.published_at}T00:00:00Z`), lng, {
        dateStyle: 'long',
        timeZone: 'UTC',
      })
    : '';
  return (
    <p className="text-xs text-muted-foreground">
      {t('settings.connectors.live.voices_provenance', { date })}
      {voices.source && (
        <>
          {' '}
          <a
            href={voices.source}
            target="_blank"
            rel="noreferrer noopener"
            className="underline underline-offset-2"
          >
            {t('settings.connectors.live.voices_source')}
          </a>
        </>
      )}
    </p>
  );
}
