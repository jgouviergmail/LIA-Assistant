'use client';

import { useApplicationFileUpload, type FileUploadDefinition } from '@/hooks/useApplicationFileUpload';
import { documentUploadResultSchema, documentUploadSelectionSchema, type DocumentUploadSelection } from '@/lib/application-document-upload';
import type { ApplicationCommandStatus } from '@/types/application-commands';

const definition: FileUploadDefinition<DocumentUploadSelection> = {
  operationId: 'knowledge_document.upload', resource: 'spaces',
  select(status) {
    const parsed = documentUploadSelectionSchema.safeParse(
      status.outcome?.values.document_to_upload ?? status.prior_outcome?.values.document_to_upload
    );
    return parsed.success ? parsed.data : null;
  },
  // Keep the bounded same-origin RAG proxy for large multipart uploads and dev TLS.
  endpoint: (commandId, selection) => `/api/rag-upload/${selection.space.id}?application_command=${commandId}`,
  accept(value, commandId, selection) {
    const result = documentUploadResultSchema.safeParse(value);
    return result.success && result.data.values.document_id === commandId &&
      result.data.values.space_id === selection.space.id ? { cacheRefreshPending: false } : null;
  },
};

export function useApplicationDocumentUpload(status: ApplicationCommandStatus, checkResult: () => Promise<void>) {
  return useApplicationFileUpload(status, checkResult, definition);
}
