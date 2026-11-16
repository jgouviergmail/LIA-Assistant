/**
 * A reminder's push offers two « later », pressed with the person's own session
 * (ADR-268 amendment 2026-11-16). Run on the REAL worker file.
 */
import { describe, expect, it, vi } from 'vitest';

import { worker, type FetchAnswer } from './service-worker-harness';

const FIRING = '0b0e7c2a-4f1d-4c5e-9a8b-1c2d3e4f5a6b';
const SNOOZE_URL = `https://api.lia.test/api/v1/reminders/firings/${FIRING}/snooze`;

const reminderData = (overrides: Record<string, string> = {}) => ({
  type: 'reminder',
  reminder_id: 'reminder-1',
  firing_id: FIRING,
  snooze_url: SNOOZE_URL,
  snooze_short_label: 'Dans 10 min',
  snooze_long_label: 'Dans 1 h',
  ...overrides,
});

const push = (data: Record<string, string>) => ({
  data: {
    json: () => ({ notification: { title: 'Rappel', body: '🔔 Appeler la banque' }, data }),
    text: () => '',
  },
});

const answer = (outcome: string): FetchAnswer => ({
  ok: true,
  json: async () => ({ outcome, snoozed_until: null, next_occurrence_at: null }),
});

describe('the push of a reminder that rang', () => {
  it('offers the two delays its push names, in the labels it carries', async () => {
    const app = worker();

    await app.emit('push', push(reminderData()));

    expect(app.showNotification.mock.calls[0][1].actions).toEqual([
      { action: 'snooze_short', title: 'Dans 10 min' },
      { action: 'snooze_long', title: 'Dans 1 h' },
    ]);
  });

  it('offers nothing when the occurrence was not recorded', async () => {
    const app = worker();

    await app.emit('push', push({ type: 'reminder', reminder_id: 'reminder-1' }));

    expect(app.showNotification.mock.calls[0][1].actions).toEqual([]);
  });

  it.each([
    ['another route', 'https://api.lia.test/api/v1/peers/blocks'],
    [
      'another occurrence',
      `https://api.lia.test/api/v1/reminders/firings/${'f'.repeat(8)}-0000-4000-8000-000000000000/snooze`,
    ],
    [
      'plain http to a remote host',
      `http://api.lia.test/api/v1/reminders/firings/${FIRING}/snooze`,
    ],
    ['a query string', `${SNOOZE_URL}?next=https://outside.test`],
    [
      'credentials in the address',
      `https://user:pass@api.lia.test/api/v1/reminders/firings/${FIRING}/snooze`,
    ],
    ['no address at all', 'not a url'],
  ])('refuses an address that is not the occurrence’s snooze route: %s', async (_case, url) => {
    const app = worker();

    await app.emit('push', push(reminderData({ snooze_url: url })));

    expect(app.showNotification.mock.calls[0][1].actions).toEqual([]);
  });

  it('accepts a loopback development address over http', async () => {
    const app = worker();
    const local = `http://localhost:8000/api/v1/reminders/firings/${FIRING}/snooze`;

    await app.emit('push', push(reminderData({ snooze_url: local })));

    expect(app.showNotification.mock.calls[0][1].actions).toHaveLength(2);
  });
});

describe('a press on one of the delays', () => {
  const click = (action: string | undefined, data = reminderData()) => ({
    action,
    notification: { data: { ...data, url: '/dashboard/chat' }, close: vi.fn() },
  });

  it('posts the choice with the session and opens nothing once it landed', async () => {
    const app = worker(async () => answer('snoozed'));

    await app.emit('notificationclick', click('snooze_long'));

    expect(app.fetch).toHaveBeenCalledOnce();
    const [url, init] = app.fetch.mock.calls[0];
    expect(url).toBe(SNOOZE_URL);
    expect(init.method).toBe('POST');
    expect(init.credentials).toBe('include');
    expect(JSON.parse(String(init.body))).toEqual({ choice: 'long', surface: 'push' });
    expect(app.client.focus).not.toHaveBeenCalled();
    expect(app.openWindow).not.toHaveBeenCalled();
  });

  it('treats an occurrence another device postponed as landed', async () => {
    const app = worker(async () => answer('already_snoozed'));

    await app.emit('notificationclick', click('snooze_short'));

    expect(app.client.focus).not.toHaveBeenCalled();
  });

  it.each(['collides', 'expired'])(
    'opens the chat when the server refused the delay (%s): the bubble says why',
    async outcome => {
      const app = worker(async () => answer(outcome));

      await app.emit('notificationclick', click('snooze_long'));

      expect(app.client.focus).toHaveBeenCalledOnce();
    }
  );

  it('opens the chat when the press cannot reach the server', async () => {
    const app = worker(async () => {
      throw new TypeError('Failed to fetch');
    });

    await app.emit('notificationclick', click('snooze_short'));

    expect(app.client.focus).toHaveBeenCalledOnce();
  });

  it('opens the chat when the session is gone', async () => {
    const app = worker(async () => ({ ok: false, json: async () => ({ detail: 'expired' }) }));

    await app.emit('notificationclick', click('snooze_short'));

    expect(app.client.focus).toHaveBeenCalledOnce();
  });

  it('a press on the body opens the chat and posts nothing', async () => {
    const app = worker(async () => answer('snoozed'));

    await app.emit('notificationclick', click(undefined));

    expect(app.fetch).not.toHaveBeenCalled();
    expect(app.client.focus).toHaveBeenCalledOnce();
  });

  it('an action no notification draws posts nothing', async () => {
    const app = worker(async () => answer('snoozed'));

    await app.emit('notificationclick', click('constructor'));

    expect(app.fetch).not.toHaveBeenCalled();
  });
});
