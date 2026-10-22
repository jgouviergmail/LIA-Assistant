'use client';

import { useEffect, useId, useRef } from 'react';
import { useTranslation } from '@/i18n/client';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { TimelineDayGroup } from '@/components/ui/timeline-group';
import { CallHistoryRow } from './CallHistoryRow';
import { projectCallTimeline } from '@/lib/telephony/timeline';
import type { TelephonyCallSummary } from '@/types/telephony';
import type { Language } from '@/i18n/settings';

/** The linked call is independent of the bounded recent page. */
export function FocusedCall({
  callId,
  lng,
  currentCall,
  refreshVersion,
}: {
  callId: string;
  lng: Language;
  currentCall?: TelephonyCallSummary;
  refreshVersion: number;
}) {
  const { t } = useTranslation(lng);
  const id = useId();
  const {
    data: fetched,
    error,
    loading,
    refetch,
  } = useApplicationAccountQuery<TelephonyCallSummary>(
    `/telephony/calls/${encodeURIComponent(callId)}`,
    'FocusedCall',
    !currentCall,
    undefined,
    { deps: [refreshVersion] }
  );
  const data = currentCall ?? fetched;
  const summary = useRef<HTMLElement>(null);
  const origin = useRef<Element | null>(null);
  const focused = useRef(false);
  useEffect(() => {
    origin.current = document.activeElement;
  }, []);
  useEffect(() => {
    if (!data || focused.current) return;
    focused.current = true;
    if (document.activeElement === document.body || document.activeElement === origin.current)
      summary.current?.focus();
  }, [data]);
  if (error && !data)
    return (
      <div className="space-y-3">
        <p role="alert" className="text-sm text-destructive">
          {t('settings.telephony.calls.load_error')}
        </p>
        <Button
          variant="outline"
          aria-disabled={loading}
          onClick={() => {
            if (!loading) void refetch().catch(() => {});
          }}
        >
          {t('common.retry')}
        </Button>
      </div>
    );
  const day = data ? projectCallTimeline([data], lng).days[0] : undefined;
  const entry = day?.entries[0];
  return day && entry ? (
    <TimelineDayGroup
      headingId={id}
      heading={day.label ?? t('settings.telephony.calls.unknown_date')}
      level={4}
      dayNumber={day.dayNumber}
      month={day.month}
    >
      {error && (
        <p role="alert" className="p-3 text-sm text-destructive">
          {t('settings.telephony.calls.refresh_error')}
        </p>
      )}
      <ul className="min-w-0">
        <CallHistoryRow entry={entry} lng={lng} initiallyOpen summaryRef={summary} />
      </ul>
    </TimelineDayGroup>
  ) : (
    <Skeleton className="h-28 w-full rounded-xl" label={t('common.loading')} />
  );
}
