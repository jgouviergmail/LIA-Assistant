import { describe, expect, it, vi } from 'vitest';
import { browPath, sculptedBrowPath } from '../face-geometry';
import { restChannelValues } from '../channels';
import { createRigWriter } from '../apply';

function points(path: string) {
  return (path.match(/-?\d+(?:\.\d+)?/g) ?? []).map(Number);
}

function face() {
  const root = document.createElement('span');
  root.innerHTML = '<svg><path data-rig-brow="L"/><path data-rig-brow="R"/></svg>';
  const left = root.querySelector<SVGPathElement>('[data-rig-brow="L"]')!;
  const right = root.querySelector<SVGPathElement>('[data-rig-brow="R"]')!;
  return { writer: createRigWriter(root), left, right };
}

describe('Opt-in sculpted toon brows', () => {
  it('draws a closed tapered volume, anatomically mirrored on the right', () => {
    const values = restChannelValues();
    const left = sculptedBrowPath(values, 'L');
    const right = sculptedBrowPath(values, 'R');
    expect(left).toMatch(/ Z$/);
    expect(right).toMatch(/ Z$/);
    expect(browPath(values, 'L')).not.toMatch(/ Z$/);
    const leftPoints = points(left);
    const rightPoints = points(right);
    expect(rightPoints).toHaveLength(leftPoints.length);
    for (let index = 0; index < leftPoints.length; index += 2) {
      expect(leftPoints[index] + rightPoints[index]).toBe(100);
      expect(leftPoints[index + 1]).toBe(rightPoints[index + 1]);
    }
  });

  it('keeps each side independent and smoothly changes from raised to angled', () => {
    const values = restChannelValues();
    const right = sculptedBrowPath(values, 'R');
    const raised = { ...values, browArcL: 0.85, browRotL: -12 };
    expect(sculptedBrowPath(raised, 'L')).not.toBe(sculptedBrowPath(values, 'L'));
    expect(sculptedBrowPath(raised, 'R')).toBe(right);
    const before = points(sculptedBrowPath(raised, 'L'));
    const after = points(sculptedBrowPath({ ...raised, browArcL: 0.851 }, 'L'));
    expect(Math.max(...after.map((value, index) => Math.abs(value - before[index])))).toBeLessThan(
      0.1
    );
    const extreme = points(
      sculptedBrowPath({ ...values, browArcL: Infinity, browRotL: -999 }, 'L')
    );
    expect(extreme.every(Number.isFinite)).toBe(true);
  });

  it('projects only the opted-in path and keeps the classic brow unchanged', () => {
    const { writer, left, right } = face();
    left.dataset.rigBrowShape = 'sculpted';
    const values = { ...restChannelValues(), browArcL: 0.85, browRotL: -12 };
    writer.write(values);
    expect(left.getAttribute('d')).toBe(sculptedBrowPath(values, 'L'));
    expect(right.getAttribute('d')).toBe(browPath(values, 'R'));
    const writes = vi.spyOn(left, 'setAttribute');
    writer.write(values);
    expect(writes).not.toHaveBeenCalled();
  });

  it('reprojects a style change on a settled pose without adding a new clock', () => {
    const { writer, left, right } = face();
    const values = restChannelValues();
    writer.write(values);
    const classic = left.getAttribute('d');
    const rightWrites = vi.spyOn(right, 'setAttribute');
    left.dataset.rigBrowShape = 'sculpted';
    writer.write(values);
    expect(left.getAttribute('d')).toBe(sculptedBrowPath(values, 'L'));
    expect(rightWrites).not.toHaveBeenCalled();
    delete left.dataset.rigBrowShape;
    writer.write(values);
    expect(left.getAttribute('d')).toBe(classic);
  });

  it('preserves the native brow weight as filled ribbon thickness', () => {
    const { writer, left, right } = face();
    left.dataset.rigBrowShape = right.dataset.rigBrowShape = 'sculpted';
    const values = restChannelValues();
    writer.write({ ...values, browSL: 0.94 });
    const thin = points(left.getAttribute('d')!);
    const rightBefore = right.getAttribute('d');
    writer.write({ ...values, browSL: 1.06 });
    const thick = points(left.getAttribute('d')!);
    expect(thick[3]).toBe(thin[3]);
    expect(thick[13]).toBeGreaterThan(thin[13]);
    expect(thick[17]).toBeGreaterThan(thin[17]);
    expect(right.getAttribute('d')).toBe(rightBefore);
  });

  it('has visible central volume rather than a thin closed arch', () => {
    const contour = points(sculptedBrowPath(restChannelValues(), 'L'));
    const top = (contour[1] + 3 * contour[3] + 3 * contour[5] + contour[7]) / 8;
    const bottom = (contour[11] + 3 * contour[13] + 3 * contour[15] + contour[17]) / 8;
    expect(bottom - top).toBeGreaterThanOrEqual(16);
  });
});
