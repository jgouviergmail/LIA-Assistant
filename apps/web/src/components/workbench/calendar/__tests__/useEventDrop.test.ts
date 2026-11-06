/**
 * What a drop does (ADR-369, lot 2).
 *
 * Nobody is told by a slip of the mouse: an event with guests opens its editor
 * on the new times and nothing leaves. Without guests the change leaves at once
 * and can be taken back; the event stays where it landed until the provider
 * answers, and goes back if it refuses. One drop at a time.
 */
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ShownEvent } from '@/lib/workbench/calendar/events';
import type { CalendarEventDetail } from '@/lib/workbench/types';

const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { useEventDrop, type EventDropOptions } from '../useEventDrop';

const PARIS = 'Europe/Paris';

const EVENT: ShownEvent = {
  id: 'e1',
  key: 'primary|e1',
  calendar_id: 'primary',
  summary: 'Review',
  all_day: false,
  start: '2026-11-02T09:00:00Z',
  end: '2026-11-02T10:00:00Z',
  location: null,
  recurring: false,
  conference_url: null,
  color: null,
};

const ALONE: CalendarEventDetail = {
  ...EVENT,
  description: null,
  attendees: [],
  organizer: null,
  link: null,
  reminder_minutes: null,
  busy: true,
  private: false,
  zone: null,
  my_response: null,
};

const LATER = { edge: 'move', minutes: 60, day: '2026-11-02' } as const;

function setup(detail: CalendarEventDetail = ALONE) {
  const options = {
    lng: 'en',
    zone: PARIS,
    state: {
      read: vi.fn().mockResolvedValue(detail),
      update: vi.fn().mockResolvedValue(detail),
    },
    edit: vi.fn(),
    onChanged: vi.fn(),
    tell: vi.fn(),
  } satisfies EventDropOptions;
  return { options, hook: renderHook(() => useEventDrop(options)) };
}

beforeEach(() => vi.clearAllMocks());

describe('useEventDrop', () => {
  it('sends the wall times and the zone of an event nobody else is in', async () => {
    const { options, hook } = setup();

    await act(() => hook.result.current.drop(EVENT, LATER));

    expect(options.state.update).toHaveBeenCalledWith({
      calendar_id: 'primary',
      event_id: 'e1',
      start: '2026-11-02T11:00',
      end: '2026-11-02T12:00',
      all_day: false,
      timezone: PARIS,
    });
    expect(options.onChanged).toHaveBeenCalledOnce();
    expect(options.edit).not.toHaveBeenCalled();
  });

  it('takes the move back from the toast', async () => {
    const { options, hook } = setup();
    await act(() => hook.result.current.drop(EVENT, LATER));
    const { action } = toast.success.mock.calls[0][1];

    action.onClick();

    await waitFor(() => expect(options.state.update).toHaveBeenCalledTimes(2));
    expect(options.state.update.mock.calls[1][0]).toMatchObject({
      start: '2026-11-02T10:00',
      end: '2026-11-02T11:00',
    });
  });

  it('opens the editor on the new times when the event has guests, sending nothing', async () => {
    const guests: CalendarEventDetail = {
      ...ALONE,
      attendees: [{ email: 'ana@example.org', name: null, response: 'accepted' }],
    };
    const { options, hook } = setup(guests);

    await act(() => hook.result.current.drop(EVENT, LATER));

    expect(options.state.update).not.toHaveBeenCalled();
    expect(options.edit).toHaveBeenCalledWith({
      kind: 'edit',
      event: guests,
      fields: expect.objectContaining({ startTime: '11:00', endTime: '12:00' }),
    });
    expect(hook.result.current.moved).toBeNull();
  });

  it('draws the event where it landed until the provider answers', async () => {
    const { options, hook } = setup();
    let answer: (value: CalendarEventDetail) => void = () => undefined;
    options.state.update.mockReturnValue(
      new Promise<CalendarEventDetail>(resolve => {
        answer = resolve;
      })
    );

    let dropped: Promise<void> = Promise.resolve();
    act(() => {
      dropped = hook.result.current.drop(EVENT, LATER);
    });

    expect(hook.result.current.moved).toEqual({
      key: 'primary|e1',
      start: '2026-11-02T10:00:00.000Z',
      end: '2026-11-02T11:00:00.000Z',
    });
    await waitFor(() => expect(options.state.update).toHaveBeenCalled());
    await act(async () => {
      answer(ALONE);
      await dropped;
    });
    expect(hook.result.current.moved).toBeNull();
  });

  it('puts the event back and says why when the provider refuses', async () => {
    const { options, hook } = setup();
    const refusal = new Error('refused');
    options.state.update.mockRejectedValue(refusal);

    await act(() => hook.result.current.drop(EVENT, LATER));

    expect(options.tell).toHaveBeenCalledWith(refusal);
    expect(hook.result.current.moved).toBeNull();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('says a read that failed, and sends nothing', async () => {
    const { options, hook } = setup();
    const refusal = new Error('gone');
    options.state.read.mockRejectedValue(refusal);

    await act(() => hook.result.current.drop(EVENT, LATER));

    expect(options.tell).toHaveBeenCalledWith(refusal);
    expect(options.state.update).not.toHaveBeenCalled();
  });

  it('asks nothing for a drop that lands where the event was', async () => {
    const { options, hook } = setup();

    await act(() =>
      hook.result.current.drop(EVENT, { edge: 'move', minutes: 0, day: '2026-11-02' })
    );

    expect(options.state.read).not.toHaveBeenCalled();
  });

  it('takes one drop at a time', async () => {
    const { options, hook } = setup();
    options.state.read.mockReturnValue(new Promise<CalendarEventDetail>(() => undefined));

    act(() => {
      void hook.result.current.drop(EVENT, LATER);
      void hook.result.current.drop(EVENT, LATER);
    });

    expect(options.state.read).toHaveBeenCalledOnce();
  });
});
