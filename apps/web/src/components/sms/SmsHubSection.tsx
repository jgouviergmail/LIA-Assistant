'use client';

import { useCallback, useState } from 'react';
import { MessageSquareText } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useAuth } from '@/hooks/useAuth';
import { HUB_PAGE_SIZE } from '@/hooks/usePagedSection';
import { useSmsArchive } from '@/hooks/useSmsArchive';
import { capabilityEnabled } from '@/lib/capability-state';
import { HubSection } from '@/components/notifications/HubSection';
import { NotificationHistoryItem } from '@/components/settings/NotificationHistoryList';
import type { Language } from '@/i18n/settings';

interface Props {
  lng: Language;
  total: number | null | undefined;
}

export function SmsHubSection(props: Props) {
  const { config } = useAppConfig();
  if (!capabilityEnabled(config?.capabilities, 'sms', config?.features.sms_enabled)) return null;
  return <AccountSmsSection {...props} />;
}

function AccountSmsSection(props: Props) {
  const { user } = useAuth();
  return <ReceivedSmsSection key={user?.id ?? 'signed-out'} {...props} />;
}

function ReceivedSmsSection({ lng, total }: Props) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [trail, setTrail] = useState<string[]>([]);
  const reset = useCallback(() => setTrail([]), []);
  const { data, loading, error, refresh } = useSmsArchive(
    { limit: HUB_PAGE_SIZE, cursor: trail.at(-1) },
    open,
    reset,
    true
  );
  const count = data?.total ?? total ?? undefined;
  const page = trail.length + 1;
  const formatter = new Intl.DateTimeFormat(lng, {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: user?.timezone || 'Europe/Paris',
  });
  const nextCursor = data?.next_cursor;
  return (
    <HubSection
      icon={MessageSquareText}
      title={t('sms.title')}
      subtitle={t('sms.description')}
      emptyLabel={t('sms.empty')}
      errorLabel={t('sms.unavailable')}
      total={count}
      page={page}
      totalPages={Math.max(page, Math.ceil((count ?? 0) / HUB_PAGE_SIZE))}
      onPageChange={next => {
        if (loading) return;
        if (next === page - 1) setTrail(value => value.slice(0, -1));
        else if (next === page + 1 && nextCursor) setTrail(value => [...value, nextCursor]);
      }}
      firstLoad={!data && !error}
      loading={loading}
      error={error}
      isEmpty={!data?.items.length}
      onOpenChange={value => {
        setOpen(value);
        if (!value) void refresh();
      }}
    >
      <ul className="min-w-0 [overflow-wrap:anywhere]" role="list">
        {data?.items.map(message => (
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
    </HubSection>
  );
}
