import { describe, expect, it } from 'vitest';
import { WORLD } from '../definition';
import { compilePoseSlots } from '../pose-slots';
import { compileNavigation, findRoute } from '../navigation';
import { compileSeatContexts, seatContext } from '../seat-context';
import { authoredActivity } from '../activity-catalogue';

describe('explicit table and seat relationships', () => {
  it.each(['bed', 'lounger', 'bench', 'toilet'] as const)(
    'does not offer a dashboard on a %s even if authored beside a table',
    kind => {
      const seat = WORLD.props.find(prop => prop.key === 'atrium-n')!;
      const table = WORLD.props.find(prop => prop.key === seat.tableKey)!;
      const contexts = compileSeatContexts({ ...WORLD, props: [{ ...seat, kind }, table] });
      expect(contexts.get('atrium-n:0')?.dashboardEligible).toBe(false);
    }
  );
  it('binds every generic table to a real reachable seat without stealing a native activity', () => {
    const contexts = compileSeatContexts(WORLD);
    const slots = compilePoseSlots(WORLD);
    const nav = compileNavigation(WORLD);
    for (const table of WORLD.props.filter(p => p.kind === 'table')) {
      expect(table.key, table.id).toBeTruthy();
      const bound = [...contexts.entries()].filter(([, value]) => value.tableKey === table.key);
      expect(bound.length, table.id).toBeGreaterThan(0);
      for (const [id, value] of bound) {
        const slot = slots.find(s => s.id === id)!;
        expect(findRoute(nav, WORLD.spawn, slot.approach).length, id).toBeGreaterThan(0);
        expect(value.activity).toEqual(authoredActivity(table.activity));
        expect(value.dashboardEligible).toBe(!table.activity);
        expect(seatContext(id)).toEqual(value);
      }
    }
    expect(seatContext('meeting-boss:0')?.activity).toEqual({ kind: 'workspace', id: 'meetings' });
    expect(seatContext('library-seat-2:0')?.activity).toEqual({
      kind: 'native',
      token: 'rag-spaces',
    });
    expect(seatContext('wc-seat:0')?.tableKey).toBeNull();
  });
  it('rejects duplicate keys and associations with no real table', () => {
    const seat = WORLD.props.find(p => p.key === 'atrium-n')!;
    expect(() =>
      compileSeatContexts({ ...WORLD, props: [...WORLD.props, { ...seat, id: 'duplicate' }] })
    ).toThrow('duplicate');
    expect(() =>
      compileSeatContexts({ ...WORLD, props: [{ ...seat, tableKey: 'absent' }] })
    ).toThrow('table');
  });
  it('inherits a registered table activity instead of offering an unrelated dashboard', () => {
    const seat = WORLD.props.find(prop => prop.key === 'atrium-n')!;
    const table = WORLD.props.find(prop => prop.key === seat.tableKey)!;
    const contexts = compileSeatContexts({
      ...WORLD,
      props: [seat, { ...table, activity: 'meetings' }],
    });
    expect(contexts.get('atrium-n:0')?.activity).toEqual({ kind: 'workspace', id: 'meetings' });
    expect(contexts.get('atrium-n:0')?.dashboardEligible).toBe(false);
  });
  it.each(['seat', 'table'])(
    'does not reinterpret a registered %s activity as a dashboard',
    target => {
      const seat = WORLD.props.find(prop => prop.key === 'atrium-n')!;
      const table = WORLD.props.find(prop => prop.key === seat.tableKey)!;
      const contexts = compileSeatContexts({
        ...WORLD,
        props: [
          { ...seat, ...(target === 'seat' ? { activity: 'memories' } : {}) },
          { ...table, ...(target === 'table' ? { activity: 'memories' } : {}) },
        ],
      });
      expect(contexts.get('atrium-n:0')?.dashboardEligible).toBe(false);
    }
  );
});
