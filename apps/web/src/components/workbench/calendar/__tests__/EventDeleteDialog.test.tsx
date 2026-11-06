/**
 * Deleting one event (ADR-369): an occurrence alone, and its guests told only
 * where the provider lets the page choose — checked by default there, never
 * offered elsewhere (the provider tells them its own way). The act runs once
 * per opening, however many clicks reach it.
 */

import { describe, expect, it, vi } from 'vitest';

import { act, renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import type { CalendarEventDetail } from '@/lib/workbench/types';

import { EventDeleteDialog } from '../EventDeleteDialog';

const EVENT: CalendarEventDetail = {
  id: 'e1_20261101',
  calendar_id: 'primary',
  summary: 'Weekly sync',
  all_day: false,
  start: '2026-11-01T13:00:00Z',
  end: '2026-11-01T13:30:00Z',
  location: null,
  recurring: true,
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

function dialog(
  overrides: Partial<CalendarEventDetail> = {},
  notifyOffered = true,
  occurrenceEdit = true
) {
  const onDelete = vi.fn().mockResolvedValue(undefined);
  const onClose = vi.fn();
  const rendered = renderWithProviders(
    <EventDeleteDialog
      lng="en"
      event={{ ...EVENT, ...overrides }}
      notifyOffered={notifyOffered}
      occurrenceEdit={occurrenceEdit}
      onDelete={onDelete}
      onClose={onClose}
    />
  );
  return { ...rendered, onDelete, onClose };
}

describe('EventDeleteDialog — a series', () => {
  it('asks which, this occurrence by default', async () => {
    const { user, onDelete } = dialog();

    expect(screen.getByRole('radio', { name: 'workbench.calendar.delete_this' })).toBeChecked();
    await user.click(screen.getByRole('radio', { name: 'workbench.calendar.delete_whole' }));
    expect(screen.getByText('workbench.calendar.delete_series')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'workbench.calendar.delete' }));

    expect(onDelete).toHaveBeenCalledWith(true, true);
  });

  it('asks nothing of an event that is no series', () => {
    dialog({ recurring: false });

    expect(screen.queryByRole('radio')).toBeNull();
  });

  it('offers the whole series alone where one occurrence cannot go', async () => {
    const { user, onDelete } = dialog({}, true, false);

    expect(screen.queryByRole('radio')).toBeNull();
    expect(screen.getByText('workbench.calendar.delete_series')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'workbench.calendar.delete' }));

    expect(onDelete).toHaveBeenCalledWith(true, true);
  });
});

describe('EventDeleteDialog', () => {
  it('says an occurrence leaves alone, and tells the guests by default', async () => {
    const { user, onDelete } = dialog();

    expect(screen.getByText('workbench.calendar.delete_occurrence')).toBeInTheDocument();
    expect(
      screen.getByRole('checkbox', { name: 'workbench.calendar.editor.notify' })
    ).toBeChecked();
    await user.click(screen.getByRole('button', { name: 'workbench.calendar.delete' }));

    expect(onDelete).toHaveBeenCalledWith(true, false);
  });

  it('keeps the guests uninformed when the person unticks it', async () => {
    const { user, onDelete } = dialog({ recurring: false });

    expect(screen.getByText('workbench.calendar.delete_description')).toBeInTheDocument();
    await user.click(screen.getByRole('checkbox', { name: 'workbench.calendar.editor.notify' }));
    await user.click(screen.getByRole('button', { name: 'workbench.calendar.delete' }));

    expect(onDelete).toHaveBeenCalledWith(false, false);
  });

  it('offers no choice the provider does not give, nor one with nobody to tell', async () => {
    const elsewhere = dialog({}, false);
    expect(screen.queryByRole('checkbox')).toBeNull();
    await elsewhere.user.click(screen.getByRole('button', { name: 'workbench.calendar.delete' }));
    expect(elsewhere.onDelete).toHaveBeenCalledWith(undefined, false);
    elsewhere.unmount();

    dialog({ attendees: [] });
    expect(screen.queryByRole('checkbox')).toBeNull();
  });

  it('deletes once however many clicks reach it, and closes on cancel', async () => {
    let finish: () => void = () => undefined;
    const { user, onDelete, onClose } = dialog();
    onDelete.mockImplementation(() => new Promise<void>(resolve => (finish = resolve)));
    const remove = screen.getByRole('button', { name: 'workbench.calendar.delete' });

    // A double tap lands both clicks before the button can say it is busy.
    act(() => {
      remove.click();
      remove.click();
    });
    await user.click(remove);
    finish();

    expect(onDelete).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole('button', { name: 'common.cancel' }));
    expect(onClose).toHaveBeenCalled();
  });

  it('can be tried again once a refused deletion has come back', async () => {
    // The tool says the refusal and keeps the dialog open: the act settles.
    const { user, onDelete } = dialog();
    const remove = screen.getByRole('button', { name: 'workbench.calendar.delete' });

    await user.click(remove);
    await waitFor(() => expect(remove).not.toHaveAttribute('aria-busy'));
    await user.click(remove);

    expect(onDelete).toHaveBeenCalledTimes(2);
  });
});
