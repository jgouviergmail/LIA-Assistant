import { expect, it } from 'vitest';
import { preparePublicMessage, PUBLIC_THREAD } from '../public-message-protocol';
import { readMailbox } from '../message-protocol';
const scope = { epoch: '11111111-1111-4111-8111-111111111111', controller: 'c'.repeat(32) };
const base = { server_time: 100, ttl_seconds: 1800, truncated: false, messages: [] };
it('prepares an explicit public audience without a synthetic recipient or account field', () => {
  const intent = preparePublicMessage(
    scope,
    'Bonjour',
    true,
    { serverSeconds: 100, receivedAt: 1000 },
    1100
  );
  expect(intent.audience).toBe('public');
  expect(intent.created_at).toBe(100.1);
  expect('recipient' in intent).toBe(false);
  expect(Object.values(intent)).not.toContain(PUBLIC_THREAD);
  expect(() =>
    preparePublicMessage(
      scope,
      'x'.repeat(241),
      true,
      { serverSeconds: 100, receivedAt: 1000 },
      1100
    )
  ).toThrow();
});
it('isolates malformed public content without discarding a valid private mailbox', () => {
  const result = readMailbox({
    ...base,
    public_available: true,
    public_truncated: false,
    public_messages: [{ owner_id: 'PRIVATE' }],
  });
  expect(result.messages).toEqual([]);
  expect(result.public_available).toBe(false);
  expect(result.public_messages).toEqual([]);
  expect(readMailbox(base)).toEqual(base);
});
