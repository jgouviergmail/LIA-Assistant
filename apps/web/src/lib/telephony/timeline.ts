import type { Language } from '@/i18n/settings';
import { ACTIVE_CALL_STATUSES, type TelephonyCallSummary } from '@/types/telephony';

export interface CallTimelineItem {
  call: TelephonyCallSummary;
  start: string | null;
  end: string | null;
  endDay: string | null;
}
export interface CallTimelineDay {
  id: string;
  key: string;
  label: string | null;
  dayNumber: string | null;
  month: string | null;
  entries: CallTimelineItem[];
}

function validDate(value: string | null): Date | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? date : null;
}

function createFormatters(lng: Language, timeZone: string) {
  const options = { timeZone };
  const localDate = new Intl.DateTimeFormat('en', {
    ...options,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    calendar: 'gregory',
    numberingSystem: 'latn',
  });
  const time = new Intl.DateTimeFormat(lng, { ...options, hour: '2-digit', minute: '2-digit' });
  const zonedTime = new Intl.DateTimeFormat(lng, {
    ...options,
    hour: '2-digit',
    minute: '2-digit',
    timeZoneName: 'shortOffset',
  });
  const offset = new Intl.DateTimeFormat('en', { ...options, timeZoneName: 'shortOffset' });
  const label = new Intl.DateTimeFormat(lng, { ...options, dateStyle: 'full' });
  const endDay = new Intl.DateTimeFormat(lng, { ...options, dateStyle: 'medium' });
  const dayNumber = new Intl.DateTimeFormat(lng, { ...options, day: 'numeric' });
  const month = new Intl.DateTimeFormat(lng, { ...options, month: 'short' });
  const dayKey = (date: Date) => {
    const parts = Object.fromEntries(
      localDate.formatToParts(date).map(part => [part.type, part.value])
    );
    return `${parts.year}-${parts.month}-${parts.day}`;
  };
  const zoneOffset = (date: Date) =>
    offset.formatToParts(date).find(part => part.type === 'timeZoneName')?.value;
  return { time, zonedTime, label, endDay, dayKey, zoneOffset, dayNumber, month };
}
type TimelineFormatters = ReturnType<typeof createFormatters>;

function projectTimes(
  call: TelephonyCallSummary,
  start: Date | null,
  formats: TimelineFormatters
): CallTimelineItem {
  const suppliedEnd = validDate(call.completed_at);
  const end =
    !ACTIVE_CALL_STATUSES.includes(call.status) &&
    suppliedEnd &&
    (!start || suppliedEnd.getTime() >= start.getTime())
      ? suppliedEnd
      : null;
  const changesOffset = start && end && formats.zoneOffset(start) !== formats.zoneOffset(end);
  const clock = changesOffset ? formats.zonedTime : formats.time;
  const differentDay = end && (!start || formats.dayKey(end) !== formats.dayKey(start));
  return {
    call,
    start: start ? clock.format(start) : null,
    end: end ? clock.format(end) : null,
    endDay: differentDay ? formats.endDay.format(end) : null,
  };
}

/** Contiguous browser-zone dates retain every row in the server's order. */
export function projectCallTimeline(
  calls: readonly TelephonyCallSummary[],
  lng: Language,
  timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone
): { days: CallTimelineDay[] } {
  const formats = createFormatters(lng, timeZone);
  const days: CallTimelineDay[] = [];
  const occurrences = new Map<string, number>();
  for (const call of calls) {
    const start = validDate(call.created_at);
    const key = start ? formats.dayKey(start) : 'unknown';
    let day = days.at(-1);
    if (!day || day.key !== key) {
      const occurrence = occurrences.get(key) ?? 0;
      occurrences.set(key, occurrence + 1);
      day = {
        id: `${key}-${occurrence}`,
        key,
        label: start ? formats.label.format(start) : null,
        dayNumber: start ? formats.dayNumber.format(start) : null,
        month: start ? formats.month.format(start) : null,
        entries: [],
      };
      days.push(day);
    }
    day.entries.push(projectTimes(call, start, formats));
  }
  return { days };
}
