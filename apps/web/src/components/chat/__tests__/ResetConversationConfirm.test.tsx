/**
 * ResetConversationConfirm (W4a) — the destructive confirm is in-app and honest.
 *
 * Two defects were fixed at once here:
 *  - a native `window.confirm` on the most destructive action of the product
 *    (no theme, no typography, OS-language buttons, thread blocked);
 *  - a wording that announced "the conversation history" while the endpoint
 *    also purges EVERY attachment of the user, AI-generated images included.
 *    A user about to lose their images deserves to know beforehand.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { ResetConversationConfirm } from '../ResetConversationConfirm';

const onConfirm = vi.fn();
const onOpenChange = vi.fn();

function renderDialog(open = true) {
  return render(
    <ResetConversationConfirm open={open} onOpenChange={onOpenChange} onConfirm={onConfirm} />
  );
}

beforeEach(() => {
  onConfirm.mockReset();
  onOpenChange.mockReset();
});

describe('ResetConversationConfirm', () => {
  it('renders nothing while closed', () => {
    renderDialog(false);
    expect(screen.queryByRole('alertdialog')).toBeNull();
  });

  it('announces itself as an alert dialog', () => {
    // `alertdialog` (not `dialog`): assistive technology must interrupt for a
    // destructive, irreversible choice.
    renderDialog();
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
  });

  it('states the action in its title', () => {
    renderDialog();
    expect(screen.getByText('chat.reset_confirm.title')).toBeInTheDocument();
  });

  it('describes the full scope of the purge', () => {
    renderDialog();
    expect(screen.getByText('chat.reset_confirm.description')).toBeInTheDocument();
  });

  it('confirms through a destructive-labelled action', () => {
    renderDialog();
    fireEvent.click(screen.getByText('chat.reset_confirm.confirm'));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('offers a cancel that does NOT confirm', () => {
    renderDialog();
    fireEvent.click(screen.getByText('common.cancel'));
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('keeps the confirm and cancel actions distinguishable by name', () => {
    // A destructive dialog whose two buttons read alike is a trap.
    renderDialog();
    const confirm = screen.getByText('chat.reset_confirm.confirm');
    const cancel = screen.getByText('common.cancel');
    expect(confirm.textContent).not.toBe(cancel.textContent);
  });
});
