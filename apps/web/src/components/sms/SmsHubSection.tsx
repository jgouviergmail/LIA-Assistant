'use client';

import { useCallback, useState } from 'react';
import { MessageSquareText } from '@/lib/icons';
import { useTranslation } from 'react-i18next';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useAuth } from '@/hooks/useAuth';
import { HUB_PAGE_SIZE } from '@/hooks/usePagedSection';
import { useSmsArchive } from '@/hooks/useSmsArchive';
import { smsAvailable } from '@/lib/sms/availability';
import { HubSection } from '@/components/notifications/HubSection';
import { NotificationHistoryItem } from '@/components/settings/NotificationHistoryList';
import { DEFAULT_ALERT_CRITERIA, type AlertDisplayQuery } from '@/lib/alert-query';
import { smsReadErrorKey } from '@/lib/sms/read-error';
import { SmsSearchForm } from './SmsSearchForm';
import type { SmsMessage, SmsQuery } from '@/types/sms';
import type { Language } from '@/i18n/settings';

interface Props {
  lng: Language;
  criteria?: AlertDisplayQuery;
  selected?: boolean;
  total: number | null | undefined;
}

export function SmsHubSection(props: Props) {
  const { config } = useAppConfig();
  if (!smsAvailable(config)) return null;
  return <AccountSmsSection {...props} />;
}

function AccountSmsSection(props: Props) {
  const { user } = useAuth();
  return <ReceivedSmsSection key={user?.id ?? 'signed-out'} {...props} />;
}

/** Opaque cursors are scoped to a single filter generation, including A → B → A. */
function useSmsPages(
  criteria: AlertDisplayQuery,
  enabled: boolean,
  period: Pick<SmsQuery, 'from_ts' | 'to_ts'>
) {
  const criteriaKey = JSON.stringify([criteria.q, criteria.sort, period]);
  const [position, setPosition] = useState<{ scope: { key: string }; trail: string[] }>({
    scope: { key: criteriaKey },
    trail: [],
  });
  if (position.scope.key !== criteriaKey) setPosition({ scope: { key: criteriaKey }, trail: [] });
  const { trail, scope } = position;
  const setTrail = (next: string[]) =>
    setPosition(current => (current.scope === scope ? { ...current, trail: next } : current));
  const reset = useCallback(() => setPosition(current => ({ ...current, trail: [] })), []);
  const archive = useSmsArchive(
    { limit: HUB_PAGE_SIZE, cursor: trail.at(-1), query: criteria.q || undefined, ...period },
    enabled,
    reset,
    true,
    { sort: criteria.sort || 'recent' }
  );
  const { data, pageCursor, loading, error, retry } = archive;
  const page = pageCursor ? trail.indexOf(pageCursor) + 2 : 1;
  const nextCursor = data?.next_cursor;
  const turn = (next: number) => {
    if (loading) return;
    if (next === page - 1) setTrail(trail.slice(0, next - 1));
    else if (next === page + 1 && nextCursor) {
      if (trail.at(-1) === nextCursor && error) retry();
      else setTrail([...trail.slice(0, page - 1), nextCursor]);
    }
  };
  return { ...archive, page, turn, reset };
}

/** A filtered collection must never borrow an unfiltered counter from the hub. */
function smsCount(reported: number | undefined, total: Props['total'], searched: boolean) {
  if (reported !== undefined) return reported;
  return searched ? undefined : (total ?? undefined);
}

function hasSmsFilter(
  criteria: AlertDisplayQuery,
  period: Pick<SmsQuery, 'from_ts' | 'to_ts'>
): boolean {
  return Boolean(criteria.q.trim() || period.from_ts || period.to_ts);
}

function ReceivedSmsSection({
  lng,
  total,
  criteria = DEFAULT_ALERT_CRITERIA,
  selected = true,
}: Props) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [period, setPeriod] = useState<Pick<SmsQuery, 'from_ts' | 'to_ts'>>({});
  const { data, loading, error, refresh, page, turn, reset } = useSmsPages(
    criteria,
    open && selected,
    period
  );
  const searched = hasSmsFilter(criteria, period);
  const count = smsCount(data?.total, total, searched);
  const timezone = user?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone;
  const formatter = new Intl.DateTimeFormat(lng, {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: timezone,
  });
  return (
    <div hidden={!selected}>
      <HubSection
        icon={MessageSquareText}
        title={t('sms.title')}
        subtitle={t('sms.description')}
        emptyLabel={t(searched ? 'notifications_hub.filter.no_results' : 'sms.empty')}
        errorLabel={t(smsReadErrorKey(error))}
        onRetry={() => void refresh()}
        controls={
          <div className="mb-4">
            <SmsSearchForm
              searchable={false}
              surface="nested"
              timezone={timezone}
              filtered={Boolean(period.from_ts || period.to_ts)}
              onChange={({ from_ts, to_ts }) => setPeriod({ from_ts, to_ts })}
            />
          </div>
        }
        total={count}
        page={page}
        totalPages={Math.max(page, Math.ceil((count ?? 0) / HUB_PAGE_SIZE))}
        onPageChange={turn}
        firstLoad={data === null && loading}
        loading={loading}
        error={error}
        isEmpty={!data?.items.length}
        onOpenChange={value => {
          setOpen(value);
          if (!value) reset();
        }}
      >
        <SmsRows items={data?.items ?? []} formatter={formatter} />
      </HubSection>
    </div>
  );
}

function SmsRows({ items, formatter }: { items: SmsMessage[]; formatter: Intl.DateTimeFormat }) {
  return (
    <ul className="min-w-0 [overflow-wrap:anywhere]" role="list">
      {items.map(message => (
        <NotificationHistoryItem
          key={message.id}
          row={{
            id: message.id,
            createdAt: message.received_at,
            content: message.body,
            badge: { label: message.display_name, tone: 'default' },
            chips: [],
          }}
          formatDate={instant => formatter.format(new Date(instant))}
          presentation="timeline"
          // The sender leads the message's own words (owner request
          // 2026-10-21): the date titles the row, the badge opens the SMS.
          badgePlacement="content"
        />
      ))}
    </ul>
  );
}
