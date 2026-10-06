/**
 * The station's music on Web Audio (ADR-324, decision 28): each deck is an
 * `<audio>` element routed through its own gain, both through one master gain.
 *
 * Web Audio rather than the elements' `volume`: iOS ignores `volume`, so a duck
 * written there would never duck on an iPhone. The tracks are served by this
 * origin, which is what lets an element feed the graph (a cross-origin source
 * without CORS headers plays silence through it). Built inside the click: an
 * AudioContext created there starts running, and every element is played once
 * there so the browser lets it play later.
 */
import { MusicBed, type MusicChannel } from './music-bed';
import { MUSIC_LIBRARY } from './music-library';

/** Silent stereo priming (0.1 s, 8 kHz, PCM8), matching the music tracks' channels. */
function silentWav(): string {
  const channels = 2;
  const samples = 800 * channels;
  const bytes = new Uint8Array(44 + samples);
  const view = new DataView(bytes.buffer);
  const ascii = (offset: number, text: string): void => {
    for (let index = 0; index < text.length; index += 1) {
      bytes[offset + index] = text.charCodeAt(index);
    }
  };
  ascii(0, 'RIFF');
  view.setUint32(4, 36 + samples, true);
  ascii(8, 'WAVEfmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, channels, true);
  view.setUint32(24, 8000, true);
  view.setUint32(28, 8000 * channels, true);
  view.setUint16(32, channels, true);
  view.setUint16(34, 8, true);
  ascii(36, 'data');
  view.setUint32(40, samples, true);
  bytes.fill(128, 44);
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return `data:audio/wav;base64,${btoa(binary)}`;
}

let silence: string | null = null;

/** The few members of a media element the unlock needs. */
export interface UnlockableMedia {
  src: string;
  play(): Promise<void>;
  pause(): void;
}

/** Play `element` once inside the click, so the browser lets it play later. */
export function unlockMedia(element: UnlockableMedia): void {
  const quiet = (silence ??= silentWav());
  element.src = quiet;
  void element
    .play()
    .then(() => {
      // A segment may already have replaced the silence: never pause it.
      if (element.src === quiet) element.pause();
    })
    .catch(() => undefined);
}

function ramp(context: AudioContext, param: AudioParam, level: number, seconds: number): void {
  const now = context.currentTime;
  param.cancelScheduledValues(now);
  param.setValueAtTime(param.value, now);
  if (seconds > 0) param.linearRampToValueAtTime(level, now + seconds);
  else param.setValueAtTime(level, now);
}

function deck(context: AudioContext, master: AudioNode): MusicChannel {
  const element = new Audio();
  element.preload = 'auto';
  const gain = context.createGain();
  gain.gain.value = 0;
  context.createMediaElementSource(element).connect(gain);
  gain.connect(master);
  return {
    unlock: () => unlockMedia(element),
    load: url => {
      element.src = url;
    },
    play: () => element.play(),
    pause: () => element.pause(),
    fade: (level, seconds) => ramp(context, gain.gain, level, seconds),
    get currentTime() {
      return element.currentTime;
    },
    get duration() {
      return element.duration;
    },
    onProgress: listener => {
      element.addEventListener('timeupdate', listener);
      element.addEventListener('ended', listener);
    },
  };
}

/** The station's music, on this browser's audio engine — call it inside the click. */
export function browserMusicBed(): MusicBed {
  const context = new AudioContext();
  const master = context.createGain();
  master.connect(context.destination);
  return new MusicBed({
    channels: [deck(context, master), deck(context, master)],
    master: { fade: (level, seconds) => ramp(context, master.gain, level, seconds) },
    library: MUSIC_LIBRARY,
    wake: () => {
      if (context.state === 'suspended') void context.resume();
    },
    random: Math.random,
    later: (callback, seconds) => {
      window.setTimeout(callback, seconds * 1000);
    },
  });
}
