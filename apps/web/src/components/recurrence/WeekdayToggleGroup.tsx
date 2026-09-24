'use client';

/**
 * The seven ISO weekday toggles (Monday first), plus the three named sets.
 *
 * Shared by the recurrence editor — which days a schedule fires — and the LLM
 * pricing windows — which UTC days a peak window applies on (DeepSeek bills its
 * peaks Monday to Friday). One component, because the rules are the reader's,
 * not a screen's: a set of days is never empty, the weekend reads as a group,
 * and the working week is one press away.
 */

import { Fragment, useId } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { FRIDAY, ISO_WEEKDAYS, WEEKDAY_SETS, type NamedDaySet } from '@/lib/recurrence';

const NAMED_SETS: readonly NamedDaySet[] = ['all', 'workdays', 'weekend'];

export interface WeekdayToggleGroupProps {
  /** The chosen ISO weekdays (1 = Monday … 7 = Sunday). */
  days: readonly number[];
  /** Receives the next set, sorted, never empty. */
  onChange: (next: number[]) => void;
  /** The group's visible, already translated name. */
  label: string;
}

export function WeekdayToggleGroup({ days, onChange, label }: WeekdayToggleGroupProps) {
  const { t } = useTranslation();
  const labelId = useId();
  const keepOneId = `${labelId}-keep-one`;
  /** The one day that cannot be unchecked, or null when several are checked. */
  const lastChecked = days.length === 1 ? days[0] : null;

  const toggle = (day: number) => {
    const chosen = days.includes(day)
      ? days.filter(d => d !== day)
      : [...days, day].sort((a, b) => a - b);
    // Never hand a caller an empty set. The guard is what prevents it;
    // `aria-disabled` on the button is what tells the reader beforehand.
    if (chosen.length === 0) return;
    onChange(chosen);
  };

  return (
    <div className="space-y-3">
      <Label id={labelId}>{label}</Label>
      <div role="group" aria-labelledby={labelId} className="flex flex-wrap gap-2">
        {ISO_WEEKDAYS.map(day => (
          <Fragment key={day}>
            <Button
              type="button"
              size="sm"
              variant={days.includes(day) ? 'default' : 'outline'}
              aria-pressed={days.includes(day)}
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
            onClick={() => onChange([...WEEKDAY_SETS[name]])}
          >
            {t(`recurrence.weekday_set.${name}`)}
          </Button>
        ))}
      </div>
    </div>
  );
}
