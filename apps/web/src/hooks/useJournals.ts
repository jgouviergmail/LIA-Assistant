import { useCallback } from 'react';
import { useApiQuery } from './useApiQuery';
import { useApiMutation } from './useApiMutation';

/**
 * Journal theme types matching backend JournalTheme enum.
 */
export type JournalTheme = 'self_reflection' | 'user_observations' | 'ideas_analyses' | 'learnings';

/**
 * Journal entry mood types matching backend JournalEntryMood enum.
 */
export type JournalEntryMood = 'reflective' | 'curious' | 'satisfied' | 'concerned' | 'inspired';

/**
 * Journal entry status types.
 */
export type JournalEntryStatus = 'active' | 'archived';

/**
 * Journal entry source types.
 */
export type JournalEntrySource = 'conversation' | 'consolidation' | 'manual';

/**
 * Journal entry from the API.
 */
export interface JournalEntry {
  id: string;
  theme: JournalTheme;
  title: string;
  content: string;
  mood: JournalEntryMood;
  status: JournalEntryStatus;
  source: JournalEntrySource;
  personality_code: string | null;
  char_count: number;
  created_at: string;
  updated_at: string;
}

/**
 * Journal entry creation payload.
 */
export interface JournalEntryCreate {
  theme: JournalTheme;
  title: string;
  content: string;
  mood?: JournalEntryMood;
}

/**
 * Journal entry update payload (partial).
 */
export interface JournalEntryUpdate {
  title?: string;
  content?: string;
  mood?: JournalEntryMood;
}

/**
 * Theme count item.
 */
export interface ThemeCount {
  theme: JournalTheme;
  count: number;
}

/**
 * Journal entry list response from API.
 */
export interface JournalListResponse {
  entries: JournalEntry[];
  total: number;
  by_theme: ThemeCount[];
  total_chars: number;
  max_total_chars: number;
  usage_pct: number;
}

/**
 * Journal cost info from last background intervention.
 */
export interface JournalCostInfo {
  tokens_in: number | null;
  tokens_out: number | null;
  cost_eur: number | null;
  timestamp: string | null;
  source: string | null;
}

/**
 * Journal size info.
 */
export interface JournalSizeInfo {
  total_chars: number;
  max_total_chars: number;
  usage_pct: number;
}

/**
 * Journal settings response from API.
 */
export interface JournalSettings {
  journals_enabled: boolean;
  journal_consolidation_enabled: boolean;
  journal_consolidation_with_history: boolean;
  journal_max_total_chars: number;
  journal_context_max_chars: number;
  journal_max_entry_chars: number;
  journal_context_max_results: number;
  size_info: JournalSizeInfo;
  last_cost: JournalCostInfo;
}

/**
 * Journal settings update payload (partial).
 */
export interface JournalSettingsUpdate {
  journals_enabled?: boolean;
  journal_consolidation_enabled?: boolean;
  journal_consolidation_with_history?: boolean;
  journal_max_total_chars?: number;
  journal_context_max_chars?: number;
  journal_max_entry_chars?: number;
  journal_context_max_results?: number;
}

/**
 * Theme info from API.
 */
export interface JournalThemeInfo {
  code: string;
  label: string;
}

/**
 * Hook for journal entry CRUD operations and settings management.
 *
 * Uses optimistic updates to prevent focus loss during mutations.
 * Pattern: domains/interests/useInterests.ts
 */
export function useJournals() {
  // Fetch entries
  const {
    data: entriesData,
    loading,
    error,
    refetch,
    setData,
  } = useApiQuery<JournalListResponse>('/journals', {
    componentName: 'useJournals',
  });

  // Fetch settings
  const {
    data: settingsData,
    loading: settingsLoading,
    refetch: refetchSettings,
  } = useApiQuery<JournalSettings>('/journals/settings', {
    componentName: 'useJournals',
  });

  // Fetch themes
  const { data: themesData } = useApiQuery<{ themes: JournalThemeInfo[] }>('/journals/themes', {
    componentName: 'useJournals',
    initialData: { themes: [] },
  });

  // Mutations
  const { mutate: createMutate, loading: creating } = useApiMutation<
    JournalEntryCreate,
    JournalEntry
  >({
    method: 'POST',
    componentName: 'useJournals',
  });

  const { mutate: updateMutate, loading: updating } = useApiMutation<
    JournalEntryUpdate,
    JournalEntry
  >({
    method: 'PATCH',
    componentName: 'useJournals',
  });

  const { mutate: deleteMutate, loading: deleting } = useApiMutation({
    method: 'DELETE',
    componentName: 'useJournals',
  });

  const { mutate: deleteAllMutate } = useApiMutation({
    method: 'DELETE',
    componentName: 'useJournals',
  });

  const { mutate: updateSettingsMutate, loading: updatingSettings } = useApiMutation<
    JournalSettingsUpdate,
    JournalSettings
  >({
    method: 'PATCH',
    componentName: 'useJournals',
  });

  // Create entry
  const createEntry = useCallback(
    async (data: JournalEntryCreate) => {
      const result = await createMutate('/journals', data);
      if (result) {
        // Optimistic update
        setData(prev => {
          if (!prev) return prev;
          return {
            ...prev,
            entries: [result, ...prev.entries],
            total: prev.total + 1,
            total_chars: prev.total_chars + (result.char_count || 0),
          };
        });
      }
      return result;
    },
    [createMutate, setData]
  );

  // Update entry
  const updateEntry = useCallback(
    async (entryId: string, data: JournalEntryUpdate) => {
      const result = await updateMutate(`/journals/${entryId}`, data);
      if (result) {
        setData(prev => {
          if (!prev) return prev;
          return {
            ...prev,
            entries: prev.entries.map(e => (e.id === entryId ? result : e)),
          };
        });
      }
      return result;
    },
    [updateMutate, setData]
  );

  // Delete entry
  const deleteEntry = useCallback(
    async (entryId: string) => {
      const entry = entriesData?.entries.find(e => e.id === entryId);
      await deleteMutate(`/journals/${entryId}`);
      setData(prev => {
        if (!prev) return prev;
        return {
          ...prev,
          entries: prev.entries.filter(e => e.id !== entryId),
          total: Math.max(0, prev.total - 1),
          total_chars: Math.max(0, prev.total_chars - (entry?.char_count || 0)),
        };
      });
    },
    [deleteMutate, setData, entriesData]
  );

  // Delete all entries (GDPR)
  const deleteAllEntries = useCallback(async () => {
    await deleteAllMutate('/journals');
    setData(prev => {
      if (!prev) return prev;
      return {
        ...prev,
        entries: [],
        total: 0,
        by_theme: [],
        total_chars: 0,
        usage_pct: 0,
      };
    });
  }, [deleteAllMutate, setData]);

  // Update settings
  const updateSettings = useCallback(
    async (data: JournalSettingsUpdate) => {
      const result = await updateSettingsMutate('/journals/settings', data);
      if (result) {
        await refetchSettings();
      }
      return result;
    },
    [updateSettingsMutate, refetchSettings]
  );

  return {
    // Data
    entries: entriesData,
    settings: settingsData,
    themes: themesData?.themes ?? [],

    // Loading states
    isLoading: loading || settingsLoading,
    error,

    // Mutations
    createEntry,
    updateEntry,
    deleteEntry,
    deleteAllEntries,
    updateSettings,

    // Mutation states
    isCreating: creating,
    isUpdating: updating,
    isDeleting: deleting,
    isUpdatingSettings: updatingSettings,

    // Refetch
    refetchEntries: refetch,
    refetchSettings,
  };
}
