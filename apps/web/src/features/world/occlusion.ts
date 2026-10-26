import { project } from './geometry';
import type { Point, Rect, WorldProp } from './types';

/** The view ray points along +x/+y: a prop cannot hide an actor beyond either front face. */
export function actorOccluders(props: readonly WorldProp[], actor: Point, area: Rect): WorldProp[] {
  return props.filter(prop => {
    if (prop.height < 0.1 || actor.x >= prop.x + prop.width || actor.y >= prop.y + prop.depth)
      return false;
    const p = project(prop);
    // Same conservative authored sprite bounds as Painter; shadows are excluded from masks.
    const left = p.x - prop.depth * 32 - 20;
    const top = p.y - Math.max(prop.height, 2.5) * 32 - 20;
    const right = p.x + prop.width * 32 + 20;
    const bottom = p.y + (prop.width + prop.depth) * 16 + 28;
    return (
      left < area.x + area.width && right > area.x && top < area.y + area.height && bottom > area.y
    );
  });
}
