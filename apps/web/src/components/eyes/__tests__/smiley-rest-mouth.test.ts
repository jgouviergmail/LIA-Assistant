import { describe, expect, it } from 'vitest';
import { smileyMouthWidth } from '../smiley/rest-mouth';
import { resolvePose } from '../rig/poses';

describe('Smiley resting mouth width preserves native acting amplitude', () => {
  it('narrows the closed neutral mouth on both portraits without changing the native channels', () => {
    const pose = resolvePose('neutral', 'smiley');
    expect(smileyMouthWidth(pose) * 1.45).toBeCloseTo(0.84);
    expect(pose.mouthW).toBe(0.72);
  });
  it('preserves the exact approved grin, open speech and the quiet interval between words', () => {
    const joy = resolvePose('joy', 'smiley');
    expect(smileyMouthWidth(joy)).toBe(joy.mouthW);
    const speech = { ...resolvePose('speaking', 'smiley'), mouthOpen: 0.62 };
    expect(smileyMouthWidth(speech)).toBe(speech.mouthW);
    expect(smileyMouthWidth({ ...speech, mouthOpen: 0 })).toBe(speech.mouthW);
    expect(smileyMouthWidth({ ...speech, mouthOpen: 0.2 })).toBe(speech.mouthW);
  });
  it('releases continuously with opening or a broader smile, preserving negative expressive contours', () => {
    const pose = resolvePose('neutral', 'smiley');
    const widths = Array.from({ length: 161 }, (_, index) =>
      smileyMouthWidth({ ...pose, mouthOpen: index / 1000 })
    );
    expect(widths.at(-1)).toBe(pose.mouthW);
    widths.slice(1).forEach((width, index) => {
      expect(width).toBeGreaterThanOrEqual(widths[index]);
      expect(width - widths[index]).toBeLessThan(0.003);
    });
    const sad = resolvePose('sad', 'smiley');
    expect(smileyMouthWidth(sad)).toBe(sad.mouthW);
  });
});
