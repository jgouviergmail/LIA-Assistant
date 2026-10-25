/**
 * What the composer can attach as a COPY of something the person already holds
 * (owner request 2026-10-24): a kept answer, a generated file — beside the
 * knowledge-space documents (ADR-295). Each copy is made by the API, which
 * checks the source is the caller's; the composer only names the source.
 *
 * The chat's `?attach=<kind>:<id>` deep link names one, so a « Use in the
 * discussion » button on the bookmarks or the gallery page is a plain link: the
 * chat makes the copy on arrival, the link is dropped from the address at once,
 * and replaying it can only attach another copy — never send anything.
 */

import apiClient from '@/lib/api-client';
import type { AttachSource, AttachSourceKind } from '@/lib/attach-source-link';
import type { ServerAttachmentMeta } from '@/hooks/useFileUpload';

/** What a copy endpoint answers: the new attachment row, as an upload's. */
export interface AttachmentCreated {
  id: string;
  original_filename: string;
  mime_type: string;
  file_size: number;
  content_type: 'image' | 'document';
}

/** The copy endpoint of each kind, and the body it takes. */
const COPY_ENDPOINTS: Record<AttachSourceKind, (id: string) => [string, Record<string, string>]> = {
  bookmark: id => ['/attachments/from-bookmark', { bookmark_id: id }],
  generated: id => ['/attachments/from-generated', { attachment_id: id }],
};

/** Ask the API for a copy of the source; the created row is the truth about it. */
export async function copyAttachSource(source: AttachSource): Promise<AttachmentCreated> {
  const [path, body] = COPY_ENDPOINTS[source.kind](source.id);
  return apiClient.post<AttachmentCreated>(path, body);
}

/** The strip's view of a created copy. */
export function attachmentMeta(
  created: AttachmentCreated,
  filename?: string
): ServerAttachmentMeta {
  return {
    id: created.id,
    filename: filename ?? created.original_filename,
    mimeType: created.mime_type,
    size: created.file_size,
    contentType: created.content_type,
  };
}
