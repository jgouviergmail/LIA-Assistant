'use client';

/** Identify the calendar a chat card opened after its real source has loaded. */
import { CalendarDays } from '@/lib/icons';
import { useEffect, useRef } from 'react';

import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { WorkbenchCalendar } from '@/lib/workbench/types';

export function CalendarTarget({
  lng,
  requested,
  target,
  loading,
  failed,
}: {
  lng: Language;
  requested: string | null;
  target: WorkbenchCalendar | undefined;
  loading: boolean;
  failed: boolean;
}) {
  const { t } = useTranslation(lng);
  const notice = useRef<HTMLDivElement>(null);
  const ready = Boolean(requested) && !loading;
  useEffect(() => {
    if (ready) notice.current?.focus();
  }, [ready, requested, target?.id, failed]);
  if (!ready) return null;
  const text = failed
    ? t('workbench.calendar.failed')
    : target
      ? t('workbench.calendar.selected_calendar', { name: target.name })
      : t('workbench.states.calendar_target_missing');
  return (
    <div
      ref={notice}
      role="status"
      aria-label={target?.name}
      tabIndex={-1}
      className="flex items-center gap-2 rounded-lg border bg-card p-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <CalendarDays aria-hidden="true" className="h-4 w-4 shrink-0 text-primary" />
      <span>{text}</span>
    </div>
  );
}
