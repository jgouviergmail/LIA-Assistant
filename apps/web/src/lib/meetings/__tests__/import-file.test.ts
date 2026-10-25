/**
 * Choosing a file to import as a meeting (owner request 2026-10-24): its format
 * comes from its name first, then its type; every bound the server publishes is
 * checked before a byte is sent; it is dated, by default, when it began.
 */
import { describe, expect, it } from 'vitest';

import {
  defaultRecordedAt,
  fromLocalInput,
  importFormatOf,
  importRefusal,
  toLocalInput,
} from '../import-file';

const LIMITS = { max_bytes: 1000, chunk_max_bytes: 100, max_duration_minutes: 60 };

describe('importFormatOf', () => {
  it.each([
    ['memo.m4a', '', 'import_m4a'],
    ['MEETING.WAV', '', 'import_wav'],
    ['call.mp3', 'audio/mpeg', 'import_mp3'],
    ['no-extension', 'audio/x-m4a', 'import_m4a'],
    ['no-extension', 'audio/wav', 'import_wav'],
  ])('%s (%s) is %s', (name, type, expected) => {
    expect(importFormatOf({ name, type })).toBe(expected);
  });

  it.each([
    ['notes.txt', 'text/plain'],
    ['video.mov', 'video/quicktime'],
    ['playlist.m3u8', 'application/vnd.apple.mpegurl'],
  ])('%s is not an importable recording', (name, type) => {
    expect(importFormatOf({ name, type })).toBeNull();
  });
});

describe('importRefusal', () => {
  const file = (size: number, name = 'memo.m4a') => ({ name, type: '', size });

  it('accepts a file within every bound, its length known or not', () => {
    expect(importRefusal(file(1000), 3600, LIMITS)).toBeNull();
    expect(importRefusal(file(500), null, LIMITS)).toBeNull();
  });

  it('names the first bound a file breaks', () => {
    expect(importRefusal(file(10, 'notes.txt'), null, LIMITS)).toBe('unsupported');
    expect(importRefusal(file(0), null, LIMITS)).toBe('empty');
    expect(importRefusal(file(1001), null, LIMITS)).toBe('too_large');
    expect(importRefusal(file(500), 3601, LIMITS)).toBe('too_long');
  });
});

describe('the recording date', () => {
  it('begins its length before the file was last written', () => {
    const written = Date.UTC(2026, 9, 20, 10, 0, 0);
    expect(defaultRecordedAt(written, 1800).toISOString()).toBe('2026-10-20T09:30:00.000Z');
    expect(defaultRecordedAt(written, null).toISOString()).toBe('2026-10-20T10:00:00.000Z');
  });

  it('round-trips through the local datetime input, to the minute', () => {
    const date = new Date(2026, 9, 20, 9, 30, 42);
    const value = toLocalInput(date);
    expect(value).toBe('2026-10-20T09:30');
    expect(fromLocalInput(value)?.getTime()).toBe(new Date(2026, 9, 20, 9, 30).getTime());
    expect(fromLocalInput('')).toBeNull();
    expect(fromLocalInput('not a date')).toBeNull();
  });
});
