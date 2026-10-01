/**
 * EmailShareDialog — one file or one answer, a subject, optional words, one click.
 *
 * What is pinned: the three states that must not be confused (still checking,
 * a read that failed, no road at all), the two roads (free recipients from the
 * mailbox; the account's own address, locked, on the relay), the payload the
 * API receives, the published bounds the form obeys before the server has to,
 * and every refusal reaching the reader in their words — never as a raw code.
 */

import { fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { ApiError } from '@/lib/api-client';
import type { EmailShareOptions, EmailShareSource } from '@/lib/email-share/share';

const { query } = vi.hoisted(() => ({ query: vi.fn() }));
vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery: query }));

const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { post },
}));

const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

// The pause before a query is asked is `useDebounce`'s own, tested with it.
vi.mock('@/hooks/useDebounce', () => ({ useDebounce: <T,>(value: T) => value }));

import { EmailShareDialog } from '../EmailShareDialog';

const MAILBOX: EmailShareOptions = {
  route: 'mailbox',
  own_address: null,
  mailbox_needs_reconnect: false,
  max_file_bytes: 3_000_000,
  max_recipients: 10,
  subject_max_chars: 200,
  message_max_chars: 5000,
  recipient_suggestions: false,
  recipient_query_min_chars: 2,
  recipient_suggestions_max: 8,
};

const RELAY: EmailShareOptions = { ...MAILBOX, route: 'relay', own_address: 'me@example.com' };

const FILE: EmailShareSource = { kind: 'file', attachmentId: 'att-1', name: 'plan.pdf' };

function answer(options: Partial<{ data: EmailShareOptions; loading: boolean; error: Error }>) {
  query.mockReturnValue({
    data: options.data,
    loading: options.loading ?? false,
    error: options.error ?? null,
    refetch: vi.fn(),
  });
}

function renderDialog(source: EmailShareSource = FILE, defaultSubject = 'plan.pdf') {
  const onOpenChange = vi.fn();
  renderWithProviders(
    <EmailShareDialog
      open
      onOpenChange={onOpenChange}
      source={source}
      defaultSubject={defaultSubject}
    />
  );
  return { onOpenChange };
}

const sendButton = () => screen.getByRole('button', { name: 'email_share.send' });

function typeRecipients(value: string) {
  fireEvent.change(screen.getByLabelText('email_share.to_label'), { target: { value } });
}

beforeEach(() => {
  vi.clearAllMocks();
  post.mockResolvedValue({ route: 'mailbox', recipients: 1 });
});

describe('EmailShareDialog — before the road is known', () => {
  it('says it is checking, and offers nothing to send yet', () => {
    answer({ loading: true });
    renderDialog();

    expect(screen.getByRole('status')).toHaveTextContent('email_share.loading');
    expect(sendButton()).toBeDisabled();
  });

  it('says the check failed, never that there is no way to send', () => {
    answer({ error: new Error('503') });
    renderDialog();

    expect(screen.getByRole('alert')).toHaveTextContent('email_share.load_error');
    expect(screen.queryByText(/email_share\.unavailable/)).not.toBeInTheDocument();
  });

  it('explains where to go when there is truly no road', () => {
    answer({ data: { ...MAILBOX, route: 'unavailable', max_file_bytes: null } });
    renderDialog();

    expect(screen.getByText(/email_share\.unavailable/)).toBeInTheDocument();
    expect(sendButton()).toBeDisabled();
  });
});

describe('EmailShareDialog — from the connected mailbox', () => {
  it('sends the file to the typed recipients under the proposed subject', async () => {
    answer({ data: MAILBOX });
    const { onOpenChange } = renderDialog();

    typeRecipients('bob@example.com, eve@example.com');
    fireEvent.click(sendButton());

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/email-share', {
        recipients: ['bob@example.com', 'eve@example.com'],
        subject: 'plan.pdf',
        message: null,
        attachment: { kind: 'file', attachment_id: 'att-1' },
      })
    );
    expect(toast.success).toHaveBeenCalledWith('email_share.sent');
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('names what is not an address and holds the send', () => {
    answer({ data: MAILBOX });
    renderDialog();

    typeRecipients('bob');

    expect(screen.getByText(/email_share\.to_invalid/)).toBeInTheDocument();
    expect(sendButton()).toBeDisabled();
  });

  it('holds a send with no recipient', () => {
    answer({ data: MAILBOX });
    renderDialog();

    expect(sendButton()).toBeDisabled();
  });
});

describe('EmailShareDialog — through the relay', () => {
  it('writes to the account itself: no field to fill, no recipient sent', async () => {
    answer({ data: RELAY });
    post.mockResolvedValue({ route: 'relay', recipients: 1 });
    renderDialog();

    expect(screen.queryByLabelText('email_share.to_label')).not.toBeInTheDocument();
    expect(screen.getByText(/email_share\.to_self/)).toBeInTheDocument();
    fireEvent.click(sendButton());

    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(post.mock.calls[0][1].recipients).toEqual([]);
    expect(toast.success).toHaveBeenCalledWith('email_share.sent_to_self');
  });

  it('says a broken mailbox is why it goes to the account itself', () => {
    answer({ data: { ...RELAY, mailbox_needs_reconnect: true } });
    renderDialog();

    expect(screen.getByText(/email_share\.reconnect_hint/)).toBeInTheDocument();
  });
});

describe('EmailShareDialog — bounds and refusals', () => {
  it('refuses a file heavier than the road before asking the server', () => {
    answer({ data: { ...MAILBOX, max_file_bytes: 3 } });
    renderDialog({ kind: 'markdown', filename: 'lia-x', text: 'more than three bytes' });

    expect(screen.getByRole('alert')).toHaveTextContent('email_share.too_large');
    expect(sendButton()).toBeDisabled();
  });

  it('proposes a subject within the published bound', () => {
    answer({ data: { ...MAILBOX, subject_max_chars: 5 } });
    renderDialog(FILE, 'a very long image prompt');

    expect(screen.getByLabelText('email_share.subject_label')).toHaveValue('a ver');
  });

  it.each([
    [413, { code: 'email_share_too_large', max_bytes: 3 }, 'email_share.errors.too_large'],
    [409, { code: 'email_share_mailbox_reconnect' }, 'email_share.errors.mailbox_reconnect'],
    [429, 'Rate limit exceeded', 'email_share.errors.rate_limited'],
    [500, 'boom', 'email_share.errors.generic'],
  ])('a %s refusal is said in words, and the dialog stays open', async (status, detail, key) => {
    answer({ data: MAILBOX });
    post.mockRejectedValue(new ApiError('refused', status, { detail }));
    const { onOpenChange } = renderDialog();

    typeRecipients('bob@example.com');
    fireEvent.click(sendButton());

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(key));
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });
});

describe('EmailShareDialog — contact suggestions', () => {
  const SUGGESTING: EmailShareOptions = { ...MAILBOX, recipient_suggestions: true };
  const JEAN = { name: 'Jean Dupont', email: 'jean@example.org' };
  const JEANNE = { name: 'Jeanne Martin', email: 'jeanne@example.org' };

  /** The options, and a suggestion answer to whatever is asked (or a fixed one). */
  function suggest(
    found: { name: string; email: string }[],
    { answersQuery, truncated = false }: { answersQuery?: string; truncated?: boolean } = {}
  ) {
    query.mockImplementation(
      (endpoint: string, options: { enabled?: boolean; params?: { q?: string } }) => {
        if (endpoint === '/email-share/recipients') {
          return {
            data: options.enabled
              ? { query: answersQuery ?? options.params?.q, suggestions: found, truncated }
              : undefined,
            loading: false,
            error: null,
            refetch: vi.fn(),
          };
        }
        return { data: SUGGESTING, loading: false, error: null, refetch: vi.fn() };
      }
    );
  }

  const field = () => screen.getByRole('combobox', { name: 'email_share.to_label' });

  it('asks for the recipient being typed and puts the picked address in the field', async () => {
    suggest([JEAN, JEANNE]);
    const { user } = renderWithProviders(
      <EmailShareDialog open onOpenChange={vi.fn()} source={FILE} defaultSubject="plan.pdf" />
    );

    await user.type(field(), 'jea');

    expect(query).toHaveBeenCalledWith(
      '/email-share/recipients',
      expect.objectContaining({ enabled: true, params: { q: 'jea' } })
    );
    expect(screen.getByRole('listbox', { name: 'email_share.suggestions_label' })).toBeVisible();
    await user.keyboard('{ArrowDown}{ArrowDown}{Enter}');

    expect(field()).toHaveValue('jeanne@example.org, ');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('enter picks nothing the person did not move to', async () => {
    suggest([JEAN]);
    const { user } = renderWithProviders(
      <EmailShareDialog open onOpenChange={vi.fn()} source={FILE} defaultSubject="plan.pdf" />
    );

    await user.type(field(), 'jea{Enter}');

    expect(field()).toHaveValue('jea');
  });

  it('a pick by pointer keeps the focus in the field', async () => {
    suggest([JEAN]);
    const { user } = renderWithProviders(
      <EmailShareDialog open onOpenChange={vi.fn()} source={FILE} defaultSubject="plan.pdf" />
    );
    await user.type(field(), 'jea');

    await user.click(screen.getByRole('option', { name: /jean@example\.org/ }));

    expect(field()).toHaveValue('jean@example.org, ');
    expect(field()).toHaveFocus();
  });

  it('escape closes the list, not the dialog', async () => {
    suggest([JEAN]);
    const onOpenChange = vi.fn();
    const { user } = renderWithProviders(
      <EmailShareDialog open onOpenChange={onOpenChange} source={FILE} defaultSubject="plan.pdf" />
    );
    await user.type(field(), 'jea');

    await user.keyboard('{Escape}');

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(onOpenChange).not.toHaveBeenCalled();
    expect(field()).toHaveValue('jea');
  });

  it('never offers an address already in the field', async () => {
    suggest([JEAN, JEANNE]);
    const { user } = renderWithProviders(
      <EmailShareDialog open onOpenChange={vi.fn()} source={FILE} defaultSubject="plan.pdf" />
    );

    await user.type(field(), 'jean@example.org, jea');

    const options = screen.getAllByRole('option');
    expect(options).toHaveLength(1);
    expect(options[0]).toHaveTextContent('jeanne@example.org');
  });

  it('never shows the answer to an older query', async () => {
    suggest([JEAN], { answersQuery: 'je' });
    const { user } = renderWithProviders(
      <EmailShareDialog open onOpenChange={vi.fn()} source={FILE} defaultSubject="plan.pdf" />
    );

    await user.type(field(), 'jea');

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('says when only part of the address book is searched', async () => {
    suggest([JEAN], { truncated: true });
    const { user } = renderWithProviders(
      <EmailShareDialog open onOpenChange={vi.fn()} source={FILE} defaultSubject="plan.pdf" />
    );

    await user.type(field(), 'jea');

    expect(screen.getByText('email_share.suggestions_truncated')).toBeVisible();
    expect(screen.getByRole('status', { name: '' })).toHaveTextContent(
      'email_share.suggestions_count'
    );
  });

  it('asks nothing below the published minimum', async () => {
    suggest([JEAN]);
    const { user } = renderWithProviders(
      <EmailShareDialog open onOpenChange={vi.fn()} source={FILE} defaultSubject="plan.pdf" />
    );

    await user.type(field(), 'j');

    expect(query).not.toHaveBeenCalledWith(
      '/email-share/recipients',
      expect.objectContaining({ enabled: true })
    );
  });

  it('does not call a name being typed a wrong address until the field is left', async () => {
    suggest([]);
    const { user } = renderWithProviders(
      <EmailShareDialog open onOpenChange={vi.fn()} source={FILE} defaultSubject="plan.pdf" />
    );

    await user.type(field(), 'lef');
    expect(screen.queryByText('email_share.to_invalid')).not.toBeInTheDocument();
    expect(sendButton()).toBeDisabled();

    await user.tab();
    expect(screen.getByText('email_share.to_invalid')).toBeInTheDocument();
  });

  it('is a plain address field when no suggestion is published', () => {
    answer({ data: MAILBOX });
    renderDialog();

    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    expect(screen.getByLabelText('email_share.to_label')).toBeInTheDocument();
  });
});
