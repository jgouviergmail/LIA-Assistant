import { expect, it } from 'vitest';
import {
  COSMETIC_ACTIONS,
  cosmeticActionForId,
  cosmeticPropTarget,
} from '../cosmetic-interactions';
import { WORLD } from '../definition';
import { ambientLifeAt, catAt } from '../world-life';
import { NEUTRAL_ATMOSPHERE } from '../atmosphere';
it('binds every clickable response to existing art, excluding flowers and birds', () => {
  const cat = catAt(WORLD, 0);
  if (!cat) throw new Error('Missing cat');
  const targets = [...WORLD.props, cat].flatMap(prop => {
    const target = cosmeticPropTarget(prop);
    return target ? [target] : [];
  });
  targets.push(
    ...ambientLifeAt(
      WORLD,
      { ...NEUTRAL_ATMOSPHERE, phase: 'afternoon', sunny: true },
      0,
      'high',
      false
    ).filter(target => target.action !== 'bird')
  );
  expect(new Set(targets.map(target => target.action))).toEqual(new Set(COSMETIC_ACTIONS));
  for (const target of targets) expect(cosmeticActionForId(WORLD, target.id)).toBe(target.action);
  for (const id of ['ambient-cat-evil', 'ambient-bird-3', 'ambient-butterfly-4', 'unknown'])
    expect(cosmeticActionForId(WORLD, id)).toBeNull();
  expect(cosmeticPropTarget({ ...cat, kind: 'bed' })).toBeNull();
  for (const prop of WORLD.props.filter(prop => prop.kind === 'flowers'))
    expect(cosmeticPropTarget(prop)).toBeNull();
  expect(cosmeticPropTarget({ ...cat, kind: 'desk', tone: 'sage' })).toBeNull();
  expect(cosmeticActionForId({ props: [{ ...cat, id: 'bed', kind: 'bed' }] }, 'bed')).toBeNull();
});
