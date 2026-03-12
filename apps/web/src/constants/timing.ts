/**
 * Timing constants for the frontend application.
 * Centralized configuration for all timeouts, intervals, and delays.
 */

/**
 * Auto-refresh intervals for real-time data (in milliseconds)
 */
export const REFRESH_INTERVALS = {
  /** User statistics auto-refresh */
  USER_STATISTICS: 30_000, // 30 seconds

  /** Chat reconnect attempts */
  CHAT_RECONNECT: 5_000, // 5 seconds

  /** SSE heartbeat interval */
  HEARTBEAT: 15_000, // 15 seconds

  /** Conversation list refresh */
  CONVERSATIONS: 60_000, // 1 minute
} as const;

/**
 * Timeout values for various operations (in milliseconds)
 */
export const TIMEOUTS = {
  /** OAuth redirect delay after successful auth */
  OAUTH_REDIRECT: 3_000, // 3 seconds

  /** API request timeout */
  API_REQUEST: 30_000, // 30 seconds

  /** SSE reconnection delay */
  SSE_RECONNECT: 5_000, // 5 seconds

  /** Tool approval timeout (user has 5 minutes to approve) */
  TOOL_APPROVAL: 300_000, // 5 minutes

  /** Debounce delay for search inputs */
  SEARCH_DEBOUNCE: 300, // 300 milliseconds
} as const;

/**
 * SSE (Server-Sent Events) configuration
 */
export const SSE_CONFIG = {
  /** Client-side retry interval (should match backend configuration) */
  RETRY_INTERVAL: 5_000, // 5 seconds

  /** Maximum number of retry attempts before giving up */
  MAX_RETRIES: 3,

  /** Heartbeat interval (should match backend SSE_HEARTBEAT_INTERVAL) */
  HEARTBEAT_INTERVAL: 15_000, // 15 seconds
} as const;

/**
 * Animation and transition durations (in milliseconds)
 */
export const DURATIONS = {
  /** Toast notification display time */
  TOAST: 5_000, // 5 seconds

  /** Loading indicator minimum display time (prevents flashing) */
  MIN_LOADING: 200, // 200 milliseconds

  /** Modal transition duration */
  MODAL_TRANSITION: 150, // 150 milliseconds
} as const;
