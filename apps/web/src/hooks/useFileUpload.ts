/**
 * Hook for file upload with progress tracking.
 *
 * Handles:
 * - Client-side validation (size, type) for both images and documents
 * - Image compression before upload
 * - Upload via XMLHttpRequest (progress tracking)
 * - State management for pending attachments
 * - Object URL cleanup on unmount
 *
 * Phase: evolution F4 — File Attachments & Vision Analysis
 * Created: 2026-03-09
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { API_ENDPOINTS } from '@/lib/api-config';
import { compressImage, isImageFile } from '@/lib/utils/image-compress';

export interface PendingAttachment {
  /** Client-side temporary ID */
  tempId: string;
  /** Server-side attachment ID (set after upload completes) */
  attachmentId?: string;
  /** Original filename */
  filename: string;
  /** File MIME type */
  mimeType: string;
  /** File size in bytes (after compression) */
  size: number;
  /** Content category */
  contentType: 'image' | 'document';
  /** Upload status */
  status: 'uploading' | 'ready' | 'error';
  /** Upload progress 0-100 */
  progress: number;
  /** Error message if status === 'error' */
  error?: string;
  /** Object URL for image preview (revoked on cleanup) */
  previewUrl?: string;
}

interface UseFileUploadOptions {
  maxImageSizeMB?: number;
  maxDocSizeMB?: number;
  maxAttachments?: number;
  allowedImageTypes?: string[];
  allowedDocTypes?: string[];
}

const DEFAULT_OPTIONS: Required<UseFileUploadOptions> = {
  maxImageSizeMB: 10,
  maxDocSizeMB: 20,
  maxAttachments: 5,
  allowedImageTypes: ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/heic', 'image/heif'],
  allowedDocTypes: ['application/pdf'],
};

/** XHR timeout for uploads in milliseconds (2 minutes) */
const UPLOAD_TIMEOUT_MS = 120_000;

export function useFileUpload(options?: UseFileUploadOptions) {
  // M1: Memoize opts to prevent uploadFile callback recreation every render
  // Destructure to stable primitives — avoids stale closure on the `options` object ref
  const maxImageSizeMB = options?.maxImageSizeMB;
  const maxDocSizeMB = options?.maxDocSizeMB;
  const maxAttachments = options?.maxAttachments;
  const allowedImageTypes = options?.allowedImageTypes;
  const allowedDocTypes = options?.allowedDocTypes;
  const opts = useMemo(
    () => ({
      ...DEFAULT_OPTIONS,
      ...(maxImageSizeMB !== undefined && { maxImageSizeMB }),
      ...(maxDocSizeMB !== undefined && { maxDocSizeMB }),
      ...(maxAttachments !== undefined && { maxAttachments }),
      ...(allowedImageTypes !== undefined && { allowedImageTypes }),
      ...(allowedDocTypes !== undefined && { allowedDocTypes }),
    }),
    [maxImageSizeMB, maxDocSizeMB, maxAttachments, allowedImageTypes, allowedDocTypes]
  );

  const [attachments, setAttachments] = useState<PendingAttachment[]>([]);
  const xhrRefs = useRef<Map<string, XMLHttpRequest>>(new Map());
  // H2: Use ref to track count for concurrent upload validation (avoids stale closure)
  const attachmentCountRef = useRef(0);
  // L4: Ref to track current attachments for cleanup on unmount (avoids stale closure)
  const attachmentsRef = useRef<PendingAttachment[]>([]);

  // Keep refs in sync with state
  useEffect(() => {
    attachmentCountRef.current = attachments.length;
    attachmentsRef.current = attachments;
  }, [attachments]);

  // L4: Cleanup Object URLs and abort XHRs on unmount to prevent memory leaks
  useEffect(() => {
    const xhrMap = xhrRefs.current;
    const attRef = attachmentsRef;
    return () => {
      xhrMap.forEach((xhr) => xhr.abort());
      xhrMap.clear();
      // Revoke all preview Object URLs to prevent memory leaks
      attRef.current.forEach((a) => {
        if (a.previewUrl) URL.revokeObjectURL(a.previewUrl);
      });
    };
  }, []);

  const isUploading = attachments.some((a) => a.status === 'uploading');

  const uploadFile = useCallback(
    async (file: File) => {
      // H2: Use ref for concurrent-safe count check
      if (attachmentCountRef.current >= opts.maxAttachments) {
        return { error: 'max_attachments' as const };
      }

      const isImage = isImageFile(file);
      const contentType = isImage ? 'image' : 'document';

      // H1: Validate MIME type for BOTH images and documents
      const allowedTypes = isImage ? opts.allowedImageTypes : opts.allowedDocTypes;
      if (!allowedTypes.includes(file.type)) {
        // Browser may not report HEIC correctly — allow if it starts with image/
        if (isImage && file.type.startsWith('image/')) {
          // Accept unknown image subtypes (HEIC quirk)
        } else {
          return { error: 'type_not_allowed' as const };
        }
      }

      // Validate size
      const maxBytes = (isImage ? opts.maxImageSizeMB : opts.maxDocSizeMB) * 1024 * 1024;
      if (file.size > maxBytes) {
        return { error: 'file_too_large' as const };
      }

      const tempId = crypto.randomUUID();
      const previewUrl = isImage ? URL.createObjectURL(file) : undefined;

      // Add to state as uploading
      const pending: PendingAttachment = {
        tempId,
        filename: file.name,
        mimeType: file.type || 'application/octet-stream',
        size: file.size,
        contentType,
        status: 'uploading',
        progress: 0,
        previewUrl,
      };
      // H2: Increment ref immediately (before async work) to prevent concurrent overflow
      attachmentCountRef.current += 1;
      setAttachments((prev) => [...prev, pending]);

      try {
        // Compress images client-side
        let uploadBlob: Blob = file;
        if (isImage) {
          const compressed = await compressImage(file);
          uploadBlob = compressed.blob;
          // Update size to reflect actual compressed size (displayed in metadata)
          if (uploadBlob.size !== file.size) {
            setAttachments((prev) =>
              prev.map((a) => (a.tempId === tempId ? { ...a, size: uploadBlob.size } : a))
            );
          }
        }

        // Upload via XHR for progress tracking
        const formData = new FormData();
        formData.append('file', uploadBlob, file.name);

        const result = await new Promise<{ id: string }>((resolve, reject) => {
          const xhr = new XMLHttpRequest();
          xhrRefs.current.set(tempId, xhr);

          // L5: Set timeout to prevent hanging uploads
          xhr.timeout = UPLOAD_TIMEOUT_MS;

          xhr.upload.onprogress = (e) => {
            if (e.lengthComputable) {
              const progress = Math.round((e.loaded / e.total) * 100);
              setAttachments((prev) =>
                prev.map((a) => (a.tempId === tempId ? { ...a, progress } : a))
              );
            }
          };

          xhr.onload = () => {
            xhrRefs.current.delete(tempId);
            if (xhr.status === 201) {
              try {
                const data = JSON.parse(xhr.responseText);
                resolve({ id: data.id });
              } catch {
                reject(new Error('Invalid response'));
              }
            } else {
              reject(new Error(`Upload failed: ${xhr.status}`));
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

          xhr.open('POST', API_ENDPOINTS.ATTACHMENTS.UPLOAD);
          xhr.withCredentials = true;
          xhr.send(formData);
        });

        // Mark as ready
        setAttachments((prev) =>
          prev.map((a) =>
            a.tempId === tempId
              ? { ...a, status: 'ready' as const, progress: 100, attachmentId: result.id }
              : a
          )
        );

        return { success: true as const };
      } catch (err) {
        // Mark as error
        setAttachments((prev) =>
          prev.map((a) =>
            a.tempId === tempId
              ? { ...a, status: 'error' as const, error: (err as Error).message }
              : a
          )
        );
        return { error: 'upload_failed' as const };
      }
    },
    [opts]
  );

  const removeFile = useCallback((tempId: string) => {
    // Cancel in-progress upload
    const xhr = xhrRefs.current.get(tempId);
    if (xhr) {
      xhr.abort();
      xhrRefs.current.delete(tempId);
    }

    setAttachments((prev) => {
      const attachment = prev.find((a) => a.tempId === tempId);
      if (attachment?.previewUrl) {
        URL.revokeObjectURL(attachment.previewUrl);
      }
      return prev.filter((a) => a.tempId !== tempId);
    });
  }, []);

  const clearAttachments = useCallback(() => {
    // Cancel all uploads
    xhrRefs.current.forEach((xhr) => xhr.abort());
    xhrRefs.current.clear();

    // Revoke preview URLs using functional update (avoids stale closure)
    setAttachments((prev) => {
      prev.forEach((a) => {
        if (a.previewUrl) URL.revokeObjectURL(a.previewUrl);
      });
      return [];
    });
  }, []);

  /** Get attachment IDs that are ready for sending */
  const getReadyAttachmentIds = useCallback((): string[] => {
    return attachments
      .filter((a) => a.status === 'ready' && a.attachmentId)
      .map((a) => a.attachmentId!);
  }, [attachments]);

  return {
    attachments,
    uploadFile,
    removeFile,
    clearAttachments,
    getReadyAttachmentIds,
    isUploading,
  };
}
