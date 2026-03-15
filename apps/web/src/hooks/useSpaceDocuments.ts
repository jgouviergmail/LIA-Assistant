/**
 * Hook for RAG Space document management (upload, delete, status polling).
 *
 * Upload uses XHR for progress tracking (pattern from useFileUpload).
 * Status polling uses setInterval + refetch for processing documents.
 *
 * Phase: evolution — RAG Spaces (User Knowledge Documents)
 * Created: 2026-03-14
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useApiMutation } from './useApiMutation';
import type { RAGDocument } from '@/types/rag-spaces';

/** Upload progress state for a single file. */
export interface DocumentUploadState {
  tempId: string;
  filename: string;
  progress: number;
  status: 'uploading' | 'done' | 'error';
  error?: string;
}

/** XHR timeout for uploads in milliseconds (2 minutes). */
const UPLOAD_TIMEOUT_MS = 120_000;

/** Polling interval for document processing status (5 seconds). */
const STATUS_POLL_INTERVAL_MS = 5_000;

interface UseSpaceDocumentsOptions {
  spaceId: string;
  documents: RAGDocument[];
  onDocumentReady?: () => void;
}

/**
 * Hook for uploading/deleting documents and polling processing status.
 */
export function useSpaceDocuments({ spaceId, documents, onDocumentReady }: UseSpaceDocumentsOptions) {
  const [uploads, setUploads] = useState<DocumentUploadState[]>([]);
  const xhrRefs = useRef<Map<string, XMLHttpRequest>>(new Map());
  const onDocumentReadyRef = useRef(onDocumentReady);
  useEffect(() => {
    onDocumentReadyRef.current = onDocumentReady;
  }, [onDocumentReady]);

  const isUploading = uploads.some((u) => u.status === 'uploading');

  // Cleanup XHRs on unmount
  useEffect(() => {
    const xhrMap = xhrRefs.current;
    return () => {
      xhrMap.forEach((xhr) => xhr.abort());
      xhrMap.clear();
    };
  }, []);

  // Poll processing status for documents in "processing" state
  const processingDocs = documents.filter((d) => d.status === 'processing');

  useEffect(() => {
    if (processingDocs.length === 0) return;

    const interval = setInterval(() => {
      onDocumentReadyRef.current?.();
    }, STATUS_POLL_INTERVAL_MS);

    return () => clearInterval(interval);
  }, [processingDocs.length]);

  // Upload a file via XHR
  const uploadDocument = useCallback(
    async (file: File): Promise<{ success?: boolean; error?: string }> => {
      const tempId = crypto.randomUUID();

      setUploads((prev) => [
        ...prev,
        { tempId, filename: file.name, progress: 0, status: 'uploading' },
      ]);

      try {
        const formData = new FormData();
        formData.append('file', file);

        await new Promise<RAGDocument>((resolve, reject) => {
          const xhr = new XMLHttpRequest();
          xhrRefs.current.set(tempId, xhr);

          xhr.timeout = UPLOAD_TIMEOUT_MS;

          xhr.upload.onprogress = (e) => {
            if (e.lengthComputable) {
              const progress = Math.round((e.loaded / e.total) * 100);
              setUploads((prev) =>
                prev.map((u) => (u.tempId === tempId ? { ...u, progress } : u))
              );
            }
          };

          xhr.onload = () => {
            xhrRefs.current.delete(tempId);
            if (xhr.status === 201 || xhr.status === 200) {
              try {
                resolve(JSON.parse(xhr.responseText));
              } catch {
                reject(new Error('Invalid response'));
              }
            } else {
              let message = `Upload failed: ${xhr.status}`;
              try {
                const errorData = JSON.parse(xhr.responseText);
                message = errorData.detail || message;
              } catch {
                // Use default message
              }
              reject(new Error(message));
            }
          };

          xhr.onerror = () => {
            xhrRefs.current.delete(tempId);
            reject(new Error('Network error'));
          };

          xhr.ontimeout = () => {
            xhrRefs.current.delete(tempId);
            reject(new Error('Upload timeout'));
          };

          xhr.onabort = () => {
            xhrRefs.current.delete(tempId);
            reject(new Error('Upload aborted'));
          };

          // Use dedicated API route handler for uploads to bypass Next.js rewrite proxy
          // (rewrite proxy fails with large multipart bodies + self-signed certs in dev)
          xhr.open('POST', `/api/rag-upload/${spaceId}`);
          xhr.withCredentials = true;
          xhr.send(formData);
        });

        setUploads((prev) =>
          prev.map((u) =>
            u.tempId === tempId ? { ...u, status: 'done' as const, progress: 100 } : u
          )
        );

        // Trigger refetch to get updated document list
        onDocumentReadyRef.current?.();

        return { success: true };
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : String(err);
        setUploads((prev) =>
          prev.map((u) =>
            u.tempId === tempId
              ? { ...u, status: 'error' as const, error: errorMessage }
              : u
          )
        );
        return { error: errorMessage };
      }
    },
    [spaceId]
  );

  // Delete a document
  const deleteMutation = useApiMutation<void, void>({
    method: 'DELETE',
    componentName: 'SpaceDocuments',
  });

  const deleteDocument = useCallback(
    async (documentId: string) => {
      await deleteMutation.mutate(`/rag-spaces/${spaceId}/documents/${documentId}`);
      onDocumentReadyRef.current?.();
    },
    [spaceId, deleteMutation]
  );

  // Remove an upload entry from the list
  const dismissUpload = useCallback((tempId: string) => {
    const xhr = xhrRefs.current.get(tempId);
    if (xhr) {
      xhr.abort();
      xhrRefs.current.delete(tempId);
    }
    setUploads((prev) => prev.filter((u) => u.tempId !== tempId));
  }, []);

  const clearCompletedUploads = useCallback(() => {
    setUploads((prev) => prev.filter((u) => u.status === 'uploading'));
  }, []);

  return {
    uploads,
    isUploading,
    uploadDocument,
    deleteDocument,
    dismissUpload,
    clearCompletedUploads,
    deleting: deleteMutation.loading,
  };
}
