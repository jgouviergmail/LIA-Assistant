/**
 * SSE (Server-Sent Events) Chat API Client
 * Handles streaming responses from the agents endpoint
 */

import { ChatStreamChunk, ChatRequest } from '@/types/chat';
import { logger } from '@/lib/logger';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const SSE_ENDPOINT = `${API_BASE_URL}/api/v1/agents/chat/stream`;

/**
 * Custom error class for chat stream errors with i18n support.
 * Consumer components should use the i18nKey to translate the message.
 */
export class ChatStreamError extends Error {
  /** i18n key for translation (e.g., 'errors.chat.session_expired') */
  readonly i18nKey: string;
  /** Optional interpolation params for i18n (e.g., { status: 500 }) */
  readonly i18nParams?: Record<string, string | number>;
  /**
   * Present on RunInProgressError (HTTP 409, ADR-117 Lot 2): the transport
   * id of the in-flight run — the caller reattaches to it instead of
   * surfacing an error.
   */
  readonly activeStreamId?: string;

  constructor(
    name: string,
    i18nKey: string,
    fallbackMessage: string,
    i18nParams?: Record<string, string | number>,
    activeStreamId?: string
  ) {
    super(fallbackMessage);
    this.name = name;
    this.i18nKey = i18nKey;
    this.i18nParams = i18nParams;
    this.activeStreamId = activeStreamId;
  }
}

/** Active background run of the user's conversation (ADR-117 Lot 2). */
export interface ActiveRunStatus {
  active: boolean;
  stream_id?: string;
  run_id?: string;
}

/**
 * Check whether a background run is in flight for the user's conversation.
 * Called at chat-page mount (and on visibility change) to trigger reattach.
 * Fail-closed: any error reads as "no active run" (the page then behaves
 * exactly as before ADR-117 Lot 2).
 */
/**
 * Request cancellation of the caller's in-flight background run (stop
 * button, ADR-117 Lot 3). The server resolves the active run itself.
 * Fail-closed: any error reads as "nothing was cancelled" — the caller
 * then falls back to the legacy local abort.
 */
export async function cancelActiveRun(): Promise<{ cancelled: boolean }> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/agents/runs/active/cancel`, {
      method: 'POST',
      credentials: 'include',
    });
    if (!response.ok) {
      return { cancelled: false };
    }
    const body = (await response.json()) as { cancelled?: boolean };
    return { cancelled: body?.cancelled === true };
  } catch (error) {
    logger.warn('cancel_active_run_failed', {
      component: 'ChatSSEClient',
      error: String(error),
    });
    return { cancelled: false };
  }
}

export async function fetchActiveRun(): Promise<ActiveRunStatus> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/agents/runs/active`, {
      method: 'GET',
      credentials: 'include',
    });
    if (!response.ok) {
      return { active: false };
    }
    const body = (await response.json()) as ActiveRunStatus;
    return body?.active && body.stream_id ? body : { active: false };
  } catch (error) {
    logger.warn('active_run_check_failed', {
      component: 'ChatSSEClient',
      error: String(error),
    });
    return { active: false };
  }
}

export class ChatSSEClient {
  private abortController: AbortController | null = null;
  private isConnected = false;
  // Flag to ignore chunks after cancel() - prevents race condition
  // where buffered chunks from previous request are processed after new request starts
  private isCancelled = false;

  /**
   * Stream chat response via SSE
   * @param request Chat request with message and session info
   * @param onChunk Callback for each SSE chunk received
   * @param onError Callback for errors
   * @param onDone Callback when stream completes
   */
  async streamChat(
    request: ChatRequest,
    onChunk: (chunk: ChatStreamChunk) => void,
    onError: (error: Error) => void,
    onDone: () => void
  ): Promise<void> {
    try {
      // Build SSE URL with GET parameters (EventSource doesn't support POST)
      // Alternative: use fetch with ReadableStream
      await this.streamChatWithFetch(request, onChunk, onError, onDone);
    } catch (error) {
      logger.error('chat_sse_stream_error', error instanceof Error ? error : undefined, {
        component: 'ChatSSEClient',
      });
      onError(error instanceof Error ? error : new Error('Unknown error'));
    }
  }

  /**
   * Stream chat using Fetch API with ReadableStream
   * More flexible than EventSource (supports POST, headers, etc.)
   */
  private async streamChatWithFetch(
    request: ChatRequest,
    onChunk: (chunk: ChatStreamChunk) => void,
    onError: (error: Error) => void,
    onDone: () => void
  ): Promise<void> {
    try {
      // Reset cancelled flag for new stream
      this.isCancelled = false;
      // Create new AbortController for this stream
      this.abortController = new AbortController();

      const response = await fetch(SSE_ENDPOINT, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include', // Important: send session cookie
        body: JSON.stringify(request),
        signal: this.abortController.signal, // Enable cancellation
      });

      if (!response.ok) {
        // Handle specific HTTP errors with i18n-ready error codes
        if (response.status === 401) {
          // Session expired - user needs to re-authenticate
          throw new ChatStreamError(
            'AuthenticationError',
            'errors.chat.session_expired',
            'Your session has expired. Please log in again.'
          );
        } else if (response.status === 403) {
          // Forbidden - user doesn't have access (account might be inactive)
          throw new ChatStreamError(
            'AccountInactiveError',
            'errors.chat.account_inactive',
            'Your account is disabled. Check your emails for more information or contact an administrator.'
          );
        } else if (response.status === 429) {
          // Usage limit exceeded
          throw new ChatStreamError(
            'UsageLimitExceededError',
            'errors.chat.usage_limit_exceeded',
            'You have reached your usage limit. Contact your administrator.'
          );
        } else if (response.status === 409) {
          // A background run is already in flight for this conversation
          // (ADR-117 Lot 2) — surface its stream id so the caller reattaches.
          let activeStreamId: string | undefined;
          try {
            const body = (await response.json()) as {
              detail?: { active_run?: { stream_id?: string } };
            };
            activeStreamId = body?.detail?.active_run?.stream_id ?? undefined;
          } catch {
            // Malformed body: fall through without a stream id
          }
          throw new ChatStreamError(
            'RunInProgressError',
            'errors.chat.run_in_progress',
            'A response is already being generated for this conversation.',
            undefined,
            activeStreamId
          );
        } else if (response.status === 503) {
          // Service unavailable
          throw new ChatStreamError(
            'ServiceUnavailableError',
            'errors.chat.service_unavailable',
            'The service is temporarily unavailable. Please try again in a moment.'
          );
        } else if (response.status >= 500) {
          // Server error
          throw new ChatStreamError(
            'ServerError',
            'errors.chat.server_error',
            `Server error (${response.status}). Please try again.`,
            { status: response.status }
          );
        } else {
          // Other client errors
          throw new ChatStreamError(
            'HttpError',
            'errors.chat.http_error',
            `HTTP Error ${response.status}: ${response.statusText}`,
            { status: response.status, statusText: response.statusText }
          );
        }
      }

      if (!response.body) {
        throw new Error('Response body is null');
      }

      this.isConnected = true;
      await this.readSseStream(response, onChunk, onDone);
    } catch (error) {
      this.handleStreamError(error, onError);
    } finally {
      // Cleanup AbortController
      this.abortController = null;
    }
  }

  /**
   * Reattach to an in-flight background run (ADR-117 Lot 2).
   *
   * GET variant of the chat stream: full replay of the run's backlog, then
   * the live tail. The server marks the replay→live boundary with the
   * `: replay-end` transport comment (surfaced via onReplayEnd so the
   * caller lifts its replay-mode side-effect suppression).
   *
   * @param streamId Transport id from GET /agents/runs/active (or a 409)
   * @param onChunk Callback for each SSE chunk received
   * @param onError Callback for errors
   * @param onDone Callback when stream completes
   * @param onReplayEnd Callback fired once at the replay→live boundary
   */
  async reattachStream(
    streamId: string,
    onChunk: (chunk: ChatStreamChunk) => void,
    onError: (error: Error) => void,
    onDone: () => void,
    onReplayEnd?: () => void
  ): Promise<void> {
    try {
      this.isCancelled = false;
      this.abortController = new AbortController();

      const response = await fetch(
        `${API_BASE_URL}/api/v1/agents/runs/${encodeURIComponent(streamId)}/stream`,
        {
          method: 'GET',
          credentials: 'include',
          signal: this.abortController.signal,
        }
      );

      if (!response.ok) {
        if (response.status === 401) {
          throw new ChatStreamError(
            'AuthenticationError',
            'errors.chat.session_expired',
            'Your session has expired. Please log in again.'
          );
        }
        // 404 = the run finished (or never existed) between the active-run
        // check and this call — the history reload owns that content now.
        throw new ChatStreamError(
          'RunGoneError',
          'errors.chat.run_gone',
          'This response finished in the background. Reloading the history.',
          { status: response.status }
        );
      }

      if (!response.body) {
        throw new Error('Response body is null');
      }

      this.isConnected = true;
      await this.readSseStream(response, onChunk, onDone, onReplayEnd);
    } catch (error) {
      this.handleStreamError(error, onError);
    } finally {
      this.abortController = null;
    }
  }

  /**
   * Shared SSE reader loop (POST send + GET reattach).
   * Parses `data:` frames into ChatStreamChunk, ignores heartbeats/retry
   * hints, and surfaces the `: replay-end` transport comment (Lot 2).
   */
  private async readSseStream(
    response: Response,
    onChunk: (chunk: ChatStreamChunk) => void,
    onDone: () => void,
    onReplayEnd?: () => void
  ): Promise<void> {
    // Read stream
    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();

      if (done) {
        logger.debug('chat_sse_stream_completed', { component: 'ChatSSEClient' });
        this.isConnected = false;
        onDone();
        break;
      }

      // Decode chunk and add to buffer
      buffer += decoder.decode(value, { stream: true });

      // Process complete SSE messages
      const lines = buffer.split('\n');
      buffer = lines.pop() || ''; // Keep last incomplete line

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6); // Remove 'data: ' prefix

          try {
            const chunk: ChatStreamChunk = JSON.parse(data);

            // ============================================================================
            // Structured logger: debug-level entries are dropped in production,
            // and message content is never logged (PII protection).
            // ============================================================================
            if (chunk.type === 'error') {
              logger.error('chat_sse_error_chunk', undefined, {
                component: 'ChatSSEClient',
                error: chunk.error,
                code: chunk.error_code,
              });
            } else if (chunk.type === 'done') {
              logger.debug('chat_sse_stream_complete', {
                component: 'ChatSSEClient',
              });
            } else if (chunk.type === 'execution_step') {
              // Phase 6: Execution step tracking
              const stepMetadata = chunk.metadata as Record<string, unknown> | undefined;
              logger.debug('chat_sse_execution_step', {
                component: 'ChatSSEClient',
                step_type: stepMetadata?.step_type,
                step_name: stepMetadata?.step_name,
                i18n_key: stepMetadata?.i18n_key,
                category: stepMetadata?.category,
              });
            } else if (chunk.type === 'token') {
              // Token chunks are frequent - no logging needed
            } else if (
              chunk.type === 'hitl_question_token' ||
              chunk.type === 'content_replacement'
            ) {
              // HITL streaming tokens and content replacements - no logging needed
              // These are frequent and would flood the console
            } else {
              // Unknown chunk type - log type only for debugging
              logger.debug('chat_sse_unknown_chunk_type', {
                component: 'ChatSSEClient',
                chunk_type: chunk.type,
              });
            }

            // CRITICAL: Skip chunk if stream was cancelled
            // This prevents race condition where buffered chunks from previous
            // request are processed after a new request has started
            if (this.isCancelled) {
              logger.debug('chat_sse_chunk_skipped_cancelled', {
                component: 'ChatSSEClient',
                chunk_type: chunk.type,
              });
              continue;
            }

            onChunk(chunk);
          } catch (parseError) {
            // Log the parse failure without the raw payload (may contain PII)
            logger.warn('chat_sse_chunk_parse_failed', {
              component: 'ChatSSEClient',
              data_length: data.length,
              error: String(parseError),
            });
          }
        } else if (line.startsWith(': replay-end')) {
          // ADR-117 Lot 2: replay→live boundary on a reattached stream
          onReplayEnd?.();
        } else if (line.startsWith(': heartbeat')) {
          // Heartbeat - keep connection alive, no logging needed
        } else if (line.startsWith('retry:')) {
          // Retry interval sent by server - no logging needed
        }
      }
    }
  }

  /**
   * Shared error funnel (POST send + GET reattach): maps transport errors
   * to i18n-ready ChatStreamError instances; silent on user cancellation.
   */
  private handleStreamError(error: unknown, onError: (error: Error) => void): void {
    logger.error('chat_sse_fetch_stream_error', error instanceof Error ? error : undefined, {
      component: 'ChatSSEClient',
    });
    this.isConnected = false;

    // Handle network errors with i18n-ready error codes
    if (error instanceof DOMException && error.name === 'AbortError') {
      // Stream was cancelled by user - this is expected, don't call onError
      logger.debug('chat_sse_stream_cancelled_by_user', { component: 'ChatSSEClient' });
      return; // Silent cancellation, no error callback
    } else if (error instanceof TypeError && error.message.includes('fetch')) {
      onError(
        new ChatStreamError(
          'NetworkError',
          'errors.chat.network_error',
          'Network connection error. Check your internet connection.'
        )
      );
    } else if (error instanceof ChatStreamError) {
      // ChatStreamError already has i18n info - pass through
      onError(error);
      // Handle redirect for auth errors
      if (error.name === 'AuthenticationError' && typeof window !== 'undefined') {
        setTimeout(() => {
          window.location.href = '/login?redirect=' + encodeURIComponent(window.location.pathname);
        }, 2000);
      }
    } else {
      onError(
        error instanceof Error
          ? error
          : new ChatStreamError(
              'UnknownError',
              'errors.chat.unknown_error',
              'Unknown error during streaming'
            )
      );
    }
  }

  /**
   * Cancel current stream
   * Aborts the fetch request and stops streaming
   * Sets isCancelled flag to ignore any buffered chunks still being processed
   */
  cancel(): void {
    if (this.abortController) {
      logger.debug('chat_sse_cancelling_stream', { component: 'ChatSSEClient' });
      this.isCancelled = true; // CRITICAL: Set BEFORE abort to prevent race condition
      this.abortController.abort();
      this.abortController = null;
    }
    this.isConnected = false;
  }

  /**
   * Check if currently connected and streaming
   */
  getIsConnected(): boolean {
    return this.isConnected;
  }
}

/**
 * Singleton instance
 */
export const chatSSEClient = new ChatSSEClient();

// ============================================================================
// HITL (Human-in-the-Loop) API Functions
