import { beforeEach, expect, it, vi } from 'vitest';
import type { AvatarDemand } from '../activation-policy';

const post = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  apiClient: { post },
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
  post.mockResolvedValue({ released: true });
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
  expect(post).toHaveBeenCalledWith('/avatars/sessions/release', identity, { timeout: 5000 });
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
