/**
 * SSE Handler Types for useChat.ts refactoring.
 *
 * Provides typed context and handler interfaces for all SSE event handlers.
 */

import { Dispatch, type MutableRefObject } from 'react';
import { ChatAction } from '@/types/chat-state';
import { ChatStreamChunk, VoiceAudioChunk } from '@/types/chat';
import type { ExecutionTraceStep } from '@/types/execution-trace';
import type { StepTally } from '@/lib/execution-outcome';
import { TFunction } from 'i18next';
import type { LogContext } from '@/lib/logger';
import type { ApplicationStateChange } from '@/types/application-state';

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
  handleApplicationStateChange?: (change: ApplicationStateChange) => void;
  /** Latch the output once per new production run; replay never acquires it. */
  beginVoiceRun?: (runId: string) => void;
  /** The run's last clip is queued (`voice_complete`); replay never ends a live one. */
  endVoiceRun?: () => void;
  /** Buffer for HITL streaming questions (accumulates tokens) */
  hitlQuestionBuffer: MutableRefObject<Map<string, string>>;
  /** Accumulated execution step lines for progressive display (cleared on first token) */
  executionStepsRef: MutableRefObject<string[]>;
  /** Set of i18n_keys already emitted — used for deduplication between handlers */
  emittedStepKeysRef: MutableRefObject<Set<string>>;
  /**
   * What each label's steps did, by i18n_key (2026-10-24): the line and the
   * trace step a later step of the same label updates in place.
   */
  stepTalliesRef: MutableRefObject<Map<string, LiveStepTally>>;
  /** Accumulated live reasoning text (💭 block), cleared on first answer token */
  reasoningBufRef: MutableRefObject<string>;
  /**
   * Execution trace accumulators (Lot 2 P2-V1). Parallel to the ephemeral
   * step/reasoning refs above but NOT wiped at the progress→answer flip —
   * they live from the turn start (router_decision / new send) until the
   * `done`, where the trace is attached to the message. This is what lets the
   * backstage record survive the response instead of vanishing.
   */
  traceStepsRef: MutableRefObject<ExecutionTraceStep[]>;
  /** Live reasoning kept for the trace (survives the answer flip). */
  traceReasoningRef: MutableRefObject<string>;
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
  /**
   * Replay mode (ADR-117 Lot 2): true while reattaching to an in-flight
   * background run and replaying its backlog. Reducer dispatches run
   * normally (state reconstruction) but out-of-reducer side effects
   * (sonner toasts, voice playback) are suppressed — they already happened
   * or are stale. Lifted when the server emits the `: replay-end`
   * transport comment. Always false on the normal send path.
   */
  isReplay: boolean;
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

/** One label's live line: its tally, and where its line and trace step sit. */
export interface LiveStepTally {
  tally: StepTally;
  /**
   * The lines its line was written into. The answer's first token and a HITL
   * question REPLACE the lines but keep the tallies (the trace still learns),
   * so an index alone could point at a line drawn since.
   */
  lines: string[];
  lineIndex: number;
  traceIndex: number | null;
}

/**
 * Progress message metadata for execution steps.
 */
export interface ProgressMessageMetadata {
  emoji?: string;
  i18n_key?: string;
  tool_name?: string;
  /** Reasoning sub-type discriminator (live chain-of-thought) */
  step_type?: string;
  /** Coalesced reasoning text fragment (when step_type === 'reasoning') */
  delta?: string;
  /** Originating node name (e.g. 'query_analyzer') */
  node?: string;
  /** Trace grouping bucket (Lot 2): system | agent | tool | context. */
  category?: string;
  /** One tool call's identity across its started and finished steps (2026-10-24). */
  step_key?: string;
  /** What the step did — counts only (2026-10-24). */
  outcome?: Record<string, unknown>;
}
