'use client';

import { useCallback, useMemo, useSyncExternalStore } from 'react';
import { CalendarDays } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/hooks/useAuth';
import { fallbackLng, isLanguage } from '@/i18n/settings';
import { formatDate } from '@/lib/format';
import { cn } from '@/lib/utils';

type DayReader = (instant: number) => string;

/** Search civil dates, rather than adding 24 hours across a DST transition. */
function nextDayDelay(now: number, readDay: DayReader): number {
  const today = readDay(now);
  let first = now + 1;
  let last = now + 48 * 60 * 60 * 1000;
  while (first < last) {
    const middle = Math.floor((first + last) / 2);
    if (readDay(middle) === today) first = middle + 1;
    else last = middle;
  }
  return first - now;
}

function dateReader(lng: string, timezone: string | undefined): DayReader | null {
  if (!timezone) return null;
  const locale = isLanguage(lng) ? lng : fallbackLng;
  const options: Intl.DateTimeFormatOptions = {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    timeZone: timezone,
  };
  try {
    // Validation is explicit: Intl's omitted timezone would use the browser's.
    new Intl.DateTimeFormat(locale, options);
    return instant => {
      const label = formatDate(new Date(instant), locale, options);
      return label.charAt(0).toLocaleUpperCase(locale) + label.slice(1);
    };
  } catch {
    return null;
  }
}

/** The clock is an external store; SSR and hydration both start with the title. */
export function DashboardDateHeading({ lng, className }: { lng: string; className?: string }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const timezone = user?.timezone;
  const readDay = useMemo(() => dateReader(lng, timezone), [lng, timezone]);
  const getSnapshot = useCallback(() => readDay?.(Date.now()) ?? null, [readDay]);
  const subscribe = useCallback(
    (onStoreChange: () => void) => {
      if (!readDay) return () => {};
      let timer: ReturnType<typeof setTimeout>;
      const refresh = () => {
        clearTimeout(timer);
        onStoreChange();
        const now = Date.now();
        timer = setTimeout(refresh, nextDayDelay(now, readDay));
      };
      const onVisibility = () => {
        if (document.visibilityState === 'visible') refresh();
      };
      refresh();
      window.addEventListener('focus', refresh);
      document.addEventListener('visibilitychange', onVisibility);
      return () => {
        clearTimeout(timer);
        window.removeEventListener('focus', refresh);
        document.removeEventListener('visibilitychange', onVisibility);
      };
    },
    [readDay]
  );
  const date = useSyncExternalStore(subscribe, getSnapshot, () => null);

  return (
    <h1
      className={cn(
        'flex items-center gap-3 text-2xl font-bold tracking-tight text-foreground sm:text-3xl',
        className
      )}
    >
      <CalendarDays className="size-7 shrink-0 text-primary" aria-hidden="true" />
      <span>{date ?? t('dashboard.title')}</span>
    </h1>
  );
}
