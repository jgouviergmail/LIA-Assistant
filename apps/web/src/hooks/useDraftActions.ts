/**
 * useDraftActions - Hook for handling draft confirmation/edit/cancel actions
 *
 * Provides callbacks for draft actions that integrate with the chat system.
 * Actions are sent as HITL responses to resume the conversation flow.
 *
 * LOT 6: Frontend Draft Preview
 *
 * @module hooks/useDraftActions
 */

import { useCallback, useState } from 'react';
import { useChat } from './useChat';
import { logger } from '@/lib/logger';
import { useLoggingContext } from '@/lib/logging-context';
import type { DraftAction, DraftActionRequest } from '@/types/draft';

// ============================================================================
// Types
// ============================================================================

export interface UseDraftActionsReturn {
  /**
   * Handle a draft action (confirm, edit, cancel).
   * Sends the action to backend via chat message with HITL metadata.
   */
  handleDraftAction: (
    action: DraftAction,
    draftId: string,
    updatedContent?: Record<string, unknown>
  ) => Promise<void>;

  /**
   * Whether a draft action is currently being processed.
   */
  isProcessing: boolean;

  /**
   * ID of the draft currently being processed (if any).
   */
  processingDraftId: string | null;

  /**
   * Error message if the last action failed.
   */
  error: string | null;

  /**
   * Clear any error state.
   */
  clearError: () => void;
}

// ============================================================================
// Hook
// ============================================================================

/**
 * Hook for handling draft actions with HITL integration.
 *
 * Usage:
 * ```tsx
 * const { handleDraftAction, isProcessing } = useDraftActions();
 *
 * <DraftActions
 *   draftId="draft_abc123"
 *   actions={['confirm', 'edit', 'cancel']}
 *   status="pending"
 *   onAction={handleDraftAction}
 *   isLoading={isProcessing}
 * />
 * ```
 */
export function useDraftActions(): UseDraftActionsReturn {
  const { sendMessage } = useChat();
  const { withContext } = useLoggingContext();

  const [isProcessing, setIsProcessing] = useState(false);
  const [processingDraftId, setProcessingDraftId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  /**
   * Handle a draft action by sending it as a HITL response.
   *
   * The backend interprets this as a resumption of the draft confirmation flow.
   * - confirm: Execute the draft action (send email, create event, etc.)
   * - edit: Update draft content (triggers re-confirmation)
   * - cancel: Cancel the draft (removes it from pending state)
   */
  const handleDraftAction = useCallback(
    async (action: DraftAction, draftId: string, updatedContent?: Record<string, unknown>) => {
      // Don't allow concurrent actions
      if (isProcessing) {
        logger.warn(
          'draft_action_already_processing',
          withContext({
            component: 'useDraftActions',
            action,
            draftId,
            currentlyProcessing: processingDraftId,
          })
        );
        return;
      }

      setIsProcessing(true);
      setProcessingDraftId(draftId);
      setError(null);

      try {
        // Build the draft action request
        const actionRequest: DraftActionRequest = {
          draft_id: draftId,
          action,
          updated_content: updatedContent,
        };

        // Log the action
        logger.info(
          'draft_action_initiated',
          withContext({
            component: 'useDraftActions',
            action,
            draftId,
            hasUpdatedContent: !!updatedContent,
          })
        );

        // Send as HITL response message
        // The backend will detect this as a draft action and process accordingly
        // Message format: JSON with hitl_response metadata
        const message = JSON.stringify({
          type: 'draft_action',
          ...actionRequest,
        });

        // Send via chat system with HITL metadata
        // Note: The backend processes this as a draft action in the HITL flow
        await sendMessage(message);

        logger.info(
          'draft_action_sent',
          withContext({
            component: 'useDraftActions',
            action,
            draftId,
          })
        );
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'Unknown error';

        logger.error(
          'draft_action_failed',
          err as Error,
          withContext({
            component: 'useDraftActions',
            action,
            draftId,
          })
        );

        setError(errorMessage);
      } finally {
        setIsProcessing(false);
        setProcessingDraftId(null);
      }
    },
    [sendMessage, isProcessing, processingDraftId, withContext]
  );

  /**
   * Clear any error state.
   */
  const clearError = useCallback(() => {
    setError(null);
  }, []);

  return {
    handleDraftAction,
    isProcessing,
    processingDraftId,
    error,
    clearError,
  };
}

export default useDraftActions;
