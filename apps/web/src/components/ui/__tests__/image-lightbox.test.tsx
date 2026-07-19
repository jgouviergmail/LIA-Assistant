/**
 * ImageLightbox — open/close gating, the close affordances (button, Escape,
 * backdrop), the stop-propagation guard on the image, and the download flow.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, fireEvent, waitFor, within } from '@/__tests__/test-utils';

const { downloadImage } = vi.hoisted(() => ({ downloadImage: vi.fn() }));
vi.mock('@/lib/utils/download-image', () => ({ downloadImage }));

import { ImageLightbox } from '../image-lightbox';

beforeEach(() => {
  vi.clearAllMocks();
  downloadImage.mockResolvedValue(undefined);
});

function open(overrides: Partial<Parameters<typeof ImageLightbox>[0]> = {}) {
  const onClose = vi.fn();
  const result = renderWithProviders(
    <ImageLightbox src="/img.png" alt="A cat" isOpen onClose={onClose} {...overrides} />
  );
  return { onClose, ...result };
}

describe('ImageLightbox — visibility', () => {
  it('renders nothing while closed', () => {
    renderWithProviders(
      <ImageLightbox src="/img.png" alt="A cat" isOpen={false} onClose={vi.fn()} />
    );
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });

  it('renders the image and action buttons when open', () => {
    open();
    expect(screen.getByRole('img', { name: 'A cat' })).toHaveAttribute('src', '/img.png');
    expect(screen.getByRole('button', { name: 'common.close' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'common.download' })).toBeInTheDocument();
  });
});

describe('ImageLightbox — closing', () => {
  it('closes via the close button', async () => {
    const { onClose, user } = open();
    await user.click(screen.getByRole('button', { name: 'common.close' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('closes on Escape', () => {
    const { onClose } = open();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('closes when the backdrop is clicked', () => {
    const { onClose, container } = open();
    // The backdrop is its own layer (the dialog must stay handler-free), so
    // the click target is that layer, not the outer wrapper.
    const backdrop = container.querySelector('[role="presentation"]');
    expect(backdrop).not.toBeNull();
    fireEvent.click(backdrop!);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('does not close when the image itself is clicked (stop-propagation guard)', async () => {
    const { onClose, user } = open();
    await user.click(screen.getByRole('img', { name: 'A cat' }));
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe('ImageLightbox — download', () => {
  it('downloads the image without closing the lightbox', async () => {
    const { onClose, user } = open();
    await user.click(screen.getByRole('button', { name: 'common.download' }));
    await waitFor(() => expect(downloadImage).toHaveBeenCalledWith('/img.png', 'A cat'));
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe('ImageLightbox — modal semantics', () => {
  it('announces itself as a modal named after the picture', () => {
    open();

    const dialog = screen.getByRole('dialog', { name: 'A cat' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    // Controls live inside the dialog: a screen-reader user who lands here
    // reaches the close button without leaving the modal.
    expect(within(dialog).getByRole('button', { name: 'common.close' })).toBeInTheDocument();
  });

  it('takes focus when it opens', () => {
    open();

    expect(screen.getByRole('dialog')).toHaveFocus();
  });

  it('gives focus back to whatever opened it', async () => {
    const trigger = document.createElement('button');
    document.body.appendChild(trigger);
    trigger.focus();
    expect(trigger).toHaveFocus();

    const { unmount } = open();
    expect(screen.getByRole('dialog')).toHaveFocus();

    unmount();

    // Without this, a keyboard user is dropped at the top of the document and
    // has to tab all the way back to the thumbnail they came from.
    await waitFor(() => expect(trigger).toHaveFocus());
    trigger.remove();
  });

  it('releases the page scroll when it closes', () => {
    const { unmount } = open();
    expect(document.body.style.overflow).toBe('hidden');

    unmount();

    expect(document.body.style.overflow).not.toBe('hidden');
  });
});

describe('ImageLightbox — focus stability', () => {
  /**
   * Mirrors every real call site: `onClose` is an inline arrow, so its identity
   * changes on each parent render. `tick` only exists to force that render —
   * driving it through `rerender()` rather than a click keeps the probe
   * focus-neutral (a pointer click would focus the button it hit and mask the
   * very thing under test).
   */
  function Host({ tick }: { tick: number }) {
    return (
      <>
        <span data-testid="tick">{tick}</span>
        <ImageLightbox src="/img.png" alt="A cat" isOpen onClose={() => {}} />
      </>
    );
  }

  it('keeps focus on the control the user reached when the parent re-renders', () => {
    const { rerender } = renderWithProviders(<Host tick={0} />);
    const download = screen.getByRole('button', { name: 'common.download' });
    download.focus();

    // A streaming chat message re-renders constantly while the lightbox is
    // open. Before the effect split, each render restored focus to the trigger
    // and bounced it back to the dialog, stealing it from this button.
    rerender(<Host tick={1} />);

    expect(download).toHaveFocus();
  });

  // Note: no companion test on the scroll lock. The buggy version churned it
  // ('unset' then 'hidden' within the same commit) but ended on the right
  // value, so any assertion on `body.style.overflow` passes before AND after
  // the fix — it would be a test that proves nothing. The release path is
  // covered by 'releases the page scroll when it closes' above.
});

describe('ImageLightbox — focus trap', () => {
  it('cycles forward from the last control back to the first', async () => {
    const { user } = open();
    const [download, close] = [
      screen.getByRole('button', { name: 'common.download' }),
      screen.getByRole('button', { name: 'common.close' }),
    ];

    // From the dialog itself, Tab enters the ring at the first control…
    await user.tab();
    expect(download).toHaveFocus();
    await user.tab();
    expect(close).toHaveFocus();

    // …and wraps instead of walking out into the page `aria-modal` just
    // declared inert.
    await user.tab();
    expect(download).toHaveFocus();
  });

  it('cycles backward from the first control to the last', async () => {
    const { user } = open();
    screen.getByRole('button', { name: 'common.download' }).focus();

    await user.tab({ shift: true });

    expect(screen.getByRole('button', { name: 'common.close' })).toHaveFocus();
  });

  it('pulls focus back in when it has escaped to the document body', async () => {
    const outside = document.createElement('button');
    document.body.appendChild(outside);
    const { user } = open();
    // Reproduces the download button disabling itself under the user's fingers.
    (document.activeElement as HTMLElement | null)?.blur();

    await user.tab();

    expect(screen.getByRole('button', { name: 'common.download' })).toHaveFocus();
    expect(outside).not.toHaveFocus();
    outside.remove();
  });
});
