/**
 * The resume record (ADR-330 amendment): a language switch or a full reload
 * remounts the player; what it was doing survives in the session for a short
 * while, and nothing here ever throws — a storage that refuses is a visitor
 * who starts afresh.
 */

import { describe, expect, it, vi } from 'vitest';

import {
  PLAYER_RESUME_MAX_AGE_MS,
  clearResume,
  readResume,
  writeResume,
  type StorageLike,
} from '../player-session';

function memoryStorage(): StorageLike & { store: Map<string, string> } {
  const store = new Map<string, string>();
  return {
    store,
    getItem: key => store.get(key) ?? null,
    setItem: (key, value) => {
      store.set(key, value);
    },
    removeItem: key => {
      store.delete(key);
    },
  };
}

describe('the resume record', () => {
  it('comes back within its age bound, with the time and the sound as written', () => {
    const storage = memoryStorage();
    writeResume(storage, { video: 1, time: 12.5, sound: true }, 1_000);
    expect(readResume(storage, 1_000 + PLAYER_RESUME_MAX_AGE_MS - 1)).toEqual({
      video: 1,
      time: 12.5,
      sound: true,
    });
  });

  it('is ignored once too old, and once cleared', () => {
    const storage = memoryStorage();
    writeResume(storage, { video: 0, time: 3, sound: false }, 1_000);
    expect(readResume(storage, 1_000 + PLAYER_RESUME_MAX_AGE_MS + 1)).toBeNull();
    writeResume(storage, { video: 0, time: 3, sound: false }, 1_000);
    clearResume(storage);
    expect(readResume(storage, 1_001)).toBeNull();
  });

  it('refuses a malformed record, a time that is not a finite number, a rank that is no rank', () => {
    const storage = memoryStorage();
    storage.store.set('lia_landing_video', '{not json');
    expect(readResume(storage, 0)).toBeNull();
    storage.store.set('lia_landing_video', JSON.stringify({ time: 'x', sound: true, at: 0 }));
    expect(readResume(storage, 0)).toBeNull();
    for (const video of [-1, 1.5, '1', null]) {
      storage.store.set(
        'lia_landing_video',
        JSON.stringify({ video, time: 3, sound: true, at: 0 })
      );
      expect(readResume(storage, 0), String(video)).toBeNull();
    }
  });

  it('reads a record written before playlists as the first video', () => {
    const storage = memoryStorage();
    storage.store.set('lia_landing_video', JSON.stringify({ time: 7, sound: false, at: 0 }));
    expect(readResume(storage, 0)).toEqual({ video: 0, time: 7, sound: false });
  });

  it('never throws on a storage that refuses, nor without a storage at all', () => {
    const refusing: StorageLike = {
      getItem: vi.fn(() => {
        throw new Error('blocked');
      }),
      setItem: vi.fn(() => {
        throw new Error('blocked');
      }),
      removeItem: vi.fn(() => {
        throw new Error('blocked');
      }),
    };
    expect(() => writeResume(refusing, { video: 0, time: 1, sound: true }, 0)).not.toThrow();
    expect(readResume(refusing, 0)).toBeNull();
    expect(() => clearResume(refusing)).not.toThrow();
    expect(readResume(null, 0)).toBeNull();
    expect(() => writeResume(null, { video: 0, time: 1, sound: true }, 0)).not.toThrow();
  });
});
