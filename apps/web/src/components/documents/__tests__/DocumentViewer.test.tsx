/**
 * DocumentViewer — the HTML page a generated-document card opens (ADR-226
 * amendment 2026-08-18): fetches the attachment with credentials and renders
 * it by type — csv as a real table, markdown through the sanitized pipeline,
 * txt as preformatted text; office formats get an honest file panel with a
 * download action; a failed fetch reports instead of spinning forever.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

vi.mock('@/components/chat/MarkdownContent', () => ({
  MarkdownContent: ({ content }: { content: string }) => (
    <div data-testid="markdown">{content}</div>
  ),
}));

import { DocumentViewer } from '../DocumentViewer';

function mockFetchBlob(body: string | Blob, ok = true) {
  const blob = typeof body === 'string' ? new Blob([body]) : body;
  const fetchMock = vi.fn(async () => ({
    ok,
    status: ok ? 200 : 404,
    blob: async () => blob,
  }));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

beforeEach(() => {
  vi.stubGlobal('URL', {
    ...URL,
    createObjectURL: vi.fn(() => 'blob:mock'),
    revokeObjectURL: vi.fn(),
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('DocumentViewer — renderable types', () => {
  it('renders a csv as a table (headers + rows)', async () => {
    const fetchMock = mockFetchBlob('modèle,prix\n"Fable 5","20,00"');
    renderWithProviders(
      <DocumentViewer attachmentId="d1" filename="modeles.csv" docType="csv" />
    );
    expect(await screen.findByRole('table')).toBeInTheDocument();
    expect(screen.getByText('modèle')).toBeInTheDocument();
    expect(screen.getByText('20,00')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/attachments/d1',
      expect.objectContaining({ credentials: 'include' })
    );
  });

  it('renders markdown through the sanitized pipeline', async () => {
    mockFetchBlob('# Titre\n\ncorps');
    renderWithProviders(
      <DocumentViewer attachmentId="d2" filename="rapport.md" docType="md" />
    );
    expect(await screen.findByTestId('markdown')).toHaveTextContent('Titre');
  });

  it('renders txt as preformatted text', async () => {
    mockFetchBlob('ligne 1\nligne 2');
    renderWithProviders(
      <DocumentViewer attachmentId="d3" filename="notes.txt" docType="txt" />
    );
    await waitFor(() => expect(screen.getByText(/ligne 1/)).toBeInTheDocument());
  });
});

describe('DocumentViewer — non-renderable types and errors', () => {
  it('offers an honest file panel with a download action for xlsx', async () => {
    mockFetchBlob(new Blob(['x']));
    renderWithProviders(
      <DocumentViewer attachmentId="d4" filename="data.xlsx" docType="xlsx" />
    );
    expect(await screen.findByText('documents.viewer.not_renderable')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'documents.viewer.download' })).toBeInTheDocument();
  });

  it('reports a fetch failure instead of spinning forever', async () => {
    mockFetchBlob('', false);
    renderWithProviders(
      <DocumentViewer attachmentId="d5" filename="gone.csv" docType="csv" />
    );
    expect(await screen.findByText('documents.viewer.error')).toBeInTheDocument();
  });

  it('always shows the filename as the page heading', async () => {
    mockFetchBlob('a,b\n1,2');
    renderWithProviders(
      <DocumentViewer attachmentId="d6" filename="modeles.csv" docType="csv" />
    );
    expect(
      await screen.findByRole('heading', { name: 'modeles.csv' })
    ).toBeInTheDocument();
  });
});
