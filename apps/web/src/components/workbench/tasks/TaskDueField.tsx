'use client';

/**
 * TaskDueField — the day a task is due, typed or a tap away (ADR-369): today, tomorrow, in a week,
 * or no date at all. A provider that keeps a date without a time says so under the field. Shared
 * by the task's detail and the form a handed task opens in, so the two never drift apart.
 */
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { addDays } from '@/lib/workbench/calendar/zoned';

/** The dates at hand: their words and how far from today. */
const QUICK_DUES: readonly (readonly [string, number])[] = [
  ['workbench.tasks.due_today', 0],
  ['workbench.tasks.due_tomorrow', 1],
  ['workbench.tasks.due_next_week', 7],
];

export interface TaskDueFieldProps {
  lng: Language;
  /** The day the form holds, `YYYY-MM-DD`, or empty. */
  value: string;
  /** The account's day, `YYYY-MM-DD`. */
  today: string;
  /** The provider keeps a date without a time. */
  dateOnly: boolean;
  /** A day typed. */
  onType: (value: string) => void;
  /** A day chosen with one press, or none. */
  onPick: (value: string) => void;
  onBlur?: () => void;
}

export function TaskDueField({
  lng,
  value,
  today,
  dateOnly,
  onType,
  onPick,
  onBlur,
}: TaskDueFieldProps) {
  const { t } = useTranslation(lng);
  return (
    <div className="space-y-1">
      <Input
        type="date"
        label={t('workbench.tasks.due')}
        value={value}
        onChange={event => onType(event.target.value)}
        onBlur={onBlur}
      />
      <div className="flex flex-wrap gap-1.5 pt-1">
        {QUICK_DUES.map(([key, days]) => (
          <Button
            key={key}
            type="button"
            variant="outline"
            size="sm"
            className="h-8 px-2.5 text-xs"
            onClick={() => onPick(addDays(today, days))}
          >
            {t(key)}
          </Button>
        ))}
        {value && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-8 px-2.5 text-xs"
            onClick={() => onPick('')}
          >
            {t('workbench.tasks.due_none')}
          </Button>
        )}
      </div>
      {dateOnly && (
        <p className="text-xs text-muted-foreground">{t('workbench.tasks.due_date_only')}</p>
      )}
    </div>
  );
}
