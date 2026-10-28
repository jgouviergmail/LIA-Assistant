import { describe, expect, it } from 'vitest';
import { nearbyConversations } from '../nearby-conversations';
import { compileNavigation } from '../navigation';
import type { PublicActor, WorldView } from '../protocol';
import type { WorldDefinition } from '../types';

const world: WorldDefinition = {
  id: 'nearby-test',
  version: 1,
  width: 12,
  height: 12,
  spawn: { x: 3.5, y: 3.5 },
  bipSpawn: { x: 1.5, y: 1.5 },
  patrol: [],
  props: [],
  grounds: [],
  zones: [
    { id: 'home', x: 8, y: 8, width: 3, height: 3, tone: 'cream', arrival: { x: 8.5, y: 8.5 } },
  ],
};
function actor(id: string, x: number, y = 3.5): PublicActor {
  return { id, alias: id, position: { x, y }, facing: 0, walking: false };
}
function view(actors: PublicActor[]): WorldView {
  return {
    type: 'snapshot',
    version: 2,
    epoch: 'epoch',
    revision: 1,
    server_time: 100,
    receipts: [],
    status: 'active',
    controlling: true,
    you: actor('you', 3.5),
    actors,
    ack: 0,
    position: null,
    offer_until: null,
    idle_until: 200,
  };
}

describe('authoritative nearby conversation candidates', () => {
  it('includes the exact two-tile boundary and excludes farther or diagonal-out-of-radius peers', () => {
    expect(
      nearbyConversations(
        view([actor('boundary', 5.5), actor('outside', 5.5001), actor('diagonal', 5.5, 5.5)]),
        [],
        world,
        compileNavigation(world)
      )
    ).toEqual([{ id: 'boundary', alias: 'boundary' }]);
  });

  it('never selects a peer through a wall even when a route exists around it', () => {
    const navigation = compileNavigation(world);
    navigation.blocked[3 * navigation.width + 4] = 1;
    expect(nearbyConversations(view([actor('behind-wall', 5.5)]), [], world, navigation)).toEqual(
      []
    );
  });

  it('orders by ground distance then stable identity rather than incoming actor order', () => {
    expect(
      nearbyConversations(
        view([actor('far', 5.5), actor('z', 4.5), actor('a', 2.5), actor('you', 3.5)]),
        [],
        world,
        compileNavigation(world)
      )
    ).toEqual([
      { id: 'a', alias: 'a' },
      { id: 'z', alias: 'z' },
      { id: 'far', alias: 'far' },
    ]);
  });

  it('reuses the projection across movement that keeps candidate identities and order unchanged', () => {
    const navigation = compileNavigation(world);
    const previous = nearbyConversations(view([actor('peer', 4.5)]), [], world, navigation);
    expect(nearbyConversations(view([actor('peer', 4.6)]), previous, world, navigation)).toBe(
      previous
    );
    expect(nearbyConversations(view([]), previous, world, navigation)).toEqual([]);
    expect(
      nearbyConversations(
        view([{ ...actor('peer', 4.5), alias: 'Renamed' }]),
        previous,
        world,
        navigation
      )
    ).toEqual([{ id: 'peer', alias: 'Renamed' }]);
  });

  it.each([
    { status: 'waiting' as const },
    { status: 'absent' as const },
    { controlling: false },
    { you: null },
    { idle_until: 100 },
    { idle_until: null },
    { you: actor('you', 8.5, 8.5) },
    { you: actor('you', NaN) },
  ])('clears candidates when the local snapshot is unavailable: %j', change => {
    expect(
      nearbyConversations(
        { ...view([actor('peer', 4.5)]), ...change },
        [{ id: 'old', alias: 'Old' }],
        world,
        compileNavigation(world)
      )
    ).toEqual([]);
  });

  it('excludes invalid coordinates and people in the private home', () => {
    const snapshot = view([actor('invalid', Infinity), actor('home', 8.5, 8.5)]);
    snapshot.you = actor('you', 7.5, 8.5);
    expect(nearbyConversations(snapshot, [], world, compileNavigation(world))).toEqual([]);
  });

  it.each([false, true])('uses a verified seated peer approach with local seated=%s', seated => {
    const furnished: WorldDefinition = {
      ...world,
      props: [
        {
          id: 'local-seat',
          key: 'local-seat',
          kind: 'chair',
          x: 3,
          y: 3,
          width: 1,
          depth: 1,
          height: 1,
          tone: 'cream',
          blocking: true,
          facing: 1,
        },
        {
          id: 'peer-seat',
          key: 'peer-seat',
          kind: 'chair',
          x: 4,
          y: 3,
          width: 1,
          depth: 1,
          height: 1,
          tone: 'cream',
          blocking: true,
          facing: 1,
        },
      ],
    };
    const snapshot = view([{ ...actor('peer', 4.5), pose: 'peer-seat:0' }]);
    snapshot.you = seated ? { ...actor('you', 3.5), pose: 'local-seat:0' } : actor('you', 3.5, 4.5);
    expect(nearbyConversations(snapshot, [], furnished, compileNavigation(furnished))).toEqual([
      { id: 'peer', alias: 'peer' },
    ]);
  });

  it('does not let a seat bypass actual distance, an unknown pose, a position mismatch or a wall', () => {
    const furnished: WorldDefinition = {
      ...world,
      props: [
        {
          id: 'peer-seat',
          key: 'peer-seat',
          kind: 'chair',
          x: 4,
          y: 3,
          width: 1,
          depth: 1,
          height: 1,
          tone: 'cream',
          blocking: true,
          facing: 1,
        },
      ],
    };
    const snapshot = view([{ ...actor('peer', 4.5), pose: 'peer-seat:0' }]);
    snapshot.you = actor('you', 4.5, 6);
    expect(nearbyConversations(snapshot, [], furnished, compileNavigation(furnished))).toEqual([]);
    snapshot.you = actor('you', 3.5, 4.5);
    for (const candidate of [
      { ...actor('peer', 4.5), pose: 'unknown' },
      { ...actor('peer', 4.4), pose: 'peer-seat:0' },
    ]) {
      expect(
        nearbyConversations(
          { ...snapshot, actors: [candidate] },
          [],
          furnished,
          compileNavigation(furnished)
        )
      ).toEqual([]);
    }
    const navigation = compileNavigation(furnished);
    navigation.blocked[4 * navigation.width + 4] = 1;
    expect(nearbyConversations(snapshot, [], furnished, navigation)).toEqual([]);
  });
});
