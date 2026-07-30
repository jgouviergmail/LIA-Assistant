/**
 * GlowCard (glass surface, optional tilt) and BlurReveal (one-shot blur→sharp
 * staging, reduced-motion final state).
 */

import { act, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { BlurReveal } from '../BlurReveal';
import { GlowCard } from '../GlowCard';

describe('GlowCard', () => {
  it('renders the glass surface and merges custom classes', () => {
    render(
      <GlowCard className="extra">
        <p>content</p>
      </GlowCard>
    );
    const card = screen.getByText('content').parentElement as HTMLElement;
    expect(card).toHaveClass('cosmos-glass', 'extra');
  });

  it('maps each tilt to its class, none by default', () => {
    const { container, rerender } = render(<GlowCard tilt={-2}>x</GlowCard>);
    expect(container.firstChild).toHaveClass('cosmos-tilt-n2');
    rerender(<GlowCard tilt={1}>x</GlowCard>);
    expect(container.firstChild).toHaveClass('cosmos-tilt-1');
    rerender(<GlowCard>x</GlowCard>);
    expect((container.firstChild as HTMLElement).className).not.toMatch(/cosmos-tilt/);
  });
});

type IOCallback = (entries: Array<{ isIntersecting: boolean; target: Element }>) => void;

function installObserverDouble() {
  const state: { callback: IOCallback | null; unobserved: Element[] } = {
    callback: null,
    unobserved: [],
  };
  class ObserverDouble {
    constructor(cb: IOCallback) {
      state.callback = cb;
    }
    observe(): void {}
    unobserve(el: Element): void {
      state.unobserved.push(el);
    }
    disconnect(): void {}
  }
  vi.stubGlobal('IntersectionObserver', ObserverDouble as unknown as typeof IntersectionObserver);
  return state;
}

describe('BlurReveal', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('starts blurred and reveals once when intersecting, then unobserves', () => {
    const observer = installObserverDouble();
    const { container } = render(
      <BlurReveal>
        <p>proof</p>
      </BlurReveal>
    );
    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper).toHaveClass('cosmos-reveal');
    expect(wrapper).not.toHaveClass('in');

    act(() => {
      observer.callback?.([{ isIntersecting: true, target: wrapper }]);
    });
    expect(wrapper).toHaveClass('in');
    expect(observer.unobserved).toContain(wrapper);
  });

  it('applies the stagger delay as a transition delay', () => {
    installObserverDouble();
    const { container } = render(<BlurReveal delay={240}>x</BlurReveal>);
    expect((container.firstChild as HTMLElement).style.transitionDelay).toBe('240ms');
  });

  it('sets no transition delay by default (siblings only stagger on request)', () => {
    installObserverDouble();
    const { container } = render(<BlurReveal>x</BlurReveal>);
    expect((container.firstChild as HTMLElement).style.transitionDelay).toBe('');
    // Reduced motion is handled by the CSS kill-switch (`.cosmos-reveal`
    // forced to its final state), not by a JS branch — nothing to assert here.
  });
});
