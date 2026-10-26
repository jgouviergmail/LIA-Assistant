'use client';

import { useEffect, useMemo, useState } from 'react';
import { usePreviewAtmosphere } from './WorldEnvironmentPreview';
import { useAuth } from '@/hooks/useAuth';
import { useApiQuery } from '@/hooks/useApiQuery';
import { atmosphereAt, readWorldEnvironment, type WorldEnvironmentAnchor } from './atmosphere';

/** Mounted within the keyed account world, independently of the native face widget. */
export function useWorldEnvironment(ownerId: string, enabled: boolean) {
  const { user } = useAuth();
  const authorized = enabled && user?.id === ownerId && user.is_active;
  const [clock, setClock] = useState(() => performance.now());
  const [snapshot, setSnapshot] = useState<{
    owner: string;
    anchor: WorldEnvironmentAnchor | null;
  } | null>(null);
  const { refetch } = useApiQuery<unknown>('/world/environment', {
    enabled: authorized,
    componentName: 'WorldEnvironment',
    deps: [ownerId],
    onSuccess: value => {
      const now = performance.now();
      setSnapshot({ owner: ownerId, anchor: readWorldEnvironment(value, now) });
      setClock(now);
    },
  });
  useEffect(() => {
    if (!authorized) return;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let requestedAt = performance.now();
    const cancel = () => {
      if (timer) clearTimeout(timer);
      timer = null;
    };
    const pulse = () => {
      cancel();
      if (document.hidden) return;
      const now = performance.now();
      setClock(now);
      if (now - requestedAt >= 15 * 60_000) {
        requestedAt = now;
        void refetch();
      }
      timer = setTimeout(pulse, 30_000);
    };
    const visible = () => {
      if (document.hidden) cancel();
      else pulse();
    };
    timer = setTimeout(pulse, 30_000);
    document.addEventListener('visibilitychange', visible);
    return () => {
      cancel();
      document.removeEventListener('visibilitychange', visible);
    };
  }, [authorized, ownerId, refetch]);
  const native = useMemo(
    () => atmosphereAt(authorized && snapshot?.owner === ownerId ? snapshot.anchor : null, clock),
    [authorized, ownerId, snapshot, clock]
  );
  return usePreviewAtmosphere(native);
}
