/**
 * What a brick map lights up: one order of precedence for both maps — the
 * journey being played, then the brick under the pointer, then the selection,
 * then the isolated family, then the search.
 */

import { describe, expect, it } from 'vitest';

import { mapsData } from '../data';
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

  it('lets the prose answer only when no name or identifier does', () => {
    // 'fil' is in the role of f.one alone, and in no name or identifier.
    expect(matchBricks(map.bricks, map.families, 'fil')).toEqual(['f.one']);
    // 'prevenir' is f.three's role AND its family: the family wins, the prose adds nothing.
    expect(matchBricks(map.bricks, map.families, 'prevenir')).toEqual(['f.three']);
  });

  it('puts the bricks named after the search before those it only identifies', () => {
    // Family 'Converser' holds f.one and f.two; only f.one is NAMED 'Conversation'.
    // In reverse map order f.two comes first, and the name still leads: Enter opens it.
    const reversed = [...map.bricks].reverse();
    expect(matchBricks(reversed, map.families, 'convers')).toEqual(['f.one', 'f.two']);
  });

  it('answers the searches measured on the real functional map', () => {
    // 2026-10-29: each of these lit bricks that only MENTION the word, and Enter
    // opened one of them ('agenda' → request understanding, 'telephone' → personalities).
    const real = buildBrickMap(mapsData('fr'), 'functional');
    const search = (query: string): string[] => matchBricks(real.bricks, real.families, query);
    expect(search('radio')).toEqual(['f.radio']);
    expect(search('agenda')).toEqual(['f.calendar']);
    expect(search('rappel')).toEqual(['f.reminders']);
    expect(search('téléphone')).toEqual(['f.telephony']);
    expect(search('monde')).toEqual(['f.world']);
    expect(search('image')).toEqual(['f.images']);
    // No brick is NAMED after the voice: the bricks that speak of it still answer.
    expect(search('voix')).toContain('f.voice');
  });

  it('searches the stack and the paths of the technical map', () => {
    const technical = buildBrickMap(mapsDataFixture(), 'technical');
    expect(matchBricks(technical.bricks, technical.families, 'pydantic')).toEqual(['t.one']);
    expect(matchBricks(technical.bricks, technical.families, 'src/core')).toEqual(['t.one']);
  });
});
