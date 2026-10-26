import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { WorldMailboxClient } from '../mailbox-client';
import { PUBLIC_THREAD } from '../public-message-protocol';
const id = '11111111-1111-4111-8111-111111111111',
  second = '22222222-2222-4222-8222-222222222222';
const scope = { epoch: id, controller: 'c'.repeat(32) };
const mailbox = {
  server_time: 1000,
  ttl_seconds: 1800,
  truncated: false,
  messages: [],
  public_available: true,
  public_truncated: false,
  public_messages: [],
};
beforeEach(() => {
  vi.useFakeTimers();
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});
it('never replays a public send after a lost acknowledgement and never puts a UI thread key on the wire', async () => {
  let sentId = '';
  const request = vi.fn(async (path: string, body: unknown) => {
    if (path.endsWith('/public')) {
      if (body && typeof body === 'object' && 'id' in body) sentId = String(body.id);
      throw new Error('lost');
    }
    if (path.endsWith('/status')) return { id: sentId, status: 'uncertain' };
    return mailbox;
  });
  const client = new WorldMailboxClient({ request, getScope: () => scope, onState: vi.fn() });
  client.start();
  await vi.advanceTimersByTimeAsync(0);
  expect(await client.sendPublic('Hello everyone', true)).toBe('uncertain');
  await vi.advanceTimersByTimeAsync(30000);
  await client.check();
  expect(await client.sendPublic('Hello everyone', true)).toBe('uncertain');
  const calls = request.mock.calls.filter(([path]) => path.endsWith('/public'));
  expect(calls).toHaveLength(1);
  expect(calls[0][1]).toMatchObject({ audience: 'public', text: 'Hello everyone' });
  expect(calls[0][1]).not.toHaveProperty('recipient');
  expect(JSON.stringify(calls[0][1])).not.toContain(PUBLIC_THREAD);
  client.stop();
  expect(vi.getTimerCount()).toBe(0);
});
it('reading the public channel does not mark a private thread read', async () => {
  const common = {
    sender_id: id,
    sender_alias: 'Peer',
    outgoing: false,
    original: 'Hello',
    text: 'Hello',
    language: 'en',
    status: 'original',
    created_at: 1000,
    expires_at: 2800,
    receipt: null,
  };
  const response = {
    ...mailbox,
    messages: [{ ...common, id, recipient_id: second, recipient_alias: 'Owner' }],
    public_messages: [{ ...common, id: second, audience: 'public' }],
  };
  const client = new WorldMailboxClient({
    request: async () => response,
    getScope: () => scope,
    onState: vi.fn(),
  });
  client.start();
  await vi.advanceTimersByTimeAsync(0);
  expect(client.state.unread).toBe(2);
  client.setReading(true, PUBLIC_THREAD);
  expect(client.state.unreadByRecipient[id]).toBe(1);
  expect(client.state.unreadByRecipient[PUBLIC_THREAD] ?? 0).toBe(0);
  client.setReading(true, id);
  expect(client.state.unread).toBe(0);
  client.stop();
});

it('clears an unverifiable public substream without disabling private messages', async () => {
  let available = true;
  const onState = vi.fn();
  const request = vi.fn(async () =>
    available
      ? {
          ...mailbox,
          public_messages: [
            {
              audience: 'public',
              id,
              sender_id: second,
              sender_alias: 'Peer',
              outgoing: false,
              original: 'Hello',
              text: 'Hello',
              language: 'en',
              status: 'original',
              created_at: 1000,
              expires_at: 2800,
              receipt: null,
            },
          ],
        }
      : { ...mailbox, public_available: false }
  );
  const client = new WorldMailboxClient({ request, getScope: () => scope, onState });
  client.start();
  await vi.advanceTimersByTimeAsync(0);
  expect(client.state.mailbox?.public_messages).toHaveLength(1);
  available = false;
  await vi.advanceTimersByTimeAsync(3000);
  expect(client.state.status).toBe('online');
  expect(client.state.mailbox?.public_messages).toEqual([]);
  expect(client.state.mailbox?.public_available).toBe(false);
  expect(await client.sendPublic('Hello', true)).toBe('unavailable');
  client.stop();
});
