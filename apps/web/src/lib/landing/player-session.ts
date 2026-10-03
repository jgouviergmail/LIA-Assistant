/**
 * The resume record of the persistent player (ADR-330 amendment). A language
 * switch re-renders the `[lng]` layout and remounts the player; a full reload
 * does too. What it was doing — which video of the playlist, the time in it,
 * whether the sound was on — survives in the session for
 * `PLAYER_RESUME_MAX_AGE_MS`, a per-browser convenience: nothing here must
 * hold, and nothing here ever throws.
 */

export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export interface ResumeRecord {
  /** The rank of the video in playing order (a record written before playlists reads as the first). */
  video: number;
  /** Playback position in that video, in seconds. */
  time: number;
  /** Whether the sound was on — the visitor had clicked for it. */
  sound: boolean;
}

export const PLAYER_RESUME_KEY = 'lia_landing_video';
export const PLAYER_RESUME_MAX_AGE_MS = 2 * 60_000;

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

/** The record, when there is one younger than the age bound and well formed. */
export function readResume(storage: StorageLike | null, now: number): ResumeRecord | null {
  try {
    const raw = storage?.getItem(PLAYER_RESUME_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (!isPlainObject(parsed)) return null;
    const { video = 0, time, sound, at } = parsed;
    if (typeof video !== 'number' || !Number.isInteger(video) || video < 0) return null;
    if (typeof time !== 'number' || !Number.isFinite(time)) return null;
    if (typeof sound !== 'boolean') return null;
    if (typeof at !== 'number' || !Number.isFinite(at) || now - at > PLAYER_RESUME_MAX_AGE_MS) {
      return null;
    }
    return { video, time, sound };
  } catch {
    // A private window, blocked site data, a corrupt value: the visitor starts afresh.
    return null;
  }
}

export function writeResume(storage: StorageLike | null, record: ResumeRecord, now: number): void {
  try {
    storage?.setItem(PLAYER_RESUME_KEY, JSON.stringify({ ...record, at: now }));
  } catch {
    // A storage that refuses writes keeps no record; nothing to do.
  }
}

/** The session storage, or `null` where the browser refuses it (a private window, blocked site data). */
export function sessionStorageOrNull(): StorageLike | null {
  try {
    return window.sessionStorage;
  } catch {
    // No storage, no record, no resume.
    return null;
  }
}

export function clearResume(storage: StorageLike | null): void {
  try {
    storage?.removeItem(PLAYER_RESUME_KEY);
  } catch {
    // Nothing to remove from a storage that refuses.
  }
}
