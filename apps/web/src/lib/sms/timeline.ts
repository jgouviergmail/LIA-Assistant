import type { SmsMessage } from '@/types/sms';
export interface SmsDay {
  key: string;
  title: string;
  day: string;
  month: string;
  messages: SmsMessage[];
}
/** Bounded page projection uses the account zone rather than the device clock. */
export function projectSmsDays(
  messages: readonly SmsMessage[],
  locale: string,
  timeZone: string
): SmsDay[] {
  const keyFormat = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });
  const titleFormat = new Intl.DateTimeFormat(locale, { timeZone, dateStyle: 'full' });
  const groups = new Map<string, SmsDay>();
  const sorted = [...messages].sort(
    (a, b) => Date.parse(b.received_at) - Date.parse(a.received_at) || b.id.localeCompare(a.id)
  );
  for (const message of sorted) {
    const instant = new Date(message.received_at);
    const parts = keyFormat.formatToParts(instant);
    const get = (type: Intl.DateTimeFormatPartTypes) =>
      parts.find(part => part.type === type)?.value ?? '';
    const key = `${get('year')}-${get('month')}-${get('day')}`;
    let group = groups.get(key);
    if (!group) {
      group = {
        key,
        title: titleFormat.format(instant),
        day: get('day'),
        month: new Intl.DateTimeFormat(locale, { timeZone, month: 'short' }).format(instant),
        messages: [],
      };
      groups.set(key, group);
    }
    group.messages.push(message);
  }
  return [...groups.values()];
}
