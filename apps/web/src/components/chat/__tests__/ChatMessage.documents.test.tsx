/**
 * GeneratedDocumentCards — the download card grafted under an assistant
 * bubble for each AI-generated document (ADR-226): filename, type + size
 * line, download link (PDF opens in a tab instead — the API serves it
 * inline), expiry notice sharing the image cards' logic, and nothing at all
 * when the message carries no document.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { makeMessage, makeUser } from '@/__tests__/factories';
import { usePsycheStore } from '@/stores/psycheStore';
import type { GeneratedDocument, Message } from '@/types/chat';

const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));

const { mutate, apiMutationOptions } = vi.hoisted(() => ({
  mutate: vi.fn(async () => {}),
  apiMutationOptions: vi.fn(),
}));
vi.mock('@/hooks/useApiMutation', () => ({
  useApiMutation: (options: unknown) => {
    apiMutationOptions(options);
    return { mutate };
  },
}));

const { toast } = vi.hoisted(() => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));
vi.mock('sonner', () => ({ toast }));

import { ChatMessage } from '../ChatMessage';

function renderMessage(message: Message) {
  return renderWithProviders(<ChatMessage message={message} isUser={false} />);
}

const csvDocument: GeneratedDocument = {
  url: '/api/v1/attachments/d1',
  filename: 'modeles-llm.csv',
  doc_type: 'csv',
  size_bytes: 2048,
  expires_at: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  usePsycheStore.getState().reset();
  useAuth.mockReturnValue({ user: makeUser({ tokens_display_enabled: false }) });
});

describe('ChatMessage — generated document cards', () => {
  it('renders filename, type/size line, and a download link to the attachment', () => {
    renderMessage(makeMessage({ generatedDocuments: [csvDocument] }));
    expect(screen.getByText('modeles-llm.csv')).toBeInTheDocument();
    expect(screen.getByText(/CSV/)).toBeInTheDocument();
    const link = screen.getByRole('link', { name: 'chat.document_card.download' });
    expect(link).toHaveAttribute('href', '/api/v1/attachments/d1');
    expect(link).toHaveAttribute('download', 'modeles-llm.csv');
  });

  it('opens pdf in a new tab instead of forcing a download (inline serving)', () => {
    renderMessage(
      makeMessage({
        generatedDocuments: [
          { ...csvDocument, filename: 'rapport.pdf', doc_type: 'pdf' },
        ],
      })
    );
    const link = screen.getByRole('link', { name: 'chat.document_card.open' });
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).not.toHaveAttribute('download');
  });

  it('renders one card per document', () => {
    renderMessage(
      makeMessage({
        generatedDocuments: [
          csvDocument,
          { ...csvDocument, filename: 'annexe.docx', doc_type: 'docx' },
        ],
      })
    );
    expect(screen.getAllByTestId('generated-document-card')).toHaveLength(2);
  });

  it('shows the document expiry notice when a deadline is known', () => {
    const inTwoHours = new Date(Date.now() + 2 * 3600 * 1000).toISOString();
    renderMessage(
      makeMessage({ generatedDocuments: [{ ...csvDocument, expires_at: inTwoHours }] })
    );
    // Same classification logic as image cards; "soon" copy is generic.
    expect(screen.getByText(/chat\.image_expiry\.soon/)).toBeInTheDocument();
  });

  it('renders nothing without documents', () => {
    renderMessage(makeMessage({}));
    expect(screen.queryByTestId('generated-document-card')).not.toBeInTheDocument();
  });
});
