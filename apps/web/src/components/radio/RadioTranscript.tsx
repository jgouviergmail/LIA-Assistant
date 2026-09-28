'use client';

/**
 * The programme on air, line by line (ADR-324): who speaks, what is said, and
 * what each sentence rests on — the outlet and the article for the world, the
 * family of the record for the listener's own day. The line being spoken is
 * marked (`aria-current`) as the audio moves on.
 *
 * Every link comes from a feed a stranger publishes: only a web address ever
 * becomes an anchor, opened in a new tab without a referrer.
 */

import { ExternalLink } from 'lucide-react';

import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { currentLineIndex, webUrl } from '@/lib/radio/format';
import type { RadioSegment, RadioSource } from '@/lib/radio/types';
import { cn } from '@/lib/utils';

function Source({ lng, source }: { lng: Language; source: RadioSource }) {
  const href = webUrl(source.url);
  const date =
    source.published_at !== null
      ? new Intl.DateTimeFormat(lng, { dateStyle: 'medium' }).format(new Date(source.published_at))
      : null;
  const label = date ? `${source.label} · ${date}` : source.label;
  if (href === null) return <span className="text-muted-foreground">{label}</span>;
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline"
    >
      {label}
      <ExternalLink className="h-3 w-3" aria-hidden="true" />
    </a>
  );
}

export function RadioTranscript({
  lng,
  segment,
  positionS,
}: {
  lng: Language;
  segment: RadioSegment;
  positionS: number;
}) {
  const { t } = useTranslation(lng);
  const current = currentLineIndex(
    segment.transcript.map(line => line.offset_s),
    positionS
  );
  return (
    <ol className="space-y-2" aria-label={t('radio.page.transcript_label')}>
      {segment.transcript.map((line, index) => (
        <li
          // The lines of one segment never reorder: their place is their identity.
          key={index}
          aria-current={index === current ? 'true' : undefined}
          className={cn(
            'rounded-lg border px-3 py-2',
            index === current ? 'border-primary/40 bg-primary/5' : 'border-border/60'
          )}
        >
          <p className="text-xs font-medium text-muted-foreground">
            {t(`radio.roles.${line.role}`)}
          </p>
          <p className="text-sm leading-relaxed">{line.text}</p>
          {line.sources.length > 0 && (
            <p className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs">
              <span className="sr-only">{t('radio.page.sources_label')}</span>
              {line.sources.map(source => (
                <Source key={`${source.label}|${source.url ?? ''}`} lng={lng} source={source} />
              ))}
            </p>
          )}
        </li>
      ))}
    </ol>
  );
}
