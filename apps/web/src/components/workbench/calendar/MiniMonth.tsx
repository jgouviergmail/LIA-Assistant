'use client';

/**
 * MiniMonth — a month to pick a day from (ADR-369, mock-up « Agenda », left
 * column).
 *
 * The same six-week grid as the month view, from the locale's first weekday;
 * its own arrows page through months without moving the view; a day moves the
 * view to it. Walked with the keyboard like the month view (arrows, Home, End).
 */
import { ChevronLeft, ChevronRight } from '@/lib/icons';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import { getIntlLocale, type Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import { longDay, monthLabel } from '@/lib/workbench/calendar/format';
import { monthGrid } from '@/lib/workbench/calendar/layout';
import { addMonths, firstWeekday } from '@/lib/workbench/calendar/zoned';

import { useRovingGrid } from './useRovingGrid';

export interface MiniMonthProps {
  lng: Language;
  /** The day the view holds. */
  day: string;
  today: string;
  onPick: (day: string) => void;
}

export function MiniMonth({ lng, day, today, onPick }: MiniMonthProps) {
  const { t } = useTranslation(lng);
  const [month, setMonth] = useState(`${day.slice(0, 7)}-01`);
  return (
    <section aria-label={t('workbench.calendar.mini_month')} className="space-y-1">
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-semibold" aria-live="polite">
          {monthLabel(month, lng)}
        </h2>
        <span className="flex">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => setMonth(addMonths(month, -1))}
            aria-label={t('workbench.calendar.mini_previous')}
          >
            <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => setMonth(addMonths(month, 1))}
            aria-label={t('workbench.calendar.mini_next')}
          >
            <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
        </span>
      </div>
      {/* Keyed by month: the cell in the tab order starts on that month's own day. */}
      <MiniGrid key={month} lng={lng} month={month} day={day} today={today} onPick={onPick} />
    </section>
  );
}

function MiniGrid({ lng, month, day, today, onPick }: MiniMonthProps & { month: string }) {
  const days = monthGrid(month, firstWeekday(getIntlLocale(lng)));
  const start = [day, today, month].map(item => days.indexOf(item)).find(index => index >= 0) ?? 0;
  const grid = useRovingGrid(days.length, start);
  const narrow = new Intl.DateTimeFormat(getIntlLocale(lng), {
    weekday: 'narrow',
    timeZone: 'UTC',
  });
  return (
    <div role="grid" aria-label={monthLabel(month, lng)} className="grid grid-cols-7 text-center">
      <div role="row" className="contents">
        {days.slice(0, 7).map(item => (
          <span key={item} role="columnheader" className="py-1 text-[11px] text-muted-foreground">
            {narrow.format(new Date(`${item}T00:00:00Z`))}
          </span>
        ))}
      </div>
      {Array.from({ length: days.length / 7 }, (_, week) => (
        <div key={week} role="row" className="contents">
          {days.slice(week * 7, week * 7 + 7).map((item, index) => (
            <span key={item} role="gridcell" className="flex justify-center">
              <button
                type="button"
                {...grid.cell(week * 7 + index)}
                onClick={() => onPick(item)}
                aria-label={longDay(item, lng)}
                aria-current={item === day ? 'date' : undefined}
                className={cn(
                  'h-7 w-7 rounded-full text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                  item.slice(0, 7) !== month.slice(0, 7) && 'text-muted-foreground',
                  item === day && 'bg-primary/15 font-semibold text-primary',
                  item === today && 'bg-primary font-semibold text-primary-foreground'
                )}
              >
                {Number(item.slice(8))}
              </button>
            </span>
          ))}
        </div>
      ))}
    </div>
  );
}
