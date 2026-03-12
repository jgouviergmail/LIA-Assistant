/**
 * Voice Input Service for WebSocket audio streaming.
 *
 * Implements the BFF (Backend-for-Frontend) pattern for WebSocket authentication:
 * 1. Request ticket via REST endpoint (authenticated via HTTP-only session cookie)
 * 2. Connect WebSocket with ticket in query param
 * 3. Stream audio chunks for real-time transcription
 *
 * Protocol:
 * - Send: Binary audio chunks (PCM 16kHz mono int16)
 * - Send: Text "END" when done speaking
 * - Send: Text "PING" for heartbeat
 * - Receive: JSON {"type": "transcription", "text": "...", "duration_seconds": ...}
 * - Receive: JSON {"type": "pong"} for heartbeat response
 *
 * Close Codes:
 * - 4001: Invalid or expired ticket
 * - 4008: Idle timeout
 * - 4013: Audio buffer overflow
 * - 4029: Rate limited
 * - 1000: Normal close
 */

import { apiClient, ApiError } from '@/lib/api-client';
import { logger } from '@/lib/logger';
import {
  VOICE_INPUT_WS_RECONNECT_DELAYS,
  VOICE_INPUT_HEARTBEAT_INTERVAL_MS,
} from '@/lib/constants';

// ============================================================================
// Types
// ============================================================================

/**
 * Response from POST /voice/ticket endpoint.
 */
export interface WebSocketTicketResponse {
  ticket: string;
  ttl_seconds: number;
}

/**
 * Transcription result from WebSocket.
 */
export interface TranscriptionResult {
  type: 'transcription';
  text: string;
  duration_seconds: number;
}

/**
 * Pong response from WebSocket heartbeat.
 */
export interface PongResponse {
  type: 'pong';
}

/**
 * Union type for all WebSocket message types.
 */
export type WebSocketMessage = TranscriptionResult | PongResponse;

/**
 * Voice input service configuration.
 */
export interface VoiceInputServiceConfig {
  /** Callback when transcription is received */
  onTranscription: (text: string, durationSeconds: number) => void;
  /** Callback when connection state changes */
  onConnectionChange?: (isConnected: boolean) => void;
  /** Callback on error */
  onError?: (error: Error) => void;
}

// ============================================================================
// Service Class
// ============================================================================

/**
 * Voice Input Service for managing WebSocket audio streaming.
 *
 * Usage:
 * ```ts
 * const service = new VoiceInputService({
 *   onTranscription: (text, duration) => console.log(text),
 * });
 *
 * await service.connect();
 * service.sendAudio(audioChunk);
 * service.endAudio();
 * service.disconnect();
 * ```
 */
export class VoiceInputService {
  private ws: WebSocket | null = null;
  private heartbeatInterval: ReturnType<typeof setInterval> | null = null;
  private reconnectAttempt = 0;
  private reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
  private isDisposed = false;
  private config: VoiceInputServiceConfig;

  constructor(config: VoiceInputServiceConfig) {
    this.config = config;
  }

  /**
   * Check if WebSocket is currently connected.
   */
  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  /**
   * Acquire authentication ticket from BFF endpoint.
   * Uses session cookie for authentication.
   */
  private async acquireTicket(): Promise<string> {
    try {
      const response = await apiClient.post<WebSocketTicketResponse>('/voice/ticket');

      logger.debug('voice_input_ticket_acquired', {
        component: 'VoiceInputService',
        ttl_seconds: response.ttl_seconds,
      });

      return response.ticket;
    } catch (error) {
      const apiError = error as ApiError;

      logger.error('voice_input_ticket_failed', apiError, {
        component: 'VoiceInputService',
        status: apiError.status,
      });

      throw new Error(`Failed to acquire WebSocket ticket: ${apiError.message}`);
    }
  }

  /**
   * Build WebSocket URL with ticket.
   */
  private buildWebSocketUrl(ticket: string): string {
    // Get API URL (empty string for relative URLs in dev)
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || '';

    // Convert HTTP to WS protocol
    let wsBase: string;
    if (apiUrl) {
      wsBase = apiUrl.replace(/^http/, 'ws');
    } else {
      // Relative URL - construct from current location
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      wsBase = `${protocol}//${window.location.host}`;
    }

    return `${wsBase}/api/v1/voice/ws/audio?ticket=${encodeURIComponent(ticket)}`;
  }

  /**
   * Connect to the WebSocket audio endpoint.
   * Automatically acquires ticket and handles connection.
   */
  async connect(): Promise<void> {
    if (this.isDisposed) {
      throw new Error('VoiceInputService has been disposed');
    }

    if (this.isConnected) {
      logger.debug('voice_input_already_connected', { component: 'VoiceInputService' });
      return;
    }

    try {
      // Step 1: Acquire ticket (BFF pattern)
      const ticket = await this.acquireTicket();

      // Step 2: Build WebSocket URL
      const wsUrl = this.buildWebSocketUrl(ticket);

      // Step 3: Create WebSocket connection
      await this.createWebSocket(wsUrl);

    } catch (error) {
      const err = error instanceof Error ? error : new Error(String(error));
      this.config.onError?.(err);
      throw err;
    }
  }

  /**
   * Create and configure WebSocket connection.
   */
  private createWebSocket(url: string): Promise<void> {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(url);
      this.ws = ws;

      ws.onopen = () => {
        this.reconnectAttempt = 0;
        this.config.onConnectionChange?.(true);
        this.startHeartbeat();

        logger.info('voice_input_connected', { component: 'VoiceInputService' });
        resolve();
      };

      ws.onmessage = (event) => {
        this.handleMessage(event.data);
      };

      ws.onclose = (event) => {
        this.stopHeartbeat();
        this.config.onConnectionChange?.(false);

        logger.info('voice_input_disconnected', {
          component: 'VoiceInputService',
          code: event.code,
          reason: event.reason,
          wasClean: event.wasClean,
        });

        // Auto-reconnect on unexpected close (not clean close or normal close)
        if (!event.wasClean && event.code !== 1000 && !this.isDisposed) {
          this.scheduleReconnect();
        }
      };

      ws.onerror = () => {
        const error = new Error('WebSocket connection error');

        logger.error('voice_input_error', error, { component: 'VoiceInputService' });

        this.config.onError?.(error);
        reject(error);
      };
    });
  }

  /**
   * Handle incoming WebSocket message.
   */
  private handleMessage(data: string): void {
    try {
      const message = JSON.parse(data) as WebSocketMessage;

      if (message.type === 'transcription') {
        const result = message as TranscriptionResult;

        logger.debug('voice_input_transcription', {
          component: 'VoiceInputService',
          text_length: result.text.length,
          duration_seconds: result.duration_seconds,
        });

        this.config.onTranscription(result.text, result.duration_seconds);

      } else if (message.type === 'pong') {
        logger.debug('voice_input_pong', { component: 'VoiceInputService' });
      }
    } catch (error) {
      logger.error(
        'voice_input_message_parse_error',
        error instanceof Error ? error : new Error(String(error)),
        { component: 'VoiceInputService' }
      );
    }
  }

  /**
   * Start heartbeat interval.
   */
  private startHeartbeat(): void {
    this.stopHeartbeat();

    this.heartbeatInterval = setInterval(() => {
      if (this.isConnected) {
        this.ws?.send('PING');
      }
    }, VOICE_INPUT_HEARTBEAT_INTERVAL_MS);
  }

  /**
   * Stop heartbeat interval.
   */
  private stopHeartbeat(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  /**
   * Schedule reconnection with exponential backoff.
   */
  private scheduleReconnect(): void {
    if (this.reconnectAttempt >= VOICE_INPUT_WS_RECONNECT_DELAYS.length) {
      logger.warn('voice_input_reconnect_exhausted', {
        component: 'VoiceInputService',
        attempts: this.reconnectAttempt,
      });
      return;
    }

    const delay = VOICE_INPUT_WS_RECONNECT_DELAYS[this.reconnectAttempt];
    this.reconnectAttempt++;

    logger.debug('voice_input_reconnecting', {
      component: 'VoiceInputService',
      attempt: this.reconnectAttempt,
      delay_ms: delay,
    });

    this.reconnectTimeout = setTimeout(() => {
      this.connect().catch(() => {
        // Error already logged in connect()
      });
    }, delay);
  }

  /**
   * Send audio chunk to server.
   * Audio must be PCM 16kHz mono int16 format.
   */
  sendAudio(audioData: ArrayBuffer): void {
    if (!this.isConnected) {
      logger.warn('voice_input_send_not_connected', { component: 'VoiceInputService' });
      return;
    }

    this.ws?.send(audioData);
  }

  /**
   * Signal end of audio stream.
   * Server will process buffered audio and return transcription.
   */
  endAudio(): void {
    if (!this.isConnected) {
      logger.warn('voice_input_end_not_connected', { component: 'VoiceInputService' });
      return;
    }

    this.ws?.send('END');

    logger.debug('voice_input_end_sent', { component: 'VoiceInputService' });
  }

  /**
   * Disconnect from WebSocket.
   */
  disconnect(): void {
    // Cancel pending reconnect
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }

    this.stopHeartbeat();

    if (this.ws) {
      this.ws.close(1000, 'User disconnect');
      this.ws = null;
    }

    this.reconnectAttempt = 0;

    logger.debug('voice_input_disconnected_manual', { component: 'VoiceInputService' });
  }

  /**
   * Dispose of the service.
   * Releases all resources and prevents further use.
   */
  dispose(): void {
    this.isDisposed = true;
    this.disconnect();

    logger.debug('voice_input_disposed', { component: 'VoiceInputService' });
  }
}
