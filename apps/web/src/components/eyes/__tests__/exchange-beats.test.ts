/**
 * The beats the exchange earns, as decisions: what counts as a message sent,
 * and which finished tool has something to show for it. The host's own tests
 * (`EyesWidget.test.tsx`, « the wait ») hold what the face then does.
 */

import { describe, expect, it } from 'vitest';

import type { Activity, ActivityRecord } from '../activity';
import {
  ACKNOWLEDGEMENT_GESTURE,
  HAND_OVER_AFTER_MS,
  HAND_OVER_GESTURE,
  TOOL_DONE_GESTURE,
  finishedToolKey,
  handsOver,
  mayHandOver,
  messageSent,
} from '../exchange-beats';
import { GESTURE_DURATION_MS, REACTION_HOLD_MS } from '../expression-engine';
import { RIG_OWNED_GESTURES } from '../rig/gestures';

function record(
  invocation: string,
  phase: Activity['phase'],
  outcome: Activity['outcome'],
  at = 1000
): ActivityRecord {
  return {
    at,
    event: {
      version: 1,
      run_id: 'run-1',
      invocation_id: invocation,
      family: 'reading',
      intent: 'read',
      phase,
      outcome,
    },
  };
}

describe('a message sent', () => {
  it('is the EDGE to `sending`, from anywhere', () => {
    expect(messageSent('idle', 'sending')).toBe(true);
    expect(messageSent('error', 'sending')).toBe(true);
    expect(messageSent('streaming', 'sending')).toBe(true);
  });

  it('is not a turn that is still being sent, nor one that moved on', () => {
    expect(messageSent('sending', 'sending')).toBe(false);
    expect(messageSent('sending', 'streaming')).toBe(false);
    expect(messageSent('streaming', 'idle')).toBe(false);
    expect(messageSent('idle', 'idle')).toBe(false);
  });
});

describe('a tool that finished with a result', () => {
  it('is known by its run and its invocation', () => {
    expect(finishedToolKey(record('a', 'finished', 'succeeded'))).toBe('run-1:a');
    expect(finishedToolKey(record('b', 'finished', 'prepared'))).toBe('run-1:b');
  });

  it('keeps its identity when the answer stamps the same evidence again', () => {
    expect(finishedToolKey(record('a', 'finished', 'succeeded', 1000))).toBe(
      finishedToolKey(record('a', 'finished', 'succeeded', 9000))
    );
  });

  it.each(['failed', 'cancelled', 'waiting', 'unknown'] as const)(
    'is not one that ended %s',
    outcome => {
      expect(finishedToolKey(record('a', 'finished', outcome))).toBeNull();
    }
  );

  it('is not one that only started, and is not nothing', () => {
    expect(finishedToolKey(record('a', 'started', null))).toBeNull();
    expect(finishedToolKey(null)).toBeNull();
  });
});

describe('the gestures of the exchange', () => {
  it('are three different beats the rig owns, each with a time to play', () => {
    const beats = [ACKNOWLEDGEMENT_GESTURE, TOOL_DONE_GESTURE, HAND_OVER_GESTURE] as const;
    expect(new Set(beats).size).toBe(beats.length);
    for (const gesture of beats) {
      expect(RIG_OWNED_GESTURES).toContain(gesture);
      expect(GESTURE_DURATION_MS[gesture]).toBeGreaterThan(300);
    }
  });
});

describe('an answer handed over', () => {
  it('follows a presentation, and nothing else', () => {
    expect(handsOver('present-factual')).toBe(true);
    expect(handsOver('present-soft')).toBe(true);
    expect(handsOver('nod')).toBe(false);
    expect(handsOver(null)).toBe(false);
  });

  it('comes once the presentation has been seen, before the answer stops holding the face', () => {
    expect(HAND_OVER_AFTER_MS).toBeGreaterThan(GESTURE_DURATION_MS['present-factual'] - 1000);
    expect(HAND_OVER_AFTER_MS).toBeLessThan(REACTION_HOLD_MS);
  });

  it('is still owed while the answer it presented holds and nobody writes', () => {
    expect(mayHandOver(1000, 1000, false)).toBe(true);
  });

  it('is not owed for another answer, after a new turn, nor to someone who started writing', () => {
    expect(mayHandOver(5000, 1000, false)).toBe(false);
    expect(mayHandOver(null, 1000, false)).toBe(false);
    expect(mayHandOver(1000, 1000, true)).toBe(false);
  });
});
