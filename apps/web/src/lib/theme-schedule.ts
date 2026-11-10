import type { ThemeModeState } from './theme-mode';

export const THEME_SCHEDULE_STORAGE_KEY = 'lia-theme-schedule';
export const DEFAULT_LIGHT_START_MINUTE = 420;
export const DEFAULT_DARK_START_MINUTE = 1200;
export const THEME_CLOCK_INTERVAL_MS = 30_000;

export interface ThemeSchedule {
  lightStartMinute: number;
  darkStartMinute: number;
  timezone: string;
}

export interface StoredThemeSchedule extends ThemeSchedule {
  ownerId: string;
}

/** Resolve an account's civil-time display interval. */
export function automaticThemeAt(
  instant: number,
  timezone: string,
  lightStartMinute: number,
  darkStartMinute: number
): ThemeModeState {
  if (
    !Number.isInteger(lightStartMinute) ||
    !Number.isInteger(darkStartMinute) ||
    lightStartMinute < 0 ||
    darkStartMinute < 0 ||
    lightStartMinute >= 1440 ||
    darkStartMinute >= 1440 ||
    lightStartMinute === darkStartMinute
  )
    throw new RangeError('Invalid theme schedule');
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: timezone,
    hour: 'numeric',
    minute: 'numeric',
    hourCycle: 'h23',
  }).formatToParts(new Date(instant));
  const minute =
    Number(parts.find(part => part.type === 'hour')?.value) * 60 +
    Number(parts.find(part => part.type === 'minute')?.value);
  const light =
    lightStartMinute < darkStartMinute
      ? minute >= lightStartMinute && minute < darkStartMinute
      : minute >= lightStartMinute || minute < darkStartMinute;
  return { mode: light ? 'light' : 'dark', oled: !light };
}

/** Parse untrusted device storage, using the same resolver as the blocking script. */
export function readThemeSchedule(): StoredThemeSchedule | null {
  try {
    const raw: unknown = JSON.parse(localStorage.getItem(THEME_SCHEDULE_STORAGE_KEY) ?? 'null');
    if (
      !raw ||
      typeof raw !== 'object' ||
      !('ownerId' in raw) ||
      typeof raw.ownerId !== 'string' ||
      !('timezone' in raw) ||
      typeof raw.timezone !== 'string' ||
      !('lightStartMinute' in raw) ||
      typeof raw.lightStartMinute !== 'number' ||
      !('darkStartMinute' in raw) ||
      typeof raw.darkStartMinute !== 'number'
    )
      return null;
    automaticThemeAt(Date.now(), raw.timezone, raw.lightStartMinute, raw.darkStartMinute);
    return {
      ownerId: raw.ownerId,
      timezone: raw.timezone,
      lightStartMinute: raw.lightStartMinute,
      darkStartMinute: raw.darkStartMinute,
    };
  } catch {
    return null;
  }
}

/** Device storage is best effort; an unavailable store never breaks rendering. */
export function writeThemeSchedule(value: StoredThemeSchedule | null): void {
  try {
    if (value) localStorage.setItem(THEME_SCHEDULE_STORAGE_KEY, JSON.stringify(value));
    else localStorage.removeItem(THEME_SCHEDULE_STORAGE_KEY);
  } catch {
    /* The in-memory preference still works in private mode. */
  }
}
