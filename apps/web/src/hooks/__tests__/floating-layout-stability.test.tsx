import { act, render, screen } from '@testing-library/react';
import { useRef } from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { useFloatingDrag } from '@/hooks/useFloatingDrag';

const saved = { xPct: 20, yPct: 90 };
function Surface({ kind = 'div' }: { kind?: 'div' | 'nav' }) {
  const ref = useRef<HTMLDivElement>(null);
  const drag = useFloatingDrag(ref, saved, vi.fn());
  const style = drag.displayPos ? { left: drag.displayPos.x, top: drag.displayPos.y } : undefined;
  return kind === 'div' ? (
    <div ref={ref} data-testid="surface" style={style} />
  ) : (
    <nav ref={ref} data-testid="surface" style={style} />
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

it('remeasures a replaced surface without reading layout on subsequent unchanged renders', () => {
  vi.stubGlobal('innerHeight', 320);
  vi.stubGlobal('visualViewport', undefined);
  const measure = vi
    .spyOn(HTMLElement.prototype, 'getBoundingClientRect')
    .mockImplementation(function (this: HTMLElement) {
      return new DOMRect(0, 0, 100, this.tagName === 'NAV' ? 300 : 100);
    });
  const { rerender } = render(<Surface />);
  expect(screen.getByTestId('surface').style.top).toBe('220px');
  rerender(<Surface kind="nav" />);
  expect(screen.getByTestId('surface').style.top).toBe('20px');
  const count = measure.mock.calls.length;
  rerender(<Surface kind="nav" />);
  expect(measure).toHaveBeenCalledTimes(count);
});

it('updates from widget resizing and stops observing the detached surface', () => {
  vi.stubGlobal('innerHeight', 320);
  vi.stubGlobal('visualViewport', undefined);
  const observers: RecordingObserver[] = [];
  class RecordingObserver implements ResizeObserver {
    readonly observe = vi.fn();
    readonly unobserve = vi.fn();
    readonly disconnect = vi.fn();
    readonly update: () => void;
    constructor(callback: ResizeObserverCallback) {
      this.update = () => callback([], this);
      observers.push(this);
    }
  }
  vi.stubGlobal('ResizeObserver', RecordingObserver);
  let height = 100;
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(
    () => new DOMRect(0, 0, 100, height)
  );
  const { unmount } = render(<Surface />);
  const observer = observers[0];
  expect(observer.observe).toHaveBeenCalledWith(screen.getByTestId('surface'));
  act(() => {
    height = 200;
    observer.update();
  });
  expect(screen.getByTestId('surface').style.top).toBe('120px');
  unmount();
  expect(observer.disconnect).toHaveBeenCalled();
  expect(() => observer.update()).not.toThrow();
});

it('does not reread moving layout during React renders while the keyboard changes the viewport', () => {
  vi.stubGlobal('innerHeight', 320);
  vi.stubGlobal('innerWidth', 390);
  const viewport = Object.assign(new EventTarget(), {
    width: 390,
    height: 320,
    offsetLeft: 0,
    offsetTop: 0,
  });
  vi.stubGlobal('visualViewport', viewport);
  let reads = 0;
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(() => {
    // Layout can settle between reads as a keyboard, media or animation changes it.
    const height = 100 + ++reads / 1000;
    return new DOMRect(0, 0, 100, height);
  });
  const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
  expect(() => render(<Surface />)).not.toThrow();
  expect(screen.getByTestId('surface').style.top).not.toBe('');
  act(() => {
    viewport.offsetTop = 350;
    viewport.dispatchEvent(new Event('resize'));
  });
  expect(screen.getByTestId('surface').style.top).toBe('350px');
  expect(consoleError).not.toHaveBeenCalled();
  expect(reads).toBeLessThan(8);
});
