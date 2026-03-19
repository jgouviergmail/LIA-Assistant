/**
 * SSE (Server-Sent Events) Chat API Client
 * Handles streaming responses from the agents endpoint
 */

import { ChatStreamChunk, ChatRequest, OrchestrationMetadata } from '@/types/chat';

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

  constructor(
    name: string,
    i18nKey: string,
    fallbackMessage: string,
    i18nParams?: Record<string, string | number>
  ) {
    super(fallbackMessage);
    this.name = name;
    this.i18nKey = i18nKey;
    this.i18nParams = i18nParams;
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
      console.error('[ChatSSEClient] Stream error:', error);
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

      // Read stream
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();

        if (done) {
          console.log('[ChatSSEClient] Stream completed');
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
              // PHASE 5 - Enhanced Logging for Orchestration Workflow
              // ============================================================================

              // Log chunk type and key info for debugging orchestration
              if (chunk.type === 'node') {
                console.log(`[ChatSSE] 🟢 Node: ${chunk.node_name}`, {
                  type: chunk.type,
                  node: chunk.node_name,
                  timestamp: new Date().toISOString(),
                });
              } else if (chunk.type === 'content') {
                // Content chunks - show first 50 chars
                const preview = chunk.content?.substring(0, 50) || '';
                console.log(
                  `[ChatSSE] 📝 Content:`,
                  preview + (chunk.content && chunk.content.length > 50 ? '...' : '')
                );
              } else if (chunk.type === 'tool_call') {
                console.log(`[ChatSSE] 🔧 Tool Call: ${chunk.tool_name}`, {
                  tool: chunk.tool_name,
                  args: chunk.args,
                  timestamp: new Date().toISOString(),
                });
              } else if (chunk.type === 'tool_result') {
                console.log(`[ChatSSE] ✅ Tool Result: ${chunk.tool_name}`, {
                  tool: chunk.tool_name,
                  success: chunk.success,
                  timestamp: new Date().toISOString(),
                });
              } else if (chunk.type === 'metadata') {
                // Phase 5: Orchestration metadata
                const metadata = (chunk.metadata || {}) as OrchestrationMetadata;
                if (metadata.step === 'plan_validation') {
                  console.log(`[ChatSSE] ✓ Plan Validator:`, {
                    step: 'validation',
                    valid: metadata.is_valid,
                    cost: metadata.total_cost_usd,
                    steps: metadata.step_count,
                    timestamp: new Date().toISOString(),
                  });
                } else if (metadata.step === 'plan_execution') {
                  console.log(`[ChatSSE] ⚡ Plan Executor:`, {
                    step: 'execution',
                    current_step: metadata.current_step,
                    total_steps: metadata.total_steps,
                    progress: `${metadata.current_step}/${metadata.total_steps}`,
                    timestamp: new Date().toISOString(),
                  });
                } else if (metadata.step === 'orchestrator') {
                  console.log(`[ChatSSE] 🎯 Orchestrator:`, {
                    step: 'orchestration',
                    agent: metadata.agent_name,
                    plan_generated: metadata.plan_generated,
                    timestamp: new Date().toISOString(),
                  });
                } else if (metadata.router_decision) {
                  console.log(`[ChatSSE] 🧭 Router Decision:`, {
                    intention: metadata.router_decision.intention,
                    confidence: metadata.router_decision.confidence,
                    agent: metadata.router_decision.selected_agent,
                    timestamp: new Date().toISOString(),
                  });
                } else {
                  console.log(`[ChatSSE] ℹ️ Metadata:`, metadata);
                }
              } else if (chunk.type === 'error') {
                console.error(`[ChatSSE] ❌ Error:`, {
                  error: chunk.error,
                  code: chunk.error_code,
                  timestamp: new Date().toISOString(),
                });
              } else if (chunk.type === 'done') {
                console.log(`[ChatSSE] ✅ Stream Complete`, {
                  type: 'done',
                  timestamp: new Date().toISOString(),
                });
              } else if (chunk.type === 'execution_step') {
                // Phase 6: Execution step tracking
                const stepMetadata = chunk.metadata as Record<string, unknown> | undefined;
                console.log(
                  `[ChatSSE] ${(stepMetadata?.emoji as string) || '⚙️'} Execution Step:`,
                  {
                    step_type: stepMetadata?.step_type,
                    step_name: stepMetadata?.step_name,
                    i18n_key: stepMetadata?.i18n_key,
                    category: stepMetadata?.category,
                    timestamp: new Date().toISOString(),
                  }
                );
              } else if (chunk.type === 'token') {
                // Token chunks are frequent - no logging needed
              } else if (
                chunk.type === 'hitl_question_token' ||
                chunk.type === 'hitl_clarification_token' ||
                chunk.type === 'hitl_rejection_token' ||
                chunk.type === 'content_replacement'
              ) {
                // HITL streaming tokens and content replacements - no logging needed
                // These are frequent and would flood the console
              } else {
                // Unknown chunk type - log for debugging
                console.log(`[ChatSSE] ⚪ ${chunk.type}:`, chunk);
              }

              // CRITICAL: Skip chunk if stream was cancelled
              // This prevents race condition where buffered chunks from previous
              // request are processed after a new request has started
              if (this.isCancelled) {
                console.log(`[ChatSSE] ⏭️ Skipping chunk (stream cancelled):`, chunk.type);
                continue;
              }

              onChunk(chunk);
            } catch (parseError) {
              console.warn('[ChatSSEClient] Failed to parse chunk:', data, parseError);
            }
          } else if (line.startsWith(': heartbeat')) {
            // Heartbeat - keep connection alive, no logging needed
          } else if (line.startsWith('retry:')) {
            // Retry interval sent by server - no logging needed
          }
        }
      }
    } catch (error) {
      console.error('[ChatSSEClient] Fetch stream error:', error);
      this.isConnected = false;

      // Handle network errors with i18n-ready error codes
      if (error instanceof DOMException && error.name === 'AbortError') {
        // Stream was cancelled by user - this is expected, don't call onError
        console.log('[ChatSSEClient] Stream cancelled by user');
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
            window.location.href =
              '/login?redirect=' + encodeURIComponent(window.location.pathname);
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
    } finally {
      // Cleanup AbortController
      this.abortController = null;
    }
  }

  /**
   * Cancel current stream
   * Aborts the fetch request and stops streaming
   * Sets isCancelled flag to ignore any buffered chunks still being processed
   */
  cancel(): void {
    if (this.abortController) {
      console.log('[ChatSSEClient] Cancelling stream...');
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
