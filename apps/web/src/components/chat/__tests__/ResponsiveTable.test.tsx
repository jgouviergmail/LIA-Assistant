/**
 * ResponsiveTable — the frame states how its table is drawn (B2).
 *
 * jsdom performs no layout, so the geometry is injected: the scroll box
 * reports the widths a real engine measured (a 341 px phone bubble, a 908 px
 * table). The layout is decided BEFORE the first paint, by the layout effect,
 * so the frame already carries its verdict when `render` returns.
 */
import { render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ResponsiveTable } from '../ResponsiveTable';

interface Geometry {
  clientWidth: number;
  scrollWidth: number;
}

let geometry: Geometry = { clientWidth: 0, scrollWidth: 0 };
const originals = {
  clientWidth: Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'clientWidth'),
  scrollWidth: Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'scrollWidth'),
};

function isScrollBox(element: HTMLElement): boolean {
  return element.classList.contains('table-wrapper');
}

beforeEach(() => {
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
    configurable: true,
    get(this: HTMLElement) {
      return isScrollBox(this) ? geometry.clientWidth : 0;
    },
  });
  Object.defineProperty(HTMLElement.prototype, 'scrollWidth', {
    configurable: true,
    get(this: HTMLElement) {
      return isScrollBox(this) ? geometry.scrollWidth : 0;
    },
  });
});

afterEach(() => {
  for (const [key, descriptor] of Object.entries(originals)) {
    if (descriptor) Object.defineProperty(HTMLElement.prototype, key, descriptor);
  }
  vi.restoreAllMocks();
});

function renderTable() {
  return render(
    <ResponsiveTable>
      <tbody>
        <tr>
          <td data-label="Restaurant">Chez Marcel</td>
        </tr>
      </tbody>
    </ResponsiveTable>
  );
}

function frameOf(container: HTMLElement): HTMLElement {
  const frame = container.querySelector<HTMLElement>('.table-frame');
  if (!frame) throw new Error('no table frame');
  return frame;
}

describe('ResponsiveTable', () => {
  it('stacks a table that overflows a phone-width bubble, before the first paint', () => {
    geometry = { clientWidth: 341, scrollWidth: 908 };
    const { container } = renderTable();
    const frame = frameOf(container);
    expect(frame.getAttribute('data-stacked')).toBe('true');
    expect(frame.getAttribute('data-overflowing')).toBe('false');
  });

  it('keeps a wide container scrolling, and says there is more to the right', () => {
    geometry = { clientWidth: 942, scrollWidth: 1400 };
    const frame = frameOf(renderTable().container);
    expect(frame.getAttribute('data-stacked')).toBe('false');
    expect(frame.getAttribute('data-overflowing')).toBe('true');
    expect(frame.getAttribute('data-scrolled-end')).toBe('false');
  });

  it('draws a table that fits as a plain table', () => {
    geometry = { clientWidth: 341, scrollWidth: 341 };
    const frame = frameOf(renderTable().container);
    expect(frame.getAttribute('data-stacked')).toBe('false');
    expect(frame.getAttribute('data-overflowing')).toBe('false');
  });

  it('re-decides after a resize (a phone turned to landscape unstacks it)', () => {
    const observers: RecordingObserver[] = [];
    class RecordingObserver implements ResizeObserver {
      readonly callback: ResizeObserverCallback;
      constructor(callback: ResizeObserverCallback) {
        this.callback = callback;
        observers.push(this);
      }
      observe(): void {}
      unobserve(): void {}
      disconnect(): void {}
    }
    vi.stubGlobal('ResizeObserver', RecordingObserver);
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation(callback => {
      callback(0);
      return 1;
    });

    geometry = { clientWidth: 341, scrollWidth: 908 };
    const frame = frameOf(renderTable().container);
    expect(frame.getAttribute('data-stacked')).toBe('true');

    geometry = { clientWidth: 780, scrollWidth: 908 };
    observers[0].callback([], observers[0]);
    expect(frame.getAttribute('data-stacked')).toBe('false');
    vi.unstubAllGlobals();
  });

  it('stops observing when the table leaves the page', () => {
    const disconnect = vi.fn();
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe(): void {}
        unobserve(): void {}
        disconnect = disconnect;
      }
    );
    geometry = { clientWidth: 341, scrollWidth: 341 };
    renderTable().unmount();
    expect(disconnect).toHaveBeenCalledTimes(1);
    vi.unstubAllGlobals();
  });
});
