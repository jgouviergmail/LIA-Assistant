/**
 * What a brick map lights up: one order of precedence for both maps — the
 * journey being played, then the brick under the pointer, then the selection,
 * then the isolated family, then the search.
 */

import { describe, expect, it } from 'vitest';

import { computeHighlight, edgeKey, matchBricks, stepNumbers } from '../highlight';
import { buildBrickMap } from '../model';
import { mapsDataFixture } from './fixtures';

const map = buildBrickMap(mapsDataFixture(), 'functional');
const base = {
  bricks: map.bricks,
  flow: null,
  hovered: null,
  selected: null,
  family: null,
  matches: null,
};

describe('computeHighlight', () => {
  it('lights nothing at rest', () => {
    expect(computeHighlight(base).active).toBe(false);
  });

  it('traces a focused brick: its dependencies out, its users in', () => {
    const h = computeHighlight({ ...base, selected: 'f.one' });
    expect(h.active).toBe(true);
    expect([...h.on]).toEqual(['f.one']);
    expect([...h.near].sort()).toEqual(['f.three', 'f.two']);
    expect([...h.out]).toEqual([edgeKey('f.one', 'f.two')]);
    expect([...h.in]).toEqual([edgeKey('f.three', 'f.one')]);
  });

  it('lets the pointer win over the selection, and the journey win over both', () => {
    expect([...computeHighlight({ ...base, selected: 'f.one', hovered: 'f.two' }).on]).toEqual([
      'f.two',
    ]);
    const journey = computeHighlight({
      ...base,
      selected: 'f.one',
      hovered: 'f.two',
      flow: { flow: map.flows[0], step: 3 },
    });
    expect(journey.current).toBe('f.three');
    expect([...journey.on]).toEqual(['f.three']);
    expect([...journey.near].sort()).toEqual(['f.one', 'f.two']);
    expect(journey.out.size).toBe(0);
  });

  it('isolates a family, then a search, when nothing is focused', () => {
    expect([...computeHighlight({ ...base, family: 'g.a' }).on]).toEqual(['f.one', 'f.two']);
    expect([...computeHighlight({ ...base, matches: new Set(['f.three']) }).on]).toEqual([
      'f.three',
    ]);
    // A search that matches nothing still dims the whole map.
    expect(computeHighlight({ ...base, matches: new Set() }).active).toBe(true);
  });

  it('ignores a focus on a brick the map does not hold', () => {
    expect(computeHighlight({ ...base, selected: 'f.gone' }).active).toBe(false);
  });
});

describe('stepNumbers', () => {
  it('groups the step numbers each brick carries in a journey', () => {
    expect(Object.fromEntries(stepNumbers(map.flows[0]))).toEqual({
      'f.one': '1',
      'f.two': '2·3',
      'f.three': '4',
    });
  });
});

describe('matchBricks', () => {
  it('matches names, roles, goals, families and identifiers, accents folded', () => {
    expect(matchBricks(map.bricks, map.families, 'memoire')).toEqual(['f.two']);
    expect(matchBricks(map.bricks, map.families, 'PRÉVENIR')).toEqual(['f.three']);
    expect(matchBricks(map.bricks, map.families, 'dashboard/chat')).toEqual(['f.one']);
    expect(matchBricks(map.bricks, map.families, 'converser')).toEqual(['f.one', 'f.two']);
    expect(matchBricks(map.bricks, map.families, '   ')).toEqual([]);
  });

  it('searches the stack and the paths of the technical map', () => {
    const technical = buildBrickMap(mapsDataFixture(), 'technical');
    expect(matchBricks(technical.bricks, technical.families, 'pydantic')).toEqual(['t.one']);
    expect(matchBricks(technical.bricks, technical.families, 'src/core')).toEqual(['t.one']);
  });
});
