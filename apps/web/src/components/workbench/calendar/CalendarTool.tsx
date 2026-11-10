'use client';

/**
 * CalendarTool — the « Tools » calendar screen (ADR-369, spec §6.3, mock-up
 * « Agenda »).
 *
 * The account's calendars, those this device hides left out; the week holding
 * the day the address names, as an agenda or as a grid, on the account's wall;
 * the open event beside it from `xl`, in its place below.
 * A calendar that could not be read, one cut at the published bound, or events
 * whose times could not be read are SAID above the view — never an empty week
 * that looks quiet. Creating, changing and deleting are offered where the
 * calendar can be written; a video call and « tell the guests » where the
 * provider has them (the descriptor). A click on an empty slot starts an event
 * there, and from `lg` an event is dragged or stretched in the grid
 * (`useEventDrop`); a phone reads the month as dots above the picked day.
 */
import { Plus } from '@/lib/icons';
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
  useCalendarManagement,
  useDueTasks,
  useOpenEvent,
  useWorkbenchCalendar,
  useWorkbenchCalendars,
  type WorkbenchCalendarState,
} from '@/hooks/useWorkbenchCalendar';
import type { WorkbenchItemState } from '@/hooks/useWorkbenchItem';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import {
  DUE_TASKS_LAYER,
  shownEvents,
  shownTasks,
  type ShownEvent,
} from '@/lib/workbench/calendar/events';
import { eventWhen } from '@/lib/workbench/calendar/format';
import { CALENDAR_VIEWS } from '@/lib/workbench/calendar/preferences';
import { refusalOfCode, workbenchRefusal } from '@/lib/workbench/errors';
import { dayIn } from '@/lib/workbench/tasks';
import {
  WORKBENCH_BEYOND_PHONE,
  WORKBENCH_DESKTOP,
  WORKBENCH_HEADER_PRIMARY,
  WORKBENCH_PANE_HEIGHT,
  WORKBENCH_SIDE_BY_SIDE,
} from '@/lib/workbench/tools';
import type {
  CalendarEventDetail,
  DueTasks,
  WorkbenchCalendar,
  WorkbenchLimits,
  WorkbenchToolAvailability,
} from '@/lib/workbench/types';

import { useWorkbench } from '../WorkbenchShell';
import { WorkbenchToolHeader } from '../WorkbenchToolHeader';
import { WorkbenchUnavailable, unavailableKind } from '../WorkbenchUnavailable';
import { useEventAssist } from '../assist/useEventAssist';
import { useHandoff } from '@/hooks/useHandoff';
import { useToolBridges } from '../useToolBridges';
import type { ToolShortcut } from '../useToolShortcuts';
import { PANE_SEPARATOR_CLASS, paneWidth, useWorkbenchPane } from '../useWorkbenchPane';
import { LabelsManager } from '../mail/LabelsManager';
import { AgendaView } from './AgendaView';
import type { EventDrag } from './CalendarDrag';
import { CalendarList } from './CalendarList';
import { SearchOrView, useCalendarSearch } from './CalendarSearch';
import { CalendarToolbar } from './CalendarToolbar';
import { CalendarTarget } from './CalendarTarget';
import { EventDeleteDialog } from './EventDeleteDialog';
import { EventDetail } from './EventDetail';
import { EventEditor, type EditorTarget } from './EventEditor';
import { MiniMonth } from './MiniMonth';
import { MonthCompact } from './MonthCompact';
import { MonthView } from './MonthView';
import {
  stepDay,
  useCalendarAddress,
  useOwnCalendarAlias,
  useHiddenCalendars,
  calendarSelection,
  type CalendarAddress,
} from './useCalendarScreen';
import { useEventDrop, type MovedEvent } from './useEventDrop';
import { useEventAnswer, type EventAnswering } from './useEventAnswer';
import { useEventMove, type EventMoving } from './useEventMove';
import { eventStarts, type EventStarts } from './useEventStarts';
import { WeekView } from './WeekView';

const NO_CALENDARS: readonly WorkbenchCalendar[] = [];

export function CalendarTool({ lng }: { lng: Language }) {
  const { availability } = useWorkbench();
  const tool = availability.tools.find(item => item.tool === 'calendar');
  const tasksReady = availability.tools.some(
    item => item.tool === 'tasks' && item.state === 'ready'
  );
  if (tool?.state !== 'ready') {
    return (
      <>
        <WorkbenchToolHeader lng={lng} tool="calendar" />
        <WorkbenchUnavailable lng={lng} kind={unavailableKind(tool)} tool="calendar" />
      </>
    );
  }
  return (
    <ReadyCalendar lng={lng} tool={tool} limits={availability.limits} tasksReady={tasksReady} />
  );
}

interface ReadyCalendarProps {
  lng: Language;
  tool: WorkbenchToolAvailability;
  limits: WorkbenchLimits;
  /** Whether the account has tasks a calendar can draw. */
  tasksReady: boolean;
}

function ReadyCalendar({ lng, tool, limits, tasksReady }: ReadyCalendarProps) {
  const { t } = useTranslation(lng);
  const { user } = useAuth();
  const zone = user?.timezone ?? 'UTC';
  const today = dayIn(zone, new Date());
  const desktop = useMediaQuery(WORKBENCH_DESKTOP);
  const address = useCalendarAddress(lng, today, desktop ? 'week' : 'agenda');
  const preferences = useHiddenCalendars(user?.id ?? '');
  const [editor, setEditor] = useState<{ id: number; target: EditorTarget } | null>(null);
  const [deleting, setDeleting] = useState<CalendarEventDetail | null>(null);
  const wide = useMediaQuery(WORKBENCH_SIDE_BY_SIDE);
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
  const { hidden, toggle, target } = calendarSelection(address, calendars, preferences);
  useOwnCalendarAlias(address, calendars);
  const shownIds = calendars
    .filter(calendar => !hidden.has(calendar.id))
    .map(calendar => calendar.id);
  const state = useWorkbenchCalendar({
    calendarIds: shownIds,
    start: address.days[0],
    end: address.days[address.days.length - 1],
  });
  const due = useDueTasks(
    address.days[0],
    address.days[address.days.length - 1],
    tasksReady && !hidden.has(DUE_TASKS_LAYER)
  );
  const listed = withDueTasks(calendars, tasksReady, t('workbench.calendar.due_tasks_layer'));
  const open = address.open;
  const searching = useCalendarSearch(shownIds);
  // On a large screen the person sizes the calendars and, beside the view, the detail.
  const calendarsPane = useWorkbenchPane(lng, 'calendar.calendars');
  const detailPane = useWorkbenchPane(lng, 'calendar.detail');
  const detail = useOpenEvent(open);

  // Each opening mounts a new editor, hence a new key.
  const compose = useCallback((target: EditorTarget) => {
    setEditor(previous => ({ id: (previous?.id ?? 0) + 1, target }));
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
  const starts = eventStarts(calendars, today, zone, compose);
  const { ask } = useToolBridges(lng);
  const answering = useEventAnswer(
    state,
    detail,
    t('workbench.calendar.answered'),
    address.close,
    tell
  );
  const moving = useEventMove(
    state,
    name => t('workbench.calendar.moved_to', { name }),
    address.close,
    tell
  );
  const [managing, setManaging] = useState(false);
  const manage = managingOffered(tool) ? () => setManaging(true) : undefined;
  useHandoff(
    'event',
    starts.writable,
    handed => starts.startWith(handed.summary, handed.description, handed.proposal),
    editor !== null
  );
  const newEvent = (
    <NewEventButton
      lng={lng}
      writable={starts.writable}
      onClick={() => starts.startOn(address.day)}
    />
  );
  const dropping = useEventDrop({
    lng,
    zone,
    state,
    edit: compose,
    onChanged: () => void detail.refresh(),
    tell,
  });
  const drag: EventDrag = {
    allows: event => draggable(event, calendars, tool),
    onDrop: (event, drop) => void dropping.drop(event, drop),
  };

  return (
    <>
      <WorkbenchToolHeader
        lng={lng}
        tool="calendar"
        shortcuts={calendarShortcuts(address, today, starts)}
        onRefresh={async options => {
          await Promise.all([
            calendarsRead.refresh(options),
            state.window.refresh(options),
            detail.refresh(options),
            due.refresh(options),
          ]);
        }}
      >
        <span className={cn(WORKBENCH_HEADER_PRIMARY, 'lg:hidden [&>button]:min-h-10')}>
          {newEvent}
        </span>
      </WorkbenchToolHeader>
      <CalendarTarget
        lng={lng}
        requested={address.selectedCalendarId}
        target={target}
        loading={calendarsRead.loading}
        failed={Boolean(calendarsRead.error)}
      />
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
          <CalendarList
            lng={lng}
            calendars={listed}
            hidden={hidden}
            onToggle={toggle}
            onManage={manage}
          />
        </aside>
        <PaneSeparator
          {...calendarsPane.separator}
          className={cn(PANE_SEPARATOR_CLASS, 'hidden lg:flex')}
        />
        <div className={cn('min-w-0 flex-1 flex-col', open ? 'hidden xl:flex' : 'flex')}>
          <CalendarToolbar
            lng={lng}
            today={today}
            todayRef={todayRef}
            address={address}
            calendars={listed}
            hidden={hidden}
            onToggle={toggle}
            onManage={manage}
            searching={searching}
          />
          <SearchOrView
            lng={lng}
            zone={zone}
            searching={searching}
            hrefOf={address.eventHref}
            linkRef={linkRef}
          >
            <Notices lng={lng} state={state} calendars={calendars} limits={limits} due={due} />
            <ViewBody
              lng={lng}
              zone={zone}
              today={today}
              address={address}
              state={state}
              calendars={calendars}
              calendarsLoading={calendarsRead.loading}
              noneShown={calendars.length > 0 && shownIds.length === 0}
              due={due.item}
              linkRef={linkRef}
              starts={starts}
              drag={desktop ? drag : undefined}
              moved={dropping.moved}
            />
          </SearchOrView>
        </div>
        {open && (
          <OpenEventPane
            lng={lng}
            tool={tool}
            zone={zone}
            pane={detailPane}
            detail={detail}
            calendar={calendars.find(calendar => calendar.id === open.calendarId)}
            calendars={calendars}
            moving={moving}
            closeRef={closeRef}
            onClose={address.close}
            onEdit={event => compose({ kind: 'edit', event })}
            onEditSeries={event => compose({ kind: 'edit', event, series: true })}
            onDelete={setDeleting}
            onDuplicate={starts.onDuplicate}
            answering={answering}
            onAsk={event =>
              ask(
                t('workbench.ask.event', {
                  title: event.summary,
                  when: eventWhen(event, zone, lng, t('workbench.calendar.all_day')),
                })
              )
            }
          />
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
      <CalendarsManagement
        lng={lng}
        tool={tool}
        calendars={calendars}
        open={managing}
        onOpenChange={setManaging}
        reread={async () => {
          // The open event's calendar may be the one just deleted.
          await Promise.all([calendarsRead.refresh(), state.window.refresh(), detail.refresh()]);
        }}
        tell={tell}
      />
    </>
  );
}

function managingOffered(tool: WorkbenchToolAvailability): boolean {
  return tool.features.includes('calendar_management');
}

interface CalendarsManagementProps {
  lng: Language;
  tool: WorkbenchToolAvailability;
  calendars: readonly WorkbenchCalendar[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  reread: () => Promise<void>;
  tell: (error: unknown) => void;
}

/** The person's own calendars: a refusal is said, and the field keeps what was typed. */
function CalendarsManagement({
  lng,
  tool,
  calendars,
  open,
  onOpenChange,
  reread,
  tell,
}: CalendarsManagementProps) {
  const managed = useCalendarManagement(reread);
  const said =
    <T extends unknown[]>(act: (...args: T) => Promise<void>) =>
    async (...args: T) => {
      try {
        await act(...args);
      } catch (error: unknown) {
        tell(error);
        throw error;
      }
    };
  return (
    <LabelsManager
      kind="calendars"
      lng={lng}
      open={open}
      onOpenChange={onOpenChange}
      labels={calendars.filter(calendar => calendar.manageable)}
      maxLength={tool.bounds.calendar_name_max_chars}
      onCreate={said(managed.create)}
      onRename={said(managed.rename)}
      onDelete={said(managed.remove)}
    />
  );
}

interface OpenEventPaneProps {
  lng: Language;
  tool: WorkbenchToolAvailability;
  zone: string;
  pane: ReturnType<typeof useWorkbenchPane>;
  detail: WorkbenchItemState<CalendarEventDetail>;
  calendar: WorkbenchCalendar | undefined;
  calendars: readonly WorkbenchCalendar[];
  moving: EventMoving;
  closeRef: RefObject<HTMLButtonElement | null>;
  onClose: () => void;
  onEdit: (event: CalendarEventDetail) => void;
  onEditSeries: (event: CalendarEventDetail) => void;
  onDelete: (event: CalendarEventDetail) => void;
  onDuplicate: EventStarts['onDuplicate'];
  answering: EventAnswering;
  onAsk: (event: CalendarEventDetail) => void;
}

/** The open event: beside the view from `xl`, in its place below. */
function OpenEventPane({
  lng,
  tool,
  zone,
  pane,
  detail,
  calendar,
  calendars,
  moving,
  closeRef,
  onClose,
  onEdit,
  onEditSeries,
  onDelete,
  onDuplicate,
  answering,
  onAsk,
}: OpenEventPaneProps) {
  const { item } = detail;
  const assist = useEventAssist(lng, item, zone);
  return (
    <>
      <PaneSeparator {...pane.separator} className={cn(PANE_SEPARATOR_CLASS, 'hidden xl:flex')} />
      <div
        {...pane.pane}
        className={cn(
          'flex min-w-0 flex-1 border-l',
          paneWidth(pane, 'xl:w-96 xl:flex-none', 'xl')
        )}
      >
        <EventDetail
          lng={lng}
          event={item}
          loading={detail.loading}
          error={detail.error}
          calendar={calendar}
          zone={zone}
          occurrenceEdit={tool.features.includes('occurrence_edit')}
          onClose={onClose}
          closeRef={closeRef}
          onRetry={() => void detail.refresh()}
          onEdit={() => item && onEdit(item)}
          onEditSeries={() => item && onEditSeries(item)}
          onDelete={() => item && onDelete(item)}
          onDuplicate={onDuplicate && (() => item && onDuplicate(item))}
          onAsk={() => item && onAsk(item)}
          assist={assist}
          onAnswer={response => item && void answering.answer(item, response)}
          answering={answering.answering}
          destinations={item ? moveTargets(item, calendar, calendars, tool) : undefined}
          onMove={destination => item && void moving.move(item, destination)}
        />
      </div>
    </>
  );
}

/** The keys of the calendar: a new event, moving the view, changing it. */
function calendarShortcuts(
  address: CalendarAddress,
  today: string,
  starts: EventStarts
): ToolShortcut[] {
  const step = (steps: number) => () =>
    address.move({ day: stepDay(address.view, address.day, steps) });
  return [
    {
      key: 'n',
      labelKey: 'workbench.shortcuts.new_event',
      run: () => starts.startOn(address.day),
    },
    { key: 't', labelKey: 'workbench.shortcuts.today', run: () => address.move({ day: today }) },
    { key: 'j', labelKey: 'workbench.shortcuts.later', run: step(1) },
    { key: 'k', labelKey: 'workbench.shortcuts.earlier', run: step(-1) },
    ...CALENDAR_VIEWS.map(view => ({
      key: view[0],
      labelKey: `workbench.calendar.views.${view}`,
      run: () => address.move({ view }),
    })),
  ];
}

/**
 * The calendars an event can go to. An invitation is its organiser's; a series moves
 * nowhere on a provider that copies, and neither do guests, who would hear of it twice.
 */
function moveTargets(
  event: CalendarEventDetail,
  source: WorkbenchCalendar | undefined,
  calendars: readonly WorkbenchCalendar[],
  { features }: WorkbenchToolAvailability
): readonly WorkbenchCalendar[] {
  const guests = event.attendees.length === 0 || features.includes('event_move_with_guests');
  const movable =
    features.includes('event_move') &&
    (source?.writable ?? false) &&
    !event.recurring &&
    event.my_response === null &&
    guests;
  return movable
    ? calendars.filter(calendar => calendar.writable && calendar.id !== event.calendar_id)
    : [];
}

/** An event the page may change where it stands: a timed one, in a calendar it can write. */
function draggable(
  event: ShownEvent,
  calendars: readonly WorkbenchCalendar[],
  tool: WorkbenchToolAvailability
): boolean {
  const calendar = calendars.find(item => item.id === event.calendar_id);
  const series = !event.recurring || tool.features.includes('occurrence_edit');
  return !event.all_day && (calendar?.writable ?? false) && series;
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
    <Button
      className="justify-start gap-1.5"
      onClick={onClick}
      aria-disabled={!writable || undefined}
    >
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
  const remove = async (
    event: CalendarEventDetail,
    notify: boolean | undefined,
    series: boolean
  ) => {
    try {
      await state.remove(event.calendar_id, event.id, notify, series);
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
          occurrenceEdit={tool.features.includes('occurrence_edit')}
          onDelete={(notify, series) => remove(deleting, notify, series)}
          onClose={onCloseDelete}
        />
      )}
    </>
  );
}

interface NoticesProps {
  lng: Language;
  state: WorkbenchCalendarState;
  calendars: readonly WorkbenchCalendar[];
  limits: WorkbenchLimits;
  due: WorkbenchItemState<DueTasks>;
}

/** The list of calendars: the tasks' line beside them, shown and hidden the same way. */
function withDueTasks(
  calendars: readonly WorkbenchCalendar[],
  tasksReady: boolean,
  name: string
): readonly WorkbenchCalendar[] {
  if (!tasksReady) return calendars;
  const tasks = {
    id: DUE_TASKS_LAYER,
    name,
    color: null,
    primary: false,
    default: false,
    writable: false,
    manageable: false,
  };
  return [...calendars, tasks];
}

/** What could not be said of the tasks, in the notices' words. */
function dueTaskNotices(
  due: WorkbenchItemState<DueTasks>,
  t: (key: string) => string
): readonly string[] {
  const failed = due.error !== null || (due.item?.failed.length ?? 0) > 0;
  return [
    ...(failed ? [t('workbench.calendar.due_tasks_failed')] : []),
    ...(due.item?.truncated ? [t('workbench.calendar.due_tasks_truncated')] : []),
  ];
}

/** What the view could not show, said above it. */
function Notices({ lng, state, calendars, limits, due }: NoticesProps) {
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
  lines.push(...dueTaskNotices(due, t));
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
  /** The tasks read for the days shown. */
  due: DueTasks | undefined;
  lng: Language;
  zone: string;
  today: string;
  address: CalendarAddress;
  state: WorkbenchCalendarState;
  calendars: readonly WorkbenchCalendar[];
  calendarsLoading: boolean;
  noneShown: boolean;
  linkRef: (key: string, element: HTMLElement | null) => void;
  starts: EventStarts;
  drag?: EventDrag;
  /** An event drawn where it was dropped, the provider not having answered. */
  moved: MovedEvent | null;
}

function ViewBody({
  due,
  lng,
  zone,
  today,
  address,
  state,
  calendars,
  calendarsLoading,
  noneShown,
  linkRef,
  starts,
  drag,
  moved,
}: ViewBodyProps) {
  const { t } = useTranslation(lng);
  const beyondPhone = useMediaQuery(WORKBENCH_BEYOND_PHONE);
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
  const tasks = shownTasks(due, title => t('workbench.calendar.due_task', { title }), lng);
  const events = [...shownEvents(window.item, calendars), ...tasks].map(event =>
    event.key === moved?.key ? { ...event, start: moved.start, end: moved.end } : event
  );
  const common = {
    lng,
    days: address.days,
    today,
    zone,
    events,
    openId: address.openKey,
    hrefOf: (event: ShownEvent) => event.href ?? address.eventHref(event),
    linkRef,
  };
  if (address.view === 'month') {
    const month = address.day.slice(0, 7);
    return beyondPhone ? (
      <MonthView {...common} month={month} agendaHref={address.agendaHref} onDay={starts.onDay} />
    ) : (
      <MonthCompact
        {...common}
        month={month}
        day={address.day}
        onPick={day => address.move({ day })}
      />
    );
  }
  return address.view === 'agenda' ? (
    <AgendaView {...common} focusDay={address.day} />
  ) : (
    <WeekView
      {...common}
      days={address.days}
      agendaHref={address.agendaHref}
      onSlot={starts.onSlot}
      drag={drag}
    />
  );
}
