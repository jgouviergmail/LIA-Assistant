/**
 * The views the maps' pages hand their client components: every reference
 * resolved, nothing left to join in the browser.
 */

import { describe, expect, it } from 'vitest';

import {
  DRAWER_DECISIONS,
  asTone,
  brickRefs,
  buildBrickMap,
  buildHistory,
  buildSummary,
  decisionsByBrick,
  kindOf,
  relatedBricks,
  reverseDeps,
} from '../model';
import { mapsDataFixture } from './fixtures';

describe('maps model', () => {
  it('names every brick of both maps with the tone of its family', () => {
    const refs = brickRefs(mapsDataFixture());
    expect(refs['f.one']).toEqual({
      id: 'f.one',
      kind: 'functional',
      name: 'Conversation',
      icon: 'brain',
      tone: 'blue',
    });
    expect(refs['f.three'].tone).toBe('rose');
    expect(refs['t.two']).toMatchObject({ kind: 'technical', name: 'Redis', tone: 'violet' });
  });

  it('reads who depends on each brick, ignoring a dependency outside the map', () => {
    const used = reverseDeps([
      { id: 'a', deps: ['b', 'elsewhere'] },
      { id: 'b', deps: [] },
      { id: 'c', deps: ['a'] },
    ]);
    expect(used.get('b')).toEqual(['a']);
    expect(used.get('a')).toEqual(['c']);
    expect(used.get('c')).toEqual([]);
  });

  it('lists the decisions that shaped a brick, newest first, in their theme tone', () => {
    const shaped = decisionsByBrick(mapsDataFixture());
    expect(shaped.get('f.one')?.map(d => d.adr)).toEqual([2, 1]);
    expect(shaped.get('f.one')?.[0]).toMatchObject({ title: 'La voix', tone: 'amber' });
    expect(shaped.get('f.two')?.map(d => d.adr)).toEqual([2]);
  });

  it('relates a brick to the bricks of the other map the same decisions shaped', () => {
    const data = mapsDataFixture();
    expect(relatedBricks(data, 'f.one')).toEqual(['t.one']);
    expect(relatedBricks(data, 't.one')).toEqual(['f.one', 'f.two']);
    expect(relatedBricks(data, 't.two')).toEqual(['f.three']);
  });

  it('builds the functional map: families counted, links both ways, journeys, decisions', () => {
    const map = buildBrickMap(mapsDataFixture(), 'functional');
    expect(map.kind).toBe('functional');
    expect(map.lede).toBe('Ce que LIA fait.');
    expect(map.families.map(f => [f.id, f.count])).toEqual([
      ['g.a', 2],
      ['g.b', 1],
    ]);
    const one = map.bricks.find(b => b.id === 'f.one');
    expect(one).toMatchObject({
      name: 'Conversation',
      goal: 'Répondre juste.',
      deps: ['f.two'],
      usedBy: ['f.three'],
      flows: ['flow.x'],
      domains: ['alpha'],
      surfaces: ['/dashboard/chat'],
      related: ['t.one'],
      decisionCount: 2,
      stack: [],
      paths: [],
    });
    expect(map.flows[0].steps.map(s => s.brick)).toEqual(['f.one', 'f.two', 'f.two', 'f.three']);
    expect(map.flows[0].steps[1].text).toBe('Elle se souvient.');
    expect(Object.keys(map.refs)).toHaveLength(5);
    expect(map.facts).toMatchObject({ version: '1.2.0', decisions: 3, domains: 2 });
  });

  it('builds the technical map: no goal, a stack, paths', () => {
    const map = buildBrickMap(mapsDataFixture(), 'technical');
    const one = map.bricks.find(b => b.id === 't.one');
    expect(one).toMatchObject({
      goal: null,
      stack: ['Python 3.14', 'Pydantic v2'],
      paths: ['apps/api/src/core'],
      usedBy: ['t.two'],
      tone: 'violet',
    });
    expect(map.repo).toBe('https://example.test/blob/main/');
  });

  it('lists at most DRAWER_DECISIONS decisions in a brick detail but counts them all', () => {
    const data = mapsDataFixture();
    const extra = DRAWER_DECISIONS + 2;
    for (let n = 10; n < 10 + extra; n += 1) {
      data.history.entries.push({
        adr: n,
        date: '2026-02-01',
        theme: 'platform',
        functional: ['f.two'],
        technical: [],
      });
      data.text.history.entries[String(n)] = { title: `Décision ${n}`, summary: 'Résumé.' };
    }
    const two = buildBrickMap(data, 'functional').bricks.find(b => b.id === 'f.two');
    expect(two?.decisions).toHaveLength(DRAWER_DECISIONS);
    expect(two?.decisionCount).toBe(extra + 1);
    expect(two?.decisions[0].adr).toBe(10 + extra - 1);
  });

  it('builds the history: themes counted, chapters named, files resolved', () => {
    const view = buildHistory(mapsDataFixture());
    expect(view.themes.map(t => [t.id, t.count])).toEqual([
      ['platform', 2],
      ['voice', 1],
    ]);
    expect(view.eras[1]).toMatchObject({ id: 'second', name: 'La suite', to: null });
    const [first, , third] = view.decisions;
    expect(first).toMatchObject({ file: 'ADR-001-First.md', bricks: ['f.one', 't.one'] });
    expect(third.file).toBeNull();
    expect(view.releases).toHaveLength(2);
  });

  it('summarises the three maps for the section home', () => {
    const summary = buildSummary(mapsDataFixture());
    expect(summary.functional).toEqual({ bricks: 3, families: 2, flows: 1 });
    expect(summary.technical).toEqual({ bricks: 2, layers: 1, flows: 1 });
    expect(summary.history).toEqual({ decisions: 3, themes: 2, eras: 2 });
    expect(summary.lede.history).toBe('Chaque décision.');
  });

  it('refuses a tone the vocabulary does not know, and a unit the language lacks', () => {
    expect(asTone('emerald')).toBe('emerald');
    expect(() => asTone('beige')).toThrow(/unknown tone/);
    const data = mapsDataFixture();
    delete data.text.functional.bricks['f.two'];
    expect(() => buildBrickMap(data, 'functional')).toThrow(/no text for f\.two/);
  });

  it('tells the map of a brick from its id', () => {
    expect(kindOf('t.redis')).toBe('technical');
    expect(kindOf('f.chat')).toBe('functional');
  });
});
