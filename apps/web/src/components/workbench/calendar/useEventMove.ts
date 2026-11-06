'use client';

/**
 * Sending the open event to another calendar (ADR-369, lot 5).
 *
 * Its id may change on the way (Outlook and iCloud copy it), so the pane closes on what it
 * was showing. One move at a time: a second press while one is on its way asks nothing.
 */
import { useRef } from 'react';
import { toast } from 'sonner';

import type { WorkbenchCalendarState } from '@/hooks/useWorkbenchCalendar';
import type { CalendarEventDetail, WorkbenchCalendar } from '@/lib/workbench/types';

export interface EventMoving {
  move: (event: CalendarEventDetail, destination: WorkbenchCalendar) => Promise<void>;
}

/**
 * @param state - The screen's reads and acts.
 * @param said - The sentence a move done is told in, given where the event went.
 * @param onMoved - Closes the event.
 * @param tell - Says why the move was refused.
 */
export function useEventMove(
  state: WorkbenchCalendarState,
  said: (name: string) => string,
  onMoved: () => void,
  tell: (error: unknown) => void
): EventMoving {
  const busy = useRef(false);
  const move = async (event: CalendarEventDetail, destination: WorkbenchCalendar) => {
    if (busy.current) return;
    busy.current = true;
    try {
      await state.move(event.calendar_id, event.id, destination.id);
      toast.success(said(destination.name));
      onMoved();
    } catch (error: unknown) {
      tell(error);
    } finally {
      busy.current = false;
    }
  };
  return { move };
}
