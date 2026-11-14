import type { AppConfig } from '@/hooks/useAppConfig';
import { attachmentFormats, type AttachmentFormats } from '@/lib/attachment-formats';
import { bookmarksReadable } from '@/lib/bookmarks/availability';
import { capabilityAvailable } from '@/lib/capability-availability';
import { meetingsAvailable } from '@/lib/meetings/availability';
import { ragSpacesAvailable } from '@/lib/rag-spaces/availability';

/**
 * The composer's instance flags (module-level — CC discipline): attachments
 * default ON (the historical behaviour) and follow the operator's switch,
 * which closes the upload; meeting recording default OFF
 * (ADR-258: an instance that does not publish the flag has no recorder),
 * the knowledge-space documents in the « + » default OFF (no spaces, no
 * documents to offer). The meetings — the recorder, and the import, which is
 * a part of them — and the knowledge documents are offered where the instance
 * offers them NOW, the operator's switch included: their routes refuse once
 * it is off (ADR-280). The kept answers follow the bookmark routes; the
 * generated files are always the person's to bring back (2026-10-24). What an
 * upload takes is the instance's own allowlist, published by `/config`.
 *
 * While LIA answers (`textOnly`), no source of an attachment is offered: the
 * words typed meanwhile wait for their turn, and only words can (ADR-384).
 * The recorder is not a part of a message and stays as it is.
 */
export function composerFeatureFlags(
  config: AppConfig | null,
  { textOnly = false }: { textOnly?: boolean } = {}
): {
  attachmentsEnabled: boolean;
  attachmentFormats: AttachmentFormats;
  knowledgeDocumentsEnabled: boolean;
  bookmarksEnabled: boolean;
  generatedFilesEnabled: boolean;
  meetingImportEnabled: boolean;
  meetingsEnabled: boolean;
} {
  const meetings = meetingsAvailable(config);
  const attachable = !textOnly;
  return {
    attachmentsEnabled: attachable && capabilityAvailable(config, 'attachments', true),
    attachmentFormats: attachmentFormats(config),
    knowledgeDocumentsEnabled: attachable && ragSpacesAvailable(config),
    bookmarksEnabled: attachable && bookmarksReadable(config),
    generatedFilesEnabled: attachable,
    meetingImportEnabled: meetings && (config?.features?.meetings_import_enabled ?? false),
    meetingsEnabled: meetings,
  };
}
