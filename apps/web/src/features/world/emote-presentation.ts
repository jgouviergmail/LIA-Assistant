import type { WorldView } from './protocol';
import type { EmoteKind } from './emote-catalogue';
export interface PublicGesture {
  id: string;
  alias: string;
  serial: number;
  kind: EmoteKind;
}

/** Accessible projection shares the same finite server event and never retains a history. */
export function publicGestures(
  view: WorldView,
  previous: readonly PublicGesture[]
): readonly PublicGesture[] {
  const next: PublicGesture[] = [];
  for (const actor of [...view.actors, ...(view.you ? [view.you] : [])]) {
    if (actor.emote && actor.emote.expires_at > view.server_time)
      next.push({
        id: actor.id,
        alias: actor.alias,
        serial: actor.emote.serial,
        kind: actor.emote.emote,
      });
  }
  return next.length === previous.length &&
    next.every((item, index) => {
      const old = previous[index];
      return (
        item.id === old.id &&
        item.alias === old.alias &&
        item.serial === old.serial &&
        item.kind === old.kind
      );
    })
    ? previous
    : next;
}
