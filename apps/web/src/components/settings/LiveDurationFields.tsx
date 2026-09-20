'use client';

/**
 * The two per-model durations of a live connector (owner decision 2026-09-19):
 * the silence after which the session closes and the longest session before
 * the extension dialog — `0` for « no limit », within the bounds the API
 * publishes because it enforces them (ADR-184). Above them, the warning the
 * owner asked for: a provider may bill the whole session (waiting included)
 * or only the interactions, and only the person knows their model's billing —
 * an unlimited session on a per-second provider is theirs to choose, eyes open.
 */
import { AlertTriangle } from 'lucide-react';
import { useState } from 'react';

import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { LiveDurationBounds } from '@/lib/live/types';

interface DurationFieldProps {
  id: string;
  label: string;
  help: string;
  value: number;
  bounds: LiveDurationBounds;
  unlimited: number;
  unlimitedHint: string;
  /** The API would refuse this value: said under the field, and the save withheld. */
  invalid: boolean;
  invalidHint: string;
  disabled: boolean;
  onChange: (value: number) => void;
}

/**
 * One bounded integer, `unlimited` allowed below the minimum. The text under
 * edit is kept apart from the number it names, so that emptying the field to
 * type another value does not snap back to the previous one (a controlled
 * number input on `value` alone turned « 60 » cleared then « 0 » into 600).
 * A value the API would refuse is shown as such; the parent withholds it.
 */
function DurationField({
  id,
  label,
  help,
  value,
  bounds,
  unlimited,
  unlimitedHint,
  invalid,
  invalidHint,
  disabled,
  onChange,
}: DurationFieldProps) {
  const [edit, setEdit] = useState<{ text: string; from: number } | null>(null);
  // The typed text stands while it names the current number (or nothing yet);
  // a number set from outside — a model switched to — replaces it.
  const text = edit !== null && edit.from === value ? edit.text : String(value);
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        type="number"
        inputMode="numeric"
        min={unlimited}
        max={bounds.max}
        step={1}
        value={text}
        disabled={disabled}
        aria-invalid={invalid || undefined}
        aria-describedby={invalid ? `${id}-help ${id}-error` : `${id}-help`}
        onChange={event => {
          const raw = event.target.value;
          setEdit({ text: raw, from: value });
          const parsed = Number.parseInt(raw, 10);
          if (Number.isFinite(parsed)) onChange(parsed);
        }}
      />
      <p id={`${id}-help`} className="text-xs text-muted-foreground">
        {help} {unlimitedHint}
        {value === unlimited && <span className="ml-1 font-medium text-foreground">∞</span>}
      </p>
      {invalid && (
        <p id={`${id}-error`} role="alert" className="text-xs text-destructive">
          {invalidHint}
        </p>
      )}
    </div>
  );
}

export interface LiveDurationFieldsProps {
  lng: Language;
  idleTimeoutSeconds: number;
  sessionMaxMinutes: number;
  idleBounds: LiveDurationBounds;
  sessionBounds: LiveDurationBounds;
  unlimited: number;
  idleAllowed: boolean;
  sessionAllowed: boolean;
  disabled: boolean;
  onIdleTimeout: (seconds: number) => void;
  onSessionMax: (minutes: number) => void;
}

export function LiveDurationFields({
  lng,
  idleTimeoutSeconds,
  sessionMaxMinutes,
  idleBounds,
  sessionBounds,
  unlimited,
  idleAllowed,
  sessionAllowed,
  disabled,
  onIdleTimeout,
  onSessionMax,
}: LiveDurationFieldsProps) {
  const { t } = useTranslation(lng);
  const outOfBounds = (bounds: LiveDurationBounds) =>
    t('settings.live_mode.duration_out_of_bounds', {
      min: bounds.min,
      max: bounds.max,
      unlimited,
    });
  return (
    <div className="space-y-3">
      <div
        role="note"
        className="flex gap-2 rounded-lg border border-amber-300/60 bg-amber-50 p-3 text-xs text-amber-800 dark:border-amber-700/60 dark:bg-amber-900/20 dark:text-amber-300"
      >
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <p>
          <span className="font-medium">{t('settings.live_mode.billing_warning_title')}</span>{' '}
          {t('settings.live_mode.billing_warning')}
        </p>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <DurationField
          id="live-idle-timeout"
          label={t('settings.live_mode.idle_timeout')}
          help={t('settings.live_mode.idle_timeout_help', {
            min: idleBounds.min,
            max: idleBounds.max,
          })}
          value={idleTimeoutSeconds}
          bounds={idleBounds}
          unlimited={unlimited}
          unlimitedHint={t('settings.live_mode.unlimited_hint', { value: unlimited })}
          invalid={!idleAllowed}
          invalidHint={outOfBounds(idleBounds)}
          disabled={disabled}
          onChange={onIdleTimeout}
        />
        <DurationField
          id="live-session-max"
          label={t('settings.live_mode.session_max')}
          help={t('settings.live_mode.session_max_help', {
            min: sessionBounds.min,
            max: sessionBounds.max,
          })}
          value={sessionMaxMinutes}
          bounds={sessionBounds}
          unlimited={unlimited}
          unlimitedHint={t('settings.live_mode.unlimited_hint', { value: unlimited })}
          invalid={!sessionAllowed}
          invalidHint={outOfBounds(sessionBounds)}
          disabled={disabled}
          onChange={onSessionMax}
        />
      </div>
    </div>
  );
}
