/** Local-time presentation of the received server page. Never reorders or infers capture times. */
import type { Language } from '@/i18n/settings';
import type { MeetingSummary } from '@/types/meetings';

export type MeetingPeriod = 'night' | 'morning' | 'midday' | 'afternoon' | 'evening' | 'unknown';
export interface MeetingTimelineItem {
  meeting: MeetingSummary;
  start: string | null;
  end: string | null;
  endDay: string | null;
}
export interface MeetingTimelineDay {
  id: string;
  key: string;
  label: string | null;
  dayNumber: string | null;
  month: string | null;
  periods: { id: string; key: MeetingPeriod; entries: MeetingTimelineItem[] }[];
}

function validDate(value: string | null): Date | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? date : null;
}

function periodAt(hour: number): MeetingPeriod {
  if (hour < 6) return 'night';
  if (hour < 12) return 'morning';
  if (hour < 14) return 'midday';
  if (hour < 18) return 'afternoon';
  return 'evening';
}

function createFormatters(lng: Language, timeZone: string) {
  const options = { timeZone };
  const localParts = new Intl.DateTimeFormat('en', {
    ...options,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    hourCycle: 'h23',
    numberingSystem: 'latn',
  });
  const time = new Intl.DateTimeFormat(lng, { ...options, hour: '2-digit', minute: '2-digit' });
  const offset = new Intl.DateTimeFormat('en', { ...options, timeZoneName: 'shortOffset' });
  const zonedTime = new Intl.DateTimeFormat(lng, {
    ...options,
    hour: '2-digit',
    minute: '2-digit',
    timeZoneName: 'shortOffset',
  });
  const label = new Intl.DateTimeFormat(lng, { ...options, dateStyle: 'full' });
  const dayNumber = new Intl.DateTimeFormat(lng, { ...options, day: 'numeric' });
  const month = new Intl.DateTimeFormat(lng, { ...options, month: 'short' });
  const endDay = new Intl.DateTimeFormat(lng, { ...options, dateStyle: 'medium' });
  const parts = (date: Date) =>
    Object.fromEntries(localParts.formatToParts(date).map(part => [part.type, part.value]));
  const dayKey = (date: Date) => {
    const p = parts(date);
    return `${p.year}-${p.month}-${p.day}`;
  };
  const zoneOffset = (date: Date) =>
    offset.formatToParts(date).find(part => part.type === 'timeZoneName')?.value;
  return { time, zonedTime, label, dayNumber, month, endDay, parts, dayKey, zoneOffset };
}
type TimelineFormatters = ReturnType<typeof createFormatters>;

function projectTimes(
  meeting: MeetingSummary,
  start: Date | null,
  formats: TimelineFormatters
): MeetingTimelineItem {
  const end = validDate(meeting.stopped_at);
  const changesOffset = start && end && formats.zoneOffset(start) !== formats.zoneOffset(end);
  const clock = changesOffset ? formats.zonedTime : formats.time;
  const differentDay = end && (!start || formats.dayKey(end) !== formats.dayKey(start));
  return {
    meeting,
    start: start ? clock.format(start) : null,
    end: end ? clock.format(end) : null,
    endDay: differentDay ? formats.endDay.format(end) : null,
  };
}

function newDay(
  start: Date | null,
  key: string,
  id: string,
  formats: TimelineFormatters
): MeetingTimelineDay {
  return {
    id,
    key,
    label: start ? formats.label.format(start) : null,
    dayNumber: start ? formats.dayNumber.format(start) : null,
    month: start ? formats.month.format(start) : null,
    periods: [],
  };
}

/** The browser zone is the existing list contract; capture zones are not in MeetingSummary. */
export function projectMeetingTimeline(
  meetings: readonly MeetingSummary[],
  lng: Language,
  timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone
): { timeZone: string; days: MeetingTimelineDay[] } {
  const formats = createFormatters(lng, timeZone);
  const days: MeetingTimelineDay[] = [];
  const dayOccurrences = new Map<string, number>();
  const periodOccurrences = new Map<MeetingPeriod, number>();
  const occurrenceId = <Key extends string>(key: Key, counts: Map<Key, number>) => {
    const occurrence = counts.get(key) ?? 0;
    counts.set(key, occurrence + 1);
    return `${key}-${occurrence}`;
  };

  for (const meeting of meetings) {
    const start = validDate(meeting.started_at);
    const key = start ? formats.dayKey(start) : 'unknown';
    let day = days.at(-1);
    // Contiguous groups preserve the server order even on a malformed/unsorted page.
    if (!day || day.key !== key) {
      day = newDay(start, key, occurrenceId(key, dayOccurrences), formats);
      days.push(day);
      periodOccurrences.clear();
    }
    const periodKey = start ? periodAt(Number(formats.parts(start).hour)) : 'unknown';
    let period = day.periods.at(-1);
    if (!period || period.key !== periodKey) {
      period = { id: occurrenceId(periodKey, periodOccurrences), key: periodKey, entries: [] };
      day.periods.push(period);
    }
    period.entries.push(projectTimes(meeting, start, formats));
  }
  return { timeZone, days };
}
