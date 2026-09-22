import { beforeEach, describe, expect, it } from 'vitest';
import { handleDone, handleExecutionStep } from '../handlers';
import { buildHandlerContext } from './context-fixture';
import { useEyesSignalsStore as signals } from '@/stores/eyesSignalsStore';
import type { Activity } from '@/components/eyes/activity';

const activity: Activity = {
  version: 1,
  run_id: 'r',
  invocation_id: 'i',
  family: 'communicating',
  intent: 'prepare',
  phase: 'started',
  outcome: null,
};

beforeEach(() => signals.getState().reset());

describe('execution stream to companion', () => {
  it('ignores an incomplete activity envelope and replayed reasoning', () => {
    const { context, dispatch } = buildHandlerContext({ isReplay: true });
    signals.getState().beginTurn(context.assistantMessageId);
    handleExecutionStep(
      { type: 'execution_step', content: '', metadata: { step_type: 'activity' } },
      context
    );
    expect(dispatch).not.toHaveBeenCalled();
    handleExecutionStep(
      {
        type: 'execution_step',
        content: '',
        metadata: { step_type: 'reasoning', message: 'Planning a call' },
      },
      context
    );
    expect(signals.getState().lastStepKind).toBeNull();
    expect(signals.getState().activities).toEqual([]);
  });
  it('consumes only actual evidence, independently of the progress message', () => {
    const { context, dispatch } = buildHandlerContext();
    signals.getState().beginTurn(context.assistantMessageId);
    handleExecutionStep(
      { type: 'execution_step', content: '', metadata: { step_type: 'activity', activity } },
      context
    );
    expect(signals.getState().liveActivity(Date.now())).toEqual(activity);
    expect(dispatch).not.toHaveBeenCalled();
    handleExecutionStep(
      {
        type: 'execution_step',
        content: '',
        metadata: {
          step_type: 'activity',
          activity: { ...activity, phase: 'finished', outcome: 'prepared' },
        },
      },
      context
    );
    expect(signals.getState().liveActivity(Date.now())).toBeNull();
    expect(signals.getState().lastActivity?.event.outcome).toBe('prepared');
    handleDone({ type: 'done', content: '', metadata: {} }, context);
    expect(signals.getState().completedAnswerId).toBe(context.assistantMessageId);
  });

  it.each([true, false])('rejects malformed evidence and suppresses replay=%s', isReplay => {
    const { context } = buildHandlerContext({ isReplay });
    signals.getState().beginTurn(context.assistantMessageId);
    for (const payload of [null, { ...activity, version: 2 }, { ...activity, phase: 'finished' }]) {
      handleExecutionStep(
        {
          type: 'execution_step',
          content: '',
          metadata: { step_type: 'activity', activity: payload },
        },
        context
      );
    }
    expect(signals.getState().activities).toEqual([]);
    if (isReplay) {
      handleExecutionStep(
        { type: 'execution_step', content: '', metadata: { step_type: 'activity', activity } },
        context
      );
      handleDone({ type: 'done', content: '', metadata: {} }, context);
      expect(signals.getState().activities).toEqual([]);
      expect(signals.getState().completedAnswerId).toBeNull();
    }
  });

  it('does not confirm an interrupted turn or accept a previous run', () => {
    const { context } = buildHandlerContext();
    signals.getState().beginTurn('new-answer');
    handleExecutionStep(
      { type: 'execution_step', content: '', metadata: { step_type: 'activity', activity } },
      context
    );
    handleDone({ type: 'done', content: '', metadata: { cancelled: true } }, context);
    expect(signals.getState().activities).toEqual([]);
    expect(signals.getState().completedAnswerId).toBeNull();
  });
});
