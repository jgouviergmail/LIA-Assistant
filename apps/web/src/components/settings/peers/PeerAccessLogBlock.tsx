'use client';

/**
 * PeerAccessLogBlock — transparency view (peers program, spec §12.4).
 *
 * Lists cross-user reads OF the viewer's shared data ("X read your
 * availability"), newest first. Pure presentation: data comes from the
 * section shell. Dates render as semantic `<time>` in the viewer's locale
 * and browser timezone (the display-timezone doctrine).
 */

import { Eye } from 'lucide-react';

import type { AccessLogEntry } from '@/hooks/usePeerConnections';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';

export interface PeerAccessLogBlockProps {
  lng: Language;
  entries: AccessLogEntry[];
}

/** Format an ISO instant in the viewer's locale + browser timezone. */
function formatInstant(lng: string, iso: string): string {
  return new Intl.DateTimeFormat(lng, { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(iso)
  );
}

export function PeerAccessLogBlock({ lng, entries }: PeerAccessLogBlockProps) {
  const { t } = useTranslation(lng);

  return (
    <div className="space-y-2">
      <h4 className="flex items-center gap-2 text-sm font-medium">
        <Eye className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
        {t('settings.peers.access_log.title')}
      </h4>
      <p className="text-xs text-muted-foreground">{t('settings.peers.access_log.hint')}</p>
      {entries.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('settings.peers.access_log.empty')}</p>
      ) : (
        <ul className="space-y-1">
          {entries.map((entry, index) => (
            <li
              key={`${entry.created_at}-${index}`}
              className="flex flex-wrap items-baseline gap-x-2 text-sm"
            >
              <span className="font-medium">{entry.accessor_display_name}</span>
              <span className="text-muted-foreground">
                {t(`settings.peers.domains.${entry.domain}`)}
              </span>
              <time dateTime={entry.created_at} className="text-xs text-muted-foreground">
                {formatInstant(lng, entry.created_at)}
              </time>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
