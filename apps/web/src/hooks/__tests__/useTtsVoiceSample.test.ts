/** A selected TTS voice owns one abortable audio session; obsolete work stays silent. */
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ post: vi.fn() }));
const account = vi.hoisted(() => ({ id: 'account-a' as string | undefined }));
vi.mock('@/lib/api-client', () => ({ default: api }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: account.id } }) }));
const radio = vi.hoisted(() => ({ pause: vi.fn() }));
vi.mock('@/lib/radio/player', () => ({ radioPlayer: () => ({ pause: radio.pause }) }));

import { useLiveStore } from '@/stores/liveStore';
import { useMeetingRecorderStore } from '@/stores/meetingRecorderStore';
import { IDLE_RADIO_VIEW, useRadioStore } from '@/stores/radioStore';

import { useTtsVoiceSample, type TtsVoiceSampleRequest } from '../useTtsVoiceSample';

const chosen: TtsVoiceSampleRequest = {
  endpoint: '/voice/lia-voices/sample',
  payload: { gender: 'female', voice_id: 'voice-a' },
};
const WAV = { audio_base64: btoa('RIFF....WAVEfmt '), mime_type: 'audio/wav', voice_id: 'voice-a' };
const nextPlay = vi.fn<() => Promise<void>>();
const revoke = vi.fn();
const create = vi.fn();

class FakeAudio {
  static instances: FakeAudio[] = [];
  src = '';
  onended: (() => void) | null = null;
  onerror: (() => void) | null = null;
  play = vi.fn(() => nextPlay());
  pause = vi.fn();
  removeAttribute = vi.fn((name: string) => {
    if (name === 'src') this.src = '';
  });
  load = vi.fn();
  constructor() {
    FakeAudio.instances.push(this);
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((accept, refuse) => {
    resolve = accept;
    reject = refuse;
  });
  return { promise, resolve, reject };
}

beforeEach(() => {
  account.id = 'account-a';
  api.post.mockReset().mockResolvedValue(WAV);
  nextPlay.mockReset().mockResolvedValue(undefined);
  create.mockReset().mockImplementation(() => `blob:voice-${create.mock.calls.length}`);
  revoke.mockReset();
  FakeAudio.instances = [];
  useLiveStore.setState({ status: 'idle' });
  useMeetingRecorderStore.setState({ phase: 'idle' });
  useRadioStore.setState({ view: { ...IDLE_RADIO_VIEW } });
  radio.pause.mockReset().mockImplementation(() => {
    useRadioStore.setState({ view: { ...useRadioStore.getState().view, status: 'paused' } });
  });
  vi.stubGlobal('Audio', FakeAudio);
  vi.stubGlobal('URL', { ...URL, createObjectURL: create, revokeObjectURL: revoke });
});

afterEach(() => vi.unstubAllGlobals());

describe('useTtsVoiceSample', () => {
  it('stays silent until an explicit selection and primes the same media inside the gesture', async () => {
    const response = deferred<typeof WAV>();
    api.post.mockReturnValue(response.promise);
    const { result } = renderHook(() => useTtsVoiceSample());
    expect(api.post).not.toHaveBeenCalled();
    expect(FakeAudio.instances).toHaveLength(0);
    expect(result.current.canReplay).toBe(false);

    let pending!: Promise<void>;
    act(() => {
      pending = result.current.play(chosen);
      expect(FakeAudio.instances).toHaveLength(1);
      expect(FakeAudio.instances[0].play).toHaveBeenCalledTimes(1);
      expect(FakeAudio.instances[0].src).toMatch(/^data:audio\/wav;base64,/);
      expect(FakeAudio.instances[0].onended).toBeNull();
      expect(FakeAudio.instances[0].onerror).toBeNull();
    });
    expect(result.current.status).toBe('loading');
    await waitFor(() => expect(api.post).toHaveBeenCalledOnce());
    expect(api.post).toHaveBeenCalledWith(chosen.endpoint, chosen.payload, {
      signal: expect.any(AbortSignal),
    });
    await act(async () => {
      response.resolve(WAV);
      await pending;
    });
    expect(FakeAudio.instances).toHaveLength(1);
    expect(FakeAudio.instances[0].src).toBe('blob:voice-1');
    expect(FakeAudio.instances[0].play).toHaveBeenCalledTimes(2);
    expect(result.current.status).toBe('playing');
    expect(radio.pause).not.toHaveBeenCalled();
  });

  it('passes the complete radio voice draft without inventing a provider or text', async () => {
    const radio: TtsVoiceSampleRequest = {
      endpoint: '/radio/voices/sample',
      payload: { role: 'speaker_b', voices: { host: 'host', anchor: 'anchor', speaker_a: 'one' } },
    };
    const { result } = renderHook(() => useTtsVoiceSample());
    await act(() => result.current.play(radio));
    expect(api.post).toHaveBeenCalledWith(radio.endpoint, radio.payload, {
      signal: expect.any(AbortSignal),
    });
  });

  it('aborts superseded synthesis and ignores its response even when the transport ignores abort', async () => {
    const first = deferred<typeof WAV>();
    api.post.mockReturnValueOnce(first.promise);
    const { result } = renderHook(() => useTtsVoiceSample());
    let obsolete!: Promise<void>;
    act(() => {
      obsolete = result.current.play(chosen);
    });
    const oldAudio = FakeAudio.instances[0];
    await waitFor(() => expect(api.post).toHaveBeenCalledOnce());
    const signal = api.post.mock.calls[0][2].signal as AbortSignal;
    await act(() =>
      result.current.play({ ...chosen, payload: { gender: 'female', voice_id: 'voice-b' } })
    );
    expect(signal.aborted).toBe(true);
    expect(oldAudio.src).toBe('');
    await act(async () => {
      first.resolve(WAV);
      await obsolete;
    });
    expect(create).toHaveBeenCalledTimes(1);
    expect(FakeAudio.instances[1].src).toBe('blob:voice-1');
    expect(result.current.status).toBe('playing');
  });

  it('a rejected obsolete synthesis cannot overwrite the current playback', async () => {
    const first = deferred<typeof WAV>();
    api.post.mockReturnValueOnce(first.promise);
    const { result } = renderHook(() => useTtsVoiceSample());
    let obsolete!: Promise<void>;
    act(() => {
      obsolete = result.current.play(chosen);
    });
    await waitFor(() => expect(api.post).toHaveBeenCalledOnce());
    await act(() => result.current.play(chosen));
    await act(async () => {
      first.reject(new Error('old failure'));
      await obsolete;
    });
    expect(result.current.status).toBe('playing');
  });

  it('stops and releases playback exactly once, retaining the last choice for explicit replay', async () => {
    const { result, unmount } = renderHook(() => useTtsVoiceSample());
    await act(() => result.current.play(chosen));
    const audio = FakeAudio.instances[0];
    const ended = audio.onended;
    act(() => result.current.stop());
    act(() => ended?.());
    expect(result.current.status).toBe('idle');
    expect(result.current.canReplay).toBe(true);
    expect(audio.src).toBe('');
    expect(audio.onended).toBeNull();
    expect(audio.onerror).toBeNull();
    expect(revoke.mock.calls).toEqual([['blob:voice-1']]);
    unmount();
    expect(revoke).toHaveBeenCalledTimes(1);
  });

  it('natural completion and old media events cannot stop a newer sample', async () => {
    const { result } = renderHook(() => useTtsVoiceSample());
    await act(() => result.current.play(chosen));
    const ended = FakeAudio.instances[0].onended;
    act(() => ended?.());
    expect(result.current.status).toBe('idle');
    await act(() => result.current.replay());
    act(() => ended?.());
    expect(result.current.status).toBe('playing');
    expect(api.post).toHaveBeenCalledTimes(2);
  });

  it('a failed synthesis stays local and can be retried without selecting or saving again', async () => {
    api.post.mockRejectedValueOnce(new Error('unavailable'));
    const { result } = renderHook(() => useTtsVoiceSample());
    await act(() => result.current.play(chosen));
    expect(result.current.status).toBe('error');
    expect(result.current.canReplay).toBe(true);
    expect(FakeAudio.instances[0].src).toBe('');
    await act(() => result.current.replay());
    expect(api.post).toHaveBeenNthCalledWith(2, chosen.endpoint, chosen.payload, {
      signal: expect.any(AbortSignal),
    });
    expect(result.current.status).toBe('playing');
  });

  it('a media decode error releases the URL and exposes one local error', async () => {
    const { result } = renderHook(() => useTtsVoiceSample());
    await act(() => result.current.play(chosen));
    const audio = FakeAudio.instances[0];
    const failed = audio.onerror;
    act(() => failed?.());
    act(() => failed?.());
    expect(result.current.status).toBe('error');
    expect(revoke.mock.calls).toEqual([['blob:voice-1']]);
    expect(audio.src).toBe('');
  });

  it('a rejected playback permission releases the URL and keeps replay available', async () => {
    nextPlay
      .mockResolvedValueOnce(undefined)
      .mockRejectedValueOnce(new DOMException('gesture', 'NotAllowedError'));
    const { result } = renderHook(() => useTtsVoiceSample());
    await act(() => result.current.play(chosen));
    expect(result.current.status).toBe('error');
    expect(result.current.canReplay).toBe(true);
    expect(revoke.mock.calls).toEqual([['blob:voice-1']]);
    expect(FakeAudio.instances[0].src).toBe('');
  });

  it.each(['resolve', 'reject'] as const)(
    'unmount aborts synthesis and ignores its late %s',
    async verdict => {
      const response = deferred<typeof WAV>();
      api.post.mockReturnValueOnce(response.promise);
      const { result, unmount } = renderHook(() => useTtsVoiceSample());
      let pending!: Promise<void>;
      act(() => {
        pending = result.current.play(chosen);
      });
      await waitFor(() => expect(api.post).toHaveBeenCalledOnce());
      const signal = api.post.mock.calls[0][2].signal as AbortSignal;
      unmount();
      expect(signal.aborted).toBe(true);
      await act(async () => {
        if (verdict === 'resolve') response.resolve(WAV);
        else response.reject(new Error('late error'));
        await pending;
      });
      expect(create).not.toHaveBeenCalled();
      expect(FakeAudio.instances[0].src).toBe('');
    }
  );

  it.each(['resolve', 'reject'] as const)(
    'ignores a playback promise that %ss after a newer selection',
    async verdict => {
      const playback = deferred<void>();
      nextPlay.mockResolvedValueOnce(undefined).mockReturnValueOnce(playback.promise);
      const { result } = renderHook(() => useTtsVoiceSample());
      let pending!: Promise<void>;
      act(() => {
        pending = result.current.play(chosen);
      });
      await act(async () => {
        await Promise.resolve();
      });
      await act(() => result.current.play(chosen));
      await act(async () => {
        if (verdict === 'resolve') playback.resolve();
        else playback.reject(new Error('old permission'));
        await pending;
      });
      expect(result.current.status).toBe('playing');
      expect(revoke.mock.calls).toEqual([['blob:voice-1']]);
    }
  );

  it('changing account releases playback, hides its choice and rejects retained callbacks', async () => {
    const { result, rerender } = renderHook(() => useTtsVoiceSample());
    await act(() => result.current.play(chosen));
    const oldReplay = result.current.replay;
    const oldPlay = result.current.play;
    const oldStop = result.current.stop;
    account.id = 'account-b';
    rerender();
    expect(result.current.status).toBe('idle');
    expect(result.current.canReplay).toBe(false);
    expect(FakeAudio.instances[0].src).toBe('');
    await act(() => oldReplay());
    await act(() => oldPlay(chosen));
    expect(api.post).toHaveBeenCalledTimes(1);
    await act(() => result.current.play(chosen));
    act(() => oldStop());
    expect(result.current.status).toBe('playing');
    expect(FakeAudio.instances[1].src).toBe('blob:voice-2');
    account.id = 'account-a';
    rerender();
    expect(result.current.canReplay).toBe(false);
  });

  it.each(['meeting', 'live'] as const)(
    'does not synthesize or prime over an active %s capture',
    async source => {
      if (source === 'meeting') useMeetingRecorderStore.setState({ phase: 'recording' });
      else useLiveStore.setState({ status: 'live' });
      const { result } = renderHook(() => useTtsVoiceSample());
      await act(() => result.current.play(chosen));
      expect(result.current.status).toBe('blocked');
      expect(result.current.canReplay).toBe(true);
      expect(api.post).not.toHaveBeenCalled();
      expect(FakeAudio.instances).toHaveLength(0);
    }
  );

  it.each(['starting', 'ending'] as const)(
    'does not synthesize or prime while radio is %s',
    async status => {
      useRadioStore.setState({ view: { ...IDLE_RADIO_VIEW, status } });
      const { result } = renderHook(() => useTtsVoiceSample());
      await act(() => result.current.play(chosen));
      expect(result.current.status).toBe('radio_wait');
      expect(api.post).not.toHaveBeenCalled();
      expect(FakeAudio.instances).toHaveLength(0);
    }
  );

  it('pauses an existing antenna for the sample and leaves resumption to the listener', async () => {
    useRadioStore.setState({ view: { ...IDLE_RADIO_VIEW, status: 'playing' } });
    const { result } = renderHook(() => useTtsVoiceSample());
    await act(() => result.current.play(chosen));
    expect(radio.pause).toHaveBeenCalledOnce();
    expect(useRadioStore.getState().view.status).toBe('paused');
    expect(result.current.status).toBe('playing');
    expect(result.current.radioPaused).toBe(true);
    act(() => result.current.stop());
    expect(useRadioStore.getState().view.status).toBe('paused');
  });

  it.each(['meeting', 'live', 'radio'] as const)(
    'releases audio when %s starts during a sample',
    async source => {
      const { result } = renderHook(() => useTtsVoiceSample());
      await act(() => result.current.play(chosen));
      act(() => {
        if (source === 'meeting') useMeetingRecorderStore.setState({ phase: 'recording' });
        else if (source === 'live') useLiveStore.setState({ status: 'live' });
        else useRadioStore.setState({ view: { ...IDLE_RADIO_VIEW, status: 'playing' } });
      });
      expect(result.current.status).toBe(source === 'radio' ? 'idle' : 'blocked');
      expect(FakeAudio.instances[0].src).toBe('');
      expect(revoke).toHaveBeenCalledOnce();
    }
  );
});
