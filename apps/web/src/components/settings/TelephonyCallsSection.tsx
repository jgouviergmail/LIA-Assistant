'use client';

/** Recent calls: a bounded chronological index, with factual times and reviewable chat drafts. */
import { useId, useRef, useState } from 'react';
import { PhoneCall, RefreshCw } from 'lucide-react';
import { useSearchParams } from 'next/navigation';
import { useTranslation } from '@/i18n/client';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { TimelineDayGroup } from '@/components/ui/timeline-group';
import { CallHistoryRow } from '@/components/telephony/CallHistoryRow';
import { FocusedCall } from '@/components/telephony/FocusedCall';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { useAuth } from '@/hooks/useAuth';
import { useTelephonyCalls } from '@/hooks/useTelephonyCalls';
import { projectCallTimeline } from '@/lib/telephony/timeline';
import type { BaseSettingsProps } from '@/types/settings';

const RECENT_CALLS_LIMIT = 10;

/** Changing accounts also resets expanded rows and the local manual-refresh lock. */
export default function TelephonyCallsSection(props: BaseSettingsProps) {
  const { user } = useAuth();
  return <CallHistory key={user?.id ?? 'anonymous'} {...props} />;
}

function CallHistoryToolbar({
  lng,
  count,
  loading,
  error,
  refreshing,
  onRefresh,
}: {
  lng: BaseSettingsProps['lng'];
  count: number;
  loading: boolean;
  error: Error | null;
  refreshing: boolean;
  onRefresh: () => void;
}) {
  const { t } = useTranslation(lng);
  return (
    <div className="flex min-w-0 flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0 space-y-1 text-sm text-muted-foreground">
        <p>{t('settings.telephony.calls.timeline_hint')}</p>
        {count > 0 && (
          <p className="text-xs tabular-nums">{t('settings.telephony.calls.count', { count })}</p>
        )}
      </div>
      {!loading && (
        <Button
          variant={error ? 'outline' : 'default'}
          onClick={onRefresh}
          aria-disabled={refreshing}
          aria-busy={refreshing || undefined}
          className="min-h-11 max-w-full shrink-0 whitespace-normal text-left sm:min-h-9"
        >
          <RefreshCw
            className={refreshing ? 'animate-spin motion-reduce:animate-none' : undefined}
            aria-hidden="true"
          />
          {t(error ? 'common.retry' : 'settings.telephony.calls.refresh')}
        </Button>
      )}
    </div>
  );
}

function CallHistory({ lng }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const id = useId();
  const { calls, hasActiveCall, isLoading, isUnavailable, error, refetch } = useTelephonyCalls(
    true,
    RECENT_CALLS_LIMIT
  );
  const [refreshing, setRefreshing] = useState(false);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const pending = useRef(false);
  const refresh = async () => {
    if (pending.current) return;
    pending.current = true;
    setRefreshing(true);
    setRefreshVersion(value => value + 1);
    try {
      await refetch();
    } finally {
      pending.current = false;
      setRefreshing(false);
    }
  };
  const linkedId = useSearchParams().get('call');
  const focused =
    linkedId && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(linkedId)
      ? linkedId.toLowerCase()
      : null;
  const { days } = projectCallTimeline(
    calls.filter(call => call.id !== focused),
    lng
  );
  if (isUnavailable || (!focused && !isLoading && !error && calls.length === 0)) return null;
  return (
    <SettingsSection
      value="telephony-calls"
      title={t('settings.telephony.calls.title')}
      description={t('settings.telephony.calls.description')}
      icon={PhoneCall}
    >
      <div aria-live="polite" className="sr-only">
        {hasActiveCall ? t('settings.telephony.calls.in_flight') : ''}
      </div>
      <div className="space-y-5">
        <CallHistoryToolbar
          lng={lng}
          count={calls.length}
          loading={isLoading}
          error={error}
          refreshing={refreshing}
          onRefresh={() => void refresh()}
        />
        {error && (
          <p
            role="alert"
            className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-foreground"
          >
            {t(
              calls.length
                ? 'settings.telephony.calls.refresh_error'
                : 'settings.telephony.calls.load_error'
            )}
          </p>
        )}
        {isLoading && <Skeleton className="h-28 w-full rounded-xl" label={t('common.loading')} />}
        {focused && (
          <FocusedCall
            key={focused}
            callId={focused}
            lng={lng}
            currentCall={calls.find(call => call.id === focused)}
            refreshVersion={refreshVersion}
          />
        )}
        {days.map(day => (
          <TimelineDayGroup
            key={day.id}
            headingId={`${id}-${day.id}`}
            heading={day.label ?? t('settings.telephony.calls.unknown_date')}
            dayNumber={day.dayNumber}
            month={day.month}
            level={4}
          >
            <ul className="divide-y divide-border">
              {day.entries.map(entry => (
                <CallHistoryRow key={entry.call.id} entry={entry} lng={lng} />
              ))}
            </ul>
          </TimelineDayGroup>
        ))}
      </div>
    </SettingsSection>
  );
}
