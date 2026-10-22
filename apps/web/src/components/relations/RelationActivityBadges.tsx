'use client';
import { Handshake, ListTodo, MessageSquare, PhoneCall } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { RelationSummary } from '@/hooks/useRelations';

/**
 * One tone for every count of the card (owner request 2026-10-21): the icon
 * and the word tell the kinds apart, the colour only says « there is
 * something here ». The theme's primary, the peers' identity colour.
 */
const PILL =
  'inline-flex max-w-full items-center gap-1 rounded-full border border-primary/25 bg-primary/10 px-2 py-0.5 font-medium text-primary';

export function RelationActivityBadges({ relation }: { relation: RelationSummary }) {
  const { t } = useTranslation();
  return (
    <>
      {(relation.is_peer ||
        relation.open_loops_count > 0 ||
        relation.calls_count > 0 ||
        relation.peer_messages_count > 0 ||
        (relation.sms_count ?? 0) > 0) && (
        // At the foot of the card, on its right edge, whatever the name above holds.
        <div className="mt-auto flex max-w-full flex-wrap justify-end gap-1.5 self-end text-px-11">
          {relation.is_peer && (
            <span className={PILL} title={t('relations.peer_badge_hint')}>
              <Handshake className="h-3 w-3" aria-hidden="true" />
              LIA
            </span>
          )}
          {relation.open_loops_count > 0 && (
            <span className={PILL}>
              <ListTodo className="h-3 w-3" aria-hidden="true" />
              {t('relations.open_loops_count', { count: relation.open_loops_count })}
            </span>
          )}
          {(relation.sms_count ?? 0) > 0 && (
            <span className={PILL}>
              <MessageSquare className="h-3 w-3" aria-hidden="true" />
              {t('relations.sms_count', { count: relation.sms_count })}
            </span>
          )}
          {relation.calls_count > 0 && (
            <span className={PILL}>
              <PhoneCall className="h-3 w-3" aria-hidden="true" />
              {t('relations.calls_count', { count: relation.calls_count })}
            </span>
          )}
          {relation.peer_messages_count > 0 && (
            <span className={PILL}>
              <MessageSquare className="h-3 w-3" aria-hidden="true" />
              {t('relations.peer_messages_count', { count: relation.peer_messages_count })}
            </span>
          )}
        </div>
      )}
    </>
  );
}
