import { beforeEach, expect, it, vi } from 'vitest';
import type { AvatarDemand } from '../activation-policy';

const post = vi.hoisted(() => vi.fn());
const get = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  apiClient: { post, get },
}));
import { avatarApi } from '../api';
import { ApiError } from '@/lib/api-client';

const live: AvatarDemand = {
  account: 'account',
  credential: 'version',
  face: 'face',
  source: 'live',
  live_id: '11111111-1111-4111-8111-111111111111',
  connectSeconds: 15,
};
beforeEach(() => {
  post.mockReset();
  get.mockReset();
  get.mockResolvedValue(null);
  post.mockResolvedValue({ released: true });
});
it('reconciles a closed owned generation after reload before creating any new session', async () => {
  get.mockResolvedValueOnce({
    owner_id: 'old',
    lease_id: 'old-lease',
    phase: 'ready',
    controlled: true,
    control_phase: 'closed',
  });
  await avatarApi.start('new', live, new AbortController().signal);
  expect(post.mock.calls.map(call => call[0])).toEqual([
    '/avatars/sessions/release',
    '/avatars/sessions',
  ]);
  expect(post.mock.calls[0][1]).toEqual({ owner_id: 'old', lease_id: 'old-lease' });
});
it('does not mint when closure could not be verified, and never retries an uncertain mint', async () => {
  get.mockResolvedValueOnce({
    owner_id: 'old',
    lease_id: 'old-lease',
    phase: 'ready',
    controlled: true,
    control_phase: 'closed',
  });
  post.mockResolvedValueOnce({ released: false });
  await expect(avatarApi.start('new', live, new AbortController().signal)).rejects.toMatchObject({
    beforeMint: true,
  });
  expect(post).toHaveBeenCalledOnce();
});
it('permits explicit stop after reload, but refuses an unknown or legacy generation', async () => {
  get.mockResolvedValueOnce({
    owner_id: 'old',
    lease_id: 'lease',
    phase: 'ready',
    controlled: true,
    control_phase: 'open',
  });
  expect(await avatarApi.stopCurrent?.()).toBe(true);
  post.mockClear();
  get.mockResolvedValueOnce({ owner_id: 'old', phase: 'unknown', controlled: true });
  expect(await avatarApi.stopCurrent?.()).toBe(false);
  expect(post).not.toHaveBeenCalled();
});

it('serializes Live admission with the authenticated server schema, excluding credential metadata', async () => {
  const signal = new AbortController().signal;
  await avatarApi.start('owner', live, signal);
  expect(post).toHaveBeenCalledWith(
    '/avatars/sessions',
    {
      owner_id: 'owner',
      source: 'live',
      live_session_id: live.live_id,
    },
    { signal }
  );
});

it('uses the mounted heartbeat and release endpoints with their owner and lease', async () => {
  const identity = { owner_id: 'owner', lease_id: 'lease' };
  const signal = new AbortController().signal;
  await avatarApi.heartbeat(identity, live, signal);
  expect(post).toHaveBeenCalledWith(
    '/avatars/sessions/heartbeat',
    {
      ...identity,
      source: 'live',
      live_session_id: live.live_id,
    },
    { signal }
  );
  expect(await avatarApi.release(identity)).toBe(true);
  expect(post).toHaveBeenCalledWith('/avatars/sessions/release', identity, {
    timeout: 15000,
    keepalive: true,
  });
});
it('distinguishes a definite pre-mint rate refusal from an ambiguous network failure without exposing response data', async () => {
  post.mockRejectedValueOnce(
    new ApiError('unsafe text', 429, { detail: 'avatar_start_rate_limited' })
  );
  await expect(avatarApi.start('owner', live, new AbortController().signal)).rejects.toMatchObject({
    message: 'avatar_start_rate_limited',
    beforeMint: true,
  });
  post.mockRejectedValueOnce(
    new ApiError('unsafe text', 502, { detail: 'avatar_configuration_changed' })
  );
  await expect(avatarApi.start('owner', live, new AbortController().signal)).rejects.toMatchObject({
    message: 'avatar_start_failed',
    beforeMint: false,
  });
});
