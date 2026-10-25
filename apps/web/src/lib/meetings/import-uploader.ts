/**
 * Upload of a file imported as a meeting (owner request 2026-10-24).
 *
 * The file is cut with `Blob.slice()` — nothing copied in memory — into chunks
 * of the size the server publishes, queued on the recorder's own
 * `SegmentUploader` (ordered, retrying, offline-aware), and completed only once
 * every chunk landed. A refusal or an abort never completes: the caller then
 * deletes the meeting the import opened.
 */

import { meetingErrorCode, meetingsApi } from '@/lib/meetings/api';
import {
  apiImportTransport,
  SegmentUploader,
  type SegmentTransport,
} from '@/lib/meetings/segment-uploader';

export interface ImportUploadOptions {
  meetingId: string;
  file: Blob;
  /** The server's published chunk size. */
  chunkBytes: number;
  transport?: SegmentTransport;
  complete?: (meetingId: string, chunkCount: number) => Promise<unknown>;
  onProgress?: (sent: number, total: number) => void;
  signal?: AbortSignal;
}

export type ImportUploadResult =
  | { kind: 'complete' }
  | { kind: 'refused'; code: string }
  | { kind: 'aborted' };

/** How many chunks a file of `size` bytes travels in. */
export function chunkCountOf(size: number, chunkBytes: number): number {
  return Math.max(1, Math.ceil(size / chunkBytes));
}

export async function uploadImportFile(options: ImportUploadOptions): Promise<ImportUploadResult> {
  const { meetingId, file, chunkBytes, signal } = options;
  const total = chunkCountOf(file.size, chunkBytes);
  const uploader = new SegmentUploader({
    meetingId,
    transport: options.transport ?? apiImportTransport,
    onProgress: progress => options.onProgress?.(progress.uploaded, total),
  });
  const abort = () => uploader.dispose();
  signal?.addEventListener('abort', abort, { once: true });
  try {
    for (let sequence = 0; sequence < total && !signal?.aborted; sequence += 1) {
      uploader.enqueue(file.slice(sequence * chunkBytes, (sequence + 1) * chunkBytes));
    }
    await uploader.flush();
    if (signal?.aborted) return { kind: 'aborted' };
    if (uploader.fatalCode !== null) return { kind: 'refused', code: uploader.fatalCode };
    try {
      await (options.complete ?? meetingsApi.completeImport)(meetingId, total);
    } catch (error) {
      return { kind: 'refused', code: meetingErrorCode(error) ?? 'unexpected' };
    }
    return { kind: 'complete' };
  } finally {
    signal?.removeEventListener('abort', abort);
  }
}
