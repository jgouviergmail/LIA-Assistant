import { describe, expect, it } from 'vitest';

import { formatElapsed, meetingStatusTone } from '../format';

describe('formatElapsed', () => {
  it.each([
    [0, '0:00'],
    [5, '0:05'],
    [65, '1:05'],
    [3599, '59:59'],
    [3600, '1:00:00'],
    [3725, '1:02:05'],
    [-4, '0:00'],
  ])('%d s → %s', (seconds, expected) => {
    expect(formatElapsed(seconds)).toBe(expected);
  });
});

describe('meetingStatusTone', () => {
  it('maps every status to a semantic tone', () => {
    expect(meetingStatusTone('ready')).toBe('success');
    expect(meetingStatusTone('failed')).toBe('destructive');
    expect(meetingStatusTone('interrupted')).toBe('warning');
    expect(meetingStatusTone('processing')).toBe('info');
    expect(meetingStatusTone('recording')).toBe('info');
    expect(meetingStatusTone('stopped')).toBe('info');
  });
});
