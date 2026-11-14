/** The hub's display vocabulary; complete routine collections filter before paging. */
import type { ScheduledActionRow } from '@/components/notifications/ScheduledActionsList';
import { normalizeSearchText } from '@/lib/utils';

export const ALERT_CATEGORIES = [
  'peer_messages',
  'proactive',
  'interests',
  'reminders',
  'scheduled',
  'workboard',
  'discussions',
  'sms',
] as const;
export type AlertCategory = (typeof ALERT_CATEGORIES)[number];
export interface AlertCriteria {
  q: string;
  sort: '' | 'recent' | 'oldest' | 'name';
  category: '' | AlertCategory;
}
export type AlertDisplayQuery = Pick<AlertCriteria, 'q' | 'sort'>;
export const DEFAULT_ALERT_CRITERIA: AlertCriteria = { q: '', sort: '', category: '' };

export function alertParams(query: AlertDisplayQuery) {
  return { q: query.q, ...(query.sort ? { sort: query.sort } : {}) };
}

function nextInstant(row: ScheduledActionRow): number | null {
  // Only a schedule announces a run (ADR-322, ADR-386).
  if (!row.is_enabled || row.trigger_kind !== 'time' || !row.next_trigger_at) return null;
  const instant = Date.parse(row.next_trigger_at);
  return Number.isFinite(instant) ? instant : null;
}

function compareNext(a: ScheduledActionRow, b: ScheduledActionRow, recent: boolean): number {
  const left = nextInstant(a),
    right = nextInstant(b);
  if (left === null) return right === null ? 0 : 1;
  if (right === null) return -1;
  return recent ? right - left : left - right;
}

const compareText = (a: string, b: string): number => (a < b ? -1 : a > b ? 1 : 0);

export function scheduledDisplayRows(
  rows: readonly ScheduledActionRow[],
  query: AlertDisplayQuery
): ScheduledActionRow[] {
  const needle = normalizeSearchText(query.q.trim());
  return rows
    .filter(row =>
      [row.title, row.schedule_display].some(value => normalizeSearchText(value).includes(needle))
    )
    .sort((a, b) => {
      const order =
        query.sort === 'name'
          ? compareText(normalizeSearchText(a.title), normalizeSearchText(b.title))
          : compareNext(a, b, query.sort === 'recent');
      return order || compareText(a.id, b.id);
    });
}
