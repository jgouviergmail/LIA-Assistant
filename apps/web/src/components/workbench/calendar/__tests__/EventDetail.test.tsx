/**
 * What an open event offers (ADR-369, owner 2026-11-06): all of it as icons in the bar, on a
 * computer and on a phone, nothing behind « … ». Moving opens the calendars it can go to under its
 * own icon. A series keeps its second edit beside the first, a calendar it cannot be written on
 * keeps what touches nothing of it.
 */
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, within } from '@/__tests__/test-utils';
import type { CalendarEventDetail, WorkbenchCalendar } from '@/lib/workbench/types';

import { EventDetail, type EventDetailProps } from '../EventDetail';

const EVENT: CalendarEventDetail = {
  id: 'e1',
  calendar_id: 'primary',
  summary: 'Committee review',
  all_day: false,
  start: '2026-11-06T11:00:00Z',
  end: '2026-11-06T12:00:00Z',
  location: null,
  recurring: false,
  conference_url: null,
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

const CALENDAR: WorkbenchCalendar = {
  id: 'primary',
  name: 'Work',
  color: '#336699',
  primary: true,
  default: true,
  writable: true,
  manageable: false,
};

const OTHER: WorkbenchCalendar = { ...CALENDAR, id: 'family', name: 'Family', primary: false };

function draw(overrides: Partial<EventDetailProps> = {}) {
  const props: EventDetailProps = {
    lng: 'en',
    event: EVENT,
    loading: false,
    error: null,
    calendar: CALENDAR,
    zone: 'Europe/Paris',
    occurrenceEdit: true,
    onClose: vi.fn(),
    onRetry: vi.fn(),
    onEdit: vi.fn(),
    onEditSeries: vi.fn(),
    onDelete: vi.fn(),
    onDuplicate: vi.fn(),
    onAsk: vi.fn(),
    destinations: [OTHER],
    onMove: vi.fn(),
    ...overrides,
  };
  return { ...renderWithProviders(<EventDetail {...props} />), props };
}

/** The bar's acts, the way out set aside. */
function bar(): (string | null)[] {
  return within(screen.getByTestId('detail-acts'))
    .getAllByRole('button')
    .map(button => button.getAttribute('aria-label'));
}

const EDIT = 'workbench.calendar.edit';
const SERIES = 'workbench.calendar.edit_series';
const DUPLICATE = 'workbench.calendar.duplicate';
const DELETE = 'workbench.calendar.delete';
const MOVE = 'workbench.calendar.move_to';
const MOVE_LINE = 'workbench.calendar.move_to_name';
const ASK = 'workbench.ask.label';

describe('EventDetail — what it offers', () => {
  it('holds everything in the bar, moving and the question included', () => {
    draw();

    expect(bar()).toEqual([EDIT, DUPLICATE, MOVE, DELETE, ASK]);
  });

  it('holds the whole series beside the occurrence, where a series cannot move', () => {
    draw({ event: { ...EVENT, recurring: true }, destinations: [] });

    expect(bar()).toEqual([EDIT, SERIES, DUPLICATE, DELETE, ASK]);
  });

  it('offers only the whole series where the provider changes no occurrence alone', () => {
    draw({ event: { ...EVENT, recurring: true }, occurrenceEdit: false, destinations: [] });

    expect(bar()).toEqual([SERIES, DUPLICATE, DELETE, ASK]);
  });

  it('offers no move where the event can go nowhere', () => {
    draw({ destinations: [] });

    expect(bar()).toEqual([EDIT, DUPLICATE, DELETE, ASK]);
  });

  it('offers a copy and a question on a calendar it cannot write', () => {
    draw({ calendar: { ...CALENDAR, writable: false }, destinations: [] });

    expect(bar()).toEqual([DUPLICATE, ASK]);
  });

  it('draws a deletion in the colour of what cannot be taken lightly', () => {
    draw();

    expect(screen.getByRole('button', { name: DELETE })).toHaveClass('text-destructive');
  });

  it('names every calendar it can go to, under one icon', async () => {
    const team = { ...OTHER, id: 'team', name: 'Team' };
    const { user } = draw({ destinations: [OTHER, team] });

    expect(bar()).toEqual([EDIT, DUPLICATE, MOVE, DELETE, ASK]);
    await user.click(screen.getByRole('button', { name: MOVE }));

    expect(await screen.findAllByRole('menuitem')).toHaveLength(2);
  });

  it('moves the event to the calendar its line names', async () => {
    const team = { ...OTHER, id: 'team', name: 'Team' };
    const { user, props } = draw({ destinations: [OTHER, team] });

    await user.click(screen.getByRole('button', { name: MOVE }));
    const [, second] = await screen.findAllByRole('menuitem');
    await user.click(second!);

    expect(props.onMove).toHaveBeenCalledTimes(1);
    expect(props.onMove).toHaveBeenCalledWith(team);
  });

  it('moves nothing on the icon alone, even towards the only other calendar', async () => {
    const { user, props } = draw();

    await user.click(screen.getByRole('button', { name: MOVE }));

    expect(await screen.findByRole('menuitem', { name: MOVE_LINE })).toBeInTheDocument();
    expect(props.onMove).not.toHaveBeenCalled();
  });

  it('offers no series on a calendar it cannot write', () => {
    draw({
      event: { ...EVENT, recurring: true },
      calendar: { ...CALENDAR, writable: false },
      destinations: [],
    });

    expect(bar()).toEqual([DUPLICATE, ASK]);
  });

  it('offers the question alone when nothing can be done to it', () => {
    draw({
      calendar: { ...CALENDAR, writable: false },
      destinations: [],
      onDuplicate: undefined,
    });

    expect(bar()).toEqual([ASK]);
  });

  it('offers nothing while the event is being read', () => {
    draw({ event: undefined, loading: true });

    expect(screen.queryByTestId('detail-acts')).toBeNull();
  });

  it('runs what each names', async () => {
    const { user, props } = draw({ event: { ...EVENT, recurring: true }, destinations: [] });

    await user.click(screen.getByRole('button', { name: EDIT }));
    await user.click(screen.getByRole('button', { name: SERIES }));
    await user.click(screen.getByRole('button', { name: DUPLICATE }));
    await user.click(screen.getByRole('button', { name: DELETE }));
    await user.click(screen.getByRole('button', { name: ASK }));

    expect(props.onEdit).toHaveBeenCalledTimes(1);
    expect(props.onEditSeries).toHaveBeenCalledTimes(1);
    expect(props.onDuplicate).toHaveBeenCalledTimes(1);
    expect(props.onDelete).toHaveBeenCalledTimes(1);
    expect(props.onAsk).toHaveBeenCalledTimes(1);
  });

  it('moves the event to the calendar picked in the list', async () => {
    const { user, props } = draw();

    await user.click(screen.getByRole('button', { name: MOVE }));
    await user.click(await screen.findByRole('menuitem', { name: MOVE_LINE }));

    expect(props.onMove).toHaveBeenCalledWith(OTHER);
  });
});
