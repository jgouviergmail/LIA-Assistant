'use client';

/**
 * useWritingStyle — what LIA learned of how the person writes, their switch, and
 * forgetting it (ADR-383).
 *
 * Read through the account-scoped query, so another account's style never shows
 * across a sign-in; the switch answers the whole state it leaves, and forgetting
 * clears what was learned while keeping the switch.
 */

import { useCallback } from 'react';

import { useApiMutation } from '@/hooks/useApiMutation';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import type { WritingStyle } from '@/types/writing-style';

const ENDPOINT = '/writing-style';
const COMPONENT = 'useWritingStyle';

export interface UseWritingStyleReturn {
  style: WritingStyle | undefined;
  loading: boolean;
  error: boolean;
  refetch: () => void;
  /** Saves the switch; resolves to whether the server took it. */
  setEnabled: (enabled: boolean) => Promise<boolean>;
  /** Forgets what was learned; resolves to whether the server did. */
  forget: () => Promise<boolean>;
  saving: boolean;
  forgetting: boolean;
}

export function useWritingStyle(): UseWritingStyleReturn {
  const { data, loading, error, refetch, setData } = useApplicationAccountQuery<WritingStyle>(
    ENDPOINT,
    COMPONENT
  );
  const switching = useApiMutation<{ writing_style_enabled: boolean }, WritingStyle>({
    method: 'PATCH',
    componentName: COMPONENT,
  });
  const forgetting = useApiMutation<undefined, void>({
    method: 'DELETE',
    componentName: COMPONENT,
  });
  const { mutate: patch } = switching;
  const { mutate: remove } = forgetting;

  const setEnabled = useCallback(
    async (enabled: boolean) => {
      let saved: WritingStyle | undefined;
      try {
        saved = await patch(ENDPOINT, { writing_style_enabled: enabled });
      } catch {
        return false;
      }
      if (!saved) return false;
      setData(saved);
      return true;
    },
    [patch, setData]
  );

  const forget = useCallback(async () => {
    try {
      await remove(ENDPOINT);
    } catch {
      return false;
    }
    setData(current =>
      current
        ? { ...current, profile: null, mails_read: null, learned_at: null, renews_at: null }
        : current
    );
    return true;
  }, [remove, setData]);

  return {
    style: data,
    loading,
    error: Boolean(error),
    refetch: () => void refetch(),
    setEnabled,
    forget,
    saving: switching.loading,
    forgetting: forgetting.loading,
  };
}
