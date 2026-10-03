/**
 * The fixed chapter rail steps aside when the footer comes into view: the
 * footer's glass band is drawn above it, so at the end of the page its links
 * would sit under the band, blurred and unclickable. Hidden with `visibility`,
 * the rail also leaves the focus order — and comes back when the footer leaves.
 */

import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

import { ChapterRail } from '../ChapterRail';

interface Observed {
  callback: IntersectionObserverCallback;
  targets: Element[];
}

let observers: Observed[];

beforeEach(() => {
  observers = [];
  vi.stubGlobal(
    'IntersectionObserver',
    class {
      private readonly record: Observed;
      constructor(callback: IntersectionObserverCallback) {
        this.record = { callback, targets: [] };
        observers.push(this.record);
      }
      observe(target: Element) {
        this.record.targets.push(target);
      }
      unobserve() {}
      disconnect() {}
      takeRecords() {
        return [];
      }
    }
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.replaceChildren();
});

/** Tells the observer watching the footer whether it is on screen. */
function footerInView(footer: Element, isIntersecting: boolean): void {
  const watcher = observers.find(o => o.targets.includes(footer));
  expect(watcher).toBeDefined();
  act(() =>
    watcher?.callback(
      [{ target: footer, isIntersecting } as IntersectionObserverEntry],
      {} as IntersectionObserver
    )
  );
}

describe('ChapterRail', () => {
  it('hides while the footer is on screen, and returns when it leaves', () => {
    const footer = document.createElement('footer');
    footer.className = 'landing-footer';
    document.body.append(footer);
    render(<ChapterRail />);
    const rail = screen.getByRole('navigation', { name: 'landing.rail.aria' });
    expect(rail.className).not.toContain('invisible');

    footerInView(footer, true);
    expect(rail.className).toContain('invisible');
    expect(rail.className).toContain('pointer-events-none');

    footerInView(footer, false);
    expect(rail.className).not.toContain('invisible');
  });

  it('stays put on a page with no landing footer', () => {
    render(<ChapterRail />);
    const rail = screen.getByRole('navigation', { name: 'landing.rail.aria' });
    expect(rail.className).not.toContain('invisible');
  });
});
