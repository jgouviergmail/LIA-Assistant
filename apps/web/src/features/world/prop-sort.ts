import type { WorldProp } from './types';

/** A long furnishing must stay on the same side of every overlapping wall tile.
 * The far-corner depth key alone interleaves the middle tiles with the furniture.
 * Build these constraints only when the layout changes, not on each frame. */
function wallPredecessors(props: readonly WorldProp[]): Map<string, WorldProp[]> {
  const walls = props.filter(p => p.kind === 'partition'),
    predecessors = new Map<string, WorldProp[]>();
  for (const prop of props) {
    if (prop.kind === 'partition' || prop.height < 0.1) continue;
    for (const wall of walls) {
      // Disjoint horizontal projections cannot obscure one another.
      if (
        prop.x - prop.y - prop.depth >= wall.x - wall.y + wall.width ||
        wall.x - wall.y - wall.depth >= prop.x - prop.y + prop.width
      )
        continue;
      const wallBehind = wall.x + wall.width <= prop.x || wall.y + wall.depth <= prop.y,
        propBehind = prop.x + prop.width <= wall.x || prop.y + prop.depth <= wall.y;
      // Intersecting footprints or opposite separations retain the depth key.
      if (wallBehind === propBehind) continue;
      const first = propBehind ? prop : wall,
        last = propBehind ? wall : prop,
        previous = predecessors.get(last.id) ?? [];
      previous.push(first);
      predecessors.set(last.id, previous);
    }
  }
  return predecessors;
}

/** Preserve wall occlusion and mounted supports without changing collision footprints. */
export function sortProps(props: readonly WorldProp[]): WorldProp[] {
  const byId = new Map(props.map(p => [p.id, p])),
    predecessors = wallPredecessors(props),
    seen = new Set<string>(),
    visiting = new Set<string>(),
    result: WorldProp[] = [];
  const emit = (p: WorldProp) => {
    if (seen.has(p.id) || visiting.has(p.id)) return;
    visiting.add(p.id);
    const support = p.support ? byId.get(p.support) : null;
    if (support) emit(support);
    for (const previous of predecessors.get(p.id) ?? []) emit(previous);
    visiting.delete(p.id);
    seen.add(p.id);
    result.push(p);
  };
  for (const p of [...props].sort(
    (a, b) => a.x + a.y + a.width + a.depth - b.x - b.y - b.width - b.depth
  ))
    emit(p);
  return result;
}
