'use client';

/**
 * TaskDueChip — the day a task is due, read against the account's today (ADR-369).
 *
 * One chip for a list's rows and for the views across the lists: « Today » and an overdue
 * day are drawn in the warning tone, and an overdue day also SAYS so — colour is never the
 * only carrier.
 */
import { CalendarDays } from '@/lib/icons';

import { Badge } from '@/components/ui/badge';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { formatDay, type DueTone } from '@/lib/workbench/tasks';

export interface TaskDueChipProps {
  lng: Language;
  /** The day it is due, `YYYY-MM-DD`. */
  due: string;
  /** How that day reads against today (`dueTone`); a done task is never late. */
  tone: DueTone | null;
}

export function TaskDueChip({ lng, due, tone }: TaskDueChipProps) {
  const { t } = useTranslation(lng);
  const pressing = tone === 'today' || tone === 'overdue';
  return (
    <Badge variant={pressing ? 'warning' : 'outline'} size="sm" className="shrink-0">
      <CalendarDays className="h-3 w-3" aria-hidden="true" />
      {tone === 'today' ? t('workbench.tasks.today') : formatDay(due, lng)}
      {tone === 'overdue' && <span className="sr-only"> {t('workbench.tasks.overdue')}</span>}
    </Badge>
  );
}
