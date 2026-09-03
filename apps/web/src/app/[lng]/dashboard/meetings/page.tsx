'use client';

/**
 * The user's meetings (ADR-258): every recording and where its minutes stand.
 */

import { useState } from 'react';
import { ClipboardList, MessageSquare } from 'lucide-react';

import { MeetingStatusBadge } from '@/components/meetings/MeetingStatusBadge';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { LoadingAnnouncement } from '@/components/ui/loading-announcement';
import { Skeleton } from '@/components/ui/skeleton';
import { useLanguageParam } from '@/hooks/useLanguageParam';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import { useMeetingList } from '@/hooks/useMeetings';
import { useTranslation } from '@/i18n/client';
import { formatEuro } from '@/lib/format';
import { formatElapsed } from '@/lib/meetings/format';

const PAGE_SIZE = 20;

interface MeetingsPageProps {
  params: Promise<{ lng: string }>;
}

export default function MeetingsPage({ params }: MeetingsPageProps) {
  const lng = useLanguageParam(params);
  const { t } = useTranslation(lng);
  const router = useLocalizedRouter();
  const [offset, setOffset] = useState(0);
  const { meetings, total, isLoading, isUnavailable } = useMeetingList(PAGE_SIZE, offset);

  const dateFormat = new Intl.DateTimeFormat(lng, { dateStyle: 'medium', timeStyle: 'short' });

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
            <ClipboardList className="h-6 w-6 text-primary" aria-hidden="true" />
            {t('meetings.list.title')}
          </h1>
          <p className="text-sm text-muted-foreground">{t('meetings.list.subtitle')}</p>
        </div>
        {total > 0 && (
          <p className="text-sm text-muted-foreground">
            {t('meetings.list.total', { count: total })}
          </p>
        )}
      </header>

      {isLoading ? (
        <div className="space-y-3">
          <LoadingAnnouncement />
          {[1, 2, 3].map(i => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : isUnavailable || meetings.length === 0 ? (
        <EmptyState
          variant="page"
          icon={ClipboardList}
          title={t('meetings.list.empty_title')}
          description={t('meetings.list.empty_description')}
          reason="no-data"
          action={{
            label: t('meetings.list.empty_action'),
            onClick: () => router.push('/dashboard/chat'),
            icon: MessageSquare,
          }}
        />
      ) : (
        <ul className="divide-y divide-border/60 rounded-lg border border-border/60 bg-card/60">
          {meetings.map(meeting => {
            const title = meeting.title ?? t('meetings.list.untitled');
            return (
              <li key={meeting.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                <button
                  type="button"
                  className="min-w-0 flex-1 text-left"
                  aria-label={t('meetings.list.open', { title })}
                  onClick={() => router.push(`/dashboard/meetings/${meeting.id}`)}
                >
                  <span className="block truncate font-medium hover:underline">{title}</span>
                  <span className="block text-xs text-muted-foreground">
                    {dateFormat.format(new Date(meeting.started_at))}
                    {meeting.audio_duration_seconds
                      ? ` · ${formatElapsed(meeting.audio_duration_seconds)}`
                      : ''}
                    {meeting.status === 'ready' &&
                      ` · ${t('meetings.list.participants', { count: meeting.participants_count })} · ${t(
                        'meetings.list.actions',
                        { count: meeting.action_items_count }
                      )}`}
                    {/* What the meeting cost, when anything priced was spent. */}
                    {meeting.total_cost_eur !== null &&
                      meeting.total_cost_eur > 0 &&
                      ` · ${formatEuro(meeting.total_cost_eur, 4, lng)}`}
                  </span>
                </button>
                <MeetingStatusBadge lng={lng} status={meeting.status} stage={meeting.stage} />
              </li>
            );
          })}
        </ul>
      )}

      {total > PAGE_SIZE && (
        <nav className="flex items-center justify-between" aria-label={t('common.pagination')}>
          <Button
            type="button"
            variant="outline"
            size="sm"
            aria-disabled={offset === 0}
            onClick={() => offset > 0 && setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            {t('common.previous')}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            aria-disabled={offset + PAGE_SIZE >= total}
            onClick={() => offset + PAGE_SIZE < total && setOffset(offset + PAGE_SIZE)}
          >
            {t('common.next')}
          </Button>
        </nav>
      )}
    </div>
  );
}
