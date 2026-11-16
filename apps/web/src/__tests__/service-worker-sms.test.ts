/** Execute the real worker handlers with synthetic Push API clients. */
import { expect, it, vi } from 'vitest';

import { worker } from './service-worker-harness';

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
