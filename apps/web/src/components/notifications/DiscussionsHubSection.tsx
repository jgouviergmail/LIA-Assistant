'use client';

/** The proactive discussions LIA opened, as one more received history of the hub (ADR-358).
 *
 * Its filtered display pages use the shared account-owned pagination lifecycle.
 * The assistant's native keyset reader retains its separate contract. */

import { useCallback, useState } from 'react';
import { MessagesSquare } from '@/lib/icons';
import { useTranslation } from 'react-i18next';
import { HubSection } from '@/components/notifications/HubSection';
import { NotificationHistoryItem } from '@/components/settings/NotificationHistoryList';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useApplicationResourceSync } from '@/hooks/useApplicationResourceSync';
import { useAuth } from '@/hooks/useAuth';
import { usePagedSection } from '@/hooks/usePagedSection';
import { alertParams, DEFAULT_ALERT_CRITERIA, type AlertDisplayQuery } from '@/lib/alert-query';
import { capabilityEnabled } from '@/lib/capability-state';
import {
  discussionOpeningPageSchema,
  type DiscussionOpeningPage,
} from '@/types/proactive-discussions';

interface Props {
  /** The hub's own count, known before the section is ever opened. */
  total: number | undefined;
  /** BCP-47 locale for dates. */
  locale: string;
  criteria?: AlertDisplayQuery;
  selected?: boolean;
}

export function DiscussionsHubSection(props: Props) {
  const { config } = useAppConfig();
  // Gate-keeper (ADR-061): a switched-off capability is never offered at all.
  if (!capabilityEnabled(config?.capabilities, 'proactive_discussions', false)) return null;
  return <OpeningsSection {...props} />;
}

/** One validated, account-owned page, read only while its selected section is open. */
function useHubOpenings(open: boolean, total: number | undefined, criteria: AlertDisplayQuery) {
  const { user } = useAuth();
  const query = usePagedSection<DiscussionOpeningPage, DiscussionOpeningPage['items'][number]>({
    path: '/proactive-discussions/openings',
    enabled: open,
    params: alertParams(criteria),
    parse: value => discussionOpeningPageSchema.parse(value),
    selectItems: value => value.items,
    selectTotal: value => value.total,
    selectAsOf: value => value.as_of ?? undefined,
  });
  const { refetch } = query;
  const refresh = useCallback(async () => {
    refetch();
  }, [refetch]);
  useApplicationResourceSync(user?.id, 'proactive_discussions', refresh);
  return {
    ...query,
    items: query.items ?? [],
    count: query.items === undefined ? (criteria.q.trim() ? undefined : total) : query.total,
  };
}

function OpeningsSection({
  total,
  locale,
  criteria = DEFAULT_ALERT_CRITERIA,
  selected = true,
}: Props) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const openings = useHubOpenings(open && selected, total, criteria);
  const formatter = new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
    ...(user?.timezone ? { timeZone: user.timezone } : {}),
  });
  return (
    <div hidden={!selected}>
      <HubSection
        icon={MessagesSquare}
        title={t('notifications_hub.sections.discussions.title')}
        subtitle={t('notifications_hub.sections.discussions.subtitle')}
        emptyLabel={t(
          criteria.q.trim()
            ? 'notifications_hub.filter.no_results'
            : 'notifications_hub.sections.discussions.empty'
        )}
        errorLabel={t('notifications_hub.sections.discussions.error')}
        total={openings.count}
        page={openings.page}
        totalPages={openings.totalPages}
        onPageChange={openings.setPage}
        onRetry={openings.refetch}
        firstLoad={openings.firstLoad}
        loading={openings.loading}
        error={openings.error}
        isEmpty={openings.items.length === 0}
        onOpenChange={setOpen}
      >
        <ul className="min-w-0 [overflow-wrap:anywhere]" role="list">
          {openings.items.map(item => (
            <NotificationHistoryItem
              key={item.id}
              row={{
                id: item.id,
                createdAt: item.created_at,
                content: item.content,
                // No state badge (owner request 2026-10-21): the date titles the
                // row and the words follow — the hub reads as a conversation log.
                chips: [],
              }}
              formatDate={instant => formatter.format(new Date(instant))}
              presentation="timeline"
            />
          ))}
        </ul>
      </HubSection>
    </div>
  );
}
