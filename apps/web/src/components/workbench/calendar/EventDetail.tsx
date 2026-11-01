'use client';

/**
 * EventDetail — one event, whole (ADR-369, mock-up « Agenda », right panel).
 *
 * Its calendar (the calendar's own colour, data), its title, when — days for an
 * all-day event, the last one INCLUDED as a person reads it; hours on the
 * account's wall otherwise —, where, its video call, who is invited and what
 * each answered (the response's colour and icon both say it: colour is never
 * the only carrier), its notes. Changing and deleting are offered where the
 * calendar can be written and, for an occurrence of a series, where the
 * provider changes one occurrence alone.
 */
import {
  CircleCheck,
  CircleHelp,
  CircleX,
  Clock,
  MapPin,
  Pencil,
  Trash2,
  Video,
  X,
} from 'lucide-react';
import type { ReactNode, Ref } from 'react';

import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import { workbenchRefusal } from '@/lib/workbench/errors';
import type {
  AttendeeResponse,
  CalendarEventDetail,
  WorkbenchCalendar,
} from '@/lib/workbench/types';

import { CalendarSwatch } from './EventChip';

import { eventWhen } from '@/lib/workbench/calendar/format';

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
  onDelete: () => void;
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
      <div className="flex items-center justify-end border-b px-2 py-1.5">
        <Button
          ref={closeRef}
          variant="ghost"
          size="icon"
          onClick={onClose}
          aria-label={t('workbench.calendar.close_event')}
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
      {content}
    </article>
  );
}

function DetailBody(props: EventDetailProps & { event: CalendarEventDetail }) {
  const { lng, event, calendar, occurrenceEdit } = props;
  const changeable = (calendar?.writable ?? false) && (!event.recurring || occurrenceEdit);
  return (
    <>
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
        <DetailFacts {...props} />
        <DetailLinks lng={lng} event={event} occurrenceEdit={occurrenceEdit} />
        <Attendees lng={lng} event={event} />
        <DetailNotes lng={lng} event={event} />
      </div>
      {changeable && <DetailActions {...props} />}
    </>
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
        {event.location && (
          <li className="flex items-start gap-2">
            <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
            <span className="break-words">{event.location}</span>
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
  return (
    <>
      {event.recurring && <p className="text-xs text-muted-foreground">{t(series)}</p>}
      {event.conference_url && (
        <Button asChild variant="outline" size="sm" className="gap-2">
          <a href={event.conference_url} target="_blank" rel="noopener noreferrer">
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
      <p className="whitespace-pre-wrap break-words text-sm">{event.description}</p>
    </section>
  );
}

function DetailActions({ lng, onEdit, onDelete }: EventDetailProps) {
  const { t } = useTranslation(lng);
  return (
    <div className="flex justify-end gap-2 border-t p-3">
      <Button variant="outline" size="sm" className="gap-1.5" onClick={onEdit}>
        <Pencil className="h-4 w-4" aria-hidden="true" />
        {t('workbench.calendar.edit')}
      </Button>
      <Button
        variant="outline"
        size="sm"
        className="gap-1.5 text-destructive hover:text-destructive"
        onClick={onDelete}
      >
        <Trash2 className="h-4 w-4" aria-hidden="true" />
        {t('workbench.calendar.delete')}
      </Button>
    </div>
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
