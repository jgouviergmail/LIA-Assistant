import { afterEach, expect, it, vi } from 'vitest';
import { activateRtcAudio } from '../rtc-audio-activation';

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = '';
});

it('activates RTC decoding with a muted owned element and never stops the borrowed track', async () => {
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue();
  const pause = vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
  const stop = vi.fn();
  const stream = { getTracks: () => [{ stop }] } as unknown as MediaStream;
  const release = activateRtcAudio(stream);
  const audio = document.querySelector('audio')!;
  expect(audio.muted).toBe(true);
  expect(audio.defaultMuted).toBe(true);
  expect(audio.srcObject).toBe(stream);
  expect(audio.hidden).toBe(true);
  expect(audio.play).toHaveBeenCalledOnce();
  release();
  release();
  expect(pause).toHaveBeenCalledOnce();
  expect(audio.srcObject).toBeNull();
  expect(document.querySelector('audio')).toBeNull();
  expect(stop).not.toHaveBeenCalled();
});

it('contains autoplay rejection and stale promises without exposing provider errors', async () => {
  let reject: (error: Error) => void = () => {};
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockReturnValue(
    new Promise((_resolve, fail) => {
      reject = fail;
    })
  );
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
  const release = activateRtcAudio({} as MediaStream);
  release();
  reject(new Error('private URL'));
  await Promise.resolve();
  expect(document.querySelector('audio')).toBeNull();
});

it('supports a legacy media play implementation without a returned promise', () => {
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockReturnValue(
    undefined as unknown as Promise<void>
  );
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
  const release = activateRtcAudio({} as MediaStream);
  release();
  expect(document.querySelector('audio')).toBeNull();
});
