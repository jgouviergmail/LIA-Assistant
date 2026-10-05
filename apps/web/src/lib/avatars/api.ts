import { apiClient, ApiError } from '@/lib/api-client';
import type { AvatarDemand } from './activation-policy';
import type { AvatarSession } from './types';

export interface AvatarLeaseIdentity {
  owner_id: string;
  lease_id?: string;
}
export interface AvatarApi {
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
    try {
      return await apiClient.post<AvatarSession>(
        '/avatars/sessions',
        {
          owner_id: owner,
          ...sourceOf(demand),
        },
        { signal }
      );
    } catch (error) {
      throw safeStartError(error);
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
        identity,
        {
          timeout: 5000,
        }
      );
      return result.released === true;
    } catch {
      return false;
    }
  },
};
