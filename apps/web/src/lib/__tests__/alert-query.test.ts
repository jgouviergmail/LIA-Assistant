import { describe, expect, it } from 'vitest';
import { scheduledDisplayRows } from '../alert-query';
import type { ScheduledActionRow } from '@/components/notifications/ScheduledActionsList';

const row = (id: string, title: string, next: string | null): ScheduledActionRow => ({
  id,
  title,
  next_trigger_at: next,
  is_enabled: true,
  trigger_kind: 'time',
  schedule_display: 'Chaque été',
});

describe('complete routine collection', () => {
  const rows = [
    row('b', 'Zèbre', '2026-11-01T00:00:00Z'),
    row('a', 'Alpha', '2026-11-02T00:00:00Z'),
    row('c', 'Unknown', null),
  ];
  it('filters the entire displayed collection, literally and accent-insensitively', () => {
    expect(scheduledDisplayRows(rows, { q: 'ete', sort: '' })).toHaveLength(3);
    expect(scheduledDisplayRows(rows, { q: 'ZEB', sort: '' }).map(r => r.id)).toEqual(['b']);
    expect(scheduledDisplayRows(rows, { q: '%', sort: '' })).toEqual([]);
  });
  it('keeps unknown next instants last in either direction and defaults to soonest', () => {
    expect(scheduledDisplayRows(rows, { q: '', sort: '' }).map(r => r.id)).toEqual(['b', 'a', 'c']);
    expect(scheduledDisplayRows(rows, { q: '', sort: 'recent' }).map(r => r.id)).toEqual([
      'a',
      'b',
      'c',
    ]);
    expect(scheduledDisplayRows(rows, { q: '', sort: 'name' }).map(r => r.id)).toEqual([
      'a',
      'c',
      'b',
    ]);
    expect(rows.map(r => r.id)).toEqual(['b', 'a', 'c']);
  });
  it('does not invent a next run for disabled or condition routines', () => {
    const disabled = { ...rows[0], is_enabled: false };
    expect(scheduledDisplayRows([disabled, rows[1]], { q: '', sort: '' }).map(r => r.id)).toEqual([
      'a',
      'b',
    ]);
    const condition: ScheduledActionRow = { ...rows[0], trigger_kind: 'condition' };
    expect(
      scheduledDisplayRows([condition, rows[1]], { q: '', sort: 'recent' }).map(r => r.id)
    ).toEqual(['a', 'b']);
  });
  it('does not invent a next run for a routine started by calls (ADR-386)', () => {
    // Armed for the scheduler's next look at its calls, never a planned run.
    // Soonest first: armed for Nov 1, it would come BEFORE Nov 2 if read as a run.
    const onCalls: ScheduledActionRow = { ...rows[0], trigger_kind: 'webhook' };
    expect(scheduledDisplayRows([onCalls, rows[1]], { q: '', sort: '' }).map(r => r.id)).toEqual([
      'a',
      'b',
    ]);
  });
});
