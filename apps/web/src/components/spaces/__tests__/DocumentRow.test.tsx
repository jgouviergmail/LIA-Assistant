/**
 * A document row (ADR-259): a named checkbox, and its actions ONE way
 * (ADR-208) — download as a link, move (uploads only), delete red at rest.
 * Names are asserted by key in the global stub and in English and French
 * through the real locales, as the frontend contract requires.
 */

import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, within } from '@/__tests__/test-utils';
import en from '@/../locales/en/translation.json';
import fr from '@/../locales/fr/translation.json';
import type { RAGDocument } from '@/types/rag-spaces';

import { DocumentRow } from '../DocumentRow';

function document(over: Partial<RAGDocument> = {}): RAGDocument {
  return {
    id: 'd1',
    original_filename: 'report.pdf',
    file_size: 2048,
    content_type: 'application/pdf',
    status: 'ready',
    error_message: null,
    chunk_count: 3,
    embedding_model: 'm',
    embedding_tokens: 0,
    embedding_cost_eur: 0,
    source_type: 'upload',
    drive_file_id: null,
    created_at: '2026-09-02T10:00:00Z',
    ...over,
  };
}

function render(over: Partial<React.ComponentProps<typeof DocumentRow>> = {}) {
  const handlers = { onToggle: vi.fn(), onDelete: vi.fn(), onMove: vi.fn() };
  const utils = renderWithProviders(
    <DocumentRow
      document={document()}
      selected={false}
      downloadHref="https://api.test/rag-spaces/s1/documents/d1/download"
      deleting={false}
      {...handlers}
      {...over}
    />
  );
  return { ...utils, ...handlers };
}

describe('DocumentRow', () => {
  it('offers a named checkbox that toggles the selection', async () => {
    const { user, onToggle } = render();
    const box = screen.getByRole('checkbox', { name: 'spaces.documents.select_row' });
    expect(box).not.toBeChecked();
    await user.click(box);
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it('downloads through a link, moves and deletes through named actions', async () => {
    const { user, onMove, onDelete } = render();
    const row = screen.getByRole('listitem', { name: 'report.pdf' });
    expect(within(row).getByRole('link', { name: 'spaces.documents.download' })).toHaveAttribute(
      'href',
      'https://api.test/rag-spaces/s1/documents/d1/download'
    );
    await user.click(within(row).getByRole('button', { name: 'spaces.documents.move' }));
    expect(onMove).toHaveBeenCalledWith('d1');
    await user.click(within(row).getByRole('button', { name: 'common.delete' }));
    expect(onDelete).toHaveBeenCalledWith('d1');
  });

  it('offers no move on a row another system manages', () => {
    render({ document: document({ source_type: 'drive', drive_file_id: 'f1' }) });
    expect(screen.queryByRole('button', { name: 'spaces.documents.move' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'spaces.documents.download' })).toBeInTheDocument();
  });

  it('names its actions in English and in French', () => {
    const enDocs = en.spaces.documents;
    const frDocs = fr.spaces.documents;
    expect(enDocs.download).toBe('Download');
    expect(frDocs.download).toBe('Télécharger');
    expect(enDocs.move).toBe('Move to another space…');
    expect(frDocs.move).toBe('Déplacer vers un autre espace…');
    expect(enDocs.row_actions).toContain('{{name}}');
    expect(frDocs.row_actions).toContain('{{name}}');
  });
});
