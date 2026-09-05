'use client';

/**
 * The weekly grid of the routines: hours down, days across (ADR-265).
 *
 * A real `<table>`, because that is what a two-dimensional grid IS: a screen
 * reader walks it by row and column header, which no stack of `<div>`s with
 * ARIA bolted on gives for free. Rows are the 24 hours at a fixed height, so
 * the axis stays linear; columns are the ISO week, Monday first, the same
 * order and the same labels as the day picker of the form.
 *
 * What the grid claims, and where each claim comes from:
 *
 * - **Position** is the routine's own schedule — `trigger_hour` on the row,
 *   `days_of_week` on the columns — read as the wall clock of the routine's
 *   zone, which is named beside the grid. No instant is converted here.
 * - **Colour** is the current week's facts, computed server-side from the
 *   scheduler's own cron engine (`/scheduled-actions/week`): the browser
 *   never re-reads a schedule, it paints. When that read is unavailable the
 *   grid still draws, every chip idle, and SAYS the states are unavailable
 *   rather than leaving a silent white.
 * - **Today** is the column of the routines' zone, from the same read, with
 *   `Intl` as the fallback — a zone NAME, never a schedule.
 *
 * A chip is a `<button>`: it names the routine, its time and its state, and
 * takes the reader to the card. The title itself is never rendered as text
 * here — the card owns it, and a second visible copy would make every
 * "find the routine by name" query ambiguous.
 */

import { AlertTriangle } from 'lucide-react';
import { memo, useMemo, useRef, useState } from 'react';

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { RoutineNumberChip } from '@/components/settings/RoutineNumberChip';
import type { ScheduledActionWeekResponse } from '@/hooks/useScheduledActions';
import { useTranslation } from '@/i18n/client';
import { getIntlLocale, type Language } from '@/i18n/settings';
import {
  buildTimelineGrid,
  chipKey,
  chipState,
  GRID_HOURS,
  ISO_WEEKDAYS,
  isoWeekdayInZone,
  routineZones,
  rovingTarget,
  timelineKey,
  triggerTimeLabel,
  weekDates,
  type ChipState,
  type ChipTone,
  type NumberedAction,
  type TimelineEntry,
} from '@/lib/scheduled-actions';
import { cn } from '@/lib/utils';

export interface ScheduledActionsTimelineProps {
  lng: Language;
  /** Routines in chronological order, numbered (`numberByTriggerTime`). */
  numbered: readonly NumberedAction[];
  /** The current week's states, or null while unknown / unavailable. */
  week: ScheduledActionWeekResponse | null;
  /** A chip was activated: take the reader to that routine's card. */
  onSelect: (actionId: string) => void;
  /** The instant "today" is read at. Defaults to now; a test pins it. */
  now?: Date;
}

/** The legend, in reading order: every tone the grid can show. */
const LEGEND_TONES: readonly ChipTone[] = ['idle', 'success', 'failure', 'proposed', 'paused'];

/** The wording key of a chip's state: running first, then the reason, then the tone. */
function stateKey(state: ChipState): string {
  if (state.executing) return 'executing';
  return state.reason ?? state.tone;
}

/**
 * The column to highlight, or null when the routines disagree on what day it is.
 *
 * From the server's week when it is there (one reading per routine, all
 * equal when the zones are), from `Intl` on the routines' single zone
 * otherwise, and nothing at all across several zones — a highlight that is
 * right for one routine and wrong for its neighbour is worse than none.
 */
function todayColumn(
  numbered: readonly NumberedAction[],
  week: ScheduledActionWeekResponse | null,
  now: Date
): number | null {
  const zones = routineZones(numbered.map(n => n.action));
  if (zones.length !== 1) return null;
  const fromWeek = new Set(week?.actions.map(w => w.today) ?? []);
  if (fromWeek.size === 1) return [...fromWeek][0] ?? null;
  return isoWeekdayInZone(now, zones[0] as string);
}

/** The seven dates of the week when every routine agrees on which week it is. */
function headerDates(week: ScheduledActionWeekResponse | null): string[] {
  const starts = new Set(week?.actions.map(w => w.week_start) ?? []);
  if (starts.size !== 1) return [];
  return weekDates([...starts][0] as string);
}

/** Renders an instant in a routine's zone; the caller caches the formatters. */
type RunAtFormatter = (iso: string, timeZone: string) => string;

/**
 * One `Intl.DateTimeFormat` per (locale, zone), reused across chips and
 * renders: the constructor is the expensive part, and a page with fifty
 * routines draws up to 350 chips (`occurrences.ts` measured the same trap).
 */
function makeRunAtFormatter(intlLocale: string): RunAtFormatter {
  const cache = new Map<string, Intl.DateTimeFormat | null>();
  return (iso, timeZone) => {
    let formatter = cache.get(timeZone);
    if (formatter === undefined) {
      try {
        formatter = new Intl.DateTimeFormat(intlLocale, {
          dateStyle: 'short',
          timeStyle: 'short',
          timeZone,
        });
      } catch {
        // An unknown zone must not blank the tooltip: fall back to the reader's.
        formatter = null;
      }
      cache.set(timeZone, formatter);
    }
    const date = new Date(iso);
    return formatter ? formatter.format(date) : date.toLocaleString(intlLocale);
  };
}

function TimelineChip({
  entry,
  day,
  lng,
  formatRunAt,
  tabbable,
  onFocus,
  onSelect,
}: {
  entry: TimelineEntry;
  day: number;
  lng: Language;
  formatRunAt: RunAtFormatter;
  /** The ONE chip in the tab order (roving focus); the arrows reach the rest. */
  tabbable: boolean;
  onFocus: (key: string) => void;
  onSelect: (actionId: string) => void;
}) {
  const { t } = useTranslation(lng);
  const key = chipKey(entry.action.id, day);
  const state = chipState(entry.action, entry.cell);
  const stateLabel = t(`scheduled_actions.timeline.state.${stateKey(state)}`);
  const time = triggerTimeLabel(entry.action);
  const isCondition = (entry.action.trigger_kind ?? 'time') === 'condition';
  const runAt = entry.cell?.run_at
    ? formatRunAt(entry.cell.run_at, entry.action.user_timezone)
    : null;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          data-routine-chip={entry.action.id}
          data-chip-key={key}
          data-tone={state.tone}
          tabIndex={tabbable ? 0 : -1}
          onFocus={() => onFocus(key)}
          className="rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 active:scale-[0.98]"
          aria-label={t('scheduled_actions.timeline.chip_aria', {
            n: entry.number,
            title: entry.action.title,
            time,
            state: stateLabel,
          })}
          onClick={() => onSelect(entry.action.id)}
        >
          <RoutineNumberChip
            number={entry.number}
            tone={state.tone}
            kind={entry.action.trigger_kind ?? 'time'}
            executing={state.executing}
          />
        </button>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs">
        <p className="font-medium text-foreground">
          {entry.number}. {entry.action.title}
        </p>
        <p className="tabular-nums">
          {time} · {stateLabel}
        </p>
        {isCondition && (
          <p className="text-muted-foreground">{t('scheduled_actions.timeline.condition_kind')}</p>
        )}
        {runAt && (
          <p className="tabular-nums text-muted-foreground">
            {t('scheduled_actions.timeline.run_at', { when: runAt })}
          </p>
        )}
        {entry.cell?.error && <p className="line-clamp-2 text-destructive">{entry.cell.error}</p>}
      </TooltipContent>
    </Tooltip>
  );
}

/**
 * Memoised on purpose: the section re-renders on every keystroke of its
 * create/edit form, and the grid's inputs (`numbered`, `week`, `onSelect`)
 * are all referentially stable across those renders.
 */
export const ScheduledActionsTimeline = memo(function ScheduledActionsTimeline({
  lng,
  numbered,
  week,
  onSelect,
  now,
}: ScheduledActionsTimelineProps) {
  const { t } = useTranslation(lng);
  const intlLocale = getIntlLocale(lng);
  const formatRunAt = useMemo(() => makeRunAtFormatter(intlLocale), [intlLocale]);
  // A pinned instant is memoised by its VALUE; an unpinned one is read inside
  // the memo, so "now" never becomes a dependency that changes every render.
  const pinnedNow = now?.getTime();

  const grid = useMemo(() => buildTimelineGrid(numbered, week), [numbered, week]);
  // Reading order of the chips — rows, then days — for the roving focus.
  const chipKeys = useMemo(
    () =>
      GRID_HOURS.flatMap(hour =>
        ISO_WEEKDAYS.flatMap(day =>
          (grid.get(timelineKey(day, hour)) ?? []).map(entry => chipKey(entry.action.id, day))
        )
      ),
    [grid]
  );
  // The chip the reader last visited keeps the tab stop; derived, so a chip
  // that left the grid hands it back to the first one without an effect.
  const [visitedKey, setVisitedKey] = useState<string | null>(null);
  const tabbableKey =
    visitedKey !== null && chipKeys.includes(visitedKey) ? visitedKey : (chipKeys[0] ?? null);
  const bodyRef = useRef<HTMLTableSectionElement>(null);
  const handleKeyDown = (event: React.KeyboardEvent<HTMLTableSectionElement>) => {
    const current = (event.target as HTMLElement).dataset.chipKey ?? null;
    if (current === null) return;
    const target = rovingTarget(chipKeys, current, event.key);
    if (target === null) return;
    event.preventDefault();
    bodyRef.current
      ?.querySelector<HTMLButtonElement>(`[data-chip-key="${CSS.escape(target)}"]`)
      ?.focus();
  };
  const zones = useMemo(() => routineZones(numbered.map(n => n.action)), [numbered]);
  const today = useMemo(
    () => todayColumn(numbered, week, pinnedNow === undefined ? new Date() : new Date(pinnedNow)),
    [numbered, week, pinnedNow]
  );
  const dates = useMemo(() => headerDates(week), [week]);
  const dayOfMonth = useMemo(
    () => new Intl.DateTimeFormat(intlLocale, { day: 'numeric', timeZone: 'UTC' }),
    [intlLocale]
  );

  const zoneLine =
    zones.length === 1
      ? t('scheduled_actions.timeline.hours_in_zone', { zone: zones[0] })
      : t('scheduled_actions.timeline.zones_mixed');

  return (
    <TooltipProvider delayDuration={200}>
      <div className="space-y-3">
        <p className="text-[11px] text-muted-foreground">{zoneLine}</p>

        {week === null && (
          <p role="status" className="flex items-start gap-1.5 text-[11px] text-muted-foreground">
            <AlertTriangle className="mt-px h-3 w-3 shrink-0 text-warning" aria-hidden="true" />
            <span>{t('scheduled_actions.timeline.unavailable')}</span>
          </p>
        )}

        <div className="overflow-x-auto">
          <table
            className="w-full min-w-[18rem] table-fixed border-separate border-spacing-0"
            data-timeline-grid
          >
            <caption className="sr-only">
              {t('scheduled_actions.timeline.caption', { zone: zones.join(', ') })}
            </caption>
            <colgroup>
              <col className="w-9" />
              {ISO_WEEKDAYS.map(day => (
                <col key={day} />
              ))}
            </colgroup>
            <thead>
              <tr>
                <th
                  scope="col"
                  className="pb-1.5 text-right text-[10px] font-medium text-muted-foreground"
                >
                  <span className="sr-only">{t('scheduled_actions.timeline.hour_header')}</span>
                </th>
                {ISO_WEEKDAYS.map((day, index) => {
                  const isToday = day === today;
                  return (
                    <th
                      key={day}
                      scope="col"
                      aria-current={isToday ? 'date' : undefined}
                      data-today={isToday || undefined}
                      className={cn(
                        'px-0.5 pb-1.5 text-center text-[11px] font-medium leading-tight',
                        isToday ? 'text-primary' : 'text-muted-foreground'
                      )}
                    >
                      <span className="block truncate">{t(`scheduled_actions.days.d${day}`)}</span>
                      {dates[index] && (
                        <span
                          className={cn(
                            'block text-[10px] tabular-nums',
                            isToday ? 'font-semibold' : 'font-normal'
                          )}
                        >
                          {dayOfMonth.format(new Date(`${dates[index]}T00:00:00Z`))}
                        </span>
                      )}
                      {isToday && (
                        <span className="sr-only">{t('scheduled_actions.timeline.today')}</span>
                      )}
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody ref={bodyRef} onKeyDown={handleKeyDown}>
              {GRID_HOURS.map(hour => (
                <tr key={hour}>
                  <th
                    scope="row"
                    className="h-7 border-t border-border/40 pr-1.5 text-right align-top text-[10px] font-normal leading-7 tabular-nums text-muted-foreground"
                  >
                    {String(hour).padStart(2, '0')}
                  </th>
                  {ISO_WEEKDAYS.map(day => {
                    const entries = grid.get(timelineKey(day, hour)) ?? [];
                    return (
                      <td
                        key={day}
                        className={cn(
                          'h-7 border-l border-t border-border/40 p-0.5 align-top',
                          day === today && 'bg-primary/5'
                        )}
                      >
                        {entries.length > 0 && (
                          <div className="flex flex-wrap items-start justify-center gap-0.5">
                            {entries.map(entry => (
                              <TimelineChip
                                key={entry.action.id}
                                entry={entry}
                                day={day}
                                lng={lng}
                                formatRunAt={formatRunAt}
                                tabbable={chipKey(entry.action.id, day) === tabbableKey}
                                onFocus={setVisitedKey}
                                onSelect={onSelect}
                              />
                            ))}
                          </div>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <ul
          className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] text-muted-foreground"
          aria-label={t('scheduled_actions.timeline.legend_title')}
        >
          {LEGEND_TONES.map(tone => (
            <li key={tone} className="flex items-center gap-1.5">
              <RoutineNumberChip
                number={0}
                tone={tone}
                className="h-4 min-w-4 w-4 px-0 text-transparent"
              />
              <span>{t(`scheduled_actions.timeline.state.${tone}`)}</span>
            </li>
          ))}
          <li className="flex items-center gap-1.5">
            <RoutineNumberChip
              number={0}
              tone="idle"
              kind="condition"
              className="h-4 min-w-4 w-4 px-0 text-transparent"
            />
            <span>{t('scheduled_actions.timeline.condition_kind')}</span>
          </li>
        </ul>
      </div>
    </TooltipProvider>
  );
});
