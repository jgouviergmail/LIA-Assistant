import type { AvatarConfig, AvatarSource } from './types';

export interface AvatarDemand {
  account: string;
  credential: string;
  face: string;
  source: AvatarSource;
  live_id?: string;
  connectSeconds: number;
}

function configuredDemand(
  account: string | undefined,
  config: AvatarConfig | null
): Omit<AvatarDemand, 'source'> | null {
  if (
    !account ||
    !config?.available ||
    !config.enabled ||
    !config.connected ||
    !config.face_id ||
    !config.connector_version
  )
    return null;
  return {
    account,
    credential: config.connector_version,
    face: config.face_id,
    connectSeconds: config.connect_timeout_seconds,
  };
}

export function avatarDemand(
  account: string | undefined,
  config: AvatarConfig | null,
  voiceEnabled: boolean,
  live: { status: string; session_id: string | null },
  previous: AvatarDemand | null = null
): AvatarDemand | null {
  const base = configuredDemand(account, config);
  if (!base || live.status === 'standby') return null;
  // Keep only an existing owner while the Live record is being minted.
  // No comments session can be opened for a cold, voice-disabled account.
  if (live.status === 'minting' && !live.session_id) {
    return sameAvatar(previous, { ...base, source: 'comments' }) ? previous : null;
  }
  if (live.session_id && !['idle', 'ended', 'error'].includes(live.status)) {
    return { ...base, source: 'live', live_id: live.session_id };
  }
  return voiceEnabled ? { ...base, source: 'comments' } : null;
}

export function sameAvatar(a: AvatarDemand | null, b: AvatarDemand | null): boolean {
  return (
    !!a && !!b && a.account === b.account && a.credential === b.credential && a.face === b.face
  );
}
