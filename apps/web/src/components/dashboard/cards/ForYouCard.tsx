'use client';

import Link from 'next/link';
import { Sparkles } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { BriefingCard } from '../BriefingCard';
import { chatDraftHref } from '@/lib/briefing-utils';
import type { CardSection, ForYouData } from '@/types/briefing';

interface ForYouCardProps {
  section: CardSection<ForYouData>;
  isRefreshing: boolean;
  onRefresh: () => void;
  staggerIndex?: number;
}

/**
 * « For you » card (P15, interdomain program Lot 4).
 *
 * Aggregates the commitments ledger (open loops, ADR-139) and the
 * automations digest (ADR-140): what ran in the last 24 h and what runs
 * next. Loop rows deep-link to the chat prefilled with a direction-aware
 * intent (QW-9 `?draft=` mechanism) — nothing is auto-sent.
 */
export function ForYouCard({ section, isRefreshing, onRefresh, staggerIndex }: ForYouCardProps) {
  const router = useRouter();
  const { i18n } = useTranslation();
  const lng = (i18n.language || 'fr').split('-')[0];
  return (
    <BriefingCard<ForYouData>
      titleKey="dashboard.briefing.cards.for_you.title"
      icon={<Sparkles className="h-5 w-5" />}
      tone="fuchsia"
      section={section}
      isRefreshing={isRefreshing}
      onRefresh={onRefresh}
      emptyStateKey="dashboard.briefing.cards.for_you.empty"
      renderContent={data => (
        <ForYouContent data={data} onOpenChat={draft => router.push(chatDraftHref(lng, draft))} />
      )}
      staggerIndex={staggerIndex}
    />
  );
}

function ForYouContent({
  data,
  onOpenChat,
}: {
  data: ForYouData;
  onOpenChat: (draft: string) => void;
}) {
  const { t, i18n } = useTranslation();
  const lng = (i18n.language || 'fr').split('-')[0];
  return (
    <div className="space-y-3">
      {data.open_loops.length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">
            {/* UXR Lot 7 (B5): the heading opens the full ledger view. */}
            <Link
              href={`/${lng}/dashboard/settings`}
              className="hover:text-primary hover:underline"
            >
              {t('dashboard.briefing.cards.for_you.loops_title')}
            </Link>
          </p>
          <ul className="space-y-0.5" role="list">
            {data.open_loops.map(loop => {
              const intent = t(
                loop.direction === 'waiting_on_other'
                  ? 'dashboard.briefing.intents.loop_waiting'
                  : 'dashboard.briefing.intents.loop_owed',
                { subject: loop.subject }
              );
              return (
                <li key={loop.id}>
                  <button
                    type="button"
                    onClick={() => onOpenChat(intent)}
                    aria-label={intent}
                    className="w-full text-left flex items-baseline justify-between gap-2 text-sm rounded-md px-1.5 py-1 -mx-1.5 hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <span className="text-foreground/90 truncate font-medium">{loop.subject}</span>
                    <span className="shrink-0 text-xs text-fuchsia-600 dark:text-fuchsia-300 tabular-nums">
                      {t('dashboard.briefing.cards.for_you.days_open', {
                        count: loop.days_open,
                      })}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {(data.recent_automations.length > 0 || data.next_automation) && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">
            {t('dashboard.briefing.cards.for_you.automations_title')}
          </p>
          <ul className="space-y-0.5 text-sm" role="list">
            {data.recent_automations.map(auto => (
              <li key={auto.id} className="flex items-baseline justify-between gap-2">
                <span className="text-foreground/90 truncate">{auto.title}</span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {t('dashboard.briefing.cards.for_you.ran_recently')}
                </span>
              </li>
            ))}
            {data.next_automation && (
              <li className="flex items-baseline justify-between gap-2">
                <span className="text-foreground/90 truncate">{data.next_automation.title}</span>
                <span className="shrink-0 text-xs font-semibold text-fuchsia-600 dark:text-fuchsia-300 tabular-nums">
                  {/* Precise backend-formatted execution time; label fallback
                      keeps older cached payloads rendering. */}
                  {data.next_automation.next_trigger_local ??
                    t('dashboard.briefing.cards.for_you.next_up')}
                </span>
              </li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
