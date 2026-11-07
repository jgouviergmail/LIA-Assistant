/**
 * What a composer does with a send that did not answer « sent » (ADR-369,
 * ADR-221, Review focus 3).
 *
 * An outcome nobody knows is never retried by the page: the content stays and
 * the person is told to look in Sent. A first submission already done is a
 * message sent. A recipient that cannot be read is said under its own field.
 * Anything else is a refusal the person may fix — the server freed the key.
 */

import { describe, expect, it } from 'vitest';

import { ApiError } from '@/lib/api-client';

import {
  composeFailure,
  DRIVE_ORIGIN,
  filesToSend,
  fittingFiles,
  initialFields,
  ownWords,
  withProposal,
  keptFiles,
  linkOf,
  localProblem,
  recipientsOf,
  textToHtml,
  writes,
  type ComposerTarget,
  parseMailTo,
} from '../mail-compose';
import type { AttachableFile, MailAttachment, MailDraft, MailMessage } from '../types';

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

const DRAFT: MailDraft = {
  id: 'd1',
  revision: 'r1',
  sender: null,
  to: [
    { name: 'Ana', address: 'ana@example.org' },
    { name: '', address: 'bob@example.org' },
  ],
  cc: [],
  bcc: [{ name: '', address: 'carla@example.org' }],
  subject: 'Plan',
  body: 'Draft text',
  attachments: [],
  updated_at: null,
};

function refused(status: number, detail: Record<string, unknown>): ApiError {
  return new ApiError('refused', status, { detail });
}

describe('LIA’s words in the composer', () => {
  const SIGNATURE = '\n\n-- \nAna';
  const fields = (body: string, html: string | null = null) => ({
    ...initialFields({ kind: 'new' }),
    body,
    html,
  });

  it('reads the person’s words apart from the signature', () => {
    expect(ownWords(fields(SIGNATURE), SIGNATURE)).toBe('');
    expect(ownWords(fields(`Hello${SIGNATURE}`), SIGNATURE)).toBe('Hello');
    expect(ownWords(fields('Hello'), SIGNATURE)).toBe('Hello');
  });

  it('keeps the signature last when the words replace the person’s', () => {
    const change = withProposal(fields(`Mine${SIGNATURE}`), SIGNATURE, 'Yours', 'replace');

    expect(change.body).toBe(`Yours${SIGNATURE}`);
  });

  it('keeps the person’s words first when they add to them', () => {
    const change = withProposal(fields(`Mine${SIGNATURE}`), SIGNATURE, 'Yours', 'add');

    expect(change.body).toBe(`Mine\n\nYours${SIGNATURE}`);
  });

  it('keeps what the person formatted when the words follow theirs', () => {
    const signed = textToHtml(SIGNATURE);
    const held = { ...fields(`Mine${SIGNATURE}`), html: `<b>Mine</b>${signed}` };

    const change = withProposal(held, SIGNATURE, 'You & me', 'add');

    expect(change.html).toBe(`<b>Mine</b><br><br>You &amp; me${signed}`);
  });

  it('writes the page anew when the words replace the person’s', () => {
    const held = { ...fields(`Mine${SIGNATURE}`), html: `<b>Mine</b>${textToHtml(SIGNATURE)}` };

    const change = withProposal(held, SIGNATURE, 'Yours', 'replace');

    expect(change.html).toBe(textToHtml(`Yours${SIGNATURE}`));
  });

  it('never leaves the signature above the words of a page it cannot read', () => {
    const held = { ...fields(`Mine${SIGNATURE}`), html: '<div>Mine</div><div>signed</div>' };

    const change = withProposal(held, SIGNATURE, 'Yours', 'add');

    expect(change.html).toBe(textToHtml(`Mine\n\nYours${SIGNATURE}`));
  });

  it('adds nothing but the words to a body that held none', () => {
    expect(withProposal(fields(''), '', 'Yours', 'add').body).toBe('Yours');
  });

  it('leaves a signature the person took off out', () => {
    expect(withProposal(fields('Mine'), SIGNATURE, 'Yours', 'replace').body).toBe('Yours');
  });

  it('writes the formatted words too when the body is formatted', () => {
    const change = withProposal(fields('Mine', '<b>Mine</b>'), '', 'Yours <now>', 'replace');

    expect(change.html).toBe('Yours &lt;now&gt;');
  });

  it('leaves the plain body plain', () => {
    expect(withProposal(fields('Mine'), '', 'Yours', 'replace').html).toBeNull();
  });
});

describe('parseMailTo', () => {
  it('reads the address and what the sender wants said', () => {
    expect(parseMailTo('leave@example.org?subject=stop%20it&body=Remove%20me')).toEqual({
      to: 'leave@example.org',
      subject: 'stop it',
      body: 'Remove me',
    });
  });

  it('takes an address alone', () => {
    expect(parseMailTo('leave@example.org')).toEqual({
      to: 'leave@example.org',
      subject: '',
      body: '',
    });
  });

  it('carries nothing else a stranger may have written', () => {
    expect(parseMailTo('leave@example.org?cc=boss@example.org&bcc=x@example.org').to).toBe(
      'leave@example.org'
    );
  });
});

describe('composeFailure', () => {
  it('reads a lost answer as an outcome nobody knows', () => {
    expect(composeFailure(refused(504, { code: 'outcome_unknown' }))).toEqual({ kind: 'unknown' });
  });

  it.each(['unknown', 'pending'])(
    'reads a second press while the first is %s as an outcome nobody knows',
    outcome => {
      expect(composeFailure(refused(409, { code: 'already_submitted', outcome }))).toEqual({
        kind: 'unknown',
      });
    }
  );

  it('reads a first submission already done as a message sent', () => {
    expect(composeFailure(refused(409, { code: 'already_submitted', outcome: 'done' }))).toEqual({
      kind: 'already_sent',
    });
  });

  it('puts an unreadable recipient under its own field, at its place', () => {
    expect(
      composeFailure(refused(422, { code: 'invalid_recipient', field: 'cc', index: 1 }))
    ).toEqual({
      kind: 'recipient',
      field: 'cc',
      refusal: { key: 'workbench.errors.invalid_recipient_at', values: { position: 2 } },
    });
  });

  it('reads a recipient refusal naming no field it knows as a plain refusal', () => {
    expect(composeFailure(refused(422, { code: 'invalid_recipient', field: 'from' }))).toEqual({
      kind: 'refused',
      refusal: { key: 'workbench.errors.invalid_recipient' },
    });
  });

  it('reads anything else as a refusal the person may fix', () => {
    expect(
      composeFailure(refused(429, { code: 'provider_rate_limited', retry_after: 30 }))
    ).toEqual({
      kind: 'refused',
      refusal: { key: 'workbench.errors.provider_rate_limited_wait', values: { seconds: 30 } },
    });
    expect(composeFailure(new Error('network'))).toEqual({ kind: 'refused', refusal: null });
  });
});

describe('recipientsOf', () => {
  it('reads a field as the addresses typed, each once', () => {
    expect(recipientsOf(' ana@example.org, bob@example.org; ana@example.org ')).toEqual([
      'ana@example.org',
      'bob@example.org',
    ]);
    expect(recipientsOf('   ')).toEqual([]);
  });
});

describe('a drive file', () => {
  const FILE = {
    id: 'f1',
    filename: 'Report.pdf',
    mime_type: 'application/pdf',
    size: 3,
    origin: DRIVE_ORIGIN,
    expires_at: null,
  };

  it('starts a new message with what was handed to it', () => {
    expect(initialFields({ kind: 'new', files: [FILE] }).files).toEqual([FILE]);
  });

  it('is sent apart from the person’s own files', () => {
    const own = { ...FILE, id: 'a1', origin: 'upload' };

    expect(filesToSend([own, FILE])).toEqual({ attachment_ids: ['a1'], drive_file_ids: ['f1'] });
  });
});

describe('the composer’s targets', () => {
  it('opens a draft on what it holds, every other target empty', () => {
    expect(initialFields({ kind: 'draft', draft: DRAFT })).toEqual({
      to: 'ana@example.org, bob@example.org',
      cc: '',
      bcc: 'carla@example.org',
      subject: 'Plan',
      body: 'Draft text',
      files: [],
      removedFiles: [],
      sendAs: '',
      html: null,
    });
    expect(initialFields({ kind: 'reply', message: MESSAGE, all: false }).body).toBe('');
  });

  it('writes only what each target carries', () => {
    expect(writes({ kind: 'new' })).toEqual({
      recipients: true,
      bcc: true,
      subject: true,
      files: true,
    });
    expect(writes({ kind: 'draft', draft: DRAFT })).toEqual({
      recipients: true,
      bcc: true,
      subject: true,
      files: true,
    });
    expect(writes({ kind: 'forward', message: MESSAGE })).toEqual({
      recipients: true,
      bcc: false,
      subject: false,
      files: true,
    });
    expect(writes({ kind: 'reply', message: MESSAGE, all: true })).toEqual({
      recipients: false,
      bcc: false,
      subject: false,
      files: true,
    });
  });

  it('writes the recipients of a reply once it knows who it reaches', () => {
    const reply: ComposerTarget = { kind: 'reply', message: MESSAGE, all: true };

    expect(writes(reply, true).recipients).toBe(true);
    expect(writes(reply, true).bcc).toBe(false);
  });
});

describe('textToHtml', () => {
  it('keeps the words as words, and the lines', () => {
    expect(textToHtml('a <b> & c\nd')).toBe('a &lt;b&gt; &amp; c<br>d');
  });

  it('leaves nothing as nothing', () => {
    expect(textToHtml('')).toBe('');
  });
});

describe('linkOf', () => {
  it.each([
    ['https://example.org/a', 'https://example.org/a'],
    ['HTTP://example.org', 'HTTP://example.org'],
    ['mailto:ana@example.org', 'mailto:ana@example.org'],
    ['example.org/a', 'https://example.org/a'],
    ['  example.org  ', 'https://example.org'],
    ['ana@example.org', 'mailto:ana@example.org'],
  ])('reads %s as an address people can follow', (typed, address) => {
    expect(linkOf(typed)).toBe(address);
  });

  it.each(['', '   ', 'javascript:alert(1)', 'data:text/html,x', 'vbscript:x', 'file:///etc'])(
    'refuses %j',
    typed => {
      expect(linkOf(typed)).toBeNull();
    }
  );
});

describe('initialFields — a signature', () => {
  const BLOCK = '\n\n-- \nAna';

  it('closes a new message, the words to write above it', () => {
    expect(initialFields({ kind: 'new' }, BLOCK).body).toBe(BLOCK);
  });

  it('follows the words a message opens on', () => {
    expect(initialFields({ kind: 'new', body: 'Hello' }, BLOCK).body).toBe(`Hello${BLOCK}`);
  });

  it('closes an answer too', () => {
    expect(initialFields({ kind: 'reply', message: MESSAGE, all: false }, BLOCK).body).toBe(BLOCK);
    expect(initialFields({ kind: 'forward', message: MESSAGE }, BLOCK).body).toBe(BLOCK);
  });

  it('leaves a draft as it was written', () => {
    expect(initialFields({ kind: 'draft', draft: DRAFT }, BLOCK).body).toBe('Draft text');
  });
});

describe('keptFiles', () => {
  const file = (filename: string): MailAttachment => ({
    id: null,
    filename,
    mime_type: 'text/plain',
    size: 1,
  });

  it('takes one file per name, the first bearing it', () => {
    expect(keptFiles([file('a'), file('a'), file('b')], ['a']).map(item => item.filename)).toEqual([
      'a',
      'b',
    ]);
  });

  it('leaves everything to a name no file bears', () => {
    expect(keptFiles([file('a'), file('b')], ['gone']).map(item => item.filename)).toEqual([
      'a',
      'b',
    ]);
  });
});

describe('fittingFiles', () => {
  const bounds = { maxFiles: 3, maxBytes: 100, eachMaxBytes: 60 };
  const held = (size: number): AttachableFile => ({
    id: `f${size}`,
    filename: 'kept.pdf',
    mime_type: 'application/pdf',
    size,
    origin: 'upload',
    expires_at: null,
  });
  const device = (name: string, size: number) => new File(['x'.repeat(size)], name);

  it('takes what fits, in the order it came', () => {
    const { fitting, over } = fittingFiles([device('a', 10), device('b', 20)], [], bounds);

    expect(fitting.map(file => file.name)).toEqual(['a', 'b']);
    expect(over).toBeNull();
  });

  it('counts what the message already carries', () => {
    const { fitting, over } = fittingFiles([device('a', 10)], [held(1), held(2), held(3)], bounds);

    expect(fitting).toEqual([]);
    expect(over).toEqual({ kind: 'count', name: 'a' });
  });

  it('adds up the bytes, and leaves out only what passes them', () => {
    const { fitting, over } = fittingFiles(
      [device('a', 50), device('b', 50), device('c', 10)],
      [held(30)],
      bounds
    );

    expect(fitting.map(file => file.name)).toEqual(['a', 'c']);
    expect(over).toEqual({ kind: 'bytes', name: 'b' });
  });

  it('says a file past what one upload takes by its name', () => {
    expect(fittingFiles([device('big', 61)], [], bounds).over).toEqual({
      kind: 'each',
      name: 'big',
    });
  });
});

describe('localProblem', () => {
  const empty = initialFields({ kind: 'new' });
  const target: ComposerTarget = { kind: 'new' };

  it('asks for someone to write to before anything is sent', () => {
    expect(localProblem(empty, target, 100)).toEqual({
      field: 'to',
      key: 'workbench.mail.compose.no_recipient',
    });
    expect(localProblem({ ...empty, bcc: 'a@example.org' }, target, 100)).toBeNull();
  });

  it('states the published bound on a field that passes it', () => {
    const many = Array.from({ length: 3 }, (_, index) => `p${index}@example.org`).join(', ');

    expect(localProblem({ ...empty, cc: many, to: 'a@example.org' }, target, 2)).toEqual({
      field: 'cc',
      key: 'workbench.mail.compose.too_many',
      values: { count: 2 },
    });
  });

  it('asks a forward for someone in To: the server forwards to them, a copy alone is no one', () => {
    expect(
      localProblem({ ...empty, cc: 'a@example.org' }, { kind: 'forward', message: MESSAGE }, 100)
    ).toEqual({ field: 'to', key: 'workbench.mail.compose.no_recipient' });
  });

  it('asks nothing of a reply nobody has read the recipients of: the provider computes them', () => {
    expect(localProblem(empty, { kind: 'reply', message: MESSAGE, all: false }, 100)).toBeNull();
  });

  it('asks a reply for someone in To once the person can see who it reaches', () => {
    const reply: ComposerTarget = { kind: 'reply', message: MESSAGE, all: false };

    expect(localProblem({ ...empty, cc: 'a@example.org' }, reply, 100, true)).toEqual({
      field: 'to',
      key: 'workbench.mail.compose.no_recipient',
    });
    expect(localProblem({ ...empty, to: 'a@example.org' }, reply, 100, true)).toBeNull();
  });
});
