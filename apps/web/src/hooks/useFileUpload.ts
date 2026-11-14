/**
 * Hook for file upload with progress tracking.
 *
 * Handles:
 * - Client-side validation for both images and documents: the size, and the
 *   format as the instance publishes it (`lib/attachment-formats`, the reading
 *   the picker, the drop and the paste share)
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
import { isAcceptedFile, type AttachmentFormats } from '@/lib/attachment-formats';
import { compressImage, isImageFile } from '@/lib/utils/image-compress';
import { generateUUID } from '@/lib/utils';

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

/** What the server says about an attachment it already holds. */
export interface ServerAttachmentMeta {
  id: string;
  filename: string;
  mimeType: string;
  size: number;
  contentType: 'image' | 'document';
}

export type AddServerAttachmentOutcome =
  | { ok: true }
  | { error: 'max_attachments'; max: number }
  | { error: 'already_attached' };

interface UseFileUploadOptions {
  maxImageSizeMB?: number;
  maxDocSizeMB?: number;
  maxAttachments?: number;
}

const DEFAULT_OPTIONS: Required<UseFileUploadOptions> = {
  maxImageSizeMB: 10,
  maxDocSizeMB: 20,
  maxAttachments: 5,
};

/** XHR timeout for uploads in milliseconds (2 minutes) */
const UPLOAD_TIMEOUT_MS = 120_000;

function attachmentRejection(
  file: File,
  isImage: boolean,
  options: Required<UseFileUploadOptions>,
  formats: AttachmentFormats | undefined
) {
  // Any image subtype passes (some browsers report HEIC as another one); a
  // document is read by its name, a browser's type for it being no evidence.
  if (!isAcceptedFile(file, formats)) return { error: 'type_not_allowed' as const };
  const maxMB = isImage ? options.maxImageSizeMB : options.maxDocSizeMB;
  return file.size > maxMB * 1024 * 1024 ? { error: 'file_too_large' as const, maxMB } : null;
}

export function useFileUpload(options?: UseFileUploadOptions) {
  // M1: Memoize opts to prevent uploadFile callback recreation every render
  // Destructure to stable primitives — avoids stale closure on the `options` object ref
  const maxImageSizeMB = options?.maxImageSizeMB;
  const maxDocSizeMB = options?.maxDocSizeMB;
  const maxAttachments = options?.maxAttachments;
  const opts = useMemo(
    () => ({
      ...DEFAULT_OPTIONS,
      ...(maxImageSizeMB !== undefined && { maxImageSizeMB }),
      ...(maxDocSizeMB !== undefined && { maxDocSizeMB }),
      ...(maxAttachments !== undefined && { maxAttachments }),
    }),
    [maxImageSizeMB, maxDocSizeMB, maxAttachments]
  );

  const [attachments, setAttachments] = useState<PendingAttachment[]>([]);
  const xhrRefs = useRef<Map<string, XMLHttpRequest>>(new Map());
  const preparing = useRef(new Set<string>());
  const mounted = useRef(false);
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
    const preparation = preparing.current;
    mounted.current = true;
    return () => {
      mounted.current = false;
      preparation.clear();
      xhrMap.forEach(xhr => xhr.abort());
      xhrMap.clear();
      // Revoke all preview Object URLs to prevent memory leaks
      attRef.current.forEach(a => {
        if (a.previewUrl) URL.revokeObjectURL(a.previewUrl);
      });
    };
  }, []);

  const isUploading = attachments.some(a => a.status === 'uploading');

  /**
   * Uploads one file. `formats` is what the instance publishes as its upload
   * formats (`/config`); left out, the door keeps to what an older API takes.
   * The composer that drew the picker hands it over, because this hook belongs
   * to the discussion and outlives any one composer.
   */
  const uploadFile = useCallback(
    async (file: File, formats?: AttachmentFormats) => {
      if (!mounted.current) return { error: 'upload_cancelled' as const };
      // H2: Use ref for concurrent-safe count check
      if (attachmentCountRef.current >= opts.maxAttachments) {
        return { error: 'max_attachments' as const, max: opts.maxAttachments };
      }

      const isImage = isImageFile(file);
      const rejection = attachmentRejection(file, isImage, opts, formats);
      if (rejection) return rejection;

      const tempId = generateUUID();
      const previewUrl = isImage ? URL.createObjectURL(file) : undefined;

      // Add to state as uploading
      const pending: PendingAttachment = {
        tempId,
        filename: file.name,
        mimeType: file.type || 'application/octet-stream',
        size: file.size,
        contentType: isImage ? 'image' : 'document',
        status: 'uploading',
        progress: 0,
        previewUrl,
      };
      // H2: Increment ref immediately (before async work) to prevent concurrent overflow
      attachmentCountRef.current += 1;
      setAttachments(prev => [...prev, pending]);

      try {
        // Compress images client-side
        let uploadBlob: Blob = file;
        if (isImage) {
          preparing.current.add(tempId);
          const compressed = await compressImage(file).catch(error => {
            if (preparing.current.has(tempId)) throw error;
            return null;
          });
          // Claim the still-owned preparation before starting any network I/O.
          if (!preparing.current.delete(tempId) || !compressed)
            return { error: 'upload_cancelled' as const };
          uploadBlob = compressed.blob;
          // Update size to reflect actual compressed size (displayed in metadata)
          if (uploadBlob.size !== file.size) {
            setAttachments(prev =>
              prev.map(a => (a.tempId === tempId ? { ...a, size: uploadBlob.size } : a))
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

          xhr.upload.onprogress = e => {
            if (e.lengthComputable) {
              const progress = Math.round((e.loaded / e.total) * 100);
              setAttachments(prev => prev.map(a => (a.tempId === tempId ? { ...a, progress } : a)));
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

          xhr.onabort = () => {
            xhrRefs.current.delete(tempId);
            reject(new DOMException('Upload cancelled', 'AbortError'));
          };

          xhr.open('POST', API_ENDPOINTS.ATTACHMENTS.UPLOAD);
          xhr.withCredentials = true;
          xhr.send(formData);
        });

        // Mark as ready
        setAttachments(prev =>
          prev.map(a =>
            a.tempId === tempId
              ? { ...a, status: 'ready' as const, progress: 100, attachmentId: result.id }
              : a
          )
        );

        return { success: true as const };
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') {
          return { error: 'upload_cancelled' as const };
        }
        // Mark as error
        setAttachments(prev =>
          prev.map(a =>
            a.tempId === tempId
              ? { ...a, status: 'error' as const, error: (err as Error).message }
              : a
          )
        );
        return { error: 'upload_failed' as const };
      } finally {
        preparing.current.delete(tempId);
      }
    },
    [opts]
  );

  const removeFile = useCallback((tempId: string) => {
    preparing.current.delete(tempId);
    // Cancel in-progress upload
    const xhr = xhrRefs.current.get(tempId);
    if (xhr) {
      xhr.abort();
      xhrRefs.current.delete(tempId);
    }

    setAttachments(prev => {
      const attachment = prev.find(a => a.tempId === tempId);
      if (attachment?.previewUrl) {
        URL.revokeObjectURL(attachment.previewUrl);
      }
      return prev.filter(a => a.tempId !== tempId);
    });
  }, []);

  const clearAttachments = useCallback(() => {
    preparing.current.clear();
    // Cancel all uploads
    xhrRefs.current.forEach(xhr => xhr.abort());
    xhrRefs.current.clear();

    // Revoke preview URLs using functional update (avoids stale closure)
    setAttachments(prev => {
      prev.forEach(a => {
        if (a.previewUrl) URL.revokeObjectURL(a.previewUrl);
      });
      return [];
    });
  }, []);

  /**
   * Add an attachment the server ALREADY holds — a copy of a knowledge-space
   * document the person picked. No upload: it joins the strip ready, with its
   * id, under the same per-message cap as an upload, and is sent like one.
   */
  const addServerAttachment = useCallback(
    (meta: ServerAttachmentMeta): AddServerAttachmentOutcome => {
      if (attachmentsRef.current.some(a => a.attachmentId === meta.id)) {
        return { error: 'already_attached' as const };
      }
      if (attachmentCountRef.current >= opts.maxAttachments) {
        return { error: 'max_attachments' as const, max: opts.maxAttachments };
      }
      attachmentCountRef.current += 1;
      const pending: PendingAttachment = {
        tempId: `server-${meta.id}`,
        attachmentId: meta.id,
        filename: meta.filename,
        mimeType: meta.mimeType,
        size: meta.size,
        contentType: meta.contentType,
        status: 'ready',
        progress: 100,
      };
      attachmentsRef.current = [...attachmentsRef.current, pending];
      setAttachments(prev => [...prev, pending]);
      return { ok: true as const };
    },
    [opts.maxAttachments]
  );

  /** Get attachment IDs that are ready for sending */
  const getReadyAttachmentIds = useCallback((): string[] => {
    return attachments
      .filter(a => a.status === 'ready' && a.attachmentId)
      .map(a => a.attachmentId!);
  }, [attachments]);

  return {
    attachments,
    uploadFile,
    addServerAttachment,
    removeFile,
    clearAttachments,
    getReadyAttachmentIds,
    isUploading,
    /** The per-message cap the hook enforces — published so a picker can bound itself. */
    maxAttachments: opts.maxAttachments,
  };
}
