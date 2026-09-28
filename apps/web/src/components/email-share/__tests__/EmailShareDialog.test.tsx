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

import { EmailShareDialog } from '../EmailShareDialog';

const MAILBOX: EmailShareOptions = {
  route: 'mailbox',
  own_address: null,
  mailbox_needs_reconnect: false,
  max_file_bytes: 3_000_000,
  max_recipients: 10,
  subject_max_chars: 200,
  message_max_chars: 5000,
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
