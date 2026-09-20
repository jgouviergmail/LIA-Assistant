'use client';

/**
 * The optional spend ceiling of a live connector, per session (ADR-300 wave
 * 3, owner decision 2026-09-19: optional, provider granularity). In euros on
 * the person's OWN key: the banner's indicative meter ends the session when
 * the cost it computes reaches it — the platform records nothing of it. An
 * empty field means no ceiling; the bound is the API's, published because
 * enforced (ADR-184).
 *
 * As for the durations, the typed text is kept apart from the number it
 * names, so emptying the field to type another amount never snaps back.
 */
import { useState } from 'react';

import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';

export interface LiveBudgetFieldProps {
  lng: Language;
  /** The provider's brand, named in the label: the ceiling is the connector's. */
  provider: string;
  value: number | null;
  max: number;
  /** The API would refuse this value: said under the field, the save withheld. */
  invalid: boolean;
  disabled: boolean;
  onChange: (value: number | null) => void;
}

const ID = 'live-session-budget';

export function LiveBudgetField({
  lng,
  provider,
  value,
  max,
  invalid,
  disabled,
  onChange,
}: LiveBudgetFieldProps) {
  const { t } = useTranslation(lng);
  const [edit, setEdit] = useState<{ text: string; from: number | null } | null>(null);
  const text = edit !== null && edit.from === value ? edit.text : value === null ? '' : String(value);
  return (
    <div className="space-y-2">
      <Label htmlFor={ID}>{t('settings.live_mode.budget', { provider })}</Label>
      <Input
        id={ID}
        type="number"
        inputMode="decimal"
        min={0}
        max={max}
        step="0.01"
        placeholder={t('settings.live_mode.budget_placeholder')}
        value={text}
        disabled={disabled}
        aria-invalid={invalid || undefined}
        aria-describedby={invalid ? `${ID}-help ${ID}-error` : `${ID}-help`}
        onChange={event => {
          const raw = event.target.value;
          setEdit({ text: raw, from: value });
          if (raw.trim() === '') {
            onChange(null);
            return;
          }
          const parsed = Number.parseFloat(raw);
          if (Number.isFinite(parsed)) onChange(parsed);
        }}
      />
      <p id={`${ID}-help`} className="text-xs text-muted-foreground">
        {t('settings.live_mode.budget_help', { max })}
      </p>
      {invalid && (
        <p id={`${ID}-error`} role="alert" className="text-xs text-destructive">
          {t('settings.live_mode.budget_out_of_bounds', { max })}
        </p>
      )}
    </div>
  );
}
