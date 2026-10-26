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
import { CHAPTERS, WORLD_CHAPTER_ANCHOR } from '../chapters-data';

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
  it('names every chapter and preserves both the connection and World destinations', () => {
    render(<ChapterRail />);
    expect(screen.getAllByRole('link')).toHaveLength(CHAPTERS.length + 1);
    for (const chapter of CHAPTERS) {
      const link = screen.getByRole('link', { name: `landing.chapters.${chapter.key}.title` });
      expect(link).toHaveAttribute('href', `#${chapter.anchor}`);
      expect(link).toHaveTextContent(chapter.num);
    }
    expect(screen.getByRole('link', { name: 'landing.chapters.c6.title' })).toHaveAttribute(
      'href',
      '#chapter-connect'
    );
    expect(screen.getByRole('link', { name: 'landing.chapters.c7.title' })).toHaveAttribute(
      'href',
      `#${WORLD_CHAPTER_ANCHOR}`
    );
  });

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

  it('tracks the World anchor independently of the connection chapter', () => {
    const world = document.createElement('section');
    world.id = WORLD_CHAPTER_ANCHOR;
    document.body.append(world);
    render(<ChapterRail />);
    const watcher = observers.find(observer => observer.targets.includes(world));
    expect(watcher).toBeDefined();
    const entry: IntersectionObserverEntry = {
      target: world,
      isIntersecting: true,
      boundingClientRect: world.getBoundingClientRect(),
      intersectionRect: world.getBoundingClientRect(),
      intersectionRatio: 1,
      rootBounds: null,
      time: 0,
    };
    act(() => watcher?.callback([entry], {} as IntersectionObserver));
    expect(screen.getByRole('link', { name: 'landing.chapters.c7.title' })).toHaveAttribute(
      'aria-current',
      'true'
    );
    expect(screen.getByRole('link', { name: 'landing.chapters.c6.title' })).not.toHaveAttribute(
      'aria-current'
    );
  });
});
