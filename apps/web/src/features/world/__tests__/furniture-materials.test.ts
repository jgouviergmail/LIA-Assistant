import { expect, it } from 'vitest';
import { Model } from '../art/model';
import { modelTable } from '../art/model-details';

it('retains the authored tabletop material instead of replacing every surface with oak', () => {
  const paint = (color: string) => {
    const model = new Model();
    modelTable(model, 3, 2, color);
    return model.parts.filter(part => part.kind === 'face');
  };
  const walnut = paint('#594039');
  const enamel = paint('#e2ded0');
  expect(walnut.length).toBeGreaterThan(0);
  expect(walnut.map(part => part.color)).not.toEqual(enamel.map(part => part.color));
  expect(walnut.map(part => part.kind)).toEqual(enamel.map(part => part.kind));
});
