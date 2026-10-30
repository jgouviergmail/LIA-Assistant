/** The chat's first-token timing (spec 2026-10-21 O2): once per turn, never a progress step. */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { trackClientTiming } = vi.hoisted(() => ({ trackClientTiming: vi.fn() }));
vi.mock('@/lib/product-telemetry', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/product-telemetry')>()),
  trackClientTiming,
}));

import { clearChatTurnTiming, markChatTurnStarted } from '@/lib/journey-timing';
import { processSSEChunk, resetTokenBatching } from '@/lib/sse-handlers';
import { buildHandlerContext } from '@/lib/sse-handlers/__tests__/context-fixture';
import type { ChatStreamChunk } from '@/types/chat';

function token(content: string): ChatStreamChunk {
  return { type: 'token', content, metadata: null } as ChatStreamChunk;
}

const STEP = {
  type: 'execution_step',
  content: '',
  metadata: { step_type: 'node', i18n_key: 'router', emoji: '🧭' },
} as ChatStreamChunk;

beforeEach(() => {
  vi.resetAllMocks();
  resetTokenBatching();
  clearChatTurnTiming();
});

describe('chat first token timing', () => {
  it('emits chat_first_token once per turn and never for a progress step', () => {
    const { context } = buildHandlerContext();
    markChatTurnStarted();

    processSSEChunk(STEP, context);
    expect(trackClientTiming).not.toHaveBeenCalled();
    processSSEChunk(token('Hel'), context);
    processSSEChunk(token('lo'), context);

    expect(trackClientTiming).toHaveBeenCalledOnce();
    const [metric, seconds] = trackClientTiming.mock.calls[0];
    expect(metric).toBe('chat_first_token');
    expect(seconds).toBeGreaterThanOrEqual(0);

    markChatTurnStarted();
    processSSEChunk(token('Again'), context);
    expect(trackClientTiming).toHaveBeenCalledTimes(2);
  });

  it('measures nothing for a stream it did not start (a resumed run)', () => {
    const { context } = buildHandlerContext();
    markChatTurnStarted();
    clearChatTurnTiming();

    processSSEChunk(token('Resumed'), context);

    expect(trackClientTiming).not.toHaveBeenCalled();
  });
});
