/**
 * RemindersCard — reading a reminder, and cancelling exactly that one.
 *
 * The card used to open the chat and nothing else: cancelling meant asking in
 * prose, and the agent resolves its target from a content substring — two
 * reminders worded alike and the wrong one goes.
 *
 * "Cancel" is a deletion, so it still asks before acting. The confirmation
 * simply moved to where the reader already is, instead of a chat round-trip.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { mutate } = vi.hoisted(() => ({ mutate: vi.fn(async () => {}) }));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation: () => ({ mutate }) }));

const { openChat } = vi.hoisted(() => ({ openChat: vi.fn() }));
vi.mock('@/lib/chat-deep-link', () => ({ openChatDeepLink: openChat }));

const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { RemindersCard } from '../RemindersCard';
import type { CardSection, RemindersData, ReminderItem } from '@/types/briefing';

const REMINDER_ID = '11111111-1111-4111-8111-111111111111';

function reminder(over: Partial<ReminderItem> = {}): ReminderItem {
  return { id: REMINDER_ID, content: 'Appeler le plombier', trigger_at_local: '14:30', ...over };
}

function section(items: ReminderItem[]): CardSection<RemindersData> {
  return {
    status: 'ok',
    data: { items },
    generated_at: '2026-08-03T08:00:00Z',
    error_code: null,
    error_message: null,
    from_cache: false,
    stale_generated_at: null,
    last_attempt_at: null,
  };
}

const props = { isRefreshing: false, onRefresh: vi.fn(), staggerIndex: 0 };
const CANCEL = 'dashboard.briefing.actions.cancel_reminder';

beforeEach(() => vi.clearAllMocks());

describe('RemindersCard — cancelling', () => {
  it('offers a named cancel action per reminder', () => {
    renderWithProviders(<RemindersCard {...props} section={section([reminder()])} />);

    expect(screen.getByRole('button', { name: CANCEL })).toBeInTheDocument();
  });

  it('asks before deleting, and deletes nothing on the first press', async () => {
    const { user } = renderWithProviders(
      <RemindersCard {...props} section={section([reminder()])} />
    );

    await user.click(screen.getByRole('button', { name: CANCEL }));

    expect(await screen.findByRole('alertdialog')).toBeInTheDocument();
    expect(mutate).not.toHaveBeenCalled();
  });

  it('cancels the reminder by ID once confirmed', async () => {
    const onRefresh = vi.fn();
    const { user } = renderWithProviders(
      <RemindersCard {...props} onRefresh={onRefresh} section={section([reminder()])} />
    );

    await user.click(screen.getByRole('button', { name: CANCEL }));
    await user.click(await screen.findByRole('button', { name: 'common.confirm' }));

    await waitFor(() => expect(mutate).toHaveBeenCalledWith(`/reminders/${REMINDER_ID}`));
    // The card reloads from the server rather than guessing the new list.
    await waitFor(() => expect(onRefresh).toHaveBeenCalled());
  });

  it('keeps the reminder when the reader backs out', async () => {
    const { user } = renderWithProviders(
      <RemindersCard {...props} section={section([reminder()])} />
    );

    await user.click(screen.getByRole('button', { name: CANCEL }));
    await user.click(await screen.findByRole('button', { name: 'common.cancel' }));

    expect(mutate).not.toHaveBeenCalled();
    expect(screen.getByText('Appeler le plombier')).toBeInTheDocument();
  });

  it('reports a refused cancellation instead of pretending it worked', async () => {
    mutate.mockRejectedValueOnce(new Error('boom'));
    const { user } = renderWithProviders(
      <RemindersCard {...props} section={section([reminder()])} />
    );

    await user.click(screen.getByRole('button', { name: CANCEL }));
    await user.click(await screen.findByRole('button', { name: 'common.confirm' }));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
  });

  it('offers no cancel on a row whose id is unknown', () => {
    // Cached payloads predate the field. Offering an action we cannot target
    // exactly is precisely the ambiguity this replaces.
    renderWithProviders(<RemindersCard {...props} section={section([reminder({ id: null })])} />);

    expect(screen.queryByRole('button', { name: CANCEL })).not.toBeInTheDocument();
    // …but the reminder itself still reads, and still opens the chat.
    expect(screen.getByText('Appeler le plombier')).toBeInTheDocument();
  });
});

describe('RemindersCard — reading', () => {
  it('still opens the chat from the reminder itself', async () => {
    const { user } = renderWithProviders(
      <RemindersCard {...props} section={section([reminder()])} />
    );

    await user.click(screen.getByRole('button', { name: 'dashboard.briefing.intents.reminder_aria' }));

    expect(openChat).toHaveBeenCalled();
  });
});

describe('where the keyboard lands once the reminder is gone', () => {
  // Cancelling removes the row the reader was standing on. Radix returns focus
  // to the trigger it opened from — which no longer exists — so the keyboard
  // user is dropped on <body> and has to tab back through the whole page.
  // Measured before the fix: `document.activeElement === document.body`.
  it('returns focus to the card, not to the top of the document', async () => {
    const onRefresh = vi.fn();
    const { user } = renderWithProviders(
      <RemindersCard
        section={section([
          { id: 'r1', content: 'Appeler le dentiste', trigger_at_local: '14:00' },
          { id: 'r2', content: 'Sortir le chien', trigger_at_local: '18:00' },
        ])}
        isRefreshing={false}
        onRefresh={onRefresh}
      />
    );

    await user.click(
      screen.getAllByRole('button', { name: 'dashboard.briefing.actions.cancel_reminder' })[0]
    );
    await user.click(screen.getByText('common.confirm'));

    await waitFor(() => expect(onRefresh).toHaveBeenCalled());

    await waitFor(() => {
      expect(document.activeElement).not.toBe(document.body);
      // The card's own named region: it survives every state this card can
      // reach, including the empty one it lands in when the last reminder
      // goes — which is precisely when a row-based anchor would vanish too.
      expect(document.activeElement).toHaveAttribute('role', 'region');
    });
  });
});
