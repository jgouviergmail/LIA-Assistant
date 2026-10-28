import { expect, it } from 'vitest';
import { WORLD } from '../definition';
import { DeviceInbox } from '../device-inbox';
import {
  projectPrivateSignals,
  readResourceSignal,
  signalPresentation,
} from '../private-signal-projection';

const owner = 'ef910df4-a74c-4007-a41c-88dc9a43655d';
const messageId = '51bb9a96-5f4f-431e-9887-a5922ac6fa8a';
const empty = { status: 'unknown' as const, count: null, firstId: null };
const inputs = (box: DeviceInbox) => ({
  ownerId: owner,
  snapshotOwnerId: owner,
  enabled: true,
  smsEnabled: true,
  workboardEnabled: true,
  assetsEnabled: true,
  entries: box.snapshot(),
  workboard: empty,
  images: empty,
  documents: empty,
  screenshots: empty,
});
it('shares acknowledgment with the phone and never projects notice identities or text into rendering', () => {
  const box = new DeviceInbox(owner);
  const sms = {
    type: 'sms_received' as const,
    user_id: owner,
    message_id: messageId,
    occurrence_id: 'ed84f7c8-1a66-4eb7-a606-c5e3ce3253ba',
  };
  expect(box.receiveSms({ ...sms, user_id: messageId })).toBe(false);
  expect(box.receiveSms(sms)).toBe(true);
  expect(box.receiveSms(sms)).toBe(false);
  box.receiveReminder(
    {
      id: 'r',
      reminder_id: 'r',
      type: 'reminder',
      content: 'PRIVATE BODY',
      timestamp: new Date(),
      read: false,
    },
    0
  );
  const projected = projectPrivateSignals(WORLD, inputs(box));
  expect(projected.map(item => item.kind)).toContain('sms');
  expect(projected.map(item => item.kind)).toContain('reminder');
  const paint = JSON.stringify(signalPresentation(projected));
  expect(paint).not.toContain(messageId);
  expect(paint).not.toContain('PRIVATE BODY');
  expect(paint).not.toContain('noticeKey');
  const notice = box.snapshot().find(item => item.kind === 'sms');
  if (!notice) throw new Error('Expected the accepted SMS');
  box.read(notice.key);
  expect(projectPrivateSignals(WORLD, inputs(box)).some(item => item.kind === 'sms')).toBe(false);
  expect(projectPrivateSignals(WORLD, { ...inputs(box), snapshotOwnerId: 'other' })).toEqual([]);
  expect(projectPrivateSignals(WORLD, { ...inputs(box), enabled: false })).toEqual([]);
});
it('projects authenticated exact resource counts, unavailable state and the correct gallery family', () => {
  const box = new DeviceInbox(owner);
  const workboard = readResourceSignal(
    { total: 4, tickets: [{ id: messageId, title: 'PRIVATE TITLE' }] },
    'tickets'
  );
  const documents = readResourceSignal(
    { total: 2, items: [{ id: messageId, original_filename: 'PRIVATE FILE' }] },
    'items'
  );
  const projected = projectPrivateSignals(WORLD, {
    ...inputs(box),
    workboard,
    documents,
    images: { status: 'unavailable', count: null, firstId: null },
  });
  expect(projected.find(item => item.kind === 'workboard')).toMatchObject({
    count: 4,
    target: { kind: 'workboard', ticketId: messageId },
  });
  expect(projected.find(item => item.kind === 'documents')).toMatchObject({
    count: 2,
    target: { kind: 'gallery', tab: 'documents' },
  });
  expect(projected.find(item => item.kind === 'images')).toMatchObject({
    count: null,
    status: 'unavailable',
    target: null,
  });
  expect(JSON.stringify(projected)).not.toMatch(/PRIVATE TITLE|PRIVATE FILE/);
  expect(
    projectPrivateSignals(WORLD, {
      ...inputs(box),
      workboard,
      documents,
      workboardEnabled: false,
      assetsEnabled: false,
    })
  ).toEqual([]);
});
it('refuses malformed totals, forged identities and inconsistent positive pages without inventing zero', () => {
  for (const payload of [
    null,
    {},
    { total: true, tickets: [] },
    { total: -1, tickets: [] },
    { total: 1, tickets: [] },
    { total: 0, tickets: [{ id: messageId }] },
    { total: 1, tickets: [{ id: 'forged' }] },
  ])
    expect(readResourceSignal(payload, 'tickets')).toEqual({
      status: 'unavailable',
      count: null,
      firstId: null,
    });
  expect(readResourceSignal({ total: 0, items: [] }, 'items')).toEqual({
    status: 'ready',
    count: 0,
    firstId: null,
  });
});
