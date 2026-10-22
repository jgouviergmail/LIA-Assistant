'use client';

import { useTranslation } from '@/i18n/client';
import { getIntlLocale, type Language } from '@/i18n/settings';
import { contextTimeline } from '@/lib/discussion-context';
import type { DiscussionContextItem } from '@/types/proactive-discussions';

/** When an item's evidence happened, and when LIA last read it; nothing is invented. */
export function DiscussionContextTimeline({
  lng,
  item,
}: {
  lng: Language;
  item: DiscussionContextItem;
}) {
  const { t } = useTranslation(lng);
  const { start, end, updated } = contextTimeline(item);
  const locale = getIntlLocale(lng);
  const day = (value: string) =>
    new Date(value).toLocaleDateString(locale, { dateStyle: 'medium' });
  const moment = (value: string) =>
    new Date(value).toLocaleString(locale, { dateStyle: 'medium', timeStyle: 'short' });
  const parts = [
    start && end && day(start) !== day(end)
      ? t('discussions.item_period', { start: day(start), end: day(end) })
      : start && t('discussions.item_on', { date: day(start) }),
    updated && t('discussions.item_updated', { date: moment(updated) }),
  ].filter(Boolean);
  if (parts.length === 0) return null;
  return <p className="text-xs text-muted-foreground">{parts.join(' · ')}</p>;
}
