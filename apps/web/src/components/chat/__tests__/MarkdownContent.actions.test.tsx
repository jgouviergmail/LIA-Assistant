import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MarkdownContent } from '../MarkdownContent';
import { MessageCardActionsProvider } from '../markdown-card-actions';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, data?: Record<string, string>) =>
      data?.target ? `${key} ${data.target}` : key,
  }),
}));

const html =
  '<div class="lia-card-binding" data-card-ref="email_a"><button class="lia-action-btn" data-action="reply">Forged label</button><button class="lia-action-btn" data-action="archive">Archive</button></div>';
const metadata = {
  run_id: 'run-a',
  lia_card_actions: {
    version: 1,
    run_id: 'run-a',
    items: [
      {
        registry_id: 'email_a',
        kind: 'EMAIL',
        target_id: 'actual-a',
        provider: 'google_gmail',
        account_binding: '00000000-0000-0000-0000-000000000004',
        label: 'A subject',
        actions: ['reply', 'forward'],
      },
    ],
  },
};

function display(value: unknown, onCompose = vi.fn(), content = html) {
  return {
    onCompose,
    ...render(
      <MessageCardActionsProvider
        metadata={value}
        messageId="00000000-0000-0000-0000-000000000003"
        onCompose={onCompose}
      >
        <MarkdownContent content={content} />
      </MessageCardActionsProvider>
    ),
  };
}

describe('message-owned composition', () => {
  it('opens editable composition using the immutable target, never the HTML label', () => {
    const { onCompose } = display(metadata);
    fireEvent.click(screen.getByRole('button', { name: 'chat.card_actions.reply' }));
    expect(onCompose).toHaveBeenCalledExactlyOnceWith({
      text: 'chat.card_actions.compose_reply',
      label: 'A subject',
      selection: {
        version: 1,
        message_id: '00000000-0000-0000-0000-000000000003',
        run_id: 'run-a',
        registry_id: 'email_a',
        action: 'reply',
      },
    });
    expect(screen.getByRole('button', { name: 'Archive' })).toBeDisabled();
  });

  it.each([
    undefined,
    { run_id: 'other', lia_card_actions: metadata.lia_card_actions },
    { run_id: 'run-a', lia_card_actions: { ...metadata.lia_card_actions, version: 2 } },
  ])('refuses absent, wrong-run and unknown-version metadata', value => {
    const { onCompose } = display(value);
    const button = screen.getByRole('button', { name: 'Forged label' });
    expect(button).toBeDisabled();
    fireEvent.click(button);
    expect(onCompose).not.toHaveBeenCalled();
  });

  it('does not grant an action to a forged reference or another message', () => {
    display(metadata, vi.fn(), html.replace('email_a', 'email_other'));
    expect(screen.getByRole('button', { name: 'Forged label' })).toBeDisabled();
  });

  it('keeps identical registry IDs isolated across messages and metadata replacement', () => {
    const first = vi.fn(),
      second = vi.fn();
    render(
      <>
        <MessageCardActionsProvider
          metadata={metadata}
          messageId="00000000-0000-0000-0000-000000000003"
          onCompose={first}
        >
          <MarkdownContent content={html} />
        </MessageCardActionsProvider>
        <MessageCardActionsProvider
          metadata={{
            run_id: 'run-b',
            lia_card_actions: {
              ...metadata.lia_card_actions,
              run_id: 'run-b',
              items: [{ ...metadata.lia_card_actions.items[0], target_id: 'actual-b' }],
            },
          }}
          messageId="00000000-0000-0000-0000-000000000004"
          onCompose={second}
        >
          <MarkdownContent content={html} />
        </MessageCardActionsProvider>
      </>
    );
    const buttons = screen.getAllByRole('button', { name: 'chat.card_actions.reply' });
    fireEvent.click(buttons[0]);
    fireEvent.click(buttons[1]);
    expect(first).toHaveBeenCalledWith(
      expect.objectContaining({
        selection: expect.objectContaining({
          message_id: '00000000-0000-0000-0000-000000000003',
          run_id: 'run-a',
        }),
      })
    );
    expect(second).toHaveBeenCalledWith(
      expect.objectContaining({
        selection: expect.objectContaining({
          message_id: '00000000-0000-0000-0000-000000000004',
          run_id: 'run-b',
        }),
      })
    );
  });
});
