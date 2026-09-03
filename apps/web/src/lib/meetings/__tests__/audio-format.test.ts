/**
 * The format decision: Opus where MediaRecorder is trustworthy, raw PCM on
 * Apple devices and wherever Opus is unavailable.
 */

import { describe, expect, it } from 'vitest';

import {
  OGG_OPUS_MIME,
  WEBM_OPUS_MIME,
  chooseMeetingAudioFormat,
  detectAppleDevice,
} from '../audio-format';

describe('chooseMeetingAudioFormat', () => {
  it('prefers WebM/Opus when the recorder supports it', () => {
    expect(
      chooseMeetingAudioFormat({ isAppleDevice: false, isTypeSupported: m => m === WEBM_OPUS_MIME })
    ).toEqual({ format: 'webm_opus', mimeType: WEBM_OPUS_MIME });
  });

  it('falls back to Ogg/Opus, then to PCM', () => {
    expect(
      chooseMeetingAudioFormat({ isAppleDevice: false, isTypeSupported: m => m === OGG_OPUS_MIME })
    ).toEqual({ format: 'ogg_opus', mimeType: OGG_OPUS_MIME });
    expect(
      chooseMeetingAudioFormat({ isAppleDevice: false, isTypeSupported: () => false })
    ).toEqual({
      format: 'pcm_s16le_16',
    });
  });

  it('records PCM on Apple devices even when the recorder claims Opus support', () => {
    // Measured: Safari < 18.4 produced MP4/AAC, home-screen PWAs had a
    // MediaRecorder bug through 18.x; every iOS browser embeds the same WebKit.
    expect(chooseMeetingAudioFormat({ isAppleDevice: true, isTypeSupported: () => true })).toEqual({
      format: 'pcm_s16le_16',
    });
  });
});

describe('detectAppleDevice', () => {
  it('recognises iPhone and iPad user agents', () => {
    expect(
      detectAppleDevice({
        userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)',
        platform: 'iPhone',
        maxTouchPoints: 5,
      })
    ).toBe(true);
  });

  it('catches iPadOS behind its desktop user agent through the touch points', () => {
    expect(
      detectAppleDevice({
        userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
        platform: 'MacIntel',
        maxTouchPoints: 5,
      })
    ).toBe(true);
    expect(
      detectAppleDevice({
        userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
        platform: 'MacIntel',
        maxTouchPoints: 0,
      })
    ).toBe(false);
  });

  it('leaves Android and Windows alone', () => {
    expect(
      detectAppleDevice({
        userAgent: 'Mozilla/5.0 (Linux; Android 14; Pixel 8)',
        platform: 'Linux armv8l',
        maxTouchPoints: 5,
      })
    ).toBe(false);
  });
});
