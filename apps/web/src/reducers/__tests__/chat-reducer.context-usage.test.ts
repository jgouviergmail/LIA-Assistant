/**
 * Reducer tests for the context-usage pill (STREAM_DONE metadata).
 */

import { describe, it, expect } from 'vitest';

import { chatReducer } from '@/reducers/chat-reducer';
import { initialChatState, type ChatState } from '@/types/chat-state';

const baseState: ChatState = { ...initialChatState };

function streamDoneAction(metadataOverrides: Record<string, unknown> = {}) {
  return {
    type: 'STREAM_DONE' as const,
    payload: {
      messageId: 'm-1',
      metadata: {
        tokens_in: 100,
        tokens_out: 50,
        ...metadataOverrides,
      },
    },
  };
}

describe('chatReducer — contextUsage transitions (pill)', () => {
  it('stores contextUsage when STREAM_DONE carries context_tokens and context_threshold', () => {
    const s = chatReducer(baseState, streamDoneAction({
      context_tokens: 12_800,
      context_threshold: 51_200,
    }));
    expect(s.contextUsage).not.toBeNull();
    expect(s.contextUsage!.tokens).toBe(12_800);
    expect(s.contextUsage!.threshold).toBe(51_200);
    expect(s.contextUsage!.ratio).toBeCloseTo(0.25, 5);
  });

  it('clamps ratio at 1.5 when tokens overshoot the threshold', () => {
    const s = chatReducer(baseState, streamDoneAction({
      context_tokens: 200_000,
      context_threshold: 50_000,
    }));
    expect(s.contextUsage!.ratio).toBe(1.5);
  });

  it('keeps the previous contextUsage when metadata is missing those fields', () => {
    const seeded = chatReducer(baseState, streamDoneAction({
      context_tokens: 5_000,
      context_threshold: 20_000,
    }));
    expect(seeded.contextUsage).not.toBeNull();
    const next = chatReducer(seeded, streamDoneAction({})); // no context_* fields
    expect(next.contextUsage).toEqual(seeded.contextUsage);
  });

  it('ignores zero/negative thresholds defensively (no division blow-up)', () => {
    const s = chatReducer(baseState, streamDoneAction({
      context_tokens: 1000,
      context_threshold: 0,
    }));
    expect(s.contextUsage).toBeNull();
  });

  it('CLEAR_MESSAGES wipes contextUsage', () => {
    let s = chatReducer(baseState, streamDoneAction({
      context_tokens: 1_000,
      context_threshold: 10_000,
    }));
    expect(s.contextUsage).not.toBeNull();
    s = chatReducer(s, { type: 'CLEAR_MESSAGES' });
    expect(s.contextUsage).toBeNull();
  });

  it('CONTEXT_USAGE_HYDRATE seeds the pill from server totals payload', () => {
    const s = chatReducer(baseState, {
      type: 'CONTEXT_USAGE_HYDRATE',
      payload: { tokens: 38_400, threshold: 128_000 },
    });
    expect(s.contextUsage).not.toBeNull();
    expect(s.contextUsage!.tokens).toBe(38_400);
    expect(s.contextUsage!.threshold).toBe(128_000);
    expect(s.contextUsage!.ratio).toBeCloseTo(0.3, 5);
  });

  it('CONTEXT_USAGE_HYDRATE ignores zero / negative threshold defensively', () => {
    const s = chatReducer(baseState, {
      type: 'CONTEXT_USAGE_HYDRATE',
      payload: { tokens: 5_000, threshold: 0 },
    });
    expect(s.contextUsage).toBeNull();
  });
});
