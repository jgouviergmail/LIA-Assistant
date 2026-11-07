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
  fireEvent,
  renderWithProviders,
  screen,
  waitFor,
  within,
} from '@/__tests__/test-utils';
import type { WorkbenchMailWriting } from '@/hooks/useWorkbenchMailWriting';
import { ApiError } from '@/lib/api-client';
import type { ComposerTarget } from '@/lib/workbench/mail-compose';
import { FileSendStopped } from '@/lib/workbench/upload';
import type {
  AttachableFile,
  MailDraft,
  MailMessage,
  MailSender,
  WorkbenchFeature,
} from '@/lib/workbench/types';

const { api, i18n, sendFile, toast } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  sendFile: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn() },
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
vi.mock('@/lib/workbench/upload', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/workbench/upload')>()),
  sendFile,
}));
vi.mock('sonner', () => ({ toast }));

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
  has_attachments: false,
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
  sender: null,
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
    replyRecipients: vi.fn().mockRejectedValue(new Error('unread')),
  };
}

function composer(
  target: ComposerTarget = { kind: 'new' },
  features: WorkbenchFeature[] = ['attachments', 'drafts'],
  holdMs = 0,
  write: WorkbenchMailWriting = writing(),
  autosaveMs = 0,
  signatureBlock = '',
  senders: MailSender[] = []
) {
  const props = { writing: write, onClose: vi.fn(), onSent: vi.fn(), onDraftSaved: vi.fn() };
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
      uploadMaxBytes={1000}
      holdMs={holdMs}
      autosaveMs={autosaveMs}
      signatureBlock={signatureBlock}
      senders={senders}
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

describe('Composer — a window beside the mail', () => {
  it('leaves the page usable: nothing behind it is hidden from anyone', async () => {
    composer({ kind: 'new' });

    const panel = await screen.findByRole('dialog', { name: 'workbench.mail.compose.title_new' });

    expect(panel).toHaveAttribute('aria-modal', 'false');
    expect(document.querySelector('[data-aria-hidden="true"]')).toBeNull();
  });

  it('opens on the field the person writes first: the message, for a reply', async () => {
    composer({ kind: 'reply', message: MESSAGE, all: false });

    expect(
      await screen.findByRole('textbox', { name: 'workbench.mail.compose.body' })
    ).toHaveFocus();
  });

  it('keeps the message answered in sight', async () => {
    composer({ kind: 'reply', message: MESSAGE, all: false });

    expect(await screen.findByText(MESSAGE.body)).toBeInTheDocument();
  });

  it('closes on Escape, and asks first when words would be lost', async () => {
    const { user, onClose } = composer({ kind: 'new' });
    await user.type(
      await screen.findByRole('textbox', { name: 'workbench.mail.compose.body' }),
      'Words'
    );

    await user.keyboard('{Escape}');

    expect(await screen.findByRole('alertdialog')).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });

  it('gives the focus back to what opened it', async () => {
    const opener = document.createElement('button');
    document.body.append(opener);
    opener.focus();
    const { unmount } = composer({ kind: 'new' });
    await screen.findByRole('dialog');

    unmount();

    expect(opener).toHaveFocus();
    opener.remove();
  });
});

describe('Composer — taking a message back', () => {
  it('steps aside while it holds the message and comes back on « Undo »', async () => {
    const { user } = composer({ kind: 'new' }, undefined, 5000);
    await user.type(
      await screen.findByRole('combobox', { name: 'workbench.mail.compose.to' }),
      'ana@example.org'
    );
    await user.click(screen.getByRole('button', { name: /workbench\.mail\.compose\.send/ }));

    const undo = await screen.findByRole('button', { name: 'workbench.mail.compose.undo' });
    expect(undo).toHaveFocus();
    expect(screen.getByRole('status')).toHaveTextContent('workbench.mail.compose.holding');
    expect(screen.queryByRole('dialog')).toBeNull();

    await user.click(undo);

    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'workbench.mail.compose.body' })).toHaveFocus();
  });

  it('warns before a page closes on a message not gone yet', async () => {
    const { user } = composer({ kind: 'new' }, undefined, 5000);
    await user.type(
      await screen.findByRole('combobox', { name: 'workbench.mail.compose.to' }),
      'ana@example.org'
    );
    await user.click(screen.getByRole('button', { name: /workbench\.mail\.compose\.send/ }));
    await screen.findByRole('button', { name: 'workbench.mail.compose.undo' });

    const leaving = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(leaving);

    expect(leaving.defaultPrevented).toBe(true);
  });
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

  it('shows who a reply reaches once it is read, the copies with it, and no Bcc', async () => {
    const write = {
      ...writing(),
      replyRecipients: vi.fn().mockResolvedValue({
        to: [{ name: 'Ana', address: 'ana@example.org' }],
        cc: [{ name: '', address: 'carl@example.org' }],
      }),
    };
    composer({ kind: 'reply', message: MESSAGE, all: true }, ['attachments'], 0, write);

    expect(await screen.findByLabelText('workbench.mail.compose.to')).toHaveValue(
      'ana@example.org'
    );
    expect(screen.getByLabelText('workbench.mail.compose.cc')).toHaveValue('carl@example.org');
    expect(screen.queryByLabelText('workbench.mail.compose.bcc')).toBeNull();
    expect(screen.queryByLabelText('workbench.mail.compose.subject')).toBeNull();
    expect(screen.getByText('workbench.mail.compose.reply_about(Budget)')).toBeInTheDocument();
  });

  it('keeps the copies folded on a reply that copies nobody', async () => {
    const write = {
      ...writing(),
      replyRecipients: vi.fn().mockResolvedValue({
        to: [{ name: 'Ana', address: 'ana@example.org' }],
        cc: [],
      }),
    };
    composer({ kind: 'reply', message: MESSAGE, all: false }, ['attachments'], 0, write);

    await screen.findByLabelText('workbench.mail.compose.to');
    expect(screen.queryByLabelText('workbench.mail.compose.cc')).toBeNull();
  });

  it('offers files on a reply and on a forward', () => {
    const reply = composer({ kind: 'reply', message: MESSAGE, all: false });
    expect(screen.getByRole('button', { name: 'workbench.mail.files.add' })).toBeInTheDocument();
    reply.unmount();

    composer({ kind: 'forward', message: MESSAGE });
    expect(screen.getByRole('button', { name: 'workbench.mail.files.add' })).toBeInTheDocument();
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

  it('opens a draft with its copies and its files shown, and offers more', () => {
    composer({
      kind: 'draft',
      draft: {
        ...DRAFT,
        attachments: [{ id: 'a1', filename: 'a.pdf', mime_type: 'application/pdf', size: 1 }],
      },
    });

    expect(screen.getByLabelText('workbench.mail.compose.cc')).toHaveValue('cc@example.org');
    expect(screen.getByLabelText('workbench.mail.compose.bcc')).toBeInTheDocument();
    expect(screen.getByText('a.pdf')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'workbench.mail.files.add' })).toBeInTheDocument();
  });
});

describe('Composer — a file of the device', () => {
  const chooser = () => screen.getByLabelText('workbench.mail.files.from_device');
  const named = (name: string, size = 3) => new File(['x'.repeat(size)], name);
  const kept = (id: string, filename: string): AttachableFile => ({ ...FILE, id, filename });
  const send = () => screen.getByRole('button', { name: 'workbench.mail.compose.send' });

  it('is kept, then leaves with the message like any file of the person', async () => {
    sendFile.mockResolvedValue(kept('k1', 'notes.txt'));
    const { user, writing: write } = composer();
    await user.type(screen.getByLabelText('workbench.mail.compose.to'), 'ana@example.org');

    await user.upload(chooser(), named('notes.txt'));

    expect(await screen.findByText('notes.txt')).toBeInTheDocument();
    const [path, form] = sendFile.mock.calls[0];
    expect(path).toBe('/workbench/mail/files');
    expect((form as FormData).get('file')).toBeInstanceOf(File);

    await user.click(send());

    await waitFor(() =>
      expect(write.send).toHaveBeenCalledWith(expect.objectContaining({ attachment_ids: ['k1'] }))
    );
  });

  it('stops a file on its way without sending the message', async () => {
    sendFile.mockReturnValue(new Promise(() => undefined));
    const { user, writing: write } = composer();
    await user.type(screen.getByLabelText('workbench.mail.compose.to'), 'ana@example.org');
    await user.upload(chooser(), named('notes.txt'));

    const stop = await screen.findByRole('button', { name: 'workbench.files.stop_sending' });
    expect(stop).toHaveAttribute('type', 'button');
    await user.click(stop);

    expect(write.send).not.toHaveBeenCalled();
  });

  it('keeps several, each added once it arrived', async () => {
    sendFile.mockResolvedValueOnce(kept('k1', 'a.txt')).mockResolvedValueOnce(kept('k2', 'b.txt'));
    const { user } = composer();

    await user.upload(chooser(), [named('a.txt'), named('b.txt')]);

    expect(await screen.findByText('a.txt')).toBeInTheDocument();
    expect(await screen.findByText('b.txt')).toBeInTheDocument();
  });

  it('is offered on a reply too', async () => {
    sendFile.mockResolvedValue(kept('k1', 'notes.txt'));
    const { user } = composer({ kind: 'reply', message: MESSAGE, all: false });

    await user.upload(chooser(), named('notes.txt'));

    expect(await screen.findByText('notes.txt')).toBeInTheDocument();
  });

  it('holds the message while a file is on its way: nothing leaves without it', async () => {
    let arrive: (file: AttachableFile) => void = () => undefined;
    sendFile.mockReturnValue(new Promise(resolve => (arrive = resolve)));
    const { user, writing: write } = composer();
    await user.type(screen.getByLabelText('workbench.mail.compose.to'), 'ana@example.org');
    await user.upload(chooser(), named('notes.txt'));

    await user.click(send());

    expect(write.send).not.toHaveBeenCalled();
    expect(send()).toHaveAttribute('aria-disabled', 'true');

    arrive(kept('k1', 'notes.txt'));
    await screen.findByText('notes.txt');
    await user.click(send());

    await waitFor(() => expect(write.send).toHaveBeenCalledTimes(1));
  });

  it('stops a file without sending the message around it', async () => {
    sendFile.mockImplementation(
      (_path, _form, _progress, signal: AbortSignal) =>
        new Promise((_resolve, reject) => {
          signal.addEventListener('abort', () => reject(new FileSendStopped()));
        })
    );
    const { user, writing: write } = composer();
    await user.type(screen.getByLabelText('workbench.mail.compose.to'), 'ana@example.org');
    await user.upload(chooser(), named('notes.txt'));

    await user.click(await screen.findByRole('button', { name: 'workbench.files.stop_sending' }));

    await waitFor(() => expect(send()).not.toHaveAttribute('aria-disabled'));
    expect(write.send).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('says what the server refused', async () => {
    sendFile.mockRejectedValue(
      new ApiError('refused', 413, { detail: { code: 'too_large', max_bytes: 1000 } })
    );
    const { user } = composer();

    await user.upload(chooser(), named('notes.txt'));

    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
    expect(screen.queryByText('notes.txt')).toBeNull();
  });

  it('says what passes a bound and reads none of it', async () => {
    const { user } = composer();

    await user.upload(chooser(), named('big.bin', 1001));

    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(sendFile).not.toHaveBeenCalled();
  });

  it('counts a file on its way against the bound of a message', async () => {
    sendFile.mockReturnValue(new Promise(() => undefined));
    const { user } = composer();

    await user.upload(
      chooser(),
      [1, 2, 3, 4, 5].map(index => named(`${index}.txt`))
    );
    await user.upload(chooser(), named('6.txt'));

    expect(toast.error).toHaveBeenCalledTimes(1);
  });

  it('takes what is dropped on it', async () => {
    sendFile.mockResolvedValue(kept('k1', 'dropped.txt'));
    composer();
    const panel = screen.getByRole('dialog');
    const transfer = {
      types: ['Files'],
      files: [named('dropped.txt')],
      items: [{ webkitGetAsEntry: () => ({ isDirectory: false }) }],
    };

    fireEvent.dragOver(panel, { dataTransfer: transfer });
    expect(await screen.findByText('workbench.files.drop_here')).toBeInTheDocument();
    fireEvent.drop(panel, { dataTransfer: transfer });

    expect(await screen.findByText('dropped.txt')).toBeInTheDocument();
  });
});

describe('Composer — where it leaves from', () => {
  const OWN: MailSender = { address: 'me@gmail.com', name: '', is_default: true };
  const WORK: MailSender = { address: 'work@example.com', name: 'Ana', is_default: false };
  const field = () => screen.getByLabelText('workbench.mail.compose.from');
  const open = (target: ComposerTarget, senders: MailSender[]) =>
    composer(target, ['attachments', 'drafts'], 0, writing(), 0, '', senders);

  it('asks nothing of a mailbox with one address', () => {
    open({ kind: 'new' }, [OWN]);

    expect(screen.queryByLabelText('workbench.mail.compose.from')).toBeNull();
  });

  it('opens on the default, and names no alias when the person chose none', async () => {
    const { user, writing: write } = open({ kind: 'new' }, [OWN, WORK]);
    expect(field()).toHaveValue('me@gmail.com');

    await user.type(screen.getByLabelText('workbench.mail.compose.to'), 'ana@example.org');
    await user.click(screen.getByRole('button', { name: 'workbench.mail.compose.send' }));

    await waitFor(() => expect(write.send).toHaveBeenCalledTimes(1));
    expect(vi.mocked(write.send).mock.calls[0][0]).not.toHaveProperty('send_as');
  });

  it('sends from the alias chosen', async () => {
    const { user, writing: write } = open({ kind: 'new' }, [OWN, WORK]);

    await user.selectOptions(field(), 'work@example.com');
    await user.type(screen.getByLabelText('workbench.mail.compose.to'), 'ana@example.org');
    await user.click(screen.getByRole('button', { name: 'workbench.mail.compose.send' }));

    await waitFor(() =>
      expect(write.send).toHaveBeenCalledWith(
        expect.objectContaining({ send_as: 'work@example.com' })
      )
    );
  });

  it('opens a draft on the address it holds', () => {
    open(
      { kind: 'draft', draft: { ...DRAFT, sender: { name: '', address: 'work@example.com' } } },
      [OWN, WORK]
    );

    expect(field()).toHaveValue('work@example.com');
  });

  it('names an alias to the draft once, not at every save', async () => {
    const { user, writing: write } = open({ kind: 'new' }, [OWN, WORK]);
    const save = screen.getByRole('button', { name: 'workbench.mail.compose.save_draft' });
    await user.selectOptions(field(), 'work@example.com');

    await user.click(save);
    await waitFor(() => expect(write.saveDraft).toHaveBeenCalledTimes(1));
    await user.type(body(), 'More');
    await user.click(save);
    await waitFor(() => expect(write.saveDraft).toHaveBeenCalledTimes(2));

    const [first, second] = vi.mocked(write.saveDraft).mock.calls;
    expect(first[0].send_as).toBe('work@example.com');
    expect(second[0]).not.toHaveProperty('send_as');
  });
});

describe('Composer — formatted words', () => {
  const formatting = () => screen.getByRole('button', { name: 'workbench.mail.compose.format' });

  it('starts as plain text, and turns on with the words already written', async () => {
    const { user } = composer();
    await user.type(body(), 'a <b>');
    expect(formatting()).toHaveAttribute('aria-pressed', 'false');

    await user.click(formatting());

    expect(formatting()).toHaveAttribute('aria-pressed', 'true');
    expect(body().innerHTML).toBe('a &lt;b&gt;');
    expect(screen.queryByRole('toolbar')).toBeInTheDocument();
  });

  it('turns off keeping the words', async () => {
    const { user } = composer();
    await user.type(body(), 'kept');
    await user.click(formatting());

    await user.click(formatting());

    expect(body()).toHaveValue('kept');
    expect(screen.queryByRole('toolbar')).toBeNull();
  });

  it('is offered on a reply too, its signature kept', async () => {
    const { user } = composer(
      { kind: 'reply', message: MESSAGE, all: false },
      ['attachments'],
      0,
      writing(),
      0,
      '\n\n-- \nAna'
    );

    await user.click(formatting());

    expect(body().innerHTML).toBe('<br><br>-- <br>Ana');
  });
});

describe('Composer — a signature', () => {
  const BLOCK = '\n\n-- \nAna';
  const signed = (target: ComposerTarget) =>
    composer(target, ['attachments', 'drafts'], 0, writing(), 0, BLOCK);

  it('stands below the words, the person writing above it', () => {
    signed({ kind: 'reply', message: MESSAGE, all: false });

    const field = body() as HTMLTextAreaElement;
    expect(field).toHaveValue(BLOCK);
    expect(field).toHaveFocus();
    expect(field.selectionStart).toBe(0);
  });

  it('is no word to lose: closing on it asks nothing', async () => {
    const { user, onClose } = signed({ kind: 'new' });

    await user.click(cancel());

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('leaves with the message, as the person left it', async () => {
    const { user, writing: write } = signed({ kind: 'new' });
    await user.type(screen.getByLabelText('workbench.mail.compose.to'), 'ana@example.org');
    await user.click(screen.getByRole('button', { name: 'workbench.mail.compose.send' }));

    await waitFor(() =>
      expect(write.send).toHaveBeenCalledWith(expect.objectContaining({ body: BLOCK }))
    );
  });
});

describe('Composer — an answer kept for later', () => {
  it('offers a draft on a reply and closes on it, the words safe in the mailbox', async () => {
    const write = writing();
    const { user, onClose, onDraftSaved } = composer(
      { kind: 'reply', message: MESSAGE, all: false },
      ['attachments', 'drafts'],
      0,
      write
    );

    await user.type(body(), 'Later');
    await user.click(screen.getByRole('button', { name: 'workbench.mail.compose.save_draft' }));

    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(onDraftSaved).toHaveBeenCalledTimes(1);
    expect(write.saveDraft).toHaveBeenCalledWith(
      expect.objectContaining({ origin: { message_id: 'm1', kind: 'reply' }, body: 'Later' })
    );
  });

  it('stays open on a new message, which goes on being that draft', async () => {
    const { user, onClose, onDraftSaved } = composer();

    await user.type(body(), 'Later');
    await user.click(screen.getByRole('button', { name: 'workbench.mail.compose.save_draft' }));

    await waitFor(() => expect(onDraftSaved).toHaveBeenCalledTimes(1));
    expect(onClose).not.toHaveBeenCalled();
  });

  it('says whom a forward lacks, and keeps it open', async () => {
    const write = writing();
    const { user, onClose } = composer(
      { kind: 'forward', message: MESSAGE },
      ['attachments', 'drafts'],
      0,
      write
    );

    await user.click(screen.getByRole('button', { name: 'workbench.mail.compose.save_draft' }));

    expect(await screen.findByText('workbench.mail.compose.no_recipient')).toBeInTheDocument();
    expect(write.saveDraft).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });

  it('offers no draft where the provider keeps none', () => {
    composer({ kind: 'reply', message: MESSAGE, all: false }, ['attachments']);

    expect(screen.queryByRole('button', { name: 'workbench.mail.compose.save_draft' })).toBeNull();
  });
});

describe('Composer — a draft saved by itself', () => {
  const QUIET_MS = 20;

  it('says it saved, and closes on it without asking, saying where the words are', async () => {
    const {
      user,
      writing: write,
      onClose,
      onDraftSaved,
    } = composer({ kind: 'new' }, ['attachments', 'drafts'], 0, writing(), QUIET_MS);

    await user.type(body(), 'Later');

    expect(await screen.findByText('workbench.mail.compose.autosaved')).toBeInTheDocument();
    expect(write.saveDraft).toHaveBeenCalledTimes(1);
    expect(onDraftSaved).not.toHaveBeenCalled();

    await user.click(cancel());

    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(onDraftSaved).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('says when it could not', async () => {
    const write = { ...writing(), saveDraft: vi.fn().mockRejectedValue(new Error('down')) };
    const { user } = composer({ kind: 'new' }, ['attachments', 'drafts'], 0, write, QUIET_MS);

    await user.type(body(), 'Later');

    expect(await screen.findByText('workbench.mail.compose.autosave_failed')).toBeInTheDocument();
  });

  it('never runs where the provider keeps no draft', async () => {
    const { user, writing: write } = composer(
      { kind: 'new' },
      ['attachments'],
      0,
      writing(),
      QUIET_MS
    );

    await user.type(body(), 'Later');
    await new Promise(resolve => window.setTimeout(resolve, QUIET_MS * 3));

    expect(write.saveDraft).not.toHaveBeenCalled();
  });
});

describe('Composer — files and drafts', () => {
  it('takes a file off a draft, and saves that', async () => {
    const { user, writing: write } = composer({
      kind: 'draft',
      draft: {
        ...DRAFT,
        attachments: [{ id: 'a1', filename: 'a.pdf', mime_type: 'application/pdf', size: 1 }],
      },
    });

    await user.click(screen.getByRole('button', { name: 'workbench.mail.files.remove(a.pdf)' }));

    expect(screen.queryByText('a.pdf')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'workbench.mail.compose.save_draft' }));
    await waitFor(() =>
      expect(write.saveDraft).toHaveBeenCalledWith(
        expect.objectContaining({ removed_files: ['a.pdf'] })
      )
    );
  });

  it('counts what a draft holds against what a message carries', async () => {
    const held = [1, 2, 3, 4, 5].map(index => ({
      id: `a${index}`,
      filename: `${index}.pdf`,
      mime_type: 'application/pdf',
      size: 1,
    }));
    const { user } = composer({ kind: 'draft', draft: { ...DRAFT, attachments: held } });

    await user.upload(
      screen.getByLabelText('workbench.mail.files.from_device'),
      new File(['x'], 'sixth.txt')
    );

    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(sendFile).not.toHaveBeenCalled();
  });

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
    // A draft carries files too: they stay on offer once the words are a draft.
    expect(screen.getByRole('button', { name: 'workbench.mail.files.add' })).toBeInTheDocument();
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
