import { describe, expect, it, vi } from 'vitest';
import { upperLashPath, createLashWriter } from '../smiley/lash-geometry';
import { resolvePose } from '../rig/poses';
import { projectSmileyCrown, spherePose } from '../smiley/sphere-geometry';

function roots(path: string) {
  return [...path.matchAll(/M ([\d.-]+) ([\d.-]+)/g)].map(match => ({
    x: Number(match[1]),
    y: Number(match[2]),
  }));
}

describe('Smiley curved upper lashes and crown attachment', () => {
  it('omits the inner lash on each eye, keeps the upper arc mirrored, then follows the closing native lid', () => {
    const pose = resolvePose('neutral', 'smiley');
    const open = roots(upperLashPath(pose, 'L'));
    const right = roots(upperLashPath(pose, 'R'));
    expect(open).toHaveLength(4);
    expect(right).toHaveLength(4);
    expect(open.at(-1)!.x).toBeLessThan(100 - open[0].x);
    expect(right[0].x).toBeGreaterThan(100 - right.at(-1)!.x);
    expect(right).toEqual(open.map(point => ({ x: 100 - point.x, y: point.y })).reverse());
    expect(open[0].y - open[2].y).toBeGreaterThan(30);
    expect(open[3].y).toBe(open[1].y);
    const mid = roots(upperLashPath({ ...pose, blinkL: 0.5 }, 'L'));
    expect(mid[0].y - mid[2].y).toBeLessThan(open[0].y - open[2].y);
    expect(mid[2].y).toBe(open[2].y);
    const closed = roots(upperLashPath({ ...pose, blinkL: 1 }, 'L'));
    expect(closed.every(point => point.y === closed[2].y)).toBe(true);
  });
  it('does not reformat idle contours or let mouth-only motion rewrite eyelashes', () => {
    const host = document.createElement('span');
    host.innerHTML = '<svg><path data-smiley-lashes="L"/><path data-smiley-lashes="R"/></svg>';
    const writer = createLashWriter(host),
      pose = resolvePose('neutral', 'smiley');
    writer.write(pose);
    const path = host.querySelector('path')!;
    const write = vi.spyOn(path, 'setAttribute');
    writer.write(pose);
    writer.write({ ...pose, mouthOpen: 0.6 });
    expect(write).not.toHaveBeenCalled();
    writer.write({ ...pose, blinkL: 0.5 });
    expect(write).toHaveBeenCalledOnce();
  });
  it('places the bow at the exact crown center at rest and preserves its upright volume under gaze/pitch', () => {
    const pose = resolvePose('neutral', 'smiley');
    const crown = projectSmileyCrown(spherePose(pose));
    expect(crown.x).toBe(0);
    expect(crown.y).toBe(-1.3);
    expect(crown.a).toBe(1);
    expect(crown.d).toBe(1);
    for (const headYaw of [-1, 1])
      for (const headPitch of [-1, 1]) {
        const turned = projectSmileyCrown(spherePose({ ...pose, headYaw, headPitch }));
        expect(Math.abs(turned.x)).toBeLessThan(0.15);
        expect(turned.y).toBeLessThan(-1.2);
        expect(turned.z).toBeGreaterThan(0);
        expect(turned.d).toBeGreaterThan(0.98);
      }
  });
});
