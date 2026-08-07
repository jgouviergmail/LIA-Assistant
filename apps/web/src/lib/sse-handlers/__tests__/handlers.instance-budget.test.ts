/**
 * sse-handlers — the instance spend ceiling is not the visitor's quota.
 *
 * A personal limit says "you reached your quota, contact your administrator".
 * When the whole deployment paused until the next UTC day, that sentence is
 * wrong on both counts, so the pause carries its own error code and its own
 * localized message.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { toast } from 'sonner';

import { handleError } from '@/lib/sse-handlers/handlers';
import type { ChatStreamChunk } from '@/types/chat';
import { buildHandlerContext, dispatchedOfType } from './context-fixture';

vi.mock('sonner', () => ({
  toast: Object.assign(vi.fn(), {
    error: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
    loading: vi.fn(),
    info: vi.fn(),
  }),
}));

vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe('instance budget exhausted', () => {
  it('shows the localized instance message, never the raw backend string', () => {
    const { context } = buildHandlerContext();

    handleError(
      {
        type: 'error',
        content: 'Instance daily budget exhausted',
        metadata: { error_code: 'instance_budget_exhausted' },
      } as ChatStreamChunk,
      context
    );

    // The backend sentence is technical and English-only; the visitor reads
    // the translated key instead.
    expect(toast.error).toHaveBeenCalledWith('errors.chat.instance_budget_exhausted');
    expect(toast.error).not.toHaveBeenCalledWith('Instance daily budget exhausted');
  });

  it('still records the stream error so the conversation shows the failure', () => {
    const { context, dispatch } = buildHandlerContext();

    handleError(
      {
        type: 'error',
        content: 'Instance daily budget exhausted',
        metadata: { error_code: 'instance_budget_exhausted' },
      } as ChatStreamChunk,
      context
    );

    expect(dispatchedOfType(dispatch, 'STREAM_ERROR')).toHaveLength(1);
  });

  it('stays silent on replay, like every other already-seen error', () => {
    const { context } = buildHandlerContext();

    handleError(
      {
        type: 'error',
        content: 'Instance daily budget exhausted',
        metadata: { error_code: 'instance_budget_exhausted' },
      } as ChatStreamChunk,
      { ...context, isReplay: true }
    );

    expect(toast.error).not.toHaveBeenCalled();
  });

  it('leaves the personal-limit toast untouched', () => {
    const { context } = buildHandlerContext();

    handleError(
      {
        type: 'error',
        content: 'Daily limit reached',
        metadata: { error_code: 'usage_limit_exceeded' },
      } as ChatStreamChunk,
      context
    );

    expect(toast.error).toHaveBeenCalledWith('Daily limit reached');
  });
});
