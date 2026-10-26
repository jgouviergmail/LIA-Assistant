import { expect, it } from 'vitest';
import { conversationDirectory } from '../conversation-directory';
import type { WorldMessage } from '../message-protocol';

const message = (changes: Partial<WorldMessage> = {}): WorldMessage => ({
  id: 'message',
  sender_id: 'a',
  sender_alias: 'Alex',
  recipient_id: 'owner',
  recipient_alias: 'You',
  outgoing: false,
  original: 'PRIVATE untranslated original',
  text: 'Hello',
  language: 'en',
  status: 'original',
  created_at: 1,
  expires_at: 1000,
  receipt: null,
  ...changes,
});

it('groups incoming and outgoing messages by public person, retaining departed history', () => {
  const rows = conversationDirectory(
    [{ id: 'b', alias: 'Blair' }],
    [
      message(),
      message({
        id: 'reply',
        outgoing: true,
        sender_id: 'owner',
        recipient_id: 'a',
        recipient_alias: 'Alex',
        created_at: 2,
        text: 'Reply',
      }),
    ],
    { a: 1 },
    { b: 'Draft' }
  );
  expect(rows).toHaveLength(2);
  expect(rows[0]).toMatchObject({
    id: 'a',
    alias: 'Alex',
    online: false,
    unread: 1,
    latest: expect.objectContaining({ id: 'reply' }),
  });
  expect(rows[1]).toMatchObject({ id: 'b', online: true, hasDraft: true });
});

it('does not turn an unavailable translation into an original-text directory preview', () => {
  const [row] = conversationDirectory([], [message({ text: null, status: 'pending' })], {}, {});
  expect(row.preview).toBeNull();
  expect(row.latest?.status).toBe('pending');
});

it('keeps homonymous people separate and deterministically orders activity', () => {
  const rows = conversationDirectory(
    [
      { id: 'a', alias: 'Alex' },
      { id: 'b', alias: 'Alex' },
    ],
    [message(), message({ id: 'new', sender_id: 'b', created_at: 5 })],
    {},
    {}
  );
  expect(rows.map(row => row.id)).toEqual(['b', 'a']);
  expect(rows.every(row => row.ambiguous)).toBe(true);
});

it('uses the active alias and never shares a draft with another recipient', () => {
  const rows = conversationDirectory(
    [{ id: 'a', alias: 'Renamed' }],
    [message()],
    {},
    { b: 'secret' }
  );
  expect(rows[0]).toMatchObject({ alias: 'Renamed', hasDraft: false });
});

it('retains an addressed draft after its person leaves, without inventing anonymous recipients', () => {
  const rows = conversationDirectory(
    [],
    [],
    {},
    { a: 'Unsent private draft', unknown: 'orphan', empty: ' ' },
    { a: 'Alex', empty: 'Empty' }
  );
  expect(rows).toEqual([
    expect.objectContaining({
      id: 'a',
      alias: 'Alex',
      online: false,
      hasDraft: true,
      preview: null,
    }),
  ]);
});

it('keeps the newest departed alias when mailbox records arrive out of order', () => {
  const rows = conversationDirectory(
    [],
    [
      message({ id: 'new', created_at: 3, sender_alias: 'New alias' }),
      message({ id: 'old', created_at: 1, sender_alias: 'Old alias' }),
    ],
    {},
    {}
  );
  expect(rows[0]).toMatchObject({ alias: 'New alias', latest: { id: 'new' } });
});

it('uses the addressed alias for an outgoing-only departed conversation', () => {
  const rows = conversationDirectory(
    [],
    [
      message({
        outgoing: true,
        recipient_id: 'b',
        recipient_alias: 'Blair',
        text: 'My answer',
      }),
    ],
    {},
    {}
  );
  expect(rows[0]).toMatchObject({ id: 'b', alias: 'Blair', online: false, preview: 'My answer' });
});

it('orders empty homonymous conversations by stable identity, independent of arrival order', () => {
  const rows = conversationDirectory(
    [
      { id: 'b', alias: 'Same name' },
      { id: 'a', alias: 'Same name' },
    ],
    [],
    {},
    {}
  );
  expect(rows.map(row => row.id)).toEqual(['a', 'b']);
  expect(rows.every(row => row.ambiguous)).toBe(true);
});
