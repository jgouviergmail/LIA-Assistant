/**
 * A new event, or a change to one (ADR-369, spec §14) — the editor's wiring
 * (the bodies themselves are `lib/workbench/calendar/editor`'s, tested there):
 * an event is created once, in a calendar the person may write, with a video
 * call only where offered and asked; a change sends what changed and nothing
 * when nothing did, telling the guests only where the provider lets the page
 * choose; a title is required and an end before the start is refused; a
 * refusal keeps the form, an outcome nobody knows says to look in the calendar.
 */

import { describe, expect, it, vi } from 'vitest';

import { fireEvent, renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { ApiError } from '@/lib/api-client';
import { newEventFields } from '@/lib/workbench/calendar/editor';
import { WORKBENCH_RECIPIENTS_PATH } from '@/lib/workbench/recipients';
import type { CalendarEventDetail, WorkbenchCalendar } from '@/lib/workbench/types';

import { EventEditor, type EditorTarget } from '../EventEditor';

// The contacts matcher, played: « Mar… » finds Marc; the arguments say which door asked.
const { suggest } = vi.hoisted(() => ({
  suggest: vi.fn((query: string) => ({
    suggestions: query.toLowerCase().startsWith('mar')
      ? [{ name: 'Marc Dupont', email: 'marc@example.org' }]
      : [],
    truncated: false,
  })),
}));
vi.mock('@/hooks/useRecipientSuggestions', () => ({ useRecipientSuggestions: suggest }));

const PARIS = 'Europe/Paris';

const CALENDARS: WorkbenchCalendar[] = [
  {
    id: 'primary',
    name: 'Me',
    color: null,
    primary: true,
    default: false,
    writable: true,
    manageable: false,
  },
  {
    id: 'team',
    name: 'Team',
    color: null,
    primary: false,
    default: false,
    writable: true,
    manageable: true,
  },
  {
    id: 'holidays',
    name: 'Holidays',
    color: null,
    primary: false,
    default: false,
    writable: false,
    manageable: false,
  },
];

const EVENT: CalendarEventDetail = {
  id: 'e1',
  calendar_id: 'primary',
  summary: 'Review',
  all_day: false,
  start: '2026-11-02T09:00:00Z',
  end: '2026-11-02T10:00:00Z',
  location: 'Room 1',
  recurring: false,
  conference_url: null,
  description: null,
  attendees: [{ email: 'ana@example.org', name: 'Ana', response: 'accepted' }],
  organizer: null,
  link: null,
  reminder_minutes: null,
  busy: true,
  private: false,
  zone: null,
  my_response: null,
};

const NEW: EditorTarget = { kind: 'new', fields: newEventFields('primary', '2026-11-02', '10:00') };

function editor(
  target: EditorTarget = NEW,
  {
    conferenceOffered = true,
    notifyOffered = true,
    bounds = { summary_max_chars: 1024 } as Record<string, number>,
  } = {}
) {
  const props = {
    onCreate: vi.fn().mockResolvedValue({}),
    onUpdate: vi.fn().mockResolvedValue({}),
    onClose: vi.fn(),
  };
  const rendered = renderWithProviders(
    <EventEditor
      lng="en"
      target={target}
      zone={PARIS}
      calendars={CALENDARS}
      conferenceOffered={conferenceOffered}
      notifyOffered={notifyOffered}
      bounds={bounds}
      {...props}
    />
  );
  return { ...rendered, ...props };
}

const title = () => screen.getByLabelText('workbench.calendar.editor.summary');
const create = () => screen.getByRole('button', { name: 'workbench.calendar.editor.create' });
const save = () => screen.getByRole('button', { name: 'workbench.calendar.editor.save' });

describe('EventEditor — a repeating event', () => {
  it('asks when it comes back on a new event, and sends the rule', async () => {
    const { user, onCreate } = editor();

    expect(await screen.findByText('workbench.calendar.editor.repeat')).toBeInTheDocument();
    await user.type(screen.getByLabelText('workbench.calendar.editor.summary'), 'Standup');
    await user.click(screen.getByRole('combobox', { name: 'recurrence.freq_label' }));
    await user.click(await screen.findByRole('option', { name: 'recurrence.freq.daily' }));
    await user.click(screen.getByRole('button', { name: 'workbench.calendar.editor.create' }));

    await waitFor(() => expect(onCreate).toHaveBeenCalled());
    expect(onCreate.mock.calls[0][0].recurrence).toMatchObject({
      freq: 'daily',
      anchor_date: '2026-11-02',
    });
  });

  it('asks nothing of the kind when one occurrence is changed', async () => {
    editor({ kind: 'edit', event: { ...EVENT, recurring: true } });

    await screen.findByLabelText('workbench.calendar.editor.summary');
    expect(screen.queryByText('workbench.calendar.editor.repeat')).toBeNull();
  });

  it('says a whole series is changed, and sends so', async () => {
    const { user, onUpdate } = editor({
      kind: 'edit',
      event: { ...EVENT, recurring: true },
      series: true,
    });

    expect(await screen.findByText('workbench.calendar.editor.title_series')).toBeInTheDocument();
    const summary = screen.getByLabelText('workbench.calendar.editor.summary');
    await user.clear(summary);
    await user.type(summary, 'Retro');
    await user.click(screen.getByRole('button', { name: 'workbench.calendar.editor.save' }));

    await waitFor(() => expect(onUpdate).toHaveBeenCalled());
    expect(onUpdate.mock.calls[0][0]).toMatchObject({ summary: 'Retro', scope: 'series' });
  });
});

describe('EventEditor — a new event', () => {
  it('creates it once, in a calendar the person may write, with the video call asked', async () => {
    let finish: () => void = () => undefined;
    const { user, onCreate, onClose } = editor();
    onCreate.mockImplementationOnce(() => new Promise<void>(resolve => (finish = resolve)));
    const calendar = screen.getByLabelText('workbench.calendar.editor.calendar');

    expect([...calendar.querySelectorAll('option')].map(option => option.value)).toEqual([
      'primary',
      'team',
    ]);
    await user.type(title(), '  Planning  ');
    await user.selectOptions(calendar, 'team');
    await user.click(screen.getByLabelText('workbench.calendar.editor.conference'));
    await user.click(create());
    fireEvent.submit(title().closest('form') as HTMLFormElement);
    finish();

    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(onCreate).toHaveBeenCalledTimes(1);
    expect(onCreate.mock.calls[0][0]).toMatchObject({
      calendar_id: 'team',
      summary: 'Planning',
      timezone: PARIS,
      conference: true,
      idempotency_key: expect.any(String),
    });
  });

  /**
   * Owner request (2026-10-31): a guest is suggested from the account's contacts exactly as
   * a message's recipient is — the same field, the same matcher, from the shortest query
   * the calendar's own descriptor publishes.
   */
  it("suggests the account's contacts for the guests, and the pick is a guest", async () => {
    const { user, onCreate } = editor(NEW, {
      bounds: { summary_max_chars: 1024, recipient_query_min_chars: 3 },
    });
    await user.type(title(), 'Review');
    const guests = screen.getByRole('combobox', { name: 'workbench.calendar.editor.attendees' });
    await user.type(guests, 'Mar');

    expect(suggest).toHaveBeenLastCalledWith('Mar', true, 3, WORKBENCH_RECIPIENTS_PATH);
    fireEvent.mouseDown(screen.getByRole('option', { name: /Marc Dupont/ }));
    expect(guests).toHaveValue('marc@example.org, ');

    fireEvent.submit(title().closest('form') as HTMLFormElement);
    await waitFor(() => expect(onCreate).toHaveBeenCalledOnce());
    expect(onCreate.mock.calls[0][0]).toMatchObject({ attendees: ['marc@example.org'] });
  });

  /** Owner request (2026-10-31): the guests come right under the title. */
  it('asks for the guests right under the title', () => {
    editor();
    const guests = screen.getByRole('combobox', { name: 'workbench.calendar.editor.attendees' });
    const calendar = screen.getByLabelText('workbench.calendar.editor.calendar');
    const follows = (first: Element, next: Element) =>
      Boolean(first.compareDocumentPosition(next) & Node.DOCUMENT_POSITION_FOLLOWING);

    expect(follows(title(), guests)).toBe(true);
    expect(follows(guests, calendar)).toBe(true);
  });

  it('offers no video call the provider does not have', async () => {
    const { user, onCreate } = editor(NEW, { conferenceOffered: false });

    expect(screen.queryByLabelText('workbench.calendar.editor.conference')).toBeNull();
    await user.type(title(), 'Planning');
    await user.click(create());

    await waitFor(() => expect(onCreate).toHaveBeenCalledTimes(1));
    expect(onCreate.mock.calls[0][0]).not.toHaveProperty('conference');
  });

  it('sends nothing without a title, nor when the event ends before it starts', async () => {
    const { user, onCreate } = editor();

    await user.click(create());
    expect(create()).toHaveAttribute('aria-disabled', 'true');
    // Spaces pass the browser's own `required`: the editor refuses them itself.
    await user.type(title(), '   ');
    await user.click(create());
    expect(onCreate).not.toHaveBeenCalled();
    await user.clear(title());
    await user.type(title(), 'Planning');
    fireEvent.change(screen.getByLabelText('workbench.calendar.editor.end_time'), {
      target: { value: '09:00' },
    });
    expect(screen.getByText('workbench.calendar.editor.ends_before')).toBeInTheDocument();
    fireEvent.submit(title().closest('form') as HTMLFormElement);

    expect(onCreate).not.toHaveBeenCalled();
  });

  it('asks an all-day event for its days, not its times', async () => {
    const { user } = editor();

    await user.click(screen.getByRole('switch', { name: 'workbench.calendar.editor.all_day' }));

    expect(screen.getByLabelText('workbench.calendar.editor.first_day')).toBeInTheDocument();
    expect(screen.getByLabelText('workbench.calendar.editor.last_day')).toBeInTheDocument();
    expect(screen.queryByLabelText('workbench.calendar.editor.start_time')).toBeNull();
  });
});

describe('EventEditor — a change', () => {
  const EDIT: EditorTarget = { kind: 'edit', event: EVENT };

  it('sends what changed, telling the guests by default where the page may choose', async () => {
    const { user, onUpdate, onClose } = editor(EDIT);
    const where = screen.getByLabelText('workbench.calendar.editor.location');

    expect(screen.queryByLabelText('workbench.calendar.editor.calendar')).toBeNull();
    await user.clear(where);
    await user.type(where, 'Room 2');
    await user.click(save());

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(onUpdate).toHaveBeenCalledWith({
      calendar_id: 'primary',
      event_id: 'e1',
      location: 'Room 2',
      notify: true,
    });
  });

  it('keeps the guests uninformed when unticked, and asks nothing where the page may not', async () => {
    const chosen = editor(EDIT);
    await chosen.user.type(title(), '!');
    await chosen.user.click(screen.getByLabelText('workbench.calendar.editor.notify'));
    await chosen.user.click(save());
    await waitFor(() => expect(chosen.onUpdate).toHaveBeenCalled());
    expect(chosen.onUpdate.mock.calls[0][0]).toMatchObject({ summary: 'Review!', notify: false });
    chosen.unmount();

    const elsewhere = editor(EDIT, { notifyOffered: false });
    expect(screen.queryByLabelText('workbench.calendar.editor.notify')).toBeNull();
    await elsewhere.user.type(title(), '!');
    await elsewhere.user.click(save());
    await waitFor(() => expect(elsewhere.onUpdate).toHaveBeenCalled());
    expect(elsewhere.onUpdate.mock.calls[0][0]).not.toHaveProperty('notify');
  });

  it('closes without a request when nothing changed', async () => {
    const { user, onUpdate, onClose } = editor(EDIT);

    await user.click(save());

    expect(onUpdate).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe('EventEditor — a zone of its own', () => {
  const zone = () => screen.getByLabelText('workbench.calendar.editor.time_zone');

  it('sends a new event on the clock the person chose', async () => {
    const { user, onCreate } = editor();

    await user.type(title(), 'Call');
    await user.selectOptions(zone(), 'Asia/Tokyo');
    await user.click(create());

    await waitFor(() => expect(onCreate).toHaveBeenCalledTimes(1));
    expect(onCreate.mock.calls[0]![0]).toMatchObject({
      timezone: 'Asia/Tokyo',
      start: '2026-11-02T10:00',
    });
  });

  it('offers the account’s clock first, and says so', () => {
    editor();

    expect(zone().querySelector('option')).toHaveValue(PARIS);
    expect(screen.getByText('workbench.calendar.editor.zone')).toBeInTheDocument();
  });

  it('asks a day for no clock', async () => {
    const { user } = editor();

    await user.click(screen.getByRole('switch'));

    expect(screen.queryByLabelText('workbench.calendar.editor.time_zone')).not.toBeInTheDocument();
  });

  it('opens an event on the clock it was set on, and says so', () => {
    editor({
      kind: 'edit',
      event: {
        ...EVENT,
        zone: 'America/New_York',
        start: '2026-11-02T14:00:00Z',
        end: '2026-11-02T15:00:00Z',
      },
    });

    expect(zone()).toHaveValue('America/New_York');
    expect(screen.getByText('workbench.calendar.editor.own_zone')).toBeInTheDocument();
  });
});

describe('EventEditor — refusals', () => {
  it('says a refusal in its own words and keeps the form', async () => {
    const { user, onCreate, onClose } = editor();
    onCreate
      .mockRejectedValueOnce(
        new ApiError('down', 502, { detail: { code: 'provider_unavailable' } })
      )
      .mockRejectedValueOnce(new Error('network'));

    await user.type(title(), 'Planning');
    await user.click(create());
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'workbench.errors.provider_unavailable'
    );
    await user.click(create());
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('workbench.calendar.failed')
    );

    expect(onClose).not.toHaveBeenCalled();
    expect(title()).toHaveValue('Planning');
  });

  it('says to look in the calendar when nobody knows whether it was made', async () => {
    const { user, onCreate } = editor();
    onCreate.mockRejectedValueOnce(
      new ApiError('lost', 504, { detail: { code: 'outcome_unknown' } })
    );

    await user.type(title(), 'Planning');
    await user.click(create());

    expect(await screen.findByRole('alert')).toHaveTextContent('workbench.calendar.editor.unknown');
  });
});
