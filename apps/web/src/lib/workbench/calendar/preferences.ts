/**
 * The calendar screen's per-device preferences (ADR-369, spec §7): which
 * calendars are hidden — per account, since calendar ids are an account's —
 * and the view the screen opens on.
 *
 * Kept in `localStorage`, every access wrapped (private windows and blocked
 * site data throw), outside the account purge registry, and read through
 * `useSyncExternalStore`: a change here or in another tab redraws the screen.
 * A snapshot is the stored STRING, stable between two reads; it is parsed by
 * the reader.
 */

/** The views of the screen. */
export type CalendarView = 'agenda' | 'week' | 'month';

export const CALENDAR_VIEWS: readonly CalendarView[] = ['agenda', 'week', 'month'];
export const CALENDAR_VIEW_KEY = 'lia_workbench_calendar_view';
const HIDDEN_KEY = 'lia_workbench_calendar_hidden';
/** Dispatched on `window` after every change, for `useSyncExternalStore`. */
const CHANGED = 'lia:workbench-calendar-preferences';

/** @returns The key of an account's hidden calendars. */
export function hiddenCalendarsKey(owner: string): string {
  return `${HIDDEN_KEY}:${owner}`;
}

/** @returns What is stored under `key`; null when nothing is or storage is refused. */
export function readCalendarPreference(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

/** Remembers `value` under `key` (a refused storage keeps it for the page only). */
export function writeCalendarPreference(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Storage unavailable (private window, blocked site data): nothing to keep.
  }
  window.dispatchEvent(new Event(CHANGED));
}

/** Calls `onChange` after every change of a calendar preference, here or in another tab. */
export function subscribeCalendarPreferences(onChange: () => void): () => void {
  const onStorage = (event: StorageEvent) => {
    if (event.key === CALENDAR_VIEW_KEY || event.key?.startsWith(HIDDEN_KEY)) onChange();
  };
  window.addEventListener(CHANGED, onChange);
  window.addEventListener('storage', onStorage);
  return () => {
    window.removeEventListener(CHANGED, onChange);
    window.removeEventListener('storage', onStorage);
  };
}

/** @returns The hidden calendars a stored value names; none for anything unreadable. */
export function parseHidden(stored: string | null): ReadonlySet<string> {
  if (!stored) return new Set();
  try {
    const value: unknown = JSON.parse(stored);
    return new Set(Array.isArray(value) ? value.filter(item => typeof item === 'string') : []);
  } catch {
    return new Set();
  }
}

/** @returns The view a stored value names; null for anything else. */
export function parseView(stored: string | null): CalendarView | null {
  return CALENDAR_VIEWS.find(view => view === stored) ?? null;
}
