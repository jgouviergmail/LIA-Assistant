/**
 * Handing a thing to LIA (lot 5): a ticket like any other, its words filled and still the person's
 * to change. Nothing leaves before the press, and a refusal keeps what they wrote.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { create, success } = vi.hoisted(() => ({ create: vi.fn(), success: vi.fn() }));
vi.mock('@/lib/workboard/api', () => ({ workboardApi: { create } }));
vi.mock('sonner', () => ({ toast: { success } }));
vi.mock('@/i18n/client', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

import { ApiError } from '@/lib/api-client';

import { ConfideDialog } from '../ConfideDialog';

const SUBMIT = 'workbench.assist.confide.submit';

function dialog() {
  const onClose = vi.fn();
  render(<ConfideDialog lng="en" title="Budget" brief="Deal with it." onClose={onClose} />);
  return { user: userEvent.setup(), onClose };
}

beforeEach(() => {
  vi.clearAllMocks();
  create.mockResolvedValue({ id: 'ticket' });
});

describe('ConfideDialog', () => {
  it('creates the ticket for LIA with the words as they stand', async () => {
    const { user, onClose } = dialog();
    expect(create).not.toHaveBeenCalled();

    const brief = screen.getByLabelText('workbench.assist.confide.brief');
    await user.clear(brief);
    await user.type(brief, 'Answer before Friday');
    await user.click(screen.getByRole('button', { name: SUBMIT }));

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(create).toHaveBeenCalledExactlyOnceWith({
      title: 'Budget',
      description: 'Answer before Friday',
      assignee: 'lia',
    });
    expect(success).toHaveBeenCalledWith('workbench.assist.confide.done');
  });

  it('sends no empty brief, and no ticket without a name', async () => {
    const { user } = dialog();

    await user.clear(screen.getByLabelText('workbench.assist.confide.brief'));
    const name = screen.getByLabelText('workbench.assist.confide.name');
    await user.clear(name);
    await user.click(screen.getByRole('button', { name: SUBMIT }));
    expect(create).not.toHaveBeenCalled();

    await user.type(name, 'Mine');
    await user.click(screen.getByRole('button', { name: SUBMIT }));
    await waitFor(() =>
      expect(create).toHaveBeenCalledWith({
        title: 'Mine',
        description: null,
        assignee: 'lia',
      })
    );
  });

  it('says the board’s refusal in its words and keeps what was written', async () => {
    create.mockRejectedValueOnce(
      new ApiError('refused', 422, { detail: 'workboard_title_too_long' })
    );
    const { user, onClose } = dialog();

    await user.click(screen.getByRole('button', { name: SUBMIT }));

    expect(await screen.findByRole('alert')).toHaveTextContent('workboard.errors.title_too_long');
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByLabelText('workbench.assist.confide.name')).toHaveValue('Budget');
  });

  it('falls back on the board’s plain words for a failure with no code', async () => {
    create.mockRejectedValueOnce(new Error('network'));
    const { user } = dialog();

    await user.click(screen.getByRole('button', { name: SUBMIT }));

    expect(await screen.findByRole('alert')).toHaveTextContent('workboard.errors.generic');
  });

  it('makes one ticket of a double press', async () => {
    let answer = (_value: unknown) => {};
    create.mockReturnValueOnce(new Promise(resolve => (answer = resolve)));
    const { user, onClose } = dialog();

    const submit = screen.getByRole('button', { name: SUBMIT });
    await user.dblClick(submit);
    answer({ id: 'ticket' });

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(create).toHaveBeenCalledOnce();
  });

  it('opens on the press, not on a field: a phone keeps its keyboard down', async () => {
    dialog();

    await waitFor(() => expect(screen.getByRole('button', { name: SUBMIT })).toHaveFocus());
  });
});
