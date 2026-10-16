import { describe, expect, it } from 'vitest';
import { projectMeetingTimeline } from '../timeline';
import type { MeetingSummary } from '@/types/meetings';

const meeting = (
  id: string,
  started_at: string,
  stopped_at: string | null = null
): MeetingSummary => ({
  id,
  started_at,
  stopped_at,
  title: id,
  status: 'ready',
  stage: null,
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
});

describe('meeting timeline — local capture instants, never inferred end times', () => {
  it('groups the received page in display-zone days and periods without sorting or dropping IDs', () => {
    const records = [
      meeting('late', '2026-10-13T22:15:00Z'),
      meeting('evening', '2026-10-13T18:00:00Z'),
      meeting('afternoon', '2026-10-13T13:00:00Z'),
      meeting('noon', '2026-10-13T10:00:00Z'),
      meeting('morning', '2026-10-13T07:00:00Z'),
    ];
    const result = projectMeetingTimeline(records, 'fr', 'Europe/Paris');
    expect(result.days.map(day => day.key)).toEqual(['2026-10-14', '2026-10-13']);
    expect(result.days[1].periods.map(period => period.key)).toEqual([
      'evening',
      'afternoon',
      'midday',
      'morning',
    ]);
    expect(
      result.days.flatMap(day =>
        day.periods.flatMap(period => period.entries.map(entry => entry.meeting.id))
      )
    ).toEqual(records.map(record => record.id));
    expect(result.days[0].label).toMatch(/mercredi 14 octobre 2026/);
    expect(result.days[0].periods[0].entries[0].start).toBe('00:15');
  });

  it('keeps a null or invalid end absent, including while recording, and tolerates invalid starts', () => {
    const result = projectMeetingTimeline(
      [
        meeting('live', '2026-10-13T07:00:00Z'),
        meeting('bad-end', '2026-10-13T07:00:00Z', 'not a date'),
        meeting('bad-start', 'invalid'),
      ],
      'en',
      'UTC'
    );
    const entries = result.days.flatMap(day => day.periods.flatMap(period => period.entries));
    expect(entries.map(entry => entry.end)).toEqual([null, null, null]);
    expect(entries[2].start).toBeNull();
    expect(result.days[1].key).toBe('unknown');
    expect(result.days[1].label).toBeNull();
  });

  it('labels an end on another local day and retains the supplied audio duration independently', () => {
    const record = {
      ...meeting('overnight', '2026-10-13T21:50:00Z', '2026-10-13T22:10:00Z'),
      audio_duration_seconds: 0,
    };
    const entry = projectMeetingTimeline([record], 'fr', 'Europe/Paris').days[0].periods[0]
      .entries[0];
    expect(entry.start).toBe('23:50');
    expect(entry.end).toBe('00:10');
    expect(entry.endDay).toMatch(/14 oct/);
    expect(entry.meeting.audio_duration_seconds).toBe(0);
  });

  it('disambiguates repeated wall times when the clocks change', () => {
    const entry = projectMeetingTimeline(
      [meeting('fall-back', '2026-10-25T00:30:00Z', '2026-10-25T01:30:00Z')],
      'fr',
      'Europe/Paris'
    ).days[0].periods[0].entries[0];
    expect(entry.start).toMatch(/02:30.*UTC\+2/);
    expect(entry.end).toMatch(/02:30.*UTC\+1/);
    expect(entry.endDay).toBeNull();
  });

  it('keeps source order even when a malformed/unsorted page revisits a day or period', () => {
    const records = [
      meeting('a', '2026-10-13T10:00:00Z'),
      meeting('b', 'bad'),
      meeting('c', '2026-10-13T10:00:00Z'),
    ];
    const result = projectMeetingTimeline(records, 'de', 'America/New_York');
    expect(
      result.days.flatMap(day =>
        day.periods.flatMap(period => period.entries.map(entry => entry.meeting.id))
      )
    ).toEqual(['a', 'b', 'c']);
    expect(projectMeetingTimeline([], 'de', 'UTC').days).toEqual([]);
  });
});
