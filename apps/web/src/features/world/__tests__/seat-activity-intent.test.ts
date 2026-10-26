import { beforeEach, expect, it } from 'vitest';
import { SeatActivityIntent } from '../seat-activity-intent';
import type { WorldView } from '../protocol';

const epoch = '11111111-1111-4111-8111-111111111111';
const actor = '22222222-2222-4222-8222-222222222222';
function snapshot(patch: Partial<WorldView> = {}): WorldView {
  return {
    version: 1,
    type: 'snapshot',
    epoch,
    revision: 1,
    status: 'active',
    controlling: true,
    ack: 4,
    actors: [],
    position: null,
    offer_until: null,
    idle_until: null,
    pose_result: 'accepted',
    you: {
      id: actor,
      alias: 'Me',
      position: { x: 10, y: 10 },
      facing: 1,
      walking: false,
      pose: 'memory-seat:0',
    },
    ...patch,
  };
}
let intent: SeatActivityIntent;
beforeEach(() => {
  intent = new SeatActivityIntent();
});
function arm() {
  intent.arm({ slot: 'memory-seat:0', seq: 4, epoch, stream: 2, now: 100 });
}

it('opens only after the requested authoritative pose is acknowledged, once', () => {
  arm();
  expect(intent.accept(snapshot({ ack: 3 }), 2, 200)).toBeNull();
  expect(intent.accept(snapshot(), 2, 300)).toBe('memory-seat:0');
  expect(intent.accept(snapshot(), 2, 400)).toBeNull();
});
it('does not react to a seated snapshot without a local request', () => {
  expect(intent.accept(snapshot(), 2, 200)).toBeNull();
});
it.each(['occupied', 'out_of_reach', 'invalid'] as const)(
  'never opens a refused %s seat',
  result => {
    arm();
    expect(
      intent.accept(
        snapshot({ pose_result: result, you: { ...snapshot().you!, pose: null } }),
        2,
        200
      )
    ).toBeNull();
    expect(intent.accept(snapshot(), 2, 300)).toBeNull();
  }
);
it.each([
  { name: 'another pose', patch: { you: { ...snapshot().you!, pose: 'other:0' } } },
  { name: 'another epoch', patch: { epoch: actor } },
  { name: 'lost control', patch: { controlling: false } },
  { name: 'left world', patch: { status: 'absent' as const, you: null } },
])('cancels after $name, including a later old acknowledgment', ({ patch }) => {
  arm();
  expect(intent.accept(snapshot(patch), 2, 200)).toBeNull();
  expect(intent.accept(snapshot(), 2, 300)).toBeNull();
});
it('cancels across reconnects, timeouts, manual interruption and superseding requests', () => {
  arm();
  expect(intent.accept(snapshot(), 3, 200)).toBeNull();
  arm();
  expect(intent.accept(snapshot(), 2, 6100)).toBeNull();
  arm();
  intent.cancel();
  expect(intent.accept(snapshot(), 2, 200)).toBeNull();
  arm();
  intent.arm({ slot: 'other:0', seq: 5, epoch, stream: 2, now: 110 });
  expect(intent.accept(snapshot(), 2, 200)).toBeNull();
  expect(
    intent.accept(snapshot({ ack: 5, you: { ...snapshot().you!, pose: 'other:0' } }), 2, 300)
  ).toBe('other:0');
});
