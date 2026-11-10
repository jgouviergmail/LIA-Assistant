'use client';

/**
 * What LIA can do on an open event (ADR-372): the list under its bar's last icon.
 *
 * The minutes a recording left on it are one press away, and a meeting about to happen can be
 * recorded from here: the minutes then find their event by its hours, as any recording's do.
 * Its guests can be written to with LIA (2026-11-07): a new message to each of them once, the
 * person's own address left out, opening on « Write from an instruction ».
 */
import { ClipboardList, Disc, PenLine } from '@/lib/icons';

import { useMeetingRecorderContext } from '@/components/meetings/MeetingRecorderProvider';
import { useApiQuery } from '@/hooks/useApiQuery';
import { useAuth } from '@/hooks/useAuth';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { isRecordableNow } from '@/lib/workbench/calendar/events';
import { eventWhen } from '@/lib/workbench/calendar/format';
import type { CalendarEventDetail } from '@/lib/workbench/types';
import type { MeetingListResponse } from '@/types/meetings';

import { useMinuteClock } from '../calendar/useWallClock';
import type { AssistOffer, DetailDeed } from '../DetailBar';
import { useToolBridges } from '../useToolBridges';
import { confideLine, readyLine, remindLine } from './lines';

/**
 * Who a message about an event goes to: its guests and its organiser, each once, whatever the
 * case, the person's own address left out (the account's, as far as the page knows it).
 */
function guestsOf(event: CalendarEventDetail, own: string | undefined): string[] {
  const seen = new Set(own ? [own.toLowerCase()] : []);
  const guests: string[] = [];
  for (const address of [...event.attendees.map(guest => guest.email), event.organizer ?? '']) {
    const key = address.trim().toLowerCase();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    guests.push(address.trim());
  }
  return guests;
}

/** The minutes filed on this event, once read; nothing is asked where meetings are off. */
function useEventMinutes(eventId: string | null, offered: boolean): string | null {
  const { data, loading } = useApiQuery<MeetingListResponse>('/meetings', {
    componentName: 'EventMinutes',
    enabled: offered && eventId !== null,
    params: { calendar_event_id: eventId ?? '', limit: 1 },
  });
  return loading ? null : (data?.items[0]?.id ?? null);
}

/**
 * @param lng - The reader's language.
 * @param event - The event read, once it is.
 * @param zone - The account's zone.
 * @returns The offer of its bar; nothing while it is being read.
 */
export function useEventAssist(
  lng: Language,
  event: CalendarEventDetail | undefined,
  zone: string
): AssistOffer {
  const { t } = useTranslation(lng);
  const { ask, remind, confide, meetings, assists, offers, go } = useToolBridges(lng);
  const { user } = useAuth();
  const router = useLocalizedRouter();
  const recorder = useMeetingRecorderContext();
  const minutes = useEventMinutes(event?.id ?? null, meetings);
  const now = useMinuteClock();
  if (!event) return { lines: [] };
  const title = event.summary || t('workbench.calendar.no_title');
  const when = eventWhen(event, zone, lng, t('workbench.calendar.all_day'));
  const meeting: DetailDeed[] = [];
  if (minutes) {
    meeting.push({
      label: t('workbench.assist.calendar.minutes'),
      icon: ClipboardList,
      onSelect: () => router.push(`/dashboard/meetings/${minutes}`),
    });
  }
  const recordable = meetings && recorder?.isSupported && recorder.phase === 'idle';
  if (recordable && isRecordableNow(event, now.getTime())) {
    meeting.push({
      label: t('workbench.assist.calendar.record'),
      icon: Disc,
      onSelect: () => void recorder.start(),
    });
  }
  const guests = guestsOf(event, user?.email);
  const writes: DetailDeed[] =
    assists && guests.length > 0 && offers('compose')
      ? [
          {
            label: t('workbench.assist.calendar.write_guests'),
            icon: PenLine,
            onSelect: () =>
              go({
                kind: 'compose',
                to: guests.join(', '),
                ...(event.summary ? { subject: event.summary } : {}),
                assisted: true,
              }),
          },
        ]
      : [];
  return {
    lines: [
      ...meeting,
      ...writes,
      remindLine(t, t('workbench.assist.remind.words.event', { title, when }), remind),
      ...confideLine(t, title, t('workbench.assist.confide.brief_event', { title, when }), confide),
      readyLine(t, 'event', { title, when }, ask),
    ],
  };
}
