'use client';

import { useCallback, useEffect, useLayoutEffect, useRef } from 'react';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { useApplicationAccountState } from '@/hooks/useApplicationAccountState';
import { useApplicationResourceSync } from '@/hooks/useApplicationResourceSync';
import { useApiMutation } from '@/hooks/useApiMutation';
import type { ApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { publishApplicationResources } from '@/lib/application-resources';
import { rebuildBlockedReason } from '@/lib/discussion-context';
import {
  discussionActivitySchema,
  discussionContextSchema,
  discussionSettingsSchema,
  discussionPurgePreviewSchema,
  type DiscussionActivity,
  type DiscussionContextFence,
  type DiscussionContext,
  type DiscussionSettings,
  type DiscussionPolicyPatch,
} from '@/types/proactive-discussions';

/** How often a rebuild in flight is re-read; it settles within the run's own deadline. */
export const DISCUSSION_ACTIVITY_POLL_MS = 4_000;
/** How often the activity is re-read while the context is shown and no rebuild runs:
 *  automatic runs update the context on their own schedule. */
export const DISCUSSION_ACTIVITY_IDLE_POLL_MS = 60_000;

/** A rebuild is in flight from the moment it is asked until a run settles it. */
export function rebuildInFlight(activity: unknown): boolean {
  const parsed = discussionActivitySchema.safeParse(activity);
  return parsed.success && parsed.data.rebuild !== 'idle';
}

/** When the context was last updated by a run, as the server published it. */
export function lastContextUpdate(activity: unknown): string | undefined {
  const parsed = discussionActivitySchema.safeParse(activity);
  const update = parsed.success ? parsed.data.last_update : null;
  return update ? (update.settled_at ?? update.claimed_at) : undefined;
}

/**
 * A rebuild is progressing while it runs, or while it is asked and nothing the server
 * published blocks it. A blocked request waits for the person: it is not polled.
 */
export function rebuildProgressing(settings: unknown, activity: unknown): boolean {
  const current = discussionActivitySchema.safeParse(activity);
  if (!current.success || current.data.rebuild === 'idle') return false;
  if (current.data.rebuild === 'running') return true;
  const parsed = discussionSettingsSchema.safeParse(settings);
  return !parsed.success || rebuildBlockedReason(parsed.data, current.data) === undefined;
}

export function useProactiveDiscussions(contextOpen: boolean) {
  const settings = useApplicationAccountQuery<DiscussionSettings>(
    '/proactive-discussions/settings',
    'useProactiveDiscussions'
  );
  const [cursor, setCursor] = useApplicationAccountState<string | undefined>(
    settings.ownerId,
    undefined
  );
  const [exclusionsCursor, setExclusionsCursor] = useApplicationAccountState<string | undefined>(
    settings.ownerId,
    undefined
  );
  const [filters, setStoredFilters] = useApplicationAccountState<Record<string, string>>(
    settings.ownerId,
    {}
  );
  const setFilters = useCallback(
    (value: Record<string, string>) => {
      setStoredFilters(value);
      setCursor(undefined);
    },
    [setStoredFilters, setCursor]
  );
  const context = useApplicationAccountQuery<DiscussionContext>(
    '/proactive-discussions/context',
    'useProactiveDiscussions',
    contextOpen,
    undefined,
    {
      params: {
        limit: 30,
        ...filters,
        ...(cursor ? { after_id: cursor } : {}),
        ...(exclusionsCursor ? { after_exclusion_id: exclusionsCursor } : {}),
      },
    }
  );
  const activity = useApplicationAccountQuery<DiscussionActivity>(
    '/proactive-discussions/activity',
    'useProactiveDiscussions',
    contextOpen
  );
  const { ownerId, lifetime, isCurrent, acceptData, refetch: refreshSettings } = settings;
  const { refetch: refreshContext, acceptData: acceptContext } = context;
  const { refetch: refreshActivity } = activity;
  const busy = rebuildProgressing(settings.data, activity.data);
  const wasBusy = useRef(false);
  useEffect(() => {
    if (!busy) {
      // The rebuild just settled: show what it built, without waiting for a click.
      if (wasBusy.current) void refreshContext().catch(() => undefined);
      wasBusy.current = false;
      return;
    }
    wasBusy.current = true;
    const timer = setInterval(() => {
      void refreshActivity().catch(() => undefined);
    }, DISCUSSION_ACTIVITY_POLL_MS);
    return () => clearInterval(timer);
  }, [busy, refreshActivity, refreshContext]);
  useEffect(() => {
    // Automatic runs update the context on their own schedule: a shown context
    // keeps reading the activity, gently, while no rebuild is polled faster.
    if (!contextOpen || busy) return;
    const timer = setInterval(() => {
      void refreshActivity().catch(() => undefined);
    }, DISCUSSION_ACTIVITY_IDLE_POLL_MS);
    return () => clearInterval(timer);
  }, [contextOpen, busy, refreshActivity]);
  const updatedAt = lastContextUpdate(activity.data);
  const seenUpdate = useRef(updatedAt);
  useEffect(() => {
    // A run updated the context since it was read: show what that run built.
    if (
      updatedAt !== undefined &&
      seenUpdate.current !== undefined &&
      updatedAt !== seenUpdate.current
    )
      void refreshContext().catch(() => undefined);
    seenUpdate.current = updatedAt;
  }, [updatedAt, refreshContext]);
  const [saving, setSaving] = useApplicationAccountState(ownerId, false);
  const [error, setError] = useApplicationAccountState(ownerId, false);
  const inFlight = useRef<ApplicationAccountLifetime | null>(null);
  const latest = useRef(settings.data);
  const epoch = useRef(context.data?.context_epoch);
  const generation = useRef(context.data?.generation);
  useLayoutEffect(() => {
    latest.current = settings.data;
    epoch.current = context.data?.context_epoch;
    generation.current = context.data?.generation;
  }, [settings.data, context.data]);
  const { mutate: patch } = useApiMutation<object, unknown>({
    method: 'PATCH',
    componentName: 'useProactiveDiscussions',
    retainResponse: false,
  });
  const { mutate: post } = useApiMutation<object, unknown>({
    method: 'POST',
    componentName: 'useProactiveDiscussions',
    retainResponse: false,
  });
  const refresh = useCallback(async () => {
    await Promise.all([
      refreshSettings(),
      ...(contextOpen ? [refreshContext(), refreshActivity()] : []),
    ]);
  }, [refreshSettings, refreshContext, refreshActivity, contextOpen]);
  useApplicationResourceSync(ownerId, 'proactive_discussions', refresh);

  const perform = useCallback(
    async (action: () => Promise<void>) => {
      if (!isCurrent() || inFlight.current === lifetime) return false;
      inFlight.current = lifetime;
      setSaving(true);
      setError(false);
      try {
        await action();
        return isCurrent();
      } catch {
        if (isCurrent()) setError(true);
        return false;
      } finally {
        if (inFlight.current === lifetime) inFlight.current = null;
        setSaving(false);
        if (isCurrent() && ownerId)
          publishApplicationResources(ownerId, new Set(['proactive_discussions']));
      }
    },
    [isCurrent, lifetime, setSaving, setError, ownerId]
  );

  const update = useCallback(
    (changes: DiscussionPolicyPatch) =>
      perform(async () => {
        if (!latest.current) return;
        const result = discussionSettingsSchema.parse(
          await patch('/proactive-discussions/settings', {
            expected_revision: latest.current.policy.revision,
            changes,
          })
        );
        if (isCurrent()) acceptData(result);
      }),
    [perform, patch, acceptData, isCurrent]
  );
  const setUsable = useCallback(
    (itemId: string, usable: boolean, revision: number | null) =>
      perform(async () => {
        if (epoch.current === undefined) return;
        const result = discussionContextSchema.parse(
          await patch(`/proactive-discussions/context/${itemId}/usability`, {
            usable,
            expected_revision: revision,
            expected_epoch: epoch.current,
          })
        );
        if (isCurrent()) {
          setCursor(undefined);
          setExclusionsCursor(undefined);
          acceptContext(result);
        }
      }),
    [perform, patch, isCurrent, setCursor, setExclusionsCursor, acceptContext]
  );
  const contextAction = useCallback(
    (action: 'purge' | 'rebuild', selection?: string[], expected?: DiscussionContextFence) =>
      perform(async () => {
        if (epoch.current === undefined) throw new Error('Context snapshot unavailable');
        const fence = expected ?? {
          expected_epoch: epoch.current,
          expected_generation: generation.current,
        };
        const result = discussionContextSchema.parse(
          await post(`/proactive-discussions/context/${action}`, {
            expected_epoch: fence.expected_epoch,
            ...(action === 'purge' ? { expected_generation: fence.expected_generation } : {}),
            ...(selection ? { selection } : {}),
          })
        );
        if (isCurrent()) {
          setCursor(undefined);
          setExclusionsCursor(undefined);
          acceptContext(result);
          // Both actions change what runs next: the rebuild state is read again at once.
          await refreshActivity();
        }
      }),
    [perform, post, isCurrent, setCursor, setExclusionsCursor, acceptContext, refreshActivity]
  );
  const previewPurge = useCallback(
    async (selection: string[] | undefined, expected: DiscussionContextFence) => {
      if (!isCurrent()) return undefined;
      const result = discussionPurgePreviewSchema.parse(
        await post('/proactive-discussions/context/purge-preview', {
          ...expected,
          ...(selection ? { selection } : {}),
        })
      );
      if (
        !isCurrent() ||
        result.context_epoch !== expected.expected_epoch ||
        result.generation !== expected.expected_generation
      )
        return undefined;
      return result;
    },
    [isCurrent, post]
  );
  return {
    settings,
    context,
    activity,
    rebuildActive: busy,
    saving,
    error,
    update,
    setUsable,
    contextAction,
    previewPurge,
    refresh,
    cursor,
    setCursor,
    exclusionsCursor,
    setExclusionsCursor,
    filters,
    setFilters,
  };
}
