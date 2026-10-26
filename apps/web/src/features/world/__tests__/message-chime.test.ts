import { expect, it } from 'vitest';
import { RecipientChime } from '../audio/message-chime';
import type { WorldMailbox, WorldMessage } from '../message-protocol';
const message = (id: string, extra: Partial<WorldMessage> = {}): WorldMessage => ({
  id,
  sender_id: 'peer',
  sender_alias: 'Peer',
  recipient_id: 'self',
  recipient_alias: 'You',
  outgoing: false,
  original: 'hello',
  text: 'hello',
  language: 'fr',
  status: 'original',
  created_at: 100,
  expires_at: 1000,
  receipt: null,
  ...extra,
});
const mailbox = (messages: WorldMessage[], time = 100): WorldMailbox => ({
  server_time: time,
  ttl_seconds: 600,
  messages,
  truncated: false,
});
it('sounds once for a fresh incoming private delivery, not initial history, sender echoes or public messages', () => {
  const cue = new RecipientChime();
  cue.setActive(true);
  expect(cue.receive(mailbox([message('old')]))).toBe(false);
  expect(cue.receive(mailbox([message('old'), message('new')]))).toBe(true);
  expect(cue.receive(mailbox([message('new', { status: 'translated' })]))).toBe(false);
  expect(cue.receive(mailbox([message('sent', { outgoing: true })]))).toBe(false);
  expect(cue.receive({ ...mailbox([]), public_available: true, public_messages: [] })).toBe(false);
  expect(cue.receive(mailbox([message('expired', { created_at: 20 })]))).toBe(false);
  expect(cue.receive(mailbox([message('future', { created_at: 110 })]))).toBe(false);
});
it('silently establishes a new baseline after an authority interruption and bounds long-session IDs', () => {
  const cue = new RecipientChime();
  expect(cue.receive(mailbox([message('a')]))).toBe(false);
  cue.setActive(true);
  expect(cue.receive(mailbox([]))).toBe(false);
  expect(cue.receive(mailbox([message('a')]))).toBe(true);
  cue.setActive(false);
  expect(cue.receive(mailbox([message('b')]))).toBe(false);
  cue.setActive(true);
  expect(cue.receive(mailbox([message('b')]))).toBe(false);
  for (let n = 0; n < 400; n++) cue.receive(mailbox([message(String(n))]));
  expect(cue.receive(mailbox([message('old-again', { created_at: 0 })]))).toBe(false);
});
