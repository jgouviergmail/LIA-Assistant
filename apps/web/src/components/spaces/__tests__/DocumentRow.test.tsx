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
    error_code: null,
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
  it('explains a coded failure in the person\'s language, remedy included', () => {
    render({
      document: document({
        status: 'error',
        error_code: 'scanned_pdf_no_text_layer',
        error_message: 'No text content extracted',
      }),
    });
    const row = screen.getByRole('listitem', { name: 'report.pdf' });
    expect(
      within(row).getByText('spaces.documents.errors.scanned_pdf_no_text_layer')
    ).toBeInTheDocument();
    // The sentence names the cause AND the remedy — the Google Drive route,
    // which recognises the text of a scan on the way to a Google Doc.
    expect(en.spaces.documents.errors.scanned_pdf_no_text_layer).toBe(
      'This PDF is a scanned document with no text layer, and character recognition is not available here. To index it, put it on Google Drive, open it with Google Docs (the text is recognised automatically), then add that Google Doc to the space through its Drive source.'
    );
    expect(fr.spaces.documents.errors.scanned_pdf_no_text_layer).toBe(
      'Ce PDF est un document scanné sans couche texte, et la reconnaissance de caractères n\'est pas disponible ici. Pour l\'indexer, déposez-le sur Google Drive, ouvrez-le avec Google Docs (le texte est reconnu automatiquement), puis ajoutez ce Google Doc à l\'espace via sa source Drive.'
    );
  });

  it('keeps a failure without a code as the badge title alone', () => {
    render({
      document: document({
        status: 'error',
        error_code: null,
        error_message: 'Text extraction failed: boom',
      }),
    });
    const row = screen.getByRole('listitem', { name: 'report.pdf' });
    expect(within(row).getByTitle('Text extraction failed: boom')).toBeInTheDocument();
    expect(within(row).queryByText(/^spaces\.documents\.errors\./)).not.toBeInTheDocument();
  });

  it('falls back to the message when the code is unknown to this build', () => {
    render({
      document: document({
        status: 'error',
        error_code: 'a_code_from_a_newer_server',
        error_message: 'Something new',
      }),
    });
    const row = screen.getByRole('listitem', { name: 'report.pdf' });
    expect(within(row).getByTitle('Something new')).toBeInTheDocument();
    expect(within(row).queryByText(/^spaces\.documents\.errors\./)).not.toBeInTheDocument();
  });

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

  it('offers neither move nor delete on a kept answer, and says what it is', () => {
    // The bookmark is the record; its projection goes with the bookmark.
    render({ document: document({ source_type: 'bookmark', original_filename: 'Kept.md' }) });
    const row = screen.getByRole('listitem', { name: 'Kept.md' });
    expect(within(row).getByText('spaces.bookmarks.source_type_bookmark')).toBeInTheDocument();
    expect(
      within(row).queryByRole('button', { name: 'spaces.documents.move' })
    ).not.toBeInTheDocument();
    expect(within(row).queryByRole('button', { name: 'common.delete' })).not.toBeInTheDocument();
    expect(
      within(row).getByRole('link', { name: 'spaces.documents.download' })
    ).toBeInTheDocument();
  });

  it('names the kept-answer badge and the skip reasons in English and in French', () => {
    expect(en.spaces.bookmarks.source_type_bookmark).toBe('Kept answer');
    expect(fr.spaces.bookmarks.source_type_bookmark).toBe('Réponse conservée');
    expect(en.spaces.documents.skip.document_managed_by_bookmarks).toBe('a kept answer');
    expect(fr.spaces.documents.skip.document_managed_by_bookmarks).toBe('une réponse conservée');
    expect(en.spaces.documents.skip.document_managed_by_mail).toBe(
      'kept in sync from a Gmail label'
    );
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
