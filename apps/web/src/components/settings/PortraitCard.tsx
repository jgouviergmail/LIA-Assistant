'use client';

/**
 * The compiled portrait — « How LIA sees you » — read-only, in its two
 * formats, with what it was compiled from (ADR-292), a dated line when its
 * evidence moved since (the words stay — 2026-10-12), and the one lever the
 * card itself offers: signalling a problem (lever 2 of ADR-079).
 *
 * Extracted from `JournalsSettings` so the section's render keeps every
 * branch about the portrait in one place, under the complexity cap (F011).
 * Nothing here is computed: the words, the date and the provenance are the
 * payload's.
 */

import { useState } from 'react';
import { Flag, UserSquare2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { PortraitProvenance } from '@/components/settings/PortraitProvenance';
import type { JournalPortrait } from '@/hooks/useJournals';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';

export type PortraitFormat = 'full' | 'brief';

export interface PortraitCardProps {
  /** The hook's own shape: undefined before the first read, null fields before a compilation. */
  portrait: JournalPortrait | null | undefined;
  lng: Language;
  /** Renders an ISO instant the way the section renders its other dates. */
  formatRelativeDate: (iso: string | null) => string;
  onSignal: () => void;
  signalDisabled: boolean;
}

export function PortraitCard({
  portrait,
  lng,
  formatRelativeDate,
  onSignal,
  signalDisabled,
}: PortraitCardProps) {
  const { t } = useTranslation(lng, 'translation');
  const [chosen, setFormat] = useState<PortraitFormat>('full');

  if (!portrait || (!portrait.full && !portrait.brief)) return null;

  // The shown format is one the portrait HAS at render time: a compilation may
  // publish a brief alone, an erasure may leave one, and the portrait arrives
  // after the mount — a choice frozen at the mount showed an empty body.
  const format: PortraitFormat = portrait[chosen] ? chosen : portrait.full ? 'full' : 'brief';

  const compiledLine = portrait.compiled_at
    ? t('journals.portraitCompiledAt', 'Compiled {{when}}', {
        when: formatRelativeDate(portrait.compiled_at),
      })
    : t('journals.portraitNeverCompiled', 'Not compiled yet');
  const text = format === 'full' ? portrait.full : portrait.brief;

  return (
    <div className="rounded-lg border bg-background p-3 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <UserSquare2 className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
          <div className="min-w-0">
            <div className="text-sm font-medium">
              {t('journals.portraitTitle', 'How LIA sees you')}
            </div>
            <div className="text-px-11 text-muted-foreground">{compiledLine}</div>
            {portrait.stale && (
              <div className="text-px-11 text-warning" data-testid="portrait-stale">
                {t(
                  'journals.portraitStale',
                  'A recompilation is pending: the text below may be dated.'
                )}
              </div>
            )}
          </div>
        </div>
        <div className="flex gap-1 shrink-0">
          <Button
            size="sm"
            variant={format === 'full' ? 'default' : 'outline'}
            className="h-7 text-xs"
            onClick={() => setFormat('full')}
            disabled={!portrait.full}
          >
            {t('journals.portraitFormatFull', 'Full')}
          </Button>
          <Button
            size="sm"
            variant={format === 'brief' ? 'default' : 'outline'}
            className="h-7 text-xs"
            onClick={() => setFormat('brief')}
            disabled={!portrait.brief}
          >
            {t('journals.portraitFormatBrief', 'Brief')}
          </Button>
        </div>
      </div>

      <p className="text-xs text-muted-foreground whitespace-pre-wrap leading-relaxed">
        {text ?? ''}
      </p>

      {portrait.sources && <PortraitProvenance provenance={portrait.sources} lng={lng} />}

      <p className="text-px-10 text-muted-foreground italic">
        {t(
          'journals.portraitTip',
          'The portrait is a living synthesis. To correct it: signal a problem, edit the L3 entries, or trigger a consolidation.'
        )}
      </p>

      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="outline"
          className="h-8 text-xs"
          onClick={onSignal}
          disabled={signalDisabled}
        >
          <Flag className="h-3.5 w-3.5 mr-1" />
          {t('journals.portraitFeedbackButton', 'Signal a problem')}
        </Button>
      </div>
    </div>
  );
}
