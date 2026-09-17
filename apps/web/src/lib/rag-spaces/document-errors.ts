/**
 * Why a document of a knowledge space could not be indexed — the frontend
 * mirror of the backend's `RAGDocumentErrorCode` (a backend guard holds the
 * two lists equal). A code the build does not know renders nothing: the row
 * then keeps the technical message as the badge title, as before.
 */
import type { RAGDocument } from '@/types/rag-spaces';

export const RAG_DOCUMENT_ERROR_CODES = [
  'file_missing',
  'extraction_failed',
  'scanned_pdf_no_text_layer',
  'no_text_content',
  'no_chunks',
  'too_many_chunks',
  'retries_exhausted',
] as const;

export type RagDocumentErrorCode = (typeof RAG_DOCUMENT_ERROR_CODES)[number];

export function isRagDocumentErrorCode(value: string | null | undefined): value is RagDocumentErrorCode {
  return value != null && (RAG_DOCUMENT_ERROR_CODES as readonly string[]).includes(value);
}

/**
 * The translation key of the sentence explaining a failed document, or null
 * when the document is not in error or its code is unknown to this build.
 */
export function documentFailureKey(
  document: Pick<RAGDocument, 'status' | 'error_code'>
): `spaces.documents.errors.${RagDocumentErrorCode}` | null {
  if (document.status !== 'error' || !isRagDocumentErrorCode(document.error_code)) {
    return null;
  }
  return `spaces.documents.errors.${document.error_code}`;
}
