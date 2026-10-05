/**
 * ADR-258: LIA never speaks into a meeting being recorded — chunks are dropped
 * while a capture is open and flow again once it closes.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';

import { useMeetingRecorderStore } from '@/stores/meetingRecorderStore';
import type { VoiceAudioChunk } from '@/types/chat';

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { voice_enabled: true } }),
}));

const queue = vi.hoisted(() => ({ enqueue: vi.fn(async () => undefined) }));
vi.mock('@/lib/audio-queue', () => ({
  AudioQueue: class {
    setOnPlaybackComplete() {}
    setOnError() {}
    setOnStateChange() {}
    setDecodedOutput() {}
    enqueue = queue.enqueue;
    dispose() {}
    stop() {}
    clear() {}
    resume() {}
    warmup() {}
  },
}));
vi.mock('@/lib/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

import { useVoicePlayback } from '../useVoicePlayback';

beforeEach(() => {
  queue.enqueue.mockClear();
  useMeetingRecorderStore.getState().reset();
});

afterEach(() => {
  useMeetingRecorderStore.getState().reset();
});

describe('useVoicePlayback while a meeting records', () => {
  const chunk: VoiceAudioChunk = { audio_base64: 'QUJD', mime_type: 'audio/mpeg', phrase_index: 0, is_last: true };
  it('drops spoken answers during a capture and speaks again afterwards', async () => {
    const { result } = renderHook(() => useVoicePlayback());
    act(() => {
      useMeetingRecorderStore.getState().setPhase('recording');
    });
    await act(async () => {
      await result.current.handleVoiceChunk(chunk);
    });
    expect(queue.enqueue).not.toHaveBeenCalled();

    act(() => {
      useMeetingRecorderStore.getState().reset();
    });
    await act(async () => {
      await result.current.handleVoiceChunk(chunk);
    });
    expect(queue.enqueue).toHaveBeenCalledTimes(1);
  });
});
