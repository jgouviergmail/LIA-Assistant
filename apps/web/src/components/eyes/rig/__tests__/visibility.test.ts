import { expect, it, vi } from 'vitest';
import { observeRigVisibility } from '../visibility';

it('suspends offscreen faces and combines viewport and document visibility', () => {
  const instances: IntersectionObserver[] = [];
  const callbacks: IntersectionObserverCallback[] = [];
  const NativeStub = IntersectionObserver;
  const disconnect = vi.fn();
  vi.stubGlobal(
    'IntersectionObserver',
    class extends NativeStub {
      constructor(callback: IntersectionObserverCallback) {
        super(callback);
        instances.push(this);
        callbacks.push(callback);
      }
      disconnect() {
        disconnect();
      }
    }
  );
  const element = document.createElement('span');
  const changes: boolean[] = [];
  const stop = observeRigVisibility(element, value => changes.push(value));
  const bounds = new DOMRectReadOnly(0, 0, 20, 20);
  const intersect = (visible: boolean) =>
    callbacks[0](
      [
        {
          target: element,
          boundingClientRect: bounds,
          intersectionRect: bounds,
          rootBounds: bounds,
          time: 0,
          intersectionRatio: visible ? 1 : 0,
          isIntersecting: visible,
        },
      ],
      instances[0]
    );
  try {
    intersect(false);
    expect(changes.at(-1)).toBe(false);
    const hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(true);
    intersect(true);
    expect(changes.at(-1)).toBe(false);
    hidden.mockReturnValue(false);
    document.dispatchEvent(new Event('visibilitychange'));
    expect(changes.at(-1)).toBe(true);
    stop();
    expect(disconnect).toHaveBeenCalledOnce();
    const count = changes.length;
    document.dispatchEvent(new Event('visibilitychange'));
    expect(changes).toHaveLength(count);
  } finally {
    stop();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  }
});

it('retains document suspension where intersection observation is unavailable', () => {
  vi.stubGlobal('IntersectionObserver', undefined);
  const changes: boolean[] = [];
  const stop = observeRigVisibility(document.createElement('span'), value => changes.push(value));
  try {
    document.dispatchEvent(new Event('visibilitychange'));
    expect(changes.at(-1)).toBe(true);
  } finally {
    stop();
    vi.unstubAllGlobals();
  }
});
