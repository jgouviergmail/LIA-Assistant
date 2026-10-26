import { afterEach, describe, expect, it, vi } from 'vitest';
import { LiaAtlas } from '../art/lia-atlas';

afterEach(() => vi.unstubAllGlobals());

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
