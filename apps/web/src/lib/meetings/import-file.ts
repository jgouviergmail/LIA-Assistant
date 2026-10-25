/**
 * A file chosen to be imported as a meeting (owner request 2026-10-24).
 *
 * Pure decisions, unit-tested: which import format a file is (its name first,
 * then the type the browser reports — a phone's voice memo often has none),
 * which published bound it breaks before a byte is sent (ADR-184), and when the
 * meeting began by default — the file's last write minus its length.
 */

import type { MeetingImportFormat, MeetingImportLimits } from '@/types/meetings';

/** What the file picker offers: the three formats, by extension and by type. */
export const IMPORT_ACCEPT =
  '.wav,.mp3,.m4a,audio/wav,audio/x-wav,audio/wave,audio/mpeg,audio/mp4,audio/x-m4a';

const BY_EXTENSION: Readonly<Record<string, MeetingImportFormat>> = {
  wav: 'import_wav',
  mp3: 'import_mp3',
  m4a: 'import_m4a',
};

const BY_TYPE: Readonly<Record<string, MeetingImportFormat>> = {
  'audio/wav': 'import_wav',
  'audio/x-wav': 'import_wav',
  'audio/wave': 'import_wav',
  'audio/mpeg': 'import_mp3',
  'audio/mp3': 'import_mp3',
  'audio/mp4': 'import_m4a',
  'audio/x-m4a': 'import_m4a',
  'audio/m4a': 'import_m4a',
};

export type ImportRefusal = 'unsupported' | 'empty' | 'too_large' | 'too_long';

/** The import format of a file, or null when it is none of the three. */
export function importFormatOf(file: { name: string; type: string }): MeetingImportFormat | null {
  const dot = file.name.lastIndexOf('.');
  const extension = dot >= 0 ? file.name.slice(dot + 1).toLowerCase() : '';
  return BY_EXTENSION[extension] ?? BY_TYPE[file.type.toLowerCase()] ?? null;
}

/**
 * The first published bound a file breaks, or null.
 *
 * @param durationSeconds - Its length as the browser read it; null when it could
 *   not (the server measures it anyway, before any engine is paid).
 */
export function importRefusal(
  file: { name: string; type: string; size: number },
  durationSeconds: number | null,
  limits: MeetingImportLimits
): ImportRefusal | null {
  if (importFormatOf(file) === null) return 'unsupported';
  if (file.size === 0) return 'empty';
  if (file.size > limits.max_bytes) return 'too_large';
  if (durationSeconds !== null && durationSeconds > limits.max_duration_minutes * 60)
    return 'too_long';
  return null;
}

/** When the meeting began: the file's last write minus its length (when known). */
export function defaultRecordedAt(lastModified: number, durationSeconds: number | null): Date {
  return new Date(lastModified - Math.round((durationSeconds ?? 0) * 1000));
}

const pad = (value: number) => String(value).padStart(2, '0');

/** A `datetime-local` value, in the reader's own clock, to the minute. */
export function toLocalInput(date: Date): string {
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

/** The instant a `datetime-local` value names, or null when it names none. */
export function fromLocalInput(value: string): Date | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? date : null;
}

/**
 * The file's length as the browser reads it, or null (unknown format, a
 * decoder that never answers): the server's measure decides anyway.
 */
export function readAudioDuration(file: Blob, timeoutMs = 8000): Promise<number | null> {
  return new Promise(resolve => {
    const url = URL.createObjectURL(file);
    const audio = new Audio();
    const settle = (value: number | null) => {
      clearTimeout(timer);
      audio.removeAttribute('src');
      URL.revokeObjectURL(url);
      resolve(value);
    };
    const timer = setTimeout(() => settle(null), timeoutMs);
    audio.preload = 'metadata';
    audio.onloadedmetadata = () =>
      settle(Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : null);
    audio.onerror = () => settle(null);
    audio.src = url;
  });
}
