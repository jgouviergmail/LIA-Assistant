'use client';

/**
 * The generic recurrence editor — two questions, never one flat form.
 *
 * **Which days**, then **at what time**: that is the structure of the thought,
 * and it is the structure of the model (`[calendar days] × [times of day]`).
 * A single form mixing weekdays, months, hours and an end rule is what makes
 * recurrence pickers unreadable — so each question is its own component, which
 * also keeps every function at the size of what it asks.
 *
 * The component knows nothing about routines or reminders. What a consumer
 * allows travels in `limits`, so one editor serves a routine capped at twelve
 * runs a day and a reminder capped at forty-eight, with no branch of its own.
 *
 * Three rules it obeys, each paid for elsewhere in this codebase:
 *
 * - **It refuses what the API refuses, first and with a reason.** Unchecking
 *   the last weekday, or removing the last moment of a day, produces a shape
 *   the server rejects; the editor states the impossibility on the control
 *   BEFORE the click rather than doing nothing in silence.
 * - **No control is gated on width.** `hidden lg:flex` amputates a feature on
 *   phones and tablets — the defect `MemorySettings` records.
 * - **The summary travels with the form**, so the reader sees what the shape
 *   produces while they are still choosing it.
 */

import { CalendarClock, SlidersHorizontal } from 'lucide-react';
import { useId, useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import {
  RecurrenceAdvancedFields,
  hasAdvancedValues,
} from '@/components/recurrence/RecurrenceAdvancedFields';
import { Disclosure } from '@/components/ui/disclosure';
import { FormSection } from '@/components/ui/form-section';

import { RecurrenceDaysField } from '@/components/recurrence/RecurrenceDaysField';
import { RecurrenceSummary } from '@/components/recurrence/RecurrenceSummary';
import {
  RecurrenceTimesField,
} from '@/components/recurrence/RecurrenceTimesField';
import type { RecurrenceSpec } from '@/types/recurrence';
import { runsPerDay } from '@/lib/recurrence';

/** What ONE consumer allows. Injected, never owned by the editor. */
export interface RecurrenceLimits {
  maxTimesPerDay: number;
  minStepMinutes: number;
  maxSeriesCount: number;
}

export interface RecurrenceEditorProps {
  value: RecurrenceSpec;
  onChange: (next: RecurrenceSpec) => void;
  limits: RecurrenceLimits;
  /** IANA zone the recurrence is evaluated in — shown, never re-interpreted. */
  timezone: string;
  /** Prefix for generated ids, so two editors on one page never collide. */
  idPrefix: string;
  /** The sentence the server composed for the saved value, when there is one. */
  sentence?: string;
  /** The server's upcoming instants, when there are any. */
  occurrences?: readonly string[];
  /**
   * The saved series has no future left. Distinct from an empty
   * `occurrences`: "nothing follows" is a fact to state, and silence reads as
   * a loading list that never arrives.
   */
  finished?: boolean;
}

export function RecurrenceEditor({
  value,
  onChange,
  limits,
  timezone,
  idPrefix,
  sentence,
  occurrences,
  finished,
}: RecurrenceEditorProps) {
  const { t, i18n } = useTranslation();
  const uid = useId();
  const id = (name: string) => `${idPrefix}-${uid}-${name}`;

  const perDay = useMemo(() => runsPerDay(value.times), [value.times]);
  const error = useMemo(() => validationError(value, limits, perDay), [value, limits, perDay]);

  return (
    // The editor answers ONE question — when — so it names itself. Both
    // consumers mount it unchanged, so the heading lives here rather than
    // being written twice in two dialogs (owner arbitration 2026-09-06).
    <FormSection icon={CalendarClock} title={t('recurrence.section_when')}>
      <RecurrenceDaysField value={value} onChange={onChange} id={id} />
      <RecurrenceTimesField
        value={value}
        onChange={onChange}
        minStepMinutes={limits.minStepMinutes}
        id={id}
      />
      {/* Folded by default, OPEN whenever it already holds something: a
          schedule saying "every third week" must never hide that from the
          reader editing it (owner trial 2026-09-06). */}
      <Disclosure
        icon={SlidersHorizontal}
        title={t('recurrence.advanced')}
        defaultOpen={hasAdvancedValues(value)}
      >
        <RecurrenceAdvancedFields
          value={value}
          onChange={onChange}
          maxSeriesCount={limits.maxSeriesCount}
          id={id}
        />
      </Disclosure>

      {error && (
        <p className="text-xs text-destructive" role="alert">
          {t(error.key, error.params)}
        </p>
      )}

      <RecurrenceSummary
        spec={value}
        timezone={timezone}
        locale={i18n.language}
        sentence={sentence}
        occurrences={occurrences}
        finished={finished}
      />
    </FormSection>
  );
}

/**
 * The one message the editor shows, or null.
 *
 * A pure function rather than JSX branches: the messages are ordered by what a
 * reader should fix first, and that order is easier to read — and to test —
 * as a list of guards than as nested conditionals.
 */
function validationError(
  spec: RecurrenceSpec,
  limits: RecurrenceLimits,
  perDay: number
): { key: string; params?: Record<string, unknown> } | null {
  if (spec.freq === 'weekly' && spec.byweekday.length === 0) {
    return { key: 'recurrence.error_no_weekday' };
  }
  if (perDay === 0) return { key: 'recurrence.error_no_time' };
  if (spec.times.mode === 'every' && (spec.times.step_minutes ?? 0) < limits.minStepMinutes) {
    return { key: 'recurrence.error_step_too_small', params: { limit: limits.minStepMinutes } };
  }
  if (perDay > limits.maxTimesPerDay) {
    return {
      key: 'recurrence.error_too_many',
      params: { count: perDay, limit: limits.maxTimesPerDay },
    };
  }
  // A cleared end date blocks the save (`recurrenceIsComplete` refuses it, and
  // the API would too), so it must SAY so: a form that stops responding with
  // nothing on screen is the reader looking for a mistake they cannot see.
  // The count field cannot reach this — its handler floors at 1 — but a text
  // input is legitimately empty while someone retypes a date.
  if (spec.end.kind === 'on_date' && !spec.end.on_date) {
    return { key: 'recurrence.error_no_end_date' };
  }
  return null;
}
