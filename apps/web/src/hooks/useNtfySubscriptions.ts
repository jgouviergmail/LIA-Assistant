/**
 * useNtfySubscriptions — the ntfy settings of an account (ADR-391).
 *
 * ntfy delivers LIA's notifications to any app subscribed to a TOPIC on a server: the instance's
 * own, or a public one the person names. This hook reads the account's subscriptions and runs
 * the four verbs (subscribe, change, remove, test). After a success the list is re-read, never
 * patched by hand, and the verb resolves once it was; a refusal comes back WITH its stable code
 * (`ntfy_*`), which the screen translates (label-key doctrine), and re-reads nothing.
 */

import { useCallback } from 'react';

import { useApiMutation } from '@/hooks/useApiMutation';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { getApiErrorCode } from '@/lib/api-error';

export type NtfyServerKind = 'instance' | 'custom';
export type NtfyContent = 'minimal' | 'full';

/** How a publication ended — the API's `NtfyOutcome`. */
export type NtfyOutcome =
  | 'sent'
  | 'auth_refused'
  | 'not_found'
  | 'too_large'
  | 'rate_limited'
  | 'refused'
  | 'server_error'
  | 'unreachable'
  | 'no_answer'
  | 'url_refused'
  | 'not_configured';

export interface NtfySubscriptionView {
  id: string;
  server_kind: NtfyServerKind;
  /** The address an app subscribes to. */
  server_url: string;
  /** A password, shown to its owner; null when it no longer decrypts (remove it). */
  topic: string | null;
  has_token: boolean;
  content: NtfyContent;
  is_active: boolean;
  last_sent_at: string | null;
  last_error_code: NtfyOutcome | null;
  last_error_at: string | null;
  created_at: string;
  /** The `ntfy://` link that subscribes the app in one tap, when one can be written. */
  subscribe_link: string | null;
}

export interface NtfyOverview {
  /** The instance server people subscribe to; null when the instance offers none. */
  instance_url: string | null;
  custom_servers_enabled: boolean;
  max_subscriptions: number;
  subscriptions: NtfySubscriptionView[];
}

export interface NtfySubscriptionInput {
  server: NtfyServerKind;
  server_url?: string;
  topic?: string;
  token?: string;
  content: NtfyContent;
}

export interface NtfySubscriptionChange {
  content?: NtfyContent;
  is_active?: boolean;
}

/** One verb's outcome: its stable refusal code travels WITH it, never through state. */
export interface NtfyActionResult<T = undefined> {
  ok: boolean;
  errorCode: string | null;
  data?: T;
}

const ENDPOINT = '/notifications/ntfy';
const COMPONENT = 'useNtfySubscriptions';

/**
 * The ntfy settings of the signed-in account.
 *
 * @param enabled - False while the capability is not offered: nothing is read.
 */
export function useNtfySubscriptions(enabled: boolean) {
  const query = useApplicationAccountQuery<NtfyOverview>(ENDPOINT, COMPONENT, enabled);
  const { mutate: post } = useApiMutation({ method: 'POST', componentName: COMPONENT });
  const { mutate: patch } = useApiMutation({ method: 'PATCH', componentName: COMPONENT });
  const { mutate: remove } = useApiMutation({ method: 'DELETE', componentName: COMPONENT });
  const { refetch, isCurrent } = query;

  /** Run one verb; a success re-reads the list when `reread` says so. */
  const run = useCallback(
    async <T>(
      act: () => Promise<unknown>,
      reread: boolean,
      read: (answer: unknown) => T | undefined = () => undefined
    ): Promise<NtfyActionResult<T>> => {
      if (!enabled || !isCurrent()) return { ok: false, errorCode: null };
      try {
        const answer = await act();
        if (!isCurrent()) return { ok: false, errorCode: null };
        // The verb resolves once the list was read again: what the screen shows next is the
        // server's own, never a value a control must snap back from.
        if (reread) await refetch().catch(() => {});
        const data = read(answer);
        return data === undefined
          ? { ok: true, errorCode: null }
          : { ok: true, errorCode: null, data };
      } catch (error) {
        return { ok: false, errorCode: getApiErrorCode(error) ?? null };
      }
    },
    [enabled, isCurrent, refetch]
  );

  const create = useCallback(
    (input: NtfySubscriptionInput) =>
      run(
        () => post(ENDPOINT, input),
        true,
        answer => answer as NtfySubscriptionView
      ),
    [run, post]
  );

  const update = useCallback(
    (id: string, change: NtfySubscriptionChange) =>
      run(
        () => patch(`${ENDPOINT}/${id}`, change),
        true,
        answer => answer as NtfySubscriptionView
      ),
    [run, patch]
  );

  const removeSubscription = useCallback(
    (id: string) => run<undefined>(() => remove(`${ENDPOINT}/${id}`), true),
    [run, remove]
  );

  const test = useCallback(
    (id: string) =>
      run(
        () => post(`${ENDPOINT}/${id}/test`),
        false,
        answer => (answer as { outcome: NtfyOutcome }).outcome
      ),
    [run, post]
  );

  return {
    overview: query.data,
    // Monotone: once one answer landed, a refresh never shows the first-load skeleton again.
    firstLoad: enabled && query.data === undefined && query.error === null,
    refreshing: query.loading && query.data !== undefined,
    readFailed: query.error !== null,
    create,
    update,
    remove: removeSubscription,
    test,
  };
}
