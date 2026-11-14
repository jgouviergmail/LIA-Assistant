/** Each mounted discussion owns its animation-frame buffer. */
import { createInstance } from 'i18next';
import { afterEach, expect, it, vi } from 'vitest';

import { createSSEProcessor, type SSEHandlerContext } from '@/lib/sse-handlers';

const timing = vi.hoisted(() => ({ record: vi.fn() }));
vi.mock('@/lib/product-telemetry', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/product-telemetry')>()),
  trackClientTiming: timing.record,
}));

function context(): SSEHandlerContext {
  return {
    dispatch: vi.fn(),
    t: createInstance().t,
    withContext: value => value ?? {},
    handleVoiceChunk: vi.fn(),
    hitlQuestionBuffer: { current: new Map() },
    executionStepsRef: { current: [] },
    emittedStepKeysRef: { current: new Set() },
    stepTalliesRef: { current: new Map() },
    reasoningBufRef: { current: '' },
    traceStepsRef: { current: [] },
    traceReasoningRef: { current: '' },
    assistantMessageId: 'assistant',
    progressMessageId: null,
    setProgressMessageId: vi.fn(),
    normalStreamInitialized: true,
    setNormalStreamInitialized: vi.fn(),
    isReplay: false,
  };
}

afterEach(() => vi.unstubAllGlobals());

it('resuming another discussion cannot erase the first-token measurement of an active send', () => {
  timing.record.mockClear();
  const sending = createSSEProcessor();
  const resuming = createSSEProcessor();
  sending.markChatTurnStarted();
  resuming.clearChatTurnTiming();
  sending.processSSEChunk({ type: 'token', content: 'answer' }, context());
  sending.resetTokenBatching();
  expect(timing.record).toHaveBeenCalledExactlyOnceWith('chat_first_token', expect.any(Number));
});

it('keeps interleaved tokens separate and cannot flush or drop a neighbour on cleanup', () => {
  vi.stubGlobal(
    'requestAnimationFrame',
    vi.fn(() => 1)
  );
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
  const left = createSSEProcessor();
  const right = createSSEProcessor();
  const a = context();
  const b = context();
  left.processSSEChunk({ type: 'token', content: 'A' }, a);
  right.processSSEChunk({ type: 'token', content: 'B' }, b);
  left.flushTokenBatching();
  expect(a.dispatch).toHaveBeenCalledWith({ type: 'STREAM_TOKEN', payload: { token: 'A' } });
  expect(b.dispatch).not.toHaveBeenCalled();
  left.resetTokenBatching();
  right.flushTokenBatching();
  expect(b.dispatch).toHaveBeenCalledWith({ type: 'STREAM_TOKEN', payload: { token: 'B' } });
  expect(a.dispatch).toHaveBeenCalledTimes(1);
});
