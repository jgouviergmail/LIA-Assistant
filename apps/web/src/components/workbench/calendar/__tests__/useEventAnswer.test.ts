/**
 * Answering an invitation (ADR-369, lot 5): the answer shows once the provider took it,
 * a declined event closes, and a refusal changes nothing and is said.
 */
import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { WorkbenchCalendarState } from '@/hooks/useWorkbenchCalendar';
import type { WorkbenchItemState } from '@/hooks/useWorkbenchItem';
import type { CalendarEventDetail } from '@/lib/workbench/types';

const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { useEventAnswer } from '../useEventAnswer';

const EVENT: CalendarEventDetail = {
  id: 'e1',
  calendar_id: 'c1',
  summary: 'Weekly sync',
  all_day: false,
  start: '2026-11-05T09:00:00Z',
  end: '2026-11-05T10:00:00Z',
  location: null,
  recurring: false,
  conference_url: null,
  description: null,
  attendees: [],
  organizer: 'ana@example.org',
  link: null,
  reminder_minutes: null,
  busy: true,
  private: false,
  zone: null,
  my_response: 'needsAction',
};

function opened() {
  let item = EVENT;
  const detail: WorkbenchItemState<CalendarEventDetail> = {
    item,
    loading: false,
    error: null,
    refresh: vi.fn(),
    setItem: change => {
      item = change(item);
    },
  };
  return { detail, current: () => item };
}

function calendarState(answer: WorkbenchCalendarState['answer']): WorkbenchCalendarState {
  return {
    window: { item: undefined, loading: false, error: null, refresh: vi.fn(), setItem: vi.fn() },
    read: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    answer,
    move: vi.fn(),
  };
}

describe('useEventAnswer', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows the answer the provider took, and says it left', async () => {
    const answer = vi.fn().mockResolvedValue(undefined);
    const { detail, current } = opened();
    const closed = vi.fn();
    const { result } = renderHook(() =>
      useEventAnswer(calendarState(answer), detail, 'sent', closed, vi.fn())
    );

    await act(() => result.current.answer(EVENT, 'tentative'));

    expect(answer).toHaveBeenCalledWith('c1', 'e1', 'tentative');
    expect(current().my_response).toBe('tentative');
    expect(toast.success).toHaveBeenCalledWith('sent');
    expect(closed).not.toHaveBeenCalled();
    expect(result.current.answering).toBeNull();
  });

  it('closes a declined event: Graph takes it out of the calendar', async () => {
    const { detail } = opened();
    const closed = vi.fn();
    const { result } = renderHook(() =>
      useEventAnswer(
        calendarState(vi.fn().mockResolvedValue(undefined)),
        detail,
        'sent',
        closed,
        vi.fn()
      )
    );

    await act(() => result.current.answer(EVENT, 'declined'));

    expect(closed).toHaveBeenCalledOnce();
  });

  it('says a refusal and changes nothing', async () => {
    const refused = new Error('no');
    const { detail, current } = opened();
    const tell = vi.fn();
    const { result } = renderHook(() =>
      useEventAnswer(
        calendarState(vi.fn().mockRejectedValue(refused)),
        detail,
        'sent',
        vi.fn(),
        tell
      )
    );

    await act(() => result.current.answer(EVENT, 'accepted'));

    expect(tell).toHaveBeenCalledWith(refused);
    expect(current().my_response).toBe('needsAction');
    expect(toast.success).not.toHaveBeenCalled();
    expect(result.current.answering).toBeNull();
  });
});
