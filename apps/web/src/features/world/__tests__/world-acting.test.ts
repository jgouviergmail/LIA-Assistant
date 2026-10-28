import { expect, it } from 'vitest';
import { NEUTRAL_CONTEXT } from '@/components/eyes/rig/direction';
import type { ActivityRecord } from '@/components/eyes/activity';
import { deriveWorldActing, WorldActingEvents, type WorldActingInputs } from '../world-acting';

const record: ActivityRecord = {
  at: 1000,
  event: {
    version: 1,
    run_id: 'run',
    invocation_id: 'step',
    family: 'creating',
    intent: 'act',
    phase: 'finished',
    outcome: 'succeeded',
  },
};
function input(patch: Partial<WorldActingInputs> = {}): WorldActingInputs {
  return {
    ownerId: 'owner',
    signalOwnerId: 'owner',
    enabled: true,
    now: 1000,
    runId: 'run',
    recent: null,
    background: null,
    context: NEUTRAL_CONTEXT,
    emphasis: 1,
    responseWeight: 1,
    expression: {
      chatStatus: 'idle',
      streamPhase: 'answer',
      lastStepKind: null,
      hitlAwaiting: false,
      voiceState: 'idle',
      reaction: null,
      notificationPing: false,
      userTyping: false,
      moodLabel: null,
      hourOfDay: 12,
      inactivityStage: 0,
      activity: null,
    },
    ...patch,
  };
}
it('uses the native priority and never treats text streaming as audio playback', () => {
  const base = input();
  expect(
    deriveWorldActing({
      ...base,
      expression: { ...base.expression, chatStatus: 'streaming', streamPhase: 'answer' },
    })
  ).toMatchObject({ state: 'responding', pose: { expression: 'attentive' } });
  expect(
    deriveWorldActing({ ...base, expression: { ...base.expression, voiceState: 'speaking' } })
  ).toMatchObject({ state: 'speaking', pose: { expression: 'speaking' } });
  expect(
    deriveWorldActing({
      ...base,
      expression: { ...base.expression, voiceState: 'speaking', hitlAwaiting: true },
    })
  ).toMatchObject({ state: 'waiting', pose: { expression: 'question' } });
  expect(
    deriveWorldActing({
      ...base,
      expression: { ...base.expression, hitlAwaiting: true, chatStatus: 'error' },
    })
  ).toMatchObject({ state: 'error', pose: { expression: 'worried' } });
  expect(
    deriveWorldActing({ ...base, expression: { ...base.expression, voiceState: 'recording' } })
      .state
  ).toBe('listening');
});
it('distinguishes creating and reading from completion, preparation, failure and uncertain outcomes', () => {
  const base = input();
  expect(
    deriveWorldActing({
      ...base,
      expression: {
        ...base.expression,
        chatStatus: 'streaming',
        streamPhase: 'progress',
        activity: 'reading',
      },
    }).state
  ).toBe('reading');
  expect(
    deriveWorldActing({
      ...base,
      expression: {
        ...base.expression,
        chatStatus: 'streaming',
        streamPhase: 'progress',
        activity: 'creating',
      },
    }).state
  ).toBe('creating');
  expect(deriveWorldActing({ ...base, recent: record })).toMatchObject({
    state: 'success',
    context: { accomplished: true },
  });
  for (const [outcome, state] of [
    ['prepared', 'prepared'],
    ['failed', 'error'],
    ['waiting', 'waiting'],
    ['unknown', 'idle'],
    ['cancelled', 'idle'],
  ] as const) {
    const frame = deriveWorldActing({
      ...base,
      recent: { ...record, event: { ...record.event, outcome } },
    });
    expect(frame.state).toBe(state);
    expect(frame.eventKey).toBeNull();
    expect(frame.context.accomplished).toBe(false);
  }
  expect(
    deriveWorldActing({
      ...base,
      recent: { ...record, event: { ...record.event, intent: 'read' } },
    }).eventKey
  ).toBeNull();
});
it('rejects foreign owners/runs, future and expired evidence and stale background samples', () => {
  for (const patch of [{ signalOwnerId: 'other' }, { enabled: false }, { now: NaN }])
    expect(deriveWorldActing(input({ ...patch, recent: record }))).toMatchObject({
      state: 'idle',
      eventKey: null,
      pose: { expression: 'neutral' },
    });
  for (const patch of [{ runId: 'other' }, { now: 7000 }, { now: 999 }])
    expect(deriveWorldActing(input({ ...patch, recent: record })).eventKey).toBeNull();
  expect(deriveWorldActing(input({ background: { working: true, at: 1000 } })).state).toBe(
    'thinking'
  );
  expect(
    deriveWorldActing(input({ now: 16001, background: { working: true, at: 1000 } })).state
  ).toBe('idle');
});
it('keeps a failed current action visible while unrelated background work is running', () => {
  expect(
    deriveWorldActing(
      input({
        recent: { ...record, event: { ...record.event, outcome: 'failed' } },
        background: { working: true, at: 1000 },
      })
    ).state
  ).toBe('error');
});
it('expires the body accent before the longer completion label, including a delayed first sample', () => {
  expect(deriveWorldActing(input({ now: 1799, recent: record }))).toMatchObject({
    state: 'success',
    accentAlive: true,
    eventKey: 'run:step',
  });
  expect(deriveWorldActing(input({ now: 1800, recent: record }))).toMatchObject({
    state: 'success',
    accentAlive: false,
    eventKey: null,
  });
});
it('consumes each confirmed event once without turning a duplicate or a panel close into success', () => {
  const events = new WorldActingEvents();
  const frame = deriveWorldActing(input({ recent: record }));
  expect(events.take(frame.eventKey)).toBe(true);
  expect(events.take(frame.eventKey)).toBe(false);
  expect(events.take(null)).toBe(false);
  expect(deriveWorldActing(input()).eventKey).toBeNull();
  for (let i = 0; i < 1000; i++) events.take(String(i));
  expect(events.size).toBeLessThanOrEqual(128);
});
