/**
 * API Configuration
 *
 * Centralized configuration for API URLs and endpoints.
 * Eliminates hardcoded URLs throughout the codebase and provides
 * a single source of truth for all API-related constants.
 *
 * Usage:
 *   import { API_BASE_URL, API_ENDPOINTS } from '@/lib/api-config';
 *
 *   // Use in fetch/axios calls
 *   const response = await fetch(API_ENDPOINTS.AUTH.LOGIN, {...});
 *
 *   // Use in SSE connections
 *   const eventSource = new EventSource(API_ENDPOINTS.CHAT.STREAM);
 *
 * Migration note:
 *   Previously hardcoded in:
 *   - hooks/useChat.ts (line 64)
 *   - Multiple components with manual URL construction
 *
 * References:
 *   - ADR-001: Constants Centralization Strategy
 */

// ============================================================================
// BASE CONFIGURATION
// ============================================================================

/**
 * Base URL for API requests.
 *
 * Reads from environment variable NEXT_PUBLIC_API_URL.
 * Falls back to localhost:8000 for development.
 *
 * IMPORTANT: In production, NEXT_PUBLIC_API_URL must be set correctly.
 */
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

/**
 * API version prefix.
 * All endpoints are prefixed with this value.
 */
export const API_PREFIX = '/api/v1';

/**
 * Full API URL with version prefix.
 * Use this as the base for all endpoint constructions.
 */
export const API_URL = `${API_BASE_URL}${API_PREFIX}`;

// ============================================================================
// ENDPOINT DEFINITIONS
// ============================================================================

/**
 * All API endpoints organized by domain.
 *
 * Structure:
 *   - Each domain has its own namespace
 *   - Endpoints include full path from API root
 *   - Dynamic parameters use :param notation (to be replaced in usage)
 *
 * @example
 * // Static endpoint
 * await fetch(API_ENDPOINTS.AUTH.LOGIN, { method: 'POST', ... });
 *
 * // Dynamic endpoint
 * const url = API_ENDPOINTS.USERS.BY_ID.replace(':userId', userId);
 * await fetch(url);
 */
export const API_ENDPOINTS = {
  // ============================================================================
  // CLIENT CONFIGURATION
  // ============================================================================
  /** GET /config - Get client-side configuration (feature flags, rate limits, etc.) */
  CONFIG: `${API_URL}/config`,

  // ============================================================================
  // AUTHENTICATION & AUTHORIZATION
  // ============================================================================
  AUTH: {
    /** POST /auth/login - Email/password authentication */
    LOGIN: `${API_URL}/auth/login`,

    /** POST /auth/register - User registration */
    REGISTER: `${API_URL}/auth/register`,

    /** POST /auth/logout - Logout current session */
    LOGOUT: `${API_URL}/auth/logout`,

    /** POST /auth/logout-all - Logout all user sessions */
    LOGOUT_ALL: `${API_URL}/auth/logout-all`,

    /** GET /auth/me - Get current user profile */
    ME: `${API_URL}/auth/me`,

    /** POST /auth/verify-email - Verify email with token */
    VERIFY_EMAIL: `${API_URL}/auth/verify-email`,

    /** POST /auth/resend-verification - Resend verification email */
    RESEND_VERIFICATION: `${API_URL}/auth/resend-verification`,

    /** POST /auth/forgot-password - Request password reset */
    FORGOT_PASSWORD: `${API_URL}/auth/forgot-password`,

    /** POST /auth/reset-password - Reset password with token */
    RESET_PASSWORD: `${API_URL}/auth/reset-password`,

    /** GET /auth/google - Google OAuth initiation */
    GOOGLE_OAUTH: `${API_URL}/auth/google`,

    /** GET /auth/google/callback - Google OAuth callback */
    GOOGLE_OAUTH_CALLBACK: `${API_URL}/auth/google/callback`,
  },

  // ============================================================================
  // USERS
  // ============================================================================
  USERS: {
    /** GET /users - List all users (admin only) */
    LIST: `${API_URL}/users`,

    /** GET /users/:userId - Get user by ID */
    BY_ID: `${API_URL}/users/:userId`,

    /** PATCH /users/:userId - Update user */
    UPDATE: `${API_URL}/users/:userId`,

    /** DELETE /users/:userId - Delete user */
    DELETE: `${API_URL}/users/:userId`,

    /** GET /users/:userId/statistics - Get user token usage statistics */
    STATISTICS: `${API_URL}/users/:userId/statistics`,
  },

  // ============================================================================
  // CHAT & AGENTS
  // ============================================================================
  CHAT: {
    /** POST /chat/stream - SSE streaming chat endpoint */
    STREAM: `${API_URL}/chat/stream`,

    /** GET /chat/health - Agent service health check */
    HEALTH: `${API_URL}/agents/health`,
  },

  AGENTS: {
    /** GET /agents/health - Agent service health check */
    HEALTH: `${API_URL}/agents/health`,

    /** POST /agents/execute - Execute agent synchronously (non-streaming) */
    EXECUTE: `${API_URL}/agents/execute`,

    /** POST /agents/approve-tool - Approve/reject tool execution (HITL) */
    APPROVE_TOOL: `${API_URL}/agents/approve-tool`,

    /** POST /agents/chat/stream - SSE streaming chat endpoint */
    STREAM: `${API_URL}/agents/chat/stream`,

    /** GET /agents/inspection-mode - Get inspection mode status */
    INSPECTION_MODE: `${API_URL}/agents/inspection-mode`,
  },

  // ============================================================================
  // CONVERSATIONS
  // ============================================================================
  CONVERSATIONS: {
    /** GET /conversations - List user conversations */
    LIST: `${API_URL}/conversations`,

    /** POST /conversations - Create new conversation (manual) */
    CREATE: `${API_URL}/conversations`,

    /** GET /conversations/:conversationId - Get conversation by ID */
    BY_ID: `${API_URL}/conversations/:conversationId`,

    /** DELETE /conversations/:conversationId - Delete/reset conversation */
    DELETE: `${API_URL}/conversations/:conversationId`,

    /** GET /conversations/:conversationId/messages - Get conversation messages */
    MESSAGES: `${API_URL}/conversations/:conversationId/messages`,
  },

  // ============================================================================
  // CONNECTORS
  // ============================================================================
  CONNECTORS: {
    /** GET /connectors - List user connectors */
    LIST: `${API_URL}/connectors`,

    /** POST /connectors - Create connector */
    CREATE: `${API_URL}/connectors`,

    /** GET /connectors/:connectorId - Get connector by ID */
    BY_ID: `${API_URL}/connectors/:connectorId`,

    /** PATCH /connectors/:connectorId - Update connector */
    UPDATE: `${API_URL}/connectors/:connectorId`,

    /** DELETE /connectors/:connectorId - Delete connector */
    DELETE: `${API_URL}/connectors/:connectorId`,

    /** POST /connectors/:connectorId/oauth - Initiate OAuth flow */
    OAUTH_INITIATE: `${API_URL}/connectors/:connectorId/oauth`,

    /** POST /connectors/:connectorId/oauth/callback - OAuth callback */
    OAUTH_CALLBACK: `${API_URL}/connectors/:connectorId/oauth/callback`,

    // Admin endpoints
    /** GET /connectors/admin/global-config - Get global connector config (admin) */
    ADMIN_GLOBAL_CONFIG: `${API_URL}/connectors/admin/global-config`,

    /** PATCH /connectors/admin/global-config/:connectorType - Update global config (admin) */
    ADMIN_UPDATE_GLOBAL_CONFIG: `${API_URL}/connectors/admin/global-config/:connectorType`,

    // Apple iCloud endpoints
    /** POST /connectors/apple/validate - Validate Apple credentials */
    APPLE_VALIDATE: `${API_URL}/connectors/apple/validate`,

    /** POST /connectors/apple/activate - Activate Apple iCloud connectors */
    APPLE_ACTIVATE: `${API_URL}/connectors/apple/activate`,
  },

  // ============================================================================
  // ATTACHMENTS
  // ============================================================================
  ATTACHMENTS: {
    /** POST /attachments/upload - Upload a file attachment (multipart) */
    UPLOAD: `${API_URL}/attachments/upload`,

    /** GET /attachments/:attachmentId - Download/serve an attachment */
    BY_ID: `${API_URL}/attachments/:attachmentId`,

    /** DELETE /attachments/:attachmentId - Delete an attachment */
    DELETE: `${API_URL}/attachments/:attachmentId`,
  },

  // ============================================================================
  // RAG SPACES (Knowledge Documents)
  // ============================================================================
  RAG_SPACES: {
    /** GET /rag-spaces - List user spaces */
    LIST: `${API_URL}/rag-spaces`,

    /** POST /rag-spaces - Create a space */
    CREATE: `${API_URL}/rag-spaces`,

    /** GET /rag-spaces/:spaceId - Get space detail with documents */
    BY_ID: `${API_URL}/rag-spaces/:spaceId`,

    /** PATCH /rag-spaces/:spaceId - Update space */
    UPDATE: `${API_URL}/rag-spaces/:spaceId`,

    /** DELETE /rag-spaces/:spaceId - Delete space and all documents */
    DELETE: `${API_URL}/rag-spaces/:spaceId`,

    /** PATCH /rag-spaces/:spaceId/toggle - Toggle space activation */
    TOGGLE: `${API_URL}/rag-spaces/:spaceId/toggle`,

    /** POST /rag-spaces/:spaceId/documents - Upload document (multipart) */
    UPLOAD_DOCUMENT: `${API_URL}/rag-spaces/:spaceId/documents`,

    /** DELETE /rag-spaces/:spaceId/documents/:documentId - Delete document */
    DELETE_DOCUMENT: `${API_URL}/rag-spaces/:spaceId/documents/:documentId`,

    /** GET /rag-spaces/:spaceId/documents/:documentId/status - Polling status */
    DOCUMENT_STATUS: `${API_URL}/rag-spaces/:spaceId/documents/:documentId/status`,

    /** POST /rag-spaces/admin/reindex - Admin: reindex all (admin) */
    ADMIN_REINDEX: `${API_URL}/rag-spaces/admin/reindex`,

    /** GET /rag-spaces/admin/reindex/status - Admin: reindex status (admin) */
    ADMIN_REINDEX_STATUS: `${API_URL}/rag-spaces/admin/reindex/status`,
  },

  // ============================================================================
  // LLM ADMIN (Pricing & Models)
  // ============================================================================
  LLM: {
    /** GET /llm/models - List LLM models */
    MODELS: `${API_URL}/llm/models`,

    /** GET /llm/pricing - List LLM pricing */
    PRICING: `${API_URL}/llm/pricing`,

    /** POST /llm/pricing - Create pricing entry (admin) */
    CREATE_PRICING: `${API_URL}/llm/pricing`,

    /** PATCH /llm/pricing/:pricingId - Update pricing (admin) */
    UPDATE_PRICING: `${API_URL}/llm/pricing/:pricingId`,

    /** DELETE /llm/pricing/:pricingId - Delete pricing (admin) */
    DELETE_PRICING: `${API_URL}/llm/pricing/:pricingId`,

    /** GET /llm/currency-rates - Get currency exchange rates */
    CURRENCY_RATES: `${API_URL}/llm/currency-rates`,
  },
} as const;

// ============================================================================
// SSE (SERVER-SENT EVENTS) CONFIGURATION
// ============================================================================

/**
 * SSE connection configuration.
 * Used in useChat hook for streaming chat responses.
 */
export const SSE_CONFIG = {
  /**
   * Heartbeat interval (seconds).
   * How often the server sends keep-alive pings.
   */
  HEARTBEAT_INTERVAL: 15,

  /**
   * Max retry attempts before giving up.
   */
  MAX_RETRY_ATTEMPTS: 3,

  /**
   * Retry delay (milliseconds).
   * Time to wait before retrying connection.
   */
  RETRY_DELAY: 3000,

  /**
   * Connection timeout (milliseconds).
   * Max time to wait for initial connection.
   */
  CONNECTION_TIMEOUT: 10000,
} as const;

// ============================================================================
// TYPE EXPORTS
// ============================================================================

/**
 * Type for all API endpoints.
 * Useful for type-safe endpoint references.
 */
export type ApiEndpoints = typeof API_ENDPOINTS;

/**
 * Type for SSE configuration.
 */
export type SseConfig = typeof SSE_CONFIG;
