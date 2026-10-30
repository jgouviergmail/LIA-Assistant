import type { ModelPart } from './model';

function bounds(part: ModelPart): number[] {
  if (part.kind === 'box')
    return [part.x, part.y, part.z, part.x + part.width, part.y + part.depth, part.z + part.height];
  return [
    Math.min(...part.points.map(p => p.x)),
    Math.min(...part.points.map(p => p.y)),
    Math.min(...part.points.map(p => p.z)),
    Math.max(...part.points.map(p => p.x)),
    Math.max(...part.points.map(p => p.y)),
    Math.max(...part.points.map(p => p.z)),
  ];
}

/** View rays advance along all three axes. Only unambiguous separations impose
 * an order; intersecting/coplanar authored layers keep their original order.
 * Runs once when baking a sprite, never during the scene's animation loop. */
export function orderedModelParts(parts: readonly ModelPart[]): ModelPart[] {
  const boxes = parts.map(bounds),
    outgoing = parts.map(() => [] as number[]),
    incoming = parts.map(() => 0);
  for (let i = 0; i < parts.length; i++)
    for (let j = i + 1; j < parts.length; j++) {
      const a = boxes[i],
        b = boxes[j];
      let before = false,
        after = false;
      for (let axis = 0; axis < 3; axis++) {
        if (a[axis + 3] <= b[axis] + 1e-7) before = true;
        if (b[axis + 3] <= a[axis] + 1e-7) after = true;
      }
      if (before === after) continue;
      const first = before ? i : j,
        last = before ? j : i;
      outgoing[first].push(last);
      incoming[last]++;
    }
  const result: ModelPart[] = [],
    painted = parts.map(() => false);
  while (result.length < parts.length) {
    let next = incoming.findIndex((count, i) => count === 0 && !painted[i]);
    // Interlocking authored solids can form a cycle. Preserve their source
    // order rather than dropping geometry or making the bake unbounded.
    if (next < 0) next = painted.indexOf(false);
    painted[next] = true;
    result.push(parts[next]);
    for (const following of outgoing[next]) incoming[following]--;
  }
  return result;
}
