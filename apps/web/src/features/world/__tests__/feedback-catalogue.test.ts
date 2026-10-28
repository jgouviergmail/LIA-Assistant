import { expect, it } from 'vitest';
import { WORLD } from '../definition';
import { functionPlace, worldActions } from '../functions';
import { zoneAt } from '../simulation';

it('lists SMS in the atrium where the native phone can be opened', () => {
  expect(functionPlace('sms')).toBe('arrival');
  expect(
    WORLD.props.some(prop => zoneAt(WORLD, prop) === 'arrival' && prop.activity === 'sms')
  ).toBe(true);
});
it('moves News onto the meeting lounge table and removes the cafeteria news desk', () => {
  const news = WORLD.props.filter(prop => prop.activity === 'news');
  expect(news).toHaveLength(1);
  expect(news[0]).toMatchObject({ key: 'meeting-lounge-table', kind: 'table' });
  expect(zoneAt(WORLD, news[0])).toBe('meeting');
  expect(worldActions(key => key).find(action => action.id === 'news')?.place).toBe('meeting');
  expect(WORLD.props.some(prop => zoneAt(WORLD, prop) === 'cafeteria' && prop.key === 'news')).toBe(
    false
  );
});
it('reserves only the rightmost weight bench for Health', () => {
  const benches = WORLD.props.filter(prop => prop.kind === 'weightbench').sort((a, b) => a.x - b.x);
  expect(benches).toHaveLength(3);
  expect(benches.map(prop => prop.activity)).toEqual([undefined, undefined, 'health']);
});
