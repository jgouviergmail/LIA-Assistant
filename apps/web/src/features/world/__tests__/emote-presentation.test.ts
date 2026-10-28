import { expect, it } from 'vitest';
import { publicGestures } from '../emote-presentation';
import { parseWorldFrame } from '../protocol';

it('publishes a bounded accessible finite event without rerendering identical snapshots or retaining history', () => {
  const view = parseWorldFrame(
    JSON.stringify({
      type: 'snapshot',
      version: 2,
      server_time: 100,
      receipts: [],
      epoch: '11111111-1111-4111-8111-111111111111',
      revision: 1,
      status: 'active',
      controlling: true,
      ack: 0,
      actors: [],
      position: null,
      offer_until: null,
      idle_until: 1000,
      you: {
        id: '11111111-1111-4111-8111-111111111111',
        alias: '<b>Me</b>',
        position: { x: 1, y: 1 },
        facing: 1,
        walking: false,
        emote: { emote: 'wave', serial: 1, expires_at: 102 },
      },
    })
  );
  if (view.type !== 'snapshot') throw new Error('expected snapshot');
  const first = publicGestures(view, []);
  expect(first).toHaveLength(1);
  expect(publicGestures(view, first)).toBe(first);
  expect(publicGestures({ ...view, server_time: 102 }, first)).toEqual([]);
  expect(Object.keys(first[0]).sort()).toEqual(['alias', 'id', 'kind', 'serial']);
});
