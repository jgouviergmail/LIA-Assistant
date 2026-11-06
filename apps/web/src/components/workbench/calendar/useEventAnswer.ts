'use client';

/**
 * Answering an invitation from the open event (ADR-369, lot 5).
 *
 * The answer shows on the event once the provider took it. A declined event closes:
 * Graph takes it out of the calendar, so nothing is left to read, and the pane does
 * the same on every provider.
 */
import { useState } from 'react';
import { toast } from 'sonner';

import type { WorkbenchCalendarState } from '@/hooks/useWorkbenchCalendar';
import type { WorkbenchItemState } from '@/hooks/useWorkbenchItem';
import type { CalendarEventDetail, EventAnswer } from '@/lib/workbench/types';

export interface EventAnswering {
  /** The answer on its way. */
  answering: EventAnswer | null;
  answer: (event: CalendarEventDetail, response: EventAnswer) => Promise<void>;
}

/**
 * @param state - The screen's reads and acts.
 * @param detail - The open event.
 * @param said - The sentence an answer taken is told in.
 * @param onDeclined - Closes the event.
 * @param tell - Says why the answer was refused.
 */
export function useEventAnswer(
  state: WorkbenchCalendarState,
  detail: WorkbenchItemState<CalendarEventDetail>,
  said: string,
  onDeclined: () => void,
  tell: (error: unknown) => void
): EventAnswering {
  const [answering, setAnswering] = useState<EventAnswer | null>(null);
  const answer = async (event: CalendarEventDetail, response: EventAnswer) => {
    setAnswering(response);
    try {
      await state.answer(event.calendar_id, event.id, response);
      toast.success(said);
      if (response === 'declined') onDeclined();
      else detail.setItem(current => ({ ...current, my_response: response }));
    } catch (error: unknown) {
      tell(error);
    } finally {
      setAnswering(null);
    }
  };
  return { answering, answer };
}
