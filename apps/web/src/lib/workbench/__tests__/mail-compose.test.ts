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
  initialFields,
  localProblem,
  recipientsOf,
  writes,
  type ComposerTarget,
} from '../mail-compose';
import type { MailDraft, MailMessage } from '../types';

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

const DRAFT: MailDraft = {
  id: 'd1',
  revision: 'r1',
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

describe('the composer’s targets', () => {
  it('opens a draft on what it holds, every other target empty', () => {
    expect(initialFields({ kind: 'draft', draft: DRAFT })).toEqual({
      to: 'ana@example.org, bob@example.org',
      cc: '',
      bcc: 'carla@example.org',
      subject: 'Plan',
      body: 'Draft text',
      files: [],
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
      files: false,
    });
    expect(writes({ kind: 'forward', message: MESSAGE })).toEqual({
      recipients: true,
      bcc: false,
      subject: false,
      files: false,
    });
    expect(writes({ kind: 'reply', message: MESSAGE, all: true })).toEqual({
      recipients: false,
      bcc: false,
      subject: false,
      files: false,
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

  it('asks nothing of a reply: its recipients are the message’s', () => {
    expect(localProblem(empty, { kind: 'reply', message: MESSAGE, all: false }, 100)).toBeNull();
  });
});
