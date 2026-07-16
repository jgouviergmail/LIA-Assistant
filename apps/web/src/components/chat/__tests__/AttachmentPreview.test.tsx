/**
 * AttachmentPreview — the empty-list null render, image vs file rendering, the
 * uploading/error overlays, and the remove affordance.
 */

import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen, fireEvent } from '@/__tests__/test-utils';
import AttachmentPreview from '../AttachmentPreview';
import type { PendingAttachment } from '@/hooks/useFileUpload';

function att(over: Partial<PendingAttachment> = {}): PendingAttachment {
  return {
    tempId: 't1',
    filename: 'photo.png',
    contentType: 'image',
    previewUrl: 'blob:preview',
    status: 'ready',
    progress: 100,
    size: 2048,
    mimeType: 'image/png',
    ...over,
  };
}

describe('AttachmentPreview', () => {
  it('renders nothing when there are no attachments', () => {
    const { container } = renderWithProviders(
      <AttachmentPreview attachments={[]} onRemove={vi.fn()} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders an image thumbnail for image attachments', () => {
    renderWithProviders(<AttachmentPreview attachments={[att()]} onRemove={vi.fn()} />);
    expect(screen.getByRole('img', { name: 'photo.png' })).toHaveAttribute('src', 'blob:preview');
  });

  it('renders a file icon and filename for non-image attachments', () => {
    renderWithProviders(
      <AttachmentPreview
        attachments={[
          att({ contentType: 'document', previewUrl: undefined, filename: 'report.pdf' }),
        ]}
        onRemove={vi.fn()}
      />
    );
    expect(screen.getByText('report.pdf')).toBeInTheDocument();
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });

  it('shows the upload progress while uploading', () => {
    renderWithProviders(
      <AttachmentPreview
        attachments={[att({ status: 'uploading', progress: 42 })]}
        onRemove={vi.fn()}
      />
    );
    expect(screen.getByText('42%')).toBeInTheDocument();
  });

  it('removes an attachment when its remove button is clicked', () => {
    const onRemove = vi.fn();
    renderWithProviders(
      <AttachmentPreview attachments={[att({ tempId: 'abc' })]} onRemove={onRemove} />
    );
    // fireEvent (not userEvent) so the Radix Tooltip's hover/focus timers don't
    // open asynchronously and race the assertion — we only exercise the click.
    fireEvent.click(screen.getByRole('button', { name: 'chat.attachments.remove' }));
    expect(onRemove).toHaveBeenCalledWith('abc');
  });
});
