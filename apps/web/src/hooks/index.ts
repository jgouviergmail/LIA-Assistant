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
export { usePaginatedQuery } from './usePaginatedQuery';
export type {
  PaginatedResponse,
  UsePaginatedQueryOptions,
  UsePaginatedQueryResult,
} from './usePaginatedQuery';
export { useLanguageParam } from './useLanguageParam';

// LOT 6: Draft Actions
export { useDraftActions } from './useDraftActions';
export type { UseDraftActionsReturn } from './useDraftActions';

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

// Long-term Memory
export { useMemories, getEmotionalEmoji, getEmotionalLabel } from './useMemories';
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
export type { FCMPermissionStatus, UseFCMTokenReturn } from './useFCMToken';

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

// Form handling
export { useFormHandler } from './useFormHandler';
export type { UseFormHandlerOptions, UseFormHandlerReturn } from './useFormHandler';

// Admin Broadcast
export { useBroadcast } from './useBroadcast';
