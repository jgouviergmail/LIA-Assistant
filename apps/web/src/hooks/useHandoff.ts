'use client';
/** One observable, account-owned handover into an existing native form. */
import {
  useCallback,
  useEffect,
  useEffectEvent,
  useLayoutEffect,
  useRef,
  useSyncExternalStore,
} from 'react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import type { Language } from '@/i18n/settings';
import { settingsSectionHref } from '@/lib/settings-sections';
import { toolPath } from '@/lib/workbench/tools';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import {
  handoffStore,
  handOff,
  takeHandoff,
  setHandoffOwner,
  HANDOFF_TOOLS,
  type ApplicationHandoff,
  type ApplicationHandoffKind,
} from '@/lib/workbench/handoff';
import { useAuth } from './useAuth';
import { useApplicationAccountLifetime } from './useApplicationAccountLifetime';

/** Mounted once under authentication, independent of the current route. */
export function useHandoffOwner(owner: string | null): void {
  useLayoutEffect(() => {
    setHandoffOwner(owner);
    return () => setHandoffOwner(null);
  }, [owner]);
}

export function handoffHref(handoff: ApplicationHandoff, lng: Language): string {
  if (handoff.kind === 'memory') return settingsSectionHref(lng, 'memories');
  if (handoff.kind === 'reminder') return settingsSectionHref(lng, 'reminders');
  if (handoff.kind === 'ticket') return buildLocalizedPath('/dashboard/workboard', lng);
  return buildLocalizedPath(toolPath(HANDOFF_TOOLS[handoff.kind]), lng);
}

/** Writers carry the same account-lifetime fence as native application mutations. */
export function useHandoffNavigation(lng: Language, navigate?: (href: string) => void) {
  const { user } = useAuth();
  const owner = user?.id;
  const { isCurrent } = useApplicationAccountLifetime(owner);
  const router = useRouter();
  const push = navigate ?? router.push;
  return useCallback(
    (handoff: ApplicationHandoff) => {
      if (!owner || !isCurrent() || !handOff(owner, handoff)) return;
      push(handoffHref(handoff, lng));
    },
    [owner, isCurrent, push, lng]
  );
}

/** A busy form retains the pending proposal until it closes; it is never overwritten. */
export function useHandoff<K extends ApplicationHandoffKind>(
  kind: K,
  ready: boolean,
  receive: (handoff: Extract<ApplicationHandoff, { kind: K }>) => void,
  busy = false
): void {
  const { user } = useAuth();
  const { isCurrent } = useApplicationAccountLifetime(user?.id);
  const pending = useSyncExternalStore(
    handoffStore.subscribe,
    handoffStore.getSnapshot,
    handoffStore.getServerSnapshot
  );
  const received = useEffectEvent(receive);
  const { t } = useTranslation();
  const notified = useRef<string | null>(null);
  useEffect(() => {
    if (
      !ready ||
      !user?.id ||
      !isCurrent() ||
      pending?.owner !== user.id ||
      pending.payload.kind !== kind
    )
      return;
    if (busy) {
      if (notified.current !== pending.id) {
        notified.current = pending.id;
        toast.info(t('selectionAssist.form_busy'));
      }
      return;
    }
    const handoff = takeHandoff(kind, user.id, pending.id);
    if (handoff) received(handoff);
  }, [kind, ready, busy, user?.id, isCurrent, pending, t]);
}
