import { afterEach, describe, expect, it, vi } from 'vitest';
import { GET } from './route';

afterEach(() => vi.unstubAllEnvs());

describe('runtime UI configuration', () => {
  it.each([undefined, '', ' ', 'https://invalid.example', 'x'.repeat(81)])(
    'does not opt a deployment into a campaign for %j',
    value => {
      vi.stubEnv('AVATAR_STYLE_ROLLOUT_ID', value);
      expect(GET().headers.get('cache-control')).toBe('no-store');
      return expect(GET().json()).resolves.toEqual({ avatarStyleRolloutId: null });
    }
  );

  it('reads the current server environment on each request and returns only the non-secret id', async () => {
    vi.stubEnv('AVATAR_STYLE_ROLLOUT_ID', '  production-bip-v3  ');
    vi.stubEnv('TEST_SECRET_NOT_EXPOSED', 'private-value');
    expect(await GET().json()).toEqual({ avatarStyleRolloutId: 'production-bip-v3' });
    vi.stubEnv('AVATAR_STYLE_ROLLOUT_ID', 'production-bip-v4');
    expect(await GET().json()).toEqual({ avatarStyleRolloutId: 'production-bip-v4' });
  });
});
