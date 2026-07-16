/**
 * Unit tests for the debug-panel formatters.
 *
 * Pure display helpers: percentages, token/byte/duration humanization, the
 * polymorphic `formatValue`, confidence badges, truncation and relative-time.
 * Every non-finite / boundary branch is exercised so the debug panel never
 * renders `NaN`/`Infinity`. `formatTimeAgo` reads `Date.now()`, so those cases
 * run under fake timers for determinism.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  formatBytes,
  formatCost,
  formatDuration,
  formatPercent,
  formatScoreWithConfidence,
  formatTimeAgo,
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

describe('formatScoreWithConfidence', () => {
  it('maps confidence level to a badge color', () => {
    expect(formatScoreWithConfidence(0.85, 'high')).toEqual({ text: '85%', color: 'green' });
    expect(formatScoreWithConfidence(0.5, 'medium')).toEqual({ text: '50%', color: 'yellow' });
    expect(formatScoreWithConfidence(0.1, 'low')).toEqual({ text: '10%', color: 'red' });
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

describe('formatBytes', () => {
  it('humanizes byte sizes with unit escalation', () => {
    expect(formatBytes(0)).toBe('0 B');
    expect(formatBytes(500)).toBe('500.0 B');
    expect(formatBytes(1024)).toBe('1.0 KB');
    expect(formatBytes(1536)).toBe('1.5 KB');
    expect(formatBytes(1_048_576)).toBe('1.0 MB');
  });

  it('returns a dash for invalid input', () => {
    expect(formatBytes(NaN)).toBe('-');
  });
});

describe('formatTimeAgo', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2025-01-15T12:00:00.000Z'));
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('buckets seconds / minutes / hours / days', () => {
    expect(formatTimeAgo(new Date(Date.now() - 2_000))).toBe('2s ago');
    expect(formatTimeAgo(new Date(Date.now() - 65_000))).toBe('1m ago');
    expect(formatTimeAgo(new Date(Date.now() - 3 * 3600_000))).toBe('3h ago');
    expect(formatTimeAgo(new Date(Date.now() - 2 * 86400_000))).toBe('2d ago');
  });

  it('accepts an ISO string', () => {
    expect(formatTimeAgo(new Date(Date.now() - 5_000).toISOString())).toBe('5s ago');
  });
});

describe('getEmotionalLabel', () => {
  it('maps -10..+10 weight to a label bucket', () => {
    expect(getEmotionalLabel(-8).label).toBe('TRAUMA');
    expect(getEmotionalLabel(-7).label).toBe('TRAUMA');
    expect(getEmotionalLabel(-4).label).toBe('NEG');
    expect(getEmotionalLabel(-3).label).toBe('NEG');
    expect(getEmotionalLabel(0).label).toBe('NEU');
    expect(getEmotionalLabel(3).label).toBe('POS');
    expect(getEmotionalLabel(7).label).toBe('TRES+');
    expect(getEmotionalLabel(10).label).toBe('TRES+');
  });

  it('carries Tailwind badge classes', () => {
    expect(getEmotionalLabel(-8).className).toContain('red');
    expect(getEmotionalLabel(5).className).toContain('green');
  });
});
