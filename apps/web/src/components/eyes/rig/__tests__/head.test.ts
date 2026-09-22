import { describe, expect, it } from 'vitest';
import { createEyeRig } from '../runtime';
import { EYE_STYLE_IDS } from '../../eye-styles';

describe('a gaze carried by a head with weight', () => {
  it.each(EYE_STYLE_IDS)('%s lets the eyes lead, then the head follow without a snap', styleId => {
    const rig = createEyeRig({ initial: { expression: 'neutral', styleId, family: 'calm' } });
    rig.setGaze({ x: 1, y: -0.8 });
    for (let i = 0; i < 5; i++) rig.step(16);
    const first = { ...rig.values() };
    expect(first.gazeX).toBeGreaterThan(first.headYaw * 2);
    expect(first.headYaw).toBeGreaterThan(0);
    for (let i = 0; i < 180; i++) rig.step(16);
    expect(rig.values().headYaw).toBeCloseTo(1, 2);
    expect(rig.values().headPitch).toBeCloseTo(-0.8, 2);
    const before = { ...rig.values() };
    rig.setGaze({ x: -1, y: 1 });
    expect(rig.values().headYaw).toBe(before.headYaw);
    rig.step(16);
    expect(Math.abs(rig.values().headYaw - before.headYaw)).toBeLessThan(0.03);
  });

  it('follows an internally authored thought, not only pointer props', () => {
    const rig = createEyeRig({
      initial: { expression: 'thinking', styleId: 'smiley', family: 'calm' },
    });
    let movement = 0;
    for (let i = 0; i < 400; i++) {
      rig.step(16);
      movement = Math.max(movement, Math.abs(rig.values().headYaw));
      expect(rig.values().mouthOpen).toBe(0);
    }
    expect(movement).toBeGreaterThan(0.1);
  });

  it('remains bounded through rapid reversals and settles without perpetual work', () => {
    const rig = createEyeRig();
    for (let i = 0; i < 600; i++) {
      if (i % 17 === 0) rig.setGaze({ x: i % 2 ? 1 : -1, y: i % 3 ? 1 : -1 });
      rig.step(16);
      expect(Math.abs(rig.values().headYaw)).toBeLessThanOrEqual(1.02);
      expect(Math.abs(rig.values().headPitch)).toBeLessThanOrEqual(1.02);
    }
    rig.setGaze(null);
    for (let i = 0; i < 400; i++) rig.step(16);
    expect(rig.values().headYaw).toBe(0);
    expect(rig.values().headPitch).toBe(0);
    expect(rig.isSettling()).toBe(false);
  });
});
