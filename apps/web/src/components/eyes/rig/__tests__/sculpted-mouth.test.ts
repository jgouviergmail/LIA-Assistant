import { describe, expect, it, vi } from 'vitest';
import { mouthPath, sculptedMouthContours } from '../face-geometry';
import { restChannelValues, type ChannelValues } from '../channels';
import { createRigWriter } from '../apply';
import { createEyeRig } from '../runtime';

function points(path: string) {
  return (path.match(/-?\d+(?:\.\d+)?/g) ?? []).map(Number);
}

function cubic(a: number, b: number, c: number, d: number, t = 0.5) {
  const u = 1 - t;
  return u ** 3 * a + 3 * u ** 2 * t * b + 3 * u * t ** 2 * c + t ** 3 * d;
}

function depth(path: string, t = 0.5) {
  const p = points(path);
  const lower =
    p.length === 28
      ? t >= 0.5
        ? cubic(p[11], p[13], p[15], p[17], (1 - t) * 2)
        : cubic(p[17], p[19], p[21], p[23], (1 - t) * 2 - 1)
      : cubic(p[11], p[13], p[15], p[17], 1 - t);
  return lower - cubic(p[1], p[3], p[5], p[7], t);
}

function pose(curve: number, open = 0): ChannelValues {
  return { ...restChannelValues(), mouthCurve: curve, mouthArc: Math.abs(curve), mouthOpen: open };
}

function host(sculpted = true) {
  const root = document.createElement('span');
  root.innerHTML = `<svg><path data-rig-mouth="" ${sculpted ? 'data-rig-mouth-shape="sculpted"' : ''}/><path data-rig-mouth-teeth=""/><path data-rig-mouth-tongue=""/></svg>`;
  const cavity = root.querySelector<SVGPathElement>('[data-rig-mouth]')!;
  const teeth = root.querySelector<SVGPathElement>('[data-rig-mouth-teeth]')!;
  const tongue = root.querySelector<SVGPathElement>('[data-rig-mouth-tongue]')!;
  return { writer: createRigWriter(root), cavity, teeth, tongue };
}

describe('Smiley sculpted mouth projection', () => {
  it('renders the chosen slightly open resting smile while joy keeps its approved deep bowl', () => {
    const neutral = sculptedMouthContours(pose(0.36));
    expect(neutral.cavity).toBe(
      'M 10 29 C 28 32 72 32 90 29 Q 92 29 89 33 C 80 42 65 47 50 47 C 35 47 20 42 11 33 Q 8 29 10 29 Z'
    );
    expect(neutral.teeth).toBe(
      'M 26 31 C 38 33 62 33 74 31 Q 73.5 33.5 73 36 C 66 37 58 37.5 50 37.5 C 42 37.5 34 37 27 36 Q 26.5 33.5 26 31 Z'
    );
    expect(depth(neutral.cavity)).toBe(15.75);
    expect(depth(neutral.teeth)).toBe(5);
    const joy = sculptedMouthContours(pose(0.9, 0.12));
    expect(joy).toEqual({
      cavity:
        'M 7.096 23 C 30.264 34.22 69.736 34.22 92.904 23 Q 95.904 25.64 92.904 28.28 C 69.736 73.333 30.264 73.333 7.096 28.28 Q 4.096 25.64 7.096 23 Z',
      teeth:
        'M 7.096 24.6 C 30.264 35.82 69.736 35.82 92.904 24.6 Q 95.904 27.75 92.904 30.9 C 69.736 44.82 30.264 44.82 7.096 30.9 Q 4.096 27.75 7.096 24.6 Z',
      tongue:
        'M 39.708 61.501 C 39.708 59.407 44.316 57.71 50 57.71 C 55.684 57.71 60.292 59.407 60.292 61.501 C 60.292 63.595 55.684 65.293 50 65.293 C 44.316 65.293 39.708 63.595 39.708 61.501 Z',
    });
    // A .95em SVG at font-size44 gives .5225 rendered pixels per SVG unit.
    expect(depth(joy.cavity) * 0.5225).toBeGreaterThanOrEqual(15);
    expect(depth(joy.cavity) * 0.5225).toBeLessThanOrEqual(17);
    expect(depth(joy.teeth)).toBeLessThan(9);
    const tongue = points(joy.tongue).filter((_, index) => index % 2 === 0);
    expect(Math.max(...tongue) - Math.min(...tongue)).toBeGreaterThanOrEqual(18);
  });

  it('keeps rest and frown closed, while a grin has raised corners and a deep U cavity', () => {
    const rest = sculptedMouthContours(pose(0.12));
    const frown = sculptedMouthContours(pose(-0.85));
    const grin = sculptedMouthContours(pose(0.9, 0.12));
    expect(depth(rest.cavity)).toBeLessThan(4);
    expect(depth(frown.cavity)).toBeLessThan(4);
    expect(depth(grin.cavity)).toBeGreaterThan(20);
    const p = points(grin.cavity);
    expect(cubic(p[1], p[3], p[5], p[7])).toBeGreaterThan(p[1]);
    expect(depth(rest.teeth)).toBe(0);
    expect(depth(frown.teeth)).toBe(0);
  });

  it('articulates OU speech with increasing depth and slightly tightening corners', () => {
    let lastDepth = 0;
    let lastWidth = Infinity;
    for (const open of [0.08, 0.22, 0.44, 0.66]) {
      const cavity = sculptedMouthContours(pose(0.2, open)).cavity;
      const p = points(cavity);
      expect(depth(cavity)).toBeGreaterThan(lastDepth);
      expect(p[6] - p[0]).toBeLessThan(lastWidth);
      lastDepth = depth(cavity);
      lastWidth = p[6] - p[0];
    }
  });

  it('rounds a real spoken opening into OU instead of a broad rectangular slot', () => {
    for (const curve of [0.12, 0.2, 0.36]) {
      const spoken = sculptedMouthContours(pose(curve, 0.624));
      const cavity = points(spoken.cavity);
      const tooth = points(spoken.teeth);
      // The two side quadratics extend1.5 units each. Include the .8-unit lip rim.
      const width = cavity[6] - cavity[0] + 3.8;
      expect((width * 1.45 * 44) / 100).toBeGreaterThanOrEqual(30);
      expect((width * 1.45 * 44 * 1.18) / 100).toBeLessThanOrEqual(40);
      expect(depth(spoken.cavity) * 0.5225).toBeGreaterThanOrEqual(12);
      expect(depth(spoken.cavity) * 0.5225).toBeLessThanOrEqual(16);
      expect(cubic(cavity[1], cavity[3], cavity[5], cavity[7])).toBeLessThan(cavity[1] - 3);
      expect(cubic(tooth[1], tooth[3], tooth[5], tooth[7])).toBeLessThan(tooth[1] - 3);
    }
  });

  it('opens the native jaw monotonically even when a strong smile already has a deep bowl', () => {
    for (const curve of [0.12, 0.32, 0.36, 0.399, 0.4, 0.401, 0.5, 0.56, 0.9, 1]) {
      let previous = 0;
      for (const open of Array.from({ length: 101 }, (_, index) => index / 100)) {
        const cavity = sculptedMouthContours(pose(curve, open)).cavity;
        expect(depth(cavity)).toBeGreaterThan(previous);
        previous = depth(cavity);
      }
    }
    const before = points(sculptedMouthContours(pose(0.399)).cavity);
    const after = points(sculptedMouthContours(pose(0.401)).cavity);
    expect(Math.max(...after.map((n, i) => Math.abs(n - before[i])))).toBeLessThan(0.1);
  });

  it('retains native asymmetric acting and approaches rest without a contour jump', () => {
    const neutral = pose(0.36);
    const left = points(sculptedMouthContours({ ...neutral, mouthSkew: -1 }).cavity);
    const right = points(sculptedMouthContours({ ...neutral, mouthSkew: 1 }).cavity);
    expect(left[1]).toBeGreaterThan(left[7]);
    expect(right[1]).toBeLessThan(right[7]);
    for (const curve of [0.12, 0.32, 0.4, 0.56]) {
      const before = sculptedMouthContours(pose(curve - 0.0001)).cavity;
      const after = sculptedMouthContours(pose(curve + 0.0001)).cavity;
      for (const t of [0, 0.2, 0.5, 0.8, 1])
        expect(Math.abs(depth(after, t) - depth(before, t))).toBeLessThan(0.03);
    }
    const almostRest = sculptedMouthContours(pose(0.36, 0.0001));
    expect(
      Math.abs(depth(almostRest.cavity) - depth(sculptedMouthContours(neutral).cavity))
    ).toBeLessThan(0.01);
  });

  it('follows the upper lip with curved teeth instead of a fixed white rectangle', () => {
    const flat = sculptedMouthContours(pose(0.4, 0.3));
    const smile = sculptedMouthContours(pose(0.9, 0.3));
    const cavity = points(smile.cavity);
    const teeth = points(smile.teeth);
    expect(smile.teeth).not.toBe(flat.teeth);
    expect(teeth[3] - teeth[1]).toBeCloseTo(cavity[3] - cavity[1], 3);
    expect(teeth[5] - teeth[7]).toBeCloseTo(cavity[5] - cavity[7], 3);
    expect(depth(smile.teeth)).toBeGreaterThan(4);
    expect(depth(smile.teeth)).toBeLessThan(depth(smile.cavity));
  });

  it('places a growing curved tongue near the floor as the jaw opens', () => {
    const closed = points(sculptedMouthContours(pose(0.2)).tongue);
    const open = points(sculptedMouthContours(pose(0.2, 0.66)).tongue);
    expect(Math.max(...closed.filter((_, index) => index % 2 === 0))).toBe(50);
    expect(Math.max(...open.filter((_, index) => index % 2 === 0))).toBeGreaterThan(60);
    expect(Math.max(...open.filter((_, index) => index % 2 === 1))).toBeGreaterThan(
      Math.max(...closed.filter((_, index) => index % 2 === 1))
    );
  });

  it('stays continuous and never crosses its lips throughout signed expression and jaw extremes', () => {
    for (const curve of [
      -1, -0.85, -0.001, 0, 0.001, 0.12, 0.2, 0.32, 0.36, 0.4, 0.5, 0.56, 0.9, 1,
    ]) {
      for (const open of [0, 0.22, 0.66, 1]) {
        for (const skew of [-1, 0, 1]) {
          const drawing = sculptedMouthContours({ ...pose(curve, open), mouthSkew: skew });
          for (const path of Object.values(drawing)) {
            expect(path).toMatch(/ Z$/);
            expect(points(path).every(n => Number.isFinite(n) && n >= 0 && n <= 100)).toBe(true);
            expect(
              points(path)
                .filter((_, i) => i % 2 === 1)
                .every(y => y <= 80)
            ).toBe(true);
          }
          for (const t of [0, 0.2, 0.5, 0.8, 1])
            expect(depth(drawing.cavity, t)).toBeGreaterThan(0);
        }
      }
    }
    const before = points(sculptedMouthContours(pose(-0.001)).cavity);
    const after = points(sculptedMouthContours(pose(0.001)).cavity);
    expect(Math.max(...after.map((n, i) => Math.abs(n - before[i])))).toBeLessThan(0.1);
    const invalid = sculptedMouthContours({ ...pose(Infinity), mouthOpen: NaN, mouthSkew: -999 });
    expect(points(invalid.cavity).every(Number.isFinite)).toBe(true);
  });

  it('projects only the opted-in mouth, caches settled paths and restores classic contours', () => {
    const { writer, cavity, teeth, tongue } = host();
    const values = pose(0.9, 0.35);
    const drawing = sculptedMouthContours(values);
    writer.write(values);
    expect(cavity).toHaveAttribute('d', drawing.cavity);
    expect(teeth).toHaveAttribute('d', drawing.teeth);
    expect(tongue).toHaveAttribute('d', drawing.tongue);
    const writes = [cavity, teeth, tongue].map(path => vi.spyOn(path, 'setAttribute'));
    writer.write(values);
    writes.forEach(write => expect(write).not.toHaveBeenCalled());
    delete cavity.dataset.rigMouthShape;
    writer.write(values);
    expect(cavity).toHaveAttribute('d', mouthPath(values));
    expect(teeth).toHaveAttribute('d', '');
    expect(tongue).toHaveAttribute('d', '');
    cavity.dataset.rigMouthShape = 'sculpted';
    writer.write(values);
    expect(cavity).toHaveAttribute('d', drawing.cavity);
  });

  it('leaves non-opted-in Spirit and monitor mouth profiles unchanged', () => {
    const { writer, cavity, teeth, tongue } = host(false);
    for (const values of [pose(-0.85), pose(0.12), pose(0.9, 0.12), pose(0.2, 0.66)]) {
      writer.write(values);
      expect(cavity).toHaveAttribute('d', mouthPath(values));
      expect(teeth).toHaveAttribute('d', '');
      expect(tongue).toHaveAttribute('d', '');
    }
  });

  it('follows the existing generated speaking rig without another animation clock', () => {
    const { writer, cavity, teeth, tongue } = host();
    const rig = createEyeRig({
      initial: { expression: 'speaking', styleId: 'smiley', family: 'calm' },
    });
    const drawings = new Set<string>();
    for (let ms = 0; ms < 2400; ms += 16) {
      rig.step(16);
      writer.write(rig.values());
      drawings.add(cavity.getAttribute('d')!);
      expect(depth(cavity.getAttribute('d')!)).toBeGreaterThan(0);
      expect(teeth.getAttribute('d')).toMatch(/ Z$/);
      expect(tongue.getAttribute('d')).toMatch(/ Z$/);
    }
    expect(drawings.size).toBeGreaterThan(20);
  });
});
