/**
 * usePersonality Hook
 * Manages user's personality preference state and API interactions
 */

import { useState, useCallback, useEffect } from 'react';
import {
  fetchPersonalities,
  fetchCurrentPersonality,
  updateCurrentPersonality,
} from '@/lib/api/personality';
import { PersonalityListItem } from '@/types/personality';
import { logger } from '@/lib/logger';

export interface UsePersonalityReturn {
  /** List of available personalities */
  personalities: PersonalityListItem[];
  /** User's current personality (null = default) */
  currentPersonality: PersonalityListItem | null;
  /** Current personality ID */
  currentPersonalityId: string | null;
  /** Loading state for initial fetch */
  loading: boolean;
  /** Loading state for update operation */
  updating: boolean;
  /** Error state */
  error: Error | null;
  /** Update personality preference */
  updatePersonality: (personalityId: string | null) => Promise<void>;
  /** Refetch personalities and current preference */
  refetch: () => Promise<void>;
}

export function usePersonality(): UsePersonalityReturn {
  const [personalities, setPersonalities] = useState<PersonalityListItem[]>([]);
  const [currentPersonality, setCurrentPersonality] = useState<PersonalityListItem | null>(null);
  const [currentPersonalityId, setCurrentPersonalityId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      // Fetch both in parallel
      const [listResponse, currentResponse] = await Promise.all([
        fetchPersonalities(),
        fetchCurrentPersonality(),
      ]);

      setPersonalities(listResponse.personalities);
      setCurrentPersonality(currentResponse.personality);
      setCurrentPersonalityId(currentResponse.personality_id);
    } catch (err) {
      const errorObj = err instanceof Error ? err : new Error('Failed to load personalities');
      setError(errorObj);
      logger.error('personality_fetch_failed', errorObj, { hook: 'usePersonality' });
    } finally {
      setLoading(false);
    }
  }, []);

  const updatePersonality = useCallback(async (personalityId: string | null) => {
    setUpdating(true);
    setError(null);

    try {
      const response = await updateCurrentPersonality({ personality_id: personalityId });
      setCurrentPersonality(response.personality);
      setCurrentPersonalityId(response.personality_id);
    } catch (err) {
      const errorObj = err instanceof Error ? err : new Error('Failed to update personality');
      setError(errorObj);
      logger.error('personality_update_failed', errorObj, { hook: 'usePersonality' });
      throw errorObj;
    } finally {
      setUpdating(false);
    }
  }, []);

  // Fetch on mount
  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return {
    personalities,
    currentPersonality,
    currentPersonalityId,
    loading,
    updating,
    error,
    updatePersonality,
    refetch: fetchData,
  };
}
