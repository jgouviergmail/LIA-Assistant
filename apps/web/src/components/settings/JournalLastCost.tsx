'use client';

import { useId } from 'react';
import { Settings2 } from 'lucide-react';
import { useTranslation } from '@/i18n/client';
import { getIntlLocale, type Language } from '@/i18n/settings';
import { Badge } from '@/components/ui/badge';
import { UsageLine, meterFigures } from '@/components/ui/usage-line';
import type { JournalCostInfo } from '@/hooks/useJournals';

/**
 * The journal's last background intervention, drawn like the last run of the
 * proactive discussions' « Context » panel (owner request 2026-10-21): a titled
 * line naming what ran and when, then the chat meter's own figures — the cache
 * reads apart from IN, exactly as the meter counts them.
 */
export function JournalLastCost({
  lng,
  cost,
  emoji,
}: {
  lng: Language;
  cost: JournalCostInfo;
  /** The source's glyph, the one the journal entries carry. */
  emoji: string;
}) {
  const { t } = useTranslation(lng);
  const titleId = useId();
  // The billing writes the snapshot whole: before it has, there is nothing to show.
  if (!cost.timestamp || cost.cost_eur == null) return null;
  const source = cost.source === 'extraction' ? 'extraction' : 'consolidation';
  return (
    <section
      aria-labelledby={titleId}
      className="min-w-0 space-y-2 rounded-lg border bg-background p-3"
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <h4 id={titleId} className="flex items-center gap-2 text-sm font-medium">
          <Settings2 className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
          {t('journals.lastCost')}
        </h4>
        {/* What ran and when wrap together, under the title when it is narrow. */}
        <span className="flex flex-wrap items-center gap-2">
          <Badge variant="default" icon={<span aria-hidden="true">{emoji}</span>}>
            {t(`journals.lastCostSources.${source}`)}
          </Badge>
          <time dateTime={cost.timestamp} className="text-xs tabular-nums text-muted-foreground">
            {new Date(cost.timestamp).toLocaleString(getIntlLocale(lng), {
              dateStyle: 'short',
              timeStyle: 'short',
            })}
          </time>
        </span>
      </div>
      <UsageLine
        // A journal intervention calls no Google service: its ledger row counts none.
        figures={meterFigures({
          tokens_in: cost.tokens_in ?? 0,
          tokens_out: cost.tokens_out ?? 0,
          tokens_cache: cost.tokens_cache ?? 0,
          google_requests: 0,
        })}
        cost={Number(cost.cost_eur)}
        decimals={6}
        className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs tabular-nums"
      />
    </section>
  );
}
