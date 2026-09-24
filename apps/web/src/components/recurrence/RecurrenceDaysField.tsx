'use client';

/**
 * The first of the editor's two questions: **which days**.
 *
 * Its own component, not a block inside `RecurrenceEditor`: the frequency, the
 * interval, and one selector per frequency add up to more branches than a
 * single function may carry (the shrink-only complexity ratchet caught exactly
 * that — CC 24 in one component). Splitting by QUESTION keeps each piece at
 * the size of what it asks.
 */

import { useTranslation } from 'react-i18next';

import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { RecurrenceFreq, RecurrenceSpec } from '@/types/recurrence';
import { withFreq } from '@/lib/recurrence';

import { WeekdayToggleGroup } from './WeekdayToggleGroup';

const FREQUENCIES: readonly RecurrenceFreq[] = ['once', 'daily', 'weekly', 'monthly', 'yearly'];
const MONTH_DAYS = Array.from({ length: 31 }, (_, i) => i + 1);
const MONTHS = Array.from({ length: 12 }, (_, i) => i + 1);

export interface RecurrenceDaysFieldProps {
  value: RecurrenceSpec;
  onChange: (next: RecurrenceSpec) => void;
  /** Builds a unique DOM id for a control of this editor. */
  id: (name: string) => string;
}

export function RecurrenceDaysField({ value, onChange, id }: RecurrenceDaysFieldProps) {
  const { t } = useTranslation();
  return (
    <fieldset className="space-y-3">
      <legend className="sr-only">{t('recurrence.legend_days')}</legend>

      <div className="space-y-3">
        <Label htmlFor={id('freq')}>{t('recurrence.freq_label')}</Label>
        <Select
          value={value.freq}
          onValueChange={freq => onChange(withFreq(value, freq as RecurrenceFreq))}
        >
          <SelectTrigger id={id('freq')} aria-label={t('recurrence.freq_label')}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {FREQUENCIES.map(freq => (
              <SelectItem key={freq} value={freq}>
                {t(`recurrence.freq.${freq}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {value.freq === 'weekly' && <WeekdayPicker value={value} onChange={onChange} />}
      {value.freq === 'monthly' && <MonthDayPicker value={value} onChange={onChange} id={id} />}
      {value.freq === 'yearly' && <YearDayPicker value={value} onChange={onChange} id={id} />}
    </fieldset>
  );
}

/** Which days of the week — the shared toggles, in this editor's words. */
function WeekdayPicker({
  value,
  onChange,
}: {
  value: RecurrenceSpec;
  onChange: (next: RecurrenceSpec) => void;
}) {
  const { t } = useTranslation();
  return (
    <WeekdayToggleGroup
      days={value.byweekday}
      onChange={byweekday => onChange({ ...value, byweekday })}
      label={t('recurrence.weekdays_label')}
    />
  );
}

/** The day of the month, `-1` meaning the last one. */
function MonthDayPicker({
  value,
  onChange,
  id,
}: {
  value: RecurrenceSpec;
  onChange: (next: RecurrenceSpec) => void;
  id: (name: string) => string;
}) {
  const { t } = useTranslation();
  return (
    <div className="space-y-3">
      <Label htmlFor={id('monthday')}>{t('recurrence.monthday_label')}</Label>
      <Select
        value={String(value.bymonthday[0] ?? 1)}
        onValueChange={v => onChange({ ...value, bymonthday: [Number(v)], nth_weekday: null })}
      >
        <SelectTrigger id={id('monthday')} aria-label={t('recurrence.monthday_label')}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="-1">{t('recurrence.monthday_last')}</SelectItem>
          {MONTH_DAYS.map(day => (
            <SelectItem key={day} value={String(day)}>
              {day}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

/** The month and the day of a yearly rule. */
function YearDayPicker({
  value,
  onChange,
  id,
}: {
  value: RecurrenceSpec;
  onChange: (next: RecurrenceSpec) => void;
  id: (name: string) => string;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-wrap gap-3">
      <div className="space-y-3">
        <Label htmlFor={id('month')}>{t('recurrence.month_label')}</Label>
        <Select
          value={String(value.bymonth[0] ?? 1)}
          onValueChange={v => onChange({ ...value, bymonth: [Number(v)] })}
        >
          <SelectTrigger id={id('month')} aria-label={t('recurrence.month_label')} className="w-32">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {MONTHS.map(month => (
              <SelectItem key={month} value={String(month)}>
                {t(`common.months.m${month}`, String(month))}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-3">
        <Label htmlFor={id('yearday')}>{t('recurrence.monthday_label')}</Label>
        <Select
          value={String(value.bymonthday[0] ?? 1)}
          onValueChange={v => onChange({ ...value, bymonthday: [Number(v)] })}
        >
          <SelectTrigger
            id={id('yearday')}
            aria-label={t('recurrence.monthday_label')}
            className="w-24"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {MONTH_DAYS.map(day => (
              <SelectItem key={day} value={String(day)}>
                {day}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}
