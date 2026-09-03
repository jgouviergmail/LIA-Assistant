/**
 * Row selection on the meetings list (ADR-259): pure helpers the page composes.
 */

import { describe, expect, it } from 'vitest';

import type { MeetingSummary } from '@/types/meetings';

import { isSelectable, pageSelectionState, toggleId } from '../selection';

function summary(over: Partial<MeetingSummary> = {}): MeetingSummary {
  return {
    id: 'm1',
    status: 'ready',
    stage: null,
    title: 'Point projet',
    started_at: '2026-09-02T10:00:00Z',
    stopped_at: null,
    audio_duration_seconds: null,
    participants_count: 0,
    action_items_count: 0,
    index_state: null,
    stt_provider: null,
    total_cost_eur: null,
    last_error_code: null,
    template_ref: null,
    template_name: null,
    template_selection: null,
    source_meeting_id: null,
    ...over,
  };
}

describe('isSelectable', () => {
  it('refuses the rows the server would skip: live captures and processing jobs', () => {
    expect(isSelectable(summary({ status: 'recording' }))).toBe(false);
    expect(isSelectable(summary({ status: 'interrupted' }))).toBe(false);
    expect(isSelectable(summary({ status: 'processing' }))).toBe(false);
  });

  it('accepts terminal and queued rows', () => {
    expect(isSelectable(summary({ status: 'ready' }))).toBe(true);
    expect(isSelectable(summary({ status: 'failed' }))).toBe(true);
    expect(isSelectable(summary({ status: 'stopped' }))).toBe(true);
  });
});

describe('toggleId', () => {
  it('adds a missing id and removes a present one without mutating the input', () => {
    const initial = new Set(['a']);
    const added = toggleId(initial, 'b');
    expect([...added]).toEqual(['a', 'b']);
    expect([...initial]).toEqual(['a']);
    expect([...toggleId(added, 'a')]).toEqual(['b']);
  });
});

describe('pageSelectionState', () => {
  it('reports none, some and all against the selectable ids of the page', () => {
    expect(pageSelectionState(['a', 'b'], new Set())).toBe('none');
    expect(pageSelectionState(['a', 'b'], new Set(['a']))).toBe('some');
    expect(pageSelectionState(['a', 'b'], new Set(['a', 'b', 'stale']))).toBe('all');
    expect(pageSelectionState([], new Set())).toBe('none');
  });
});
