'use client';

/**
 * CalendarToolbar — what moves the calendar's view (ADR-369, mock-up « Agenda »).
 *
 * Today, a step back and forward as far as the view reaches, what is shown, then
 * the calendars (below `lg`) and the views. A phone stacks them: today starts the first
 * line and what is shown ends it, the search takes all the room the calendars leave it,
 * and the views stand in the middle of theirs.
 */
import { ChevronLeft, ChevronRight } from '@/lib/icons';
import type { RefObject } from 'react';

import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { longDay, monthLabel, rangeLabel } from '@/lib/workbench/calendar/format';
import { CALENDAR_VIEWS, type CalendarView } from '@/lib/workbench/calendar/preferences';
import type { WorkbenchCalendar } from '@/lib/workbench/types';

import { CalendarListMenu } from './CalendarList';
import { CalendarSearchBox, type CalendarSearching } from './CalendarSearch';
import { stepDay, type CalendarAddress } from './useCalendarScreen';

/** What each view calls a step back and a step forward. */
const STEPS: Readonly<Record<CalendarView, readonly [string, string]>> = {
  agenda: ['workbench.calendar.earlier_days', 'workbench.calendar.later_days'],
  day: ['workbench.calendar.previous_day', 'workbench.calendar.next_day'],
  week: ['workbench.calendar.previous_week', 'workbench.calendar.next_week'],
  month: ['workbench.calendar.previous_month', 'workbench.calendar.next_month'],
};

function shownLabel(address: CalendarAddress, lng: Language): string {
  if (address.view === 'month') return monthLabel(address.day, lng);
  if (address.view === 'day') return longDay(address.day, lng);
  return rangeLabel(address.days[0], address.days[address.days.length - 1], lng);
}

export interface CalendarToolbarProps {
  lng: Language;
  today: string;
  todayRef: RefObject<HTMLButtonElement | null>;
  address: CalendarAddress;
  calendars: readonly WorkbenchCalendar[];
  hidden: ReadonlySet<string>;
  onToggle: (calendarId: string) => void;
  onManage?: () => void;
  searching: CalendarSearching;
}

export function CalendarToolbar({
  lng,
  today,
  todayRef,
  address,
  calendars,
  hidden,
  onToggle,
  onManage,
  searching,
}: CalendarToolbarProps) {
  const { t } = useTranslation(lng);
  const [earlier, later] = STEPS[address.view];
  return (
    <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2">
      <Button
        ref={todayRef}
        variant="outline"
        size="sm"
        onClick={() => address.move({ day: today })}
      >
        {t('workbench.calendar.today')}
      </Button>
      <Button
        variant="ghost"
        size="icon"
        onClick={() => address.move({ day: stepDay(address.view, address.day, -1) })}
        aria-label={t(earlier)}
      >
        <ChevronLeft className="h-4 w-4" aria-hidden="true" />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        onClick={() => address.move({ day: stepDay(address.view, address.day, 1) })}
        aria-label={t(later)}
      >
        <ChevronRight className="h-4 w-4" aria-hidden="true" />
      </Button>
      <h2 className="text-sm font-bold max-sm:ml-auto" aria-live="polite">
        {shownLabel(address, lng)}
      </h2>
      <span className="flex flex-wrap items-center justify-center gap-2 max-sm:w-full sm:ml-auto">
        <span className="flex items-center gap-2 max-sm:w-full">
          <CalendarSearchBox lng={lng} searching={searching} />
          <CalendarListMenu
            lng={lng}
            calendars={calendars}
            hidden={hidden}
            onToggle={onToggle}
            onManage={onManage}
          />
        </span>
        <span
          role="group"
          aria-label={t('workbench.calendar.view_label')}
          className="flex rounded-md border p-0.5"
        >
          {CALENDAR_VIEWS.map(view => (
            <Button
              key={view}
              variant="ghost"
              size="sm"
              aria-pressed={address.view === view}
              onClick={() => address.move({ view })}
              className="h-7 px-2.5 aria-pressed:bg-primary/10 aria-pressed:text-primary"
            >
              {t(`workbench.calendar.views.${view}`)}
            </Button>
          ))}
        </span>
      </span>
    </div>
  );
}
