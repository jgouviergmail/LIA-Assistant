import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useEyesAnchor } from '../useEyesAnchor';

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

function createHeaderScene(gap: number) {
  const navigation = document.createElement('header');
  navigation.className = 'lia-dashboard-header';
  const search = document.createElement('div');
  search.dataset.eyesAnchorStart = '';
  const actions = document.createElement('div');
  actions.dataset.eyesAnchorEnd = '';
  const avatar = document.createElement('div');
  const elements = [navigation, search, actions, avatar];
  document.body.append(...elements);
  vi.spyOn(navigation, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, 1280, 64));
  vi.spyOn(search, 'getBoundingClientRect').mockReturnValue(new DOMRect(300, 90, 100, 44));
  vi.spyOn(actions, 'getBoundingClientRect').mockReturnValue(new DOMRect(400 + gap, 90, 120, 44));
  vi.spyOn(avatar, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, 178.4, 224.4));
  return { ref: { current: avatar }, remove: () => elements.forEach(element => element.remove()) };
}

describe('the largest avatar dock', () => {
  it('reserves the navigation bar and keeps the complete XL shell below it', () => {
    const scene = createHeaderScene(400);
    const { result, unmount } = renderHook(() => useEyesAnchor(scene.ref, true));
    try {
      act(() => vi.advanceTimersByTime(30));
      expect(result.current?.top).toBe(72);
      expect(result.current?.left).toBeGreaterThanOrEqual(408);
      expect((result.current?.left ?? 0) + 178.4).toBeLessThanOrEqual(792);
    } finally {
      unmount();
      scene.remove();
    }
  });

  it('yields to the floating corner when XL cannot fit between the controls', () => {
    const scene = createHeaderScene(100);
    const { result, unmount } = renderHook(() => useEyesAnchor(scene.ref, true));
    try {
      act(() => vi.advanceTimersByTime(30));
      expect(result.current).toBeNull();
    } finally {
      unmount();
      scene.remove();
    }
  });
});
