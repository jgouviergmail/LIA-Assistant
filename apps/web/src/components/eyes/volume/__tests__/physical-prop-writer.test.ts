import { describe, expect, it, vi } from 'vitest';
import { createPhysicalPropWriter } from '../physical-prop-writer';
import { restChannelValues } from '../../rig/channels';
import { projectVolumeSurface, volumePose, volumeProfile } from '../volume-geometry';
import { projectSmileySurface, spherePose } from '../../smiley/sphere-geometry';
function host(style = 'billes', character = 'boulon') {
  const root = document.createElement('span');
  root.dataset.style = style;
  root.dataset.volumeCharacter = character;
  root.dataset.volumeVariant = 'female';
  root.dataset.volumeReady = 'true';
  root.style.setProperty('--eye-w', '.425em');
  root.style.setProperty('--eye-gap', '.06em');
  root.style.setProperty('--avatar-crown-y', '-1.203%');
  root.style.setProperty('--avatar-face-y', '43%');
  root.style.setProperty('--avatar-accessory-scale', '.9');
  document.body.append(root);
  return root;
}
const tokens = [
  '--volume-crown-transform',
  '--volume-tear-transform',
  '--volume-sweat-transform',
  '--volume-heat-transform',
];
function translated(root: HTMLElement, token: string) {
  return root.style
    .getPropertyValue(token)
    .match(/^translate\(([-\d.]+)em, ([-\d.]+)em\)/)!
    .slice(1)
    .map(Number);
}
describe('wearable and facial props share the native anatomical projection', () => {
  it.each(['male', 'female'])(
    'keeps Oscar %s facial props anchored beside the fixed sockets',
    variant => {
      const root = host('billes', 'oscar');
      root.dataset.volumeVariant = variant;
      root.style.setProperty('--eye-w', '.385em');
      root.style.setProperty('--eye-gap', '.075em');
      root.style.setProperty('--avatar-face-y', variant === 'female' ? '35.4%' : '33.6%');
      const writer = createPhysicalPropWriter(root);
      for (const direction of [-1.3, 1.3]) {
        const pose = { ...restChannelValues(), headYaw: direction, headPitch: -direction };
        writer.write(pose);
        const registered = tokens.map(token => root.style.getPropertyValue(token));
        writer.write({
          ...pose,
          gazeX: -direction,
          gazeY: direction,
          txL: direction,
          txR: -direction,
          tyL: -direction,
          tyR: direction,
        });
        expect(tokens.map(token => root.style.getPropertyValue(token))).toEqual(registered);
      }
      writer.dispose();
      root.remove();
    }
  );

  it('has exact neutral transforms, moves the crown with the head, and facial props with gaze/eye travel', () => {
    const root = host(),
      writer = createPhysicalPropWriter(root),
      rest = restChannelValues();
    writer.write(rest);
    for (const token of tokens)
      expect(root.style.getPropertyValue(token)).toBe(
        'translate(0em, 0em) matrix(1, 0, 0, 1, 0, 0)'
      );
    writer.write({ ...rest, headYaw: 1, headPitch: -0.7 });
    const crown = root.style.getPropertyValue(tokens[0]),
      tear = root.style.getPropertyValue(tokens[1]);
    expect(crown).not.toBe('translate(0em, 0em) matrix(1, 0, 0, 1, 0, 0)');
    writer.write({ ...rest, headYaw: 1, headPitch: -0.7, gazeX: 1, txL: 0.06, tyR: 0.08 });
    expect(root.style.getPropertyValue(tokens[0])).toBe(crown);
    expect(root.style.getPropertyValue(tokens[1])).not.toBe(tear);
    const queries = vi.spyOn(root, 'querySelectorAll');
    writer.write(rest);
    expect(queries).not.toHaveBeenCalled();
    writer.dispose();
    for (const token of tokens) expect(root.style.getPropertyValue(token)).toBe('');
  });
  it('clears on fallback and reacquires static geometry after style/gender changes without a clock', () => {
    const root = host(),
      writer = createPhysicalPropWriter(root),
      raf = vi.spyOn(window, 'requestAnimationFrame');
    writer.write({ ...restChannelValues(), headYaw: 1 });
    root.dataset.volumeReady = 'false';
    writer.write(restChannelValues());
    for (const token of tokens) expect(root.style.getPropertyValue(token)).toBe('');
    root.dataset.style = 'smiley';
    root.dataset.smileyVariant = 'female';
    delete root.dataset.volumeCharacter;
    writer.write(restChannelValues());
    expect(root.style.getPropertyValue(tokens[0])).toContain('matrix(1, 0, 0, 1');
    writer.write({ ...restChannelValues(), headYaw: 1 });
    expect(root.style.getPropertyValue(tokens[0])).not.toContain('matrix(1, 0, 0, 1');
    writer.reset();
    for (const token of tokens) expect(root.style.getPropertyValue(token)).toBe('');
    expect(raf).not.toHaveBeenCalled();
    writer.dispose();
    raf.mockRestore();
  });
  it('reads monitor scaled eye geometry while its rigid screen and props turn together', () => {
    const root = host('cozmo', 'monitor');
    root.style.setProperty('--monitor-face-scale', '.42');
    const writer = createPhysicalPropWriter(root);
    writer.write({ ...restChannelValues(), headYaw: 1 });
    expect(root.style.getPropertyValue(tokens[1])).toContain('matrix');
    root.dataset.volumeReady = 'false';
    writer.write(restChannelValues());
    expect(root.style.getPropertyValue(tokens[1])).toBe('');
    writer.dispose();
  });
  it('attaches the freezing laurel to its actual CSS centre, including the lower face-relative limit', () => {
    const root = host('billes', 'oscar');
    root.style.setProperty('--avatar-crown-y', '15%');
    root.style.setProperty('--avatar-face-y', '35.4%');
    const writer = createPhysicalPropWriter(root),
      values = { ...restChannelValues(), headYaw: 0.8, headPitch: -0.6 },
      profile = volumeProfile('oscar', 'female');
    // The laurel is 1.6em high; its top is the lower of its crown and face limits.
    const y =
      Math.min((0.15 - 0.5) * 2.6 - 0.24 * 0.9, (0.354 - 0.5) * 2.6 - 1.25 * 0.9) + 0.8 * 0.9;
    const expected = projectVolumeSurface(profile, { x: 0, y }, volumePose(values, 'oscar'));
    writer.write(values);
    const [x, dy] = translated(root, tokens[0]);
    expect(x).toBeCloseTo(expected.x, 4);
    expect(dy).toBeCloseTo(expected.y - y, 4);
    writer.dispose();
  });
  it('projects the Smiley freezing laurel on the sphere independently of the tied ribbon and follows the heat bead with its right eye', () => {
    const root = host('smiley');
    delete root.dataset.volumeCharacter;
    root.style.setProperty('--avatar-crown-y', '1%');
    root.style.setProperty('--avatar-face-y', '47%');
    const writer = createPhysicalPropWriter(root),
      values = { ...restChannelValues(), headYaw: 1, headPitch: -0.5 },
      y = Math.min((0.01 - 0.5) * 2.6 - 0.24 * 0.9, (0.47 - 0.5) * 2.6 - 1.25 * 0.9) + 0.8 * 0.9;
    const expected = projectSmileySurface({ x: 0, y }, spherePose(values)),
      rest = projectSmileySurface({ x: 0, y }, spherePose(restChannelValues()));
    writer.write(values);
    const [x, dy] = translated(root, tokens[0]);
    expect(x).toBeCloseTo(expected.x - rest.x, 4);
    expect(dy).toBeCloseTo(expected.y - rest.y, 4);
    const heat = root.style.getPropertyValue(tokens[3]);
    writer.write({ ...values, gazeX: 0.8, txR: 0.07 });
    expect(root.style.getPropertyValue(tokens[3])).not.toBe(heat);
    writer.dispose();
  });
});
