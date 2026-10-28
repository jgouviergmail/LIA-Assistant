import type { Navigation } from './navigation';
import type { PublicActor, WorldView } from './protocol';
import { compilePoseSlots, type PoseSlot } from './pose-slots';
import { zoneAt } from './simulation';
import { shortConversationRoute } from './social-approach';
import type { Point, WorldDefinition } from './types';
import type { WorldParticipant } from './useWorldSession';

function approach(actor: PublicActor, poses: readonly PoseSlot[]): Point | null {
  if (!actor.pose) return actor.position;
  const slot = poses.find(candidate => candidate.id === actor.pose);
  return slot &&
    Math.hypot(slot.position.x - actor.position.x, slot.position.y - actor.position.y) < 0.0001
    ? slot.approach
    : null;
}

function withinReach(
  own: PublicActor,
  person: PublicActor,
  navigation: Navigation,
  poses: readonly PoseSlot[]
): boolean {
  if (Math.hypot(person.position.x - own.position.x, person.position.y - own.position.y) > 2)
    return false;
  const from = approach(own, poses);
  const to = approach(person, poses);
  return from !== null && to !== null && shortConversationRoute(navigation, from, to, 2).length > 0;
}

/** Proximity suggests an existing recipient; it never grants message authority. */
export function nearbyConversations(
  view: WorldView,
  previous: readonly WorldParticipant[],
  world: WorldDefinition,
  navigation: Navigation,
  poses: readonly PoseSlot[] = compilePoseSlots(world)
): readonly WorldParticipant[] {
  const own = view.you;
  const available =
    view.status === 'active' &&
    view.controlling &&
    own !== null &&
    view.idle_until !== null &&
    view.idle_until > view.server_time &&
    zoneAt(world, own.position) !== 'home';
  const people = available
    ? view.actors
        .filter(
          person =>
            person.id !== own.id &&
            zoneAt(world, person.position) !== 'home' &&
            withinReach(own, person, navigation, poses)
        )
        .map(person => ({
          id: person.id,
          alias: person.alias,
          distance: Math.hypot(
            person.position.x - own.position.x,
            person.position.y - own.position.y
          ),
        }))
        .sort((a, b) => a.distance - b.distance || a.id.localeCompare(b.id))
        .map(({ id, alias }) => ({ id, alias }))
    : [];
  return people.length === previous.length &&
    people.every(
      (person, index) => person.id === previous[index].id && person.alias === previous[index].alias
    )
    ? previous
    : people;
}
