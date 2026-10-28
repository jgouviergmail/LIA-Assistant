import { expect, it } from 'vitest';
import { parseWorldFrame, publicAlias } from '../protocol';
import { SeatActivityIntent } from '../seat-activity-intent';
import { EMOTES } from '../emote-catalogue';

const epoch = '11111111-1111-4111-8111-111111111111';
const frame = () => ({
  type: 'snapshot',
  version: 2,
  epoch,
  revision: 1,
  server_time: 100,
  receipts: [{ seq: 5, kind: 'emote', result: 'accepted' }],
  pose_result: 'accepted',
  status: 'active',
  controlling: true,
  ack: 5,
  actors: [],
  position: null,
  offer_until: null,
  idle_until: 1000,
  you: {
    id: epoch,
    alias: 'Me',
    position: { x: 10, y: 10 },
    facing: 1,
    walking: false,
    pose: 'seat:0',
    emote: { emote: 'wave', serial: 1, expires_at: 102 },
  },
});

it('accepts only finite socket-v2 events while rejecting private data and obsolete generations', () => {
  expect(EMOTES).toHaveLength(6);
  expect(parseWorldFrame(JSON.stringify(frame())).type).toBe('snapshot');
  for (const patch of [
    { version: 1 },
    { server_time: -1 },
    { account_id: epoch },
    { receipts: [{ seq: 5, kind: 'emote', result: 'occupied' }] },
    { you: { ...frame().you, emote: { emote: 'free text', serial: 1, expires_at: 102 } } },
    { you: { ...frame().you, emote: { emote: 'wave', serial: true, expires_at: 102 } } },
  ]) {
    expect(() => parseWorldFrame(JSON.stringify({ ...frame(), ...patch }))).toThrow();
  }
  expect(() => parseWorldFrame('雪'.repeat(6000))).toThrow('world_frame_limit');
});

it('keeps public labels literal, normalized and bounded by code points', () => {
  expect(publicAlias('  Le\u0301a  ')).toBe('Léa');
  expect(publicAlias('🌿'.repeat(24))).toBe('🌿'.repeat(24));
  for (const value of ['', '   ', 'x'.repeat(25), 'a\nb', 'a\u202eb'])
    expect(publicAlias(value)).toBeNull();
});

it('requires the exact typed pose receipt; a later emote ack cannot confirm an old seat request', () => {
  const intent = new SeatActivityIntent();
  intent.arm({ slot: 'seat:0', seq: 4, epoch, stream: 1, now: 0 });
  const parsed = parseWorldFrame(JSON.stringify(frame()));
  if (parsed.type !== 'snapshot') throw new Error('expected snapshot');
  expect(intent.accept(parsed, 1, 100)).toBeNull();
  const confirmed = parseWorldFrame(
    JSON.stringify({
      ...frame(),
      receipts: [{ seq: 4, kind: 'pose', result: 'accepted' }, ...frame().receipts],
    })
  );
  if (confirmed.type !== 'snapshot') throw new Error('expected snapshot');
  expect(intent.accept(confirmed, 1, 200)?.slot).toBe('seat:0');
});
