'use client';

/**
 * useWritingStyle — what LIA learned of how the person writes, their switch, learning
 * it at their click, and forgetting it (ADR-383).
 *
 * Read through the account-scoped query, so another account's style never shows
 * across a sign-in; the switch answers the whole state it leaves, a learning answers
 * how it ended and the page then reads back what was learned (the answer does not
 * carry it), and forgetting clears what was learned while keeping the switch. What the
 * assistant did from a conversation is read back on its own: a learning or a forgetting
 * it confirmed (`writing_style`), the switch it turned (`profile`).
 */

import { useCallback } from 'react';

import { useApiMutation } from '@/hooks/useApiMutation';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { useApplicationAccountState } from '@/hooks/useApplicationAccountState';
import { useApplicationResourceSync } from '@/hooks/useApplicationResourceSync';
import type { WritingStyle, WritingStyleLearning } from '@/types/writing-style';

const ENDPOINT = '/writing-style';
const LEARN_ENDPOINT = `${ENDPOINT}/learn`;
const COMPONENT = 'useWritingStyle';

/** How a click on « learn » ended: the server's answer, or what refused it. */
export type WritingStyleLearnResult =
  | { answered: true; learning: WritingStyleLearning }
  | { answered: false; error: unknown };

export interface UseWritingStyleReturn {
  style: WritingStyle | undefined;
  loading: boolean;
  error: boolean;
  refetch: () => void;
  /** Saves the switch; resolves to whether the server took it. */
  setEnabled: (enabled: boolean) => Promise<boolean>;
  /** Learns the style now, then reads back what was learned. */
  learn: () => Promise<WritingStyleLearnResult>;
  /** Forgets what was learned; resolves to whether the server did. */
  forget: () => Promise<boolean>;
  saving: boolean;
  /** A learning runs: from the click until what it learned is read back. */
  learning: boolean;
  forgetting: boolean;
}

export function useWritingStyle(): UseWritingStyleReturn {
  const { data, loading, error, refetch, refetchVerified, setData, ownerId } =
    useApplicationAccountQuery<WritingStyle>(ENDPOINT, COMPONENT);
  const switching = useApiMutation<{ writing_style_enabled: boolean }, WritingStyle>({
    method: 'PATCH',
    componentName: COMPONENT,
  });
  const learning = useApiMutation<undefined, WritingStyleLearning>({
    method: 'POST',
    componentName: COMPONENT,
    retainResponse: false,
  });
  const forgetting = useApiMutation<undefined, void>({
    method: 'DELETE',
    componentName: COMPONENT,
  });
  // The account's own act: a learning still running for the previous account of the tab
  // never shows as running for the next one.
  const [learningNow, setLearningNow] = useApplicationAccountState(ownerId, false);
  const { mutate: patch } = switching;
  const { mutate: post } = learning;
  const { mutate: remove } = forgetting;
  useApplicationResourceSync(ownerId, 'writing_style', refetch);
  useApplicationResourceSync(ownerId, 'profile', refetch);

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

  const learn = useCallback(async (): Promise<WritingStyleLearnResult> => {
    setLearningNow(true);
    try {
      let answer: WritingStyleLearning | undefined;
      try {
        answer = await post(LEARN_ENDPOINT);
      } catch (refusal) {
        return { answered: false, error: refusal };
      }
      if (!answer) return { answered: false, error: undefined };
      // The answer says how it ended; what was learned, and when, is the record's.
      await refetchVerified();
      return { answered: true, learning: answer };
    } finally {
      setLearningNow(false);
    }
  }, [post, refetchVerified, setLearningNow]);

  const forget = useCallback(async () => {
    try {
      await remove(ENDPOINT);
    } catch {
      return false;
    }
    setData(current =>
      current ? { ...current, profile: null, mails_read: null, learned_at: null } : current
    );
    return true;
  }, [remove, setData]);

  return {
    style: data,
    loading,
    error: Boolean(error),
    refetch: () => void refetch(),
    setEnabled,
    learn,
    forget,
    saving: switching.loading,
    learning: learningNow,
    forgetting: forgetting.loading,
  };
}
