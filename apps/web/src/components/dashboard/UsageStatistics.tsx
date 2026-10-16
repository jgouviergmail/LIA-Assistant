'use client';

import { useEffect, useRef, useState } from 'react';
import { BarChart3, ChevronDown, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { DashboardTile } from '@/components/dashboard/DashboardTile';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { UsageLimitsTile } from '@/components/usage/UsageLimitsTile';
import { useUsageLimits } from '@/hooks/useUsageLimits';
import { useUserStatistics } from '@/hooks/useUserStatistics';
import { useStaleGuard } from '@/hooks/useStaleGuard';
import { getCycleDates } from '@/lib/format';

import { HomeConsumptionTable } from './HomeConsumptionTable';

/** One statistics read feeds both columns; limits retain their existing reader. */
export function UsageStatistics() {
  const { t, i18n } = useTranslation();
  const { statistics, isLoading, error, refetch } = useUserStatistics();
  const { limits, isLoading: limitsLoading } = useUsageLimits();
  const [retrying, setRetrying] = useState(false);
  const retryPending = useRef(false);
  const retryTrigger = useRef<HTMLButtonElement | null>(null);
  const summary = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (error || !statistics || !retryTrigger.current) return;
    if (!retryTrigger.current.isConnected && document.activeElement === document.body) {
      summary.current?.focus();
    }
    retryTrigger.current = null;
  }, [error, statistics]);
  const guard = useStaleGuard();
  const firstLoad = isLoading && !statistics;
  const cycleDates =
    statistics && validDate(statistics.current_cycle_start)
      ? getCycleDates(statistics.current_cycle_start)
      : null;
  const since = statistics ? formatSince(statistics.total_since, i18n.language) : null;

  async function retryStatistics() {
    if (retryPending.current) return;
    retryPending.current = true;
    setRetrying(true);
    try {
      await refetch();
    } finally {
      retryPending.current = false;
      if (guard.isMounted()) setRetrying(false);
    }
  }

  return (
    <details className="group/usage" open>
      <summary
        ref={summary}
        className="flex min-h-11 cursor-pointer list-none items-center gap-2 rounded-lg py-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <BarChart3 className="h-5 w-5 shrink-0 text-primary" aria-hidden="true" />
        <h2 className="min-w-0 flex-1 text-base font-semibold tracking-tight text-foreground sm:text-lg">
          {t('dashboard.statistics.consumption_title')}
        </h2>
        <ChevronDown
          className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open/usage:rotate-180 motion-reduce:transition-none"
          aria-hidden="true"
        />
      </summary>
      <div className="mt-3 space-y-4">
        {(cycleDates || since) && (
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs leading-relaxed text-muted-foreground">
            {cycleDates && <p>{t('dashboard.statistics.cycle_dates', cycleDates)}</p>}
            {since && <p>{t('dashboard.statistics.since', { date: since })}</p>}
          </div>
        )}
        {firstLoad ? (
          <DashboardTile contentClassName="p-4 sm:p-5">
            <div role="status" aria-label={t('common.loading')} className="space-y-5">
              {Array.from({ length: 8 }, (_, index) => (
                <div key={index} className="grid grid-cols-[42%_29%_29%] gap-y-2">
                  <Skeleton className="h-5 w-4/5" />
                  <Skeleton className="h-5 w-2/3 justify-self-end" />
                  <Skeleton className="h-5 w-2/3 justify-self-end" />
                </div>
              ))}
            </div>
          </DashboardTile>
        ) : (
          <>
            {(!statistics || error) && (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border/70 bg-card px-4 py-3">
                <p role="status" className="min-w-0 flex-1 text-sm text-muted-foreground">
                  {t(
                    statistics
                      ? 'dashboard.statistics.refresh_error'
                      : 'dashboard.statistics.unavailable'
                  )}
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  aria-disabled={retrying}
                  aria-busy={retrying}
                  onClick={event => {
                    retryTrigger.current = event.currentTarget;
                    void retryStatistics();
                  }}
                >
                  <RefreshCw
                    className={retrying ? 'animate-spin motion-reduce:animate-none' : ''}
                    aria-hidden="true"
                  />
                  {t('common.retry')}
                </Button>
              </div>
            )}
            {statistics && (
              <HomeConsumptionTable statistics={statistics} isLoading={isLoading || retrying} />
            )}
          </>
        )}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <UsageLimitsTile limits={limits} isLoading={limitsLoading} />
        </div>
      </div>
    </details>
  );
}

function validDate(iso: string): boolean {
  return !Number.isNaN(new Date(iso).getTime());
}

/** A malformed date or locale must not replace the real counters with an error. */
function formatSince(iso: string, locale: string): string | null {
  if (!validDate(iso)) return null;
  try {
    return new Intl.DateTimeFormat(locale || 'fr', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    }).format(new Date(iso));
  } catch {
    return null;
  }
}
