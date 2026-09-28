/**
 * Sending by e-mail — the pure half (ADR-321).
 *
 * What the dialog decides before it asks the server anything: whether the
 * action is offered, whom the typed field names, what the file weighs, and
 * which sentence a refusal becomes.
 */

import { describe, expect, it } from 'vitest';

import {
  checkShare,
  emailShareAvailable,
  emailShareErrorKey,
  invalidRecipients,
  parseRecipients,
  requestBody,
  sourceName,
  sourceSize,
  type EmailShareOptions,
} from '@/lib/email-share/share';

describe('emailShareAvailable', () => {
  it('reads the EFFECTIVE state: the operator switch wins over the ceiling', () => {
    expect(
      emailShareAvailable({
        features: { email_share_enabled: true },
        capabilities: { email_share: { enabled: false, family: 'reach' } },
      })
    ).toBe(false);
  });

  it('falls back to the ceiling when an older API publishes no capability map', () => {
    expect(emailShareAvailable({ features: { email_share_enabled: true } })).toBe(true);
    expect(emailShareAvailable({ features: {} })).toBe(false);
    expect(emailShareAvailable(null)).toBe(false);
  });
});

describe('recipients', () => {
  it('splits on commas, semicolons and spaces, and names each address once', () => {
    expect(
      parseRecipients(' bob@example.com, eve@example.com;  BOB@example.com\nzoe@x.io ')
    ).toEqual(['bob@example.com', 'eve@example.com', 'zoe@x.io']);
    expect(parseRecipients('  ')).toEqual([]);
  });

  it('points at what is not an address, and only that', () => {
    expect(invalidRecipients(['bob@example.com', 'bob', 'a@b', 'x y@z.io'])).toEqual([
      'bob',
      'a@b',
      'x y@z.io',
    ]);
  });
});

describe('the source', () => {
  it('weighs an answer in UTF-8 bytes, the way the server counts it', () => {
    const answer = { kind: 'markdown' as const, filename: 'lia-2026-09-25-10-00', text: 'Été' };

    expect(sourceSize(answer)).toBe(5);
    expect(sourceName(answer)).toBe('lia-2026-09-25-10-00.md');
  });

  it('knows a file only by what the card told it', () => {
    expect(sourceSize({ kind: 'file', attachmentId: 'a', name: 'x.png' })).toBeNull();
    expect(sourceSize({ kind: 'file', attachmentId: 'a', name: 'x.png', sizeBytes: 42 })).toBe(42);
  });

  it('builds the request the API reads: blank words become none', () => {
    expect(
      requestBody(
        { kind: 'file', attachmentId: 'id-1', name: 'x.png' },
        ['bob@example.com'],
        ' Sujet ',
        '   '
      )
    ).toEqual({
      recipients: ['bob@example.com'],
      subject: 'Sujet',
      message: null,
      attachment: { kind: 'file', attachment_id: 'id-1' },
    });
    expect(
      requestBody({ kind: 'markdown', filename: 'lia-x', text: '# Hi' }, [], 'S', 'Mot').attachment
    ).toEqual({ kind: 'markdown', filename: 'lia-x', text: '# Hi' });
  });
});

describe('emailShareErrorKey', () => {
  it('translates every code the API names, and falls back for anything else', () => {
    expect(emailShareErrorKey('email_share_too_large')).toBe('email_share.errors.too_large');
    expect(emailShareErrorKey('email_share_mailbox_reconnect')).toBe(
      'email_share.errors.mailbox_reconnect'
    );
    expect(emailShareErrorKey('something_else')).toBe('email_share.errors.generic');
    expect(emailShareErrorKey(undefined)).toBe('email_share.errors.generic');
  });

  it('names the rate limit, which answers with a status and no code', () => {
    expect(emailShareErrorKey(undefined, 429)).toBe('email_share.errors.rate_limited');
  });
});

describe('checkShare', () => {
  const mailbox: EmailShareOptions = {
    route: 'mailbox',
    own_address: null,
    mailbox_needs_reconnect: false,
    max_file_bytes: 10,
    max_recipients: 2,
    subject_max_chars: 200,
    message_max_chars: 5000,
  };
  const note = { kind: 'markdown' as const, filename: 'lia-x', text: 'abc' };

  it('is ready with a subject and valid recipients', () => {
    const check = checkShare(mailbox, note, 'bob@example.com', 'Sujet');

    expect(check).toMatchObject({ recipients: ['bob@example.com'], ready: true });
  });

  it('holds on no recipient, a wrong one, too many, a blank subject', () => {
    expect(checkShare(mailbox, note, '', 'S').ready).toBe(false);
    expect(checkShare(mailbox, note, 'bob', 'S')).toMatchObject({ invalid: ['bob'], ready: false });
    expect(checkShare(mailbox, note, 'a@x.io b@x.io c@x.io', 'S')).toMatchObject({
      tooMany: true,
      ready: false,
    });
    expect(checkShare(mailbox, note, 'bob@example.com', '   ').ready).toBe(false);
  });

  it('holds on a file heavier than the road, and never guesses an unknown size', () => {
    const heavy = { kind: 'markdown' as const, filename: 'x', text: 'a'.repeat(11) };
    const unknown = { kind: 'file' as const, attachmentId: 'id', name: 'x.png' };

    expect(checkShare(mailbox, heavy, 'bob@example.com', 'S')).toMatchObject({
      tooLarge: true,
      ready: false,
    });
    expect(checkShare(mailbox, unknown, 'bob@example.com', 'S').ready).toBe(true);
  });

  it('carries no recipient on the relay road: the server writes to the account itself', () => {
    const relay: EmailShareOptions = { ...mailbox, route: 'relay', own_address: 'me@x.io' };

    expect(checkShare(relay, note, 'ignored@x.io', 'S')).toMatchObject({
      recipients: [],
      ready: true,
    });
  });

  it('never offers a send without a road', () => {
    const none: EmailShareOptions = { ...mailbox, route: 'unavailable' };

    expect(checkShare(none, note, 'bob@example.com', 'S').ready).toBe(false);
  });
});
