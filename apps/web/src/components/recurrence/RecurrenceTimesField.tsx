'use client';

/**
 * The second of the editor's two questions: **at what time**, and the third,
 * smaller one: **when does it end**.
 *
 * Split from `RecurrenceEditor` for the same reason as the days field: one
 * component per question keeps each at the size of what it asks, which is what
 * the shrink-only complexity ratchet is there to protect.
 */

import { useId } from 'react';
import { Plus, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { RecurrenceSpec, TimeOfDay } from '@/types/recurrence';
import { clockLabel } from '@/lib/recurrence';

const HOURS = Array.from({ length: 24 }, (_, i) => i);
const MINUTES = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55];
const STEPS = [5, 10, 15, 20, 30, 45, 60, 90, 120, 180, 240, 360];

export interface RecurrenceTimesFieldProps {
  value: RecurrenceSpec;
  onChange: (next: RecurrenceSpec) => void;
  /** Smallest step this consumer allows — the default of a fresh step window. */
  minStepMinutes: number;
  id: (name: string) => string;
}

export function RecurrenceTimesField({
  value,
  onChange,
  minStepMinutes,
  id,
}: RecurrenceTimesFieldProps) {
  const { t } = useTranslation();
  const moments = value.times.mode === 'at' ? (value.times.at ?? []) : [];

  const switchMode = (mode: string) =>
    onChange({
      ...value,
      times:
        mode === 'at'
          ? { mode: 'at', at: moments.length > 0 ? moments : [{ hour: 8, minute: 0 }] }
          : {
              mode: 'every',
              step_minutes: Math.max(minStepMinutes, 60),
              start: { hour: 8, minute: 0 },
              end: { hour: 18, minute: 0 },
            },
    });

  return (
    <fieldset className="space-y-3">
      <legend className="sr-only">{t('recurrence.legend_times')}</legend>

      <div className="space-y-3">
        <Label htmlFor={id('times-mode')}>{t('recurrence.times_label')}</Label>
        <Select value={value.times.mode} onValueChange={switchMode}>
          <SelectTrigger id={id('times-mode')} aria-label={t('recurrence.times_label')}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="at">{t('recurrence.times_mode.at')}</SelectItem>
            <SelectItem value="every">{t('recurrence.times_mode.every')}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {value.times.mode === 'at' ? (
        <MomentList value={value} onChange={onChange} moments={moments} />
      ) : (
        <StepWindow value={value} onChange={onChange} id={id} />
      )}
    </fieldset>
  );
}

/** The explicit moments of a served day, one row each. */
function MomentList({
  value,
  onChange,
  moments,
}: {
  value: RecurrenceSpec;
  onChange: (next: RecurrenceSpec) => void;
  moments: readonly TimeOfDay[];
}) {
  const { t } = useTranslation();

  const setMoment = (index: number, patch: Partial<TimeOfDay>) =>
    onChange({
      ...value,
      times: {
        ...value.times,
        at: moments.map((m, i) => (i === index ? { ...m, ...patch } : m)),
      },
    });

  const onlyOneLeft = moments.length <= 1;
  const keepOneId = `${useId()}-keep-one`;

  const remove = (index: number) => {
    // A day always holds at least one moment; the API refuses none.
    if (moments.length <= 1) return;
    onChange({
      ...value,
      times: { ...value.times, at: moments.filter((_, i) => i !== index) },
    });
  };

  return (
    <div className="space-y-2">
      {moments.map((moment, index) => (
        <div key={`${moment.hour}:${moment.minute}:${index}`} className="flex items-center gap-2">
          <ClockSelect
            label={`${t('recurrence.times_label')} ${clockLabel(moment)}`}
            value={moment}
            onChange={next => setMoment(index, next)}
          />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="text-destructive"
            aria-label={t('recurrence.time_remove', { time: clockLabel(moment) })}
            aria-disabled={onlyOneLeft}
            // Same rule as the last weekday: a visible hint the control points
            // at, never a `title` no finger can reach.
            aria-describedby={onlyOneLeft ? keepOneId : undefined}
            onClick={() => remove(index)}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
      ))}
      {onlyOneLeft && (
        <p id={keepOneId} className="text-xs text-muted-foreground">
          {t('recurrence.error_no_time')}
        </p>
      )}
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() =>
          onChange({
            ...value,
            times: { ...value.times, mode: 'at', at: [...moments, { hour: 8, minute: 0 }] },
          })
        }
      >
        <Plus className="mr-1 h-4 w-4" aria-hidden="true" />
        {t('recurrence.time_add')}
      </Button>
    </div>
  );
}

/** A step, and the window it runs between. */
function StepWindow({
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
    // Two questions, two lines: how OFTEN, then between WHEN and when. The
    // three groups used to share one wrapping row, which read as a single
    // strip on a wide screen and broke at arbitrary points on a narrow one
    // (owner arbitration 2026-09-06).
    <div className="space-y-3">
      <div data-step-group className="space-y-3">
        <Label htmlFor={id('step')}>{t('recurrence.step_label')}</Label>
        <Select
          value={String(value.times.step_minutes ?? 60)}
          onValueChange={v =>
            onChange({ ...value, times: { ...value.times, step_minutes: Number(v) } })
          }
        >
          {/* Wide enough for the longest option in every locale — "360
              minutes", "360 Minuten" — now that the step owns its line. */}
          <SelectTrigger id={id('step')} aria-label={t('recurrence.step_label')} className="w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {STEPS.map(step => (
              <SelectItem key={step} value={String(step)}>
                {step} {t('recurrence.step_unit_minutes')}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {/* One phrase — "08:00 to 18:00" — rather than two captioned fields.
          The captions are GONE from the screen, not from the accessibility
          tree: each clock keeps its `aria-label`, so a screen reader still
          tells the two ends apart, and the joining word is decorative
          (owner arbitration 2026-09-06). */}
      <div data-window-group className="flex flex-wrap items-center gap-2">
        <ClockSelect
          triggerId={id('from')}
          label={t('recurrence.step_from')}
          value={value.times.start ?? { hour: 8, minute: 0 }}
          onChange={start => onChange({ ...value, times: { ...value.times, start } })}
        />
        <span aria-hidden="true" className="text-sm text-muted-foreground">
          {t('recurrence.step_separator')}
        </span>
        <ClockSelect
          triggerId={id('to')}
          label={t('recurrence.step_to')}
          value={value.times.end ?? { hour: 18, minute: 0 }}
          onChange={end => onChange({ ...value, times: { ...value.times, end } })}
        />
      </div>
    </div>
  );
}

/** An `HH:MM` pair of named selects — the one place hours and minutes are drawn. */
function ClockSelect({
  label,
  value,
  onChange,
  triggerId,
}: {
  label: string;
  value: TimeOfDay;
  onChange: (next: TimeOfDay) => void;
  triggerId?: string;
}) {
  return (
    <div className="flex items-center gap-1">
      <Select value={String(value.hour)} onValueChange={v => onChange({ ...value, hour: Number(v) })}>
        <SelectTrigger id={triggerId} aria-label={label} className="w-20">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {HOURS.map(h => (
            <SelectItem key={h} value={String(h)}>
              {String(h).padStart(2, '0')}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <span aria-hidden="true">:</span>
      <Select
        value={String(value.minute)}
        onValueChange={v => onChange({ ...value, minute: Number(v) })}
      >
        <SelectTrigger aria-label={`${label} minutes`} className="w-20">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {MINUTES.map(m => (
            <SelectItem key={m} value={String(m)}>
              {String(m).padStart(2, '0')}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

export interface RecurrenceEndFieldProps {
  value: RecurrenceSpec;
  onChange: (next: RecurrenceSpec) => void;
  maxSeriesCount: number;
  id: (name: string) => string;
}

/** How a series stops: never, on a date, or after a number of occurrences. */
export function RecurrenceEndField({
  value,
  onChange,
  maxSeriesCount,
  id,
}: RecurrenceEndFieldProps) {
  const { t } = useTranslation();
  const kinds = ['never', 'on_date', 'after_count'] as const;

  return (
    <div className="space-y-3">
      <Label htmlFor={id('end')}>{t('recurrence.end_label')}</Label>
      <div className="flex flex-wrap items-end gap-3">
        <Select
          value={value.end.kind}
          onValueChange={v =>
            onChange({
              ...value,
              end: {
                kind: v as RecurrenceSpec['end']['kind'],
                on_date: v === 'on_date' ? (value.end.on_date ?? value.anchor_date) : null,
                after_count: v === 'after_count' ? (value.end.after_count ?? 10) : null,
              },
            })
          }
        >
          <SelectTrigger id={id('end')} aria-label={t('recurrence.end_label')} className="w-52">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {kinds.map(kind => (
              <SelectItem key={kind} value={kind}>
                {t(`recurrence.end.${kind}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {value.end.kind === 'on_date' && (
          <div className="w-44">
            <Input
              type="date"
              aria-label={t('recurrence.date_label')}
              // The server refuses a series that ends before it starts, so the
              // control publishes the bound it enforces rather than letting the
              // request come back 422 (ADR-184).
              min={value.anchor_date}
              value={value.end.on_date ?? ''}
              onChange={e => onChange({ ...value, end: { ...value.end, on_date: e.target.value } })}
              className="w-full"
            />
          </div>
        )}
        {value.end.kind === 'after_count' && (
          <div className="space-y-3">
            <Label htmlFor={id('count')}>{t('recurrence.end_count_label')}</Label>
            <div className="w-24">
              <Input
                id={id('count')}
                type="number"
                min={1}
                max={maxSeriesCount}
                value={value.end.after_count ?? 1}
                onChange={e =>
                  onChange({
                    ...value,
                    end: { ...value.end, after_count: Math.max(1, Number(e.target.value) || 1) },
                  })
                }
                className="w-full"
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
