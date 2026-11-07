'use client';

/**
 * What LIA can do on an open event (ADR-372): the list under its bar's last icon.
 *
 * The minutes a recording left on it are one press away, and a meeting about to happen can be
 * recorded from here: the minutes then find their event by its hours, as any recording's do.
 */
import { ClipboardList, Disc } from 'lucide-react';

import { useMeetingRecorderContext } from '@/components/meetings/MeetingRecorderProvider';
import { useApiQuery } from '@/hooks/useApiQuery';
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
  const { ask, remind, confide, meetings } = useToolBridges(lng);
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
  return {
    lines: [
      ...meeting,
      remindLine(t, t('workbench.assist.remind.words.event', { title, when }), remind),
      ...confideLine(t, title, t('workbench.assist.confide.brief_event', { title, when }), confide),
      readyLine(t, 'event', { title, when }, ask),
    ],
  };
}
