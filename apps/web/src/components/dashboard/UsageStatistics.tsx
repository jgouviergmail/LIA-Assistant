'use client';

import { useTranslation } from 'react-i18next';
import { BarChart3, ChevronDown, Coins, Database, Globe, MessageSquare } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card';
import { useUsageLimits } from '@/hooks/useUsageLimits';
import { useUserStatistics } from '@/hooks/useUserStatistics';
import { UsageLimitsTile } from '@/components/usage/UsageLimitsTile';
import { formatEuro, formatNumber, getCycleDates } from '@/lib/format';

/**
 * Usage statistics block — extracted verbatim from the previous dashboard page.
 *
 * Shows current billing cycle counters (messages, tokens, Google API requests, cost EUR)
 * plus the per-user usage limits tile. No behavior change vs. before the refactor.
 */
export function UsageStatistics() {
  const { t } = useTranslation();
  const { statistics, isLoading: statsLoading } = useUserStatistics();
  const { limits: usageLimits, isLoading: limitsLoading } = useUsageLimits();

  const cycleDates =
    !statsLoading && statistics ? getCycleDates(statistics.current_cycle_start) : null;
  const totalSinceIso = !statsLoading && statistics ? statistics.total_since : null;

  return (
    // A native <details>: the disclosure semantics, the keyboard behaviour and
    // the open/closed announcement come from the platform. OPEN by default
    // (owner arbitration 2026-08-05): the figures are consulted often enough
    // that the extra click cost more than the visual quiet it bought — the
    // results block above still leads, and the reader can fold this one.
    // `group` drives the chevron rotation only.
    <details className="group" open>
      <summary className="flex cursor-pointer list-none items-center gap-2 rounded-lg py-2 text-base font-semibold tracking-tight text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:text-lg">
        <BarChart3 className="h-5 w-5 shrink-0 text-primary" aria-hidden="true" />
        {t('dashboard.statistics.consumption_title')}
        <ChevronDown
          className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180 motion-reduce:transition-none"
          aria-hidden="true"
        />
      </summary>
      <div className="mt-4 grid gap-6 lg:grid-cols-2 xl:grid-cols-3">
        <StatCard
          title={t('dashboard.statistics.messages.title')}
          icon={<MessageSquare className="h-5 w-5 text-primary" />}
          cycleDates={cycleDates}
          value={statsLoading ? '-' : formatNumber(statistics?.cycle_messages || 0)}
          totalLabel={t('dashboard.statistics.messages.total')}
          totalValue={!statsLoading && statistics ? formatNumber(statistics.total_messages) : null}
          totalSinceIso={totalSinceIso}
        />

        <StatCard
          title={t('dashboard.statistics.tokens.title')}
          icon={<Database className="h-5 w-5 text-primary" />}
          cycleDates={cycleDates}
          value={
            statsLoading
              ? '-'
              : formatNumber(
                  (statistics?.cycle_prompt_tokens || 0) +
                    (statistics?.cycle_completion_tokens || 0) +
                    (statistics?.cycle_cached_tokens || 0)
                )
          }
          totalLabel={t('dashboard.statistics.tokens.total')}
          totalValue={
            !statsLoading && statistics
              ? formatNumber(
                  statistics.total_prompt_tokens +
                    statistics.total_completion_tokens +
                    statistics.total_cached_tokens
                )
              : null
          }
          totalSinceIso={totalSinceIso}
        />

        <StatCard
          title={t('dashboard.statistics.google_api.title')}
          icon={<Globe className="h-5 w-5 text-primary" />}
          cycleDates={cycleDates}
          value={statsLoading ? '-' : formatNumber(statistics?.cycle_google_api_requests || 0)}
          totalLabel={t('dashboard.statistics.google_api.total')}
          totalValue={
            !statsLoading && statistics ? formatNumber(statistics.total_google_api_requests) : null
          }
          totalSinceIso={totalSinceIso}
        />

        <StatCard
          title={t('dashboard.statistics.cost.title')}
          icon={<Coins className="h-5 w-5 text-primary" />}
          cycleDates={cycleDates}
          value={statsLoading ? '-' : formatEuro(statistics?.cycle_cost_eur || 0, 2)}
          totalLabel={t('dashboard.statistics.cost.total')}
          totalValue={!statsLoading && statistics ? formatEuro(statistics.total_cost_eur, 2) : null}
          totalSinceIso={totalSinceIso}
        />

        <UsageLimitsTile limits={usageLimits} isLoading={limitsLoading} />
      </div>
    </details>
  );
}

interface StatCardProps {
  title: string;
  icon: React.ReactNode;
  cycleDates: { start: string; end: string } | null;
  value: string;
  totalLabel: string;
  totalValue: string | null;
  /** ISO datetime — start of the lifetime totals (account creation date). */
  totalSinceIso: string | null;
}

function StatCard({
  title,
  icon,
  cycleDates,
  value,
  totalLabel,
  totalValue,
  totalSinceIso,
}: StatCardProps) {
  const { t, i18n } = useTranslation();
  const totalSinceLabel = totalSinceIso
    ? new Intl.DateTimeFormat(i18n.language || 'fr', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
      }).format(new Date(totalSinceIso))
    : null;
  return (
    <Card
      variant="elevated"
      className="border-2 border-primary/20 bg-gradient-to-br from-primary/5 to-background hover:shadow-xl transition-all"
    >
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardDescription className="text-xs uppercase tracking-wider font-semibold text-primary">
            {title}
          </CardDescription>
          {icon}
        </div>
        {cycleDates && (
          <div className="text-xs text-muted-foreground mt-1">
            {t('dashboard.statistics.cycle_dates', cycleDates)}
          </div>
        )}
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="text-4xl font-bold text-primary">{value}</div>
        {totalValue !== null && (
          <div className="pt-2 border-t border-border/50 space-y-0.5">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>{totalLabel}</span>
              <span className="font-medium text-foreground/80">{totalValue}</span>
            </div>
            {totalSinceLabel && (
              <div className="text-[10px] text-muted-foreground text-right tabular-nums">
                {t('dashboard.statistics.since', { date: totalSinceLabel })}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
