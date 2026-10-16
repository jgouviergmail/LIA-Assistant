import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import type { GeneratedAsset } from '@/types/generated-assets';

const { read } = vi.hoisted(() => ({ read: vi.fn() }));
vi.mock('@/lib/document-preview', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/document-preview')>()),
  fetchDocumentPreview: read,
}));
import { AssetDocumentPreview } from '../AssetDocumentPreview';

let enter: () => void;
beforeEach(() => {
  read.mockReset();
  read.mockResolvedValue({ text: 'Actual document excerpt', truncated: false });
  class Observer implements IntersectionObserver {
    readonly scrollMargin = '0px';
    root = null;
    rootMargin = '100px';
    thresholds = [0];
    constructor(private callback: IntersectionObserverCallback) {}
    observe(target: Element) {
      const rectangle = target.getBoundingClientRect();
      enter = () =>
        this.callback(
          [
            {
              isIntersecting: true,
              target,
              boundingClientRect: rectangle,
              intersectionRect: rectangle,
              rootBounds: null,
              intersectionRatio: 1,
              time: 0,
            },
          ],
          this
        );
    }
    unobserve() {}
    takeRecords(): IntersectionObserverEntry[] {
      return [];
    }
    disconnect() {}
  }
  vi.stubGlobal('IntersectionObserver', Observer);
});
afterEach(() => vi.unstubAllGlobals());
function asset(ext: string): GeneratedAsset {
  return {
    id: '11111111-1111-4111-8111-111111111111',
    title: null,
    original_filename: `Report.${ext}`,
    mime_type: 'application/octet-stream',
    file_size: 100,
    origin: 'generated_document',
    conversation_id: null,
    created_at: '',
    expires_at: null,
    shared_by_name: null,
  };
}
describe('gallery document previews', () => {
  it('waits near the viewport before loading the real PDF page and offers no nested control', async () => {
    render(<AssetDocumentPreview asset={asset('pdf')} label="Report" />);
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    act(() => enter());
    const image = await screen.findByRole('img');
    expect(image.getAttribute('src')).toContain('/11111111-1111-4111-8111-111111111111/preview');
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(read).not.toHaveBeenCalled();
    fireEvent.error(image);
    expect(screen.getByTestId('generated-asset-typemark')).toBeInTheDocument();
  });
  it('identifies Office output as an excerpt and cancels its bounded read on unmount', async () => {
    const { unmount } = render(<AssetDocumentPreview asset={asset('docx')} label="Report" />);
    expect(read).not.toHaveBeenCalled();
    act(() => enter());
    expect(await screen.findByText('Actual document excerpt')).toBeVisible();
    expect(screen.getByText('chat.document_card.excerpt')).toBeVisible();
    const signal: AbortSignal = read.mock.calls[0][1];
    expect(signal.aborted).toBe(false);
    unmount();
    expect(signal.aborted).toBe(true);
  });
  it('falls back to the file type when an expired document refuses its excerpt', async () => {
    read.mockRejectedValueOnce(new Error('expired'));
    render(<AssetDocumentPreview asset={asset('txt')} label="Report" />);
    act(() => enter());
    await waitFor(() => expect(read).toHaveBeenCalledTimes(1));
    expect(screen.getByTestId('generated-asset-typemark')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});
