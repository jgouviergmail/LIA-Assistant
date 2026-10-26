import type { WorldProp } from './types';
/** A mounted decoration is painted after its support, without changing either collision footprint. */
export function sortProps(props: readonly WorldProp[]): WorldProp[] {
  const byId = new Map(props.map(p => [p.id, p])),
    seen = new Set<string>(),
    visiting = new Set<string>(),
    result: WorldProp[] = [];
  const emit = (p: WorldProp) => {
    if (seen.has(p.id) || visiting.has(p.id)) return;
    visiting.add(p.id);
    const support = p.support ? byId.get(p.support) : null;
    if (support) emit(support);
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
