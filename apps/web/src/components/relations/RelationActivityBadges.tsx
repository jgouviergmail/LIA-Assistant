'use client';
import { Handshake, ListTodo, MessageSquare, PhoneCall } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { RelationSummary } from '@/hooks/useRelations';
export function RelationActivityBadges({ relation }: { relation: RelationSummary }) {
  const { t } = useTranslation();
  return (
    <>
      {(relation.is_peer ||
        relation.open_loops_count > 0 ||
        relation.calls_count > 0 ||
        relation.peer_messages_count > 0 ||
        (relation.sms_count ?? 0) > 0) && (
        <div className="ml-auto flex max-w-full flex-wrap justify-end gap-1.5 text-px-11">
          {relation.is_peer && (
            <span
              className="inline-flex shrink-0 items-center gap-0.5 rounded-full border border-primary/25 bg-primary/10 px-1.5 py-px text-px-9 font-semibold text-primary"
              title={t('relations.peer_badge_hint')}
            >
              <Handshake className="h-2.5 w-2.5" aria-hidden="true" />
              LIA
            </span>
          )}
          {/* amber-800, not -700: at 11px on the tinted background the -700
                pair measures 4.34:1, under the 4.5:1 AA floor (axe, production
                bundle). Same fix as the v1.27.0 pills. */}
          {relation.open_loops_count > 0 && (
            <span className="inline-flex max-w-full items-center gap-1 rounded-full border border-amber-500/25 bg-amber-500/10 px-2 py-0.5 font-medium text-amber-800 dark:text-amber-300">
              <ListTodo className="h-3 w-3" aria-hidden="true" />
              {t('relations.open_loops_count', { count: relation.open_loops_count })}
            </span>
          )}
          {(relation.sms_count ?? 0) > 0 && (
            <span className="inline-flex max-w-full items-center gap-1 rounded-full border border-primary/25 bg-primary/10 px-2 py-0.5 font-medium text-primary">
              <MessageSquare className="h-3 w-3" aria-hidden="true" />
              {t('relations.sms_count', { count: relation.sms_count })}
            </span>
          )}
          {relation.calls_count > 0 && (
            <span className="inline-flex max-w-full items-center gap-1 rounded-full border border-sky-500/25 bg-sky-500/10 px-2 py-0.5 font-medium text-sky-700 dark:text-sky-300">
              <PhoneCall className="h-3 w-3" aria-hidden="true" />
              {t('relations.calls_count', { count: relation.calls_count })}
            </span>
          )}
          {/* Primary tint: everything relayed through LIA shares the peers
                identity colour (the "LIA" badge above, the chat bubbles). */}
          {relation.peer_messages_count > 0 && (
            <span className="inline-flex max-w-full items-center gap-1 rounded-full border border-primary/25 bg-primary/10 px-2 py-0.5 font-medium text-primary">
              <MessageSquare className="h-3 w-3" aria-hidden="true" />
              {t('relations.peer_messages_count', { count: relation.peer_messages_count })}
            </span>
          )}
        </div>
      )}
    </>
  );
}
