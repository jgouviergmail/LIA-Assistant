/**
 * The closed classification contract the web reads (ADR-374): v2 adds whether an e-mail
 * expects a reply; an annotation of v1 — archived in a thread — is still read, never
 * re-classified.
 */
import { describe, expect, it } from 'vitest';
import { readClassification } from '@/lib/content-classification';

const stamp = {
  kind: 'email',
  category: 'professional',
  priority: 'normal',
  evidence_scope: 'snippet',
  evaluated_at: '2026-11-08T10:00:00Z',
  valid_until: '2026-11-08T10:05:00Z',
} as const;

describe('readClassification', () => {
  it('still reads an annotation of the former version', () => {
    const read = readClassification({ ...stamp, version: 'email-event-v1-phishing' });
    expect(read?.kind).toBe('email');
  });

  it('reads the current version with and without a reply verdict', () => {
    const decided = readClassification({
      ...stamp,
      version: 'email-event-v2-reply',
      reply_expected: true,
    });
    expect(decided?.kind === 'email' && decided.reply_expected).toBe(true);
    const undecided = readClassification({ ...stamp, version: 'email-event-v2-reply' });
    expect(undecided?.kind === 'email' && undecided.reply_expected).toBeFalsy();
    expect(
      readClassification({ ...stamp, version: 'email-event-v2-reply', reply_expected: null })
    ).not.toBeNull();
  });

  it('refuses a reply verdict that is no boolean, and an unknown version', () => {
    expect(
      readClassification({ ...stamp, version: 'email-event-v2-reply', reply_expected: 'yes' })
    ).toBeNull();
    expect(readClassification({ ...stamp, version: 'email-event-v3' })).toBeNull();
  });

  it('gives an event no reply verdict', () => {
    const event = {
      version: 'email-event-v2-reply',
      kind: 'event',
      category: 'personal',
      evidence_scope: 'event',
      evaluated_at: stamp.evaluated_at,
      valid_until: stamp.valid_until,
    };
    expect(readClassification(event)).not.toBeNull();
    expect(readClassification({ ...event, reply_expected: true })).toBeNull();
  });
});
