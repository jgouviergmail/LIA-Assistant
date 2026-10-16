import { Coins, Database, Globe, MessageSquare } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { UserStatistics } from '@/hooks/useUserStatistics';
import { formatEuro, formatNumber } from '@/lib/format';
import { cn } from '@/lib/utils';

import { DashboardTile } from './DashboardTile';

interface ConsumptionRow {
  label: string;
  period: number;
  total: number;
  icon?: LucideIcon;
  currency?: boolean;
  emphasis?: boolean;
}

/** Present the received counters together without creating any additional reads. */
export function HomeConsumptionTable({
  statistics: s,
  isLoading,
}: {
  statistics: UserStatistics;
  isLoading: boolean;
}) {
  const { t } = useTranslation();
  const rows: ConsumptionRow[] = [
    {
      label: 'messages.title',
      period: s.cycle_messages,
      total: s.total_messages,
      icon: MessageSquare,
    },
    {
      label: 'tokens.title',
      icon: Database,
      period: s.cycle_prompt_tokens + s.cycle_completion_tokens + s.cycle_cached_tokens,
      total: s.total_prompt_tokens + s.total_completion_tokens + s.total_cached_tokens,
    },
    { label: 'prompt_tokens', period: s.cycle_prompt_tokens, total: s.total_prompt_tokens },
    {
      label: 'completion_tokens',
      period: s.cycle_completion_tokens,
      total: s.total_completion_tokens,
    },
    { label: 'cached_tokens', period: s.cycle_cached_tokens, total: s.total_cached_tokens },
    {
      label: 'google_api.title',
      icon: Globe,
      period: s.cycle_google_api_requests,
      total: s.total_google_api_requests,
    },
    {
      label: 'google_api_cost',
      currency: true,
      period: s.cycle_google_api_cost_eur,
      total: s.total_google_api_cost_eur,
    },
    {
      label: 'cost.title',
      period: s.cycle_cost_eur,
      total: s.total_cost_eur,
      icon: Coins,
      currency: true,
      emphasis: true,
    },
  ];

  return (
    <DashboardTile contentClassName="overflow-hidden">
      <table
        className="w-full table-fixed border-collapse"
        aria-label={t('dashboard.statistics.consumption_title')}
        aria-busy={isLoading}
      >
        <colgroup>
          <col className="w-[42%] sm:w-1/2" />
          <col className="w-[29%] sm:w-1/4" />
          <col className="w-[29%] sm:w-1/4" />
        </colgroup>
        <thead>
          <tr className="bg-primary/5">
            <th
              scope="col"
              className="px-3 py-3 text-left text-xs font-medium text-muted-foreground sm:px-5"
            >
              {t('dashboard.statistics.consumption_title')}
            </th>
            <th
              scope="col"
              className="px-2 py-3 text-right text-xs font-semibold text-primary sm:px-5"
            >
              {t('dashboard.statistics.period')}
            </th>
            <th
              scope="col"
              className="px-3 py-3 text-right text-xs font-medium text-muted-foreground sm:px-5"
            >
              {t('dashboard.statistics.total')}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map(row => (
            <ConsumptionTableRow key={row.label} row={row} />
          ))}
        </tbody>
      </table>
    </DashboardTile>
  );
}

function ConsumptionTableRow({ row }: { row: ConsumptionRow }) {
  const { t } = useTranslation();
  const Icon = row.icon;
  const format = row.currency ? (value: number) => formatEuro(value, 2) : formatNumber;
  return (
    <tr className={cn(Icon && 'border-t border-border/50', row.emphasis && 'bg-primary/5')}>
      <th
        scope="row"
        className={cn(
          'break-words text-left font-normal leading-relaxed [overflow-wrap:anywhere]',
          Icon
            ? 'px-3 py-3 text-xs font-medium text-foreground sm:px-5 sm:py-4 sm:text-sm'
            : 'py-1.5 pr-2 pl-9 text-xs text-muted-foreground sm:pl-12'
        )}
      >
        <span className="flex items-center gap-2 sm:gap-3">
          {Icon && <Icon className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />}
          {t(`dashboard.statistics.${row.label}`)}
        </span>
      </th>
      <td
        className={cn(
          'px-2 text-right tabular-nums [overflow-wrap:anywhere] sm:px-5',
          Icon
            ? 'py-3 text-sm font-semibold text-primary sm:py-4 sm:text-base'
            : 'py-1.5 text-xs text-foreground/80'
        )}
      >
        {format(row.period)}
      </td>
      <td
        className={cn(
          'px-3 text-right tabular-nums [overflow-wrap:anywhere] sm:px-5',
          Icon
            ? 'py-3 text-sm font-medium text-foreground sm:py-4 sm:text-base'
            : 'py-1.5 text-xs text-muted-foreground'
        )}
      >
        {format(row.total)}
      </td>
    </tr>
  );
}
