/**
 * ScrollScrub: writes the target section's clamped scroll progress into its
 * `--sp` custom property; pins the final state under reduced motion; renders
 * nothing and tolerates a missing target.
 */

import { render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ScrollScrub } from '../ScrollScrub';

function stubSyncRaf() {
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
    cb(0);
    return 0;
  });
}

function mountSection(id: string, top: number, height: number) {
  const section = document.createElement('section');
  section.id = id;
  document.body.appendChild(section);
  vi.spyOn(section, 'getBoundingClientRect').mockReturnValue({
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
  return section;
}

describe('ScrollScrub', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    document.body.innerHTML = '';
  });

  it('writes the section progress into --sp on scroll', () => {
    stubSyncRaf();
    // Symmetric middle of the traversal → progress 0.5.
    const section = mountSection('use-cases', (window.innerHeight - 600) / 2, 600);
    const { container } = render(<ScrollScrub targetId="use-cases" />);
    window.dispatchEvent(new Event('scroll'));
    expect(parseFloat(section.style.getPropertyValue('--sp'))).toBeCloseTo(0.5, 2);
    expect(container).toBeEmptyDOMElement();
  });

  it('pins --sp to 1 under prefers-reduced-motion (static final state)', () => {
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
    const section = mountSection('gallery', window.innerHeight, 600);
    render(<ScrollScrub targetId="gallery" />);
    window.dispatchEvent(new Event('scroll'));
    expect(section.style.getPropertyValue('--sp')).toBe('1.0000');
  });

  it('copies inline animation-delays into --d when syncStageDelays is set', () => {
    stubSyncRaf();
    const section = mountSection('chapter-act', 0, 600);
    const el = document.createElement('span');
    el.style.animationDelay = '250ms';
    section.appendChild(el);
    render(<ScrollScrub targetId="chapter-act" syncStageDelays />);
    expect(el.style.getPropertyValue('--d')).toBe('250');
  });

  it('tolerates a missing target without throwing', () => {
    stubSyncRaf();
    expect(() => {
      render(<ScrollScrub targetId="does-not-exist" />);
      window.dispatchEvent(new Event('scroll'));
    }).not.toThrow();
  });
});
