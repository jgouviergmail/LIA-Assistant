'use client';

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { useAuth } from '@/hooks/useAuth';
import apiClient from '@/lib/api-client';
import { getApiErrorStatus } from '@/lib/api-error';
import type { AvatarConfig } from '@/lib/avatars/types';
import { bumpRevision } from '@/stores/revisionStore';

type Preference = Pick<AvatarConfig, 'enabled' | 'face_id'>;
interface SaveState {
  confirmed: AvatarConfig | null;
  desired: Preference | null;
  saving: boolean;
  failed: boolean;
}
interface SaveContext extends SaveState {
  saved: boolean;
  initialize: (config: AvatarConfig) => void;
  change: (value: Preference) => void;
  retry: () => Promise<boolean>;
}
const Context = createContext<SaveContext | null>(null);

async function savePreference(target: Preference, signal: AbortSignal): Promise<AvatarConfig> {
  try {
    return await apiClient.put<AvatarConfig>('/avatars/settings', target, { signal });
  } catch (error) {
    const status = getApiErrorStatus(error);
    if (signal.aborted || (status !== undefined && status >= 400 && status < 500 && status !== 408))
      throw error;
    // A lost response can follow a committed write. Read before claiming a
    // rollback or offering another write, keeping this request account-bound.
    return apiClient.get<AvatarConfig>('/avatars/config', { signal });
  }
}

/** Mounted under auth above route content, so navigation cannot cancel a preference write. */
export function AvatarPreferenceSaveProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  return <AccountSaveProvider key={user?.id ?? 'anonymous'}>{children}</AccountSaveProvider>;
}

function AccountSaveProvider({ children }: { children: ReactNode }) {
  const { user, refreshUser } = useAuth();
  const [state, setState] = useState<SaveState>({
    confirmed: null,
    desired: null,
    saving: false,
    failed: false,
  });
  const [saved, setSaved] = useState(false);
  const active = useRef(true);
  const confirmed = useRef<AvatarConfig | null>(null);
  const queued = useRef<Preference | null>(null);
  const failedTarget = useRef<Preference | null>(null);
  const running = useRef(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
      controller.current?.abort();
    };
  }, []);

  async function drain() {
    if (running.current || !user) return;
    running.current = true;
    setState(previous => ({ ...previous, saving: true, failed: false }));
    while (queued.current && active.current) {
      const target = queued.current;
      queued.current = null;
      const request = new AbortController();
      controller.current = request;
      try {
        const saved = await savePreference(target, request.signal);
        if (!active.current) break;
        confirmed.current = saved;
        if (saved.enabled !== target.enabled || saved.face_id !== target.face_id)
          throw new Error('Avatar preference was not confirmed');
        failedTarget.current = null;
        setSaved(!queued.current);
        setState({
          confirmed: saved,
          desired: queued.current,
          saving: !!queued.current,
          failed: false,
        });
        bumpRevision('avatar');
      } catch {
        if (!active.current) break;
        setSaved(false);
        failedTarget.current = queued.current ?? target;
        queued.current = null;
        setState({ confirmed: confirmed.current, desired: null, saving: false, failed: true });
        break;
      }
    }
    running.current = false;
    if (active.current) {
      setState(previous => ({ ...previous, saving: false }));
      // User refresh is secondary: a refresh failure must not turn a confirmed save into an error.
      void refreshUser().catch(() => undefined);
    }
  }
  function change(value: Preference) {
    setSaved(false);
    queued.current = value;
    setState(previous => ({ ...previous, desired: value, failed: false }));
    return drain();
  }
  return (
    <Context.Provider
      value={{
        ...state,
        saved,
        initialize(config) {
          if (confirmed.current) return;
          confirmed.current = config;
          setState(previous => ({ ...previous, confirmed: config }));
        },
        change,
        async retry() {
          if (!failedTarget.current || running.current) return false;
          await change(failedTarget.current);
          return active.current && failedTarget.current === null;
        },
      }}
    >
      {children}
    </Context.Provider>
  );
}
export function useAvatarPreferenceSave() {
  const context = useContext(Context);
  if (!context) throw new Error('AvatarPreferenceSaveProvider is required');
  return context;
}
export default AvatarPreferenceSaveProvider;
