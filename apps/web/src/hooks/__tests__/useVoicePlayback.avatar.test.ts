import { act, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import type { DecodedAudioOutput } from '@/lib/voice-output/types';
import type { AvatarEngineDeps } from '@/lib/avatars/engine';
import { AvatarEngine } from '@/lib/avatars/engine';
import { mountAvatarEngine } from '@/lib/avatars/runtime';
import { useVoicePlayback } from '../useVoicePlayback';

vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { voice_enabled: true } }) }));
const queue = vi.hoisted(() => ({ outputs: [] as (DecodedAudioOutput | null)[], enqueue: vi.fn(), stop: vi.fn() }));
vi.mock('@/lib/audio-queue', () => ({ AudioQueue: class {
  setOnPlaybackComplete() {} setOnError() {} setOnStateChange() {} dispose() {}
  stop = queue.stop; enqueue = queue.enqueue;
  setDecodedOutput(output: DecodedAudioOutput | null) { queue.outputs.push(output); }
} }));
let cleanup = () => {};
afterEach(() => { cleanup(); queue.outputs = []; vi.clearAllMocks(); });
it('keeps a cold response local, uses Simli for the next run, and interruption keeps the connection', async () => {
  let ready = false; let changed = () => {};
  const wire = { connect: vi.fn(async () => {}), close: vi.fn(), skip: vi.fn(), sendPcm: vi.fn(() => true) };
  const deps: AvatarEngineDeps = { api: { start: vi.fn(async () => ({ session_token: 'fixture', lease_id: 'lease', ice_servers: [], max_session_seconds: 3600 })),
    heartbeat: vi.fn(), release: vi.fn(async () => true) }, wire: () => wire,
    media: fn => { changed = fn; return { get ready() { return ready; }, clock: 0, quiet: true,
      video: vi.fn(), audio: vi.fn(), reset: vi.fn(), mute: vi.fn(), unlock: vi.fn(), attach: vi.fn(), begin: vi.fn() }; } };
  const engine = new AvatarEngine(deps);
  const unmount = mountAvatarEngine(engine); cleanup = () => { unmount(); engine.dispose(); };
  engine.setDemand({ account: 'a', credential: 'v', face: 'f', source: 'comments', connectSeconds: 15 });
  const { result } = renderHook(() => useVoicePlayback());
  await act(async () => { result.current.beginVoiceRun('cold'); for (let n = 0; n < 20; n++) await Promise.resolve(); });
  ready = true; act(() => changed());
  await act(async () => { await result.current.handleVoiceChunk({ audio_base64: 'QUJD', mime_type: 'audio/mpeg', phrase_index: 0, is_last: true }); });
  expect(queue.outputs.every(output => output === null)).toBe(true);
  act(() => result.current.beginVoiceRun('warm'));
  expect(queue.outputs.at(-1)).not.toBeNull();
  act(() => result.current.stopPlayback());
  expect(wire.skip).toHaveBeenCalled(); expect(wire.close).not.toHaveBeenCalled();
  expect(deps.api.start).toHaveBeenCalledTimes(1);
});
