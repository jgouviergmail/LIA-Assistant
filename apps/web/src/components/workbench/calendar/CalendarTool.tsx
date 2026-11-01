'use client';

/**
 * CalendarTool — the « Tools » calendar screen (ADR-369, spec §6.3, mock-up
 * « Agenda »).
 *
 * The account's calendars, those this device hides left out; the week holding
 * the day the address names, as an agenda or as a grid, on the account's wall
 * (its zone is said); the open event beside it from `xl`, in its place below.
 * A calendar that could not be read, one cut at the published bound, or events
 * whose times could not be read are SAID above the view — never an empty week
 * that looks quiet. Creating, changing and deleting are offered where the
 * calendar can be written; a video call and « tell the guests » where the
 * provider has them (the descriptor).
 */
import { ChevronLeft, ChevronRight, Plus } from 'lucide-react';
import { useCallback, useRef, useState, type KeyboardEvent, type RefObject } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { PaneSeparator } from '@/components/ui/pane-separator';
import { Skeleton } from '@/components/ui/skeleton';
import { useAuth } from '@/hooks/useAuth';
import { useDrillDownFocus } from '@/hooks/useDrillDownFocus';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import {
  useWorkbenchCalendar,
  useWorkbenchCalendars,
  type WorkbenchCalendarState,
} from '@/hooks/useWorkbenchCalendar';
import { useWorkbenchItem } from '@/hooks/useWorkbenchItem';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import { newEventFields } from '@/lib/workbench/calendar/editor';
import { shownEvents } from '@/lib/workbench/calendar/events';
import { monthLabel, rangeLabel } from '@/lib/workbench/calendar/format';
import { CALENDAR_VIEWS } from '@/lib/workbench/calendar/preferences';
import { instantToWall } from '@/lib/workbench/calendar/zoned';
import { refusalOfCode, workbenchRefusal } from '@/lib/workbench/errors';
import { dayIn } from '@/lib/workbench/tasks';
import { WORKBENCH_DESKTOP, WORKBENCH_PANE_HEIGHT } from '@/lib/workbench/tools';
import type {
  CalendarEventDetail,
  WorkbenchCalendar,
  WorkbenchLimits,
  WorkbenchToolAvailability,
} from '@/lib/workbench/types';

import { useWorkbench } from '../WorkbenchShell';
import { WorkbenchToolHeader } from '../WorkbenchToolHeader';
import { WorkbenchUnavailable, unavailableKind } from '../WorkbenchUnavailable';
import { PANE_SEPARATOR_CLASS, paneWidth, useWorkbenchPane } from '../useWorkbenchPane';
import { AgendaView } from './AgendaView';
import { CalendarList, CalendarListMenu } from './CalendarList';
import { EventDeleteDialog } from './EventDeleteDialog';
import { EventDetail } from './EventDetail';
import { EventEditor, type EditorTarget } from './EventEditor';
import { MiniMonth } from './MiniMonth';
import { MonthView } from './MonthView';
import {
  stepDay,
  useCalendarAddress,
  useHiddenCalendars,
  type CalendarAddress,
} from './useCalendarScreen';
import { WeekView } from './WeekView';

const NO_CALENDARS: readonly WorkbenchCalendar[] = [];
/** From here the event opens beside the view; below, in its place. */
const SIDE_BY_SIDE = '(min-width: 1280px)';

export function CalendarTool({ lng }: { lng: Language }) {
  const { availability } = useWorkbench();
  const tool = availability.tools.find(item => item.tool === 'calendar');
  if (tool?.state !== 'ready') {
    return (
      <>
        <WorkbenchToolHeader lng={lng} tool="calendar" />
        <WorkbenchUnavailable lng={lng} kind={unavailableKind(tool)} tool="calendar" />
      </>
    );
  }
  return <ReadyCalendar lng={lng} tool={tool} limits={availability.limits} />;
}

interface ReadyCalendarProps {
  lng: Language;
  tool: WorkbenchToolAvailability;
  limits: WorkbenchLimits;
}

/** The calendar a new event goes in: the account's own, else the first it can write. */
function defaultCalendar(calendars: readonly WorkbenchCalendar[]): WorkbenchCalendar | undefined {
  const writable = calendars.filter(calendar => calendar.writable);
  return writable.find(calendar => calendar.primary) ?? writable[0];
}

/** The hour a new event starts at: the next one today, nine o'clock another day. */
function startHour(day: string, today: string, zone: string): { day: string; time: string } {
  if (day !== today) return { day, time: '09:00' };
  const now = instantToWall(new Date(Date.now() + 60 * 60 * 1000), zone);
  return { day: now.date, time: `${now.time.slice(0, 2)}:00` };
}

function ReadyCalendar({ lng, tool, limits }: ReadyCalendarProps) {
  const { t } = useTranslation(lng);
  const { user } = useAuth();
  const zone = user?.timezone ?? 'UTC';
  const today = dayIn(zone, new Date());
  const desktop = useMediaQuery(WORKBENCH_DESKTOP);
  const address = useCalendarAddress(lng, today, desktop ? 'week' : 'agenda');
  const { hidden, toggle } = useHiddenCalendars(user?.id ?? '');
  const [editor, setEditor] = useState<{ id: number; target: EditorTarget } | null>(null);
  const [deleting, setDeleting] = useState<CalendarEventDetail | null>(null);
  const openings = useRef(0);
  const wide = useMediaQuery(SIDE_BY_SIDE);
  const closeRef = useRef<HTMLButtonElement>(null);
  const todayRef = useRef<HTMLButtonElement>(null);
  // Below xl the event takes the view's place: the focus follows it there and back.
  const linkRef = useDrillDownFocus(address.openKey, {
    enabled: !wide,
    opened: closeRef,
    fallback: todayRef,
  });
  const calendarsRead = useWorkbenchCalendars();
  const calendars = calendarsRead.item?.calendars ?? NO_CALENDARS;
  const shownIds = calendars
    .filter(calendar => !hidden.has(calendar.id))
    .map(calendar => calendar.id);
  const state = useWorkbenchCalendar({
    calendarIds: shownIds,
    start: address.days[0],
    end: address.days[address.days.length - 1],
  });
  const open = address.open;
  // On a large screen the person sizes the calendars and, beside the view, the detail.
  const calendarsPane = useWorkbenchPane(lng, 'calendar.calendars');
  const detailPane = useWorkbenchPane(lng, 'calendar.detail');
  const detail = useWorkbenchItem<CalendarEventDetail>(open ? '/workbench/calendar/event' : null, {
    calendar_id: open?.calendarId,
    event_id: open?.eventId,
  });

  const compose = useCallback((target: EditorTarget) => {
    openings.current += 1;
    setEditor({ id: openings.current, target });
  }, []);
  const tell = useCallback(
    (error: unknown) => {
      const refusal = workbenchRefusal(error);
      toast.error(refusal ? t(refusal.key, refusal.values) : t('workbench.calendar.failed'));
    },
    [t]
  );
  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key !== 'Escape' || !open || event.defaultPrevented) return;
    event.preventDefault();
    address.close();
  };
  const startNew = () => {
    const calendar = defaultCalendar(calendars);
    if (!calendar) return;
    const at = startHour(address.day, today, zone);
    compose({ kind: 'new', fields: newEventFields(calendar.id, at.day, at.time) });
  };
  const writable = defaultCalendar(calendars) !== undefined;
  const newEvent = <NewEventButton lng={lng} writable={writable} onClick={startNew} />;

  return (
    <>
      <WorkbenchToolHeader lng={lng} tool="calendar">
        <span className="lg:hidden">{newEvent}</span>
      </WorkbenchToolHeader>
      <section
        aria-label={t('workbench.tools.calendar.label')}
        onKeyDown={onKeyDown}
        className={cn(
          'flex min-h-[28rem] overflow-hidden rounded-lg border bg-card',
          WORKBENCH_PANE_HEIGHT
        )}
      >
        <aside
          {...calendarsPane.pane}
          className={cn(
            'hidden shrink-0 space-y-4 overflow-y-auto border-r p-3 lg:block',
            paneWidth(calendarsPane, 'w-60')
          )}
        >
          <div className="[&>button]:w-full">{newEvent}</div>
          <MiniMonth
            key={address.day.slice(0, 7)}
            lng={lng}
            day={address.day}
            today={today}
            onPick={day => address.move({ day })}
          />
          <CalendarList lng={lng} calendars={calendars} hidden={hidden} onToggle={toggle} />
        </aside>
        <PaneSeparator
          {...calendarsPane.separator}
          className={cn(PANE_SEPARATOR_CLASS, 'hidden lg:flex')}
        />
        <div className={cn('min-w-0 flex-1 flex-col', open ? 'hidden xl:flex' : 'flex')}>
          <Toolbar
            lng={lng}
            zone={zone}
            today={today}
            todayRef={todayRef}
            address={address}
            calendars={calendars}
            hidden={hidden}
            onToggle={toggle}
          />
          <Notices lng={lng} state={state} calendars={calendars} limits={limits} />
          <ViewBody
            lng={lng}
            zone={zone}
            today={today}
            address={address}
            state={state}
            calendars={calendars}
            calendarsLoading={calendarsRead.loading}
            noneShown={calendars.length > 0 && shownIds.length === 0}
            linkRef={linkRef}
          />
        </div>
        {open && (
          <PaneSeparator
            {...detailPane.separator}
            className={cn(PANE_SEPARATOR_CLASS, 'hidden xl:flex')}
          />
        )}
        {open && (
          <div
            {...detailPane.pane}
            className={cn(
              'flex min-w-0 flex-1 border-l',
              paneWidth(detailPane, 'xl:w-96 xl:flex-none', 'xl')
            )}
          >
            <EventDetail
              lng={lng}
              event={detail.item}
              loading={detail.loading}
              error={detail.error}
              calendar={calendars.find(calendar => calendar.id === open.calendarId)}
              zone={zone}
              occurrenceEdit={tool.features.includes('occurrence_edit')}
              onClose={address.close}
              closeRef={closeRef}
              onRetry={() => void detail.refresh()}
              onEdit={() => detail.item && compose({ kind: 'edit', event: detail.item })}
              onDelete={() => detail.item && setDeleting(detail.item)}
            />
          </div>
        )}
      </section>
      <CalendarDialogs
        lng={lng}
        tool={tool}
        zone={zone}
        calendars={calendars}
        state={state}
        editor={editor}
        deleting={deleting}
        onEdited={() => void detail.refresh()}
        onDeleted={address.close}
        onCloseEditor={() => setEditor(null)}
        onCloseDelete={() => setDeleting(null)}
        tell={tell}
      />
    </>
  );
}

function NewEventButton({
  lng,
  writable,
  onClick,
}: {
  lng: Language;
  writable: boolean;
  onClick: () => void;
}) {
  const { t } = useTranslation(lng);
  return (
    <Button className="gap-1.5" onClick={onClick} aria-disabled={!writable || undefined}>
      <Plus className="h-4 w-4" aria-hidden="true" />
      {t('workbench.calendar.new_event')}
    </Button>
  );
}

interface CalendarDialogsProps {
  lng: Language;
  tool: WorkbenchToolAvailability;
  zone: string;
  calendars: readonly WorkbenchCalendar[];
  state: WorkbenchCalendarState;
  editor: { id: number; target: EditorTarget } | null;
  deleting: CalendarEventDetail | null;
  onEdited: () => void;
  onDeleted: () => void;
  onCloseEditor: () => void;
  onCloseDelete: () => void;
  tell: (error: unknown) => void;
}

/** The editor and the deletion, each mounted anew per opening. */
function CalendarDialogs({
  lng,
  tool,
  zone,
  calendars,
  state,
  editor,
  deleting,
  onEdited,
  onDeleted,
  onCloseEditor,
  onCloseDelete,
  tell,
}: CalendarDialogsProps) {
  const { t } = useTranslation(lng);
  const notifyOffered = tool.features.includes('notify_attendees');
  const remove = async (event: CalendarEventDetail, notify: boolean | undefined) => {
    try {
      await state.remove(event.calendar_id, event.id, notify);
      onCloseDelete();
      onDeleted();
      toast.success(t('workbench.calendar.deleted'));
    } catch (error: unknown) {
      tell(error);
    }
  };
  return (
    <>
      {editor && (
        <EventEditor
          key={editor.id}
          lng={lng}
          target={editor.target}
          zone={zone}
          calendars={calendars}
          conferenceOffered={tool.features.includes('conference')}
          notifyOffered={notifyOffered}
          bounds={tool.bounds}
          onCreate={async body => {
            await state.create(body);
            toast.success(t('workbench.calendar.created'));
          }}
          onUpdate={async body => {
            await state.update(body);
            onEdited();
            toast.success(t('workbench.calendar.saved'));
          }}
          onClose={onCloseEditor}
        />
      )}
      {deleting && (
        <EventDeleteDialog
          lng={lng}
          event={deleting}
          notifyOffered={notifyOffered}
          onDelete={notify => remove(deleting, notify)}
          onClose={onCloseDelete}
        />
      )}
    </>
  );
}

interface ToolbarProps {
  lng: Language;
  zone: string;
  today: string;
  todayRef: RefObject<HTMLButtonElement | null>;
  address: CalendarAddress;
  calendars: readonly WorkbenchCalendar[];
  hidden: ReadonlySet<string>;
  onToggle: (calendarId: string) => void;
}

function Toolbar({
  lng,
  zone,
  today,
  todayRef,
  address,
  calendars,
  hidden,
  onToggle,
}: ToolbarProps) {
  const { t } = useTranslation(lng);
  const first = address.days[0];
  const last = address.days[address.days.length - 1];
  const month = address.view === 'month';
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
        aria-label={t(
          month ? 'workbench.calendar.previous_month' : 'workbench.calendar.previous_week'
        )}
      >
        <ChevronLeft className="h-4 w-4" aria-hidden="true" />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        onClick={() => address.move({ day: stepDay(address.view, address.day, 1) })}
        aria-label={t(month ? 'workbench.calendar.next_month' : 'workbench.calendar.next_week')}
      >
        <ChevronRight className="h-4 w-4" aria-hidden="true" />
      </Button>
      <h2 className="text-sm font-bold" aria-live="polite">
        {month ? monthLabel(address.day, lng) : rangeLabel(first, last, lng)}
      </h2>
      <span className="text-xs text-muted-foreground">
        {t('workbench.calendar.zone_note', { zone })}
      </span>
      <span className="ml-auto flex items-center gap-2">
        <CalendarListMenu lng={lng} calendars={calendars} hidden={hidden} onToggle={onToggle} />
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

interface NoticesProps {
  lng: Language;
  state: WorkbenchCalendarState;
  calendars: readonly WorkbenchCalendar[];
  limits: WorkbenchLimits;
}

/** What the view could not show, said above it. */
function Notices({ lng, state, calendars, limits }: NoticesProps) {
  const { t } = useTranslation(lng);
  const names = new Map(calendars.map(calendar => [calendar.id, calendar.name]));
  const lines: string[] = [];
  for (const entry of state.window.item?.calendars ?? []) {
    const name = names.get(entry.calendar_id) ?? entry.calendar_id;
    if (entry.error) {
      const refusal = refusalOfCode(entry.error);
      const reason = refusal ? t(refusal.key) : t('workbench.calendar.failed');
      lines.push(t('workbench.calendar.calendar_failed', { name, reason }));
    }
    if (entry.truncated) {
      lines.push(
        t('workbench.calendar.truncated', { name, count: limits.calendar_window_max_events })
      );
    }
    if (entry.skipped > 0)
      lines.push(t('workbench.calendar.skipped', { name, count: entry.skipped }));
  }
  if (lines.length === 0) return null;
  return (
    <ul
      role="status"
      className="space-y-0.5 border-b bg-muted/40 px-4 py-2 text-xs text-muted-foreground"
    >
      {lines.map(line => (
        <li key={line}>{line}</li>
      ))}
    </ul>
  );
}

interface ViewBodyProps {
  lng: Language;
  zone: string;
  today: string;
  address: CalendarAddress;
  state: WorkbenchCalendarState;
  calendars: readonly WorkbenchCalendar[];
  calendarsLoading: boolean;
  noneShown: boolean;
  linkRef: (key: string, element: HTMLElement | null) => void;
}

function ViewBody({
  lng,
  zone,
  today,
  address,
  state,
  calendars,
  calendarsLoading,
  noneShown,
  linkRef,
}: ViewBodyProps) {
  const { t } = useTranslation(lng);
  const { window } = state;
  if (noneShown)
    return <EmptyState className="flex-1" description={t('workbench.calendar.no_calendar')} />;
  if (calendarsLoading || window.loading) {
    return (
      <div className="space-y-3 p-4" aria-busy="true">
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }
  if (window.error) {
    const refusal = workbenchRefusal(window.error);
    return (
      <EmptyState
        className="flex-1"
        description={refusal ? t(refusal.key, refusal.values) : t('workbench.calendar.failed')}
        action={{ label: t('workbench.states.retry'), onClick: () => void window.refresh() }}
      />
    );
  }
  const events = shownEvents(window.item, calendars);
  const common = {
    lng,
    days: address.days,
    today,
    zone,
    events,
    openId: address.openKey,
    hrefOf: address.eventHref,
    linkRef,
  };
  if (address.view === 'month') {
    return (
      <MonthView {...common} month={address.day.slice(0, 7)} agendaHref={address.agendaHref} />
    );
  }
  return address.view === 'week' ? (
    <WeekView {...common} agendaHref={address.agendaHref} />
  ) : (
    <AgendaView {...common} focusDay={address.day} />
  );
}
