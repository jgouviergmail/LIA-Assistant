/**
 * Creating a ticket: what the form actually sends.
 *
 * The assignee field carries three different things through one list —
 * the two keywords the API understands (`me`, `lia`) and a connected peer's
 * ID — and sending the wrong shape is refused server-side with a code the
 * person would read as a bug. The other rules pinned here: an empty title is
 * guarded by the HANDLER (never by `disabled` on a focused control), and a
 * dismissed form does not keep the previous draft.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { TicketForm } from '@/components/workboard/TicketForm';
import type { TicketCreateBody } from '@/types/workboard';

const onCreate = vi.fn(async (_body: TicketCreateBody) => ({ ok: true }));
const onClose = vi.fn();

const PEERS = [{ peer_id: 'peer-1', peer_display_name: 'Marie' }];

function render(open = true) {
  return renderWithProviders(
    <TicketForm open={open} lng="fr" peers={PEERS} onClose={onClose} onCreate={onCreate} />
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('what it sends', () => {
  it('sends the keyword for me, and never an id', async () => {
    const { user } = render();
    await user.type(screen.getByLabelText('workboard.form.title'), 'Réserver la salle');
    await user.click(screen.getByRole('button', { name: 'workboard.actions.create' }));

    expect(onCreate).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Réserver la salle', assignee: 'me' })
    );
    expect(onCreate.mock.calls[0][0]).not.toHaveProperty('assignee_user_id');
  });

  it("stores a due DATE as the end of that day, in the reader's own zone", async () => {
    // Measured before this: `new Date('2026-09-15').toISOString()` is midnight
    // UTC, so the ticket was overdue at midday on its own due date, and a
    // reader west of Greenwich saw the day BEFORE the one they picked.
    const { user } = render();
    await user.type(screen.getByLabelText('workboard.form.title'), 'Réserver la salle');
    await user.type(screen.getByLabelText('workboard.form.due_at'), '2026-09-15');
    await user.click(screen.getByRole('button', { name: 'workboard.actions.create' }));

    const stored = onCreate.mock.calls[0][0].due_at as string;
    const instant = new Date(stored);
    // The day the person picked, read back the way the card reads it.
    expect(new Intl.DateTimeFormat('en-CA', { dateStyle: 'short' }).format(instant)).toBe(
      '2026-09-15'
    );
    // And still in the future at midday on that day.
    expect(instant.getTime()).toBeGreaterThan(new Date('2026-09-15T12:00:00').getTime());
  });

  it('sends no deadline at all when the field is left empty', async () => {
    const { user } = render();
    await user.type(screen.getByLabelText('workboard.form.title'), 'Sans échéance');
    await user.click(screen.getByRole('button', { name: 'workboard.actions.create' }));

    expect(onCreate.mock.calls[0][0].due_at).toBeNull();
  });

  it('sends the keyword for LIA', async () => {
    const { user } = render();
    await user.type(screen.getByLabelText('workboard.form.title'), 'Chercher un traiteur');
    await user.click(screen.getByRole('combobox', { name: 'workboard.form.assignee' }));
    await user.click(await screen.findByRole('option', { name: 'workboard.party.lia' }));
    await user.click(screen.getByRole('button', { name: 'workboard.actions.create' }));

    expect(onCreate).toHaveBeenCalledWith(expect.objectContaining({ assignee: 'lia' }));
  });

  it("sends a peer as an ID, because a peer's name is not a keyword", async () => {
    const { user } = render();
    await user.type(screen.getByLabelText('workboard.form.title'), 'Relire le devis');
    await user.click(screen.getByRole('combobox', { name: 'workboard.form.assignee' }));
    await user.click(await screen.findByRole('option', { name: 'Marie' }));
    await user.click(screen.getByRole('button', { name: 'workboard.actions.create' }));

    const body = onCreate.mock.calls[0][0];
    expect(body).toMatchObject({ assignee_user_id: 'peer-1' });
    expect(body).not.toHaveProperty('assignee');
  });

  it('trims the title and sends no description rather than an empty one', async () => {
    const { user } = render();
    await user.type(screen.getByLabelText('workboard.form.title'), '   Titre   ');
    await user.click(screen.getByRole('button', { name: 'workboard.actions.create' }));

    expect(onCreate).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Titre', description: null })
    );
  });

  it('carries the follow flag the person chose', async () => {
    const { user } = render();
    await user.type(screen.getByLabelText('workboard.form.title'), 'X');
    await user.click(screen.getByRole('switch', { name: 'workboard.form.follow' }));
    await user.click(screen.getByRole('button', { name: 'workboard.actions.create' }));

    expect(onCreate).toHaveBeenCalledWith(expect.objectContaining({ follow: true }));
  });
});

describe('what it refuses to send', () => {
  it('sends nothing at all without a title, and keeps the button focusable', async () => {
    // The guard is in the HANDLER: `disabled` on a focused control blurs it and
    // drops the keyboard user back on `<body>`.
    const { user } = render();
    const submit = screen.getByRole('button', { name: 'workboard.actions.create' });

    await user.click(submit);

    expect(onCreate).not.toHaveBeenCalled();
    expect(submit).toHaveAttribute('aria-disabled', 'true');
    expect(submit).not.toBeDisabled();
  });

  it('sends nothing for a title made only of spaces', async () => {
    const { user } = render();
    await user.type(screen.getByLabelText('workboard.form.title'), '    ');
    await user.click(screen.getByRole('button', { name: 'workboard.actions.create' }));

    expect(onCreate).not.toHaveBeenCalled();
  });
});

describe('closing it', () => {
  it('clears the draft, so the next ticket starts empty', async () => {
    const { user } = render();
    await user.type(screen.getByLabelText('workboard.form.title'), 'Un brouillon');
    await user.click(screen.getByRole('button', { name: 'workboard.actions.cancel' }));

    expect(onClose).toHaveBeenCalled();
    expect(screen.getByLabelText('workboard.form.title')).toHaveValue('');
  });
});
