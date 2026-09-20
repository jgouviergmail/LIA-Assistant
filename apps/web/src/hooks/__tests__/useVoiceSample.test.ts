/**
 * useVoiceSample — one POST on the person's key, a WAV played as is; the
 * form's key travels only when given; a new sample stops the previous; a
 * failure is one toast.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';

const api = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { post: api.post } }));
const toast = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }));
vi.mock('sonner', () => ({ toast }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

import { useVoiceSample } from '../useVoiceSample';

class FakeAudio {
  static instances: FakeAudio[] = [];
  onended: (() => void) | null = null;
  play = vi.fn(async () => {});
  pause = vi.fn();
  constructor(readonly src: string) {
    FakeAudio.instances.push(this);
  }
}

const WAV_BASE64 = btoa('RIFF....WAVEfmt ');

describe('useVoiceSample', () => {
  const real = {
    Audio: globalThis.Audio,
    create: URL.createObjectURL,
    revoke: URL.revokeObjectURL,
  };
  beforeEach(() => {
    FakeAudio.instances = [];
    (globalThis as { Audio: unknown }).Audio = FakeAudio;
    URL.createObjectURL = vi.fn(() => 'blob:sample');
    URL.revokeObjectURL = vi.fn();
    api.post.mockResolvedValue({ audio_base64: WAV_BASE64, sample_rate: 24000, format: 'wav' });
    vi.clearAllMocks();
  });
  afterEach(() => {
    (globalThis as { Audio: unknown }).Audio = real.Audio;
    URL.createObjectURL = real.create;
    URL.revokeObjectURL = real.revoke;
  });

  it('asks the API for the voice and plays the WAV it returns', async () => {
    const { result } = renderHook(() => useVoiceSample());
    await act(() => result.current.play('Kore'));
    expect(api.post).toHaveBeenCalledWith('/live/voices/sample', {
      provider: 'gemini',
      voice: 'Kore',
    });
    expect(FakeAudio.instances).toHaveLength(1);
    expect(FakeAudio.instances[0].play).toHaveBeenCalledTimes(1);
    expect(result.current.playing).toBe(true);
    act(() => FakeAudio.instances[0].onended?.());
    expect(result.current.playing).toBe(false);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:sample');
  });

  it('sends the form key only when given, and stops the previous sample', async () => {
    const { result } = renderHook(() => useVoiceSample());
    await act(() => result.current.play('Kore', 'AIza-form-key'));
    expect(api.post).toHaveBeenLastCalledWith('/live/voices/sample', {
      provider: 'gemini',
      voice: 'Kore',
      api_key: 'AIza-form-key',
    });
    await act(() => result.current.play('Puck'));
    expect(FakeAudio.instances[0].pause).toHaveBeenCalledTimes(1);
    expect(FakeAudio.instances).toHaveLength(2);
  });

  it('tells a failure once and stays quiet', async () => {
    api.post.mockRejectedValueOnce(new Error('refused'));
    const { result } = renderHook(() => useVoiceSample());
    await act(() => result.current.play('Kore'));
    expect(toast.error).toHaveBeenCalledWith('settings.live_mode.voice_sample_failed');
    expect(result.current.playing).toBe(false);
    expect(FakeAudio.instances).toHaveLength(0);
  });
});
