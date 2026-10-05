import { afterEach, expect, it, vi } from 'vitest';
import {
  attachBorrowedElevenLabsTrack,
  elevenLabsAudioAdapter,
} from '../transports/elevenlabs-audio-adapter';

afterEach(() => vi.unstubAllGlobals());
it('hands the unfiltered borrowed track to one owner and never stops it on cleanup', () => {
  class Track {
    stop = vi.fn();
  }
  class Stream {
    constructor(readonly tracks: MediaStreamTrack[] = []) {}
  }
  vi.stubGlobal('MediaStreamTrack', Track);
  vi.stubGlobal('MediaStream', Stream);
  const track = new MediaStreamTrack();
  const released = vi.fn();
  const onRemoteStream = vi.fn(() => released);
  const cleanup = attachBorrowedElevenLabsTrack(track, { onRemoteStream });
  expect(onRemoteStream).toHaveBeenCalledExactlyOnceWith(new MediaStream([track]));
  cleanup?.();
  expect(released).toHaveBeenCalledTimes(1);
  expect(track.stop).not.toHaveBeenCalled();
  const adapter = elevenLabsAudioAdapter({});
  adapter.cleanup();
  adapter.cleanup();
});
