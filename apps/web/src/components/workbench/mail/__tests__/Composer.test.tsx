/**
 * The composer's screen (ADR-369, Task 4.7) — what the person sees and does
 * around a send (the send's own rules, one key and an outcome nobody knows,
 * are `useComposer`'s, tested there): closing on words not sent nor saved asks
 * first and is refused while the message leaves; a reply says to whom it goes,
 * a forward what it carries; the copies show on demand (Bcc only where the
 * target has one); the files chosen are the files sent; a draft is offered
 * only where the provider keeps drafts.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  answerConfirmDialog,
  renderWithProviders,
  screen,
  waitFor,
  within,
} from '@/__tests__/test-utils';
import type { WorkbenchMailWriting } from '@/hooks/useWorkbenchMailWriting';
import { ApiError } from '@/lib/api-client';
import type { ComposerTarget } from '@/lib/workbench/mail-compose';
import type {
  AttachableFile,
  MailDraft,
  MailMessage,
  WorkbenchFeature,
} from '@/lib/workbench/types';

const { api, i18n } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  // One stable `t` that shows its values, so « to whom » and « how many » are read.
  i18n: {
    t: (key: string, values?: Record<string, string | number>) =>
      values ? `${key}(${Object.values(values).join('|')})` : key,
    i18n: { language: 'en' },
  },
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'owner' } }) }));
vi.mock('@/i18n/client', () => ({ useTranslation: () => i18n }));
vi.mock('@/hooks/useRecipientSuggestions', () => ({
  useRecipientSuggestions: () => ({ suggestions: [], truncated: false }),
}));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: api,
}));

import { Composer } from '../Composer';

const MESSAGE: MailMessage = {
  id: 'm1',
  thread_id: 't1',
  sender: { name: 'Ana', address: 'ana@example.org' },
  reply_to: [],
  to: [],
  cc: [],
  subject: 'Budget',
  received_at: null,
  is_read: true,
  is_starred: false,
  label_ids: [],
  body: 'Hello',
  attachments: [],
};

const FILE: AttachableFile = {
  id: 'f1',
  filename: 'report.pdf',
  mime_type: 'application/pdf',
  size: 2048,
  origin: 'upload',
  expires_at: null,
};

const DRAFT: MailDraft = {
  id: 'd1',
  revision: 'r1',
  to: [{ name: 'Bob', address: 'bob@example.org' }],
  cc: [{ name: '', address: 'cc@example.org' }],
  bcc: [],
  subject: 'Plan',
  body: 'Draft words',
  attachments: [],
  updated_at: null,
};

function writing(): WorkbenchMailWriting {
  return {
    send: vi.fn().mockResolvedValue({ id: 's1', thread_id: 't1' }),
    reply: vi.fn().mockResolvedValue({ id: 's2', thread_id: 't1' }),
    forward: vi.fn().mockResolvedValue({ id: 's3', thread_id: 't1' }),
    saveDraft: vi.fn().mockResolvedValue({ ...DRAFT, id: 'd2', revision: 'r2' }),
    sendDraft: vi.fn().mockResolvedValue({ id: 's4', thread_id: 't1' }),
  };
}

function composer(
  target: ComposerTarget = { kind: 'new' },
  features: WorkbenchFeature[] = ['attachments', 'drafts']
) {
  const props = { writing: writing(), onClose: vi.fn(), onSent: vi.fn(), onDraftSaved: vi.fn() };
  const rendered = renderWithProviders(
    <Composer
      lng="en"
      target={target}
      tool={{
        tool: 'mail',
        state: 'ready',
        provider: 'google_gmail',
        features,
        bounds: {
          recipients_max: 50,
          attachments_max: 5,
          attachments_max_bytes: 10 * 1024 * 1024,
          subject_max_chars: 998,
          body_max_chars: 100_000,
        },
      }}
      {...props}
    />
  );
  return { ...rendered, ...props };
}

const cancel = () => screen.getByRole('button', { name: 'common.cancel' });
const body = () => screen.getByLabelText('workbench.mail.compose.body');

beforeEach(() => {
  vi.clearAllMocks();
  api.get.mockResolvedValue({ items: [FILE], total: 1, next_offset: null });
});

describe('Composer — closing', () => {
  it('closes at once on nothing written, and asks before dropping words', async () => {
    const empty = composer();
    await empty.user.click(cancel());
    expect(empty.onClose).toHaveBeenCalledTimes(1);
    empty.unmount();

    const { user, onClose } = composer();
    await user.type(body(), 'Half a thought');
    await user.click(cancel());
    await answerConfirmDialog(user, false);
    expect(onClose).not.toHaveBeenCalled();
    expect(body()).toHaveValue('Half a thought');

    await user.click(cancel());
    await answerConfirmDialog(user, true);
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  it('cannot be closed while the message leaves', async () => {
    const {
      user,
      onClose,
      writing: write,
    } = composer({ kind: 'reply', message: MESSAGE, all: false });
    vi.mocked(write.reply).mockImplementationOnce(() => new Promise(() => undefined));

    await user.type(body(), 'Thanks');
    await user.click(screen.getByRole('button', { name: 'workbench.mail.compose.send' }));
    await user.click(cancel());

    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe('Composer — what it writes', () => {
  it('says to whom a reply goes, its Reply-To first, and writes neither recipients nor subject', () => {
    const toReplyTo = composer({
      kind: 'reply',
      message: { ...MESSAGE, reply_to: [{ name: 'Help desk', address: 'desk@example.org' }] },
      all: false,
    });
    expect(
      screen.getByText('workbench.mail.compose.reply_line(Help desk|Budget)')
    ).toBeInTheDocument();
    expect(screen.queryByLabelText('workbench.mail.compose.to')).toBeNull();
    expect(screen.queryByLabelText('workbench.mail.compose.subject')).toBeNull();
    toReplyTo.unmount();

    composer({ kind: 'reply', message: MESSAGE, all: true });
    expect(screen.getByText('workbench.mail.compose.title_reply_all')).toBeInTheDocument();
    expect(
      screen.getByText('workbench.mail.compose.reply_all_line(Ana|Budget)')
    ).toBeInTheDocument();
  });

  it('says what a forward carries, and offers Cc without Bcc', async () => {
    const { user } = composer({
      kind: 'forward',
      message: {
        ...MESSAGE,
        attachments: [
          { id: 'a1', filename: 'a.pdf', mime_type: 'application/pdf', size: 1 },
          { id: 'a2', filename: 'b.pdf', mime_type: 'application/pdf', size: 1 },
        ],
      },
    });

    expect(screen.getByText('workbench.mail.compose.forward_files(Budget|2)')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'workbench.mail.compose.show_cc' }));
    expect(screen.getByLabelText('workbench.mail.compose.cc')).toBeInTheDocument();
    expect(screen.queryByLabelText('workbench.mail.compose.bcc')).toBeNull();
  });

  it('opens a draft with its copies shown, keeping its files as they are', () => {
    composer({
      kind: 'draft',
      draft: {
        ...DRAFT,
        attachments: [{ id: 'a1', filename: 'a.pdf', mime_type: 'application/pdf', size: 1 }],
      },
    });

    expect(screen.getByLabelText('workbench.mail.compose.cc')).toHaveValue('cc@example.org');
    expect(screen.getByLabelText('workbench.mail.compose.bcc')).toBeInTheDocument();
    expect(screen.getByText('workbench.mail.compose.draft_files(1)')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'workbench.mail.files.add' })).toBeNull();
  });
});

describe('Composer — files and drafts', () => {
  it('sends exactly the files chosen, after one taken back and chosen again', async () => {
    const { user, writing: write } = composer();
    await user.type(screen.getByLabelText('workbench.mail.compose.to'), 'bob@example.org');
    await user.type(screen.getByLabelText('workbench.mail.compose.subject'), 'Report');
    await user.type(body(), 'Attached.');

    await user.click(screen.getByRole('button', { name: 'workbench.mail.files.add' }));
    await user.click(
      await screen.findByRole('button', { name: 'workbench.mail.files.attach_named(report.pdf)' })
    );
    await user.keyboard('{Escape}');
    const chosen = await screen.findByRole('list', { name: 'workbench.mail.files.chosen' });
    expect(within(chosen).getByText('report.pdf')).toBeInTheDocument();
    await user.click(
      screen.getByRole('button', { name: 'workbench.mail.files.remove(report.pdf)' })
    );
    expect(screen.queryByRole('list', { name: 'workbench.mail.files.chosen' })).toBeNull();

    await user.click(screen.getByRole('button', { name: 'workbench.mail.files.add' }));
    const attach = await screen.findByRole('button', {
      name: 'workbench.mail.files.attach_named(report.pdf)',
    });
    // Pressed twice in the picker: taken back, then chosen again.
    await user.click(attach);
    await user.click(attach);
    expect(attach).toHaveAttribute('aria-pressed', 'false');
    await user.click(attach);
    expect(attach).toHaveAttribute('aria-pressed', 'true');
    await user.keyboard('{Escape}');
    await user.click(screen.getByRole('button', { name: 'workbench.mail.compose.send' }));

    await waitFor(() => expect(write.send).toHaveBeenCalledTimes(1));
    expect(vi.mocked(write.send).mock.calls[0][0]).toMatchObject({ attachment_ids: ['f1'] });
  });

  it('offers a draft only where the provider keeps drafts, and says it was saved', async () => {
    const withoutDrafts = composer({ kind: 'new' }, ['attachments']);
    expect(screen.queryByRole('button', { name: 'workbench.mail.compose.save_draft' })).toBeNull();
    withoutDrafts.unmount();

    const { user, writing: write, onDraftSaved } = composer();
    await user.type(body(), 'Later');
    await user.click(screen.getByRole('button', { name: 'workbench.mail.compose.save_draft' }));

    await waitFor(() => expect(onDraftSaved).toHaveBeenCalledTimes(1));
    expect(write.saveDraft).toHaveBeenCalledTimes(1);
    // A draft keeps no file: the files field leaves once the words are a draft.
    expect(screen.queryByRole('button', { name: 'workbench.mail.files.add' })).toBeNull();
  });

  it('says when nobody knows whether the message left, and sends nothing more', async () => {
    const { user, writing: write } = composer({ kind: 'reply', message: MESSAGE, all: false });
    vi.mocked(write.reply).mockRejectedValueOnce(
      new ApiError('lost', 504, { detail: { code: 'outcome_unknown' } })
    );
    const send = screen.getByRole('button', { name: 'workbench.mail.compose.send' });

    await user.type(body(), 'Thanks');
    await user.click(send);
    expect(await screen.findByText('workbench.mail.compose.unknown')).toBeInTheDocument();
    expect(send).toHaveAttribute('aria-disabled', 'true');
    await user.click(send);

    expect(write.reply).toHaveBeenCalledTimes(1);
  });
});
