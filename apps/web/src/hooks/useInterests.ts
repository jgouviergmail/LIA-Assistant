import { useState, useCallback } from 'react';
import { useApiQuery } from './useApiQuery';
import { useApiMutation } from './useApiMutation';

/**
 * Interest category types matching backend schema.
 */
export type InterestCategory =
  | 'technology'
  | 'science'
  | 'culture'
  | 'sports'
  | 'finance'
  | 'travel'
  | 'nature'
  | 'health'
  | 'entertainment'
  | 'other';

/**
 * Interest status types.
 */
export type InterestStatus = 'active' | 'blocked' | 'dormant';

/**
 * Interest feedback types.
 */
export type InterestFeedback = 'thumbs_up' | 'thumbs_down' | 'block';

/**
 * Interest item from the API.
 */
export interface Interest {
  id: string;
  topic: string;
  category: InterestCategory;
  weight: number; // Computed effective weight
  status: InterestStatus;
  positive_signals: number;
  negative_signals: number;
  last_mentioned_at: string | null;
  last_notified_at: string | null;
  created_at: string;
}

/**
 * Interest creation payload.
 */
export interface InterestCreate {
  topic: string;
  category: InterestCategory;
}

/**
 * Interest update payload (partial update).
 */
export interface InterestUpdate {
  topic?: string;
  category?: InterestCategory;
  positive_signals?: number;
  negative_signals?: number;
}

/**
 * Interest list response from API.
 */
export interface InterestListResponse {
  interests: Interest[];
  total: number;
  active_count: number;
  blocked_count: number;
}

/**
 * Interest settings response.
 */
export interface InterestSettings {
  interests_enabled: boolean;
  interests_notify_start_hour: number;
  interests_notify_end_hour: number;
  interests_notify_min_per_day: number;
  interests_notify_max_per_day: number;
}

/**
 * Interest settings update payload.
 */
export interface InterestSettingsUpdate {
  interests_enabled?: boolean;
  interests_notify_start_hour?: number;
  interests_notify_end_hour?: number;
  interests_notify_min_per_day?: number;
  interests_notify_max_per_day?: number;
}

/**
 * Interest category info for UI.
 */
export interface InterestCategoryInfo {
  value: InterestCategory;
  label: string;
  description: string;
}

/**
 * Category icons mapping.
 */
export const INTEREST_CATEGORY_ICONS: Record<InterestCategory, string> = {
  technology: '💻',
  science: '🔬',
  culture: '🎭',
  sports: '⚽',
  finance: '💰',
  travel: '✈️',
  nature: '🌿',
  health: '💪',
  entertainment: '🎬',
  other: '📌',
};

/**
 * Get weight color class based on weight value.
 */
export function getWeightColorClass(weight: number): string {
  if (weight >= 0.8) return 'text-green-500';
  if (weight >= 0.6) return 'text-emerald-500';
  if (weight >= 0.4) return 'text-yellow-500';
  if (weight >= 0.2) return 'text-orange-500';
  return 'text-red-500';
}

/**
 * Get weight badge variant based on weight value.
 */
export function getWeightBadgeVariant(
  weight: number
): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (weight >= 0.7) return 'default';
  if (weight >= 0.4) return 'secondary';
  return 'outline';
}

/**
 * Hook for managing user interests.
 * Uses optimistic updates to prevent focus loss during mutations.
 */
export function useInterests() {
  const [categoryFilter, setCategoryFilter] = useState<InterestCategory | null>(null);
  const [statusFilter, setStatusFilter] = useState<InterestStatus | null>(null);

  // Fetch interests
  const {
    data: interestsData,
    loading,
    error,
    refetch,
    setData,
  } = useApiQuery<InterestListResponse>('/interests', {
    componentName: 'useInterests',
    initialData: { interests: [], total: 0, active_count: 0, blocked_count: 0 },
  });

  // Fetch categories
  const { data: categoriesData } = useApiQuery<{ categories: InterestCategoryInfo[] }>(
    '/interests/categories',
    {
      componentName: 'useInterests',
      initialData: { categories: [] },
    }
  );

  // Fetch settings
  const {
    data: settingsData,
    loading: settingsLoading,
    setData: setSettingsData,
    refetch: refetchSettings,
  } = useApiQuery<InterestSettings>('/interests/settings', {
    componentName: 'useInterests',
  });

  // Create mutation
  const { mutate: createMutate, loading: creating } = useApiMutation<InterestCreate, Interest>({
    method: 'POST',
    componentName: 'useInterests',
  });

  // Delete mutation
  const { mutate: deleteMutate, loading: deleting } = useApiMutation({
    method: 'DELETE',
    componentName: 'useInterests',
  });

  // Delete all mutation
  const { mutate: deleteAllMutate, loading: deletingAll } = useApiMutation({
    method: 'DELETE',
    componentName: 'useInterests',
  });

  // Feedback mutation
  const { mutate: feedbackMutate, loading: submittingFeedback } = useApiMutation({
    method: 'POST',
    componentName: 'useInterests',
  });

  // Settings mutation
  const { mutate: updateSettingsMutate, loading: updatingSettings } = useApiMutation({
    method: 'PATCH',
    componentName: 'useInterests',
  });

  // Update interest mutation
  const { mutate: updateMutate, loading: updating } = useApiMutation<InterestUpdate, Interest>({
    method: 'PATCH',
    componentName: 'useInterests',
  });

  /**
   * Create a new interest (optimistic update).
   */
  const createInterest = useCallback(
    async (data: InterestCreate): Promise<Interest | undefined> => {
      const result = await createMutate('/interests', data);

      if (result) {
        // Optimistic update: add the new interest to local state
        setData(prev => {
          if (!prev) return prev;
          return {
            ...prev,
            interests: [result, ...prev.interests],
            total: prev.total + 1,
            active_count: prev.active_count + 1,
          };
        });
      }

      return result;
    },
    [createMutate, setData]
  );

  /**
   * Delete an interest (optimistic update).
   */
  const deleteInterest = useCallback(
    async (interestId: string) => {
      // Find the interest first to know its status
      const interest = interestsData?.interests.find(i => i.id === interestId);

      await deleteMutate(`/interests/${interestId}`);

      // Optimistic update: remove from local state
      setData(prev => {
        if (!prev) return prev;
        return {
          ...prev,
          interests: prev.interests.filter(i => i.id !== interestId),
          total: Math.max(0, prev.total - 1),
          active_count:
            interest?.status === 'active' ? Math.max(0, prev.active_count - 1) : prev.active_count,
          blocked_count:
            interest?.status === 'blocked'
              ? Math.max(0, prev.blocked_count - 1)
              : prev.blocked_count,
        };
      });
    },
    [deleteMutate, setData, interestsData]
  );

  /**
   * Delete all interests.
   */
  const deleteAllInterests = useCallback(async () => {
    await deleteAllMutate('/interests/all', {});

    // Optimistic update: clear all interests
    setData(prev => {
      if (!prev) return prev;
      return {
        ...prev,
        interests: [],
        total: 0,
        active_count: 0,
        blocked_count: 0,
      };
    });
  }, [deleteAllMutate, setData]);

  /**
   * Submit feedback on an interest (optimistic update).
   */
  const submitFeedback = useCallback(
    async (interestId: string, feedback: InterestFeedback) => {
      await feedbackMutate(`/interests/${interestId}/feedback`, { feedback });

      // Optimistic update based on feedback type
      setData(prev => {
        if (!prev) return prev;
        const newInterests = prev.interests.map(i => {
          if (i.id !== interestId) return i;

          if (feedback === 'block') {
            return { ...i, status: 'blocked' as InterestStatus };
          } else if (feedback === 'thumbs_up') {
            return {
              ...i,
              positive_signals: i.positive_signals + 2,
              weight: Math.min(1, i.weight + 0.1),
            };
          } else {
            return {
              ...i,
              negative_signals: i.negative_signals + 2,
              weight: Math.max(0, i.weight - 0.1),
            };
          }
        });

        const activeCount = newInterests.filter(i => i.status === 'active').length;
        const blockedCount = newInterests.filter(i => i.status === 'blocked').length;

        return {
          ...prev,
          interests: newInterests,
          active_count: activeCount,
          blocked_count: blockedCount,
        };
      });
    },
    [feedbackMutate, setData]
  );

  /**
   * Update an existing interest (optimistic update).
   */
  const updateInterest = useCallback(
    async (interestId: string, data: InterestUpdate): Promise<Interest | undefined> => {
      const result = await updateMutate(`/interests/${interestId}`, data);

      if (result) {
        // Optimistic update: replace the interest in local state
        setData(prev => {
          if (!prev) return prev;
          return {
            ...prev,
            interests: prev.interests.map(i => (i.id === interestId ? result : i)),
          };
        });
      }

      return result;
    },
    [updateMutate, setData]
  );

  /**
   * Update interest notification settings.
   */
  const updateSettings = useCallback(
    async (data: InterestSettingsUpdate) => {
      // Optimistic update
      setSettingsData(prev => {
        if (!prev) return prev;
        return { ...prev, ...data };
      });

      try {
        await updateSettingsMutate('/interests/settings', data);
      } catch {
        // Revert on failure — refetch server state
        refetchSettings();
      }
    },
    [updateSettingsMutate, setSettingsData, refetchSettings]
  );

  // Filter interests client-side
  const filteredInterests = (interestsData?.interests ?? []).filter(interest => {
    if (categoryFilter && interest.category !== categoryFilter) return false;
    if (statusFilter && interest.status !== statusFilter) return false;
    return true;
  });

  return {
    interests: filteredInterests,
    allInterests: interestsData?.interests ?? [],
    total: interestsData?.total ?? 0,
    activeCount: interestsData?.active_count ?? 0,
    blockedCount: interestsData?.blocked_count ?? 0,
    categories: categoriesData?.categories ?? [],
    settings: settingsData,
    loading,
    settingsLoading,
    error,
    creating,
    deleting,
    deletingAll,
    submittingFeedback,
    updatingSettings,
    updating,
    categoryFilter,
    setCategoryFilter,
    statusFilter,
    setStatusFilter,
    refetch,
    createInterest,
    deleteInterest,
    deleteAllInterests,
    submitFeedback,
    updateSettings,
    updateInterest,
  };
}
