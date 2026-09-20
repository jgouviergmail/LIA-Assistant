'use client';

/**
 * The end-of-session card (ADR-299, spec A5): how the session ended, its
 * duration, the requests handed to LIA, the voice-only exchanges, and LIA's
 * own cost in the chat meter's vocabulary. The provider's tokens are never
 * here, by construction — the API never sends them. A DIRECT session
 * (ADR-300 wave 4) archived no exchange, so its body counts none; it says
 * instead what became of its words (ADR-301): relayed to the chat as the
 * person's own turn, or why not — the row is rewritten when that settles.
 *
 * When the relayed words could not become a turn (a busy thread, a pending
 * question, a ceiling, a failure), the card quotes their recap — the phone's
 * fallback push carries the same — so nothing said is lost in silence.
 *
 * Drawn in place of the row's Markdown (which stays the FALLBACK for a
 * channel or an export); the bubble's meter line under it repeats the token
 * detail for a person who displays tokens.
 */
import { AudioLines } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { fallbackLng, type Language } from '@/i18n/settings';
import { formatEuro } from '@/lib/format';
import { isLiveSummary, liveSummaryOf } from '@/lib/live/live-message';

export interface LiveSessionSummaryCardProps {
  metadata: Record<string, unknown> | undefined;
}

/** Renders nothing on any row that is not a live summary (hotspot CC rule). */
export function LiveSessionSummaryCard({ metadata }: LiveSessionSummaryCardProps) {
  const { t, i18n } = useTranslation();
  if (!isLiveSummary(metadata)) return null;
  const figures = liveSummaryOf(metadata);
  const minutes = Math.max(1, Math.round(figures.durationSeconds / 60));
  const cost = typeof metadata?.cost_eur === 'number' ? metadata.cost_eur : null;
  const locale = (i18n.language?.split('-')[0] as Language) || fallbackLng;
  return (
    <div className="flex flex-col gap-1 text-sm" data-testid="live-session-summary">
      <div className="flex flex-wrap items-center gap-2 font-semibold">
        <AudioLines className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        <span>{t('live.summary.title')}</span>
        {figures.outcome && (
          <span className="font-normal text-muted-foreground">
            · {t(`live.outcome.${figures.outcome}`)}
          </span>
        )}
      </div>
      <p className="text-muted-foreground">
        {figures.mode === 'direct'
          ? t('live.summary.body_direct', { minutes })
          : t('live.summary.body', {
              minutes,
              delegations: figures.delegations,
              voice_turns: figures.voiceTurns,
            })}
        {figures.extensions > 0 &&
          ` · ${t('live.summary.extended', { count: figures.extensions })}`}
      </p>
      {figures.mode === 'direct' && figures.relay && (
        <p className="text-muted-foreground" data-testid="live-session-relay">
          {t(`live.summary.relay.${figures.relay}`)}
        </p>
      )}
      {figures.mode === 'direct' && figures.relaySummary && (
        <blockquote
          className="border-l-2 border-primary/40 pl-2 italic text-muted-foreground"
          data-testid="live-session-recap"
        >
          {figures.relaySummary}
        </blockquote>
      )}
      <p className="text-xs text-muted-foreground">
        {cost === null
          ? t('live.summary.no_cost')
          : t('live.summary.cost', { amount: formatEuro(cost, 4, locale) })}
      </p>
    </div>
  );
}
