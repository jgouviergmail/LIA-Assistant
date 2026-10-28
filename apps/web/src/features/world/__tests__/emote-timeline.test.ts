import { expect, it } from 'vitest';
import { EmoteTimeline } from '../emote-timeline';

it('anchors remaining lifetime once, without extending or replaying repeated snapshots', () => {
  const events = new EmoteTimeline();
  const event = { emote: 'wave' as const, serial: 1, expires_at: 102 };
  const first = events.receive('actor', event, 100.5, 10);
  expect(first).toEqual({ kind: 'wave', serial: 1, started: 9.5, until: 11.5 });
  expect(events.receive('actor', event, 100.6, 10.5)).toBe(first);
  expect(events.receive('actor', event, 101, 12)).toBeNull();
  expect(events.receive('actor', { ...event, serial: 2, expires_at: 105 }, 103, 12)?.until).toBe(
    14
  );
  expect(events.receive('actor', event, 103, 12)).toBeNull();
});
it('drops expired, absent and invalid clocks and bounds retained public event identities', () => {
  const events = new EmoteTimeline();
  expect(events.receive('actor', null, 1, 1)).toBeNull();
  expect(events.receive('actor', { emote: 'wave', serial: 1, expires_at: 1 }, 2, 1)).toBeNull();
  expect(events.receive('actor', { emote: 'wave', serial: 2, expires_at: 10 }, NaN, 1)).toBeNull();
  for (let n = 0; n < 150; n++)
    events.receive(String(n), { emote: 'thanks', serial: 1, expires_at: 4 }, 2, 1);
  expect(events.size).toBeLessThanOrEqual(128);
  events.clear();
  expect(events.size).toBe(0);
});
