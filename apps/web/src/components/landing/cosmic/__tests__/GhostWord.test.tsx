/**
 * The ghost word must stay decorative, translated, and drift laterally with
 * its host section's scroll progress — in the direction it was given, and not
 * at all under prefers-reduced-motion.
 */

import { render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { GhostWord } from '../GhostWord';

function mockSectionRect(top: number, height: number) {
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
    top,
    height,
    bottom: top + height,
    left: 0,
    right: 1024,
    width: 1024,
    x: 0,
    y: top,
    toJSON: () => ({}),
  } as DOMRect);
}

function renderInSection(direction: 1 | -1) {
  return render(
    <section>
      <GhostWord wordKey="landing.cosmos.ghost.act" direction={direction} />
    </section>
  );
}

function stubSyncRaf() {
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
    cb(0);
    return 0;
  });
}

describe('GhostWord', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('renders the translated word as decoration behind a screen-aligned frame', () => {
    stubSyncRaf();
    const { container } = renderInSection(1);
    const frame = container.querySelector('.cosmos-ghost-frame');
    expect(frame).toHaveAttribute('aria-hidden', 'true');
    // The setup i18n stub echoes the key.
    expect(frame?.querySelector('.cosmos-ghost')).toHaveTextContent('landing.cosmos.ghost.act');
  });

  it('drifts positively for direction 1 when the section is past its midpoint', () => {
    stubSyncRaf();
    // top = -height/2 → progress > 0.5 → positive x for direction 1.
    mockSectionRect(-600, 1200);
    const { container } = renderInSection(1);
    window.dispatchEvent(new Event('scroll'));
    const ghost = container.querySelector('.cosmos-ghost') as HTMLElement;
    const match = ghost.style.transform.match(/translateX\((-?[\d.]+)px/);
    expect(match).not.toBeNull();
    expect(parseFloat(match![1])).toBeGreaterThan(0);
  });

  it('mirrors the drift for direction -1', () => {
    stubSyncRaf();
    mockSectionRect(-600, 1200);
    const { container } = renderInSection(-1);
    window.dispatchEvent(new Event('scroll'));
    const ghost = container.querySelector('.cosmos-ghost') as HTMLElement;
    const match = ghost.style.transform.match(/translateX\((-?[\d.]+)px/);
    expect(match).not.toBeNull();
    expect(parseFloat(match![1])).toBeLessThan(0);
  });

  it('writes no transform under prefers-reduced-motion', () => {
    stubSyncRaf();
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockImplementation((query: string) => ({
        matches: query.includes('prefers-reduced-motion'),
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        onchange: null,
        dispatchEvent: vi.fn(),
      }))
    );
    mockSectionRect(-600, 1200);
    const { container } = renderInSection(1);
    window.dispatchEvent(new Event('scroll'));
    const ghost = container.querySelector('.cosmos-ghost') as HTMLElement;
    expect(ghost.style.transform).toBe('');
  });
});
