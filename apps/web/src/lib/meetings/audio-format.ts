/**
 * Which container a meeting recording uses — decided once, before the first byte.
 *
 * Two sources exist (ADR-258 arbitration A5):
 *
 *  - **Opus through `MediaRecorder`** with a timeslice: the browser encodes, a
 *    minute of speech is ~240 kB, and a three-hour meeting stays under the
 *    remote engines' file cap after a plain remux. First choice wherever the
 *    engine is trustworthy.
 *  - **Raw PCM through the worklet**: ten times heavier on the wire but
 *    container-free — nothing to corrupt on a crash, nothing for a WebView to
 *    get wrong. The fallback, and the ONLY path on Apple devices: Safari
 *    produced MP4/AAC before 18.4 (a container the backend does not accept),
 *    home-screen PWAs had a `MediaRecorder` bug through 18.x (measured), and
 *    every iOS browser runs the same WebKit engine.
 *
 * Pure: the capabilities are injected so the decision is unit-testable
 * without a browser.
 */

import type { MeetingAudioFormat } from '@/types/meetings';

export interface AudioFormatChoice {
  format: MeetingAudioFormat;
  /** `MediaRecorder` MIME type for the Opus paths; undefined for PCM. */
  mimeType?: string;
}

export interface AudioEnvironment {
  /** iPhone/iPad, whatever the browser (they all embed WebKit). */
  isAppleDevice: boolean;
  /** `MediaRecorder.isTypeSupported`, or a constant false when the API is absent. */
  isTypeSupported: (mimeType: string) => boolean;
}

export const WEBM_OPUS_MIME = 'audio/webm;codecs=opus';
export const OGG_OPUS_MIME = 'audio/ogg;codecs=opus';

/**
 * Choose the recording format for this environment.
 *
 * @param env - The browser's relevant capabilities.
 * @returns The format and, for Opus, the MIME type to open `MediaRecorder` with.
 */
export function chooseMeetingAudioFormat(env: AudioEnvironment): AudioFormatChoice {
  if (env.isAppleDevice) return { format: 'pcm_s16le_16' };
  if (env.isTypeSupported(WEBM_OPUS_MIME)) return { format: 'webm_opus', mimeType: WEBM_OPUS_MIME };
  if (env.isTypeSupported(OGG_OPUS_MIME)) return { format: 'ogg_opus', mimeType: OGG_OPUS_MIME };
  return { format: 'pcm_s16le_16' };
}

/**
 * Whether the user agent runs on an Apple mobile device.
 *
 * iPadOS reports a desktop UA since 13; the touch-point probe on `MacIntel`
 * catches it (a Mac has no touch points).
 *
 * @param nav - The navigator to inspect.
 * @returns True on iPhone, iPad and iPod.
 */
export function detectAppleDevice(
  nav: Pick<Navigator, 'userAgent' | 'platform' | 'maxTouchPoints'>
): boolean {
  if (/iPad|iPhone|iPod/.test(nav.userAgent)) return true;
  return nav.platform === 'MacIntel' && nav.maxTouchPoints > 1;
}

/** The live environment (browser only). */
export function currentAudioEnvironment(): AudioEnvironment {
  const recorder = typeof MediaRecorder === 'undefined' ? null : MediaRecorder;
  return {
    isAppleDevice: typeof navigator !== 'undefined' && detectAppleDevice(navigator),
    isTypeSupported: (mimeType: string) =>
      recorder !== null &&
      typeof recorder.isTypeSupported === 'function' &&
      recorder.isTypeSupported(mimeType),
  };
}

/** Whether this browser can record a meeting at all. */
export function isMeetingRecordingSupported(): boolean {
  return (
    typeof navigator !== 'undefined' &&
    typeof navigator.mediaDevices !== 'undefined' &&
    typeof navigator.mediaDevices.getUserMedia === 'function' &&
    typeof AudioContext !== 'undefined'
  );
}
