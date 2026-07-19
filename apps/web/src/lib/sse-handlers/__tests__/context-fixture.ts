/**
 * Shared SSEHandlerContext fixture for handler tests.
 *
 * Mirrors the mutable-state wiring of useChat: `setProgressMessageId` /
 * `setNormalStreamInitialized` mutate a backing object read back through
 * getters, so multi-chunk scenarios observe state changes exactly like the
 * real per-chunk context rebuild does. The default `t` echoes the key
 * (consistent with the global react-i18next mock in setup.ts) and can be
 * overridden per test for branches that depend on translation values.
 */

import { vi, type Mock } from 'vitest';

import type { SSEHandlerContext } from '@/lib/sse-handlers/types';
import type { VoiceAudioChunk } from '@/types/chat';
import type { ExecutionTraceStep } from '@/types/execution-trace';

export interface FixtureOptions {
  /** Initial progress message id (default: null). */
  progressMessageId?: string | null;
  /** Initial normal-stream flag (default: false). */
  normalStreamInitialized?: boolean;
  /** Custom translation function (default: echoes the key). */
  t?: (key: string, opts?: Record<string, unknown>) => unknown;
  /** Replay mode — suppresses out-of-reducer side effects (default: false). */
  isReplay?: boolean;
}

export interface HandlerFixture {
  context: SSEHandlerContext;
  dispatch: Mock;
  handleVoiceChunk: Mock;
  /** Backing mutable state observed through the context getters. */
  state: { progressMessageId: string | null; normalStreamInitialized: boolean };
}

export function buildHandlerContext(options: FixtureOptions = {}): HandlerFixture {
  const dispatch = vi.fn();
  const handleVoiceChunk = vi.fn((_chunk: VoiceAudioChunk) => {});
  const state = {
    progressMessageId: options.progressMessageId ?? null,
    normalStreamInitialized: options.normalStreamInitialized ?? false,
  };

  const t = options.t ?? ((key: string) => key);

  const context = {
    dispatch,
    t,
    withContext: (extra?: Record<string, unknown>) => extra ?? {},
    handleVoiceChunk,
    hitlQuestionBuffer: { current: new Map<string, string>() },
    executionStepsRef: { current: [] as string[] },
    emittedStepKeysRef: { current: new Set<string>() },
    reasoningBufRef: { current: '' },
    traceStepsRef: { current: [] as ExecutionTraceStep[] },
    traceReasoningRef: { current: '' },
    assistantMessageId: 'assistant-1',
    get progressMessageId() {
      return state.progressMessageId;
    },
    setProgressMessageId: (id: string | null) => {
      state.progressMessageId = id;
    },
    get normalStreamInitialized() {
      return state.normalStreamInitialized;
    },
    setNormalStreamInitialized: (v: boolean) => {
      state.normalStreamInitialized = v;
    },
    isReplay: options.isReplay ?? false,
  } as unknown as SSEHandlerContext;

  return { context, dispatch, handleVoiceChunk, state };
}

/** Extract the payloads of every dispatched action of a given type. */
export function dispatchedOfType(dispatch: Mock, type: string): unknown[] {
  return dispatch.mock.calls
    .map(call => call[0] as { type: string; payload?: unknown })
    .filter(action => action.type === type)
    .map(action => action.payload);
}
