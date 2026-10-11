import { afterEach, describe, expect, it, vi } from 'vitest';

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe('API proxy upstream protocol', () => {
  it('preserves TLS verification when loading development configuration', async () => {
    vi.stubEnv('NODE_ENV', 'development');
    vi.stubEnv('NODE_TLS_REJECT_UNAUTHORIZED', '1');
    await import('../../../next.config');
    expect(process.env.NODE_TLS_REJECT_UNAUTHORIZED).toBe('1');
  });

  it('uses the actual HTTPS API when a legacy HTTP alias is also configured', async () => {
    vi.stubEnv('API_URL_SERVER', 'https://api:8000');
    vi.stubEnv('API_URL_SERVER_HTTP', 'http://api:8000');
    const { default: config } = await import('../../../next.config');
    expect(await config.rewrites!()).toContainEqual({
      source: '/api/v1/:path*',
      destination: 'https://api:8000/api/v1/:path*',
    });
  });

  it('honors an explicitly configured HTTP API deployment', async () => {
    vi.stubEnv('API_URL_SERVER', 'http://api:8000');
    vi.stubEnv('API_URL_SERVER_HTTP', 'http://old-api:8000');
    const { default: config } = await import('../../../next.config');
    expect(await config.rewrites!()).toContainEqual({
      source: '/api/v1/:path*',
      destination: 'http://api:8000/api/v1/:path*',
    });
  });
});
