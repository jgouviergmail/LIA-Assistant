'use client';

/**
 * The person's execution mode (ADR-070, ADR-390), read and saved for the chat
 * header's menu.
 *
 * Two sources, each the authority on ONE fact: the account (`/auth/me`, through
 * `useAuth`) says which mode is chosen, as every other surface reads it; the
 * preference endpoint says what « auto » does on THIS instance (it decides turn
 * by turn, or always runs one engine when the instance lacks the other's
 * means). A save answers with both, so the instance's verdict is as fresh as
 * the choice it follows.
 *
 * One save at a time: a choice made while another is on its way is refused by
 * the guard, never by disabling the control that holds the focus, and a failed
 * save leaves the account — and so the selected mode — as it was.
 */

import { useCallback, useState } from 'react';

import { useApiMutation } from '@/hooks/useApiMutation';
import { useApiQuery } from '@/hooks/useApiQuery';
import { useAuth } from '@/hooks/useAuth';
import {
  executionModeOf,
  type AutoModeResolution,
  type ExecutionMode,
} from '@/lib/execution-mode';

const ENDPOINT = '/auth/me/execution-mode-preference';
const COMPONENT = 'useExecutionModePreference';

/** `GET` / `PATCH /auth/me/execution-mode-preference`, as the API answers. */
export interface ExecutionModePreference {
  execution_mode: ExecutionMode;
  auto_resolution: AutoModeResolution;
}

/**
 * What became of a choice: `saved` and read back, `ignored` because there was
 * nothing to send (no account yet, another save on its way, the mode already
 * chosen), or `failed` on the way — the only outcome worth an error.
 */
export type ModeChoiceOutcome = 'saved' | 'ignored' | 'failed';

export interface ExecutionModePreferenceState {
  /** The account's chosen mode; the pipeline, the default, until it is known. */
  mode: ExecutionMode;
  /** What « auto » does on this instance; `null` until the instance said. */
  autoResolution: AutoModeResolution | null;
  /** The mode being saved, or `null` when nothing is. */
  saving: ExecutionMode | null;
  /** Re-read what « auto » does here — the menu asks each time it opens. */
  refresh: () => Promise<void>;
  /** Save a mode; `saved` once the account was read back with it. */
  choose: (mode: ExecutionMode) => Promise<ModeChoiceOutcome>;
}

export function useExecutionModePreference(): ExecutionModePreferenceState {
  const { user, refreshUser } = useAuth();
  const [saving, setSaving] = useState<ExecutionMode | null>(null);
  const preference = useApiQuery<ExecutionModePreference>(ENDPOINT, {
    componentName: COMPONENT,
    enabled: user !== null,
  });
  const { mutate } = useApiMutation<{ execution_mode: ExecutionMode }, ExecutionModePreference>({
    method: 'PATCH',
    componentName: COMPONENT,
    retainResponse: false,
  });
  const mode = executionModeOf(user?.execution_mode);
  const { acceptData } = preference;
  const signedIn = user !== null;

  const choose = useCallback(
    async (next: ExecutionMode): Promise<ModeChoiceOutcome> => {
      if (!signedIn || saving !== null || next === mode) return 'ignored';
      setSaving(next);
      try {
        const stored = await mutate(ENDPOINT, { execution_mode: next });
        // An empty answer says nothing new: the verdict already read stands.
        if (stored) acceptData(stored);
        await refreshUser();
        return 'saved';
      } catch {
        // useApiMutation already logged the failure with its status.
        return 'failed';
      } finally {
        setSaving(null);
      }
    },
    [signedIn, saving, mode, mutate, acceptData, refreshUser]
  );

  return {
    mode,
    autoResolution: preference.data?.auto_resolution ?? null,
    saving,
    // Disabled until the account is known, so a refresh asks nothing before.
    refresh: preference.refetch,
    choose,
  };
}
