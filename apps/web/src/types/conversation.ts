/** The public discussion coordinate; runtime and execution authority stay on the server. */
export interface ConversationSelection {
  readonly conversation_id: string;
  readonly conversation_revision: number;
}

/** Metadata returned by the catalogue; no runtime identifier crosses this boundary. */
export interface ConversationSummary {
  id: string;
  user_id: string;
  kind: 'main' | 'secondary';
  revision: number;
  title: string | null;
  message_count: number;
  total_tokens: number;
  created_at: string;
  updated_at: string;
}

export interface ConversationCatalogueConfig {
  creation_enabled: boolean;
  background_runs_enabled: boolean;
  title_max_length: number;
  title_pattern: string;
  offset_max: number;
  page_default_limit: number;
  page_max_limit: number;
}

export interface ConversationCataloguePage {
  items: ConversationSummary[];
  total_count: number;
  offset: number;
  limit: number;
}

export interface ConversationCreateRequest {
  /** Omitted: the discussion takes its title from the first message written in it. */
  title?: string;
  request_id: string;
}

export interface ConversationCreateResult {
  conversation: ConversationSummary;
  replayed: boolean;
}

export interface ConversationRenameRequest {
  title: string;
  expected_title: string;
  expected_revision: number;
}

export type ConversationOperation = 'reset' | 'delete';

export interface ConversationOperationRequest {
  operation_id: string;
  expected_revision: number;
}

export interface ConversationOperationResult {
  operation_id: string;
  conversation_id: string;
  old_revision: number;
  new_revision: number | null;
  previous_message_count: number;
  state: 'pending' | 'running' | 'retry_wait' | 'needs_attention' | 'succeeded';
  logical_applied: boolean;
  cleanup_complete: boolean;
  replayed: boolean;
}
