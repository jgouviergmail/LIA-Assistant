'use client';

import { useEffect, useRef, type ReactNode } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { useApiQuery } from '@/hooks/useApiQuery';
import { useLiveStore } from '@/stores/liveStore';
import { useResourceRevision } from '@/stores/revisionStore';
import { avatarDemand, type AvatarDemand } from '@/lib/avatars/activation-policy';
import { avatarApi } from '@/lib/avatars/api';
import { BrowserAvatarMedia } from '@/lib/avatars/browser-media';
import { AvatarEngine } from '@/lib/avatars/engine';
import { SimliTransport } from '@/lib/avatars/simli-transport';
import { mountAvatarEngine } from '@/lib/avatars/runtime';
import type { AvatarConfig } from '@/lib/avatars/types';
import { AvatarWindow } from './AvatarWindow';

export function AvatarProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  return (
    <>
      {children}
      {user ? (
        <AccountAvatar key={user.id} account={user.id} voiceEnabled={!!user.voice_enabled} />
      ) : null}
    </>
  );
}

function AccountAvatar({ account, voiceEnabled }: { account: string; voiceEnabled: boolean }) {
  const revision = useResourceRevision('avatar');
  const query = useApiQuery<AvatarConfig>('/avatars/config', {
    componentName: 'AvatarHost',
    deps: [revision],
  });
  const current = useRef<{ config: AvatarConfig | null; voiceEnabled: boolean }>({
    config: null,
    voiceEnabled,
  });
  const updateOwned = useRef<(() => void) | null>(null);
  useEffect(() => {
    const engine = new AvatarEngine({
      api: avatarApi,
      wire: events => new SimliTransport(events),
      media: changed => new BrowserAvatarMedia(changed),
    });
    const unmount = mountAvatarEngine(engine);
    let previous: AvatarDemand | null = null;
    const update = () => {
      const live = useLiveStore.getState();
      const config = current.current.config;
      const permitted =
        avatarDemand(account, config, true, { status: 'idle', session_id: null }) !== null;
      const preparing = permitted && live.status === 'minting' && !live.sessionId;
      engine.setPermission(permitted, preparing);
      if (preparing) engine.interrupt();
      previous = avatarDemand(
        account,
        config,
        current.current.voiceEnabled,
        {
          status: live.status,
          session_id: live.sessionId,
        },
        previous
      );
      engine.setDemand(previous);
    };
    updateOwned.current = update;
    update();
    const stopLive = useLiveStore.subscribe(update);
    const unlock = () => {
      if (engine.present) void engine.media.unlock();
    };
    document.addEventListener('pointerdown', unlock);
    document.addEventListener('keydown', unlock);
    return () => {
      stopLive();
      document.removeEventListener('pointerdown', unlock);
      document.removeEventListener('keydown', unlock);
      updateOwned.current = null;
      unmount();
      engine.dispose();
    };
  }, [account]);
  useEffect(() => {
    current.current = { config: query.data ?? null, voiceEnabled };
    updateOwned.current?.();
  }, [account, query.data, voiceEnabled]);
  return <AvatarWindow />;
}
