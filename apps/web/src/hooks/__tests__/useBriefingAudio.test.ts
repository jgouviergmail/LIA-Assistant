/**
 * Briefing audio belongs to one mounted account lifetime. Tests keep the real
 * hook and auth context, delaying each external audio boundary independently.
 */

import { createElement, type ContextType, type ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

import { makeUser } from '@/__tests__/factories';
import { AuthContext, type User } from '@/lib/auth';
import { useBriefingAudio } from '../useBriefingAudio';

const nextPlay = vi.fn<() => Promise<void>>();

class FakeAudio {
  static instances: FakeAudio[] = [];
  src: string;
  onended: (() => void) | null = null;
  paused = true;
  play = vi.fn(() => {
    this.paused = false;
    return nextPlay();
  });
  pause = vi.fn(() => {
    this.paused = true;
  });
  removeAttribute = vi.fn((name: string) => {
    if (name === 'src') this.src = '';
  });
  load = vi.fn();
  constructor(src: string) {
    this.src = src;
    FakeAudio.instances.push(this);
  }
}

const fetchMock = vi.fn<typeof fetch>();
const revokeMock = vi.fn<(url: string) => void>();
const createMock = vi.fn<(blob: Blob) => string>();
let currentUser: User | null;

function Session({ children }: { children: ReactNode }) {
  const auth: NonNullable<ContextType<typeof AuthContext>> = {
    user: currentUser,
    isLoading: false,
    login: vi.fn(),
    verifyMfa: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    initiateGoogleOAuth: vi.fn(),
    completeNativeSignIn: vi.fn(),
    refreshUser: vi.fn(),
  };
  return createElement(AuthContext.Provider, { value: auth }, children);
}

function mountAudio() {
  return renderHook(() => useBriefingAudio(), { wrapper: Session });
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

function audioResponse() {
  return new Response(new Uint8Array([1, 2, 3]), {
    headers: { 'Content-Type': 'audio/mpeg' },
  });
}

function audioOk() {
  fetchMock.mockResolvedValue(audioResponse());
}

function expectNoPlayback() {
  expect(FakeAudio.instances).toHaveLength(0);
  expect(nextPlay).not.toHaveBeenCalled();
  expect(createMock).not.toHaveBeenCalled();
}

beforeEach(() => {
  currentUser = makeUser({ id: 'account-a' });
  FakeAudio.instances = [];
  fetchMock.mockReset();
  revokeMock.mockReset();
  nextPlay.mockReset().mockResolvedValue(undefined);
  let serial = 0;
  createMock.mockReset().mockImplementation(() => `blob:audio-${++serial}`);
  vi.stubGlobal('Audio', FakeAudio);
  vi.stubGlobal('fetch', fetchMock);
  vi.stubGlobal('URL', {
    ...URL,
    createObjectURL: createMock,
    revokeObjectURL: revokeMock,
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('useBriefingAudio', () => {
  it('fetches the displayed audio with credentials, an abort signal and the requested voice', async () => {
    audioOk();
    const { result } = mountAudio();

    await act(() => result.current.toggle('Bonjour, voici votre journée.', 'female'));

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/api/v1/briefing/synthesis/audio');
    expect(String(url)).not.toContain('/api/v1/api/v1');
    expect(init).toEqual(
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        signal: expect.any(AbortSignal),
        body: JSON.stringify({ text: 'Bonjour, voici votre journée.', lia_gender: 'female' }),
      })
    );
    expect(result.current.playing).toBe(true);
    expect(result.current.loading).toBe(false);
    expect(FakeAudio.instances[0].play).toHaveBeenCalledTimes(1);
  });

  it('second press stops playback and releases the exact URL only once', async () => {
    audioOk();
    const { result, unmount } = mountAudio();
    await act(() => result.current.toggle('texte'));
    const audio = FakeAudio.instances[0];
    const ended = audio.onended;

    await act(() => result.current.toggle('texte'));
    act(() => ended?.());
    unmount();

    expect(audio.pause).toHaveBeenCalledTimes(1);
    expect(audio.onended).toBeNull();
    expect(audio.src).toBe('');
    expect(revokeMock.mock.calls).toEqual([['blob:audio-1']]);
    expect(result.current.playing).toBe(false);
    expect(result.current.loading).toBe(false);
  });

  it('natural completion releases playback and cannot stop a later audio session', async () => {
    audioOk();
    const { result, unmount } = mountAudio();
    await act(() => result.current.toggle('premier'));
    const ended = FakeAudio.instances[0].onended;
    act(() => ended?.());

    expect(result.current.playing).toBe(false);
    expect(revokeMock.mock.calls).toEqual([['blob:audio-1']]);
    fetchMock.mockResolvedValueOnce(audioResponse());
    await act(() => result.current.toggle('second'));
    act(() => ended?.());

    expect(result.current.playing).toBe(true);
    expect(FakeAudio.instances[1].paused).toBe(false);
    expect(revokeMock.mock.calls).toEqual([['blob:audio-1']]);
    unmount();
    expect(revokeMock.mock.calls).toEqual([['blob:audio-1'], ['blob:audio-2']]);
  });

  it('a failed fetch surfaces an error and a later explicit attempt clears it', async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 500 }));
    const { result } = mountAudio();
    await act(() => result.current.toggle('texte'));

    expect(result.current.error).toBe(true);
    expect(result.current.playing).toBe(false);
    expect(result.current.loading).toBe(false);
    expectNoPlayback();

    audioOk();
    await act(() => result.current.toggle('retry'));
    expect(result.current.error).toBe(false);
    expect(result.current.playing).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('unmount stops playback, detaches its handler and revokes the exact URL once', async () => {
    audioOk();
    const { result, unmount } = mountAudio();
    await act(() => result.current.toggle('texte'));
    const audio = FakeAudio.instances[0];
    const ended = audio.onended;
    unmount();
    act(() => ended?.());

    expect(audio.paused).toBe(true);
    expect(audio.onended).toBeNull();
    expect(audio.src).toBe('');
    expect(revokeMock.mock.calls).toEqual([['blob:audio-1']]);
  });

  it('aborts a pending fetch on unmount and ignores its late response', async () => {
    const response = deferred<Response>();
    fetchMock.mockReturnValue(response.promise);
    const { result, unmount } = mountAudio();
    let pending!: Promise<void>;
    act(() => {
      pending = result.current.toggle('private text');
    });
    const signal = fetchMock.mock.calls[0][1]?.signal;
    unmount();
    expect(signal?.aborted).toBe(true);

    await act(async () => {
      response.resolve(audioResponse());
      await pending;
    });

    expectNoPlayback();
    expect(revokeMock).not.toHaveBeenCalled();
  });

  it('does not create an audio or object URL when a blob resolves after unmount', async () => {
    const blob = deferred<Blob>();
    const response = audioResponse();
    const readBlob = vi.spyOn(response, 'blob').mockReturnValue(blob.promise);
    fetchMock.mockResolvedValue(response);
    const { result, unmount } = mountAudio();
    let pending!: Promise<void>;
    act(() => {
      pending = result.current.toggle('private text');
    });
    await waitFor(() => expect(readBlob).toHaveBeenCalledTimes(1));
    unmount();
    await act(async () => {
      blob.resolve(new Blob(['audio']));
      await pending;
    });

    expectNoPlayback();
    expect(revokeMock).not.toHaveBeenCalled();
  });

  it.each(['resolve', 'reject'] as const)(
    'ignores a play promise that %ss after unmount',
    async verdict => {
      const play = deferred<void>();
      nextPlay.mockReturnValueOnce(play.promise);
      audioOk();
      const { result, unmount } = mountAudio();
      let pending!: Promise<void>;
      act(() => {
        pending = result.current.toggle('private text');
      });
      await waitFor(() => expect(nextPlay).toHaveBeenCalledTimes(1));
      const audio = FakeAudio.instances[0];
      unmount();
      expect(audio.paused).toBe(true);
      expect(revokeMock.mock.calls).toEqual([['blob:audio-1']]);

      await act(async () => {
        if (verdict === 'resolve') play.resolve();
        else play.reject(new Error('play cancelled'));
        await pending;
      });

      expect(audio.paused).toBe(true);
      expect(audio.onended).toBeNull();
      expect(createMock).toHaveBeenCalledTimes(1);
      expect(nextPlay).toHaveBeenCalledTimes(1);
      expect(revokeMock.mock.calls).toEqual([['blob:audio-1']]);
    }
  );

  it('synchronously treats a second press as stop, even before React renders loading', async () => {
    const response = deferred<Response>();
    fetchMock.mockReturnValue(response.promise);
    const { result } = mountAudio();
    const toggle = result.current.toggle;
    let pending!: Promise<void>;
    act(() => {
      pending = toggle('first');
      void toggle('second');
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][1]?.signal?.aborted).toBe(true);
    expect(result.current.loading).toBe(false);
    await act(async () => {
      response.resolve(audioResponse());
      await pending;
    });
    expectNoPlayback();
    expect(result.current.error).toBe(false);
  });

  it('a cancelled response cannot clear loading or publish an error over a newer request', async () => {
    const old = deferred<Response>();
    const fresh = deferred<Response>();
    fetchMock.mockReturnValueOnce(old.promise).mockReturnValueOnce(fresh.promise);
    const { result } = mountAudio();
    let first!: Promise<void>;
    act(() => {
      first = result.current.toggle('old');
    });
    await act(() => result.current.toggle('stop'));
    let second!: Promise<void>;
    act(() => {
      second = result.current.toggle('fresh');
    });

    await act(async () => {
      old.reject(new Error('aborted old request'));
      await first;
    });
    expect(result.current.loading).toBe(true);
    expect(result.current.error).toBe(false);
    expectNoPlayback();

    await act(async () => {
      fresh.resolve(audioResponse());
      await second;
    });
    expect(result.current.playing).toBe(true);
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBe(false);
  });

  it('releases the resource when play is refused and permits an explicit retry', async () => {
    nextPlay.mockRejectedValueOnce(new Error('autoplay blocked'));
    audioOk();
    const { result } = mountAudio();
    await act(() => result.current.toggle('texte'));

    expect(result.current.error).toBe(true);
    expect(result.current.loading).toBe(false);
    expect(FakeAudio.instances[0].paused).toBe(true);
    expect(FakeAudio.instances[0].onended).toBeNull();
    expect(revokeMock.mock.calls).toEqual([['blob:audio-1']]);
    fetchMock.mockResolvedValueOnce(audioResponse());
    await act(() => result.current.toggle('retry'));
    expect(result.current.playing).toBe(true);
    expect(result.current.error).toBe(false);
  });

  it('stops private playback and returns idle immediately when the account changes', async () => {
    audioOk();
    const { result, rerender } = mountAudio();
    await act(() => result.current.toggle('private text from A'));
    const oldToggle = result.current.toggle;
    currentUser = makeUser({ id: 'account-b' });
    rerender();

    expect(FakeAudio.instances[0].paused).toBe(true);
    expect(revokeMock.mock.calls).toEqual([['blob:audio-1']]);
    expect(result.current.playing).toBe(false);
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBe(false);
    await act(() => oldToggle('private text from A'));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('ignores pending account-A audio after switching A to B and back to A', async () => {
    const old = deferred<Response>();
    fetchMock.mockReturnValueOnce(old.promise);
    const { result, rerender } = mountAudio();
    let first!: Promise<void>;
    act(() => {
      first = result.current.toggle('private text from A');
    });
    const signal = fetchMock.mock.calls[0][1]?.signal;
    currentUser = makeUser({ id: 'account-b' });
    rerender();
    currentUser = makeUser({ id: 'account-a' });
    rerender();

    expect(signal?.aborted).toBe(true);
    expect(result.current.loading).toBe(false);
    await act(async () => {
      old.resolve(audioResponse());
      await first;
    });
    expectNoPlayback();
    expect(result.current.playing).toBe(false);
  });

  it('does not synthesize without an authenticated account', async () => {
    currentUser = null;
    const { result } = mountAudio();
    await act(() => result.current.toggle('private text'));
    expect(fetchMock).not.toHaveBeenCalled();
    expectNoPlayback();
  });
});
