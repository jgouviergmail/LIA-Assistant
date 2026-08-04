'use client';

/**
 * FrequencyControls — the "how often" and "between which hours" pair
 * (layout program, 2026-08-05).
 *
 * Heartbeat and Interests carried the same two controls, duplicated line for
 * line — and both copies with the same defect: four Selects with NO
 * accessible name (the Label above them named nothing, the triggers had no
 * id). One implementation, labelled properly, serves both screens.
 *
 * Strings arrive translated from the caller (ADR-206).
 */

import type { ReactNode } from 'react';

import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

export interface MinMaxPerDayProps {
  /** Visible group label, already translated. */
  label: ReactNode;
  /** Trailing unit, e.g. "per day". */
  perDayLabel: string;
  /** Accessible names of the two selects — a bare "3" announces nothing. */
  minAriaLabel: string;
  maxAriaLabel: string;
  min: number;
  max: number;
  /** Highest offered value (Heartbeat offers 8, Interests 10). */
  limit: number;
  disabled?: boolean;
  onChange: (field: 'min' | 'max', value: number) => void;
}

export function MinMaxPerDay({
  label,
  perDayLabel,
  minAriaLabel,
  maxAriaLabel,
  min,
  max,
  limit,
  disabled,
  onChange,
}: MinMaxPerDayProps) {
  const options = Array.from({ length: limit }, (_, i) => i + 1);
  return (
    <div className="space-y-3">
      {/* `flex items-center`: preflight makes svg block-level, so without it
          a caller's label icon stacks ABOVE the text instead of before it. */}
      <Label className="flex items-center gap-2 text-sm">{label}</Label>
      <div className="flex items-center gap-2">
        <Select
          value={String(min)}
          onValueChange={v => onChange('min', parseInt(v))}
          disabled={disabled}
        >
          <SelectTrigger className="w-20" aria-label={minAriaLabel}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {options.map(n => (
              <SelectItem key={n} value={String(n)}>
                {n}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="text-muted-foreground" aria-hidden="true">
          -
        </span>
        <Select
          value={String(max)}
          onValueChange={v => onChange('max', parseInt(v))}
          disabled={disabled}
        >
          <SelectTrigger className="w-20" aria-label={maxAriaLabel}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {options.map(n => (
              <SelectItem key={n} value={String(n)}>
                {n}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="text-sm text-muted-foreground">{perDayLabel}</span>
      </div>
    </div>
  );
}

export interface HourWindowProps {
  /** Visible group label, already translated. */
  label: ReactNode;
  /** Accessible names of the two selects. */
  startAriaLabel: string;
  endAriaLabel: string;
  startHour: number;
  endHour: number;
  disabled?: boolean;
  onChange: (field: 'start' | 'end', value: number) => void;
}

const HOURS = Array.from({ length: 24 }, (_, i) => i);

function formatHour(hour: number): string {
  return `${String(hour).padStart(2, '0')}:00`;
}

export function HourWindow({
  label,
  startAriaLabel,
  endAriaLabel,
  startHour,
  endHour,
  disabled,
  onChange,
}: HourWindowProps) {
  return (
    <div className="space-y-3">
      <Label className="flex items-center gap-2 text-sm">{label}</Label>
      <div className="flex items-center gap-2">
        <Select
          value={String(startHour)}
          onValueChange={v => onChange('start', parseInt(v))}
          disabled={disabled}
        >
          <SelectTrigger className="w-24" aria-label={startAriaLabel}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {HOURS.map(h => (
              <SelectItem key={h} value={String(h)}>
                {formatHour(h)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="text-muted-foreground" aria-hidden="true">
          -
        </span>
        <Select
          value={String(endHour)}
          onValueChange={v => onChange('end', parseInt(v))}
          disabled={disabled}
        >
          <SelectTrigger className="w-24" aria-label={endAriaLabel}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {HOURS.map(h => (
              <SelectItem key={h} value={String(h)}>
                {formatHour(h)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}
