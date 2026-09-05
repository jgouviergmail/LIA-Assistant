/**
 * A process uptime as a human reads it when deciding whether "a recent
 * deployment" explains an incident (ADR-266): one locale unit — minutes under
 * an hour, hours under a day, days beyond — through `Intl`, so it needs no
 * translation key and cannot drift between the six locales.
 */

const SECONDS_PER_MINUTE = 60;
const SECONDS_PER_HOUR = 3600;
const SECONDS_PER_DAY = 86400;

type UptimeUnit = 'minute' | 'hour' | 'day';

function pick(seconds: number): { unit: UptimeUnit; value: number } {
  if (seconds >= SECONDS_PER_DAY) {
    return { unit: 'day', value: Math.floor(seconds / SECONDS_PER_DAY) };
  }
  if (seconds >= SECONDS_PER_HOUR) {
    return { unit: 'hour', value: Math.floor(seconds / SECONDS_PER_HOUR) };
  }
  return { unit: 'minute', value: Math.floor(seconds / SECONDS_PER_MINUTE) };
}

/**
 * Format an uptime in seconds as `47 min`, `2 h`, `3 days` in the reader's
 * locale. Negative input reads as zero; an unknown locale falls back to the
 * engine default rather than throwing — a number the panel cannot render is
 * worse than a number in the wrong language.
 */
export function formatUptime(seconds: number, lng: string): string {
  const { unit, value } = pick(Math.max(0, Math.floor(seconds)));
  try {
    return new Intl.NumberFormat(lng, { style: 'unit', unit, unitDisplay: 'short' }).format(value);
  } catch {
    return new Intl.NumberFormat(undefined, { style: 'unit', unit, unitDisplay: 'short' }).format(
      value
    );
  }
}
