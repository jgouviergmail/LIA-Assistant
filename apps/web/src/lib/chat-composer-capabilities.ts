import type { AppConfig } from '@/hooks/useAppConfig';
import { bookmarksReadable } from '@/lib/bookmarks/availability';

/**
 * The composer's instance flags (module-level — CC discipline): attachments
 * default ON (the historical behaviour), meeting recording default OFF
 * (ADR-258: an instance that does not publish the flag has no recorder),
 * the knowledge-space documents in the « + » default OFF (no spaces, no
 * documents to offer). The kept answers follow the bookmark routes; the
 * generated files are always the person's to bring back (2026-10-24).
 */
export function composerFeatureFlags(config: AppConfig | null): {
  attachmentsEnabled: boolean;
  knowledgeDocumentsEnabled: boolean;
  bookmarksEnabled: boolean;
  generatedFilesEnabled: boolean;
  meetingImportEnabled: boolean;
  meetingsEnabled: boolean;
} {
  return {
    attachmentsEnabled: config?.features?.attachments_enabled ?? true,
    knowledgeDocumentsEnabled: config?.features?.rag_spaces_enabled ?? false,
    bookmarksEnabled: bookmarksReadable(config),
    generatedFilesEnabled: true,
    meetingImportEnabled: config?.features?.meetings_import_enabled ?? false,
    meetingsEnabled: config?.features?.meetings_enabled ?? false,
  };
}
