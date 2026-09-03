/**
 * Production wiring of the recorder controller (ADR-258).
 *
 * The controller is browser-agnostic; this module is the ONE place that binds
 * it to `getUserMedia`, `MediaRecorder`/the worklet, the wake lock, the
 * geolocation probe and the meetings API. Tests build their own `RecorderDeps`.
 */

import {
  MEETING_SILENCE_RMS_THRESHOLD,
  MEETING_STATUS_POLL_MS,
  VOICE_INPUT_SAMPLE_RATE,
} from '@/lib/constants';
import { meetingsApi } from '@/lib/meetings/api';
import { chooseMeetingAudioFormat, currentAudioEnvironment } from '@/lib/meetings/audio-format';
import { createAudioSource } from '@/lib/meetings/audio-source';
import { bestEffortPosition } from '@/lib/meetings/geolocation';
import type { RecorderDeps } from '@/lib/meetings/recorder-controller';
import { SegmentUploader, apiSegmentTransport } from '@/lib/meetings/segment-uploader';
import { acquireWakeLock } from '@/lib/wake-lock';
import { useMeetingRecorderStore } from '@/stores/meetingRecorderStore';
import type { MeetingDetail } from '@/types/meetings';

/** The microphone constraints the voice input already uses — one voice, one mic. */
export function requestMicrophone(): Promise<MediaStream> {
  return navigator.mediaDevices.getUserMedia({
    audio: {
      sampleRate: VOICE_INPUT_SAMPLE_RATE,
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });
}

/** The device's IANA timezone (the minutes are dated in it). */
export function deviceTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

export function createRecorderDeps(onProcessed?: (detail: MeetingDetail) => void): RecorderDeps {
  return {
    api: {
      start: meetingsApi.start,
      stop: meetingsApi.stop,
      discard: meetingsApi.remove,
      active: meetingsApi.active,
      detail: id => meetingsApi.detail(id),
    },
    getUserMedia: requestMicrophone,
    chooseFormat: () => chooseMeetingAudioFormat(currentAudioEnvironment()),
    createSource: createAudioSource,
    createUploader: options => new SegmentUploader({ ...options, transport: apiSegmentTransport }),
    position: bestEffortPosition,
    acquireWakeLock,
    timezone: deviceTimezone,
    isOnline: () => (typeof navigator === 'undefined' ? true : navigator.onLine),
    now: () => Date.now(),
    store: useMeetingRecorderStore,
    silenceThresholdRms: MEETING_SILENCE_RMS_THRESHOLD,
    statusPollMs: MEETING_STATUS_POLL_MS,
    onProcessed,
  };
}
