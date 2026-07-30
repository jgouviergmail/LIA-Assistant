/**
 * PinnedScene: sticky stage + scroll-driven progress on desktop; plain flow on
 * mobile, under reduced motion, or when disabled.
 */

import { render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { PinnedScene } from '../PinnedScene';

function stubSyncRaf() {
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
    cb(0);
    return 0;
  });
}

function stubMatchMedia({ mobile, reduced }: { mobile: boolean; reduced: boolean }) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockImplementation((query: string) => ({
      matches: query.includes('max-width') ? mobile : reduced,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      onchange: null,
      dispatchEvent: vi.fn(),
    }))
  );
}

/** Mock the pin wrapper geometry: 3.2 viewport-heights tall, scrolled `topPx`. */
function mockPinGeometry(topPx: number) {
  const totalHeight = window.innerHeight * 3.2;
  vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(totalHeight);
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
    top: topPx,
    height: totalHeight,
    bottom: topPx + totalHeight,
    left: 0,
    right: 1024,
    width: 1024,
    x: 0,
    y: topPx,
    toJSON: () => ({}),
  } as DOMRect);
}

describe('PinnedScene', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('renders the sticky stage on desktop and drives --p from scroll', () => {
    stubSyncRaf();
    stubMatchMedia({ mobile: false, reduced: false });
    const onProgress = vi.fn();
    // Halfway: -top = 0.5 × (offsetHeight − viewportH).
    const halfway = -(window.innerHeight * 3.2 - window.innerHeight) / 2;
    mockPinGeometry(halfway);

    const { container } = render(
      <PinnedScene heights={3.2} onProgress={onProgress}>
        <p>stage</p>
      </PinnedScene>
    );
    const pin = container.firstChild as HTMLElement;
    expect(pin.querySelector('.cosmos-pin-stage')).toBeInTheDocument();
    expect(pin.style.height).toBe('320dvh');

    window.dispatchEvent(new Event('scroll'));
    expect(parseFloat(pin.style.getPropertyValue('--p'))).toBeCloseTo(0.5, 2);
    expect(onProgress).toHaveBeenLastCalledWith(expect.closeTo(0.5, 2));
  });

  it('clamps progress to [0, 1]', () => {
    stubSyncRaf();
    stubMatchMedia({ mobile: false, reduced: false });
    mockPinGeometry(50000);
    const { container } = render(
      <PinnedScene>
        <p>stage</p>
      </PinnedScene>
    );
    window.dispatchEvent(new Event('scroll'));
    const pin = container.firstChild as HTMLElement;
    expect(parseFloat(pin.style.getPropertyValue('--p'))).toBe(0);
  });

  it.each([
    ['mobile viewport', { mobile: true, reduced: false }],
    ['reduced motion', { mobile: false, reduced: true }],
  ])('falls back to plain flow on %s', (_label, env) => {
    stubSyncRaf();
    stubMatchMedia(env);
    const { container } = render(
      <PinnedScene>
        <p>stage</p>
      </PinnedScene>
    );
    expect(container.querySelector('.cosmos-pin-stage')).not.toBeInTheDocument();
  });

  it('falls back to plain flow when disabled', () => {
    stubSyncRaf();
    stubMatchMedia({ mobile: false, reduced: false });
    const { container } = render(
      <PinnedScene disabled>
        <p>stage</p>
      </PinnedScene>
    );
    expect(container.querySelector('.cosmos-pin-stage')).not.toBeInTheDocument();
  });
});
