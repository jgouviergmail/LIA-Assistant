/**
 * MoreCard — the card shell wiring a scene to its meaning:
 *  - the animated stage is aria-hidden decoration with no interactive role
 *    (the visible title + description carry the content);
 *  - the scene's `active` prop is the AND of in-viewport and not-paused
 *    (context) — the WCAG 2.2.2 pause and the out-of-view economy both flow
 *    through it;
 *  - scene micro-labels are resolved from SCENE_LABEL_KEYS through `t`.
 */

import { act, fireEvent, render, screen } from '@testing-library/react';
import { Bell } from 'lucide-react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AnimationPauseToggle, MoreAnimationProvider } from '../animation-context';
import { MoreCard } from '../MoreCard';
import type { SceneProps } from '../scene-types';

/** Observer double: captures instances so tests can fire intersections. */
class ObserverDouble {
  static instances: ObserverDouble[] = [];
  readonly elements: Element[] = [];
  constructor(readonly callback: IntersectionObserverCallback) {
    ObserverDouble.instances.push(this);
  }
  observe(el: Element): void {
    this.elements.push(el);
  }
  unobserve(): void {}
  disconnect(): void {}
  takeRecords(): IntersectionObserverEntry[] {
    return [];
  }
  fire(isIntersecting: boolean): void {
    this.callback(
      [{ isIntersecting } as IntersectionObserverEntry],
      this as unknown as IntersectionObserver
    );
  }
}

const seenActive: boolean[] = [];
function ProbeScene({ active, labels }: SceneProps) {
  seenActive.push(active);
  return <div data-testid="probe-scene">{labels.typing ?? ''}</div>;
}

const t = (key: string) => key;

function renderCard() {
  return render(
    <MoreAnimationProvider>
      <AnimationPauseToggle />
      <ul>
        <MoreCard cardKey="draft_survives" icon={Bell} scene={ProbeScene} t={t} />
      </ul>
    </MoreAnimationProvider>
  );
}

describe('MoreCard', () => {
  beforeEach(() => {
    seenActive.length = 0;
    ObserverDouble.instances.length = 0;
    vi.stubGlobal('IntersectionObserver', ObserverDouble);
  });
  afterEach(() => vi.unstubAllGlobals());

  it('renders the translated title as an h3 and the description', () => {
    renderCard();
    expect(
      screen.getByRole('heading', { level: 3, name: 'more.cards.draft_survives.title' })
    ).toBeInTheDocument();
    expect(screen.getByText('more.cards.draft_survives.desc')).toBeInTheDocument();
  });

  it('hides the stage from assistive tech and keeps it non-interactive', () => {
    renderCard();
    // Scope to the card: the pause toggle outside also carries aria-hidden art.
    const card = screen.getByRole('listitem');
    const stage = card.querySelector('[aria-hidden="true"]');
    expect(stage).not.toBeNull();
    expect(stage!.contains(screen.getByTestId('probe-scene'))).toBe(true);
    // The only button on the page is the pause toggle, outside the card.
    expect(screen.getAllByRole('button')).toHaveLength(1);
    expect(card.querySelector('button, a, input')).toBeNull();
  });

  it('resolves the scene labels declared in SCENE_LABEL_KEYS through t', () => {
    renderCard();
    expect(screen.getByTestId('probe-scene')).toHaveTextContent(
      'more.scenes.draft_survives.typing'
    );
  });

  it('activates the scene only when in view AND not paused', () => {
    renderCard();
    // Not yet intersecting: inactive.
    expect(seenActive.at(-1)).toBe(false);

    act(() => ObserverDouble.instances.forEach(o => o.fire(true)));
    expect(seenActive.at(-1)).toBe(true);

    fireEvent.click(screen.getByRole('button'));
    expect(seenActive.at(-1)).toBe(false);

    fireEvent.click(screen.getByRole('button'));
    expect(seenActive.at(-1)).toBe(true);

    // Scrolled out again: inactive even while playing.
    act(() => ObserverDouble.instances.forEach(o => o.fire(false)));
    expect(seenActive.at(-1)).toBe(false);
  });
});
