import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useMarkdownImageLoad } from '../use-markdown-image-load';

const cache = vi.hoisted(() => ({
  isImageLoaded: vi.fn(() => false),
  markImageLoaded: vi.fn(),
}));
vi.mock('@/lib/image-cache', () => cache);

beforeEach(() => vi.clearAllMocks());

describe('URL-bound markdown image loading', () => {
  it('names a failed source and clears its error for a different image', () => {
    const { result, rerender } = renderHook(
      ({ src }) => useMarkdownImageLoad(src, undefined, false),
      { initialProps: { src: '/failed.png' } }
    );
    act(() => result.current.onError());
    expect(result.current.failed).toBe(true);
    rerender({ src: '/next.png' });
    expect(result.current.failed).toBe(false);
  });
  it('does not inherit the loaded state of a replaced image', () => {
    const { result, rerender } = renderHook(
      ({ src }) => useMarkdownImageLoad(src, undefined, false),
      { initialProps: { src: '/first.png' } }
    );
    act(() => result.current.onLoad());
    expect(result.current.loaded).toBe(true);
    rerender({ src: '/replacement.png' });
    expect(result.current.loaded).toBe(false);
    act(() => result.current.onLoad());
    expect(cache.markImageLoaded).toHaveBeenLastCalledWith('/replacement.png');
    expect(result.current.loaded).toBe(true);
  });

  it('leaves a lazy DOM image to the browser without starting a preload', () => {
    const image = vi.fn();
    vi.stubGlobal('Image', image);
    try {
      renderHook(() => useMarkdownImageLoad('/hidden-avatar.png', 'use-credentials', false));
      expect(image).not.toHaveBeenCalled();
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
