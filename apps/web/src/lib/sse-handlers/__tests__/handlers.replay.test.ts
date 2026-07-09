/**
 * Replay-mode side-effect suppression (ADR-117 Lot 2).
 *
 * While reattaching to an in-flight background run, the backlog is replayed
 * through the normal handler pipeline: reducer dispatches MUST run (state
 * reconstruction) but out-of-reducer side effects (sonner toasts, voice
 * playback) MUST NOT fire — they already happened live, or are stale.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { toast } from 'sonner';

import {
  handleError,
  handleExecutionStep,
  handleVoiceAudioChunk,
} from '@/lib/sse-handlers/handlers';
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

beforeEach(() => {
  vi.clearAllMocks();
});

function compactionChunk(stepLabel: string, extra: Record<string, unknown> = {}): ChatStreamChunk {
  return {
    type: 'execution_step',
    content: '',
    metadata: { step_type: 'compaction', step_label: stepLabel, ...extra },
  };
}

describe('replay mode — compaction toasts suppressed, dispatches intact', () => {
  it('compaction_start: no loading toast, STREAM_COMPACTION_START dispatched', () => {
    const { context, dispatch } = buildHandlerContext({ isReplay: true });

    handleExecutionStep(
      compactionChunk('compaction_start', { estimated_duration_seconds: 30 }),
      context
    );

    expect(toast.loading).not.toHaveBeenCalled();
    expect(dispatchedOfType(dispatch, 'STREAM_COMPACTION_START')).toHaveLength(1);
  });

  it('compaction_done (success): no success toast, STREAM_COMPACTION_DONE dispatched', () => {
    const { context, dispatch } = buildHandlerContext({ isReplay: true });

    handleExecutionStep(
      compactionChunk('compaction_done', { tokens_saved: 100, strategy: 'multi_chunk' }),
      context
    );

    expect(toast.success).not.toHaveBeenCalled();
    expect(dispatchedOfType(dispatch, 'STREAM_COMPACTION_DONE')).toHaveLength(1);
  });

  it('compaction_done (truncation): no warning toast, dispatch intact', () => {
    const { context, dispatch } = buildHandlerContext({ isReplay: true });

    handleExecutionStep(compactionChunk('compaction_done', { strategy: 'truncation' }), context);

    expect(toast.warning).not.toHaveBeenCalled();
    expect(dispatchedOfType(dispatch, 'STREAM_COMPACTION_DONE')).toHaveLength(1);
  });

  it('live mode control: compaction_start still toasts', () => {
    const { context } = buildHandlerContext({ isReplay: false });

    handleExecutionStep(compactionChunk('compaction_start'), context);

    expect(toast.loading).toHaveBeenCalledTimes(1);
  });
});

describe('replay mode — stale voice chunks never play', () => {
  const voiceChunk: ChatStreamChunk = {
    type: 'voice_audio_chunk',
    content: {
      audio_base64: 'QUJD',
      phrase_index: 0,
      is_last: false,
    } as unknown as ChatStreamChunk['content'],
    metadata: null,
  };

  it('replay: handleVoiceChunk is not invoked', () => {
    const { context, handleVoiceChunk } = buildHandlerContext({ isReplay: true });

    handleVoiceAudioChunk(voiceChunk, context);

    expect(handleVoiceChunk).not.toHaveBeenCalled();
  });

  it('live: handleVoiceChunk is invoked', () => {
    const { context, handleVoiceChunk } = buildHandlerContext({ isReplay: false });

    handleVoiceAudioChunk(voiceChunk, context);

    expect(handleVoiceChunk).toHaveBeenCalledTimes(1);
  });
});

describe('replay mode — usage-limit toast suppressed, error dispatch intact', () => {
  const errorChunk: ChatStreamChunk = {
    type: 'error',
    content: 'Usage limit exceeded',
    metadata: { error_code: 'usage_limit_exceeded' },
  };

  it('replay: no toast.error, STREAM_ERROR dispatched', () => {
    const { context, dispatch } = buildHandlerContext({ isReplay: true });

    handleError(errorChunk, context);

    expect(toast.error).not.toHaveBeenCalled();
    expect(dispatchedOfType(dispatch, 'STREAM_ERROR')).toHaveLength(1);
  });

  it('live: toast.error fires', () => {
    const { context } = buildHandlerContext({ isReplay: false });

    handleError(errorChunk, context);

    expect(toast.error).toHaveBeenCalledTimes(1);
  });
});
