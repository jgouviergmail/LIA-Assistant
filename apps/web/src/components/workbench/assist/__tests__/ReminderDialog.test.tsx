/**
 * « Remind me » from a tool (lot 1): the words are the person's to change, a moment is a press
 * away and always shown, and what is sent is what the dialog says. Nothing typed is ever lost to a
 * refusal.
 */
import { fireEvent } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { post, success } = vi.hoisted(() => ({ post: vi.fn(), success: vi.fn() }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { post },
}));
vi.mock('sonner', () => ({ toast: { success, error: vi.fn() } }));

import { ReminderDialog } from '../ReminderDialog';

const NOW = new Date('2026-11-04T09:00:00Z');
const ZONE = 'Europe/Paris';
const CHOICE = 'workbench.assist.remind.choices.';

function draw(onClose = vi.fn()) {
  const rendered = renderWithProviders(
    <ReminderDialog lng="en" words="Call Ana back" zone={ZONE} onClose={onClose} />
  );
  return { ...rendered, onClose };
}

function moment(): HTMLInputElement {
  return screen.getByLabelText('workbench.assist.remind.when');
}

beforeEach(() => {
  post.mockReset();
  post.mockResolvedValue({ id: 'r1' });
  success.mockReset();
  vi.useFakeTimers({ now: NOW, toFake: ['Date'] });
});

afterEach(() => {
  vi.useRealTimers();
});

describe('ReminderDialog', () => {
  it('opens on the words and on tomorrow morning, shown in the field', () => {
    draw();

    expect(screen.getByLabelText('workbench.assist.remind.what')).toHaveValue('Call Ana back');
    expect(moment()).toHaveValue('2026-11-05T09:00');
    expect(screen.getByRole('button', { name: `${CHOICE}tomorrow` })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
  });

  it('opens on its act, so a phone’s keyboard stays down', async () => {
    draw();

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'workbench.assist.remind.submit' })).toHaveFocus()
    );
  });

  it('moves the moment by one press, and the field says so', async () => {
    const { user } = draw();

    await user.click(screen.getByRole('button', { name: `${CHOICE}evening` }));

    expect(moment()).toHaveValue('2026-11-04T18:00');
    expect(screen.getByRole('button', { name: `${CHOICE}evening` })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
  });

  it('sends the words and the wall clock, says it, and closes', async () => {
    const { user, onClose } = draw();

    await user.click(screen.getByRole('button', { name: 'workbench.assist.remind.submit' }));

    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(post).toHaveBeenCalledWith('/reminders', {
      content: 'Call Ana back',
      original_message: 'Call Ana back',
      trigger_at: '2026-11-05T09:00:00',
    });
    expect(success).toHaveBeenCalledWith('workbench.assist.remind.done');
  });

  it('sends the words the person changed', async () => {
    const { user } = draw();
    const words = screen.getByLabelText('workbench.assist.remind.what');

    await user.clear(words);
    await user.type(words, 'Pay the invoice');
    await user.click(screen.getByRole('button', { name: 'workbench.assist.remind.submit' }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][1]).toMatchObject({
      content: 'Pay the invoice',
      original_message: 'Pay the invoice',
    });
  });

  it('sends nothing for a moment already gone, and says why', async () => {
    const { user, onClose } = draw();

    fireEvent.change(moment(), { target: { value: '2026-11-04T09:00' } });
    await user.click(screen.getByRole('button', { name: 'workbench.assist.remind.submit' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('workbench.assist.remind.past');
    expect(post).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });

  it('sends nothing without words', async () => {
    const { user } = draw();

    await user.clear(screen.getByLabelText('workbench.assist.remind.what'));
    await user.click(screen.getByRole('button', { name: 'workbench.assist.remind.submit' }));

    expect(post).not.toHaveBeenCalled();
  });

  it('keeps what was typed when the reminder could not be made', async () => {
    post.mockRejectedValue(new Error('refused'));
    const { user, onClose } = draw();

    await user.click(screen.getByRole('button', { name: 'workbench.assist.remind.submit' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('workbench.assist.remind.failed');
    expect(screen.getByLabelText('workbench.assist.remind.what')).toHaveValue('Call Ana back');
    expect(onClose).not.toHaveBeenCalled();
  });

  it('never sends twice for a double press', async () => {
    let answer: (value: unknown) => void = () => undefined;
    post.mockReturnValue(new Promise(resolve => (answer = resolve)));
    const { user } = draw();
    const submit = screen.getByRole('button', { name: 'workbench.assist.remind.submit' });

    await user.click(submit);
    await user.click(submit);
    answer({ id: 'r1' });

    await waitFor(() => expect(success).toHaveBeenCalledTimes(1));
    expect(post).toHaveBeenCalledTimes(1);
  });
});
