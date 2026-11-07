/**
 * Writing a message with LIA (ADR-372, lot 3): the lines follow what stands in the composer, a
 * signature is no one's words to rewrite, and a subject proposed goes to the subject alone.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { initialFields, type ComposerTarget } from '@/lib/workbench/mail-compose';
import type { MailMessage } from '@/lib/workbench/types';

const { post, bounds } = vi.hoisted(() => ({
  post: vi.fn(),
  bounds: { value: { textMax: 100, instructionMax: 100 } as object | null },
}));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { post },
}));
vi.mock('../../WorkbenchShell', () => ({ useAssistBounds: () => bounds.value }));

import { ComposerAssist } from '../ComposerAssist';

const OPEN = 'workbench.assist.writing.open';
const SIGNATURE = '\n\n-- \nAna';
const MESSAGE: MailMessage = {
  id: 'm1',
  thread_id: 't1',
  sender: null,
  subject: 'Budget',
  received_at: null,
  is_read: true,
  is_starred: false,
  has_attachments: false,
  label_ids: [],
  reply_to: [],
  to: [],
  cc: [],
  body: 'Hello',
  attachments: [],
};

function draw(target: ComposerTarget, body: string, to = '', field: 'subject' | 'body' = 'body') {
  const onBody = vi.fn();
  const onSubject = vi.fn();
  const rendered = renderWithProviders(
    <ComposerAssist
      lng="en"
      field={field}
      target={target}
      fields={{ ...initialFields({ kind: 'new' }), body, to }}
      signature={SIGNATURE}
      writesSubject={target.kind !== 'reply'}
      onBody={onBody}
      onSubject={onSubject}
    />
  );
  return { ...rendered, onBody, onSubject };
}

async function lines(user: ReturnType<typeof draw>['user']) {
  await user.click(screen.getByRole('button', { name: OPEN }));
  return (await screen.findAllByRole('menuitem')).map(item => item.textContent);
}

beforeEach(() => {
  post.mockReset();
  post.mockResolvedValue({ text: 'Proposed', subject: 'A subject', usage: null });
  bounds.value = { textMax: 100, instructionMax: 100 };
});

describe('ComposerAssist', () => {
  it('stands nowhere the instance withholds it', () => {
    bounds.value = null;

    const { container } = draw({ kind: 'new' }, '');

    expect(container).toBeEmptyDOMElement();
  });

  it('offers a whole message in an empty composer, a signature being no words of the person', async () => {
    const { user } = draw({ kind: 'new' }, SIGNATURE);

    expect(await lines(user)).toEqual(['workbench.assist.writing.compose']);
  });

  it('offers the answer to a message', async () => {
    const { user } = draw({ kind: 'reply', message: MESSAGE, all: false }, '');

    expect(await lines(user)).toEqual(['workbench.assist.mail.reply']);
  });

  it('offers what can be done with words already written', async () => {
    const { user } = draw({ kind: 'new' }, `Hello${SIGNATURE}`);

    expect(await lines(user)).toEqual([
      'workbench.assist.writing.tones.fix',
      'workbench.assist.writing.tones.shorter',
      'workbench.assist.writing.tones.formal',
      'workbench.assist.writing.tones.warm',
      'workbench.assist.writing.translate',
    ]);
  });

  it('offers a subject for those words beside the subject, and only there', async () => {
    const { user } = draw({ kind: 'new' }, `Hello${SIGNATURE}`, '', 'subject');

    expect(await lines(user)).toEqual(['workbench.assist.writing.subject']);
  });

  it('writes the whole message from beside the subject, before any words', async () => {
    const { user } = draw({ kind: 'new' }, SIGNATURE, '', 'subject');

    expect(await lines(user)).toEqual(['workbench.assist.writing.compose']);
  });

  it('does not ask twice: a reply opened with its proposal asks from the message alone', async () => {
    draw({ kind: 'reply', message: MESSAGE, all: false, propose: true }, '', '', 'subject');

    await new Promise(resolve => setTimeout(resolve, 10));
    expect(post).not.toHaveBeenCalled();
  });

  it('offers no subject where the answer keeps its message’s', async () => {
    const { user } = draw({ kind: 'reply', message: MESSAGE, all: false }, 'Hello');

    expect(await lines(user)).not.toContain('workbench.assist.writing.subject');
  });

  it('rewrites the person’s words, the signature left out', async () => {
    const { user } = draw({ kind: 'new' }, `Hello${SIGNATURE}`);

    await lines(user);
    await user.click(screen.getByRole('menuitem', { name: 'workbench.assist.writing.tones.fix' }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][1]).toEqual({ text: 'Hello', tone: 'fix' });
  });

  it('writes the whole message for whom it is, and hands body and subject back', async () => {
    const { user, onBody } = draw({ kind: 'new' }, '', 'ana@example.org');

    await lines(user);
    await user.click(screen.getByRole('menuitem', { name: 'workbench.assist.writing.compose' }));
    await user.type(screen.getByRole('textbox'), 'Invite her');
    await user.click(screen.getByRole('button', { name: 'workbench.assist.writing.ask' }));
    await user.click(await screen.findByRole('button', { name: 'workbench.assist.writing.use' }));

    expect(post.mock.calls[0][1]).toEqual({
      instruction: 'Invite her',
      recipient: 'ana@example.org',
    });
    expect(onBody).toHaveBeenCalledTimes(1);
    expect(onBody.mock.calls[0][0].text).toBe('Proposed');
  });

  it('puts a proposed subject in the subject alone, in one word', async () => {
    const { user, onBody, onSubject } = draw({ kind: 'new' }, 'Hello', '', 'subject');

    await lines(user);
    await user.click(screen.getByRole('menuitem', { name: 'workbench.assist.writing.subject' }));
    await user.click(await screen.findByRole('button', { name: 'workbench.assist.writing.use' }));

    expect(onSubject).toHaveBeenCalledWith('Proposed');
    expect(onBody).not.toHaveBeenCalled();
  });

  it('opens by itself where the reader asked for a proposal', async () => {
    draw({ kind: 'reply', message: MESSAGE, all: false, propose: true }, '');

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][0]).toBe('/tool-assists/mail/reply');
  });

  it('asks nothing by itself otherwise', async () => {
    draw({ kind: 'reply', message: MESSAGE, all: false }, '');

    await new Promise(resolve => setTimeout(resolve, 10));

    expect(post).not.toHaveBeenCalled();
  });
});
