import { expect, it } from 'vitest';
import { DeviceInbox } from '../device-inbox';
import type { Notification } from '@/hooks/useNotifications';
const owner = 'ef910df4-a74c-4007-a41c-88dc9a43655d';
const sms = {
  type: 'sms_received' as const,
  user_id: owner,
  message_id: '51bb9a96-5f4f-431e-9887-a5922ac6fa8a',
  occurrence_id: 'ed84f7c8-1a66-4eb7-a606-c5e3ce3253ba',
};
const reminder: Notification = {
  id: 'reminder-id',
  reminder_id: 'reminder-id',
  type: 'reminder',
  content: 'Private reminder',
  timestamp: new Date(),
  read: false,
};
it('rejects foreign-account signals and deduplicates SMS delivery without reading private text', () => {
  const box = new DeviceInbox(owner);
  expect(box.receiveSms({ ...sms, user_id: '3fa13afc-e569-4f66-9e1c-8913e601da15' })).toBe(false);
  expect(box.receiveSms(sms)).toBe(true);
  expect(box.receiveSms(sms)).toBe(false);
  expect(box.snapshot()).toHaveLength(1);
  expect(JSON.stringify(box.snapshot())).not.toContain('body');
  expect(new DeviceInbox(owner).snapshot()).toEqual([]);
});
it('distinguishes simultaneous SMS and reminders and accepts the next recurring reminder', () => {
  const box = new DeviceInbox(owner);
  box.receiveSms(sms);
  expect(box.receiveReminder(reminder, 0)).toBe(true);
  expect(box.receiveReminder(reminder, 1000)).toBe(false);
  expect(box.receiveReminder(reminder, 60000)).toBe(true);
  expect(box.snapshot().map(n => n.kind)).toEqual(['reminder', 'reminder', 'sms']);
  box.read(box.snapshot()[0].key);
  expect(box.snapshot().filter(n => !n.read)).toHaveLength(2);
  expect(box.receiveReminder({ ...reminder, type: 'system' }, 70000)).toBe(false);
  expect(box.receiveReminder(reminder, NaN)).toBe(false);
});
it('bounds private content and retained arrivals during a long world session', () => {
  const box = new DeviceInbox(owner);
  for (let i = 0; i < 200; i++)
    box.receiveReminder(
      { ...reminder, reminder_id: String(i), content: 'x'.repeat(9000) },
      i * 6000
    );
  expect(box.snapshot()).toHaveLength(32);
  for (const n of box.snapshot())
    if (n.kind === 'reminder') expect(n.content.length).toBeLessThanOrEqual(4000);
});
