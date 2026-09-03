'use client';

/**
 * The « minutes ready » card inside a proactive chat message (ADR-258).
 *
 * The dispatcher's content is already the title and the summary paragraph;
 * this block adds the facts the metadata carries, what the exchange cost when
 * the user displays costs (the transcription and the minutes are two paid
 * units — both are stated, with their sum), and the one action that matters:
 * open the minutes.
 */

import { ClipboardList, ExternalLink } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { formatEuro } from '@/lib/format';
import { formatElapsed } from '@/lib/meetings/format';
import type { MeetingNotificationMetadata } from '@/types/meetings';

interface MeetingMinutesCardProps {
  lng: Language;
  metadata: MeetingNotificationMetadata;
  /** The user's token-display preference: costs render only when it is on. */
  showCosts?: boolean;
}

/** A priced amount, or the localized « not priced » when the price is unknown. */
export function costLabel(
  value: number | null | undefined,
  lng: Language,
  unknown: string
): string {
  return value === null || value === undefined ? unknown : formatEuro(value, 4, lng);
}

/** Whether the metadata carries any cost fact worth a line. */
export function hasCostFacts(metadata: MeetingNotificationMetadata): boolean {
  return (
    metadata.cost_eur !== undefined ||
    metadata.stt_cost_eur !== undefined ||
    metadata.llm_cost_eur !== undefined
  );
}

export function MeetingMinutesCard({ lng, metadata, showCosts = false }: MeetingMinutesCardProps) {
  const { t } = useTranslation(lng);
  const router = useLocalizedRouter();
  const facts = [
    formatElapsed(metadata.duration_seconds),
    t('meetings.list.participants', { count: metadata.participants_count }),
    t('meetings.list.actions', { count: metadata.action_items_count }),
  ].join(' · ');
  const unknown = t('meetings.detail.cost_unknown');

  return (
    <div className="mt-3 flex flex-wrap items-center gap-3 rounded-md border border-border/60 bg-background/60 p-3">
      <ClipboardList className="h-5 w-5 text-primary" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{t('meetings.card.title')}</p>
        <p className="text-xs text-muted-foreground">{facts}</p>
        {metadata.template_name && (
          <p className="text-xs text-muted-foreground">
            {t('meetings.card.template', { name: metadata.template_name })}
          </p>
        )}
        {metadata.gaps > 0 && (
          <p className="text-xs text-warning">
            {t('meetings.detail.gaps_notice', { count: metadata.gaps })}
          </p>
        )}
        {showCosts && hasCostFacts(metadata) && (
          <p className="text-xs text-muted-foreground" data-testid="meeting-card-costs">
            {t('meetings.card.cost_line', {
              stt: costLabel(metadata.stt_cost_eur, lng, unknown),
              minutes: costLabel(metadata.llm_cost_eur, lng, unknown),
              total: costLabel(metadata.cost_eur, lng, unknown),
            })}
          </p>
        )}
      </div>
      <Button
        type="button"
        size="sm"
        variant="default"
        onClick={() => router.push(`/dashboard/meetings/${metadata.meeting_id}`)}
      >
        {t('meetings.card.open')}
        <ExternalLink className="ml-1 h-3.5 w-3.5" aria-hidden="true" />
      </Button>
    </div>
  );
}
