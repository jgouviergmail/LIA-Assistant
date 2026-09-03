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
export type RAGDocumentStatus = 'pending' | 'processing' | 'ready' | 'error' | 'reindexing';

/** One sync lifecycle for every synced source — Drive folder, Gmail label (ADR-262). */
export type RAGSourceSyncStatus = 'idle' | 'syncing' | 'completed' | 'error';

/** Drive folder sync status (the shared lifecycle, kept for readability). */
export type RAGDriveSyncStatus = RAGSourceSyncStatus;

/** Document source type. */
export type RAGDocumentSourceType = 'upload' | 'drive' | 'meeting' | 'mail';

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
  /** The Gmail thread this document renders, when it came from a label (ADR-262). */
  mail_thread_id?: string | null;
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

/** Linked Gmail label source (ADR-262): its threads are documents of the space. */
export interface RAGMailSource {
  id: string;
  label_id: string;
  label_name: string;
  sync_status: RAGSourceSyncStatus;
  last_sync_at: string | null;
  thread_count: number;
  synced_thread_count: number;
  error_message: string | null;
  created_at: string;
}

/** One Gmail label the picker may offer. */
export interface GmailLabel {
  id: string;
  name: string;
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
  mail_sources: RAGMailSource[];
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
/** One id a batch left untouched, with the stable reason (ADR-259). */
export interface RAGBatchSkipped {
  id: string;
  code: string;
}

/** What a batch (move, bulk delete) did. */
export interface RAGDocumentBatchResponse {
  done: string[];
  skipped: RAGBatchSkipped[];
}

export interface RAGDocumentIdsRequest {
  ids: string[];
}

export interface RAGDocumentMoveRequest extends RAGDocumentIdsRequest {
  target_space_id: string;
}

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
