'use client';

/**
 * What a drop does (ADR-369, lot 2).
 *
 * The event stays where it landed while the provider is asked, and goes back if
 * it refuses. Nobody is told by a slip of the mouse: an event with guests opens
 * its editor on the new times, « tell the guests » in sight, and nothing leaves
 * until the person saves. Without guests the change is sent at once, and the
 * toast takes it back. One drop at a time.
 */
import { useCallback, useRef, useState } from 'react';
import { toast } from 'sonner';

import type { WorkbenchCalendarState } from '@/hooks/useWorkbenchCalendar';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import {
  droppedFields,
  wallFieldsOf,
  type EventDrop,
  type WallBounds,
} from '@/lib/workbench/calendar/drag';
import { changeBody, fieldsOf } from '@/lib/workbench/calendar/editor';
import type { ShownEvent } from '@/lib/workbench/calendar/events';
import { wallTimeToInstant } from '@/lib/workbench/calendar/zoned';

import type { EditorTarget } from './EventEditor';

/** Where an event is drawn while the provider has not answered. */
export interface MovedEvent {
  key: string;
  start: string;
  end: string;
}

function landed(key: string, bounds: WallBounds, zone: string): MovedEvent {
  return {
    key,
    start: wallTimeToInstant(bounds.startDate, bounds.startTime, zone).toISOString(),
    end: wallTimeToInstant(bounds.endDate, bounds.endTime, zone).toISOString(),
  };
}

export interface EventDropOptions {
  lng: Language;
  zone: string;
  state: Pick<WorkbenchCalendarState, 'read' | 'update'>;
  /** Opens the editor on an event with guests. */
  edit: (target: EditorTarget) => void;
  onChanged: () => void;
  tell: (error: unknown) => void;
}

export interface EventDropState {
  moved: MovedEvent | null;
  drop: (event: ShownEvent, drop: EventDrop) => Promise<void>;
}

export function useEventDrop({
  lng,
  zone,
  state,
  edit,
  onChanged,
  tell,
}: EventDropOptions): EventDropState {
  const { t } = useTranslation(lng);
  const [moved, setMoved] = useState<MovedEvent | null>(null);
  // Set synchronously: a second drop lands before the render that shows the first.
  const busy = useRef(false);
  const { read, update } = state;

  const drop = useCallback(
    async (event: ShownEvent, asked: EventDrop) => {
      const bounds = droppedFields(wallFieldsOf(event, zone), asked);
      if (bounds === null || busy.current) return;
      busy.current = true;
      setMoved(landed(event.key, bounds, zone));
      try {
        const detail = await read(event.calendar_id, event.id);
        const before = fieldsOf(detail, zone);
        const after = { ...before, ...bounds };
        if (detail.attendees.length > 0) {
          edit({ kind: 'edit', event: detail, fields: after });
          return;
        }
        const forth = changeBody(detail, before, after, zone, undefined);
        const back = changeBody(detail, after, before, zone, undefined);
        if (forth === null || back === null) return;
        await update(forth);
        onChanged();
        toast.success(t('workbench.calendar.moved'), {
          action: {
            label: t('workbench.calendar.undo'),
            onClick: () => {
              update(back).then(onChanged).catch(tell);
            },
          },
        });
      } catch (error: unknown) {
        tell(error);
      } finally {
        busy.current = false;
        setMoved(null);
      }
    },
    [edit, onChanged, read, t, tell, update, zone]
  );

  return { moved, drop };
}
