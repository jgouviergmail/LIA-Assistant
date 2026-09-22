import { beforeEach, describe, expect, it, vi } from 'vitest';

import { parseActivity, recentActivity, type Activity } from '../activity';
import { useEyesSignalsStore as signals } from '@/stores/eyesSignalsStore';

const event = (overrides: Partial<Activity> = {}): Activity => ({
  version: 1,
  run_id: 'run',
  invocation_id: 'one',
  family: 'communicating',
  intent: 'act',
  phase: 'started',
  outcome: null,
  ...overrides,
});

beforeEach(() => signals.getState().reset());

describe('execution evidence', () => {
  it.each(['prepared', 'succeeded'] as const)(
    'carries %s work into a slow answer exactly once',
    outcome => {
      const now = vi.spyOn(Date, 'now').mockReturnValue(30_000);
      try {
        const store = signals.getState();
        store.beginTurn('answer');
        store.recordActivity(
          event({ phase: 'finished', intent: outcome === 'prepared' ? 'prepare' : 'act', outcome }),
          'answer',
          false,
          100
        );
        expect(recentActivity(signals.getState().lastActivity, 30_000)).toBeNull();
        store.completeTurn('answer');
        expect(recentActivity(signals.getState().lastActivity, 30_000)).toMatchObject({
          family: 'communicating',
          accomplished: outcome === 'succeeded',
          weight: 1,
        });
        now.mockReturnValue(31_000);
        store.completeTurn('answer');
        expect(signals.getState().lastActivity?.at).toBe(30_000);
        expect(recentActivity(signals.getState().lastActivity, 36_000)).toBeNull();
      } finally {
        now.mockRestore();
      }
    }
  );
  it('rejects a different run and an old completion without closing the active answer', () => {
    const store = signals.getState();
    expect(store.liveReactionWeight(100)).toBe(1);
    store.beginTurn('answer');
    store.recordActivity(event(), 'answer', false, 100);
    store.recordActivity(
      event({ run_id: 'stale-run', invocation_id: 'two' }),
      'answer',
      false,
      110
    );
    store.completeTurn('old-answer');
    expect(signals.getState().turnOpen).toBe(true);
    expect(signals.getState().completedAnswerId).toBeNull();
    expect(signals.getState().activities).toHaveLength(1);
    expect(signals.getState().liveActivity(120)?.run_id).toBe('run');
  });
  it('keeps a fading memory of real work but reserves accomplishment for explicit acts', () => {
    const prepared = recentActivity(
      {
        event: event({
          phase: 'finished',
          intent: 'prepare',
          outcome: 'prepared',
        }),
        at: 100,
      },
      110
    );
    expect(prepared?.accomplished).toBe(false);
    const action = {
      event: event({ phase: 'finished', outcome: 'succeeded' }),
      at: 100,
    };
    expect(recentActivity(action, 110)?.accomplished).toBe(true);
    expect(recentActivity(action, 2100)?.weight).toBeLessThan(1);
    expect(recentActivity(action, 7000)).toBeNull();
    expect(
      recentActivity({ ...action, event: event({ phase: 'finished', outcome: 'unknown' }) }, 110)
    ).toBeNull();
  });
  it('rejects malformed and future payloads, including contradictory phases', () => {
    for (const value of [
      null,
      {},
      { ...event(), version: 2 },
      { ...event(), arguments: { private: 'never keep payloads' } },
      event({ phase: 'finished' }),
      event({ outcome: 'succeeded' }),
    ]) {
      expect(parseActivity(value)).toBeNull();
    }
    expect(parseActivity(event())).toEqual(event());
  });

  it('only accepts the active answer and ignores replay and late events', () => {
    const store = signals.getState();
    store.beginTurn();
    store.recordActivity(event(), 'answer', false, 100);
    store.recordActivity(event({ family: 'creating' }), 'other', false, 100);
    expect(signals.getState().liveActivity(110)?.family).toBe('communicating');
    store.endTurn();
    store.recordActivity(event(), 'answer', false, 100);
    expect(signals.getState().liveActivity(110)).toBeNull();
    store.beginTurn();
    store.recordActivity(event(), 'answer', true, 100);
    expect(signals.getState().liveActivity(110)).toBeNull();
  });

  it('tracks parallel calls and a terminal event cannot be undone by a late start', () => {
    const store = signals.getState();
    store.beginTurn();
    store.recordActivity(event(), 'answer', false, 100);
    store.recordActivity(event({ invocation_id: 'two', family: 'reading' }), 'answer', false, 110);
    store.recordActivity(event({ phase: 'finished', outcome: 'succeeded' }), 'answer', false, 120);
    store.recordActivity(event(), 'answer', false, 130);
    expect(signals.getState().liveActivity(140)?.invocation_id).toBe('two');
  });

  it('never turns a draft into an accomplished action and expires missing terminals', () => {
    const store = signals.getState();
    store.beginTurn();
    store.recordActivity(
      event({ phase: 'finished', intent: 'prepare', outcome: 'prepared' }),
      'answer',
      false,
      100
    );
    expect(signals.getState().liveActivity(110)).toBeNull();
    store.recordActivity(event({ invocation_id: 'two' }), 'answer', false, 110);
    expect(signals.getState().liveActivity(600_000)).toBeNull();
  });
});
