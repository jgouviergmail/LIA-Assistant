import { expect, it, vi } from 'vitest';
import { messageText, prepareMessage, readMailbox } from '../message-protocol';

const id = '4010c2c2-4bd0-4d21-9c08-b4502db25d72';
const scope = { epoch: id, controller: 'c'.repeat(43) };

it('uses the fresh server clock even when the device clock is wrong, and freezes one intent', () => {
  vi.spyOn(Date, 'now').mockReturnValue(0);
  try {
    const message = prepareMessage(
      scope,
      id,
      'Bonjour',
      true,
      { serverSeconds: 1000, receivedAt: 100 },
      2100
    );
    expect(message.created_at).toBe(1002);
    expect(message.text).toBe('Bonjour');
    expect(Object.isFrozen(message)).toBe(true);
    expect(() =>
      prepareMessage(scope, id, 'Bonjour', true, { serverSeconds: 1000, receivedAt: 100 }, 12100)
    ).toThrow('world_message_clock');
  } finally {
    vi.restoreAllMocks();
  }
});

it('bounds Unicode without rejecting joined emoji or interpreting markup', () => {
  for (const text of ['👩‍💻', '<img src=x>', '🙂'.repeat(1000), '中文\nbonjour'])
    expect(messageText(text)).toBe(text);
  for (const text of ['🙂'.repeat(1001), 'x\u202ey', '\ud800', ' \n\t'])
    expect(messageText(text)).toBeNull();
});

it('refuses private extra fields and malformed mailboxes without reflecting their contents', () => {
  expect(
    readMailbox({ server_time: 1000, ttl_seconds: 1800, messages: [], truncated: false }).messages
  ).toEqual([]);
  expect(() =>
    readMailbox({
      server_time: 1000,
      ttl_seconds: 1800,
      messages: [],
      truncated: false,
      account_id: 'PRIVATE_ACCOUNT_SENTINEL',
    })
  ).toThrow('world_mailbox_invalid');
  expect(() => readMailbox({ server_time: Infinity, messages: [] })).toThrow(
    'world_mailbox_invalid'
  );
});
