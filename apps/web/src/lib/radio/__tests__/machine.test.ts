/**
 * The radio player's states (ADR-324): a stopped player stays stopped.
 */
import { describe, expect, it } from 'vitest';

import { isOnAir, transition, type RadioEvent, type RadioStatus } from '../machine';

describe('transition', () => {
  it('walks a whole session', () => {
    const events: RadioEvent[] = [
      'start',
      'started',
      'segment_started',
      'drained',
      'stop',
      'ended',
    ];
    const walked = events.reduce<RadioStatus[]>(
      (states, event) => [...states, transition(states[states.length - 1], event)],
      ['idle']
    );
    expect(walked).toEqual([
      'idle',
      'starting',
      'waiting',
      'playing',
      'waiting',
      'ending',
      'ended',
    ]);
  });

  it('resumes where the pause found it', () => {
    expect(transition(transition('playing', 'paused'), 'resumed_segment')).toBe('playing');
    expect(transition(transition('waiting', 'paused'), 'resumed_waiting')).toBe('waiting');
  });

  it('never lets a late event restart an ended player', () => {
    const late: RadioEvent[] = ['started', 'segment_started', 'drained', 'resumed_segment'];
    for (const event of late) expect(transition('ended', event)).toBe('ended');
  });

  it('allows a new session after the last one ended', () => {
    expect(transition('ended', 'start')).toBe('starting');
    expect(transition('playing', 'start')).toBe('playing');
  });
});

describe('isOnAir', () => {
  it('holds the audio from the click to the stop', () => {
    const on = (
      ['idle', 'starting', 'waiting', 'playing', 'paused', 'ending', 'ended'] as const
    ).filter(isOnAir);
    expect(on).toEqual(['starting', 'waiting', 'playing', 'paused']);
  });
});
