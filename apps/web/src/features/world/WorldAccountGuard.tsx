'use client';

import {
  Activity,
  createContext,
  useContext,
  useEffect,
  useEffectEvent,
  useMemo,
  type ReactNode,
} from 'react';
import { Button } from '@/components/ui/button';
import { useApiQuery } from '@/hooks/useApiQuery';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { useWorldVerificationFocus } from './useWorldVerificationFocus';
import { useWorldIdentityNotice } from './useWorldIdentityNotice';

const WorldAccountContext = createContext({ verified: true, verify: async () => {} });
export const useWorldAccountIdentity = () => useContext(WorldAccountContext);

/** Preserve local edits while hiding every nested portal and pausing its effects. */
export function WorldPrivateActivity({
  children,
  visible = true,
}: {
  children: ReactNode;
  visible?: boolean;
}) {
  const { verified } = useWorldAccountIdentity();
  return (
    <div
      className="contents"
      onChangeCapture={event => {
        const control = event.target;
        // Activity disconnects Radix's option effects while hiding a private
        // portal. Its hidden form bridge can then emit an empty synchronization
        // before options return. That is no user edit; keep it inside World.
        if (
          control instanceof HTMLSelectElement &&
          control.getAttribute('aria-hidden') === 'true' &&
          control.selectedIndex === -1
        )
          event.stopPropagation();
      }}
    >
      <Activity mode={verified && visible ? 'visible' : 'hidden'}>{children}</Activity>
    </div>
  );
}

/** A socket retains its handshake identity; HTTP cookies can change in another tab. */
export function WorldAccountGuard({
  ownerId,
  lng,
  children,
}: {
  ownerId: string;
  lng: Language;
  children: ReactNode;
}) {
  const { t } = useTranslation(lng);
  const identity = useApiQuery<{ id: string; is_active: boolean }>('/auth/me', {
    componentName: 'WorldAccountIdentity',
    deps: [ownerId],
  });
  const { refetch } = identity;
  const changed =
    identity.data !== undefined && (identity.data.id !== ownerId || !identity.data.is_active);
  const hidden = identity.loading || !!identity.error || changed;
  const verifyIdentity = useWorldVerificationFocus(hidden, changed, refetch);
  useWorldIdentityNotice(ownerId, verifyIdentity);
  // Read the committed identity even between a render and passive-effect cleanup.
  const verifyOnFocus = useEffectEvent(() => {
    if (!document.hidden) void verifyIdentity();
  });
  useEffect(() => {
    window.addEventListener('focus', verifyOnFocus);
    document.addEventListener('visibilitychange', verifyOnFocus);
    return () => {
      window.removeEventListener('focus', verifyOnFocus);
      document.removeEventListener('visibilitychange', verifyOnFocus);
    };
  }, []);
  const context = useMemo(
    () => ({ verified: !hidden, verify: verifyIdentity }),
    [hidden, verifyIdentity]
  );
  return (
    <WorldAccountContext.Provider value={context}>
      {!changed && (
        <div
          className="flex min-h-0 flex-1 flex-col"
          hidden={hidden}
          inert={hidden}
          style={hidden ? { display: 'none' } : undefined}
        >
          {children}
        </div>
      )}
      {identity.loading && <p role="status">{t('world.session.connecting')}</p>}
      {!identity.loading && (changed || identity.error) && (
        <div role="alert" className="space-y-3 rounded-xl border border-border bg-background p-4">
          <p>{t(changed ? 'world.session.account_changed' : 'world.session.unavailable')}</p>
          <Button
            onClick={() => {
              if (changed) window.location.reload();
              else void verifyIdentity();
            }}
          >
            {t(changed ? 'world.session.reload_account' : 'common.retry')}
          </Button>
        </div>
      )}
    </WorldAccountContext.Provider>
  );
}
