import { describe, expect, it } from 'vitest';
import { createRigWriter } from '../apply';
import { restChannelValues } from '../channels';
import { createEyeRig } from '../runtime';

function face() {
  const root = document.createElement('span');
  root.innerHTML =
    '<svg><path data-rig-mouth=""/><path data-rig-brow="L"/><path data-rig-brow="R"/></svg>';
  const writer = createRigWriter(root);
  return { root, writer };
}

function coordinates(root: HTMLElement, selector = '[data-rig-mouth]'): number[] {
  const path = root.querySelector(selector)?.getAttribute('d');
  expect(path).toBeTruthy();
  return (path?.match(/-?\d+(?:\.\d+)?/g) ?? []).map(Number);
}

describe('continuous facial geometry', () => {
  it('draws a continuous asymmetric mouth through the smile/frown crossing', () => {
    const { root, writer } = face();
    const values = { ...restChannelValues(), mouthSkew: 0.4 };
    writer.write({ ...values, mouthCurve: -0.019 });
    const before = coordinates(root);
    writer.write({ ...values, mouthCurve: -0.021 });
    const after = coordinates(root);
    expect(before.length).toBeGreaterThan(8);
    expect(after).toHaveLength(before.length);
    expect(Math.max(...after.map((n, i) => Math.abs(n - before[i])))).toBeLessThan(0.2);
  });

  it('keeps the projected mouth continuous throughout the actual thinking arrival', () => {
    const { root, writer } = face();
    const rig = createEyeRig({
      initial: { expression: 'neutral', styleId: 'capsules', family: 'calm' },
    });
    writer.write(rig.values());
    let previous = coordinates(root);
    rig.setPose({
      expression: 'thinking',
      styleId: 'capsules',
      family: 'calm',
    });
    for (let ms = 0; ms < 1200; ms += 8) {
      rig.step(8);
      writer.write(rig.values());
      const next = coordinates(root);
      expect(Math.max(...next.map((n, i) => Math.abs(n - previous[i])))).toBeLessThan(2);
      previous = next;
    }
  });

  it('articulates each brow without forcing the other side to move', () => {
    const { root, writer } = face();
    const values = restChannelValues();
    writer.write(values);
    const left = coordinates(root, '[data-rig-brow="L"]');
    const right = coordinates(root, '[data-rig-brow="R"]');
    writer.write({ ...values, browArcL: 0.8, browRotL: -12 });
    expect(coordinates(root, '[data-rig-brow="L"]')).not.toEqual(left);
    expect(coordinates(root, '[data-rig-brow="R"]')).toEqual(right);
  });
});
