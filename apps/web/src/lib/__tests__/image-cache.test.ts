import { beforeEach, describe, expect, it, vi } from 'vitest';

let cache: typeof import('../image-cache');

beforeEach(async () => {
  vi.resetModules();
  cache = await import('../image-cache');
});

describe('loaded image hints in long conversations', () => {
  it('evicts old hints while retaining recently viewed images', () => {
    const capacity = cache.MAX_LOADED_IMAGES;
    for (let index = 0; index < capacity; index++) cache.markImageLoaded(`/image-${index}`);
    expect(cache.isImageLoaded('/image-0')).toBe(true);
    cache.markImageLoaded('/new-image');
    expect(cache.isImageLoaded('/image-0')).toBe(true);
    expect(cache.isImageLoaded('/image-1')).toBe(false);
    expect(cache.isImageLoaded('/new-image')).toBe(true);
  });

  it('does not evict another image when the same load event is repeated', () => {
    for (let index = 0; index < cache.MAX_LOADED_IMAGES; index++)
      cache.markImageLoaded(`/image-${index}`);
    cache.markImageLoaded('/image-0');
    expect(cache.isImageLoaded('/image-1')).toBe(true);
    expect(cache.isImageLoaded('')).toBe(false);
    cache.markImageLoaded('');
    expect(cache.isImageLoaded('')).toBe(false);
    expect(cache.isImageLoaded('/image-2')).toBe(true);
  });
});
