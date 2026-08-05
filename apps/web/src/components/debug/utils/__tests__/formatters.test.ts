/**
 * Unit tests for the debug-panel formatters.
 *
 * Pure display helpers: percentages, token/duration humanization, the
 * polymorphic `formatValue`, truncation, wall-clock formatting and the
 * emotional-weight buckets. Every non-finite / boundary branch is
 * exercised so the debug panel never renders `NaN`/`Infinity`.
 */
import { describe, expect, it } from 'vitest';

import {
  formatClockTime,
  formatCost,
  formatDuration,
  formatPercent,
  formatTokenCount,
  formatValue,
  getEmotionalLabel,
  truncateText,
} from '../formatters';

describe('formatPercent', () => {
  it('formats a 0..1 ratio as a percentage with configurable decimals', () => {
    expect(formatPercent(0.45)).toBe('45%');
    expect(formatPercent(0.876)).toBe('88%');
    expect(formatPercent(0.125, 1)).toBe('12.5%');
    expect(formatPercent(0.00142, 2)).toBe('0.14%');
  });

  it('returns a dash for non-numbers and non-finite values', () => {
    expect(formatPercent(NaN)).toBe('-');
    expect(formatPercent(Infinity)).toBe('-');
    expect(formatPercent('x' as unknown as number)).toBe('-');
  });
});

describe('formatTokenCount', () => {
  it('humanizes with k / M thresholds', () => {
    expect(formatTokenCount(150)).toBe('150');
    expect(formatTokenCount(1500)).toBe('1.5k');
    expect(formatTokenCount(2_000_000)).toBe('2.0M');
    expect(formatTokenCount(2_345_678)).toBe('2.3M');
    expect(formatTokenCount(999)).toBe('999');
  });

  it('returns a dash for invalid input', () => {
    expect(formatTokenCount(NaN)).toBe('-');
    expect(formatTokenCount('x' as unknown as number)).toBe('-');
  });
});

describe('formatDuration', () => {
  it('switches to seconds at 1000ms and honors includeUnit', () => {
    expect(formatDuration(450)).toBe('450ms');
    expect(formatDuration(1200)).toBe('1.2s');
    expect(formatDuration(1250)).toBe('1.3s'); // (1.25).toFixed(1) rounds to 1.3
    expect(formatDuration(1250, false)).toBe('1.3');
    expect(formatDuration(0)).toBe('0ms');
    expect(formatDuration(450, false)).toBe('450');
  });

  it('returns a dash for invalid input', () => {
    expect(formatDuration(Infinity)).toBe('-');
  });
});

describe('formatCost', () => {
  it('delegates to the euro formatter (French locale)', () => {
    expect(formatCost(2.45, 2)).toContain('2,45');
    expect(formatCost(2.45, 2)).toContain('€');
    expect(formatCost(0.00142)).toContain('0,0014');
  });

  it('returns a dash for invalid input', () => {
    expect(formatCost(NaN)).toBe('-');
  });
});

describe('formatValue (polymorphic)', () => {
  it('null / undefined → dash', () => {
    expect(formatValue(null)).toBe('-');
    expect(formatValue(undefined)).toBe('-');
  });

  it('booleans → Yes / No', () => {
    expect(formatValue(true)).toBe('Yes');
    expect(formatValue(false)).toBe('No');
  });

  it('numbers: percentage range, large-with-separators, small, non-finite', () => {
    expect(formatValue(0.45)).toBe('45%');
    expect(formatValue(1234)).toBe('1 234'); // fr grouping, spaces normalized
    // negative large branch (value <= -1000) also routes through libFormatNumber
    expect(formatValue(-1234)).toContain('1 234');
    expect(formatValue(-1234).startsWith('-')).toBe(true);
    expect(formatValue(42)).toBe('42');
    expect(formatValue(Infinity)).toBe('-');
    expect(formatValue(0)).toBe('0'); // not in (0,1) exclusive range
    expect(formatValue(1)).toBe('1'); // boundary, not a percentage
  });

  it('strings pass through, arrays join recursively, objects stringify', () => {
    expect(formatValue('hello')).toBe('hello');
    expect(formatValue(['a', 'b'])).toBe('a, b');
    expect(formatValue([true, 0.5])).toBe('Yes, 50%');
    expect(formatValue({ x: 1 })).toBe('{"x":1}');
  });

  it('a non-serializable object → [Object]', () => {
    const circular: Record<string, unknown> = {};
    circular.self = circular;
    expect(formatValue(circular)).toBe('[Object]');
  });
});

describe('truncateText', () => {
  it('truncates with an ellipsis only past maxLength', () => {
    expect(truncateText('Hello world', 8)).toBe('Hello...');
    expect(truncateText('Short', 10)).toBe('Short');
    expect(truncateText('Long text', 6, '…')).toBe('Long …');
  });

  it('coerces non-strings via String()', () => {
    expect(truncateText(123 as unknown as string)).toBe('123');
  });
});

describe('formatClockTime', () => {
  it('renders a deterministic 24h HH:MM:SS whatever the runtime locale', () => {
    expect(formatClockTime(new Date(2026, 0, 5, 9, 7, 3))).toBe('09:07:03');
    expect(formatClockTime(new Date(2026, 5, 15, 23, 59, 59))).toBe('23:59:59');
    expect(formatClockTime(new Date(2026, 5, 15, 0, 0, 0))).toBe('00:00:00');
  });

  it('returns a dash for an invalid date', () => {
    expect(formatClockTime(new Date('nonsense'))).toBe('-');
  });
});

describe('getEmotionalLabel', () => {
  it('maps -10..+10 weight to an English label bucket', () => {
    expect(getEmotionalLabel(-8).label).toBe('TRAUMA');
    expect(getEmotionalLabel(-7).label).toBe('TRAUMA');
    expect(getEmotionalLabel(-4).label).toBe('NEG');
    expect(getEmotionalLabel(-3).label).toBe('NEG');
    expect(getEmotionalLabel(0).label).toBe('NEU');
    expect(getEmotionalLabel(3).label).toBe('POS');
    expect(getEmotionalLabel(7).label).toBe('STRONG+');
    expect(getEmotionalLabel(10).label).toBe('STRONG+');
  });

  it('carries a semantic tone, not raw palette classes', () => {
    expect(getEmotionalLabel(-8).tone).toBe('alert');
    expect(getEmotionalLabel(-4).tone).toBe('destructive');
    expect(getEmotionalLabel(0).tone).toBe('neutral');
    expect(getEmotionalLabel(5).tone).toBe('success');
    expect(getEmotionalLabel(8).tone).toBe('success');
  });
});
