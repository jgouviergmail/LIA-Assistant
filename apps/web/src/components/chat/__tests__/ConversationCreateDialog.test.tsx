import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ConversationCreateDialog, ConversationTitleDialog } from '../ConversationCreateDialog';
import type { ConversationCreateRequest } from '@/types/conversation';

const titleRules = { title_max_length: 6, title_pattern: '^[^\\x00]*$' };

describe('creating a discussion', () => {
  it('refuses an unreadable title and counts international characters as the API does', async () => {
    const create = vi.fn(async (_request: ConversationCreateRequest) => {});
    render(<ConversationCreateDialog rules={titleRules} onCreate={create} onClose={vi.fn()} />);
    const field = screen.getByRole('textbox', { name: 'chat.discussions.title_label' });
    const submit = screen.getByRole('button', { name: 'chat.discussions.create' });
    // Something was typed, and nobody can read it: not a request for an automatic title.
    fireEvent.change(field, { target: { value: ' ​ ' } });
    fireEvent.click(submit);
    expect(create).not.toHaveBeenCalled();
    expect(field).toHaveAccessibleDescription('chat.discussions.title_invalid');

    fireEvent.change(field, { target: { value: '🔭天文研究会' } });
    fireEvent.click(submit);
    await waitFor(() => expect(create).toHaveBeenCalledOnce());
    expect(create.mock.calls[0]?.[0].title).toBe('🔭天文研究会');
  });

  it.each(['', '  \t '])(
    'creates a discussion that will take its title from its first message when the field holds %j',
    async typed => {
      const create = vi.fn(async (_request: ConversationCreateRequest) => {});
      const close = vi.fn();
      render(<ConversationCreateDialog rules={titleRules} onCreate={create} onClose={close} />);
      const field = screen.getByRole('textbox', { name: 'chat.discussions.title_label' });
      // The field says so itself: an assistive technology must not announce it as required.
      expect(field).not.toBeRequired();
      fireEvent.change(field, { target: { value: typed } });
      fireEvent.click(screen.getByRole('button', { name: 'chat.discussions.create' }));

      await waitFor(() => expect(close).toHaveBeenCalledOnce());
      const request = create.mock.calls[0]?.[0];
      // No title is SENT: the API reads a blank one as an invalid title.
      expect(request).not.toHaveProperty('title');
      expect(request?.request_id).toEqual(expect.any(String));
    }
  );

  it('retries an untitled creation as the same attempt after losing the response', async () => {
    const create = vi
      .fn<(request: ConversationCreateRequest) => Promise<void>>()
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValueOnce(undefined);
    const close = vi.fn();
    render(<ConversationCreateDialog rules={titleRules} onCreate={create} onClose={close} />);
    const submit = screen.getByRole('button', { name: 'chat.discussions.create' });
    fireEvent.click(submit);
    await screen.findByText('chat.discussions.create_error');
    fireEvent.click(submit);
    await waitFor(() => expect(close).toHaveBeenCalledOnce());
    expect(create.mock.calls[1]?.[0]).toEqual(create.mock.calls[0]?.[0]);
  });

  it('keeps the title and retries the same attempt after losing the response', async () => {
    const create = vi.fn<(request: ConversationCreateRequest) => Promise<void>>()
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValueOnce(undefined);
    const close = vi.fn();
    render(<ConversationCreateDialog rules={titleRules} onCreate={create} onClose={close} />);
    const field = screen.getByRole('textbox', { name: 'chat.discussions.title_label' });
    fireEvent.change(field, { target: { value: ' Projet ' } });
    fireEvent.click(screen.getByRole('button', { name: 'chat.discussions.create' }));
    await screen.findByText('chat.discussions.create_error');
    expect(field).toHaveValue(' Projet ');
    expect(close).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'chat.discussions.create' }));
    await waitFor(() => expect(close).toHaveBeenCalledOnce());
    expect(create.mock.calls[1]?.[0]).toEqual(create.mock.calls[0]?.[0]);
  });

  it('starts a new attempt when the person types a title after an untitled one failed', async () => {
    const create = vi
      .fn<(request: ConversationCreateRequest) => Promise<void>>()
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValueOnce(undefined);
    render(<ConversationCreateDialog rules={titleRules} onCreate={create} onClose={vi.fn()} />);
    const submit = screen.getByRole('button', { name: 'chat.discussions.create' });
    fireEvent.click(submit);
    await screen.findByText('chat.discussions.create_error');
    fireEvent.change(screen.getByRole('textbox', { name: 'chat.discussions.title_label' }), {
      target: { value: 'Projet' },
    });
    fireEvent.click(submit);
    await waitFor(() => expect(create).toHaveBeenCalledTimes(2));
    // Other words are another creation: the server refuses a reused attempt.
    expect(create.mock.calls[1]?.[0].title).toBe('Projet');
    expect(create.mock.calls[1]?.[0].request_id).not.toBe(create.mock.calls[0]?.[0].request_id);
  });
});

describe('renaming a discussion', () => {
  it('still requires a title: an empty field is not a request for an automatic one', () => {
    const rename = vi.fn(async (_title: string) => {});
    render(
      <ConversationTitleDialog
        rules={titleRules}
        initialTitle="Projet"
        heading="chat.discussions.rename"
        description="chat.discussions.rename_description"
        actionLabel="chat.discussions.rename"
        onSubmitTitle={rename}
        onClose={vi.fn()}
        refusalKey={() => 'chat.discussions.rename_error'}
      />
    );
    const field = screen.getByRole('textbox', { name: 'chat.discussions.title_label' });
    expect(field).toBeRequired();
    fireEvent.change(field, { target: { value: '   ' } });
    fireEvent.click(screen.getByRole('button', { name: 'chat.discussions.rename' }));
    expect(rename).not.toHaveBeenCalled();
    expect(field).toHaveAccessibleDescription('chat.discussions.title_required');
  });
});
