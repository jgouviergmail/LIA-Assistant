'use client';

/**
 * EventRepeatField — when an event happens again (ADR-369, lot 10).
 *
 * The recurrence editor's two pieces that speak of days: an event's time is its own, so the
 * question of the hours is not asked. The rule is read from the event's own first day, whatever
 * the form says of it, so a weekly choice opens on the day the event falls on.
 */
import { useId } from 'react';

import { RecurrenceAdvancedFields } from '@/components/recurrence/RecurrenceAdvancedFields';
import { RecurrenceDaysField } from '@/components/recurrence/RecurrenceDaysField';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { EventFields } from '@/lib/workbench/calendar/editor';

export interface EventRepeatFieldProps {
  lng: Language;
  fields: EventFields;
  set: (change: Partial<EventFields>) => void;
  /** The published bound of a series counted in occurrences. */
  maxCount: number;
}

export function EventRepeatField({ lng, fields, set, maxCount }: EventRepeatFieldProps) {
  const { t } = useTranslation(lng);
  const prefix = useId();
  const id = (name: string) => `${prefix}-${name}`;
  const value = { ...fields.repeat, anchor_date: fields.startDate };
  const change = (repeat: EventFields['repeat']) => set({ repeat });
  return (
    <fieldset className="space-y-3 rounded-md border p-3">
      {/* The frequency's own label is the one drawn: the group keeps its name for the ear. */}
      <legend className="sr-only">{t('workbench.calendar.editor.repeat')}</legend>
      <RecurrenceDaysField value={value} onChange={change} id={id} />
      {value.freq !== 'once' && (
        <RecurrenceAdvancedFields
          value={value}
          onChange={change}
          maxSeriesCount={maxCount}
          id={id}
        />
      )}
    </fieldset>
  );
}
