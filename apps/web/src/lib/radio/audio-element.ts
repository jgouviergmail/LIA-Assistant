/**
 * The player's voice (ADR-324): one audio element plays the segments, over the
 * station's music (`music-bed.ts`), which it lowers under every segment and
 * raises after it. Only a SEGMENT's end is reported — the silence played inside
 * the click to take the browser's permission is none — and a segment the
 * element cannot decode is reported ended rather than left to hang the antenna.
 * A programme a news flash cut resumes where it stopped: its start position is
 * set with its source (the element seeks there once it has loaded).
 */
import type { RadioAudio } from './controller';
import type { MusicMood } from './types';
import { unlockMedia } from './web-audio';

/** The few members of an `HTMLAudioElement` the player uses. */
export interface MediaElement {
  src: string;
  currentTime: number;
  play(): Promise<void>;
  pause(): void;
  load(): void;
  removeAttribute(name: string): void;
  addEventListener(type: 'ended' | 'error', listener: () => void): void;
}

/** The station's music, behind the verbs the voice needs of it (a `MusicBed`). */
export interface RadioMusic {
  unlock(): void;
  play(mood: MusicMood): void;
  duck(under: boolean): void;
  pause(): void;
  resume(): void;
  stop(): void;
}

export function radioAudio(voice: MediaElement, music: RadioMusic): RadioAudio {
  let segmentOnAir = false;
  let segmentEnded: () => void = () => undefined;
  const endOfSegment = (): void => {
    if (!segmentOnAir) return;
    segmentOnAir = false;
    music.duck(false);
    segmentEnded();
  };
  voice.addEventListener('ended', endOfSegment);
  voice.addEventListener('error', endOfSegment);

  return {
    begin(): void {
      unlockMedia(voice);
      music.unlock();
    },
    music(mood: MusicMood): void {
      music.play(mood);
    },
    async playSegment(url: string, startAt = 0): Promise<void> {
      voice.src = url;
      if (startAt > 0) voice.currentTime = startAt;
      segmentOnAir = true;
      music.duck(true);
      try {
        await voice.play();
      } catch (error) {
        segmentOnAir = false;
        music.duck(false);
        throw error;
      }
    },
    pause(): void {
      voice.pause();
      music.pause();
    },
    async resume(): Promise<void> {
      music.resume();
      if (segmentOnAir) await voice.play();
    },
    stop(): void {
      segmentOnAir = false;
      voice.pause();
      voice.removeAttribute('src');
      voice.load();
      music.stop();
    },
    position(): number {
      return voice.currentTime;
    },
    onSegmentEnded(listener: () => void): void {
      segmentEnded = listener;
    },
  };
}
