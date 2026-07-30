/**
 * CosmosDay: pinned scroll-driven day on desktop (steps light with progress,
 * real `landing.day.*` keys, accessible Tabs), untouched classic DayTimeline
 * on mobile / reduced motion.
 */

import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { CosmosDay } from '../CosmosDay';

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

describe('CosmosDay', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('renders the pinned scene with tabs, ghost word and step cards on desktop', () => {
    stubSyncRaf();
    stubMatchMedia({ mobile: false, reduced: false });
    const { container } = render(<CosmosDay />);

    expect(screen.getByRole('heading', { name: 'landing.day.title' })).toBeInTheDocument();
    expect(container.querySelector('.cosmos-pin-stage')).toBeInTheDocument();
    expect(container.querySelector('.cosmos-ghost')).toHaveTextContent(
      'landing.cosmos.ghost.day'
    );
    expect(screen.getByRole('tablist')).toBeInTheDocument();
    expect(screen.getAllByRole('tab')).toHaveLength(4);
    // 4 profiles × 4 stops, all panels in the DOM (hidden panels included).
    expect(container.querySelectorAll('.cosmos-step')).toHaveLength(16);
    expect(container.querySelector('.cosmos-progress')).toBeInTheDocument();
  });

  it('lights the day steps as the pinned progress advances', () => {
    stubSyncRaf();
    stubMatchMedia({ mobile: false, reduced: false });
    // Pin geometry at 60% progress: -top = 0.6 × (3.2vh − vh).
    const total = window.innerHeight * 3.2;
    const top = -0.6 * (total - window.innerHeight);
    vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(total);
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
      top,
      height: total,
      bottom: top + total,
      left: 0,
      right: 300,
      width: 300,
      x: 0,
      y: top,
      toJSON: () => ({}),
    } as DOMRect);

    const { container } = render(<CosmosDay />);
    window.dispatchEvent(new Event('scroll'));

    const firstPanelSteps = container.querySelectorAll('[role="tabpanel"]')[0]
      ? container.querySelectorAll('[role="tabpanel"]')[0].querySelectorAll('.cosmos-step')
      : [];
    expect(firstPanelSteps).toHaveLength(4);
    // At p = 0.6: thresholds 0, .25, .5 are lit; .75 is not.
    expect(firstPanelSteps[0]).toHaveClass('lit');
    expect(firstPanelSteps[1]).toHaveClass('lit');
    expect(firstPanelSteps[2]).toHaveClass('lit');
    expect(firstPanelSteps[3]).not.toHaveClass('lit');
  });

  it.each([
    ['mobile', { mobile: true, reduced: false }],
    ['reduced motion', { mobile: false, reduced: true }],
  ])('falls back to the classic DayTimeline on %s', (_label, env) => {
    stubSyncRaf();
    stubMatchMedia(env);
    const { container } = render(<CosmosDay />);
    // The classic section renders (same heading), with no pin and no ghost.
    expect(screen.getByRole('heading', { name: 'landing.day.title' })).toBeInTheDocument();
    expect(container.querySelector('.cosmos-pin-stage')).not.toBeInTheDocument();
    expect(container.querySelector('.cosmos-ghost')).not.toBeInTheDocument();
  });
});
