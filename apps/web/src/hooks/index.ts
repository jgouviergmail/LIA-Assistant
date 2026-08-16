/**
 * Central export file for all custom hooks
 */

export { useAuth } from './useAuth';
export { useChat } from './useChat';
export type { UseChatReturn } from './useChat';
export { useDebounce } from './useDebounce';
export { useApiQuery } from './useApiQuery';
export type { UseApiQueryOptions, UseApiQueryResult } from './useApiQuery';
export { useApiMutation } from './useApiMutation';
export type { UseApiMutationOptions, UseApiMutationResult } from './useApiMutation';
export { useLanguageParam } from './useLanguageParam';

// Personality System
export { usePersonality } from './usePersonality';
export type { UsePersonalityReturn } from './usePersonality';

// Geolocation
export { useGeolocation } from './useGeolocation';
export type {
  GeolocationCoordinates,
  GeolocationPermission,
  GeolocationState,
} from './useGeolocation';
export { useLastKnownLocationSync } from './useLastKnownLocationSync';

// Long-term Memory
export { useMemories, getEmotionalEmoji } from './useMemories';
export type { Memory, MemoryCategory, MemoryUpdate, MemoryListResponse } from './useMemories';

// Interest Learning System
export {
  useInterests,
  INTEREST_CATEGORY_ICONS,
  getWeightColorClass,
  getWeightBadgeVariant,
} from './useInterests';
export type {
  Interest,
  InterestCategory,
  InterestStatus,
  InterestFeedback,
  InterestSettings,
  InterestListResponse,
} from './useInterests';

// Voice Playback (TTS)
export { useVoicePlayback } from './useVoicePlayback';

// Push Notifications (FCM)
export { useFCMToken } from './useFCMToken';
export type { EnrollmentResult, FCMPermissionStatus, UseFCMTokenReturn } from './useFCMToken';

// Real-time Notifications (SSE)
export { useNotifications } from './useNotifications';
export type {
  Notification,
  NotificationType,
  UseNotificationsOptions,
  UseNotificationsReturn,
} from './useNotifications';

// LIA Gender Preference (masculine/feminine avatar)
export { useLiaGender } from './useLiaGender';

// Admin Broadcast
export { useBroadcast } from './useBroadcast';
