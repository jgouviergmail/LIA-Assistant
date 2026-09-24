/**
 * What a brick map lights up, decided in ONE place for both maps.
 *
 * The functional constellation and the technical layers answer the same
 * question — "which bricks stand out right now?" — from the same inputs, in
 * the same order of precedence: a journey being played, then the brick under
 * the pointer or the keyboard, then the selected brick, then the isolated
 * family, then the search. Two copies of that order would let the two maps
 * disagree about what a click means.
 */

import { foldForSearch } from './format';
import type { BrickView, FamilyView, FlowView } from './types';

/** An edge between two bricks, keyed `from>to`. */
export const edgeKey = (from: string, to: string): string => `${from}>${to}`;

export interface HighlightInput {
  bricks: readonly BrickView[];
  /** The journey being played, with its current step, if any. */
  flow: { flow: FlowView; step: number } | null;
  hovered: string | null;
  selected: string | null;
  family: string | null;
  /** Bricks matching the search, or null when nothing is searched. */
  matches: ReadonlySet<string> | null;
}

export interface Highlight {
  /** Whether anything is highlighted at all (everything else then dims). */
  active: boolean;
  /** Bricks in full light. */
  on: ReadonlySet<string>;
  /** Bricks lit as neighbours (dependencies, users, other steps). */
  near: ReadonlySet<string>;
  /** Dependencies of the focused brick, keyed with `edgeKey`. */
  out: ReadonlySet<string>;
  /** Users of the focused brick, keyed with `edgeKey`. */
  in: ReadonlySet<string>;
  /** The brick of the journey's current step. */
  current: string | null;
}

const NONE: Highlight = {
  active: false,
  on: new Set(),
  near: new Set(),
  out: new Set(),
  in: new Set(),
  current: null,
};

function focusBrick(bricks: readonly BrickView[], id: string): Highlight {
  const brick = bricks.find(b => b.id === id);
  if (!brick) return NONE;
  return {
    active: true,
    on: new Set([id]),
    near: new Set([...brick.deps, ...brick.usedBy]),
    out: new Set(brick.deps.map(d => edgeKey(id, d))),
    in: new Set(brick.usedBy.map(u => edgeKey(u, id))),
    current: null,
  };
}

function focusSet(ids: Iterable<string>): Highlight {
  return { ...NONE, active: true, on: new Set(ids) };
}

/** The highlight of a brick map for its current state. */
export function computeHighlight(input: HighlightInput): Highlight {
  const { bricks, flow, hovered, selected, family, matches } = input;
  if (flow) {
    const ids = flow.flow.steps.map(s => s.brick);
    const current = ids[Math.min(flow.step, ids.length - 1)] ?? null;
    return {
      ...NONE,
      active: true,
      on: new Set(current ? [current] : []),
      near: new Set(ids.filter(id => id !== current)),
      current,
    };
  }
  const focused = hovered ?? selected;
  if (focused) return focusBrick(bricks, focused);
  if (family) return focusSet(bricks.filter(b => b.family === family).map(b => b.id));
  if (matches) return focusSet(matches);
  return NONE;
}

/** The step numbers each brick of a journey carries ("2·5"). */
export function stepNumbers(flow: FlowView): Map<string, string> {
  const numbers = new Map<string, number[]>();
  flow.steps.forEach((s, i) => numbers.set(s.brick, [...(numbers.get(s.brick) ?? []), i + 1]));
  return new Map([...numbers].map(([id, list]) => [id, list.join('·')]));
}

/**
 * The bricks a search matches, in map order — on the words a reader would type:
 * the name, the role, the goal, the family, and the identifiers (domains,
 * screens, technologies, paths).
 */
export function matchBricks(
  bricks: readonly BrickView[],
  families: readonly FamilyView[],
  query: string
): string[] {
  const needle = foldForSearch(query.trim());
  if (!needle) return [];
  const familyName = new Map(families.map(f => [f.id, f.name]));
  return bricks
    .filter(b =>
      foldForSearch(
        [
          b.name,
          b.role,
          b.goal ?? '',
          familyName.get(b.family) ?? '',
          ...b.domains,
          ...b.surfaces,
          ...b.stack,
          ...b.paths,
        ].join(' ')
      ).includes(needle)
    )
    .map(b => b.id);
}
