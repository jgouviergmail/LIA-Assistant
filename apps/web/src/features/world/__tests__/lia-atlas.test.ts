import { afterEach, describe, expect, it, vi } from 'vitest';
import { LiaAtlas } from '../art/lia-atlas';
import * as rigRuntime from '@/components/eyes/rig/runtime';
import { NEUTRAL_WORLD_ACTING } from '../world-acting';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function asset(width = 800) {
  const image = new Image();
  Object.defineProperties(image, {
    naturalWidth: { value: width },
    naturalHeight: { value: 952 },
  });
  vi.stubGlobal('Image', function () {
    return image;
  });
  return image;
}

describe('LIA directional asset lifetime', () => {
  it('consumes an offscreen completion without deferring its body beat until reentry', () => {
    asset();
    const rig = rigRuntime.createEyeRig({ characterId: 'bip', allowSleep: false });
    const play = vi.spyOn(rig, 'play');
    vi.spyOn(rigRuntime, 'createEyeRig').mockReturnValue(rig);
    const atlas = new LiaAtlas();
    const frame = {
      ...NEUTRAL_WORLD_ACTING,
      state: 'success' as const,
      eventKey: 'offscreen',
      accentAlive: true,
    };
    atlas.setVisible(false);
    atlas.setActing(frame);
    atlas.setVisible(true);
    atlas.setActing(frame);
    expect(play).not.toHaveBeenCalled();
    atlas.destroy();
  });
  it('cancels an unfinished body accent on culling and on expiry after tab suspension', () => {
    asset();
    const rig = rigRuntime.createEyeRig({ characterId: 'bip', allowSleep: false });
    const settle = vi.spyOn(rig, 'settle');
    vi.spyOn(rigRuntime, 'createEyeRig').mockReturnValue(rig);
    const atlas = new LiaAtlas();
    const frame = {
      ...NEUTRAL_WORLD_ACTING,
      state: 'success' as const,
      eventKey: 'visible',
      accentAlive: true,
    };
    atlas.setActing(frame);
    for (let step = 0; step < 20; step++) rig.step(16);
    const peak = Math.abs(rig.values().bodyY);
    expect(peak).toBeGreaterThan(0.001);
    atlas.setVisible(false);
    expect(Math.abs(rig.values().bodyY)).toBeLessThan(peak / 2);
    expect(settle).toHaveBeenCalledOnce();
    atlas.setVisible(true);
    atlas.setActing({ ...frame, eventKey: 'next' });
    atlas.setActing({ ...frame, eventKey: null, accentAlive: false });
    expect(settle).toHaveBeenCalledTimes(2);
    atlas.destroy();
  });
  it('uses the real native rig and changes its pose only when expression inputs change', () => {
    asset();
    const rig = rigRuntime.createEyeRig({ characterId: 'bip', allowSleep: false });
    const setPose = vi.spyOn(rig, 'setPose');
    const play = vi.spyOn(rig, 'play');
    vi.spyOn(rigRuntime, 'createEyeRig').mockReturnValue(rig);
    const atlas = new LiaAtlas();
    const thinking = {
      ...NEUTRAL_WORLD_ACTING,
      pose: { ...NEUTRAL_WORLD_ACTING.pose, expression: 'thinking' as const },
    };
    atlas.setActing(thinking);
    atlas.setActing({ ...thinking, context: { ...thinking.context } });
    expect(setPose).toHaveBeenCalledTimes(1);
    atlas.setActing({ ...thinking, pose: { ...thinking.pose, expression: 'speaking' } });
    expect(setPose).toHaveBeenCalledTimes(2);
    atlas.setActing({
      ...NEUTRAL_WORLD_ACTING,
      eventKey: 'confirmed-once',
      state: 'success',
      accentAlive: true,
    });
    atlas.setActing({
      ...NEUTRAL_WORLD_ACTING,
      eventKey: 'confirmed-once',
      state: 'success',
      accentAlive: true,
    });
    expect(play).toHaveBeenCalledTimes(1);
    atlas.destroy();
    atlas.setActing(thinking);
    expect(setPose).toHaveBeenCalledTimes(3);
  });
  it('accounts for the decoded image, releases it and ignores a late load', () => {
    const image = asset();
    const atlas = new LiaAtlas();
    const loaded = image.onload;
    image.dispatchEvent(new Event('load'));
    expect(atlas.textureBytes).toBe(800 * 952 * 4);
    atlas.destroy();
    expect(atlas.textureBytes).toBe(0);
    expect(image.onload).toBeNull();
    expect(image.onerror).toBeNull();
    loaded?.call(image, new Event('load'));
    expect(atlas.textureBytes).toBe(0);
    atlas.destroy();
  });
  it('keeps the deterministic fallback on malformed or failed artwork', () => {
    const image = asset(640);
    const atlas = new LiaAtlas();
    image.dispatchEvent(new Event('load'));
    expect(atlas.textureBytes).toBe(0);
    image.dispatchEvent(new Event('error'));
    expect(atlas.textureBytes).toBe(0);
    atlas.destroy();
  });
});
