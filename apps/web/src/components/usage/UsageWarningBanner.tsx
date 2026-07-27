'use client';

/**
 * The warning that comes BEFORE the wall (A5).
 *
 * The blocking banner it sits next to is the state this one exists to prevent:
 * until now the quota was invisible until it stopped the user mid-task, with no
 * indication of when it would lift.
 *
 * Deliberately quieter than `UsageBlockedBanner`: amber and dismissible-by-
 * progress rather than destructive, because nothing is broken yet. It names the
 * dimension that will actually block, its percentage, and — for a per-cycle
 * limit only — the date it resets. Absolute limits get no date, because none
 * ever resets.
 */

import { AlertTriangle } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/utils';
import type { UsageWarning } from '@/lib/usage-warning';

export interface UsageWarningBannerProps {
  warning: UsageWarning;
}

export function UsageWarningBanner({ warning }: UsageWarningBannerProps) {
  const { t, i18n } = useTranslation();
  const isCritical = warning.level === 'critical';

  const resetsAt = warning.cycleEnd
    ? new Date(warning.cycleEnd).toLocaleDateString(i18n.language, {
        day: 'numeric',
        month: 'long',
      })
    : null;

  return (
    <div
      // Polite, not assertive: this is context, not an interruption. The user
      // is mid-task and nothing is broken yet.
      role="status"
      className={cn(
        'flex items-center gap-3 border-b px-4 py-2',
        isCritical ? 'border-amber-500/40 bg-amber-500/15' : 'border-amber-500/25 bg-amber-500/10'
      )}
    >
      <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-500" />
      <p className="text-xs text-amber-900 dark:text-amber-200">
        <span className="font-semibold">
          {t(`usage_limits.warning.${warning.level}`, { percent: warning.usagePct })}
        </span>{' '}
        <span className="opacity-80">
          {t(`usage_limits.warning.dimension.${warning.dimension}`)}
          {resetsAt && ` · ${t('usage_limits.warning.resets_on', { date: resetsAt })}`}
        </span>
      </p>
    </div>
  );
}
