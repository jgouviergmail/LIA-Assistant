/** Execute the real worker handlers with synthetic Push API clients. */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { runInNewContext } from 'node:vm';
import { expect, it, vi } from 'vitest';
const source = readFileSync(join(process.cwd(), 'public/firebase-messaging-sw.js'), 'utf8');
interface Event {
  data?: { json: () => unknown; text: () => string };
  notification?: { data: Record<string, string>; close: () => void };
  waitUntil: (promise: Promise<unknown>) => void;
}
function worker() {
  const handlers = new Map<string, (event: Event) => void>();
  const showNotification = vi.fn<
    (title: string, options: { tag: string; data: Record<string, string> }) => Promise<void>
  >(async () => {});
  const client = {
    url: 'https://lia.test/en/dashboard',
    navigate: vi.fn(async (_url: string) => null),
    focus: vi.fn(async () => {}),
  };
  const openWindow = vi.fn(async (_url: string) => null);
  const output = { log: vi.fn(), error: vi.fn() };
  runInNewContext(source, {
    self: {
      location: { origin: 'https://lia.test' },
      registration: { showNotification },
      addEventListener: (type: string, callback: (event: Event) => void) =>
        handlers.set(type, callback),
    },
    clients: { matchAll: async () => [client], openWindow },
    URL,
    console: output,
  });
  async function emit(type: string, event: Omit<Event, 'waitUntil'>) {
    const pending: Promise<unknown>[] = [];
    const handler = handlers.get(type);
    if (!handler) throw new Error('Missing worker handler');
    handler({
      ...event,
      waitUntil: promise => {
        pending.push(promise);
      },
    });
    await Promise.all(pending);
  }
  return { emit, showNotification, client, openWindow, output };
}
it('uses the SMS occurrence as its collapse tag without logging the push payload', async () => {
  const app = worker();
  const data = {
    type: 'sms_received',
    occurrence_id: 'opaque-receipt',
    message_id: 'opaque-message',
    user_id: 'private-owner-id',
    url: '/en/dashboard/sms?message=opaque-message',
  };
  const payload = { notification: { title: 'Notice', body: 'Generic notice' }, data };
  await app.emit('push', { data: { json: () => payload, text: () => '' } });
  await app.emit('push', { data: { json: () => payload, text: () => '' } });
  expect(app.showNotification.mock.calls[0][1].tag).toBe('sms:opaque-receipt');
  expect(app.showNotification.mock.calls[1][1].tag).toBe('sms:opaque-receipt');
  expect(JSON.stringify(app.output.log.mock.calls)).not.toContain('private-owner-id');
});
it('navigates an existing app window to the protected SMS destination before focusing it', async () => {
  const app = worker();
  await app.emit('notificationclick', {
    notification: { data: { url: '/en/dashboard/sms?message=opaque-message' }, close: vi.fn() },
  });
  expect(app.client.navigate).toHaveBeenCalledWith(
    'https://lia.test/en/dashboard/sms?message=opaque-message'
  );
  expect(app.client.focus).toHaveBeenCalledOnce();
  expect(app.openWindow).not.toHaveBeenCalled();
});
it.each(['https://outside.test/steal', 'javascript:alert(1)', '/api/v1/sms'])(
  'refuses a notification destination outside the protected app: %s',
  async url => {
    const app = worker();
    await app.emit('notificationclick', { notification: { data: { url }, close: vi.fn() } });
    expect(app.client.navigate).toHaveBeenCalledWith('https://lia.test/en/dashboard/chat');
    expect(app.openWindow).not.toHaveBeenCalled();
  }
);
