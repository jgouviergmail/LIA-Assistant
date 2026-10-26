import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { WorldMailboxClient, type MailboxPayload } from '../mailbox-client';
import type { MailboxScope, WorldMessage } from '../message-protocol';
import { ApiError } from '@/lib/api-client';

const id = '4010c2c2-4bd0-4d21-9c08-b4502db25d72';
const scope: MailboxScope = { epoch: id, controller: 'c'.repeat(43) };
const mailbox = { server_time: 1000, ttl_seconds: 1800, messages: [], truncated: false };

beforeEach(() => {
  vi.useFakeTimers();
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

it('never resubmits an uncertain paid send while polling or checking its status', async () => {
  let sentId = '';
  const request = vi.fn(async (endpoint: string, body: unknown) => {
    if (endpoint.endsWith('/send')) {
      if (body && typeof body === 'object' && 'id' in body) sentId = String(body.id);
      throw new Error('uncertain network fixture');
    }
    if (endpoint.endsWith('/status')) return { id: sentId, status: 'uncertain' };
    return mailbox;
  });
  const client = new WorldMailboxClient({ request, getScope: () => scope, onState: vi.fn() });
  client.start();
  await vi.advanceTimersByTimeAsync(0);
  expect(await client.send(id, 'Bonjour', true)).toBe('uncertain');
  await vi.advanceTimersByTimeAsync(30000);
  expect(await client.send(id, 'Bonjour', true)).toBe('uncertain');
  await client.check();
  expect(client.state.sending).toBe('uncertain');
  expect(request.mock.calls.filter(([path]) => path.endsWith('/send'))).toHaveLength(1);
  client.discard();
  expect(request.mock.calls.filter(([path]) => path.endsWith('/send'))).toHaveLength(1);
  client.stop();
  expect(vi.getTimerCount()).toBe(0);
});

it('aborts owned reads and discards a reply that arrives after disposal', async () => {
  const response = Promise.withResolvers<unknown>();
  let signal: AbortSignal | undefined;
  const onState = vi.fn();
  const request = vi.fn((_endpoint: string, _body: unknown, value: AbortSignal) => {
    signal = value;
    return response.promise;
  });
  const client = new WorldMailboxClient({ request, getScope: () => scope, onState });
  client.start();
  client.stop();
  const publications = onState.mock.calls.length;
  expect(signal?.aborted).toBe(true);
  response.resolve(mailbox);
  await vi.advanceTimersByTimeAsync(0);
  expect(onState).toHaveBeenCalledTimes(publications);
  expect(client.state.mailbox).toBeNull();
  expect(vi.getTimerCount()).toBe(0);
});

it('refuses a response from an obsolete controller even within the same account', async () => {
  const response = Promise.withResolvers<unknown>();
  let current = scope;
  const client = new WorldMailboxClient({
    request: () => response.promise,
    getScope: () => current,
    onState: vi.fn(),
  });
  client.start();
  current = { ...scope, controller: 'new-controller-token' };
  response.resolve(mailbox);
  await vi.advanceTimersByTimeAsync(0);
  expect(client.state.mailbox).toBeNull();
  client.stop();
});

it('bounds failed read retries and never turns reconnection into a write', async () => {
  const request = vi.fn(async () => {
    throw new Error('unavailable fixture');
  });
  const client = new WorldMailboxClient({ request, getScope: () => scope, onState: vi.fn() });
  client.start();
  await vi.advanceTimersByTimeAsync(600000);
  expect(request.mock.calls.length).toBeLessThanOrEqual(5);
  expect(client.state.status).toBe('unavailable');
  client.stop();
  expect(vi.getTimerCount()).toBe(0);
});

it('requests an owned translation by message id without resending its original text', async () => {
  const onAccepted = vi.fn();
  const request = vi.fn(async (endpoint: string, body: unknown) => {
    if (endpoint.endsWith('/translate') && body && typeof body === 'object' && 'id' in body)
      return { id: body.id, status: 'pending' };
    return mailbox;
  });
  const client = new WorldMailboxClient({
    request,
    getScope: () => scope,
    onState: vi.fn(),
    onAccepted,
  });
  client.start();
  await vi.advanceTimersByTimeAsync(0);
  expect(await client.translate(id, true)).toBe('accepted');
  const translation = request.mock.calls.find(([path]) => path.endsWith('/translate'));
  expect(translation?.[1]).toMatchObject({ message_id: id, translation_consent: true });
  expect(translation?.[1]).not.toHaveProperty('text');
  expect(onAccepted).not.toHaveBeenCalled();
  client.stop();
});

it('withdraws a revoked mailbox and requests cookie identity verification instead of retrying it', async () => {
  const onRevoked = vi.fn();
  const client = new WorldMailboxClient({
    request: async () => {
      throw new ApiError('unavailable', 403);
    },
    getScope: () => scope,
    onState: vi.fn(),
    onRevoked,
  });
  client.start();
  await vi.advanceTimersByTimeAsync(30000);
  expect(onRevoked).toHaveBeenCalledTimes(1);
  expect(client.state.mailbox).toBeNull();
  expect(client.state.unread).toBe(0);
  expect(client.state.status).toBe('unavailable');
  client.stop();
  expect(vi.getTimerCount()).toBe(0);
});

it.each(['accepted', 'lost', 'disposed'] as const)(
  'settles an owned write across a missing transport scope (%s) without resending',
  async outcome => {
    let current: MailboxScope | null = scope;
    let sentId = '';
    let delivered = false;
    const response = Promise.withResolvers<unknown>();
    const onAccepted = vi.fn();
    const request = vi.fn(async (endpoint: string, body: MailboxPayload) => {
      if (endpoint.endsWith('/send') && 'id' in body) {
        sentId = body.id;
        return response.promise;
      }
      return {
        ...mailbox,
        messages: delivered
          ? [
              {
                id: sentId,
                sender_id: id,
                sender_alias: 'Owner',
                recipient_id: id,
                recipient_alias: 'Peer',
                outgoing: true,
                original: 'Hello',
                text: 'Hello',
                language: 'en',
                status: 'original',
                created_at: 1000,
                expires_at: 2800,
                receipt: null,
              },
            ]
          : [],
      };
    });
    const client = new WorldMailboxClient({
      request,
      getScope: () => current,
      onState: vi.fn(),
      onAccepted,
    });
    client.start();
    await vi.advanceTimersByTimeAsync(0);
    const sending = client.send(id, 'Hello', true);
    current = null;
    if (outcome === 'disposed') client.stop();
    if (outcome === 'lost') response.reject(new Error('lost acknowledgment'));
    else response.resolve({ id: sentId, status: 'delivered' });
    expect(await sending).toBe(
      outcome === 'accepted' ? 'accepted' : outcome === 'lost' ? 'uncertain' : 'unavailable'
    );
    if (outcome !== 'disposed') {
      current = scope;
      delivered = true;
      await vi.advanceTimersByTimeAsync(3000);
      expect(client.state.sending).toBe('idle');
      expect(onAccepted).toHaveBeenCalledOnce();
    } else expect(onAccepted).not.toHaveBeenCalled();
    expect(request.mock.calls.filter(([path]) => path.endsWith('/send'))).toHaveLength(1);
    client.stop();
    expect(vi.getTimerCount()).toBe(0);
  }
);

it('only marks the visible conversation read, including messages arriving while it is open', async () => {
  const first = '5010c2c2-4bd0-4d21-9c08-b4502db25d72';
  const second = '6010c2c2-4bd0-4d21-9c08-b4502db25d72';
  const incoming = (n: number, sender: string): WorldMessage => ({
    id: `7010c2c2-4bd0-4d21-9c08-${String(n).padStart(12, '0')}`,
    sender_id: sender,
    recipient_id: id,
    sender_alias: 'Peer',
    recipient_alias: 'Owner',
    outgoing: false,
    original: 'Hello',
    text: 'Hello',
    language: 'en',
    status: 'original',
    created_at: 1000,
    expires_at: 2800,
    receipt: null,
  });
  const messages = [incoming(1, first), incoming(2, second)];
  const client = new WorldMailboxClient({
    getScope: () => scope,
    request: async () => ({ ...mailbox, messages }),
    onState: vi.fn(),
  });
  client.start();
  await vi.advanceTimersByTimeAsync(0);
  expect(client.state.unread).toBe(2);
  client.setReading(true, first);
  expect(client.state.unread).toBe(1);
  messages.push(incoming(3, first), incoming(4, second));
  await vi.advanceTimersByTimeAsync(3000);
  expect(client.state.unread).toBe(2);
  client.setReading(false, first);
  messages.push(incoming(5, first));
  await vi.advanceTimersByTimeAsync(3000);
  expect(client.state.unread).toBe(3);
  client.setReading(true, second);
  expect(client.state.unread).toBe(1);
  // The directory contains previews, not the full conversations.
  client.setReading(true);
  expect(client.state.unread).toBe(1);
  expect(client.state.unreadByRecipient).toEqual({ [first]: 1 });
  client.setReading(true, first);
  expect(client.state.unread).toBe(0);
  expect(client.state.unreadByRecipient).toEqual({});
  client.stop();
});
