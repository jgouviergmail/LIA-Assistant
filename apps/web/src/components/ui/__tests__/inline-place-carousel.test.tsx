/**
 * InlinePlaceCarousel — instance-scoped keyboard navigation (audit F045).
 *
 * The carousel used to listen on document.keydown: every mounted instance
 * reacted to every arrow key anywhere on the page (cross-instance navigation,
 * and navigation while typing elsewhere). Keyboard handling must be scoped to
 * the focused instance, with named, keyboard-operable controls.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent, within } from '@testing-library/react';

import { InlinePlaceCarousel } from '../inline-place-carousel';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts ? `${key} ${opts.current}/${opts.total}` : key,
  }),
}));

const IMAGES_A = ['/a1.jpg', '/a2.jpg', '/a3.jpg'];
const IMAGES_B = ['/b1.jpg', '/b2.jpg'];

function renderTwoCarousels() {
  const utils = render(
    <div>
      <InlinePlaceCarousel images={IMAGES_A} alt="Carousel A" />
      <InlinePlaceCarousel images={IMAGES_B} alt="Carousel B" />
    </div>
  );
  const [a, b] = utils.getAllByRole('group');
  return { ...utils, a, b };
}

function currentSrc(carousel: HTMLElement): string | null {
  return carousel.querySelector('img')?.getAttribute('src') ?? null;
}

describe('InlinePlaceCarousel — keyboard scoping', () => {
  it('is a named, focusable group', () => {
    const { a, b } = renderTwoCarousels();
    expect(a.getAttribute('aria-label')).toBe('Carousel A');
    expect(b.getAttribute('aria-label')).toBe('Carousel B');
    expect(a.getAttribute('aria-roledescription')).toBe('carousel');
    expect(a.tabIndex).toBe(0);
  });

  it('arrow keys navigate ONLY the instance that has focus', () => {
    const { a, b } = renderTwoCarousels();

    a.focus();
    fireEvent.keyDown(a, { key: 'ArrowRight' });

    expect(currentSrc(a)).toBe('/a2.jpg');
    // The sibling carousel must not move (the old document listener bug).
    expect(currentSrc(b)).toBe('/b1.jpg');

    fireEvent.keyDown(a, { key: 'ArrowLeft' });
    expect(currentSrc(a)).toBe('/a1.jpg');
    expect(currentSrc(b)).toBe('/b1.jpg');
  });

  it('does not react to keys pressed outside any carousel', () => {
    const { a, b } = renderTwoCarousels();

    fireEvent.keyDown(document.body, { key: 'ArrowRight' });

    expect(currentSrc(a)).toBe('/a1.jpg');
    expect(currentSrc(b)).toBe('/b1.jpg');
  });

  it('arrow keys work while focus is on an inner control (event bubbling)', () => {
    const { a, b } = renderTwoCarousels();
    const nextButton = within(a).getByLabelText('common.next');

    nextButton.focus();
    fireEvent.keyDown(nextButton, { key: 'ArrowRight' });

    expect(currentSrc(a)).toBe('/a2.jpg');
    expect(currentSrc(b)).toBe('/b1.jpg');
  });

  it('exposes named prev/next controls operable per instance', () => {
    const { a, b } = renderTwoCarousels();

    fireEvent.click(within(b).getByLabelText('common.next'));
    expect(currentSrc(b)).toBe('/b2.jpg');
    expect(currentSrc(a)).toBe('/a1.jpg');

    fireEvent.click(within(b).getByLabelText('common.previous'));
    expect(currentSrc(b)).toBe('/b1.jpg');
  });

  it('single-image carousel is not focusable (nothing to navigate)', () => {
    const { getByRole } = render(<InlinePlaceCarousel images={['/only.jpg']} alt="Solo" />);
    const solo = getByRole('group');
    expect(solo.hasAttribute('tabindex')).toBe(false);
  });
});

describe('InlinePlaceCarousel — keyboard reach and announcement (item 10b)', () => {
  const IMAGES = ['a.png', 'b.png', 'c.png', 'd.png'];

  it('jumps to the first and last photo with Home and End', () => {
    // Arrowing through a long gallery to reach its end is a chore the
    // platform already has an answer for.
    const { getByRole, getByText } = render(<InlinePlaceCarousel images={IMAGES} alt="Lieu" />);

    fireEvent.keyDown(getByRole('group'), { key: 'End' });
    expect(getByText(`${IMAGES.length} / ${IMAGES.length}`)).toBeInTheDocument();

    fireEvent.keyDown(getByRole('group'), { key: 'Home' });
    expect(getByText(`1 / ${IMAGES.length}`)).toBeInTheDocument();
  });

  it('announces the position so it is not visual-only', () => {
    // The counter badge is text on screen; a screen-reader user needs the
    // change spoken, not merely rendered.
    const { getByRole } = render(<InlinePlaceCarousel images={IMAGES} alt="Lieu" />);

    fireEvent.keyDown(getByRole('group'), { key: 'ArrowRight' });

    expect(getByRole('status')).toHaveTextContent('gallery.photo_counter');
  });

  it('announces nothing when there is nothing to navigate', () => {
    const { queryByRole } = render(<InlinePlaceCarousel images={['only.png']} alt="Lieu" />);

    expect(queryByRole('status')).not.toBeInTheDocument();
  });
});

describe('InlinePlaceCarousel — opening a photo full screen', () => {
  const IMAGES = ['a.png', 'b.png', 'c.png'];

  it('opens the lightbox on the photo the reader is looking at', async () => {
    const { getByRole, findByRole } = render(<InlinePlaceCarousel images={IMAGES} alt="Lieu" />);

    fireEvent.keyDown(getByRole('group'), { key: 'ArrowRight' });
    fireEvent.click(getByRole('button', { name: 'gallery.expand_photo' }));

    // The dialog shows the CURRENT photo, not the first one.
    const dialog = await findByRole('dialog');
    expect(within(dialog).getByRole('img')).toHaveAttribute('src', IMAGES[1]);
  });

  it('carries the navigation into the lightbox', async () => {
    const { getByRole, findByRole } = render(<InlinePlaceCarousel images={IMAGES} alt="Lieu" />);

    fireEvent.click(getByRole('button', { name: 'gallery.expand_photo' }));
    const dialog = await findByRole('dialog');

    fireEvent.click(within(dialog).getByRole('button', { name: 'common.next' }));

    expect(within(dialog).getByRole('img')).toHaveAttribute('src', IMAGES[1]);
  });

  it('offers no full-screen entry for a single photo', () => {
    const { queryByRole } = render(<InlinePlaceCarousel images={['only.png']} alt="Lieu" />);

    expect(queryByRole('button', { name: 'gallery.expand_photo' })).not.toBeInTheDocument();
  });
});
