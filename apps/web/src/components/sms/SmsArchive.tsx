'use client';
import { useCallback, useState, type ReactNode } from 'react';
import { CalendarDays, MessageSquareText, Users } from '@/lib/icons';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/hooks/useAuth';
import { useSmsArchive } from '@/hooks/useSmsArchive';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { useApplicationResourceSync } from '@/hooks/useApplicationResourceSync';
import { FilterChip } from '@/components/ui/filter-chip';
import { SectionHeader } from '@/components/ui/section-header';
import { SmsSearchForm } from './SmsSearchForm';
import { SmsArchiveActions } from './SmsArchiveActions';
import { SmsArchiveResults, SmsArchivePager } from './SmsArchiveResults';
import type { SmsQuery, SmsSenderPage } from '@/types/sms';
import type { Language } from '@/i18n/settings';
interface Props {
  lng: Language;
  heading?: boolean;
  limit?: number;
  enabled?: boolean;
  renderResults?: (content: ReactNode) => ReactNode;
  onFiltersChange?: () => void;
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
/** Own filters, cursor invalidation and the mutually exclusive archive queries. */
function useArchiveState(limit: number, enabled: boolean) {
  const { user } = useAuth();
  const [mode, setMode] = useState<'day' | 'sender'>('sender');
  const [filters, setFilters] = useState<SmsQuery>({});
  const [trail, setTrail] = useState<string[]>([]);
  const cursor = trail.at(-1);
  const filtered = !!(filters.query || filters.from_ts || filters.to_ts);
  const queryMessages = mode === 'day' || filtered;
  const resetCursor = useCallback(() => setTrail([]), []);
  const list = useSmsArchive({ ...filters, cursor, limit }, enabled && queryMessages, resetCursor);
  const senders = useApplicationAccountQuery<SmsSenderPage>(
    '/sms/senders',
    'SmsArchive',
    enabled && !queryMessages,
    undefined,
    { params: { limit, cursor } }
  );
  const { refetch, acceptData } = senders;
  // Re-read in place: the senders in view stay until the first page lands —
  // emptied first, the list unmounted under the reader, closed every open
  // sender and dropped the focus a deletion meant to restore (owner rule
  // 2026-10-21). Back to the first page: a cursor is bound to the revision.
  const refreshSenders = useCallback(async () => {
    if (queryMessages || !enabled) return;
    setTrail([]);
    if (cursor) return;
    try {
      await refetch();
    } catch (error) {
      // A reread that failed cannot vouch for the list it was replacing.
      acceptData(undefined);
      throw error;
    }
  }, [queryMessages, refetch, acceptData, cursor, enabled]);
  useApplicationResourceSync(user?.id, 'sms', refreshSenders);
  return {
    projection: archiveProjection(queryMessages, list, senders),
    mode,
    filtered,
    hasPrevious: trail.length > 0,
    changeFilters: (query: SmsQuery) => {
      setFilters(query);
      setTrail([]);
    },
    changeMode: (value: 'day' | 'sender') => {
      setMode(value);
      setTrail([]);
    },
    previous: () => setTrail(value => value.slice(0, -1)),
    next: (cursor: string) => setTrail(value => [...value, cursor]),
    refresh: queryMessages ? list.refresh : refreshSenders,
  };
}

function AccountSmsArchive({
  lng,
  heading = true,
  limit = 20,
  enabled = true,
  renderResults,
  onFiltersChange,
}: Props) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const timezone = user?.timezone || 'Europe/Paris';
  const archive = useArchiveState(limit, enabled);
  const { current, loading, ...content } = archive.projection;
  const results = (
    <>
      <SmsArchiveResults
        {...content}
        mode={archive.mode}
        loading={loading}
        lng={lng}
        timezone={timezone}
      />
      <SmsArchivePager
        loading={loading}
        hasPrevious={archive.hasPrevious}
        nextCursor={current?.next_cursor}
        onPrevious={archive.previous}
        onNext={archive.next}
      />
    </>
  );
  return (
    <section className="min-w-0 space-y-5" aria-label={t('sms.title')} aria-busy={loading}>
      {heading && (
        <SectionHeader
          title={t('sms.title')}
          description={t('sms.description')}
          icon={MessageSquareText}
          level={1}
          actions={
            <SmsArchiveActions
              refreshing={loading}
              onRefresh={() => void archive.refresh().catch(() => {})}
            />
          }
          accessory={
            current ? (
              <span className="text-sm text-muted-foreground">
                {current.total.toLocaleString(lng)}
              </span>
            ) : undefined
          }
        />
      )}
      <SmsSearchForm
        timezone={timezone}
        filtered={archive.filtered}
        onChange={query => {
          archive.changeFilters(query);
          onFiltersChange?.();
        }}
        chips={(['day', 'sender'] as const).map(value => (
          <FilterChip
            key={value}
            active={archive.mode === value}
            label={t(`sms.by_${value}`)}
            icon={value === 'day' ? CalendarDays : Users}
            onToggle={() => {
              archive.changeMode(value);
              onFiltersChange?.();
            }}
          />
        ))}
      />
      {renderResults ? renderResults(results) : results}
    </section>
  );
}
