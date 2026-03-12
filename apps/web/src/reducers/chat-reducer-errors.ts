/**
 * Chat reducer error tracking utilities.
 *
 * Provides pure error detection without side effects (logging happens in hook).
 * Follows React best practices: reducers must be pure functions.
 */

import { ChatState, ChatAction } from '@/types/chat-state';

export interface ReducerError {
  type: 'validation' | 'state' | 'data';
  action: string;
  message: string;
  severity: 'error' | 'warning' | 'debug';
  context?: Record<string, unknown>;
}

/**
 * Validate SET_MESSAGES action payload.
 *
 * @param action - Action to validate
 * @returns Error if invalid, null otherwise
 */
export function validateSetMessages(action: ChatAction): ReducerError | null {
  if (action.type !== 'SET_MESSAGES') {
    return null;
  }

  if (!Array.isArray(action.payload.messages)) {
    return {
      type: 'validation',
      action: 'SET_MESSAGES',
      message: 'Received non-array messages payload',
      severity: 'error',
      context: {
        type: typeof action.payload.messages,
        isNull: action.payload.messages === null,
      },
    };
  }

  return null;
}

/**
 * Validate STREAM_TOKEN action state.
 *
 * @param state - Current state
 * @param action - Action being processed
 * @returns Error if invalid, null otherwise
 */
export function validateStreamToken(state: ChatState, action: ChatAction): ReducerError | null {
  if (action.type !== 'STREAM_TOKEN') {
    return null;
  }

  const messageId = state.streaming.currentMessageId;

  // Case 1: No active stream
  // This is NORMAL when SSE ends but late tokens arrive - not an error, just debug info
  if (!messageId) {
    return {
      type: 'state',
      action: 'STREAM_TOKEN',
      message: 'No currentMessageId set, ignoring token (normal after stream end)',
      severity: 'debug', // Changed from implicit 'error' to 'debug' - this is expected behavior
      context: {
        sseStatus: state.streaming.sseStatus,
      },
    };
  }

  // Case 2: Message not found (should have been created by STREAM_START)
  // This IS an actual error - message should exist if currentMessageId is set
  const messageExists = state.messages.some(m => m.id === messageId);
  if (!messageExists) {
    return {
      type: 'state',
      action: 'STREAM_TOKEN',
      message: 'Message not found despite currentMessageId being set',
      severity: 'error', // This is a real error - state inconsistency
      context: {
        messageId,
        messageCount: state.messages.length,
      },
    };
  }

  return null;
}

/**
 * Validate reducer action and state (called from hook, not reducer).
 *
 * Returns all detected errors for logging by the hook.
 *
 * @param state - Current state before action
 * @param action - Action being dispatched
 * @returns Array of errors (empty if valid)
 */
export function validateReducerAction(state: ChatState, action: ChatAction): ReducerError[] {
  const errors: ReducerError[] = [];

  // Validate based on action type
  switch (action.type) {
    case 'SET_MESSAGES': {
      const error = validateSetMessages(action);
      if (error) errors.push(error);
      break;
    }

    case 'STREAM_TOKEN': {
      const error = validateStreamToken(state, action);
      if (error) errors.push(error);
      break;
    }

    // Add more validators as needed
  }

  return errors;
}
