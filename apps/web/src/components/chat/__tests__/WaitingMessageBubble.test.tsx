/**
 * The waiting message's bubble: what it says and what it lets the person do (ADR-384).
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { createInstance } from 'i18next';

import { WaitingMessageBubble, type WaitingMessageBubbleProps } from '../WaitingMessageBubble';
import type { WaitingMessage } from '@/lib/waiting-message';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';

const i18n = createInstance();
await i18n.init({
  lng: 'en',
  interpolation: { escapeValue: false },
  resources: { en: { translation: en }, fr: { translation: fr } },
});
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: i18n.t, i18n }) }));

function waiting(overrides: Partial<WaitingMessage> = {}): WaitingMessage {
  return {
    conversation_id: 'c1',
    conversation_revision: 0,
    content: 'And the bakery',
    status: 'waiting',
    version: 1,
    send_requested: false,
    stream_id: null,
    can_join: false,
    created_at: '2026-11-13T15:00:00Z',
    updated_at: '2026-11-13T15:00:00Z',
    ...overrides,
  };
}

function props(overrides: Partial<WaitingMessageBubbleProps> = {}): WaitingMessageBubbleProps {
  return {
    message: waiting(),
    questionPending: false,
    pending: false,
    onEdit: vi.fn(async () => true),
    onWithdraw: vi.fn(),
    onSendNow: vi.fn(),
    onJoin: vi.fn(),
    ...overrides,
  };
}

describe('WaitingMessageBubble', () => {
  it('shows the words and says they leave once LIA is done', async () => {
    await i18n.changeLanguage('en');
    render(<WaitingMessageBubble {...props()} />);
    const group = screen.getByRole('group', { name: 'Waiting message' });
    expect(group).toHaveTextContent('And the bakery');
    expect(screen.getByText('Will be sent as soon as LIA is done.')).toHaveAttribute(
      'aria-live',
      'polite'
    );
  });

  it('names its actions in French too', async () => {
    await i18n.changeLanguage('fr');
    render(<WaitingMessageBubble {...props()} />);
    expect(screen.getByRole('group', { name: 'Message en attente' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Modifier' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retirer' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Envoyer maintenant' })).toBeInTheDocument();
    await i18n.changeLanguage('en');
  });

  it('sends now and withdraws on click', async () => {
    const onSendNow = vi.fn();
    const onWithdraw = vi.fn();
    render(<WaitingMessageBubble {...props({ onSendNow, onWithdraw })} />);
    await userEvent.click(screen.getByRole('button', { name: 'Send now' }));
    await userEvent.click(screen.getByRole('button', { name: 'Withdraw' }));
    expect(onSendNow).toHaveBeenCalledOnce();
    expect(onWithdraw).toHaveBeenCalledOnce();
  });

  it('never offers to send it as the answer to a pending question', () => {
    render(<WaitingMessageBubble {...props({ questionPending: true })} />);
    expect(screen.queryByRole('button', { name: 'Send now' })).not.toBeInTheDocument();
    expect(screen.getByText('Will be sent after you answer the question.')).toBeInTheDocument();
  });

  it('says a held message did not leave', () => {
    render(<WaitingMessageBubble {...props({ message: waiting({ status: 'held' }) })} />);
    expect(
      screen.getByText('Not sent yet: the previous exchange did not end normally.')
    ).toBeInTheDocument();
  });

  it('offers nothing while it is being sent', () => {
    render(
      <WaitingMessageBubble
        {...props({ message: waiting({ status: 'departing', stream_id: 's' }) })}
      />
    );
    expect(screen.queryAllByRole('button')).toHaveLength(0);
    expect(screen.getByText('Sending…')).toBeInTheDocument();
  });

  it('edits with the keyboard and gives the focus back', async () => {
    const onEdit = vi.fn(async () => true);
    render(<WaitingMessageBubble {...props({ onEdit })} />);
    const editButton = screen.getByRole('button', { name: 'Edit' });
    await userEvent.click(editButton);
    const field = screen.getByRole('textbox', { name: 'Edit the waiting message' });
    expect(field).toHaveFocus();
    await userEvent.clear(field);
    await userEvent.type(field, 'The bakery only');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(onEdit).toHaveBeenCalledWith('The bakery only');
    await waitFor(() => expect(screen.getByRole('button', { name: 'Edit' })).toHaveFocus());
  });

  it('keeps the edit open when the server refuses it', async () => {
    const onEdit = vi.fn(async () => false);
    render(<WaitingMessageBubble {...props({ onEdit })} />);
    await userEvent.click(screen.getByRole('button', { name: 'Edit' }));
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(screen.getByRole('textbox', { name: 'Edit the waiting message' })).toBeInTheDocument();
  });

  it('cancels an edit with Escape', async () => {
    const onEdit = vi.fn(async () => true);
    render(<WaitingMessageBubble {...props({ onEdit })} />);
    await userEvent.click(screen.getByRole('button', { name: 'Edit' }));
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(onEdit).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Edit' })).toHaveFocus();
  });

  it('never brings back an edit begun before the message left and came back', async () => {
    const { rerender } = render(<WaitingMessageBubble {...props()} />);
    await userEvent.click(screen.getByRole('button', { name: 'Edit' }));
    expect(screen.getByRole('textbox')).toBeInTheDocument();
    rerender(
      <WaitingMessageBubble {...props({ message: waiting({ status: 'departing', stream_id: 's' }) })} />
    );
    rerender(<WaitingMessageBubble {...props({ message: waiting({ status: 'held' }) })} />);
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('offers to add it to the answer being written, and adds it on click (ADR-385)', async () => {
    const onJoin = vi.fn();
    render(<WaitingMessageBubble {...props({ message: waiting({ can_join: true }), onJoin })} />);
    await userEvent.click(screen.getByRole('button', { name: 'Add to the answer in progress' }));
    expect(onJoin).toHaveBeenCalledOnce();
  });

  it('names the offer in French too', async () => {
    await i18n.changeLanguage('fr');
    render(<WaitingMessageBubble {...props({ message: waiting({ can_join: true }) })} />);
    expect(
      screen.getByRole('button', { name: 'Ajouter à la réponse en cours' })
    ).toBeInTheDocument();
    await i18n.changeLanguage('en');
  });

  it('offers no join while the answer takes no note', () => {
    render(<WaitingMessageBubble {...props()} />);
    expect(
      screen.queryByRole('button', { name: 'Add to the answer in progress' })
    ).not.toBeInTheDocument();
  });

  it('says a joining note is read at the next step, and can still change', () => {
    render(
      <WaitingMessageBubble
        {...props({ message: waiting({ status: 'joining', stream_id: 's' }) })}
      />
    );
    expect(
      screen.getByText(
        'LIA will read it at its next step. If it finishes first, it will be sent right after.'
      )
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Edit' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Withdraw' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Send now' })).not.toBeInTheDocument();
  });

  it('guards a repeated click while a request is on its way', async () => {
    const onSendNow = vi.fn();
    render(<WaitingMessageBubble {...props({ pending: true, onSendNow })} />);
    const button = screen.getByRole('button', { name: 'Send now' });
    expect(button).toHaveAttribute('aria-disabled', 'true');
    await userEvent.click(button);
    expect(onSendNow).not.toHaveBeenCalled();
  });
});
