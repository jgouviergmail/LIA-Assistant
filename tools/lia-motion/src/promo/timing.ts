/**
 * Clock of the promotional film.
 *
 * The soundtrack (`public/audio/promo/lia-promo-music.mp3`, an original
 * instrumental generated for this film) was measured, not assumed: kick
 * attacks land on whole and half seconds and a dynamic-programming beat
 * tracker reads 120.0 BPM with a 2-3 ms spread per 8-second window
 * (`exports/lia-motion/promo/audio-takes/`). One beat is therefore exactly
 * 30 frames at 60 fps and one 4/4 bar 120 frames, with beat 0 at frame 0.
 *
 * Measured landmarks of that recording (seconds): filtered intro 0-8, drop
 * 8.0, full groove 8-40 with a fill at 23-24, riser 39-40, breakdown 40-48,
 * full 48-55, fill 55-57, full 57-71, riser 71-72, build 72-76, final hit
 * 76.0, ring-out to silence at 82.
 *
 * The film plays the recording with bars repeated on bar lines (`MUSIC_EDIT`):
 * the groove of 22-38 s again after 38 s (seam 0.996 similar), and the two-bar
 * alternation of 58-66 s twice after 66 s (0.997). The film lasts 114 s; its
 * landmarks: drop 8, riser 55-56 into the breakdown 56-64 (« Elle anticipe »),
 * fill 71-73 into « Partout avec toi », riser 103-104, build 104-108 under
 * « Tout est relié », final hit 108.0 on the closing line, silence at 114.
 */

export const FPS = 60;
export const WIDTH = 1920;
export const HEIGHT = 1080;
/** Frames per beat at 120 BPM and 60 fps. */
export const BEAT = 30;
export const BAR = 4 * BEAT;
export const DURATION_SECONDS = 114;
export const TOTAL_FRAMES = DURATION_SECONDS * FPS;

/** Frame of a beat counted from the start of the film (fractions allowed). */
export const beat = (n: number): number => Math.round(n * BEAT);

export type SectionId =
  | 'hook'
  | 'reveal'
  | 'context'
  | 'know'
  | 'action'
  | 'act'
  | 'anticipate'
  | 'foresee'
  | 'devices'
  | 'channels'
  | 'circle'
  | 'control'
  | 'linked'
  | 'outro';

/** Start beat and length in beats of each section, on the measured grid. */
export const SECTIONS: Record<SectionId, { start: number; beats: number }> = {
  hook: { start: 0, beats: 16 },
  reveal: { start: 16, beats: 8 },
  context: { start: 24, beats: 24 },
  know: { start: 48, beats: 16 },
  action: { start: 64, beats: 32 },
  act: { start: 96, beats: 16 },
  anticipate: { start: 112, beats: 16 },
  foresee: { start: 128, beats: 16 },
  devices: { start: 144, beats: 8 },
  channels: { start: 152, beats: 16 },
  circle: { start: 168, beats: 12 },
  control: { start: 180, beats: 16 },
  linked: { start: 196, beats: 20 },
  outro: { start: 216, beats: 12 },
};

export const sectionFrom = (id: SectionId): number => beat(SECTIONS[id].start);
export const sectionLength = (id: SectionId): number => beat(SECTIONS[id].beats);

/** Source spans of the soundtrack in playback order (seconds of the recording). */
export const MUSIC_EDIT: ReadonlyArray<{ from: number; to: number | null }> = [
  { from: 0, to: 38 },
  { from: 22, to: 38 },
  { from: 38, to: 66 },
  { from: 58, to: 66 },
  { from: 58, to: 66 },
  { from: 66, to: null },
];

/**
 * The illustrated enumerations, in frames from their section's start: the
 * first tile, the spacing (one tile every two beats for six tiles, every
 * beat and a half for seven or for the short circle chapter, so the full grid
 * always holds at least two seconds), the tile count, and when it leaves.
 * Read by the scenes (`scenes/Chapters.tsx`) and by the sound cues.
 */
export const ENUMERATIONS = {
  know: { first: 30, step: 45, tiles: 7, exit: 452 },
  act: { first: 30, step: 45, tiles: 7, exit: 452 },
  foresee: { first: 30, step: 60, tiles: 6, exit: 452 },
  channels: { first: 30, step: 45, tiles: 7, exit: 452 },
  circle: { first: 30, step: 45, tiles: 5, exit: 334 },
  control: { first: 30, step: 45, tiles: 7, exit: 452 },
} as const;
export type EnumerationId = keyof typeof ENUMERATIONS;
