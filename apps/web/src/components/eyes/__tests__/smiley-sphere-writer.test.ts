import { describe, expect, it, vi } from 'vitest';
import { createRigWriter } from '../rig/apply';
import { restChannelValues } from '../rig/channels';
import { resolvePose } from '../rig/poses';

function face() {
  const root = document.createElement('span');
  root.dataset.style = 'smiley';
  root.innerHTML =
    '<span data-smiley-surface="left"></span><span data-smiley-surface="right"></span><span data-smiley-surface="mouth"></span>';
  const organs = [...root.querySelectorAll<HTMLElement>('[data-smiley-surface]')];
  return { root, organs, writer: createRigWriter(root) };
}

describe('Native writer projects distinct spherical organs', () => {
  it('keeps the jaw width continuous when speech enters or leaves before the next native frame', () => {
    const { root, writer } = face();
    const neutral = resolvePose('neutral', 'smiley');
    root.dataset.expression = 'neutral';
    writer.write(neutral);
    const width = root.style.getPropertyValue('--smiley-mouth-width');
    root.dataset.expression = 'speaking';
    writer.write(neutral);
    expect(root.style.getPropertyValue('--smiley-mouth-width')).toBe(width);
    const speaking = resolvePose('speaking', 'smiley');
    writer.write(speaking);
    const articulatedWidth = root.style.getPropertyValue('--smiley-mouth-width');
    expect(Number(articulatedWidth)).toBe(speaking.mouthW);
    root.dataset.expression = 'neutral';
    writer.write(speaking);
    expect(root.style.getPropertyValue('--smiley-mouth-width')).toBe(articulatedWidth);
  });

  it('preserves the exact frontal approved face, then makes the nearer eye wider than the farther one', () => {
    const { organs, writer } = face();
    const rest = restChannelValues();
    writer.write(rest);
    for (const organ of organs)
      expect(organ.style.transform).toBe('translate(0em, 0em) matrix(1, 0, 0, 1, 0, 0)');
    writer.write({ ...rest, headYaw: 1, headPitch: -1 });
    expect(organs[0].style.transform).not.toBe(organs[1].style.transform);
    const tangent = (organ: HTMLElement) =>
      Number(organ.style.transform.split('matrix(')[1].split(',')[0]);
    expect(tangent(organs[0])).toBeGreaterThan(1);
    expect(tangent(organs[1])).toBeGreaterThan(0);
    expect(tangent(organs[1])).toBeLessThan(tangent(organs[0]));
  });

  it('caches settled surface writes and stops writing after disposal', () => {
    const { root, organs, writer } = face();
    const rest = restChannelValues();
    writer.write(rest);
    const write = vi.spyOn(organs[0].style, 'setProperty');
    writer.write(rest);
    expect(write).not.toHaveBeenCalled();
    writer.dispose();
    const before = root.outerHTML;
    writer.write({ ...rest, headYaw: 1, mouthOpen: 0.6 });
    expect(root.outerHTML).toBe(before);
  });
});
