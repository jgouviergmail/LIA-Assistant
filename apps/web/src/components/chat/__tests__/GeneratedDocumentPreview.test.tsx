import { act, fireEvent, screen, waitFor } from '@testing-library/react';
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/__tests__/test-utils';
import { GeneratedDocumentPreview } from '../GeneratedDocumentPreview';

const url = '/api/v1/attachments/00000000-0000-4000-8000-00000000d001';
let show: () => void;
const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
  vi.stubGlobal(
    'IntersectionObserver',
    class {
      constructor(callback: IntersectionObserverCallback) {
        show = () =>
          callback(
            [{ isIntersecting: true } as IntersectionObserverEntry],
            this as unknown as IntersectionObserver
          );
      }
      observe() {}
      disconnect() {}
    }
  );
});
afterEach(() => vi.unstubAllGlobals());

describe('small source document previews', () => {
  it('fetches text only on visibility, with credentials; renders text as inert data', async () => {
    fetchMock.mockResolvedValue(
      new Response('<script>alert(1)</script>\nreceived source', {
        headers: { 'Content-Type': 'text/plain' },
      })
    );
    const { container } = renderWithProviders(
      <GeneratedDocumentPreview url={url} docType="md" filename="notes.md" />
    );
    expect(fetchMock).not.toHaveBeenCalled();
    act(() => show());
    await waitFor(() => expect(screen.getByText(/received source/)).toBeInTheDocument());
    expect(container.querySelector('script')).toBeNull();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining(`${url}/preview`),
      expect.objectContaining({ credentials: 'include', signal: expect.any(AbortSignal) })
    );
  });

  it('caps CSV rows and columns while retaining quoted source fields', async () => {
    fetchMock.mockResolvedValue(
      new Response('name,note\nCamille,"quote, kept"\n' + 'row,value\n'.repeat(30))
    );
    renderWithProviders(<GeneratedDocumentPreview url={url} docType="csv" filename="list.csv" />);
    act(() => show());
    await waitFor(() => expect(screen.getByText('quote, kept')).toBeInTheDocument());
    expect(screen.getAllByRole('row')).toHaveLength(7);
  });

  it('PDF uses a lazy credentialed first-page image, no iframe or full blob fetch', () => {
    const { container } = renderWithProviders(
      <GeneratedDocumentPreview url={url} docType="pdf" filename="report.pdf" />
    );
    expect(screen.getByRole('img')).toHaveAttribute(
      'src',
      expect.stringContaining(`${url}/preview`)
    );
    expect(screen.getByRole('img')).toHaveAttribute('loading', 'lazy');
    expect(container.querySelector('iframe')).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('a PDF preview can be expanded by keyboard and closed without losing the card', async () => {
    renderWithProviders(<GeneratedDocumentPreview url={url} docType="pdf" filename="report.pdf" />);
    const trigger = screen.getByRole('button', { name: 'chat.document_card.first_page' });
    trigger.focus();
    fireEvent.click(trigger);
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('does not fetch external or unsupported file sources', () => {
    renderWithProviders(
      <GeneratedDocumentPreview url="https://evil.test/file" docType="txt" filename="notes" />
    );
    renderWithProviders(<GeneratedDocumentPreview url={url} docType="zip" filename="report.zip" />);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('rejects a source URL under an external host even when it contains an attachment UUID', () => {
    const view = renderWithProviders(
      <GeneratedDocumentPreview url={`https://evil.test${url}`} docType="pdf" filename="file" />
    );
    expect(view.container.querySelector('img')).toBeNull();
  });

  it('rejects an oversized preview stream and cancels its reader', async () => {
    const cancel = vi.fn();
    fetchMock.mockResolvedValue(
      new Response(
        new ReadableStream<Uint8Array>({
          start(controller) {
            controller.enqueue(new Uint8Array(65537));
          },
          cancel,
        })
      )
    );
    renderWithProviders(<GeneratedDocumentPreview url={url} docType="txt" filename="file" />);
    act(() => show());
    await waitFor(() =>
      expect(screen.getByText('chat.document_card.preview_unavailable')).toBeInTheDocument()
    );
    expect(cancel).toHaveBeenCalledTimes(1);
  });

  it('withholds a truncated CSV record', async () => {
    fetchMock.mockResolvedValue(
      new Response('name,value\nreceived,whole\npartial,cut', {
        headers: { 'X-Preview-Truncated': 'true' },
      })
    );
    renderWithProviders(<GeneratedDocumentPreview url={url} docType="csv" filename="file" />);
    act(() => show());
    await waitFor(() => expect(screen.getByText('whole')).toBeInTheDocument());
    expect(screen.queryByText('cut')).toBeNull();
  });

  it('an unreadable preview exposes a fallback without removing the document', async () => {
    fetchMock.mockResolvedValue(new Response('', { status: 404 }));
    renderWithProviders(<GeneratedDocumentPreview url={url} docType="txt" filename="notes.txt" />);
    act(() => show());
    await waitFor(() =>
      expect(screen.getByText('chat.document_card.preview_unavailable')).toBeInTheDocument()
    );
  });

  it('lets the reader retry a failed preview without resending the assistant response', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response('', { status: 503 }))
      .mockResolvedValueOnce(new Response('Recovered source'));
    renderWithProviders(<GeneratedDocumentPreview url={url} docType="txt" filename="notes.txt" />);
    act(() => show());
    await screen.findByText('chat.document_card.preview_unavailable');
    fireEvent.click(screen.getByRole('button', { name: 'common.retry' }));
    act(() => show());
    expect(await screen.findByText('Recovered source')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('abort cleans up an in-flight preview', () => {
    fetchMock.mockReturnValue(new Promise(() => {}));
    const view = renderWithProviders(
      <GeneratedDocumentPreview url={url} docType="txt" filename="notes.txt" />
    );
    act(() => show());
    const signal = fetchMock.mock.calls[0][1].signal;
    view.unmount();
    expect(signal.aborted).toBe(true);
  });

  it('times out a stalled preview with a usable retry and aborts its request', async () => {
    vi.useFakeTimers();
    fetchMock.mockReturnValue(new Promise(() => {}));
    const view = renderWithProviders(
      <GeneratedDocumentPreview url={url} docType="txt" filename="notes.txt" />
    );
    try {
      act(() => show());
      const signal = fetchMock.mock.calls[0][1].signal;
      await act(() => vi.advanceTimersByTimeAsync(10000));
      expect(signal.aborted).toBe(true);
      expect(screen.getByRole('button', { name: 'common.retry' })).toBeInTheDocument();
    } finally {
      view.unmount();
      vi.useRealTimers();
    }
  });

  it('aborts the old source and never lets a late response replace the new excerpt', async () => {
    let completeOld: (response: Response) => void = () => {};
    fetchMock
      .mockImplementationOnce(
        () =>
          new Promise<Response>(resolve => {
            completeOld = resolve;
          })
      )
      .mockResolvedValueOnce(new Response('Current source'));
    const view = renderWithProviders(
      <GeneratedDocumentPreview url={url} docType="txt" filename="old.txt" />
    );
    act(() => show());
    const oldSignal = fetchMock.mock.calls[0][1].signal;
    view.rerender(
      <GeneratedDocumentPreview
        url={url.replace('d001', 'd002')}
        docType="txt"
        filename="new.txt"
      />
    );
    expect(oldSignal.aborted).toBe(true);
    act(() => show());
    expect(await screen.findByText('Current source')).toBeInTheDocument();
    await act(async () => completeOld(new Response('Stale source')));
    expect(screen.queryByText('Stale source')).toBeNull();
    expect(screen.getByText('Current source')).toBeInTheDocument();
  });

  it('retains the open PDF dialog and returns focus to retry after a late thumbnail failure', async () => {
    renderWithProviders(<GeneratedDocumentPreview url={url} docType="pdf" filename="report.pdf" />);
    const thumbnail = screen.getByRole('img');
    const trigger = screen.getByRole('button', { name: 'chat.document_card.first_page' });
    trigger.focus();
    fireEvent.click(trigger);
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    fireEvent.error(thumbnail);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    const retry = screen.getByRole('button', { name: 'common.retry' });
    expect(retry).toHaveFocus();
    fireEvent.click(retry);
    expect(screen.getByRole('img')).toHaveAttribute(
      'src',
      expect.stringContaining(`${url}/preview`)
    );
  });
});
