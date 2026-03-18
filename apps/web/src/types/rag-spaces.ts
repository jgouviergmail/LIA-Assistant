/**
 * RAG Spaces TypeScript interfaces.
 *
 * Mirrors backend Pydantic schemas from
 * `apps/api/src/domains/rag_spaces/schemas.py`.
 *
 * Phase: evolution — RAG Spaces (User Knowledge Documents)
 * Created: 2026-03-14
 */

/** Document processing lifecycle status. */
export type RAGDocumentStatus = 'processing' | 'ready' | 'error' | 'reindexing';

/** Drive folder sync status. */
export type RAGDriveSyncStatus = 'idle' | 'syncing' | 'completed' | 'error';

/** Document source type. */
export type RAGDocumentSourceType = 'upload' | 'drive';

/** Single RAG document within a space. */
export interface RAGDocument {
  id: string;
  original_filename: string;
  file_size: number;
  content_type: string;
  status: RAGDocumentStatus;
  error_message: string | null;
  chunk_count: number;
  embedding_model: string | null;
  embedding_tokens: number;
  embedding_cost_eur: number;
  source_type: RAGDocumentSourceType;
  drive_file_id: string | null;
  created_at: string;
}

/** Linked Google Drive folder source. */
export interface RAGDriveSource {
  id: string;
  folder_id: string;
  folder_name: string;
  sync_status: RAGDriveSyncStatus;
  last_sync_at: string | null;
  file_count: number;
  synced_file_count: number;
  error_message: string | null;
  created_at: string;
}

/** Google Drive folder for browsing. */
export interface DriveFolder {
  id: string;
  name: string;
  mimeType: string;
  modifiedTime: string;
}

/** Response from the Drive folder browse endpoint. */
export interface DriveFolderBrowseResponse {
  files: DriveFolder[];
  nextPageToken: string | null;
}

/** RAG space summary (list view). */
export interface RAGSpace {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  document_count: number;
  ready_document_count: number;
  total_size: number;
  created_at: string;
  updated_at: string;
}

/** RAG space with embedded documents (detail view). */
export interface RAGSpaceDetail extends RAGSpace {
  documents: RAGDocument[];
  drive_sources: RAGDriveSource[];
}

/** API response for space list endpoint. */
export interface RAGSpaceListResponse {
  spaces: RAGSpace[];
  total: number;
}

/** Payload for creating a space. */
export interface RAGSpaceCreatePayload {
  name: string;
  description?: string;
}

/** Payload for updating a space. */
export interface RAGSpaceUpdatePayload {
  name?: string;
  description?: string;
}

/** API response for toggle endpoint. */
export interface RAGSpaceToggleResponse {
  id: string;
  is_active: boolean;
}

/** API response for document status polling. */
export interface RAGDocumentStatusResponse {
  id: string;
  status: RAGDocumentStatus;
  error_message: string | null;
  chunk_count: number;
}

/** API response for admin reindex. */
export interface RAGReindexResponse {
  message: string;
  total_documents: number;
  model_from: string | null;
  model_to: string;
}

/** API response for admin reindex status. */
export interface RAGReindexStatusResponse {
  in_progress: boolean;
  model_from: string | null;
  model_to: string | null;
  total_documents: number;
  processed_documents: number;
  failed_documents: number;
  started_at: string | null;
}
