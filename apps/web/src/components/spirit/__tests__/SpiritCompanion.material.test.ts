import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const css = readFileSync(join(process.cwd(), 'src/styles/eyes.css'), 'utf8');
function material(selector: string) {
  const block = css.slice(css.indexOf(`${selector} {`));
  return block.slice(0, block.indexOf('\n}'));
}

describe('Spirit original sculpt material', () => {
  it('keeps the human sockets rigid even during saccade stretch while allowing native iris travel', () => {
    const oscar = ".lia-spirit-companion[data-character='oscar']";
    const frame = material(`${oscar} .lia-spirit-rig`);
    expect(frame).toContain('--spirit-face-x: 0em');
    expect(frame).toContain('--spirit-face-y: 0em');
    const pair = material(`${oscar} .lia-eyes-gaze`);
    expect(pair).toContain('transform: translate3d(0, 0, var(--face-eye-depth))');
    expect(pair).not.toContain('--rig-stretch');
    expect(material(`${oscar} .lia-eye-shape`)).toContain('transform: none');
    expect(material(`${oscar} .lia-eye-pupil`)).toContain('--rig-gaze-x');
  });

  it('keeps eye and mouth travel coherent inside the single rotating head', () => {
    const frame = material('.lia-spirit-companion .lia-spirit-rig');
    expect(frame).toContain('--spirit-face-x: calc(var(--rig-gaze-x, 0) * 0.03em)');
    expect(frame).toContain('--spirit-face-y: calc(var(--rig-gaze-y, 0) * 0.02em)');
    for (const selector of [
      '.lia-spirit-companion .lia-eyes-gaze',
      '.lia-spirit-companion .lia-mouth',
    ]) {
      const organ = material(selector);
      expect(organ).toContain('var(--spirit-face-x)');
      expect(organ).toContain('var(--spirit-face-y)');
      // Head rotation already moves both organs and the body. Re-reading
      // yaw/pitch as a separate translation made the jaw slide off the face.
      expect(organ).not.toContain('var(--rig-head-yaw');
      expect(organ).not.toContain('var(--rig-head-pitch');
    }
    expect(material('.lia-spirit-companion .lia-mouth')).toContain('var(--face-mouth-depth)');
    expect(material('.lia-spirit-companion .lia-eye-pupil')).toContain('--rig-gaze-x');
  });

  it('shades the sculpt subtly from the existing head channels without recoloring its eyes', () => {
    const body = material('.lia-spirit-companion .lia-head::before');
    expect(body).toContain('brightness(');
    expect(body).toContain('clamp(0.96,');
    expect(body).toContain('var(--rig-head-yaw, 0)');
    expect(body).toContain('drop-shadow(');
    expect(material('.lia-spirit-companion .lia-eye-shape')).not.toContain('brightness(');
  });

  it('keeps all moving graphical organs inside the enlarged stationary body alpha', () => {
    expect(material('.lia-spirit-companion .lia-head::before')).toContain('scale: 1.13');
    const face = material('.lia-spirit-companion .lia-raster-face-mask');
    expect(face).toContain('mask-image: var(--spirit-body-url)');
    expect(face).toContain('mask-size: 113% 113%');
    expect(face).toContain('mask-position: center');
    expect(face).not.toContain('translate:');
    expect(material('.lia-spirit-companion .lia-eye')).toContain(
      'clamp(-0.08em, var(--tx), 0.08em)'
    );
  });
  it('contains moving pupils in the same original alpha silhouette as the sclera', () => {
    const eye = material('.lia-spirit-companion .lia-eye-shape');
    expect(eye).toContain('background: var(--spirit-eye-url)');
    expect(eye).toContain('mask-image: var(--spirit-eye-url)');
    expect(eye).toContain('mask-size: 100% 100%');
    expect(eye).toContain('mask-mode: alpha');
    const right = material('.lia-spirit-companion .lia-eye--right .lia-eye-shape');
    expect(right).toContain('background-image: var(--spirit-eye-right-url)');
    expect(right).toContain('mask-image: var(--spirit-eye-right-url)');
    const pupilMask = material('.lia-spirit-companion .lia-eye-pupil-clip');
    expect(pupilMask).toContain('mask-image: var(--spirit-sclera-url)');
    expect(pupilMask).toContain('position: absolute');
    expect(pupilMask).not.toContain('translate:');
    expect(pupilMask).not.toContain('scale:');
  });

  it('covers intact organ textures instead of vertically crushing their iris/glints', () => {
    const eye = material('.lia-spirit-companion .lia-eye-shape');
    expect(eye).toContain('var(--spirit-squint)');
    expect(eye).toContain('transform: scaleX(var(--sx)) rotate(var(--rot))');
    expect(eye).not.toContain('scaleY');
    const blink = material('.lia-spirit-companion .lia-eye-blink');
    expect(blink).toContain('transform: none');
    expect(blink).toContain('var(--blink-close)');
    expect(material('.lia-spirit-companion .lia-eye-pupil')).toContain(
      'scaleX(calc(1 / var(--sx)))'
    );
  });
});
