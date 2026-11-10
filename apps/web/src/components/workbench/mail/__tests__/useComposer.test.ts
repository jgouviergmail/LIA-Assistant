/**
 * The composer's state (ADR-369, Review focus 3): a second press that lands
 * before the render showing the first sends nothing; one key per open
 * composer, kept across a refusal the person fixes; a draft whose words
 * changed is saved before it is sent, and sent at the revision just saved.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';

import { act, renderHook, waitFor } from '@/__tests__/test-utils';
import type { WorkbenchMailWriting } from '@/hooks/useWorkbenchMailWriting';
import { ApiError } from '@/lib/api-client';
import type { ComposerTarget } from '@/lib/workbench/mail-compose';
import type { AttachableFile, MailDraft, MailMessage } from '@/lib/workbench/types';

import { useComposer } from '../useComposer';

function writing(overrides: Partial<WorkbenchMailWriting> = {}): WorkbenchMailWriting {
  return {
    send: vi.fn().mockResolvedValue({ id: 's1', thread_id: 't1' }),
    reply: vi.fn().mockResolvedValue({ id: 's1', thread_id: 't1' }),
    forward: vi.fn().mockResolvedValue({ id: 's1', thread_id: 't1' }),
    saveDraft: vi.fn(),
    sendDraft: vi.fn().mockResolvedValue({ id: 's1', thread_id: 't1' }),
    replyRecipients: vi.fn().mockRejectedValue(new Error('unread')),
    ...overrides,
  };
}

function composer(
  target: ComposerTarget,
  write: WorkbenchMailWriting,
  options: Partial<Parameters<typeof useComposer>[0]> = {}
) {
  return renderHook(() =>
    useComposer({
      target,
      writing: write,
      recipientsMax: 100,
      onSent: vi.fn(),
      onDraftSaved: vi.fn(),
      ...options,
    })
  );
}

const HOLD_MS = 5000;

const ANSWERED: MailMessage = {
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

const DRIVE_FILE: AttachableFile = { ...FILE, id: 'g1', origin: 'drive' };

const REACHED = {
  to: [{ name: 'Ana', address: 'ana@example.org' }],
  cc: [{ name: '', address: 'carl@example.org' }],
};

describe('useComposer — the moment to take a message back', () => {
  afterEach(() => vi.useRealTimers());

  async function held(write: WorkbenchMailWriting, options = {}) {
    vi.useFakeTimers();
    const rendered = composer({ kind: 'new' }, write, { holdMs: HOLD_MS, ...options });
    act(() => rendered.result.current.set({ to: 'ana@example.org', body: 'See you' }));
    await act(() => rendered.result.current.send());
    return rendered;
  }

  it('holds the message, then sends it once when the moment has passed', async () => {
    const write = writing();
    const onSent = vi.fn();
    const { result } = await held(write, { onSent });

    expect(result.current.status).toBe('holding');
    expect(write.send).not.toHaveBeenCalled();

    await act(() => vi.advanceTimersByTimeAsync(HOLD_MS));

    expect(write.send).toHaveBeenCalledTimes(1);
    expect(onSent).toHaveBeenCalledWith(false);
  });

  it('gives the words back, unsent, when the person takes it back', async () => {
    const write = writing();
    const { result } = await held(write);

    act(() => result.current.undoSend());
    await act(() => vi.advanceTimersByTimeAsync(HOLD_MS));

    expect(write.send).not.toHaveBeenCalled();
    expect(result.current.status).toBe('editing');
    expect(result.current.fields.body).toBe('See you');
  });

  it('sends with the same key after a message taken back, and only then', async () => {
    const write = writing();
    const { result } = await held(write);
    act(() => result.current.undoSend());

    await act(() => result.current.send());
    await act(() => vi.advanceTimersByTimeAsync(HOLD_MS));

    expect(write.send).toHaveBeenCalledTimes(1);
  });

  it('takes no second press while it holds the message', async () => {
    const write = writing();
    const { result } = await held(write);

    await act(() => result.current.send());
    await act(() => vi.advanceTimersByTimeAsync(HOLD_MS * 2));

    expect(write.send).toHaveBeenCalledTimes(1);
  });

  it('sends what was held when the screen goes away: the person pressed « Send »', async () => {
    const write = writing();
    const { unmount } = await held(write);

    unmount();
    await vi.advanceTimersByTimeAsync(0);

    expect(write.send).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(HOLD_MS);
    expect(write.send).toHaveBeenCalledTimes(1);
  });

  it('says what could not leave once nobody is there to show it', async () => {
    const refusal = new ApiError('refused', 429, { detail: { code: 'provider_rate_limited' } });
    const onLost = vi.fn();
    const write = writing({ send: vi.fn().mockRejectedValue(refusal) });
    const { unmount } = await held(write, { onLost });

    unmount();
    await vi.advanceTimersByTimeAsync(0);

    expect(onLost).toHaveBeenCalledWith(
      expect.objectContaining({ body: 'See you' }),
      expect.objectContaining({ kind: 'refused' })
    );
  });

  it('sends at once where no moment is given', async () => {
    const write = writing();
    const { result } = composer({ kind: 'new' }, write, { holdMs: 0 });
    act(() => result.current.set({ to: 'ana@example.org' }));

    await act(() => result.current.send());

    expect(write.send).toHaveBeenCalledTimes(1);
  });

  it('holds nothing that cannot leave', async () => {
    vi.useFakeTimers();
    const write = writing();
    const { result } = composer({ kind: 'new' }, write, { holdMs: HOLD_MS });

    await act(() => result.current.send());

    expect(result.current.status).toBe('editing');
    expect(result.current.problem?.key).toBe('workbench.mail.compose.no_recipient');
  });
});

describe('useComposer — whom a reply reaches', () => {
  const reply: ComposerTarget = { kind: 'reply', message: ANSWERED, all: true };

  async function read(write: WorkbenchMailWriting) {
    const rendered = composer(reply, write);
    await act(async () => undefined);
    return rendered;
  }

  it('asks once, for the message and the reach the person chose', async () => {
    const replyRecipients = vi.fn().mockResolvedValue(REACHED);
    const { rerender } = await read(writing({ replyRecipients }));
    rerender();

    expect(replyRecipients).toHaveBeenCalledTimes(1);
    expect(replyRecipients).toHaveBeenCalledWith('m1', true);
  });

  it('shows who it reaches as something opened, never as words to lose', async () => {
    const { result } = await read(writing({ replyRecipients: vi.fn().mockResolvedValue(REACHED) }));

    expect(result.current.answered).toBe(true);
    expect(result.current.fields.to).toBe('ana@example.org');
    expect(result.current.fields.cc).toBe('carl@example.org');
    expect(result.current.dirty).toBe(false);
  });

  it('keeps the words typed while it asked', async () => {
    let answer: (value: typeof REACHED) => void = () => undefined;
    const pending = new Promise<typeof REACHED>(resolve => {
      answer = resolve;
    });
    const { result } = composer(reply, writing({ replyRecipients: () => pending }));
    act(() => result.current.set({ body: 'Thanks' }));

    await act(async () => answer(REACHED));

    expect(result.current.fields.body).toBe('Thanks');
    expect(result.current.dirty).toBe(true);
  });

  it('takes no answer meant for the message it left', async () => {
    let late: (value: typeof REACHED) => void = () => undefined;
    const replyRecipients = vi
      .fn()
      .mockImplementationOnce(() => new Promise(resolve => (late = resolve)))
      .mockResolvedValue({ to: [{ name: '', address: 'second@example.org' }], cc: [] });
    const write = writing({ replyRecipients });
    const { result, rerender } = renderHook(
      (target: ComposerTarget) =>
        useComposer({
          target,
          writing: write,
          recipientsMax: 100,
          onSent: vi.fn(),
          onDraftSaved: vi.fn(),
        }),
      { initialProps: reply }
    );

    rerender({ ...reply, message: { ...ANSWERED, id: 'm2' } });
    await act(async () => undefined);
    await act(async () => late(REACHED));

    expect(result.current.fields.to).toBe('second@example.org');
  });

  it('sends whom the person left in it', async () => {
    const write = writing({ replyRecipients: vi.fn().mockResolvedValue(REACHED) });
    const { result } = await read(write);
    act(() => result.current.set({ to: 'dora@example.org', cc: '' }));

    await act(() => result.current.send());

    expect(write.reply).toHaveBeenCalledWith(
      expect.objectContaining({ to: ['dora@example.org'], cc: [], reply_all: true })
    );
  });

  it('leaves the recipients to the provider when it could not read them', async () => {
    const write = writing();
    const { result } = await read(write);

    await act(() => result.current.send());

    expect(result.current.answered).toBe(false);
    const sent = vi.mocked(write.reply).mock.calls[0][0];
    expect(sent).not.toHaveProperty('to');
    expect(sent).not.toHaveProperty('cc');
  });

  it('refuses a reply left with nobody in To, once it knows who it reached', async () => {
    const write = writing({ replyRecipients: vi.fn().mockResolvedValue(REACHED) });
    const { result } = await read(write);
    act(() => result.current.set({ to: '' }));

    await act(() => result.current.send());

    expect(write.reply).not.toHaveBeenCalled();
    expect(result.current.problem?.field).toBe('to');
  });

  it('asks nothing for what is not a reply', () => {
    const replyRecipients = vi.fn();
    composer({ kind: 'forward', message: ANSWERED }, writing({ replyRecipients }));

    expect(replyRecipients).not.toHaveBeenCalled();
  });

  it('reads nothing once the composer is gone', async () => {
    let answer: (value: typeof REACHED) => void = () => undefined;
    const pending = new Promise<typeof REACHED>(resolve => {
      answer = resolve;
    });
    const { result, unmount } = composer(reply, writing({ replyRecipients: () => pending }));
    unmount();

    await act(async () => answer(REACHED));

    expect(result.current.answered).toBe(false);
  });
});

function stored(overrides: Partial<MailDraft> = {}): MailDraft {
  return {
    id: 'd1',
    revision: 'r1',
    sender: null,
    to: [],
    cc: [],
    bcc: [],
    subject: '',
    body: '',
    attachments: [],
    updated_at: null,
    ...overrides,
  };
}

const HELD = { id: 'a1', filename: 'kept.pdf', mime_type: 'application/pdf', size: 10 };

describe('useComposer — an answer kept as a draft', () => {
  const reply: ComposerTarget = { kind: 'reply', message: ANSWERED, all: false };

  it('keeps a reply in its thread, leaving the provider to say whom it reaches', async () => {
    const saveDraft = vi.fn().mockResolvedValue(stored());
    const { result } = composer(reply, writing({ saveDraft }));
    act(() => result.current.set({ body: 'Later' }));

    await act(() => result.current.saveDraft());

    const body = saveDraft.mock.calls[0][0];
    expect(body.origin).toEqual({ message_id: 'm1', kind: 'reply' });
    expect(body.body).toBe('Later');
    for (const left of ['to', 'cc', 'bcc', 'subject']) expect(body[left]).toBeUndefined();
  });

  it('names whom a reply to all reaches once the person sees it', async () => {
    const saveDraft = vi.fn().mockResolvedValue(stored());
    const replyRecipients = vi.fn().mockResolvedValue(REACHED);
    const { result } = composer(
      { kind: 'reply', message: ANSWERED, all: true },
      writing({ saveDraft, replyRecipients })
    );
    await act(async () => undefined);

    await act(() => result.current.saveDraft());

    expect(saveDraft).toHaveBeenCalledWith(
      expect.objectContaining({
        origin: { message_id: 'm1', kind: 'reply_all' },
        to: ['ana@example.org'],
        cc: ['carl@example.org'],
      })
    );
  });

  it('names what a forward carries and whom it goes to', async () => {
    const saveDraft = vi.fn().mockResolvedValue(stored());
    const { result } = composer({ kind: 'forward', message: ANSWERED }, writing({ saveDraft }));
    act(() => result.current.set({ to: 'ana@example.org', files: [FILE] }));

    await act(() => result.current.saveDraft());

    const body = saveDraft.mock.calls[0][0];
    expect(body.origin).toEqual({ message_id: 'm1', kind: 'forward' });
    expect(body.to).toEqual(['ana@example.org']);
    expect(body.attachment_ids).toEqual(['f1']);
    expect(body.bcc).toBeUndefined();
  });

  it('asks whom a forward goes to before keeping it', async () => {
    const saveDraft = vi.fn();
    const { result } = composer({ kind: 'forward', message: ANSWERED }, writing({ saveDraft }));

    await act(() => result.current.saveDraft());

    expect(saveDraft).not.toHaveBeenCalled();
    expect(result.current.problem).toEqual({
      field: 'to',
      key: 'workbench.mail.compose.no_recipient',
    });
  });

  it('never saves an answer by itself: a second save would lose what the first one quoted', async () => {
    vi.useFakeTimers();
    const saveDraft = vi.fn().mockResolvedValue(stored());
    const { result } = composer(reply, writing({ saveDraft }), { autosaveMs: 1000 });
    act(() => result.current.set({ body: 'Later' }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });

    expect(saveDraft).not.toHaveBeenCalled();
    vi.useRealTimers();
  });
});

describe('useComposer — a draft’s files', () => {
  it('saves the files chosen with the words, then holds them as the draft’s', async () => {
    const saveDraft = vi.fn().mockResolvedValue(stored({ attachments: [HELD] }));
    const { result } = composer({ kind: 'new' }, writing({ saveDraft }));
    act(() => result.current.set({ to: 'ana@example.org', files: [FILE, DRIVE_FILE] }));

    await act(() => result.current.saveDraft());

    expect(saveDraft).toHaveBeenCalledWith(
      expect.objectContaining({ attachment_ids: ['f1'], drive_file_ids: ['g1'] })
    );
    expect(result.current.fields.files).toEqual([]);
    expect(result.current.heldFiles).toEqual([HELD]);
    expect(result.current.dirty).toBe(false);
  });

  it('adds a file once: the next save names it no more', async () => {
    const saveDraft = vi.fn().mockResolvedValue(stored());
    const { result } = composer({ kind: 'new' }, writing({ saveDraft }));
    act(() => result.current.set({ to: 'ana@example.org', files: [FILE] }));
    await act(() => result.current.saveDraft());
    act(() => result.current.set({ body: 'More' }));

    await act(() => result.current.saveDraft());

    expect(saveDraft.mock.calls[1][0].attachment_ids).toEqual([]);
  });

  it('keeps a file chosen while the save was on its way', async () => {
    let answer: (draft: MailDraft) => void = () => undefined;
    const saveDraft = vi.fn(() => new Promise<MailDraft>(resolve => (answer = resolve)));
    const { result } = composer({ kind: 'new' }, writing({ saveDraft }));
    act(() => result.current.set({ to: 'ana@example.org', files: [FILE] }));
    let saving: Promise<void> = Promise.resolve();
    act(() => {
      saving = result.current.saveDraft();
    });
    expect(result.current.status).toBe('saving');
    await waitFor(() => expect(saveDraft).toHaveBeenCalledOnce());
    act(() => result.current.addFile(DRIVE_FILE));

    await act(async () => {
      answer(stored());
      await saving;
    });

    expect(result.current.fields.files).toEqual([DRIVE_FILE]);
    expect(result.current.dirty).toBe(true);
    expect(result.current.status).toBe('editing');
  });

  it('opens a draft on the files it holds', () => {
    const { result } = composer(
      { kind: 'draft', draft: stored({ attachments: [HELD] }) },
      writing()
    );

    expect(result.current.heldFiles).toEqual([HELD]);
  });

  it('takes a file off a draft by its name, at the next save', async () => {
    const saveDraft = vi.fn().mockResolvedValue(stored({ revision: 'r2' }));
    const { result } = composer(
      { kind: 'draft', draft: stored({ attachments: [HELD] }) },
      writing({ saveDraft })
    );

    act(() => result.current.dropHeldFile('kept.pdf'));

    expect(result.current.heldFiles).toEqual([]);
    expect(result.current.dirty).toBe(true);
    await act(() => result.current.saveDraft());
    expect(saveDraft.mock.calls[0][0].removed_files).toEqual(['kept.pdf']);
    expect(result.current.dirty).toBe(false);
  });

  it('takes one of two files of a name', () => {
    const { result } = composer(
      { kind: 'draft', draft: stored({ attachments: [HELD, { ...HELD, id: 'a2' }] }) },
      writing()
    );

    act(() => result.current.dropHeldFile('kept.pdf'));

    expect(result.current.heldFiles.map(file => file.id)).toEqual(['a2']);
  });

  it('sends a draft with its new files saved first: none is lost on the way', async () => {
    const saveDraft = vi.fn().mockResolvedValue(stored({ revision: 'r2' }));
    const sendDraft = vi.fn().mockResolvedValue({ id: 's1', thread_id: 't1' });
    const { result } = composer(
      { kind: 'draft', draft: stored({ to: [{ name: '', address: 'ana@example.org' }] }) },
      writing({ saveDraft, sendDraft })
    );
    act(() => result.current.addFile(FILE));

    await act(() => result.current.send());

    expect(saveDraft.mock.calls[0][0].attachment_ids).toEqual(['f1']);
    expect(sendDraft).toHaveBeenCalledWith(expect.objectContaining({ expected_revision: 'r2' }));
  });
});

describe('useComposer — formatted words', () => {
  const MARKED = { html: '<b>Hi</b>', body: 'Hi' };

  it('sends them with a new message, the words beside them', async () => {
    const write = writing();
    const { result } = composer({ kind: 'new' }, write);
    act(() => result.current.set({ to: 'ana@example.org', ...MARKED }));

    await act(() => result.current.send());

    expect(write.send).toHaveBeenCalledWith(
      expect.objectContaining({ html: '<b>Hi</b>', body: 'Hi' })
    );
  });

  it('sends them with a reply and a forward', async () => {
    const reply = writing();
    const answered = composer({ kind: 'reply', message: ANSWERED, all: false }, reply);
    act(() => answered.result.current.set(MARKED));
    await act(() => answered.result.current.send());
    expect(reply.reply).toHaveBeenCalledWith(expect.objectContaining({ html: '<b>Hi</b>' }));

    const forward = writing();
    const forwarded = composer({ kind: 'forward', message: ANSWERED }, forward);
    act(() => forwarded.result.current.set({ to: 'ana@example.org', ...MARKED }));
    await act(() => forwarded.result.current.send());
    expect(forward.forward).toHaveBeenCalledWith(expect.objectContaining({ html: '<b>Hi</b>' }));
  });

  it('saves them with a draft', async () => {
    const saveDraft = vi.fn().mockResolvedValue(stored());
    const { result } = composer({ kind: 'new' }, writing({ saveDraft }));
    act(() => result.current.set(MARKED));

    await act(() => result.current.saveDraft());

    expect(saveDraft.mock.calls[0][0].html).toBe('<b>Hi</b>');
  });

  it('names none when the person wrote plain text', async () => {
    const write = writing();
    const { result } = composer({ kind: 'new' }, write);
    act(() => result.current.set({ to: 'ana@example.org', body: 'Hi' }));

    await act(() => result.current.send());

    expect(vi.mocked(write.send).mock.calls[0][0]).not.toHaveProperty('html');
  });

  it('counts turning them on over nothing as nothing written', () => {
    const { result } = composer({ kind: 'new' }, writing());

    act(() => result.current.set({ html: '' }));

    expect(result.current.dirty).toBe(false);
  });
});

describe('useComposer — a draft saved by itself', () => {
  const QUIET_MS = 15_000;

  afterEach(() => vi.useRealTimers());

  function quiet(write: WorkbenchMailWriting, target: ComposerTarget = { kind: 'new' }) {
    vi.useFakeTimers();
    return composer(target, write, { autosaveMs: QUIET_MS });
  }

  const passing = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));

  it('saves what was written once the person stops', async () => {
    const saveDraft = vi.fn().mockResolvedValue(stored());
    const { result } = quiet(writing({ saveDraft }));
    act(() => result.current.set({ body: 'Words' }));

    await passing(QUIET_MS - 1);
    expect(saveDraft).not.toHaveBeenCalled();

    await passing(1);
    expect(saveDraft).toHaveBeenCalledTimes(1);
    expect(result.current.autosave).toBe('saved');
    expect(result.current.dirty).toBe(false);
  });

  it('waits for the person to stop: each change starts the moment again', async () => {
    const saveDraft = vi.fn().mockResolvedValue(stored());
    const { result } = quiet(writing({ saveDraft }));
    act(() => result.current.set({ body: 'W' }));
    await passing(QUIET_MS - 1);

    act(() => result.current.set({ body: 'Wo' }));
    await passing(QUIET_MS - 1);

    expect(saveDraft).not.toHaveBeenCalled();
  });

  it('saves nothing of a message nothing was written in', async () => {
    const saveDraft = vi.fn();
    const { result } = quiet(writing({ saveDraft }));
    act(() => result.current.set({ body: '   ' }));

    await passing(QUIET_MS);

    expect(saveDraft).not.toHaveBeenCalled();
  });

  it('changes the draft it made, against its revision', async () => {
    const saveDraft = vi.fn().mockResolvedValue(stored());
    const { result } = quiet(writing({ saveDraft }));
    act(() => result.current.set({ body: 'Words' }));
    await passing(QUIET_MS);

    act(() => result.current.set({ body: 'More words' }));
    await passing(QUIET_MS);

    expect(saveDraft.mock.calls[1][0]).toMatchObject({ draft_id: 'd1', expected_revision: 'r1' });
  });

  it('never saves an answer: the composer writes no draft of one', async () => {
    const saveDraft = vi.fn();
    const { result } = quiet(writing({ saveDraft }), {
      kind: 'forward',
      message: ANSWERED,
    });
    act(() => result.current.set({ body: 'Words' }));

    await passing(QUIET_MS);

    expect(saveDraft).not.toHaveBeenCalled();
  });

  it('never runs where it is switched off', async () => {
    vi.useFakeTimers();
    const saveDraft = vi.fn();
    const { result } = composer({ kind: 'new' }, writing({ saveDraft }), { autosaveMs: 0 });
    act(() => result.current.set({ body: 'Words' }));

    await passing(QUIET_MS);

    expect(saveDraft).not.toHaveBeenCalled();
  });

  it('says when it could not save, and lets the person go on', async () => {
    const saveDraft = vi.fn().mockRejectedValue(new Error('down'));
    const send = vi.fn().mockResolvedValue({ id: 's1', thread_id: 't1' });
    const { result } = quiet(writing({ saveDraft, send }));
    act(() => result.current.set({ to: 'ana@example.org', body: 'Words' }));

    await passing(QUIET_MS);

    expect(result.current.autosave).toBe('failed');
    expect(result.current.status).toBe('editing');
    await act(() => result.current.send());
    expect(send).toHaveBeenCalledTimes(1);
  });

  it('tries again at the next change', async () => {
    const saveDraft = vi.fn().mockRejectedValueOnce(new Error('down')).mockResolvedValue(stored());
    const { result } = quiet(writing({ saveDraft }));
    act(() => result.current.set({ body: 'Words' }));
    await passing(QUIET_MS);

    act(() => result.current.set({ body: 'More' }));
    await passing(QUIET_MS);

    expect(result.current.autosave).toBe('saved');
  });

  it('holds a send until its save ended, and adds no file twice', async () => {
    let answer: (draft: MailDraft) => void = () => undefined;
    const saveDraft = vi.fn(() => new Promise<MailDraft>(resolve => (answer = resolve)));
    const sendDraft = vi.fn().mockResolvedValue({ id: 's1', thread_id: 't1' });
    const { result } = quiet(writing({ saveDraft, sendDraft }));
    act(() => result.current.set({ to: 'ana@example.org', files: [FILE] }));
    await passing(QUIET_MS);
    expect(saveDraft).toHaveBeenCalledTimes(1);

    let sending = Promise.resolve();
    act(() => {
      sending = result.current.send();
    });
    await act(async () => {
      answer(stored());
      await sending;
    });

    expect(saveDraft).toHaveBeenCalledTimes(1);
    expect(sendDraft).toHaveBeenCalledTimes(1);
  });

  it('saves nothing while a message leaves', async () => {
    const saveDraft = vi.fn();
    let sent: (value: { id: string; thread_id: string }) => void = () => undefined;
    const send = vi.fn(
      () => new Promise<{ id: string; thread_id: string }>(resolve => (sent = resolve))
    );
    const { result } = quiet(writing({ saveDraft, send }));
    act(() => result.current.set({ to: 'ana@example.org', body: 'Words' }));
    let sending = Promise.resolve();
    act(() => {
      sending = result.current.send();
    });

    await passing(QUIET_MS);

    expect(saveDraft).not.toHaveBeenCalled();
    await act(async () => {
      sent({ id: 's1', thread_id: 't1' });
      await sending;
    });
  });
});

describe('useComposer — the files of an answer', () => {
  it('sends the person’s own and the drive’s with a reply', async () => {
    const write = writing();
    const { result } = composer({ kind: 'reply', message: ANSWERED, all: false }, write);
    act(() => result.current.set({ files: [FILE, DRIVE_FILE] }));

    await act(() => result.current.send());

    expect(write.reply).toHaveBeenCalledWith(
      expect.objectContaining({ attachment_ids: ['f1'], drive_file_ids: ['g1'] })
    );
  });

  it('sends them with a forward too', async () => {
    const write = writing();
    const { result } = composer({ kind: 'forward', message: ANSWERED }, write);
    act(() => result.current.set({ to: 'dora@example.org', files: [FILE, DRIVE_FILE] }));

    await act(() => result.current.send());

    expect(write.forward).toHaveBeenCalledWith(
      expect.objectContaining({ attachment_ids: ['f1'], drive_file_ids: ['g1'] })
    );
  });
});

describe('useComposer', () => {
  it('sends nothing for a second press that lands before the first is shown', async () => {
    let answer!: (value: unknown) => void;
    const write = writing({
      send: vi.fn().mockReturnValue(new Promise(resolve => (answer = resolve))),
    });
    const { result } = composer({ kind: 'new' }, write);
    act(() => result.current.set({ to: 'ana@example.org' }));

    let first!: Promise<void>;
    let second!: Promise<void>;
    act(() => {
      first = result.current.send();
      second = result.current.send();
    });
    await act(async () => {
      answer({ id: 's1', thread_id: 't1' });
      await Promise.all([first, second]);
    });

    expect(write.send).toHaveBeenCalledTimes(1);
  });

  it('keeps its one key across a refusal the person fixes', async () => {
    const send = vi
      .fn()
      .mockRejectedValueOnce(
        new ApiError('refused', 429, { detail: { code: 'provider_rate_limited' } })
      )
      .mockResolvedValueOnce({ id: 's1', thread_id: 't1' });
    const { result } = composer({ kind: 'new' }, writing({ send }));
    act(() => result.current.set({ to: 'ana@example.org' }));

    await act(() => result.current.send());
    expect(result.current.problem).toEqual({
      key: 'workbench.errors.provider_rate_limited',
      field: undefined,
      values: undefined,
    });
    await act(() => result.current.send());

    const [[first], [second]] = send.mock.calls;
    expect(second.idempotency_key).toBe(first.idempotency_key);
  });

  it('sends a new message saved as a draft AS that draft, never as a second copy', async () => {
    const saveDraft = vi.fn().mockResolvedValue(stored());
    const write = writing({ saveDraft });
    const { result } = composer({ kind: 'new' }, write);
    act(() => result.current.set({ to: 'ana@example.org', body: 'Hello' }));
    await act(() => result.current.saveDraft());

    await act(() => result.current.send());

    expect(write.send).not.toHaveBeenCalled();
    expect(write.sendDraft).toHaveBeenCalledWith(
      expect.objectContaining({ draft_id: 'd1', expected_revision: 'r1' })
    );
  });

  it('saves a changed draft first, then sends the revision just saved', async () => {
    const saveDraft = vi.fn().mockResolvedValue(stored({ id: 'd2', revision: 'r2' }));
    const write = writing({ saveDraft });
    const { result } = composer(
      {
        kind: 'draft',
        draft: {
          id: 'd1',
          revision: 'r1',
          sender: null,
          to: [{ name: '', address: 'ana@example.org' }],
          cc: [],
          bcc: [],
          subject: 'Plan',
          body: 'Old',
          attachments: [],
          updated_at: null,
        },
      },
      write
    );
    act(() => result.current.set({ body: 'New' }));

    await act(() => result.current.send());

    expect(saveDraft).toHaveBeenCalledWith(
      expect.objectContaining({ draft_id: 'd1', expected_revision: 'r1', body: 'New' })
    );
    expect(write.sendDraft).toHaveBeenCalledWith(
      expect.objectContaining({ draft_id: 'd2', expected_revision: 'r2' })
    );
  });
});
