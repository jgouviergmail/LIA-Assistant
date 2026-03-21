'use client';

import type { TFunction } from 'i18next';
import type { LimitDetail } from '@/types/usage-limits';

/** Color thresholds for usage gauge */
const THRESHOLDS = {
  GREEN_MAX: 60,
  YELLOW_MAX: 80,
  ORANGE_MAX: 95,
} as const;

function getGaugeColor(pct: number | null): string {
  if (pct === null) return 'bg-muted';
  if (pct < THRESHOLDS.GREEN_MAX) return 'bg-green-500';
  if (pct < THRESHOLDS.YELLOW_MAX) return 'bg-yellow-500';
  if (pct < THRESHOLDS.ORANGE_MAX) return 'bg-orange-500';
  return 'bg-red-500';
}

/**
 * Format large numbers compactly: 1234 → 1 234, 1234567 → 1.23M, 1234567890 → 1.23B
 */
function formatCompact(v: number): string {
  if (v >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(1)}B`;
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 100_000) return `${(v / 1_000).toFixed(0)}K`;
  return v.toLocaleString();
}

interface UsageGaugeProps {
  /** Limit detail with current value, limit, and percentage */
  detail: LimitDetail;
  /** Gauge label (shown left of the values) */
  label: string;
  /** Mode: period or absolute */
  mode: 'period' | 'absolute';
  /** Optional value formatter (defaults to compact formatting) */
  formatValue?: (v: number) => string;
  /** Translation function */
  t: TFunction;
  /** Size variant */
  size?: 'sm' | 'md';
}

/**
 * Reusable progress bar gauge for usage limits.
 *
 * Shows current usage vs limit with color-coded progress bar.
 * Displays "unlimited" when limit is null.
 */
export function UsageGauge({
  detail,
  label,
  mode: _mode,
  formatValue = formatCompact,
  t,
  size = 'md',
}: UsageGaugeProps) {
  const isUnlimited = detail.limit === null;
  const pct = detail.usage_pct ?? 0;
  const cappedPct = Math.min(pct, 100);
  const barColor = getGaugeColor(detail.usage_pct);
  const textSize = size === 'sm' ? 'text-[10px]' : 'text-xs';

  return (
    <div className="space-y-0.5">
      <div className={`flex items-center justify-between gap-1 ${textSize} leading-tight`}>
        <span className="font-medium text-foreground shrink-0">{label}</span>
        <span className="text-muted-foreground text-right truncate">
          {isUnlimited ? (
            t('usage_limits.unlimited')
          ) : (
            <>
              {formatValue(detail.current)}/{formatValue(detail.limit!)}{' '}
              <span className="text-muted-foreground/70">({Math.min(Math.round(pct), 9999)}%)</span>
            </>
          )}
        </span>
      </div>

      {/* Progress bar */}
      {!isUnlimited && (
        <div
          className="h-1 w-full rounded-full bg-muted overflow-hidden"
          role="progressbar"
          aria-valuenow={detail.current}
          aria-valuemax={detail.limit ?? undefined}
          aria-label={label}
        >
          <div
            className={`h-full rounded-full transition-all duration-300 ${barColor}`}
            style={{ width: `${cappedPct}%` }}
          />
        </div>
      )}
    </div>
  );
}
