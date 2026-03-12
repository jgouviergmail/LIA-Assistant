/**
 * SSE Handler Types for useChat.ts refactoring.
 *
 * Provides typed context and handler interfaces for all SSE event handlers.
 */

import { Dispatch, type MutableRefObject } from 'react';
import { ChatAction } from '@/types/chat-state';
import { ChatStreamChunk, VoiceAudioChunk } from '@/types/chat';
import { TFunction } from 'i18next';
import type { LogContext } from '@/lib/logger';

/**
 * Context passed to all SSE handlers.
 * Contains everything handlers need to dispatch actions and manage state.
 */
export interface SSEHandlerContext {
  /** React dispatch function for chat reducer actions */
  dispatch: Dispatch<ChatAction>;
  /** i18n translation function */
  t: TFunction;
  /** Logging context wrapper (adds component metadata to logs) */
  withContext: (context?: LogContext) => LogContext;
  /** Voice playback callback for TTS audio chunks */
  handleVoiceChunk: (chunk: VoiceAudioChunk) => void;
  /** Buffer for HITL streaming questions (accumulates tokens) */
  hitlQuestionBuffer: MutableRefObject<Map<string, string>>;
  /** Current assistant message ID */
  assistantMessageId: string;
  /** Progress message ID (ephemeral router/planner/HITL messages) */
  progressMessageId: string | null;
  /** Setter for progress message ID */
  setProgressMessageId: (id: string | null) => void;
  /** Whether normal streaming has been initialized */
  normalStreamInitialized: boolean;
  /** Setter for normal stream initialization flag */
  setNormalStreamInitialized: (v: boolean) => void;
}

/**
 * SSE handler function signature.
 * All handlers receive a chunk and context, returning void.
 */
export type SSEHandler = (chunk: ChatStreamChunk, context: SSEHandlerContext) => void;

/**
 * Map of SSE chunk types to their handlers.
 */
export type SSEHandlerMap = Partial<Record<string, SSEHandler>>;

/**
 * Progress message metadata for execution steps.
 */
export interface ProgressMessageMetadata {
  emoji?: string;
  i18n_key?: string;
}
