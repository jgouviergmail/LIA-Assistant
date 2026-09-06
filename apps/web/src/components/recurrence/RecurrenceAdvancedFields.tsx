'use client';

/**
 * The three settings a reader configures once and rarely revisits.
 *
 * "Every N periods", the day the series is anchored on, and where it stops:
 * true controls, but not the questions someone answers when they create a
 * routine. Folded away, the form asks five questions instead of eight
 * (owner trial 2026-09-06).
 *
 * **Folding is only safe because it opens itself.** A schedule that already
 * says "every third week" or "until 31 December" must never hide that: a
 * reader editing it would see a plain weekly rule and believe the interval had
 * been lost. `hasAdvancedValues` decides, and the disclosure follows it.
 */

import { useTranslation } from 'react-i18next';

import { RecurrenceEndField } from '@/components/recurrence/RecurrenceTimesField';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type { RecurrenceFreq, RecurrenceSpec } from '@/types/recurrence';

/** Frequencies whose interval is worth offering. `once` has none. */
const INTERVALLED: readonly RecurrenceFreq[] = ['daily', 'weekly', 'monthly', 'yearly'];

/**
 * Whether this recurrence already carries something the fold would hide.
 *
 * @param spec - The recurrence being edited.
 * @returns True when the disclosure must start open.
 */
export function hasAdvancedValues(spec: RecurrenceSpec): boolean {
  // A single occurrence is the case where the anchor is not an option at all:
  // it IS the date the reminder fires. Folding it away would hide the most
  // important field on the form behind a disclosure nobody would think to
  // open — caught by an existing test, not by review.
  if (spec.freq === 'once') return true;
  return spec.interval > 1 || spec.end.kind !== 'never';
}

export interface RecurrenceAdvancedFieldsProps {
  value: RecurrenceSpec;
  onChange: (next: RecurrenceSpec) => void;
  maxSeriesCount: number;
  id: (name: string) => string;
}

export function RecurrenceAdvancedFields({
  value,
  onChange,
  maxSeriesCount,
  id,
}: RecurrenceAdvancedFieldsProps) {
  const { t } = useTranslation();
  // The anchor appears only where it changes an outcome: it IS the date of a
  // single occurrence, and it is the phase of an interval. On a plain daily
  // rule it would be one more field asking nothing.
  const showAnchor = value.freq === 'once' || value.interval > 1;

  return (
    <div className="space-y-4">
      {INTERVALLED.includes(value.freq) && (
        <div className="space-y-3">
          <Label htmlFor={id('interval')}>{t('recurrence.interval_label')}</Label>
          <div className="flex items-center gap-2">
            {/* `Input` wraps itself in `FieldFrame`, which is `w-full`. Inside
                a flex row that wrapper claims every spare pixel and throws the
                unit against the right edge — measured in the browser
                2026-09-06, "week(s)" sat 330 px from an 80 px field. Bounding
                the WRAPPER is what puts the two side by side; a width on the
                input alone cannot. */}
            <div data-interval-field className="w-24 shrink-0">
              <Input
                id={id('interval')}
                type="number"
                min={1}
                max={99}
                value={value.interval}
                onChange={e =>
                  onChange({ ...value, interval: Math.max(1, Number(e.target.value) || 1) })
                }
                className="w-full"
              />
            </div>
            <span className="text-sm text-muted-foreground">
              {t(`recurrence.interval_unit.${value.freq}`)}
            </span>
          </div>
        </div>
      )}

      {value.freq !== 'once' && (
        <RecurrenceEndField
          value={value}
          onChange={onChange}
          maxSeriesCount={maxSeriesCount}
          id={id}
        />
      )}

      {showAnchor && (
        <div className="space-y-3">
          <Label htmlFor={id('anchor')}>{t('recurrence.anchor_label')}</Label>
          <div className="w-44">
            <Input
              id={id('anchor')}
              type="date"
              value={value.anchor_date}
              onChange={e => onChange({ ...value, anchor_date: e.target.value })}
              className="w-full"
            />
          </div>
          <p className="text-xs text-muted-foreground">{t('recurrence.anchor_hint')}</p>
        </div>
      )}
    </div>
  );
}
