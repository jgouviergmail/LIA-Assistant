'use client';
import { useCallback, useState } from 'react';
import { MessageSquareText } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/hooks/useAuth';
import { useSmsArchive } from '@/hooks/useSmsArchive';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { useApplicationResourceSync } from '@/hooks/useApplicationResourceSync';
import { Button } from '@/components/ui/button';
import { SectionHeader } from '@/components/ui/section-header';
import { SmsSearchForm } from './SmsSearchForm';
import { SmsArchiveResults, SmsArchivePager } from './SmsArchiveResults';
import type { SmsQuery, SmsSenderPage } from '@/types/sms';
import type { Language } from '@/i18n/settings';
interface Props {
  lng: Language;
  heading?: boolean;
  limit?: number;
}
export function SmsArchive(props: Props) {
  const { user } = useAuth();
  return <AccountSmsArchive key={user?.id ?? 'signed-out'} {...props} />;
}
function archiveProjection(
  queryMessages: boolean,
  list: ReturnType<typeof useSmsArchive>,
  senders: ReturnType<typeof useApplicationAccountQuery<SmsSenderPage>>
) {
  if (queryMessages)
    return {
      current: list.data,
      loading: list.loading,
      error: list.error,
      messages: list.data,
      senders: undefined,
    };
  return {
    current: senders.data,
    loading: senders.loading,
    error: senders.error,
    messages: null,
    senders: senders.data,
  };
}
function AccountSmsArchive({ lng, heading = true, limit = 20 }: Props) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const timezone = user?.timezone || 'Europe/Paris';
  const [mode, setMode] = useState<'day' | 'sender'>('day');
  const [filters, setFilters] = useState<SmsQuery>({});
  const [trail, setTrail] = useState<string[]>([]);
  const cursor = trail.at(-1);
  const filtered = !!(filters.query || filters.from_ts || filters.to_ts);
  const queryMessages = mode === 'day' || filtered;
  const resetCursor = useCallback(() => setTrail([]), []);
  const list = useSmsArchive({ ...filters, cursor, limit }, queryMessages, resetCursor);
  const senders = useApplicationAccountQuery<SmsSenderPage>(
    '/sms/senders',
    'SmsArchive',
    !queryMessages,
    undefined,
    { params: { limit, cursor } }
  );
  const { refetch, setData } = senders;
  const refreshSenders = useCallback(async () => {
    if (queryMessages) return;
    setData(undefined);
    setTrail([]);
    if (!cursor) await refetch();
  }, [queryMessages, setData, refetch, cursor]);
  useApplicationResourceSync(user?.id, 'sms', refreshSenders);
  const { current, loading, ...content } = archiveProjection(queryMessages, list, senders);
  const changeFilters = (query: SmsQuery) => {
    setFilters(query);
    setTrail([]);
  };
  return (
    <section className="min-w-0 space-y-5" aria-label={t('sms.title')} aria-busy={loading}>
      {heading && (
        <SectionHeader
          title={t('sms.title')}
          description={t('sms.description')}
          icon={MessageSquareText}
          level={1}
          accessory={
            current ? (
              <span className="text-sm text-muted-foreground">
                {current.total.toLocaleString(lng)}
              </span>
            ) : undefined
          }
        />
      )}
      <SmsSearchForm timezone={timezone} filtered={filtered} onChange={changeFilters} />
      <div className="flex flex-wrap gap-2">
        {(['day', 'sender'] as const).map(value => (
          <Button
            key={value}
            variant={mode === value ? 'default' : 'outline'}
            aria-pressed={mode === value}
            onClick={() => {
              setMode(value);
              setTrail([]);
            }}
          >
            {t(`sms.by_${value}`)}
          </Button>
        ))}
        <Button
          variant="ghost"
          onClick={() => {
            void (queryMessages ? list.refresh() : refreshSenders()).catch(() => {});
          }}
        >
          {t('common.refresh')}
        </Button>
      </div>
      <SmsArchiveResults {...content} mode={mode} loading={loading} lng={lng} timezone={timezone} />
      <SmsArchivePager
        loading={loading}
        hasPrevious={trail.length > 0}
        nextCursor={current?.next_cursor}
        onPrevious={() => setTrail(value => value.slice(0, -1))}
        onNext={next => setTrail(value => [...value, next])}
      />
    </section>
  );
}
