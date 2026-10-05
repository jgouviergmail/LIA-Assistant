import { apiClient, ApiError } from '@/lib/api-client';
import type { AvatarDemand } from './activation-policy';
import type { AvatarSession } from './types';

export interface AvatarLeaseIdentity {
  owner_id: string;
  lease_id?: string;
}
export interface AvatarApi {
  stopCurrent?(): Promise<boolean>;
  reportFailure?(identity: AvatarLeaseIdentity, code: string): Promise<void>;
  start(owner: string, demand: AvatarDemand, signal: AbortSignal): Promise<AvatarSession>;
  heartbeat(
    identity: AvatarLeaseIdentity,
    demand: AvatarDemand,
    signal: AbortSignal
  ): Promise<void>;
  release(identity: AvatarLeaseIdentity): Promise<boolean>;
}
function sourceOf(demand: AvatarDemand) {
  return { source: demand.source, ...(demand.live_id ? { live_session_id: demand.live_id } : {}) };
}
export type AvatarStartFailure =
  | 'avatar_start_rate_limited'
  | 'avatar_start_busy'
  | 'avatar_start_failed';
export class AvatarStartError extends Error {
  constructor(
    readonly code: AvatarStartFailure,
    readonly beforeMint: boolean
  ) {
    super(code);
  }
}
function safeStartError(error: unknown): AvatarStartError {
  if (!(error instanceof ApiError)) return new AvatarStartError('avatar_start_failed', false);
  const detail =
    error.data && typeof error.data === 'object' && 'detail' in error.data
      ? error.data.detail
      : null;
  if (error.status === 429 && detail === 'avatar_start_rate_limited')
    return new AvatarStartError('avatar_start_rate_limited', true);
  if (
    error.status === 409 &&
    ['avatar_already_active', 'avatar_provider_already_active'].includes(String(detail))
  )
    return new AvatarStartError('avatar_start_busy', true);
  return new AvatarStartError('avatar_start_failed', false);
}
export const avatarApi: AvatarApi = {
  start: async (owner, demand, signal) => {
    let posted = false;
    try {
      const previous = await apiClient.get<AvatarSessionStatus | null>(
        '/avatars/sessions/current',
        { signal }
      );
      if (
        previous?.controlled &&
        previous.phase === 'ready' &&
        previous.control_phase === 'closed'
      ) {
        if (!(await avatarApi.release(previous)))
          throw new AvatarStartError('avatar_start_busy', true);
      }
      posted = true;
      return await apiClient.post<AvatarSession>(
        '/avatars/sessions',
        {
          owner_id: owner,
          ...sourceOf(demand),
        },
        { signal }
      );
    } catch (error) {
      if (error instanceof AvatarStartError) throw error;
      const failure = safeStartError(error);
      throw posted ? failure : new AvatarStartError(failure.code, true);
    }
  },
  heartbeat: (identity, demand, signal) =>
    apiClient.post<void>(
      '/avatars/sessions/heartbeat',
      {
        ...identity,
        ...sourceOf(demand),
      },
      { signal }
    ),
  release: async identity => {
    try {
      const result = await apiClient.post<{ released: boolean }>(
        '/avatars/sessions/release',
        {
          owner_id: identity.owner_id,
          ...(identity.lease_id ? { lease_id: identity.lease_id } : {}),
        },
        {
          timeout: 15000,
          keepalive: true,
        }
      );
      return result.released === true;
    } catch {
      return false;
    }
  },
  stopCurrent: async () => {
    try {
      const current = await apiClient.get<AvatarSessionStatus | null>('/avatars/sessions/current');
      if (!current) return true;
      if (!current.controlled || current.phase !== 'ready') return false;
      return await avatarApi.release(current);
    } catch {
      return false;
    }
  },
  reportFailure: async (identity, code) => {
    try {
      await apiClient.post(
        '/avatars/sessions/failure',
        { ...identity, code },
        { timeout: 5000, keepalive: true }
      );
    } catch {
      /* Diagnostics never prevent cleanup. */
    }
  },
};

interface AvatarSessionStatus extends AvatarLeaseIdentity {
  phase: 'minting' | 'ready' | 'unknown';
  controlled: boolean;
  control_phase: 'pending' | 'open' | 'closed' | null;
}
