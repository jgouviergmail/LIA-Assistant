/**
 * Centralized constants for the web application.
 *
 * Following backend pattern (src/core/constants.py) for DRY compliance.
 * All magic numbers, default values, and configuration should be defined here.
 */

// ============================================================================
// PAGINATION DEFAULTS
// ============================================================================
// Must align with backend values in apps/api/src/core/pagination_helpers.py

/**
 * Default page size for standard list views.
 * Used for general user-facing lists.
 */
export const DEFAULT_PAGE_SIZE = 10;

/**
 * Default page size for admin sections.
 * Admin views typically display more items per page for efficiency.
 * Maximum value allowed by backend is 100 (MAX_PAGE_SIZE in pagination_helpers.py).
 */
export const ADMIN_DEFAULT_PAGE_SIZE = DEFAULT_PAGE_SIZE;

/**
 * Maximum page size allowed by the backend.
 * Requests exceeding this will be clamped to this value.
 */
export const MAX_PAGE_SIZE = 100;

/**
 * Minimum page size allowed.
 */
export const MIN_PAGE_SIZE = 1;

// ============================================================================
// ADMIN SECTION SPECIFIC
// ============================================================================

/**
 * Page size for LLM pricing administration.
 */
export const ADMIN_LLM_PRICING_PAGE_SIZE = DEFAULT_PAGE_SIZE;

/**
 * Page size for user administration.
 */
export const ADMIN_USERS_PAGE_SIZE = DEFAULT_PAGE_SIZE;

/**
 * Page size for Google API pricing administration.
 */
export const ADMIN_GOOGLE_API_PRICING_PAGE_SIZE = DEFAULT_PAGE_SIZE;

// ============================================================================
// DEBOUNCE DELAYS (milliseconds)
// ============================================================================

/**
 * Default debounce delay for search inputs.
 */
export const SEARCH_DEBOUNCE_MS = 300;

/**
 * Debounce delay for expensive operations.
 */
export const EXPENSIVE_DEBOUNCE_MS = 500;

// ============================================================================
// API TIMEOUTS (milliseconds)
// ============================================================================

/**
 * Default API request timeout.
 */
export const API_TIMEOUT_DEFAULT = 30000;

/**
 * Timeout for long-running operations (file uploads, etc.).
 */
export const API_TIMEOUT_LONG = 60000;

/**
 * Timeout for Server Actions.
 */
export const SERVER_ACTION_TIMEOUT = 10000;

// ============================================================================
// UI INTERACTIONS
// ============================================================================

/**
 * Minimum swipe distance in pixels to trigger carousel navigation.
 * Used by InlinePlaceCarousel for touch gesture detection.
 */
export const CAROUSEL_SWIPE_THRESHOLD_PX = 50;

// ============================================================================
// DEBUG PANEL
// ============================================================================

/**
 * Total width taken by the debug panel including gap.
 * Debug panel: 400px + gap-4 (16px) = 416px, rounded to 420px.
 * Used to calculate effective viewport width for responsive rendering.
 */
export const DEBUG_PANEL_TOTAL_WIDTH_PX = 420;

// ============================================================================
// OAUTH CONNECTOR HEALTH
// ============================================================================
// SIMPLIFIED DESIGN: Only shows modal for status=ERROR (refresh failed).
// Normal token expiration is handled silently by proactive refresh job.
// Settings fetched from backend via GET /connectors/health/settings.

/**
 * Polling interval for connector health checks (milliseconds).
 * FALLBACK ONLY - actual value comes from backend settings.
 */
export const OAUTH_HEALTH_POLLING_INTERVAL_MS = 5 * 60 * 1000;

/**
 * LocalStorage key for modal deduplication across tabs.
 */
export const OAUTH_HEALTH_TOAST_DEDUP_KEY = 'oauth_health_modal_shown';

/**
 * SessionStorage key for tracking pending OAuth reconnection.
 * Used to trigger refetch after OAuth flow completes.
 */
export const OAUTH_HEALTH_RECONNECT_PENDING_KEY = 'oauth_health_reconnect_pending';

// ============================================================================
// ONBOARDING
// ============================================================================
// Configuration for the onboarding tutorial displayed to new users.
// Must align with backend constant ONBOARDING_TOTAL_PAGES in apps/api/src/core/constants.py

/**
 * Total number of pages in the onboarding tutorial.
 * Pages: Welcome, Connectors, Personality, Memory, Interests, Notifications, Examples
 */
export const ONBOARDING_TOTAL_PAGES = 7;

/**
 * Scroll behavior for content reset on page change.
 */
export const ONBOARDING_SCROLL_BEHAVIOR = 'smooth' as const;

// ============================================================================
// VOICE INPUT (STT - Speech-to-Text)
// ============================================================================
// Configuration for WebSocket audio streaming and transcription.
// Must align with backend values in apps/api/src/core/config/voice.py

/**
 * WebSocket reconnection delays with exponential backoff (milliseconds).
 * After exhausting all delays, connection attempts stop.
 */
export const VOICE_INPUT_WS_RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 16000];

/**
 * Heartbeat interval for WebSocket keepalive (milliseconds).
 * Sends PING every 30 seconds to prevent idle timeout.
 */
export const VOICE_INPUT_HEARTBEAT_INTERVAL_MS = 30000;

/**
 * Audio recording sample rate in Hz.
 * Must match backend STT service expectation (Sherpa-onnx requires 16kHz).
 */
export const VOICE_INPUT_SAMPLE_RATE = 16000;

/**
 * Audio chunk size for streaming (samples per chunk).
 * 4096 samples at 16kHz = 256ms chunks.
 */
export const VOICE_INPUT_CHUNK_SIZE = 4096;

// ============================================================================
// VOICE MODE (Wake Word Detection + Talk Mode)
// ============================================================================
// Configuration for Sherpa-onnx WASM KWS and Voice Activity Detection.
// Reference: plan zippy-drifting-valley.md (section 2.5)

/**
 * Default wake word for keyword spotting (display value).
 * User-facing wake word: "OK Guy" or "OK Guys" (always in English).
 * Must match keywords.txt file in public/models/.
 */
export const VOICE_MODE_DEFAULT_WAKE_WORD = 'OK Guy';

/**
 * Default keyword detection sensitivity (0.0-1.0).
 * Higher = fewer false negatives, more false positives.
 */
export const VOICE_MODE_KWS_THRESHOLD = 0.25;

/**
 * Voice Activity Detection silence threshold (milliseconds).
 * Duration of silence to detect end of speech.
 * 750ms balances responsiveness with avoiding mid-sentence cuts.
 */
export const VOICE_MODE_VAD_SILENCE_MS = 750;

/**
 * VAD energy threshold for speech detection.
 * Audio energy below this is considered silence.
 * Typical values: 0.01 (very sensitive) to 0.05 (less sensitive)
 * If recording never stops, increase this value.
 */
export const VOICE_MODE_VAD_ENERGY_THRESHOLD = 0.02;

/**
 * Minimum speech duration to consider valid (milliseconds).
 * Prevents very short sounds from triggering transcription.
 */
export const VOICE_MODE_MIN_SPEECH_MS = 500;

/**
 * Maximum recording duration in voice mode (seconds).
 * Prevents runaway recordings.
 */
export const VOICE_MODE_MAX_RECORDING_SECONDS = 60;

/**
 * Idle timeout before voice mode auto-disables (seconds).
 * If no wake word detected for this duration, mode disables.
 */
export const VOICE_MODE_IDLE_TIMEOUT_SECONDS = 300;

/**
 * LocalStorage key for voice mode enabled preference.
 */
export const VOICE_MODE_ENABLED_KEY = 'voice_mode_enabled';

/**
 * Touch padding tolerance (px) for push-to-talk touch move cancellation.
 * Allows small finger movements without accidentally stopping the recording.
 */
export const VOICE_PTT_TOUCH_PADDING_PX = 20;

/**
 * Timeout (ms) for voice recording setup (getUserMedia + WebSocket connect).
 * If setup takes longer than this, abort with an error to avoid blocking the user.
 * Covers slow mobile networks, permission dialog left open, etc.
 */
export const VOICE_RECORDING_SETUP_TIMEOUT_MS = 10000;
