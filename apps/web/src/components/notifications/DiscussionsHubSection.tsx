'use client';

/** The proactive discussions LIA opened, as one more received history of the hub (ADR-358).
 *
 * Its own read and cursor trail, like the SMS section: the openings page is
 * keyset-paginated, and the hub's badge comes from the same filter server-side,
 * so the folded total and the unfolded page never disagree. */

import { useCallback, useState } from 'react';
import { MessagesSquare } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { HubSection } from '@/components/notifications/HubSection';
import { NotificationHistoryItem } from '@/components/settings/NotificationHistoryList';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { useApplicationResourceSync } from '@/hooks/useApplicationResourceSync';
import { useAuth } from '@/hooks/useAuth';
import { HUB_PAGE_SIZE } from '@/hooks/usePagedSection';
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
}

export function DiscussionsHubSection(props: Props) {
  const { config } = useAppConfig();
  // Gate-keeper (ADR-061): a switched-off capability is never offered at all.
  if (!capabilityEnabled(config?.capabilities, 'proactive_discussions', false)) return null;
  return <OpeningsSection {...props} />;
}

/** One page of openings at a time, read only while the section is open. */
function useHubOpenings(open: boolean, total: number | undefined) {
  const [trail, setTrail] = useState<string[]>([]);
  const cursor = trail.at(-1);
  const query = useApplicationAccountQuery<DiscussionOpeningPage>(
    '/proactive-discussions/openings',
    'DiscussionsHubSection',
    open,
    undefined,
    { params: { limit: HUB_PAGE_SIZE, ...(cursor ? { after_id: cursor } : {}) } }
  );
  const { refetch, ownerId } = query;
  const refresh = useCallback(async () => {
    await refetch();
  }, [refetch]);
  useApplicationResourceSync(ownerId, 'proactive_discussions', refresh);
  const decoded = discussionOpeningPageSchema.safeParse(query.data);
  const data = decoded.success ? decoded.data : undefined;
  const count = data?.total ?? total;
  const page = trail.length + 1;
  const nextCursor = data?.next_cursor ?? undefined;
  const turn = (next: number) => {
    if (query.loading) return;
    if (next === page - 1) setTrail(value => value.slice(0, -1));
    else if (next === page + 1 && nextCursor) setTrail(value => [...value, nextCursor]);
  };
  const malformed = query.data !== undefined && !decoded.success;
  return {
    items: data?.items ?? [],
    count,
    page,
    totalPages: Math.max(page, Math.ceil((count ?? 0) / HUB_PAGE_SIZE)),
    turn,
    loading: query.loading,
    firstLoad: query.data === undefined && !query.error,
    error: query.error ?? (malformed ? new Error('Malformed openings page') : null),
  };
}

function OpeningsSection({ total, locale }: Props) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const openings = useHubOpenings(open, total);
  const formatter = new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
    ...(user?.timezone ? { timeZone: user.timezone } : {}),
  });
  return (
    <HubSection
      icon={MessagesSquare}
      title={t('notifications_hub.sections.discussions.title')}
      subtitle={t('notifications_hub.sections.discussions.subtitle')}
      emptyLabel={t('notifications_hub.sections.discussions.empty')}
      errorLabel={t('notifications_hub.sections.discussions.error')}
      total={openings.count}
      page={openings.page}
      totalPages={openings.totalPages}
      onPageChange={openings.turn}
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
  );
}
