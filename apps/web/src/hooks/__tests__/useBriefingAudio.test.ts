/**
 * useBriefingAudio — the "listen" contract of the briefing synthesis (A2).
 *
 * One toggle: fetch the MP3 once, play it, stop on second press; a failed
 * fetch surfaces an error and never crashes; unmount stops playback and
 * revokes the object URL (no leaked blob, no ghost audio).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

import { useBriefingAudio } from '../useBriefingAudio';

class FakeAudio {
  static instances: FakeAudio[] = [];
  src: string;
  onended: (() => void) | null = null;
  paused = true;
  play = vi.fn(async () => {
    this.paused = false;
  });
  pause = vi.fn(() => {
    this.paused = true;
  });
  constructor(src: string) {
    this.src = src;
    FakeAudio.instances.push(this);
  }
}

const fetchMock = vi.fn();
const revokeMock = vi.fn();

beforeEach(() => {
  FakeAudio.instances = [];
  fetchMock.mockReset();
  revokeMock.mockReset();
  vi.stubGlobal('Audio', FakeAudio as unknown as typeof Audio);
  vi.stubGlobal('fetch', fetchMock);
  vi.stubGlobal('URL', {
    ...URL,
    createObjectURL: vi.fn(() => 'blob:fake'),
    revokeObjectURL: revokeMock,
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function audioOk() {
  fetchMock.mockResolvedValue({
    ok: true,
    blob: async () => new Blob([new Uint8Array([1, 2, 3])], { type: 'audio/mpeg' }),
  });
}

describe('useBriefingAudio', () => {
  it('fetches the audio with credentials and plays it', async () => {
    audioOk();
    const { result } = renderHook(() => useBriefingAudio());

    await act(() => result.current.toggle('Bonjour, voici votre journée.'));

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/api/v1/briefing/synthesis/audio');
    // apiEndpointUrl already prefixes /api/v1 — a doubled prefix 404s.
    expect(String(url)).not.toContain('/api/v1/api/v1');
    expect(init.method).toBe('POST');
    expect(init.credentials).toBe('include');
    expect(JSON.parse(init.body).text).toBe('Bonjour, voici votre journée.');
    await waitFor(() => expect(result.current.playing).toBe(true));
    expect(FakeAudio.instances[0].play).toHaveBeenCalled();
  });

  it('second press stops playback and revokes the blob URL', async () => {
    audioOk();
    const { result } = renderHook(() => useBriefingAudio());
    await act(() => result.current.toggle('texte'));
    await waitFor(() => expect(result.current.playing).toBe(true));

    await act(() => result.current.toggle('texte'));

    expect(FakeAudio.instances[0].pause).toHaveBeenCalled();
    expect(revokeMock).toHaveBeenCalledWith('blob:fake');
    expect(result.current.playing).toBe(false);
  });

  it('playback ends naturally back to idle', async () => {
    audioOk();
    const { result } = renderHook(() => useBriefingAudio());
    await act(() => result.current.toggle('texte'));
    await waitFor(() => expect(result.current.playing).toBe(true));

    act(() => FakeAudio.instances[0].onended?.());

    expect(result.current.playing).toBe(false);
    expect(revokeMock).toHaveBeenCalled();
  });

  it('a failed fetch surfaces an error and stays idle', async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 500 });
    const { result } = renderHook(() => useBriefingAudio());

    await act(() => result.current.toggle('texte'));

    expect(result.current.error).toBe(true);
    expect(result.current.playing).toBe(false);
  });

  it('unmount stops playback and revokes the URL', async () => {
    audioOk();
    const { result, unmount } = renderHook(() => useBriefingAudio());
    await act(() => result.current.toggle('texte'));
    await waitFor(() => expect(result.current.playing).toBe(true));

    unmount();

    expect(FakeAudio.instances[0].pause).toHaveBeenCalled();
    expect(revokeMock).toHaveBeenCalledWith('blob:fake');
  });
});
