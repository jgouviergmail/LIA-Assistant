'use client';

/**
 * EventDetail — one event, whole (ADR-369, mock-up « Agenda », right panel).
 *
 * Its calendar (the calendar's own colour, data), its title, when — days for an
 * all-day event, the last one INCLUDED as a person reads it; hours on the
 * account's wall otherwise, and on the clock it was set on when that is another
 * —, where, its video call, who is invited and what
 * each answered (the response's colour and icon both say it: colour is never
 * the only carrier), its notes. Changing and deleting are offered where the
 * calendar can be written and, for an occurrence of a series, where the
 * provider changes one occurrence alone; a copy wherever some calendar can be
 * written, since it touches nothing of the original. An event the person is invited
 * to asks for their answer, the current one stated, and says the organiser is told.
 */
import {
  Bell,
  CalendarArrowUp,
  CalendarOff,
  CircleCheck,
  CircleHelp,
  CircleX,
  Clock,
  Copy,
  Globe,
  Lock,
  MapPin,
  Pencil,
  Repeat,
  Sparkles,
  Trash2,
  Video,
} from 'lucide-react';
import type { ReactNode, Ref } from 'react';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { EmptyState } from '@/components/ui/empty-state';
import { LinkedText } from '@/components/ui/linked-text';
import { Skeleton } from '@/components/ui/skeleton';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import { workbenchRefusal } from '@/lib/workbench/errors';
import type {
  AttendeeResponse,
  CalendarEventDetail,
  EventAnswer,
  WorkbenchCalendar,
} from '@/lib/workbench/types';

import { DetailClose } from '../DetailClose';
import { CalendarSwatch } from './EventChip';

import { callHref } from '@/lib/workbench/calendar/events';
import { eventWhen, reminderLabel } from '@/lib/workbench/calendar/format';
import { readableZone } from '@/lib/workbench/calendar/zoned';

/** Each answer's icon and colour (statuses are data: their colours are fixed). */
const RESPONSES: Readonly<Record<AttendeeResponse, { icon: typeof CircleCheck; tone: string }>> = {
  accepted: { icon: CircleCheck, tone: 'text-emerald-600 dark:text-emerald-400' },
  declined: { icon: CircleX, tone: 'text-red-600 dark:text-red-400' },
  tentative: { icon: CircleHelp, tone: 'text-amber-600 dark:text-amber-400' },
  needsAction: { icon: Clock, tone: 'text-muted-foreground' },
};

export interface EventDetailProps {
  lng: Language;
  event: CalendarEventDetail | undefined;
  loading: boolean;
  error: unknown;
  calendar: WorkbenchCalendar | undefined;
  zone: string;
  /** The provider changes one occurrence of a series alone. */
  occurrenceEdit: boolean;
  onClose: () => void;
  onRetry: () => void;
  onEdit: () => void;
  /** Opens the editor on the whole series. */
  onEditSeries: () => void;
  onDelete: () => void;
  /** Opens a copy; left out where no calendar can be written. */
  onDuplicate?: () => void;
  /** Takes the event to LIA. */
  onAsk: () => void;
  /** Answers the invitation; absent where nothing can be answered. */
  onAnswer?: (response: EventAnswer) => void;
  /** The calendars it can go to; none, and no move is offered. */
  destinations?: readonly WorkbenchCalendar[];
  onMove?: (destination: WorkbenchCalendar) => void;
  /** The answer on its way. */
  answering?: EventAnswer | null;
  /** The close button, focused when the detail takes the view's place. */
  closeRef?: Ref<HTMLButtonElement>;
}

export function EventDetail(props: EventDetailProps) {
  const { lng, event, loading, error, onClose, onRetry, closeRef } = props;
  const { t } = useTranslation(lng);
  let content: ReactNode;
  if (event) content = <DetailBody {...props} event={event} />;
  else if (loading) content = <DetailSkeleton />;
  else {
    const refusal = workbenchRefusal(error);
    content = (
      <EmptyState
        description={
          refusal ? t(refusal.key, refusal.values) : t('workbench.calendar.event_failed')
        }
        action={{ label: t('workbench.states.retry'), onClick: onRetry }}
      />
    );
  }
  return (
    <article
      aria-label={event?.summary || t('workbench.calendar.event_title')}
      className="flex min-h-0 min-w-0 flex-1 flex-col"
    >
      <div className="flex items-center border-b px-2 py-1.5">
        <DetailClose
          closeLabel={t('workbench.calendar.close_event')}
          backLabel={t('workbench.tools.calendar.label')}
          onClose={onClose}
          buttonRef={closeRef}
        />
      </div>
      {content}
    </article>
  );
}

function DetailBody(props: EventDetailProps & { event: CalendarEventDetail }) {
  const { lng, event, calendar, occurrenceEdit } = props;
  const writable = calendar?.writable ?? false;
  const changeable = writable && (!event.recurring || occurrenceEdit);
  return (
    <>
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
        <DetailFacts {...props} />
        <InvitationAnswers {...props} />
        <DetailLinks lng={lng} event={event} occurrenceEdit={occurrenceEdit} />
        <Attendees lng={lng} event={event} />
        <DetailNotes lng={lng} event={event} />
      </div>
      <DetailActions {...props} changeable={changeable} writable={writable} />
    </>
  );
}

/** When it is on the clock it was set on, where that is not the account's. */
function OwnZoneLine({
  lng,
  event,
  zone,
}: Pick<EventDetailProps, 'lng' | 'zone'> & { event: CalendarEventDetail }) {
  const { t } = useTranslation(lng);
  const own = readableZone(event.zone);
  if (own === null || own === zone) return null;
  return (
    <li className="flex items-start gap-2">
      <Globe className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
      <span>
        {t('workbench.calendar.in_its_zone', {
          zone: own.replaceAll('_', ' '),
          when: eventWhen(event, own, lng, t('workbench.calendar.all_day')),
        })}
      </span>
    </li>
  );
}

/** Its calendar, its title, when and where. */
function DetailFacts({
  lng,
  event,
  calendar,
  zone,
}: EventDetailProps & { event: CalendarEventDetail }) {
  const { t } = useTranslation(lng);
  return (
    <>
      {calendar && (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <CalendarSwatch color={calendar.color} className="h-2.5 w-2.5" />
          {calendar.name}
        </p>
      )}
      <h2 className="text-lg font-bold leading-snug">
        {event.summary || t('workbench.calendar.no_title')}
      </h2>
      <ul className="space-y-1.5 text-sm">
        <li className="flex items-start gap-2">
          <Clock className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
          <span>{eventWhen(event, zone, lng, t('workbench.calendar.all_day'))}</span>
        </li>
        <OwnZoneLine lng={lng} event={event} zone={zone} />
        {event.location && (
          <li className="flex items-start gap-2">
            <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
            <span className="break-words">
              <LinkedText text={event.location} />
            </span>
          </li>
        )}
        {event.reminder_minutes !== null && (
          <li className="flex items-start gap-2">
            <Bell className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
            <span>{reminderLabel(event.reminder_minutes, t)}</span>
          </li>
        )}
        {!event.busy && (
          <li className="flex items-start gap-2">
            <CalendarOff className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
            <span>{t('workbench.calendar.shows_free')}</span>
          </li>
        )}
        {event.private && (
          <li className="flex items-start gap-2">
            <Lock className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
            <span>{t('workbench.calendar.is_private')}</span>
          </li>
        )}
      </ul>
    </>
  );
}

/** What a series means here, its video call and its page at the provider. */
function DetailLinks({
  lng,
  event,
  occurrenceEdit,
}: {
  lng: Language;
  event: CalendarEventDetail;
  occurrenceEdit: boolean;
}) {
  const { t } = useTranslation(lng);
  const series = occurrenceEdit
    ? 'workbench.calendar.recurring_note'
    : 'workbench.calendar.recurring_locked';
  const call = callHref(event.conference_url);
  return (
    <>
      {event.recurring && <p className="text-xs text-muted-foreground">{t(series)}</p>}
      {call && (
        <Button asChild variant="outline" size="sm" className="gap-2">
          <a href={call} target="_blank" rel="noopener noreferrer">
            <Video className="h-4 w-4" aria-hidden="true" />
            {t('workbench.calendar.join_call')}
          </a>
        </Button>
      )}
      {event.link && (
        <a
          href={event.link}
          target="_blank"
          rel="noopener noreferrer"
          className="block text-sm text-primary underline-offset-4 hover:underline"
        >
          {t('workbench.calendar.open_at_provider')}
        </a>
      )}
    </>
  );
}

function DetailNotes({ lng, event }: { lng: Language; event: CalendarEventDetail }) {
  const { t } = useTranslation(lng);
  if (!event.description) return null;
  return (
    <section className="space-y-1">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {t('workbench.calendar.description')}
      </h3>
      <p className="whitespace-pre-wrap break-words text-sm">
        <LinkedText text={event.description} />
      </p>
    </section>
  );
}

/** The calendars the event can go to: none, and there is nothing to offer. */
function MoveMenu({
  lng,
  destinations,
  onMove,
}: Pick<EventDetailProps, 'lng' | 'destinations' | 'onMove'>) {
  const { t } = useTranslation(lng);
  if (!onMove || !destinations || destinations.length === 0) return null;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="gap-1.5">
          <CalendarArrowUp className="h-4 w-4" aria-hidden="true" />
          {t('workbench.calendar.move_to')}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {destinations.map(calendar => (
          <DropdownMenuItem key={calendar.id} onSelect={() => onMove(calendar)}>
            {calendar.name}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function DetailActions({
  lng,
  changeable,
  writable,
  event,
  onEdit,
  onEditSeries,
  onDelete,
  onDuplicate,
  onAsk,
  destinations,
  onMove,
}: EventDetailProps & { changeable: boolean; writable: boolean; event: CalendarEventDetail }) {
  const { t } = useTranslation(lng);
  return (
    <div className="flex flex-wrap justify-end gap-2 border-t p-3">
      <Button variant="outline" size="sm" className="gap-1.5" onClick={onAsk}>
        <Sparkles className="h-4 w-4" aria-hidden="true" />
        {t('workbench.ask.label')}
      </Button>
      {onDuplicate && (
        <Button variant="outline" size="sm" className="gap-1.5" onClick={onDuplicate}>
          <Copy className="h-4 w-4" aria-hidden="true" />
          {t('workbench.calendar.duplicate')}
        </Button>
      )}
      <MoveMenu lng={lng} destinations={destinations} onMove={onMove} />
      {changeable && (
        <Button variant="outline" size="sm" className="gap-1.5" onClick={onEdit}>
          <Pencil className="h-4 w-4" aria-hidden="true" />
          {t('workbench.calendar.edit')}
        </Button>
      )}
      {writable && event.recurring && (
        <Button variant="outline" size="sm" className="gap-1.5" onClick={onEditSeries}>
          <Repeat className="h-4 w-4" aria-hidden="true" />
          {t('workbench.calendar.edit_series')}
        </Button>
      )}
      {writable && (
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5 text-destructive hover:text-destructive"
          onClick={onDelete}
        >
          <Trash2 className="h-4 w-4" aria-hidden="true" />
          {t('workbench.calendar.delete')}
        </Button>
      )}
    </div>
  );
}

/** The person's answer, the current one stated; the organiser is told of a change. */
function InvitationAnswers({
  lng,
  event,
  onAnswer,
  answering = null,
}: Pick<EventDetailProps, 'lng' | 'onAnswer' | 'answering'> & { event: CalendarEventDetail }) {
  const { t } = useTranslation(lng);
  if (!onAnswer || event.my_response === null) return null;
  const answers: { value: EventAnswer; key: string; icon: typeof CircleCheck }[] = [
    { value: 'accepted', key: 'workbench.calendar.answer_accept', icon: CircleCheck },
    { value: 'tentative', key: 'workbench.calendar.answer_tentative', icon: CircleHelp },
    { value: 'declined', key: 'workbench.calendar.answer_decline', icon: CircleX },
  ];
  return (
    <section aria-label={t('workbench.calendar.answer_title')} className="space-y-1.5">
      <p className="text-sm font-medium text-foreground">{t('workbench.calendar.answer_title')}</p>
      <div className="flex flex-wrap gap-1.5">
        {answers.map(({ value, key, icon: Icon }) => (
          <Button
            key={value}
            size="sm"
            variant={event.my_response === value ? 'default' : 'outline'}
            aria-pressed={event.my_response === value}
            aria-disabled={answering !== null || undefined}
            isLoading={answering === value}
            className="gap-1.5"
            onClick={() => {
              if (answering === null && event.my_response !== value) onAnswer(value);
            }}
          >
            <Icon className="h-4 w-4" aria-hidden="true" />
            {t(key)}
          </Button>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">{t('workbench.calendar.answer_note')}</p>
    </section>
  );
}

function Attendees({ lng, event }: { lng: Language; event: CalendarEventDetail }) {
  const { t } = useTranslation(lng);
  if (event.attendees.length === 0) return null;
  return (
    <section className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {t('workbench.calendar.participants', { count: event.attendees.length })}
      </h3>
      <ul className="space-y-2">
        {event.attendees.map(attendee => {
          const { icon: Icon, tone } = RESPONSES[attendee.response];
          const organizer = attendee.email === event.organizer;
          return (
            <li key={attendee.email} className="flex items-start gap-2.5 text-sm">
              <Icon className={cn('mt-0.5 h-4 w-4 shrink-0', tone)} aria-hidden="true" />
              <span className="min-w-0">
                <span className="block truncate">{attendee.name || attendee.email}</span>
                <span className="block text-xs text-muted-foreground">
                  {organizer
                    ? t('workbench.calendar.organizer')
                    : t(`workbench.calendar.responses.${attendee.response}`)}
                </span>
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function DetailSkeleton() {
  return (
    <div className="space-y-3 p-4" aria-busy="true">
      <Skeleton className="h-6 w-2/3" />
      <Skeleton className="h-4 w-1/2" />
      <Skeleton className="h-24 w-full" />
    </div>
  );
}
