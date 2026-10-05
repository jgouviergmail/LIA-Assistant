/**
 * ADR-324: LIA's spoken answers never play over the radio — chunks are dropped
 * while the station is on air (the answer stays written) and flow again once
 * it stops.
 */

import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { IDLE_RADIO_VIEW, useRadioStore } from '@/stores/radioStore';
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

const CHUNK: VoiceAudioChunk = {
  audio_base64: 'QUJD',
  phrase_index: 0,
  is_last: true,
  mime_type: 'audio/mpeg',
};

beforeEach(() => {
  queue.enqueue.mockClear();
  useRadioStore.getState().setView(IDLE_RADIO_VIEW);
});

afterEach(() => {
  useRadioStore.getState().setView(IDLE_RADIO_VIEW);
});

describe('useVoicePlayback while the radio plays', () => {
  it('keeps the answer written while the station is on air, and speaks again after', async () => {
    const { result } = renderHook(() => useVoicePlayback());
    act(() => {
      useRadioStore.getState().setView({ ...IDLE_RADIO_VIEW, status: 'playing', sessionId: 'r1' });
    });
    await act(async () => {
      await result.current.handleVoiceChunk(CHUNK);
    });
    expect(queue.enqueue).not.toHaveBeenCalled();

    act(() => {
      useRadioStore.getState().setView({ ...IDLE_RADIO_VIEW, status: 'ended', sessionId: 'r1' });
    });
    await act(async () => {
      await result.current.handleVoiceChunk(CHUNK);
    });
    expect(queue.enqueue).toHaveBeenCalledTimes(1);
  });
});
