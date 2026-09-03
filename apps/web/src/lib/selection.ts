/**
 * Row selection — pure helpers shared by every list with a selection bar
 * (meetings, knowledge-space documents; ADR-259).
 */

export type PageSelectionState = 'none' | 'some' | 'all';

/** A new set with `id` added when absent, removed when present. */
export function toggleId(selected: ReadonlySet<string>, id: string): Set<string> {
  const next = new Set(selected);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return next;
}

/** How much of the page's selectable ids the selection covers. */
export function pageSelectionState(
  selectableIds: readonly string[],
  selected: ReadonlySet<string>
): PageSelectionState {
  if (selectableIds.length === 0) return 'none';
  const covered = selectableIds.filter(id => selected.has(id)).length;
  if (covered === 0) return 'none';
  return covered === selectableIds.length ? 'all' : 'some';
}
