import { canvasContext } from '@/__tests__/fixtures/canvas-context';
import { afterEach, expect, it, vi } from 'vitest';
import { paintPerson } from '../art/person';
import { ActorMesh } from '../art/actor-mesh';
import { AVATAR_PRESETS } from '../avatar-presets';
import { compilePoseSlots } from '../pose-slots';
import { WORLD } from '../definition';
import {
  AVATAR_HAIR,
  AVATAR_OUTFITS,
  AVATAR_HEADWEAR,
  DEFAULT_AVATAR,
  type AvatarAppearance,
} from '../avatar-catalogue';

afterEach(() => vi.restoreAllMocks());
it('renders every authored preset in eight directions, standing, seated and lying within the existing sprite budget', () => {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(canvasContext({}));
  const slots = compilePoseSlots(WORLD);
  const seated = slots.find(slot => slot.kind === 'sit');
  const lying = slots.find(slot => slot.kind === 'lie');
  if (!seated || !lying) throw new Error('Missing authored posture');
  for (const preset of AVATAR_PRESETS)
    for (let heading = 0; heading < 8; heading++)
      for (const pose of [null, seated, lying]) {
        const sprite = paintPerson(1, 0, 1.5, 'sage', heading, pose, preset.appearance);
        expect(
          [sprite.width, sprite.height, sprite.anchorX, sprite.anchorY].every(Number.isFinite)
        ).toBe(true);
        expect(sprite.canvas.width * sprite.canvas.height * 4).toBeLessThan(1024 * 1024);
        expect(sprite.canvas.width).toBeGreaterThan(0);
        expect(sprite.canvas.height).toBeGreaterThan(0);
        sprite.canvas.width = sprite.canvas.height = 0;
      }
});
it('gives each hairstyle, outfit and headwear a distinct authored silhouette', () => {
  const context = canvasContext({});
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(context);
  const boxes = vi.spyOn(ActorMesh.prototype, 'box');
  const details = vi.spyOn(ActorMesh.prototype, 'front');
  const signature = (appearance: AvatarAppearance) => {
    boxes.mockClear();
    details.mockClear();
    const sprite = paintPerson(1, 0, 1.5, 'sage', 2, null, appearance);
    expect(sprite.canvas.width * sprite.canvas.height * 4).toBeLessThan(1024 * 1024);
    const result = JSON.stringify([boxes.mock.calls, details.mock.calls]);
    sprite.canvas.width = sprite.canvas.height = 0;
    return result;
  };
  for (const variations of [
    AVATAR_HAIR.map(hair => ({ ...DEFAULT_AVATAR, hair })),
    AVATAR_OUTFITS.map(outfit => ({ ...DEFAULT_AVATAR, outfit })),
    AVATAR_HEADWEAR.map(headwear => ({ ...DEFAULT_AVATAR, headwear })),
  ])
    expect(new Set(variations.map(signature)).size).toBe(variations.length);
  expect(signature({ ...DEFAULT_AVATAR, glasses: true })).not.toBe(signature(DEFAULT_AVATAR));
});
