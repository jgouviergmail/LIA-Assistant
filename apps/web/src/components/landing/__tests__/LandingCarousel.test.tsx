/**
 * Behaviour + keyboard/a11y contract of the shared landing carousel.
 *
 * The oracle is deliberately NOT the class strings: it is what a visitor can
 * see, reach and hear — which view is on stage, which controls exist without
 * hovering (the defect the redesign fixes), what the keyboard does, and what a
 * screen reader is told when the view changes.
 *
 * Slides carry already-translated strings, so the tests pass a controlled set
 * instead of leaning on the global i18n stub (which echoes keys and would make
 * every caption assertion vacuous).
 */

import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { CAROUSEL_SWIPE_THRESHOLD_PX } from '@/lib/constants';
import { LandingCarousel, type CarouselSlide } from '../LandingCarousel';

const SLIDES: CarouselSlide[] = [
  { key: 'home', src: '/screenshots/homepage.png', label: 'Home screen', caption: 'Home screen' },
  { key: 'chat', src: '/screenshots/chat.png', label: 'Chat screen', caption: 'Chat screen' },
  { key: 'faq', src: '/screenshots/faq.png', label: 'FAQ screen', caption: 'FAQ screen' },
];

function renderCarousel(props: Partial<React.ComponentProps<typeof LandingCarousel>> = {}) {
  return render(
    <LandingCarousel slides={SLIDES} variant="portrait" label="App captures" {...props} />
  );
}

/** The stage image is the one named after the current view. */
function stageAlt(): string {
  const stage = screen.getByRole('group', { name: 'App captures' });
  const named = within(stage)
    .getAllByRole('img')
    .filter(img => img.getAttribute('alt'));
  return named[0].getAttribute('alt') ?? '';
}

describe('LandingCarousel', () => {
  it('shows the first view with its caption and an always-visible control pair', () => {
    renderCarousel();

    expect(stageAlt()).toBe('Home screen');
    // Controls exist in the DOM without any hover: the previous arrows were
    // opacity-0 until :hover, i.e. unreachable on a touch device.
    expect(screen.getByRole('button', { name: 'common.previous' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'common.next' })).toBeInTheDocument();
  });

  it('advances with the next arrow and wraps around with the previous one', async () => {
    const user = userEvent.setup();
    renderCarousel();

    await user.click(screen.getByRole('button', { name: 'common.next' }));
    expect(stageAlt()).toBe('Chat screen');

    await user.click(screen.getByRole('button', { name: 'common.previous' }));
    await user.click(screen.getByRole('button', { name: 'common.previous' }));
    expect(stageAlt()).toBe('FAQ screen');
  });

  it('drives the stage from the keyboard (arrows, Home, End)', async () => {
    const user = userEvent.setup();
    renderCarousel();

    const stage = screen.getByRole('group', { name: 'App captures' });
    stage.focus();
    expect(stage).toHaveFocus();

    await user.keyboard('{ArrowRight}');
    expect(stageAlt()).toBe('Chat screen');
    await user.keyboard('{End}');
    expect(stageAlt()).toBe('FAQ screen');
    await user.keyboard('{ArrowRight}');
    expect(stageAlt()).toBe('Home screen');
    await user.keyboard('{ArrowLeft}');
    expect(stageAlt()).toBe('FAQ screen');
    await user.keyboard('{Home}');
    expect(stageAlt()).toBe('Home screen');
  });

  it('navigates on a swipe, and stays put below the threshold', () => {
    renderCarousel();
    const stage = screen.getByRole('group', { name: 'App captures' });
    // Distances are derived from the shared threshold, never hardcoded: the
    // constant may move, the intent (past it / short of it) may not.
    const past = CAROUSEL_SWIPE_THRESHOLD_PX + 20;
    const short = CAROUSEL_SWIPE_THRESHOLD_PX - 10;
    const at = (clientX: number) => ({ touches: [{ clientX }] });

    fireEvent.touchStart(stage, at(300));
    fireEvent.touchMove(stage, at(300 - past));
    fireEvent.touchEnd(stage);
    expect(stageAlt()).toBe('Chat screen');

    fireEvent.touchStart(stage, at(300));
    fireEvent.touchMove(stage, at(300 + past));
    fireEvent.touchEnd(stage);
    expect(stageAlt()).toBe('Home screen');

    fireEvent.touchStart(stage, at(300));
    fireEvent.touchMove(stage, at(300 - short));
    fireEvent.touchEnd(stage);
    expect(stageAlt()).toBe('Home screen');

    // A finger that lands and lifts without moving is a tap, not a swipe.
    fireEvent.touchStart(stage, at(300));
    fireEvent.touchEnd(stage);
    expect(stageAlt()).toBe('Home screen');
  });

  it('offers one named thumbnail per view and marks the current one', async () => {
    const user = userEvent.setup();
    renderCarousel();

    const thumbs = SLIDES.map(s => screen.getByRole('button', { name: s.label }));
    expect(thumbs).toHaveLength(3);
    expect(thumbs[0]).toHaveAttribute('aria-current', 'true');
    expect(thumbs[2]).not.toHaveAttribute('aria-current');

    await user.click(thumbs[2]);
    expect(stageAlt()).toBe('FAQ screen');
    expect(thumbs[2]).toHaveAttribute('aria-current', 'true');
    expect(thumbs[0]).not.toHaveAttribute('aria-current');
  });

  it('announces the view change through a polite live caption', async () => {
    const user = userEvent.setup();
    const { container } = renderCarousel();

    const live = container.querySelector('[aria-live="polite"]');
    expect(live).toHaveTextContent('Home screen');

    await user.click(screen.getByRole('button', { name: 'common.next' }));
    // Same node, new content: a live region replaced on every change would be
    // announced by nothing.
    expect(container.querySelector('[aria-live="polite"]')).toBe(live);
    expect(live).toHaveTextContent('Chat screen');
  });

  it('keeps the position chip decorative (the caption already says it)', () => {
    const { container } = renderCarousel();
    const chip = container.querySelector('[aria-hidden="true"].tabular-nums');
    expect(chip).toHaveTextContent('01 / 03');
  });

  it('offers no full-screen view unless the caller opts in', () => {
    renderCarousel();
    expect(screen.queryByRole('button', { name: 'common.expand_image' })).toBeNull();
  });

  it('opens the current view full screen and gives focus back on close', async () => {
    const user = userEvent.setup();
    renderCarousel({ zoomable: true });

    await user.click(screen.getByRole('button', { name: 'common.next' }));
    const expand = screen.getByRole('button', { name: 'common.expand_image' });
    await user.click(expand);

    // The dialog shows the view that is on stage, not the first one.
    expect(screen.getByRole('dialog', { name: 'Chat screen' })).toBeInTheDocument();

    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(expand).toHaveFocus();
  });
});
