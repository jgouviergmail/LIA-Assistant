/**
 * Dates, numbers and search text of the living maps, in the reader's language.
 *
 * Dates in the data are civil `YYYY-MM-DD` (or `YYYY-MM`) strings: they are
 * formatted in UTC so that no reader's timezone can move a decision to the day
 * before.
 */

import { getIntlLocale, type Language } from '@/i18n/settings';

/** A civil date string as a UTC instant (day 1 when the day is absent). */
export function civilDate(iso: string): Date {
  const [year, month, day] = iso.split('-').map(Number);
  return new Date(Date.UTC(year, (month ?? 1) - 1, day || 1));
}

/** The formatters of one language, built once per render. */
export interface MapsFormat {
  /** "24 septembre 2026". */
  day: (iso: string) => string;
  /** "24 sept. 2026". */
  dayShort: (iso: string) => string;
  /** "septembre 2026". */
  month: (isoMonth: string) => string;
  /** "sept. 26" — an axis label. */
  monthAxis: (isoMonth: string) => string;
  /** 1 069 / 1,069 / 1.069. */
  number: (value: number) => string;
}

export function mapsFormat(lng: Language): MapsFormat {
  const locale = getIntlLocale(lng);
  const day = new Intl.DateTimeFormat(locale, {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  });
  const dayShort = new Intl.DateTimeFormat(locale, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  });
  const month = new Intl.DateTimeFormat(locale, {
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  });
  const monthAxis = new Intl.DateTimeFormat(locale, {
    month: 'short',
    year: '2-digit',
    timeZone: 'UTC',
  });
  const number = new Intl.NumberFormat(locale);
  return {
    day: iso => day.format(civilDate(iso)),
    dayShort: iso => dayShort.format(civilDate(iso)),
    month: isoMonth => month.format(civilDate(`${isoMonth}-01`)),
    monthAxis: isoMonth => monthAxis.format(civilDate(`${isoMonth}-01`)),
    number: value => number.format(value),
  };
}

/** Folded for search: no accent, no case — "Mémoire" matches "memoire". */
export function foldForSearch(text: string): string {
  return text.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
}
