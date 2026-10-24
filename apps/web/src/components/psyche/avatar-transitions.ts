/**
 * Avatar transitions — the pure decisions behind the mood ping and the emotion burst.
 *
 * Both animations play on a CHANGE of the live avatar's snapshot, never on mount
 * and never on a history row. The component keeps the previous snapshot in state
 * and asks these functions whether the change it just saw deserves a reaction, so
 * each rule is decided in one place and tested without rendering.
 */

/**
 * Rare-emotion particle burst (W3): only these emotions, at intensity ≥ 0.8,
 * emit a one-shot 3-particle burst — the restraint is the point.
 */
export const EMOTION_PARTICLES: Readonly<Record<string, string>> = {
  joy: '✨',
  wonder: '🌟',
  tenderness: '❤️',
  gratitude: '💖',
  enthusiasm: '⚡',
  pride: '🌟',
  frustration: '💢',
};
export const PARTICLE_INTENSITY_THRESHOLD = 0.8;

/**
 * Whether the live avatar plays its one-shot mood ping (I6).
 *
 * @param previous - The last mood the avatar showed, or null when none yet.
 * @param next - The mood it shows now, or null for a snapshot without psyche.
 * @param live - Whether this is the latest message's avatar.
 * @returns True for a real change between two known moods on the live avatar.
 */
export function moodChangePings(
  previous: string | null,
  next: string | null,
  live: boolean
): boolean {
  return live && previous !== null && next !== null && previous !== next;
}

/**
 * The glyph a rare, strong new emotion bursts into on the live avatar (W3).
 *
 * @param previous - The emotion the avatar showed before, or null.
 * @param next - The emotion it shows now, or null.
 * @param intensity - The new emotion's intensity, from 0 to 1.
 * @param live - Whether this is the latest message's avatar.
 * @param reducedMotion - Whether the reader asked for less motion.
 * @returns The particle glyph, or null when the change deserves no burst.
 */
export function emotionBurstGlyph(
  previous: string | null,
  next: string | null,
  intensity: number,
  live: boolean,
  reducedMotion: boolean
): string | null {
  if (!live || previous === null || next === null || previous === next) return null;
  const glyph = EMOTION_PARTICLES[next];
  if (!glyph || intensity < PARTICLE_INTENSITY_THRESHOLD || reducedMotion) return null;
  return glyph;
}
