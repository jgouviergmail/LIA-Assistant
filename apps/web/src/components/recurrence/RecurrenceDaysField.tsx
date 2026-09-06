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

import { Fragment, useId } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { RecurrenceFreq, RecurrenceSpec } from '@/types/recurrence';
import { FRIDAY, ISO_WEEKDAYS, WEEKDAY_SETS, withFreq, type NamedDaySet } from '@/lib/recurrence';

const FREQUENCIES: readonly RecurrenceFreq[] = ['once', 'daily', 'weekly', 'monthly', 'yearly'];
const NAMED_SETS: readonly NamedDaySet[] = ['all', 'workdays', 'weekend'];
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

/** The seven weekday toggles, plus the three named shortcuts. */
function WeekdayPicker({
  value,
  onChange,
}: {
  value: RecurrenceSpec;
  onChange: (next: RecurrenceSpec) => void;
}) {
  const { t } = useTranslation();
  /** The one day that cannot be unchecked, or null when several are checked. */
  const lastChecked = value.byweekday.length === 1 ? value.byweekday[0] : null;
  const keepOneId = `${useId()}-keep-one`;

  const toggle = (day: number) => {
    const chosen = value.byweekday.includes(day)
      ? value.byweekday.filter(d => d !== day)
      : [...value.byweekday, day].sort((a, b) => a - b);
    // Never hand the API a weekly rule with no day. The guard is what prevents
    // it; `aria-disabled` on the button is what tells the reader beforehand.
    if (chosen.length === 0) return;
    onChange({ ...value, byweekday: chosen });
  };

  return (
    <div className="space-y-3">
      <Label>{t('recurrence.weekdays_label')}</Label>
      <div className="flex flex-wrap gap-2">
        {ISO_WEEKDAYS.map(day => (
          <Fragment key={day}>
          <Button
            type="button"
            size="sm"
            variant={value.byweekday.includes(day) ? 'default' : 'outline'}
            aria-pressed={value.byweekday.includes(day)}
            // `aria-disabled`, never `disabled`: the latter blurs a focused
            // control and drops it from the tab order.
            aria-disabled={lastChecked === day}
            // A `title` is the wrong carrier here: it never appears under a
            // finger and screen readers announce it inconsistently. The hint
            // below is visible to everyone and referenced from the control.
            aria-describedby={lastChecked === day ? keepOneId : undefined}
            onClick={() => toggle(day)}
            className="min-w-[3rem]"
          >
            {t(`scheduled_actions.days.d${day}`)}
          </Button>
          {/* A zero-height flex break after Friday, so Saturday and Sunday
              read as the weekend instead of trailing the working week. A
              break rather than a second container: the seven buttons stay ONE
              wrapping row, so a narrow screen still reflows them freely
              (owner arbitration 2026-09-06). */}
          {day === FRIDAY && <span aria-hidden="true" className="basis-full h-0" />}
          </Fragment>
        ))}
      </div>
      {lastChecked !== null && (
        <p id={keepOneId} className="text-xs text-muted-foreground">
          {t('recurrence.error_no_weekday')}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        {NAMED_SETS.map(name => (
          <Button
            key={name}
            type="button"
            size="sm"
            variant="outline"
            onClick={() => onChange({ ...value, byweekday: [...WEEKDAY_SETS[name]] })}
          >
            {t(`recurrence.weekday_set.${name}`)}
          </Button>
        ))}
      </div>
    </div>
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
