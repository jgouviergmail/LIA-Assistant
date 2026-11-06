'use client';

/**
 * CalendarList — which calendars a view draws (ADR-369, mock-up « Mes agendas »).
 *
 * Each calendar with its own colour (data) and a box that hides or shows it —
 * a choice of THIS device (`lib/workbench/calendar/preferences`). From `lg` a
 * list beside the view; below, the same choices in a menu of the toolbar.
 */
import { Layers, Settings2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { WorkbenchCalendar } from '@/lib/workbench/types';

import { CalendarSwatch } from './EventChip';

export interface CalendarListProps {
  lng: Language;
  calendars: readonly WorkbenchCalendar[];
  hidden: ReadonlySet<string>;
  onToggle: (calendarId: string) => void;
  /** Opens the management of the person's calendars, where the provider offers it. */
  onManage?: () => void;
}

export function CalendarList({ lng, calendars, hidden, onToggle, onManage }: CalendarListProps) {
  const { t } = useTranslation(lng);
  return (
    <section aria-labelledby="workbench-calendars" className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <h2
          id="workbench-calendars"
          className="text-xs font-semibold uppercase tracking-wide text-muted-foreground"
        >
          {t('workbench.calendar.calendars_title')}
        </h2>
        {onManage && (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            aria-label={t('workbench.calendar.manage_calendars')}
            onClick={onManage}
          >
            <Settings2 className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
        )}
      </div>
      <ul className="space-y-1">
        {calendars.map(calendar => (
          <li key={calendar.id}>
            <label className="flex cursor-pointer items-center gap-2 rounded-md px-1 py-1 text-sm hover:bg-muted">
              <Checkbox checked={!hidden.has(calendar.id)} onChange={() => onToggle(calendar.id)} />
              <CalendarSwatch color={calendar.color} className="h-3 w-3" />
              <span className="min-w-0 truncate">{calendar.name}</span>
            </label>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function CalendarListMenu({
  lng,
  calendars,
  hidden,
  onToggle,
  onManage,
}: CalendarListProps) {
  const { t } = useTranslation(lng);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="gap-1.5 lg:hidden">
          <Layers className="h-4 w-4" aria-hidden="true" />
          {t('workbench.calendar.calendars_menu')}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        <DropdownMenuLabel>{t('workbench.calendar.calendars_title')}</DropdownMenuLabel>
        {calendars.map(calendar => (
          <DropdownMenuCheckboxItem
            key={calendar.id}
            checked={!hidden.has(calendar.id)}
            onCheckedChange={() => onToggle(calendar.id)}
            onSelect={event => event.preventDefault()}
            className="gap-2"
          >
            <CalendarSwatch color={calendar.color} className="h-3 w-3" />
            {calendar.name}
          </DropdownMenuCheckboxItem>
        ))}
        {onManage && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={onManage}>
              {t('workbench.calendar.manage_calendars')}
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
