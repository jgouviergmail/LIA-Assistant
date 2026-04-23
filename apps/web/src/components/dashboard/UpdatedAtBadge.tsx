'use client';

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { computeTimeAgo } from '@/lib/briefing-utils';

interface UpdatedAtBadgeProps {
  /** ISO 8601 UTC datetime returned by the backend */
  generatedAt: string;
  /** When true, show the transient "updated ✨" badge instead of the timestamp */
  showJustUpdated?: boolean;
  className?: string;
}

const REFRESH_INTERVAL_MS = 30_000; // re-render the relative label every 30 s

/**
 * Compact "il y a N min" timestamp shown at the bottom of each briefing card.
 *
 * - Re-renders every 30 s so the relative label stays fresh without a global timer.
 * - When `showJustUpdated=true`, displays "mis à jour ✨" badge for 1.5 s after a refresh.
 * - Wraps the relative text in `<time>` with a full ISO `dateTime` attribute for a11y.
 */
export function UpdatedAtBadge({
  generatedAt,
  showJustUpdated = false,
  className,
}: UpdatedAtBadgeProps) {
  const { t } = useTranslation();
  const [, setTick] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setTick(n => n + 1), REFRESH_INTERVAL_MS);
    return () => clearInterval(id);
  }, []);

  if (showJustUpdated) {
    return (
      <span
        className={`inline-flex items-center gap-1 text-xs text-primary/80 animate-in fade-in duration-200 ${className ?? ''}`}
      >
        {t('dashboard.briefing.synthesis_updated_badge')}
      </span>
    );
  }

  const bucket = computeTimeAgo(generatedAt);
  let label = t('dashboard.briefing.updated_just_now');
  if (bucket.kind === 'minutes') {
    label = t('dashboard.briefing.updated_minutes_ago', { minutes: bucket.count });
  } else if (bucket.kind === 'hours') {
    label = t('dashboard.briefing.updated_hours_ago', { hours: bucket.count });
  } else if (bucket.kind === 'days') {
    label = t('dashboard.briefing.updated_days_ago', { days: bucket.count });
  }

  return (
    <time
      dateTime={generatedAt}
      title={generatedAt}
      className={`text-[10px] text-muted-foreground/50 tabular-nums ${className ?? ''}`}
    >
      {label}
    </time>
  );
}
