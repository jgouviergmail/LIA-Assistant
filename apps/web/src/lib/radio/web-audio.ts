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
import { unlockMedia } from '@/lib/audio/unlock-media';

export { unlockMedia, type UnlockableMedia } from '@/lib/audio/unlock-media';

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
