'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useAuth } from '@/hooks/useAuth';
import { setLocaleCookie } from '@/i18n/settings';
import { backendToFrontendLocale } from '@/utils/locale-mapping';
import { switchLanguageInPath } from '@/utils/i18n-path-utils';
import type { ApplicationStateChange } from '@/types/application-state';
import { publishApplicationResources, type ApplicationResource } from '@/lib/application-resources';
import { apiClient } from '@/lib/api-client';
import { stopAvatarForConnectorChange } from '@/lib/avatars/runtime';
import { bumpRevision } from '@/stores/revisionStore';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';

interface RefreshJob {
  dirty: boolean;
  cancelled: boolean;
  resources: Set<ApplicationResource>;
}
interface LocaleRefresh {
  ownerId: string;
  verified: boolean;
  streamComplete: boolean;
}

/** Runtime changes follow a fresh authenticated read and the same account lifetime. */
async function refreshConnectionRuntimes(
  resources: Set<ApplicationResource>,
  job: Pick<RefreshJob, 'cancelled'>
) {
  if (!resources.has('avatar') && !resources.has('live_connectors')) return;
  await apiClient.get('/connectors?fresh=true');
  if (job.cancelled) return;
  if (resources.has('avatar')) await stopAvatarForConnectorChange();
  if (job.cancelled) return;
  for (const resource of ['avatar', 'live_connectors'] as const) {
    if (resources.has(resource)) bumpRevision(resource);
  }
}

/** Publish a batch only after its required profile read and current-owner check. */
async function publishVerifiedResources(
  ownerId: string,
  resources: Set<ApplicationResource>,
  refreshUser: () => Promise<boolean>,
  job: Pick<RefreshJob, 'cancelled'>
) {
  const refreshed = !resources.has('profile') || (await refreshUser());
  if (!refreshed || job.cancelled) return refreshed;
  await refreshConnectionRuntimes(resources, job);
  if (!job.cancelled) publishApplicationResources(ownerId, resources);
  return refreshed;
}

/** Coalesce invalidations while preserving input, focus and all local form state. */
export function useApplicationStateSync() {
  const { user, refreshUser } = useAuth();
  const { t } = useTranslation();
  const router = useRouter();
  const ownerId = user?.id;
  const { isCurrent } = useApplicationAccountLifetime(ownerId);
  const current = useRef<{ ownerId: string | undefined; job: RefreshJob | null }>({
    ownerId,
    job: null,
  });
  const locale = useRef<LocaleRefresh | null>(null);
  const [localeRevision, setLocaleRevision] = useState(0);

  useEffect(() => {
    const state = current.current;
    state.ownerId = ownerId;
    return () => {
      if (state.job) state.job.cancelled = true;
      state.job = null;
      state.ownerId = undefined;
      locale.current = null;
    };
  }, [ownerId]);

  useEffect(() => {
    const pending = locale.current;
    if (
      !pending ||
      pending.ownerId !== ownerId ||
      !pending.verified ||
      !pending.streamComplete ||
      current.current.job ||
      !user?.language
    )
      return;
    locale.current = null;
    const language = backendToFrontendLocale(user.language);
    const path = window.location.pathname;
    const target = switchLanguageInPath(path, language);
    setLocaleCookie(language);
    if (target !== path) router.push(`${target}${window.location.search}${window.location.hash}`);
  }, [ownerId, user?.language, localeRevision, router]);

  const completeStream = useCallback(() => {
    const pending = locale.current;
    if (
      !isCurrent() ||
      !pending ||
      pending.ownerId !== ownerId ||
      current.current.ownerId !== ownerId
    )
      return;
    pending.streamComplete = true;
    setLocaleRevision(revision => revision + 1);
  }, [ownerId, isCurrent]);

  const handleChange = useCallback(
    (change: ApplicationStateChange) => {
      if (
        !isCurrent() ||
        !ownerId ||
        current.current.ownerId !== ownerId ||
        change.actor_id !== ownerId
      )
        return;
      if (change.changed_fields.includes('language')) {
        locale.current = { ownerId, verified: false, streamComplete: false };
      }
      const pending = current.current.job;
      if (pending) {
        pending.dirty = true;
        change.resources.forEach(resource => pending.resources.add(resource));
        return;
      }
      const job: RefreshJob = {
        dirty: false,
        cancelled: false,
        resources: new Set(change.resources),
      };
      current.current.job = job;
      const drain = async () => {
        try {
          do {
            job.dirty = false;
            const resources = new Set(job.resources);
            job.resources.clear();
            const refreshed = await publishVerifiedResources(ownerId, resources, refreshUser, job);
            if (job.cancelled) return;
            if (locale.current?.ownerId === ownerId) locale.current.verified = refreshed;
            if (!refreshed) {
              toast.error(t('settings.application_tools.sync_failed'));
              return;
            }
          } while (job.dirty && current.current.ownerId === ownerId);
        } catch {
          if (locale.current?.ownerId === ownerId) locale.current.verified = false;
          if (!job.cancelled) toast.error(t('settings.application_tools.sync_failed'));
        } finally {
          if (current.current.job === job) current.current.job = null;
          if (!job.cancelled && locale.current?.ownerId === ownerId)
            setLocaleRevision(revision => revision + 1);
        }
      };
      void drain();
    },
    [ownerId, refreshUser, t, isCurrent]
  );
  return { handleChange, completeStream };
}
