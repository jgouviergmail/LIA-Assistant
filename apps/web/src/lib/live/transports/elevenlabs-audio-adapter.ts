import type { WebRTCAudioAdapter, AnalysisResult } from '@elevenlabs/client/internal';
import type { LiveTransportEvents } from '../types';

const noVolume: AnalysisResult = {
  volumeProvider: {
    getVolume: () => 0,
    getByteFrequencyData: (array: Uint8Array<ArrayBuffer>) => {
      array.fill(0);
    },
  },
};

/** The exported SDK seam delegates the unfiltered borrowed track to LIA. */
export function elevenLabsAudioAdapter(events: LiveTransportEvents): WebRTCAudioAdapter {
  let release: (() => void) | null = null;
  return {
    attachRemoteTrack: async track => {
      release?.();
      release = attachBorrowedElevenLabsTrack(track.mediaStreamTrack, events);
    },
    setupInputAnalysis: () => noVolume,
    // LIA captures before WebRTCConnection's maxVolume > .01 filter. It does
    // not feed the SDK callback a second time or attach a second audible sink.
    setupOutputAnalysis: async () => noVolume,
    setVolume: () => {},
    setOutputDevice: async () => {},
    cleanup: () => {
      release?.();
      release = null;
    },
  };
}
export function attachBorrowedElevenLabsTrack(
  track: MediaStreamTrack,
  events: LiveTransportEvents
): (() => void) | null {
  return events.onRemoteStream?.(new MediaStream([track])) ?? null;
}
