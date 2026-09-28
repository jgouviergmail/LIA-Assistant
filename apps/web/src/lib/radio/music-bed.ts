/**
 * The station's music (ADR-324, decision 28): one continuous bed under the whole
 * session, the voices on top of it.
 *
 * Two decks, so a track never ends in silence: when the playing one nears its
 * end, or the programme's mood changes, the other deck brings the next track in
 * while the first fades out (a crossfade). A mood's tracks come out of a shuffled
 * bag — every one plays before any repeats, and never the same twice in a row.
 * Everything goes through one master level, lowered under each voice and raised
 * after it (the duck). The engine behind the decks (Web Audio in the browser)
 * is the caller's: this class only decides, so it is tested without one.
 */
import type { MusicTrack } from './music-library';
import type { MusicMood } from './types';

/** How long two tracks overlap when one hands over to the next. */
export const MUSIC_CROSSFADE_S = 4;
/** How long the first track takes to come up at the start. */
export const MUSIC_FADE_IN_S = 1.5;
/** The music's level under a voice (about −12 dB). */
export const MUSIC_DUCKED_LEVEL = 0.25;
/**
 * How fast the music goes down when a voice starts — shorter than the silence a
 * segment opens with (`MixParams.lead_in_s`, 0.5 s), so no first word is covered.
 */
export const MUSIC_DUCK_ATTACK_S = 0.35;
/** How slowly it comes back up after the voice. */
export const MUSIC_DUCK_RELEASE_S = 1.2;
/** The fade that takes the music out when the listener stops. */
export const MUSIC_STOP_FADE_S = 1;

/** One deck: a track player whose level the bed can ramp. */
export interface MusicChannel {
  /** Take the browser's permission to play — called inside the click. */
  unlock(): void;
  load(url: string): void;
  play(): Promise<void>;
  pause(): void;
  /** Ramp this deck's level to `level` (0–1) over `seconds` (0: at once). */
  fade(level: number, seconds: number): void;
  /** Seconds into the track. */
  readonly currentTime: number;
  /** The track's length (NaN while unknown). */
  readonly duration: number;
  /** Called as the track plays (a few times a second) and when it ends. */
  onProgress(listener: () => void): void;
}

/** The level every deck goes through. */
export interface MusicFader {
  fade(level: number, seconds: number): void;
}

export interface MusicBedDeps {
  channels: readonly [MusicChannel, MusicChannel];
  master: MusicFader;
  library: Readonly<Record<MusicMood, readonly MusicTrack[]>>;
  /** Wake the audio engine — inside the click. */
  wake(): void;
  random(): number;
  /** Run `callback` once `seconds` have passed (the end of a fade). */
  later(callback: () => void, seconds: number): void;
}

const ignore = (): void => undefined;

function shuffled(items: readonly string[], random: () => number): string[] {
  const bag = [...items];
  for (let index = bag.length - 1; index > 0; index -= 1) {
    const other = Math.floor(random() * (index + 1));
    [bag[index], bag[other]] = [bag[other], bag[index]];
  }
  return bag;
}

export class MusicBed {
  private mood: MusicMood | null = null;
  private active: 0 | 1 = 0;
  private playing = false;
  /** Bumped by every start and stop: a fade scheduled before is obsolete after. */
  private generation = 0;
  private last: string | null = null;
  private readonly bags = new Map<MusicMood, string[]>();

  constructor(private readonly deps: MusicBedDeps) {
    deps.channels.forEach((channel, index) => {
      channel.onProgress(() => this.progress(index));
    });
  }

  /** Inside the click: the engine and both decks may play from now on. */
  unlock(): void {
    this.deps.wake();
    for (const channel of this.deps.channels) channel.unlock();
  }

  /** Play `mood`'s music: the first call starts it, a new mood crossfades to it. */
  play(mood: MusicMood): void {
    if (this.playing && mood === this.mood) return;
    this.mood = mood;
    if (this.playing) {
      this.crossfade();
      return;
    }
    this.playing = true;
    this.generation += 1;
    this.deps.master.fade(1, 0);
    this.startOn(this.active, MUSIC_FADE_IN_S);
  }

  /** Lower the music under a voice (`true`), or bring it back (`false`). */
  duck(under: boolean): void {
    this.deps.master.fade(
      under ? MUSIC_DUCKED_LEVEL : 1,
      under ? MUSIC_DUCK_ATTACK_S : MUSIC_DUCK_RELEASE_S
    );
  }

  pause(): void {
    for (const channel of this.deps.channels) channel.pause();
  }

  resume(): void {
    if (this.playing) void this.deps.channels[this.active].play().catch(ignore);
  }

  /** Fade the music out, then pause both decks. */
  stop(): void {
    if (!this.playing) return;
    this.playing = false;
    this.mood = null;
    this.generation += 1;
    const generation = this.generation;
    this.deps.master.fade(0, MUSIC_STOP_FADE_S);
    this.deps.later(() => {
      if (generation === this.generation) this.pause();
    }, MUSIC_STOP_FADE_S);
  }

  private progress(index: number): void {
    if (!this.playing || index !== this.active) return;
    const channel = this.deps.channels[index];
    const left = channel.duration - channel.currentTime;
    if (Number.isFinite(left) && left <= MUSIC_CROSSFADE_S) this.crossfade();
  }

  private crossfade(): void {
    const outgoing = this.active;
    const incoming = outgoing === 0 ? 1 : 0;
    this.active = incoming;
    this.startOn(incoming, MUSIC_CROSSFADE_S);
    this.deps.channels[outgoing].fade(0, MUSIC_CROSSFADE_S);
    const generation = this.generation;
    this.deps.later(() => {
      if (generation === this.generation && this.active !== outgoing) {
        this.deps.channels[outgoing].pause();
      }
    }, MUSIC_CROSSFADE_S);
  }

  private startOn(index: 0 | 1, fadeSeconds: number): void {
    const track = this.nextTrack();
    if (track === null) return;
    const channel = this.deps.channels[index];
    channel.fade(0, 0);
    channel.load(track);
    void channel.play().catch(ignore);
    channel.fade(1, fadeSeconds);
  }

  private nextTrack(): string | null {
    if (this.mood === null) return null;
    let bag = this.bags.get(this.mood) ?? [];
    if (bag.length === 0) {
      bag = shuffled(
        this.deps.library[this.mood].map(track => track.file),
        this.deps.random
      );
      // The bag is drawn from its end: never open it on the track just heard.
      if (bag.length > 1 && bag[bag.length - 1] === this.last) {
        [bag[0], bag[bag.length - 1]] = [bag[bag.length - 1], bag[0]];
      }
      this.bags.set(this.mood, bag);
    }
    const next = bag.pop() ?? null;
    this.last = next;
    return next;
  }
}
