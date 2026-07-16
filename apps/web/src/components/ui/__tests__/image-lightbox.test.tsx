/**
 * ImageLightbox — open/close gating, the close affordances (button, Escape,
 * backdrop), the stop-propagation guard on the image, and the download flow.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, fireEvent, waitFor } from '@/__tests__/test-utils';

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
    fireEvent.click(container.firstChild as HTMLElement);
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
