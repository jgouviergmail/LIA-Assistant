/**
 * Draft Types for LARS Draft Preview System
 *
 * TypeScript types aligned with backend LARS models (commands.py).
 * Used by draft preview components for type-safe rendering.
 *
 * Backend source: apps/api/src/domains/agents/lars/models/commands.py
 *
 * @module types/draft
 * LOT 6: Frontend Draft Preview
 */

// ============================================================================
// Enums (aligned with Python DraftType, DraftStatus, DraftAction)
// ============================================================================

/**
 * Types of drafts that can be created.
 * Maps to backend DraftType enum.
 */
export type DraftType = 'email' | 'event' | 'contact' | 'task' | 'note';

/**
 * Lifecycle states for drafts.
 * Maps to backend DraftStatus enum.
 *
 * Flow: pending → confirmed → executed
 *       pending → cancelled
 *       pending → modified → pending (loop)
 */
export type DraftStatus =
  | 'pending' // Awaiting user confirmation
  | 'modified' // User edited, awaiting re-confirmation
  | 'confirmed' // User confirmed, ready for execution
  | 'executed' // Action completed successfully
  | 'failed' // Execution failed
  | 'cancelled'; // User cancelled

/**
 * Actions a user can take on a draft.
 * Maps to backend DraftAction enum.
 */
export type DraftAction = 'confirm' | 'edit' | 'cancel';

// ============================================================================
// Content Interfaces (type-specific draft content)
// ============================================================================

/**
 * Email draft content.
 * Maps to backend EmailDraftInput.
 */
export interface EmailDraftContent {
  to: string;
  subject: string;
  body: string;
  cc?: string | null;
  bcc?: string | null;
  is_html?: boolean;
}

/**
 * Calendar event draft content.
 * Maps to backend EventDraftInput.
 */
export interface EventDraftContent {
  summary: string;
  start_datetime: string;
  end_datetime: string;
  timezone: string;
  description?: string | null;
  location?: string | null;
  attendees?: string[];
}

/**
 * Contact draft content.
 * Maps to backend ContactDraftInput.
 */
export interface ContactDraftContent {
  name: string;
  email?: string | null;
  phone?: string | null;
  organization?: string | null;
  notes?: string | null;
}

/**
 * Task draft content (future).
 */
export interface TaskDraftContent {
  title: string;
  description?: string | null;
  due_date?: string | null;
  priority?: 'low' | 'medium' | 'high';
}

/**
 * Note draft content (future).
 */
export interface NoteDraftContent {
  title: string;
  content: string;
  tags?: string[];
}

/**
 * Union type for all draft content types.
 */
export type DraftContent =
  | EmailDraftContent
  | EventDraftContent
  | ContactDraftContent
  | TaskDraftContent
  | NoteDraftContent;

// ============================================================================
// Draft Payload (from registry_update SSE)
// ============================================================================

/**
 * Draft payload structure from backend.
 * This is the payload inside RegistryItem when type='DRAFT'.
 *
 * Source: LARSCommandAPI._draft_to_registry_item()
 */
export interface DraftPayload {
  /** Type of draft (email, event, contact) */
  draft_type: DraftType;

  /** Current lifecycle status */
  status: DraftStatus;

  /** Draft content (type-specific structure) */
  content: DraftContent;

  /** Related registry item IDs */
  related_registry_ids: string[];

  /** When draft was created (ISO timestamp) */
  created_at: string;

  /** Human-readable summary for display */
  summary: string;

  /** Available actions for this draft */
  actions: DraftAction[];

  /** Whether this draft requires user confirmation */
  requires_confirmation: boolean;

  /** Optional: Source tool that created this draft */
  source_tool?: string;

  /** Optional: Error message if status is 'failed' */
  error_message?: string;

  /** Optional: Execution result if status is 'executed' */
  execution_result?: Record<string, unknown>;
}

// ============================================================================
// Type Guards
// ============================================================================

/**
 * Check if draft content is email type.
 */
export function isEmailDraft(
  payload: DraftPayload
): payload is DraftPayload & { content: EmailDraftContent } {
  return payload.draft_type === 'email';
}

/**
 * Check if draft content is event type.
 */
export function isEventDraft(
  payload: DraftPayload
): payload is DraftPayload & { content: EventDraftContent } {
  return payload.draft_type === 'event';
}

/**
 * Check if draft content is contact type.
 */
export function isContactDraft(
  payload: DraftPayload
): payload is DraftPayload & { content: ContactDraftContent } {
  return payload.draft_type === 'contact';
}

/**
 * Check if draft content is task type.
 */
export function isTaskDraft(
  payload: DraftPayload
): payload is DraftPayload & { content: TaskDraftContent } {
  return payload.draft_type === 'task';
}

/**
 * Check if draft content is note type.
 */
export function isNoteDraft(
  payload: DraftPayload
): payload is DraftPayload & { content: NoteDraftContent } {
  return payload.draft_type === 'note';
}

/**
 * Check if a RegistryItem payload is a DraftPayload.
 * Use this when you have a generic payload and need to narrow.
 */
export function isDraftPayload(payload: unknown): payload is DraftPayload {
  return (
    typeof payload === 'object' &&
    payload !== null &&
    'draft_type' in payload &&
    'status' in payload &&
    'content' in payload &&
    'actions' in payload
  );
}

// ============================================================================
// Action Types (for frontend → backend communication)
// ============================================================================

/**
 * Draft action request sent to backend via HITL resume.
 * Maps to backend DraftActionRequest.
 */
export interface DraftActionRequest {
  draft_id: string;
  action: DraftAction;
  updated_content?: Record<string, unknown>;
  user_message?: string;
}

/**
 * Draft action result from backend.
 * Maps to backend DraftActionResult.
 */
export interface DraftActionResult {
  draft_id: string;
  action: DraftAction;
  success: boolean;
  new_status: DraftStatus;
  execution_result?: Record<string, unknown>;
  error_message?: string;
}

// ============================================================================
// UI Types (for component props)
// ============================================================================

/**
 * Props for draft action buttons.
 */
export interface DraftActionsProps {
  draftId: string;
  actions: DraftAction[];
  status: DraftStatus;
  onAction: (action: DraftAction, draftId: string) => void;
  isLoading?: boolean;
  disabled?: boolean;
}

/**
 * Visual configuration for draft status badges.
 */
export interface StatusBadgeConfig {
  color: 'yellow' | 'blue' | 'green' | 'gray' | 'red';
  icon: string;
  labelKey: string;
}

/**
 * Visual configuration for draft types.
 */
export interface DraftTypeConfig {
  color: 'amber' | 'purple' | 'blue' | 'orange' | 'pink';
  icon: string;
  labelKey: string;
}

// ============================================================================
// Constants
// ============================================================================

/**
 * Status badge configurations for UI.
 */
export const STATUS_BADGE_CONFIG: Record<DraftStatus, StatusBadgeConfig> = {
  pending: { color: 'yellow', icon: '⏳', labelKey: 'draft.status.pending' },
  modified: { color: 'blue', icon: '✏️', labelKey: 'draft.status.modified' },
  confirmed: { color: 'green', icon: '✓', labelKey: 'draft.status.confirmed' },
  executed: { color: 'green', icon: '✅', labelKey: 'draft.status.executed' },
  cancelled: { color: 'gray', icon: '❌', labelKey: 'draft.status.cancelled' },
  failed: { color: 'red', icon: '⚠️', labelKey: 'draft.status.failed' },
};

/**
 * Draft type configurations for UI.
 */
export const DRAFT_TYPE_CONFIG: Record<DraftType, DraftTypeConfig> = {
  email: { color: 'amber', icon: '📧', labelKey: 'draft.type.email' },
  event: { color: 'purple', icon: '📅', labelKey: 'draft.type.event' },
  contact: { color: 'blue', icon: '👤', labelKey: 'draft.type.contact' },
  task: { color: 'orange', icon: '✅', labelKey: 'draft.type.task' },
  note: { color: 'pink', icon: '📌', labelKey: 'draft.type.note' },
};

/**
 * Action button configurations for UI.
 */
export const ACTION_BUTTON_CONFIG: Record<
  DraftAction,
  { variant: 'default' | 'outline' | 'ghost' | 'destructive'; icon: string; labelKey: string }
> = {
  confirm: { variant: 'default', icon: '✓', labelKey: 'draft.action.confirm' },
  edit: { variant: 'outline', icon: '✏️', labelKey: 'draft.action.edit' },
  cancel: { variant: 'ghost', icon: '✕', labelKey: 'draft.action.cancel' },
};
