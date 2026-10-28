import { act, renderHook } from '@testing-library/react';
import { beforeEach, expect, it } from 'vitest';
import { useEyesChatStore, RESTING_CHAT } from '@/stores/eyesChatStore';
import { useEyesSignalsStore } from '@/stores/eyesSignalsStore';
import { useCompanionActivityStore } from '@/stores/companionActivityStore';
import { useWorldActingSource } from '../useWorldActingSource';
import { useLiveStore } from '@/stores/liveStore';
beforeEach(() => {
  // Each test starts from pristine eyes and Live stores: no evidence leaks between tests.
  useEyesChatStore.setState(useEyesChatStore.getInitialState(), true);
  useEyesSignalsStore.setState(useEyesSignalsStore.getInitialState(), true);
  useLiveStore.setState(useLiveStore.getInitialState(), true);
  useCompanionActivityStore.getState().bindOwner(null);
});
it('uses current Live evidence and prefers newer chat evidence without claiming a read as an action', () => {
  const { result } = renderHook(() => useWorldActingSource('owner', true));
  const now = Date.now();
  const event = {
    version: 1 as const,
    run_id: 'live-run',
    invocation_id: 'read',
    family: 'reading' as const,
    intent: 'read' as const,
    phase: 'finished' as const,
    outcome: 'succeeded' as const,
  };
  act(() => useLiveStore.setState({ sessionId: 'current-live', lastActivity: { at: now, event } }));
  expect(result.current(now)).toMatchObject({
    eventKey: null,
    context: { recentFamily: 'reading', accomplished: false },
  });
  act(() => useLiveStore.setState({ sessionId: null }));
  expect(result.current(now).context.recentFamily).toBeNull();
  act(() => {
    useLiveStore.setState({ sessionId: 'current-live', lastActivity: { at: now, event } });
    const signals = useEyesSignalsStore.getState();
    signals.beginTurn('answer');
    signals.recordActivity(
      { ...event, run_id: 'chat-run', family: 'creating', intent: 'prepare', outcome: 'prepared' },
      'answer',
      false,
      now + 1
    );
  });
  expect(result.current(now + 1)).toMatchObject({
    state: 'prepared',
    context: { recentFamily: 'creating', accomplished: false },
  });
  act(() => useLiveStore.setState({ sessionId: null, lastActivity: null }));
});
it('reads embedded native phases/playback on the existing clock and fences retained callbacks', () => {
  const { result, rerender, unmount } = renderHook(
    ({ enabled }) => useWorldActingSource('owner', enabled),
    { initialProps: { enabled: true } }
  );
  const source = result.current;
  act(() =>
    useEyesChatStore.getState().publish({ ...RESTING_CHAT, chatStatus: 'streaming' }, 'owner')
  );
  expect(source(Date.now()).state).toBe('responding');
  act(() => useEyesSignalsStore.getState().setAudioPlaying(true));
  expect(source(Date.now()).state).toBe('speaking');
  act(() => useEyesSignalsStore.getState().setAudioPlaying(false));
  expect(source(Date.now()).state).toBe('responding');
  rerender({ enabled: false });
  expect(source(Date.now()).state).toBe('idle');
  unmount();
  expect(source(Date.now()).state).toBe('idle');
});
it('drops prior-account evidence and consumes a fresh confirmed completion only once', () => {
  const { result, rerender } = renderHook(({ owner }) => useWorldActingSource(owner, true), {
    initialProps: { owner: 'one' },
  });
  const old = result.current;
  const finishedAt = Date.now();
  act(() => {
    const store = useEyesSignalsStore.getState();
    store.beginTurn('answer');
    store.recordActivity(
      {
        version: 1,
        run_id: 'run',
        invocation_id: 'step',
        family: 'creating',
        intent: 'act',
        phase: 'finished',
        outcome: 'succeeded',
      },
      'answer',
      false,
      finishedAt
    );
  });
  expect(result.current(finishedAt).eventKey).toBe('run:step');
  expect(result.current(finishedAt).eventKey).toBeNull();
  rerender({ owner: 'two' });
  expect(old(Date.now()).state).toBe('idle');
  expect(result.current(Date.now()).eventKey).toBeNull();
  expect(useEyesSignalsStore.getState().lastActivity).toBeNull();
  act(() => useCompanionActivityStore.getState().record('one', true));
  expect(result.current(Date.now()).state).toBe('idle');
  const now = Date.now();
  act(() => useCompanionActivityStore.getState().record('two', true, now));
  expect(result.current(now).state).toBe('thinking');
  expect(result.current(now + 15001).state).toBe('idle');
});
