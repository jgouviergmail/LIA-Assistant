'use client';

/**
 * RelationCardList — the CRM overview (N-09): people ranked by recent
 * interaction, each opening their 360° view. Read-only; extracted from the
 * page to keep the page's complexity flat.
 */

import { Handshake, PhoneCall, Users } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { timeAgoLabel } from '@/lib/briefing-utils';
import type { RelationSummary } from '@/hooks/useRelations';

export function RelationCardList({
  relations,
  onOpen,
}: {
  relations: RelationSummary[];
  onOpen: (name: string) => void;
}) {
  const { t } = useTranslation();

  if (relations.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 py-12 text-center">
        <Users className="h-8 w-8 text-muted-foreground/50" aria-hidden="true" />
        <p className="text-sm text-muted-foreground">{t('relations.empty')}</p>
      </div>
    );
  }

  return (
    <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3" role="list">
      {relations.map(relation => (
        <li key={relation.display_name}>
          <button
            type="button"
            onClick={() => onOpen(relation.display_name)}
            className="w-full text-left rounded-xl border border-border/50 bg-card p-4 transition-all hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="truncate font-semibold text-foreground">
                {relation.display_name}
              </span>
              {relation.last_interaction_at && (
                <span className="shrink-0 text-[11px] text-muted-foreground">
                  {timeAgoLabel(t, relation.last_interaction_at)}
                </span>
              )}
            </div>
            <div className="mt-2 flex flex-wrap gap-3 text-xs text-muted-foreground">
              {relation.open_loops_count > 0 && (
                <span className="inline-flex items-center gap-1">
                  <Handshake className="h-3.5 w-3.5" aria-hidden="true" />
                  {t('relations.open_loops_count', { count: relation.open_loops_count })}
                </span>
              )}
              {relation.calls_count > 0 && (
                <span className="inline-flex items-center gap-1">
                  <PhoneCall className="h-3.5 w-3.5" aria-hidden="true" />
                  {t('relations.calls_count', { count: relation.calls_count })}
                </span>
              )}
            </div>
          </button>
        </li>
      ))}
    </ul>
  );
}
