'use client';

import { useState, useCallback } from 'react';
import { useApplicationResourceSync } from '@/hooks/useApplicationResourceSync';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { useTranslation } from '@/i18n/client';
import { getIntlLocale, type Language } from '@/i18n/settings';
import { Button } from '@/components/ui/button';
import { DiscussionActions } from '@/components/chat/DiscussionActions';
import { DiscussionDetails } from './DiscussionDetails';
import { historyDateFormatter } from './NotificationHistoryList';
import {
  discussionOpeningPageSchema,
  type DiscussionOpeningPage,
} from '@/types/proactive-discussions';

export function DiscussionHistory({ lng, open }: { lng: Language; open: boolean }) {
  const { t } = useTranslation(lng);
  const [cursor, setCursor] = useState<string | undefined>();
  const query = useApplicationAccountQuery<DiscussionOpeningPage>(
    '/proactive-discussions/openings',
    'DiscussionHistory',
    open,
    undefined,
    { params: { limit: 10, ...(cursor ? { after_id: cursor } : {}) } }
  );
  const { refetch } = query;
  const refresh = useCallback(async () => {
    await refetch();
  }, [refetch]);
  useApplicationResourceSync(query.ownerId, 'proactive_discussions', refresh);
  const decoded = discussionOpeningPageSchema.safeParse(query.data);
  const data = decoded.success ? decoded.data : undefined;
  const formatDate = historyDateFormatter(getIntlLocale(lng));
  return (
    <div className="min-w-0 space-y-3" aria-busy={query.loading}>
      {query.loading && <p role="status">{t('common.loading')}</p>}
      {(query.error || (query.data && !data)) && (
        <p role="alert" className="text-sm text-destructive">
          {t('discussions.load_error')}
        </p>
      )}
      {data && (
        <>
          <p className="text-xs text-muted-foreground">
            {data.total === 0
              ? t('discussions.history_empty')
              : t('discussions.history_count', { count: data.total })}
          </p>
          <ol className="space-y-3">
            {data.items.map(item => (
              // The card surface: inside the nested panel the backgrounds
              // alternate, so its own « why » panel reads as nested again.
              <li key={item.id} className="min-w-0 space-y-2 rounded-lg border bg-card p-3">
                {/* The date and the hour in bold, as every row of the alerts
                    draws them (owner request 2026-10-21). */}
                <time
                  className="block text-xs font-bold tabular-nums text-muted-foreground"
                  dateTime={item.created_at}
                >
                  {formatDate(item.created_at)}
                </time>
                <p className="whitespace-pre-wrap break-words text-sm">{item.content}</p>
                <DiscussionActions
                  metadata={{
                    type: 'proactive_discussion',
                    discussion_id: item.id,
                    discussion_feedback: item.feedback,
                  }}
                />
                <DiscussionDetails lng={lng} id={item.id} />
              </li>
            ))}
          </ol>
          <div className="flex flex-wrap gap-2">
            {cursor && (
              <Button variant="outline" size="sm" onClick={() => setCursor(undefined)}>
                {t('discussions.first_page')}
              </Button>
            )}
            {data.next_cursor && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setCursor(data.next_cursor ?? undefined)}
              >
                {t('discussions.history_more')}
              </Button>
            )}
          </div>
        </>
      )}
    </div>
  );
}
